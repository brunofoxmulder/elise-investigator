from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

import main as base
from mcp_client import MCPReadOnlyClient, MCPReadOnlyError
from ui import INDEX_HTML as BASE_INDEX_HTML

VERSION = "0.2.0-dev.27"

_MCP_CARD = r'''
<div id="mcp_console" class="card">
  <p class="section-title">Recherche MCP locale</p>
  <p class="section-sub">Recherche multi-outils strictement en lecture seule. La synthèse est produite localement, sans IA, et ne modifie jamais le verdict causal d’Investigator.</p>
  <p id="mcp_status" class="small">Vérification de HA-MCP…</p>
  <details id="mcp_trace_contract_box" class="hidden">
    <summary>Contrat live ha_get_automation_traces</summary>
    <p id="mcp_trace_contract_note" class="small"></p>
    <pre id="mcp_trace_contract_json"></pre>
  </details>
  <label for="mcp_question">Question</label>
  <textarea id="mcp_question" placeholder="Ex. Pourquoi le volet salon est-il arrivé à 40 % ?"></textarea>
  <button id="mcp_go" type="button">Rechercher avec MCP</button>
</div>

<div id="mcp_result" class="card hidden">
  <div id="mcp_result_status" class="status"></div>
  <p id="mcp_answer"></p>
  <p id="mcp_provenance" class="small"></p>
  <p id="mcp_tools" class="small"></p>
  <p id="mcp_trace_summary" class="small"></p>
  <div id="mcp_text_actions" class="diag-actions hidden">
    <button id="mcp_copy_text" type="button" class="diag-copy">Texte</button>
    <p class="diag-note">Copie un résumé lisible du diagnostic MCP pour le coller dans une conversation. Rien n'est envoyé automatiquement et aucun secret ou endpoint MCP n'est inclus.</p>
  </div>
  <details><summary>Preuves et résultats MCP structurés</summary><pre id="mcp_json"></pre></details>
</div>
'''

_MCP_SCRIPT = r'''
const MCP_UI_VERSION='0.2.0-dev.27';
const mcpStatusEl=document.getElementById('mcp_status'),mcpGo=document.getElementById('mcp_go'),mcpQuestion=document.getElementById('mcp_question');
const mcpResult=document.getElementById('mcp_result'),mcpResultStatus=document.getElementById('mcp_result_status'),mcpAnswer=document.getElementById('mcp_answer'),mcpProvenance=document.getElementById('mcp_provenance'),mcpTools=document.getElementById('mcp_tools'),mcpTraceSummary=document.getElementById('mcp_trace_summary'),mcpJson=document.getElementById('mcp_json');
const mcpTraceBox=document.getElementById('mcp_trace_contract_box'),mcpTraceNote=document.getElementById('mcp_trace_contract_note'),mcpTraceJson=document.getElementById('mcp_trace_contract_json');
const mcpTextActions=document.getElementById('mcp_text_actions'),mcpCopyText=document.getElementById('mcp_copy_text');
let mcpAvailable=false,lastMcpResult=null;
function buildMcpShareText(d){
 const synth=d.local_synthesis||{},explore=d.trace_exploration||{};
 const facts=Array.isArray(synth.facts)?synth.facts:[];
 const current=facts.find(item=>item&&item.type==='current_state')||{};
 const recent=facts.find(item=>item&&item.type==='recent_history')||{};
 const events=Array.isArray(recent.events)?recent.events.slice(0,2):[];
 const leads=Array.isArray(synth.configuration_leads)?synth.configuration_leads.slice(0,6):[];
 const selected=explore.selected_run||null,detail=explore.selected_run_detail||null;
 const entity=entities.find(item=>item.entity_id===d.entity_id);
 const label=entity?entityLabel(entity):(d.entity_id||'');
 const lines=[
  'ÉLISE INVESTIGATOR — RÉSUMÉ MCP',
  'Version: '+MCP_UI_VERSION,
  'Objet: '+label,
  'Entity ID: '+(d.entity_id||''),
  'Question: '+(d.question||''),
  'Réponse: '+(synth.answer||d.answer||'')
 ];
 if(current.state!==undefined){let state='État courant: '+current.state;if(current.current_position!==null&&current.current_position!==undefined)state+=' · position '+current.current_position+' %';lines.push(state)}
 if(events.length){lines.push('Historique utile: '+events.map(event=>{let part=(event.time||'')+' · '+(event.state??'');if(event.current_position!==null&&event.current_position!==undefined)part+=' · position '+event.current_position+' %';return part}).join(' | '))}
 if(leads.length){lines.push('Candidats: '+leads.map(item=>(item.name||item.entity_id||'')+(item.entity_id&&item.name?' ['+item.entity_id+']':'')).join(' ; '))}
 lines.push('Traces: '+(explore.candidates_queried||0)+' candidat(s) interrogé(s) · détail '+(detail?'1':'0')+' · fenêtre '+Math.round((explore.max_event_distance_seconds||1800)/60)+' min');
 if(selected){lines.push('Piste détaillée: '+(selected.automation_id||'')+(selected.timestamp?' · '+(typeof selected.timestamp==='string'?selected.timestamp:(selected.timestamp.start||'')):'')+(selected.distance_seconds!==undefined?' · distance '+selected.distance_seconds+' s':''))}
 if(detail){const trigger=detail.trigger||{};const triggerLabel=typeof trigger==='string'?trigger:(trigger.description||trigger.platform||'');const detailBits=[];if(triggerLabel)detailBits.push('trigger '+triggerLabel);if(detail.condition_count!==undefined)detailBits.push('conditions '+detail.condition_count);if(detail.action_count!==undefined)detailBits.push('actions '+detail.action_count);if(detail.error)detailBits.push('erreur '+detail.error);if(detailBits.length)lines.push('Détail compact: '+detailBits.join(' · '))}
 lines.push('Outils: '+((d.tools_used||[]).join(', ')||'aucun'));
 lines.push('Lecture seule: '+(d.read_only===true?'oui':'non'));
 lines.push('IA: '+(synth.uses_llm?'oui':'non'));
 lines.push('Verdict causal Investigator: inchangé');
 lines.push('Sélection temporelle = preuve causale: non');
 return lines.join('\n');
}
async function loadMcpStatus(){
 try{
  const r=await fetch(api('api/v1/mcp/status'));const d=await r.json();
  mcpAvailable=!!d.available;
  if(mcpAvailable){
   const tools=Array.isArray(d.allowed_tools_available)?d.allowed_tools_available.join(', '):'';
   mcpStatusEl.textContent='HA-MCP connecté · lecture seule imposée par Investigator · '+(d.tool_count||0)+' outils'+(tools?' · autorisés ici : '+tools:'');
   const contract=d.trace_tool_contract;
   if(contract){
    mcpTraceNote.textContent='Contrat validé en dev.25 · ouvrir ce panneau n’appelle aucune trace. Dev.27 conserve l’exploration bornée de dev.26 et ajoute uniquement l’export Texte.';
    mcpTraceJson.textContent=JSON.stringify({inputSchema:contract.inputSchema||{},annotations:contract.annotations||{}},null,2);
    mcpTraceBox.classList.remove('hidden');
   }else if(d.trace_tool_contract_error){
    mcpTraceNote.textContent='Contrat traces indisponible : '+d.trace_tool_contract_error;
    mcpTraceJson.textContent='';mcpTraceBox.classList.remove('hidden');
   }
  }
  else{mcpStatusEl.textContent='HA-MCP indisponible : '+(d.error||'connexion non validée');}
 }catch(err){mcpAvailable=false;mcpStatusEl.textContent='HA-MCP indisponible : '+err.message;}
 mcpGo.disabled=!mcpAvailable;
}
mcpCopyText.addEventListener('click',async()=>{
 if(!lastMcpResult)return;
 const original=mcpCopyText.textContent;mcpCopyText.disabled=true;
 try{await copyText(buildMcpShareText(lastMcpResult));mcpCopyText.textContent='Texte copié ✓';mcpCopyText.classList.add('copied');setTimeout(()=>{mcpCopyText.textContent=original;mcpCopyText.classList.remove('copied')},1800)}
 catch(err){mcpCopyText.textContent='Copie impossible';setTimeout(()=>{mcpCopyText.textContent=original},2200)}
 finally{mcpCopyText.disabled=false}
});
mcpGo.addEventListener('click',async()=>{
 if(!entityEl.value){await loadEntities();const resolved=resolveTypedValue();if(resolved)setSelected(resolved)}
 if(!entityEl.value){renderError('Choisis d’abord un objet Home Assistant dans la liste.');return}
 const question=mcpQuestion.value.trim();if(!question){mcpQuestion.focus();return}
 mcpGo.disabled=true;mcpGo.textContent='Recherche MCP…';mcpResult.classList.add('hidden');mcpTextActions.classList.add('hidden');lastMcpResult=null;
 try{
  const r=await fetch(api('api/v1/mcp/search'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entity_id:entityEl.value,question})});
  const d=await r.json();if(!r.ok)throw new Error(d.error||'Recherche MCP impossible');
  const synth=d.local_synthesis||{},explore=d.trace_exploration||{};
  const explored=explore.trace_tool_called===true;
  mcpResultStatus.textContent=explored?'MCP LOCAL · EXPLORATION BORNÉE · LECTURE SEULE':(d.success?'MCP LOCAL · SYNTHÈSE DÉTERMINISTE · LECTURE SEULE':'MCP LOCAL · PARTIEL');mcpResultStatus.className='status '+(d.success?'confirmed':'indeterminate');
  mcpAnswer.textContent=synth.answer||d.answer||'';
  mcpProvenance.textContent='Source : '+(synth.source||'Recherche MCP locale')+' · IA : '+(synth.uses_llm?'oui':'non')+' · Verdict causal Investigator : inchangé';
  mcpTools.textContent='Outils utilisés : '+((d.tools_used||[]).join(', ')||'aucun');
  if(explored){const selected=explore.selected_run||{};mcpTraceSummary.textContent='Traces : '+(explore.candidates_queried||0)+' candidat(s) interrogé(s) · détail : '+(explore.selected_run_detail?'1':'0')+' · sélection temporelle = preuve causale : non'+(selected.automation_id?' · piste détaillée : '+selected.automation_id:'');}
  else{mcpTraceSummary.textContent='Traces : non appelées'+(explore.reason?' · '+explore.reason:'');}
  lastMcpResult=d;mcpTextActions.classList.remove('hidden');mcpJson.textContent=JSON.stringify(d,null,2);mcpResult.classList.remove('hidden');mcpResult.scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(err){mcpResultStatus.textContent='MCP LOCAL · ERREUR';mcpResultStatus.className='status indeterminate';mcpAnswer.textContent=err.message;mcpProvenance.textContent='';mcpTools.textContent='';mcpTraceSummary.textContent='';mcpJson.textContent='';mcpTextActions.classList.add('hidden');lastMcpResult=null;mcpResult.classList.remove('hidden');}
 finally{mcpGo.textContent='Rechercher avec MCP';mcpGo.disabled=!mcpAvailable;}
});
loadMcpStatus();
'''


def _extended_html() -> str:
    html = BASE_INDEX_HTML.replace("</main>", _MCP_CARD + "\n</main>", 1)
    return html.replace("</script>", _MCP_SCRIPT + "\n</script>", 1)


async def index(request: web.Request) -> web.Response:
    if request.path != "/":
        logging.getLogger(__name__).info(
            "Ingress root compatibility route matched path=%r x_ingress_path=%r",
            request.path,
            request.headers.get("X-Ingress-Path"),
        )
    return web.Response(text=_extended_html(), content_type="text/html")


async def mcp_status(request: web.Request) -> web.Response:
    client: MCPReadOnlyClient = request.app["mcp"]
    return web.json_response(await client.status())


async def mcp_search(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Corps JSON invalide", "read_only": True}, status=400)
    if not isinstance(data, dict):
        return web.json_response({"error": "Corps JSON invalide", "read_only": True}, status=400)
    entity_id = str(data.get("entity_id") or "").strip()
    question = str(data.get("question") or "").strip()
    if not entity_id:
        return web.json_response({"error": "entity_id est obligatoire", "read_only": True}, status=400)
    if not question:
        return web.json_response({"error": "question est obligatoire", "read_only": True}, status=400)

    client: MCPReadOnlyClient = request.app["mcp"]
    try:
        result = await client.research_entity(entity_id, question)
        return web.json_response(result)
    except MCPReadOnlyError as exc:
        return web.json_response(
            {"error": client.sanitize(str(exc)), "read_only": True}, status=503
        )
    except Exception:
        logging.getLogger(__name__).exception("MCP local research failed")
        return web.json_response(
            {"error": "Erreur interne pendant la recherche MCP", "read_only": True}, status=500
        )


async def create_app() -> web.Application:
    # Reuse the proven Investigator application unchanged, then attach the MCP
    # console as an isolated extension. This keeps the deterministic core intact.
    base.VERSION = VERSION
    base.index = index
    app = await base.create_app()
    app["mcp"] = MCPReadOnlyClient(app["session"])
    base.add_ingress_get(app, "/api/v1/mcp/status", mcp_status)
    base.add_ingress_post(app, "/api/v1/mcp/search", mcp_search)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
