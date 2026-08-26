from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

import main as base
from mcp_client import MCPReadOnlyClient, MCPReadOnlyError
from ui import INDEX_HTML as BASE_INDEX_HTML

VERSION = "0.2.0-dev.28"

_MCP_CARD = r'''
<div id="mcp_console" class="card">
  <p class="section-title">Recherche MCP locale</p>
  <p class="section-sub">Recherche multi-outils strictement en lecture seule. Choisis ici l'objet et pose ta question sans lancer Investigator. La synthèse est produite localement, sans IA, et ne modifie jamais le verdict causal d’Investigator.</p>
  <p id="mcp_status" class="small">Vérification de HA-MCP…</p>
  <details id="mcp_trace_contract_box" class="hidden">
    <summary>Contrat live ha_get_automation_traces</summary>
    <p id="mcp_trace_contract_note" class="small"></p>
    <pre id="mcp_trace_contract_json"></pre>
  </details>
  <label for="mcp_entity_search">Objet Home Assistant *</label>
  <div class="picker mcp-picker">
    <input id="mcp_entity_search" autocomplete="off" placeholder="Ex. lampe entrée, volet salon…" aria-autocomplete="list" aria-expanded="false">
    <input id="mcp_entity" type="hidden">
    <div id="mcp_picker_list" class="picker-list hidden" role="listbox"></div>
  </div>
  <p class="picker-help">Sélecteur MCP autonome · recherche par nom courant ou Entity ID.</p>
  <div id="mcp_selected_entity" class="selected-entity hidden"></div>
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
const MCP_UI_VERSION='0.2.0-dev.28';
const mcpStatusEl=document.getElementById('mcp_status'),mcpGo=document.getElementById('mcp_go'),mcpQuestion=document.getElementById('mcp_question');
const mcpEntitySearch=document.getElementById('mcp_entity_search'),mcpEntityEl=document.getElementById('mcp_entity'),mcpPickerList=document.getElementById('mcp_picker_list'),mcpSelectedEl=document.getElementById('mcp_selected_entity');
const mcpResult=document.getElementById('mcp_result'),mcpResultStatus=document.getElementById('mcp_result_status'),mcpAnswer=document.getElementById('mcp_answer'),mcpProvenance=document.getElementById('mcp_provenance'),mcpTools=document.getElementById('mcp_tools'),mcpTraceSummary=document.getElementById('mcp_trace_summary'),mcpJson=document.getElementById('mcp_json');
const mcpTraceBox=document.getElementById('mcp_trace_contract_box'),mcpTraceNote=document.getElementById('mcp_trace_contract_note'),mcpTraceJson=document.getElementById('mcp_trace_contract_json');
const mcpTextActions=document.getElementById('mcp_text_actions'),mcpCopyText=document.getElementById('mcp_copy_text');
let mcpAvailable=false,lastMcpResult=null,mcpEntities=[],mcpEntitiesLoaded=false;
function mcpNorm(v){return (v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim()}
function mcpEntityLabel(e){return e.name||e.entity_id}
async function loadMcpEntities(){
 if(mcpEntitiesLoaded)return;
 const r=await fetch(api('api/v1/entities'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Impossible de charger les objets Home Assistant');
 mcpEntities=Array.isArray(d.entities)?d.entities:[];mcpEntitiesLoaded=true;
}
function scoreMcpEntity(e,q){const n=mcpNorm(e.name),id=mcpNorm(e.entity_id),domain=mcpNorm(e.domain);if(!q)return 999;if(n===q)return 0;if(n.startsWith(q))return 1;if(n.includes(q))return 2;if(id===q)return 3;if(id.startsWith(q))return 4;if(id.includes(q))return 5;if(domain.includes(q))return 6;return 999}
function findMcpMatches(q){const nq=mcpNorm(q);if(!nq)return [];return mcpEntities.map(e=>[scoreMcpEntity(e,nq),e]).filter(x=>x[0]<999).sort((a,b)=>a[0]-b[0]||mcpEntityLabel(a[1]).localeCompare(mcpEntityLabel(b[1]),'fr')).slice(0,15).map(x=>x[1])}
function mcpSetSelected(e){mcpEntityEl.value=e.entity_id;mcpEntitySearch.value=mcpEntityLabel(e);mcpSelectedEl.textContent=e.entity_id+(e.state!==undefined?' · état : '+e.state:'');mcpSelectedEl.classList.remove('hidden');mcpClosePicker()}
function mcpClearSelected(){mcpEntityEl.value='';mcpSelectedEl.textContent='';mcpSelectedEl.classList.add('hidden')}
function mcpClosePicker(){mcpPickerList.classList.add('hidden');mcpEntitySearch.setAttribute('aria-expanded','false')}
function mcpOpenPicker(items){mcpPickerList.innerHTML='';if(!items.length){mcpClosePicker();return}items.forEach(e=>{const b=document.createElement('button');b.type='button';b.className='picker-item';b.setAttribute('role','option');const name=document.createElement('span');name.className='picker-name';name.textContent=mcpEntityLabel(e);const meta=document.createElement('span');meta.className='picker-meta';meta.textContent=e.entity_id+(e.state!==undefined?' · '+e.state:'');b.append(name,meta);b.addEventListener('click',()=>mcpSetSelected(e));mcpPickerList.appendChild(b)});mcpPickerList.classList.remove('hidden');mcpEntitySearch.setAttribute('aria-expanded','true')}
function mcpResolveTypedValue(){const q=mcpNorm(mcpEntitySearch.value);if(!q)return null;const exactId=mcpEntities.find(e=>mcpNorm(e.entity_id)===q);if(exactId)return exactId;const exactNames=mcpEntities.filter(e=>mcpNorm(e.name)===q);return exactNames.length===1?exactNames[0]:null}
function renderMcpError(message){mcpResultStatus.textContent='MCP LOCAL · À PRÉCISER';mcpResultStatus.className='status indeterminate';mcpAnswer.textContent=message;mcpProvenance.textContent='';mcpTools.textContent='';mcpTraceSummary.textContent='';mcpJson.textContent='';mcpTextActions.classList.add('hidden');lastMcpResult=null;mcpResult.classList.remove('hidden');mcpResult.scrollIntoView({behavior:'smooth',block:'nearest'})}
function buildMcpShareText(d){
 const synth=d.local_synthesis||{},explore=d.trace_exploration||{};
 const facts=Array.isArray(synth.facts)?synth.facts:[];
 const current=facts.find(item=>item&&item.type==='current_state')||{};
 const recent=facts.find(item=>item&&item.type==='recent_history')||{};
 const events=Array.isArray(recent.events)?recent.events.slice(0,2):[];
 const leads=Array.isArray(synth.configuration_leads)?synth.configuration_leads.slice(0,6):[];
 const selected=explore.selected_run||null,detail=explore.selected_run_detail||null;
 const entity=mcpEntities.find(item=>item.entity_id===d.entity_id);
 const label=entity?mcpEntityLabel(entity):(d.entity_id||'');
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
    mcpTraceNote.textContent='Contrat validé en dev.25 · ouvrir ce panneau n’appelle aucune trace. Dev.28 conserve dev.26/dev.27 et rend uniquement le sélecteur d’objet MCP autonome.';
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
mcpEntitySearch.addEventListener('focus',async()=>{try{await loadMcpEntities();const q=mcpEntitySearch.value.trim();if(q)mcpOpenPicker(findMcpMatches(q))}catch(err){renderMcpError(err.message)}});
mcpEntitySearch.addEventListener('input',async()=>{mcpClearSelected();try{await loadMcpEntities();mcpOpenPicker(findMcpMatches(mcpEntitySearch.value))}catch(err){renderMcpError(err.message)}});
mcpEntitySearch.addEventListener('keydown',e=>{if(e.key==='Escape')mcpClosePicker()});
document.addEventListener('click',e=>{if(!e.target.closest('.mcp-picker'))mcpClosePicker()});
mcpCopyText.addEventListener('click',async()=>{
 if(!lastMcpResult)return;
 const original=mcpCopyText.textContent;mcpCopyText.disabled=true;
 try{await copyText(buildMcpShareText(lastMcpResult));mcpCopyText.textContent='Texte copié ✓';mcpCopyText.classList.add('copied');setTimeout(()=>{mcpCopyText.textContent=original;mcpCopyText.classList.remove('copied')},1800)}
 catch(err){mcpCopyText.textContent='Copie impossible';setTimeout(()=>{mcpCopyText.textContent=original},2200)}
 finally{mcpCopyText.disabled=false}
});
mcpGo.addEventListener('click',async()=>{
 if(!mcpEntityEl.value){try{await loadMcpEntities();const resolved=mcpResolveTypedValue();if(resolved)mcpSetSelected(resolved)}catch(err){renderMcpError(err.message);return}}
 if(!mcpEntityEl.value){renderMcpError('Choisis un objet Home Assistant dans le sélecteur MCP.');mcpOpenPicker(findMcpMatches(mcpEntitySearch.value));return}
 const question=mcpQuestion.value.trim();if(!question){mcpQuestion.focus();return}
 mcpGo.disabled=true;mcpGo.textContent='Recherche MCP…';mcpResult.classList.add('hidden');mcpTextActions.classList.add('hidden');lastMcpResult=null;
 try{
  const r=await fetch(api('api/v1/mcp/search'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entity_id:mcpEntityEl.value,question})});
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
loadMcpEntities().catch(err=>console.warn('MCP entity catalog unavailable',err));
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
