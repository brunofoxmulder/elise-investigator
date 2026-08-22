INDEX_HTML = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Élise Investigator</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
body{margin:0;background:var(--bg,#f5f6f8);color:var(--fg,#202124)}
main{max-width:820px;margin:auto;padding:18px}
.card{background:var(--card,#fff);border-radius:18px;padding:18px;margin:0 0 14px;box-shadow:0 2px 12px #00000012}
h1{font-size:1.55rem;margin:0 0 5px}.sub{opacity:.72;margin:0}.badge{display:inline-block;border-radius:999px;padding:4px 9px;font-size:.78rem;background:#e8f5e9;color:#176b2c;font-weight:700}
label{display:block;font-weight:650;margin:13px 0 5px}input,textarea,button{font:inherit;box-sizing:border-box;width:100%;border-radius:12px;padding:11px;border:1px solid #aeb4bd;background:transparent;color:inherit}textarea{min-height:70px;resize:vertical}button{margin-top:16px;border:0;background:#3f51b5;color:#fff;font-weight:750;cursor:pointer}button:disabled{opacity:.55;cursor:wait}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:600px){.grid{grid-template-columns:1fr}}
#answer{font-size:1.05rem;line-height:1.5}.status{font-weight:800;text-transform:uppercase;font-size:.78rem;letter-spacing:.04em}.confirmed{color:#1b7f37}.probable{color:#b26a00}.indeterminate{color:#a72a2a}details{margin-top:12px}pre{white-space:pre-wrap;word-break:break-word;font-size:.78rem;background:#0000000c;padding:12px;border-radius:10px;max-height:420px;overflow:auto}.small{font-size:.86rem;opacity:.76}.token{font-family:ui-monospace,monospace;word-break:break-all;background:#0000000c;padding:8px;border-radius:8px}.hidden{display:none}
.picker{position:relative}.picker-help{font-size:.84rem;opacity:.72;margin:5px 0 0}.picker-list{position:absolute;z-index:20;left:0;right:0;top:100%;margin-top:5px;max-height:330px;overflow:auto;background:var(--card,#fff);border:1px solid #aeb4bd;border-radius:14px;box-shadow:0 12px 28px #0004}.picker-item{display:block;width:100%;text-align:left;border:0;border-radius:0;margin:0;padding:11px 13px;background:transparent;color:inherit;border-bottom:1px solid #8883}.picker-item:last-child{border-bottom:0}.picker-item:hover,.picker-item:focus{background:#8882}.picker-name{display:block;font-weight:700}.picker-meta{display:block;font-size:.78rem;opacity:.72;margin-top:2px;overflow-wrap:anywhere}.recent-wrap{margin-top:10px}.recent-title{font-size:.8rem;font-weight:700;opacity:.7;margin-bottom:6px}.recent-list{display:flex;gap:7px;flex-wrap:wrap}.recent-chip{width:auto;margin:0;padding:7px 10px;border:1px solid #8886;border-radius:999px;background:transparent;color:inherit;font-weight:600;font-size:.82rem}.selected-entity{font-size:.8rem;opacity:.75;margin-top:6px;overflow-wrap:anywhere}
.diag-actions{margin-top:14px}.diag-copy{margin-top:0;background:#455a64}.diag-copy.copied{background:#2e7d32}.diag-note{font-size:.78rem;opacity:.7;margin:7px 2px 0;line-height:1.4}
@media(prefers-color-scheme:dark){body{--bg:#111318;--fg:#e7e9ed;--card:#1b1e24}.badge{background:#153b20;color:#8ee9a4}}
</style>
</head>
<body><main>
<div class="card"><span class="badge">BÊTA 0.1 · LECTURE SEULE</span><h1>Élise Investigator</h1><p class="sub">Pourquoi cet objet a-t-il changé ?</p></div>
<form id="form" class="card">
<label for="entity_search">Objet Home Assistant *</label>
<div class="picker">
<input id="entity_search" autocomplete="off" placeholder="Ex. lampe entrée, volet salon…" aria-autocomplete="list" aria-expanded="false">
<input id="entity" name="entity_id" type="hidden">
<div id="picker_list" class="picker-list hidden" role="listbox"></div>
</div>
<p class="picker-help">Recherche par nom courant ou par Entity ID. Plus besoin de copier-coller depuis Home Assistant.</p>
<div id="selected_entity" class="selected-entity hidden"></div>
<div id="recent_wrap" class="recent-wrap hidden"><div class="recent-title">Récents</div><div id="recent_list" class="recent-list"></div></div>
<div class="grid"><div><label for="time">Heure observée</label><input id="time" name="observed_time" type="datetime-local"></div><div><label for="value">Valeur observée</label><input id="value" name="observed_value" placeholder="on, 20, open…"></div></div>
<label for="attribute">Attribut (facultatif)</label><input id="attribute" name="attribute" placeholder="temperature">
<label for="declaration">Ce que tu sais déjà (facultatif)</label><textarea id="declaration" name="user_declaration" placeholder="Ex. : c'est moi qui l'ai fait à la voix"></textarea>
<button id="go" type="submit">Enquêter</button>
</form>
<div id="result" class="card hidden"><div id="status" class="status"></div><p id="answer"></p><div id="limits"></div><details><summary>Voir les preuves structurées</summary><pre id="json"></pre></details><div id="diag_actions" class="diag-actions hidden"><button id="copy_diag" type="button" class="diag-copy">Copier le diagnostic pour Élise</button><p class="diag-note">Pour analyse uniquement. Rien n'est envoyé automatiquement et les secrets connus sont retirés avant copie.</p></div></div>
<div class="card"><strong>Connexion IA</strong><p class="small">Une IA conversationnelle peut appeler <code>POST /api/v1/investigate</code>. Le port réseau est désactivé par défaut ; s'il est activé dans les réglages réseau de l'App, ce jeton protège l'API directe.</p><div id="token" class="token">Chargement…</div><p class="small">Schéma machine : <code>openapi.json</code></p></div>
</main>
<script>
const form=document.getElementById('form'), btn=document.getElementById('go');
const result=document.getElementById('result'), statusEl=document.getElementById('status'), answer=document.getElementById('answer'), jsonEl=document.getElementById('json'), limits=document.getElementById('limits');
const diagActions=document.getElementById('diag_actions'), copyDiag=document.getElementById('copy_diag');
const searchEl=document.getElementById('entity_search'), entityEl=document.getElementById('entity'), pickerList=document.getElementById('picker_list'), selectedEl=document.getElementById('selected_entity'), recentWrap=document.getElementById('recent_wrap'), recentList=document.getElementById('recent_list');
let entities=[], entitiesLoaded=false, lastDiagnostic=null;
function api(path){return new URL(path, window.location.href).toString()}
function norm(v){return (v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim()}
function entityLabel(e){return e.name||e.entity_id}
async function loadEntities(){
 if(entitiesLoaded)return;
 try{
  const r=await fetch(api('api/v1/entities')); const d=await r.json(); if(!r.ok)throw new Error(d.error||'Impossible de charger les objets');
  entities=Array.isArray(d.entities)?d.entities:[]; entitiesLoaded=true; renderRecents();
 }catch(err){console.warn('Entity catalog unavailable',err)}
}
function scoreEntity(e,q){
 const n=norm(e.name), id=norm(e.entity_id), domain=norm(e.domain); if(!q)return 999;
 if(n===q)return 0; if(n.startsWith(q))return 1; if(n.includes(q))return 2; if(id===q)return 3; if(id.startsWith(q))return 4; if(id.includes(q))return 5; if(domain.includes(q))return 6; return 999;
}
function findMatches(q){
 const nq=norm(q); if(!nq)return [];
 return entities.map(e=>[scoreEntity(e,nq),e]).filter(x=>x[0]<999).sort((a,b)=>a[0]-b[0]||entityLabel(a[1]).localeCompare(entityLabel(b[1]),'fr')).slice(0,15).map(x=>x[1]);
}
function setSelected(e){
 entityEl.value=e.entity_id; searchEl.value=entityLabel(e); selectedEl.textContent=e.entity_id+(e.state!==undefined?' · état : '+e.state:''); selectedEl.classList.remove('hidden'); closePicker(); remember(e.entity_id);
}
function clearSelected(){entityEl.value=''; selectedEl.textContent=''; selectedEl.classList.add('hidden')}
function closePicker(){pickerList.classList.add('hidden');searchEl.setAttribute('aria-expanded','false')}
function openPicker(items){
 pickerList.innerHTML='';
 if(!items.length){closePicker();return}
 items.forEach(e=>{const b=document.createElement('button');b.type='button';b.className='picker-item';b.setAttribute('role','option');
  const name=document.createElement('span');name.className='picker-name';name.textContent=entityLabel(e);
  const meta=document.createElement('span');meta.className='picker-meta';meta.textContent=e.entity_id+(e.state!==undefined?' · '+e.state:'');
  b.append(name,meta);b.addEventListener('click',()=>setSelected(e));pickerList.appendChild(b)});
 pickerList.classList.remove('hidden');searchEl.setAttribute('aria-expanded','true');
}
function resolveTypedValue(){
 const q=norm(searchEl.value); if(!q)return null;
 const exactId=entities.find(e=>norm(e.entity_id)===q); if(exactId)return exactId;
 const exactNames=entities.filter(e=>norm(e.name)===q); return exactNames.length===1?exactNames[0]:null;
}
function getRecentIds(){try{return JSON.parse(localStorage.getItem('elise_recent_entities')||'[]')}catch{return []}}
function remember(id){const ids=[id,...getRecentIds().filter(x=>x!==id)].slice(0,6);localStorage.setItem('elise_recent_entities',JSON.stringify(ids));renderRecents()}
function renderRecents(){
 if(!entitiesLoaded)return; recentList.innerHTML=''; const recents=getRecentIds().map(id=>entities.find(e=>e.entity_id===id)).filter(Boolean);
 if(!recents.length){recentWrap.classList.add('hidden');return} recentWrap.classList.remove('hidden');
 recents.forEach(e=>{const b=document.createElement('button');b.type='button';b.className='recent-chip';b.textContent=entityLabel(e);b.addEventListener('click',()=>setSelected(e));recentList.appendChild(b)})
}
function sanitizeForAnalysis(value){
 if(Array.isArray(value))return value.map(sanitizeForAnalysis);
 if(value&&typeof value==='object'){
  const out={};
  for(const [key,item] of Object.entries(value)){
   if(/token|authorization|secret|password|api[_-]?key|access[_-]?token/i.test(key)){out[key]='[REDACTED]';continue}
   out[key]=sanitizeForAnalysis(item);
  }
  return out;
 }
 if(typeof value==='string')return value.replace(/Bearer\s+[A-Za-z0-9._~+\/=:-]+/gi,'Bearer [REDACTED]');
 return value;
}
function buildDiagnosticText(diagnostic){
 const clean=sanitizeForAnalysis(diagnostic);
 const response=clean.response||{};
 return [
  'ÉLISE INVESTIGATOR — DIAGNOSTIC POUR ANALYSE',
  'Version: 0.1.0-beta.9',
  'Objet: '+(clean.selection?.label||clean.selection?.entity_id||''),
  'Entity ID: '+(clean.selection?.entity_id||''),
  'Verdict: '+(response.status||''),
  'Réponse: '+(response.answer_text||''),
  '',
  'Diagnostic structuré:',
  JSON.stringify(clean,null,2)
 ].join('\n');
}
async function copyText(text){
 if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(text);return}
 const area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');area.style.position='fixed';area.style.opacity='0';area.style.pointerEvents='none';document.body.appendChild(area);area.select();area.setSelectionRange(0,area.value.length);
 const ok=document.execCommand('copy');area.remove();if(!ok)throw new Error('Copie impossible sur ce navigateur');
}
searchEl.addEventListener('focus',async()=>{await loadEntities();const q=searchEl.value.trim();if(q)openPicker(findMatches(q))});
searchEl.addEventListener('input',async()=>{clearSelected();await loadEntities();openPicker(findMatches(searchEl.value))});
searchEl.addEventListener('keydown',e=>{if(e.key==='Escape')closePicker()});
document.addEventListener('click',e=>{if(!e.target.closest('.picker'))closePicker()});
copyDiag.addEventListener('click',async()=>{
 if(!lastDiagnostic)return;
 const original=copyDiag.textContent;copyDiag.disabled=true;
 try{await copyText(buildDiagnosticText(lastDiagnostic));copyDiag.textContent='Diagnostic copié ✓';copyDiag.classList.add('copied');setTimeout(()=>{copyDiag.textContent=original;copyDiag.classList.remove('copied')},1800)}
 catch(err){copyDiag.textContent='Copie impossible';setTimeout(()=>{copyDiag.textContent=original},2200)}
 finally{copyDiag.disabled=false}
});
fetch(api('api/v1/connection')).then(r=>r.json()).then(d=>document.getElementById('token').textContent=d.api_token||'Indisponible').catch(()=>document.getElementById('token').textContent='Indisponible');
loadEntities();
form.addEventListener('submit',async e=>{e.preventDefault();
 if(!entityEl.value){await loadEntities();const resolved=resolveTypedValue();if(resolved)setSelected(resolved)}
 if(!entityEl.value){statusEl.textContent='CHOISIR UN OBJET';statusEl.className='status indeterminate';answer.textContent='Tape quelques lettres puis touche l’objet Home Assistant voulu dans la liste.';jsonEl.textContent='';limits.innerHTML='';lastDiagnostic=null;diagActions.classList.add('hidden');result.classList.remove('hidden');openPicker(findMatches(searchEl.value));return}
 btn.disabled=true;btn.textContent='Investigation…';result.classList.add('hidden');diagActions.classList.add('hidden');lastDiagnostic=null;
 const fd=new FormData(form), body={}; for(const [k,v] of fd.entries()){if(v!=='')body[k]=v}
 try{const r=await fetch(api('api/v1/investigate'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const d=await r.json(); if(!r.ok)throw new Error(d.error||d.message||'Erreur');
 statusEl.textContent='Cause '+d.status; statusEl.className='status '+d.status; answer.textContent=d.answer_text; jsonEl.textContent=JSON.stringify(d,null,2);
 limits.innerHTML=''; if(d.limits?.length){const ul=document.createElement('ul');d.limits.forEach(x=>{const li=document.createElement('li');li.textContent=x;ul.appendChild(li)});limits.appendChild(ul)}
 lastDiagnostic={selection:{label:searchEl.value,entity_id:entityEl.value},request:body,response:d};
 if(d.status==='probable'||d.status==='indeterminate')diagActions.classList.remove('hidden');else diagActions.classList.add('hidden');
 result.classList.remove('hidden');
 }catch(err){statusEl.textContent='ERREUR';statusEl.className='status indeterminate';answer.textContent=err.message;jsonEl.textContent='';lastDiagnostic=null;diagActions.classList.add('hidden');result.classList.remove('hidden')}finally{btn.disabled=false;btn.textContent='Enquêter'}
});
</script></body></html>'''
