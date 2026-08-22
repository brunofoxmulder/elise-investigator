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
#answer{font-size:1.05rem;line-height:1.5}.status{font-weight:800;text-transform:uppercase;font-size:.78rem;letter-spacing:.04em}.confirmed{color:#1b7f37}.probable{color:#b26a00}.indeterminate{color:#a72a2a}details{margin-top:12px}pre{white-space:pre-wrap;word-break:break-word;font-size:.78rem;background:#0000000c;padding:12px;border-radius:10px;max-height:420px;overflow:auto}.small{font-size:.86rem;opacity:.76}.token{font-family:ui-monospace,monospace;word-break:break-all;background:#0000000c;padding:8px;border-radius:8px}.hidden{display:none}@media(prefers-color-scheme:dark){body{--bg:#111318;--fg:#e7e9ed;--card:#1b1e24}.badge{background:#153b20;color:#8ee9a4}}
</style>
</head>
<body><main>
<div class="card"><span class="badge">BÊTA 0.1 · LECTURE SEULE</span><h1>Élise Investigator</h1><p class="sub">Pourquoi cet objet a-t-il changé ?</p></div>
<form id="form" class="card">
<label for="entity">Entity ID *</label><input id="entity" name="entity_id" required autocomplete="off" placeholder="light.lampe_entree">
<div class="grid"><div><label for="time">Heure observée</label><input id="time" name="observed_time" type="datetime-local"></div><div><label for="value">Valeur observée</label><input id="value" name="observed_value" placeholder="on, 20, open…"></div></div>
<label for="attribute">Attribut (facultatif)</label><input id="attribute" name="attribute" placeholder="temperature">
<label for="declaration">Ce que tu sais déjà (facultatif)</label><textarea id="declaration" name="user_declaration" placeholder="Ex. : c'est moi qui l'ai fait à la voix"></textarea>
<button id="go" type="submit">Enquêter</button>
</form>
<div id="result" class="card hidden"><div id="status" class="status"></div><p id="answer"></p><div id="limits"></div><details><summary>Voir les preuves structurées</summary><pre id="json"></pre></details></div>
<div class="card"><strong>Connexion IA</strong><p class="small">Une IA conversationnelle peut appeler <code>POST /api/v1/investigate</code>. Le port réseau est désactivé par défaut ; s'il est activé dans les réglages réseau de l'App, ce jeton protège l'API directe.</p><div id="token" class="token">Chargement…</div><p class="small">Schéma machine : <code>openapi.json</code></p></div>
</main>
<script>
const form=document.getElementById('form'), btn=document.getElementById('go');
const result=document.getElementById('result'), statusEl=document.getElementById('status'), answer=document.getElementById('answer'), jsonEl=document.getElementById('json'), limits=document.getElementById('limits');
function api(path){return new URL(path, window.location.href).toString()}
fetch(api('api/v1/connection')).then(r=>r.json()).then(d=>document.getElementById('token').textContent=d.api_token||'Indisponible').catch(()=>document.getElementById('token').textContent='Indisponible');
form.addEventListener('submit',async e=>{e.preventDefault();btn.disabled=true;btn.textContent='Investigation…';result.classList.add('hidden');
 const fd=new FormData(form), body={}; for(const [k,v] of fd.entries()){if(v!=='')body[k]=v}
 try{const r=await fetch(api('api/v1/investigate'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const d=await r.json(); if(!r.ok)throw new Error(d.error||d.message||'Erreur');
 statusEl.textContent='Cause '+d.status; statusEl.className='status '+d.status; answer.textContent=d.answer_text; jsonEl.textContent=JSON.stringify(d,null,2);
 limits.innerHTML=''; if(d.limits?.length){const ul=document.createElement('ul');d.limits.forEach(x=>{const li=document.createElement('li');li.textContent=x;ul.appendChild(li)});limits.appendChild(ul)} result.classList.remove('hidden');
 }catch(err){statusEl.textContent='ERREUR';statusEl.className='status indeterminate';answer.textContent=err.message;jsonEl.textContent='';result.classList.remove('hidden')}finally{btn.disabled=false;btn.textContent='Enquêter'}
});
</script></body></html>'''
