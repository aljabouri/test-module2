"""Minimal v0 dashboard (vanilla JS, RTL) — the Next.js frontend replaces this;
same API endpoints underneath."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KonformOS — لوحة التحكم</title>
<style>
  body{font-family:sans-serif;max-width:860px;margin:1.5rem auto;padding:0 1rem;background:#fafafa}
  section{background:#fff;border:1px solid #ddd;border-radius:8px;padding:1rem;margin-bottom:1rem}
  h1{font-size:1.4rem} h2{font-size:1.05rem;margin-top:0}
  input,button,select{padding:.45rem .6rem;margin:.15rem;border:1px solid #bbb;border-radius:6px}
  button{background:#1a56db;color:#fff;border:none;cursor:pointer}
  button.secondary{background:#555}
  table{border-collapse:collapse;width:100%} td,th{border:1px solid #ddd;padding:.4rem;text-align:right}
  .score{font-weight:bold} .ok{color:#0a7d33} .warn{color:#b45309} .bad{color:#b91c1c}
  pre{background:#f4f4f4;padding:.6rem;border-radius:6px;overflow-x:auto;font-size:.8rem}
  #status{color:#555;font-size:.85rem}
</style>
</head>
<body>
<h1>KonformOS — لوحة التحكم <small style="color:#888;font-size:.6em">v0</small></h1>
<p id="status"></p>

<section id="auth">
  <h2>الدخول / التسجيل</h2>
  <input id="org" placeholder="اسم المنظمة">
  <input id="email" placeholder="البريد" type="email">
  <input id="pw" placeholder="كلمة المرور (12+ محرفاً)" type="password">
  <button onclick="register()">تسجيل</button>
  <button class="secondary" onclick="login()">دخول</button>
</section>

<section id="props" style="display:none">
  <h2>المتاجر (Properties)</h2>
  <input id="url" placeholder="https://shop.example.de">
  <input id="label" placeholder="اسم ودّي">
  <button onclick="addProperty()">إضافة</button>
  <table id="ptable"><thead><tr>
    <th>المتجر</th><th>Readiness</th><th>إجراءات</th></tr></thead><tbody></tbody></table>
</section>

<section id="out" style="display:none"><h2>النتيجة</h2><pre id="result"></pre></section>

<script>
let token = localStorage.getItem('k_token') || '';
const $ = id => document.getElementById(id);
const api = async (path, opts={}) => {
  const res = await fetch(path, {...opts, headers: {
    'Content-Type':'application/json',
    ...(token ? {'Authorization':'Bearer '+token} : {}), ...(opts.headers||{})}});
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error((data.error&&data.error.message)||res.status);
  return data;
};
const show = obj => { $('out').style.display='block'; $('result').textContent = JSON.stringify(obj,null,2); };
const flash = msg => { $('status').textContent = msg; };

async function register(){
  try{ const d = await api('/v1/auth/register',{method:'POST',body:JSON.stringify({
    organization_name:$('org').value||'My Shop', email:$('email').value, password:$('pw').value})});
    token=d.token; localStorage.setItem('k_token',token); flash('تم التسجيل ✓'); refresh();
  }catch(e){ flash('خطأ: '+e.message); }
}
async function login(){
  try{ const d = await api('/v1/auth/login',{method:'POST',body:JSON.stringify({
    email:$('email').value, password:$('pw').value})});
    token=d.token; localStorage.setItem('k_token',token); flash('تم الدخول ✓'); refresh();
  }catch(e){ flash('خطأ: '+e.message); }
}
async function addProperty(){
  try{ await api('/v1/properties',{method:'POST',body:JSON.stringify({
    url:$('url').value, label:$('label').value})}); refresh();
  }catch(e){ flash('خطأ: '+e.message); }
}
function cls(s){ return s>=80?'ok':(s>=50?'warn':'bad'); }
async function refresh(){
  if(!token) return;
  try{
    const d = await api('/v1/properties');
    $('props').style.display='block';
    const tb = $('ptable').querySelector('tbody'); tb.innerHTML='';
    for(const p of d.properties){
      const r = p.readiness_current
        ? Object.entries(p.readiness_current).map(([j,s])=>`<span class="score ${cls(s)}">${j}: ${s}</span>`).join(' · ')
        : '—';
      tb.insertAdjacentHTML('beforeend', `<tr><td>${p.label||''}<br><small>${p.url}</small></td>
        <td>${r}</td>
        <td><button onclick="fp('${p.id}')">بصمة</button>
            <button onclick="scan('${p.id}')">فحص</button>
            <button class="secondary" onclick="dossier('${p.id}')">Dossier</button></td></tr>`);
    }
  }catch(e){ flash('خطأ: '+e.message); }
}
async function fp(id){ try{ show(await api(`/v1/properties/${id}/fingerprint`,{method:'POST'})); }catch(e){ flash('خطأ: '+e.message);} }
async function scan(id){
  try{
    const d = await api(`/v1/properties/${id}/scans`,{method:'POST',body:JSON.stringify({input_type:'url'})});
    flash('فحص في الطابور… '+d.scan_id);
    const poll = setInterval(async ()=>{
      const s = await api(d.poll);
      if(s.status==='completed'||s.status==='failed'){ clearInterval(poll); show(s); flash('الفحص: '+s.status); refresh(); }
    }, 1500);
  }catch(e){ flash('خطأ: '+e.message); }
}
async function dossier(id){
  try{ const d = await api(`/v1/properties/${id}/dossier`,{method:'POST'});
    show(d); window.open(d.verify_url+'/page','_blank');
  }catch(e){ flash('خطأ: '+e.message); }
}
refresh();
</script>
</body>
</html>"""
