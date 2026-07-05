"""KonformOS dashboard — a self-contained, production-grade single-page app
served at /app. No build step, no CDN (CSP/offline-safe inside the container):
system fonts, inline SVG, vanilla JS. Covers the full API surface — auth+MFA,
properties, fingerprint, compliance profile, scanning with live polling,
findings + AI/knowledge fixes, dossier + public verify, statement, timeline,
notifications, billing tiers, theme intelligence. Customer surface ONLY —
internal portals live in the isolated /admin console (ISO-01)."""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KonformOS — منصّة الامتثال الرقمي</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🛡️</text></svg>">
<style>
:root{
  --bg:#0b1020; --bg-2:#121a2e; --surface:#161f38; --surface-2:#1d2842;
  --border:#26324f; --border-2:#33436b;
  --text:#e8edf7; --muted:#93a1c0; --faint:#63719a;
  --accent:#5b8cff; --accent-2:#3f6fe0; --accent-soft:rgba(91,140,255,.14);
  --ok:#2fbf71; --warn:#e0a325; --bad:#ef5f6b;
  --crit:#ef5f6b; --serious:#f08a3c; --moderate:#e0a325; --minor:#7c8aad;
  --shadow:0 10px 40px -12px rgba(0,0,0,.55);
  --radius:14px; --radius-sm:10px;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue","Noto Sans Arabic",Arial,sans-serif;
}
:root[data-theme="light"]{
  --bg:#f3f5fb; --bg-2:#eef1f9; --surface:#ffffff; --surface-2:#f7f9fe;
  --border:#e3e8f4; --border-2:#d2dbef;
  --text:#131a2c; --muted:#586287; --faint:#8a94b4;
  --accent:#3f6fe0; --accent-2:#2f57c0; --accent-soft:rgba(63,111,224,.10);
  --shadow:0 10px 34px -14px rgba(31,45,90,.22);
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);font-family:var(--font);
  font-size:14.5px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
button{font-family:inherit;cursor:pointer}
input,select,textarea{font-family:inherit}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--border-2);border-radius:8px}

/* ---------- primitives ---------- */
.btn{border:1px solid transparent;border-radius:var(--radius-sm);padding:.5rem .9rem;
  font-weight:600;font-size:.85rem;background:var(--accent);color:#fff;transition:.15s;
  display:inline-flex;align-items:center;gap:.4rem;white-space:nowrap}
.btn:hover{background:var(--accent-2)}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn.ghost{background:transparent;border-color:var(--border-2);color:var(--text)}
.btn.ghost:hover{background:var(--surface-2)}
.btn.soft{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.btn.sm{padding:.32rem .6rem;font-size:.78rem}
.btn.danger{background:transparent;border-color:var(--bad);color:var(--bad)}
.btn.danger:hover{background:rgba(239,95,107,.12)}
.input{width:100%;background:var(--surface-2);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:.55rem .7rem;color:var(--text);font-size:.9rem}
.input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
label.fld{display:block;margin-bottom:.7rem}
label.fld > span{display:block;font-size:.78rem;color:var(--muted);margin-bottom:.28rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:1.15rem 1.25rem;box-shadow:var(--shadow)}
.card h3{margin:0 0 .9rem;font-size:1rem;display:flex;align-items:center;gap:.5rem}
.muted{color:var(--muted)} .faint{color:var(--faint)} .small{font-size:.8rem}
.row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
.spread{display:flex;justify-content:space-between;align-items:center;gap:1rem}
.grid{display:grid;gap:1rem}
.pill{display:inline-flex;align-items:center;gap:.35rem;padding:.15rem .55rem;border-radius:999px;
  font-size:.72rem;font-weight:700;background:var(--surface-2);border:1px solid var(--border)}
.dot{width:.5rem;height:.5rem;border-radius:50%;display:inline-block}
.badge{padding:.12rem .5rem;border-radius:6px;font-size:.7rem;font-weight:700}
.sev-critical{background:rgba(239,95,107,.16);color:var(--crit)}
.sev-serious{background:rgba(240,138,60,.16);color:var(--serious)}
.sev-moderate{background:rgba(224,163,37,.16);color:var(--moderate)}
.sev-minor{background:rgba(124,138,173,.16);color:var(--minor)}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:right;color:var(--muted);font-weight:600;font-size:.75rem;
  padding:.5rem .6rem;border-bottom:1px solid var(--border)}
td{padding:.6rem;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
.divider{height:1px;background:var(--border);margin:1rem 0}

/* ---------- layout ---------- */
#app{min-height:100vh;display:flex;flex-direction:column}
.topbar{height:60px;display:flex;align-items:center;gap:1rem;padding:0 1.2rem;
  border-bottom:1px solid var(--border);background:var(--bg-2);position:sticky;top:0;z-index:20}
.brand{font-weight:800;font-size:1.05rem;letter-spacing:-.01em;display:flex;align-items:center;gap:.5rem}
.brand .v{font-size:.62rem;background:var(--accent-soft);color:var(--accent);
  padding:.08rem .4rem;border-radius:6px;font-weight:700}
.shell{flex:1;display:flex;min-height:0}
.sidebar{width:230px;border-left:1px solid var(--border);background:var(--bg-2);
  padding:.9rem;display:flex;flex-direction:column;gap:.2rem;overflow-y:auto}
.nav-item{display:flex;align-items:center;gap:.65rem;padding:.6rem .7rem;border-radius:var(--radius-sm);
  color:var(--muted);font-weight:600;font-size:.88rem;transition:.12s;border:1px solid transparent}
.nav-item:hover{background:var(--surface);color:var(--text)}
.nav-item.active{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.nav-item svg{width:18px;height:18px;flex:none}
.nav-sec{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--faint);
  padding:.9rem .7rem .3rem}
.main{flex:1;overflow-y:auto;padding:1.5rem;max-width:1180px;width:100%;margin:0 auto}
.page-title{font-size:1.5rem;font-weight:800;margin:0 0 .2rem;letter-spacing:-.02em}
.page-sub{color:var(--muted);margin:0 0 1.4rem}

/* metric tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:1.4rem}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.2rem}
.tile .k{font-size:.78rem;color:var(--muted);display:flex;align-items:center;gap:.45rem}
.tile .v{font-size:2rem;font-weight:800;margin-top:.3rem;letter-spacing:-.02em}
.tile .s{font-size:.75rem;color:var(--faint);margin-top:.15rem}

/* gauge */
.gauge{display:flex;flex-direction:column;align-items:center;gap:.3rem}
.gauge svg{transform:rotate(-90deg)}
.gauge .lbl{font-weight:800;font-size:1.15rem}

/* auth */
.auth-wrap{max-width:440px;margin:8vh auto;padding:0 1rem}
.auth-logo{text-align:center;font-size:1.8rem;font-weight:800;margin-bottom:.2rem}
.auth-tag{text-align:center;color:var(--muted);margin-bottom:1.8rem}
.tabs{display:flex;background:var(--surface-2);border-radius:var(--radius-sm);padding:.25rem;margin-bottom:1.1rem}
.tabs button{flex:1;border:none;background:transparent;color:var(--muted);padding:.5rem;
  border-radius:8px;font-weight:700;font-size:.85rem}
.tabs button.active{background:var(--surface);color:var(--text);box-shadow:0 2px 8px -3px rgba(0,0,0,.4)}

/* drawer */
.drawer-bg{position:fixed;inset:0;background:rgba(6,10,22,.55);backdrop-filter:blur(2px);
  z-index:40;opacity:0;pointer-events:none;transition:.2s}
.drawer-bg.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;bottom:0;left:0;width:min(520px,92vw);background:var(--surface);
  border-left:1px solid var(--border);z-index:41;transform:translateX(-100%);transition:.25s;
  display:flex;flex-direction:column;box-shadow:var(--shadow)}
.drawer.open{transform:translateX(0)}
.drawer-head{padding:1.1rem 1.25rem;border-bottom:1px solid var(--border);display:flex;
  justify-content:space-between;align-items:center}
.drawer-body{padding:1.25rem;overflow-y:auto;flex:1}

/* toasts */
#toasts{position:fixed;bottom:1.2rem;left:1.2rem;z-index:60;display:flex;flex-direction:column;gap:.6rem}
.toast{background:var(--surface);border:1px solid var(--border);border-right:3px solid var(--accent);
  border-radius:var(--radius-sm);padding:.7rem 1rem;box-shadow:var(--shadow);min-width:260px;
  animation:slidein .25s;font-size:.85rem}
.toast.ok{border-right-color:var(--ok)} .toast.err{border-right-color:var(--bad)}
@keyframes slidein{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}
.spinner{width:16px;height:16px;border:2px solid var(--border-2);border-top-color:var(--accent);
  border-radius:50%;animation:spin .7s linear infinite;display:inline-block}
@keyframes spin{to{transform:rotate(360deg)}}
.progress{height:6px;background:var(--surface-2);border-radius:6px;overflow:hidden}
.progress > div{height:100%;background:var(--accent);width:0;transition:width .4s}
.hidden{display:none!important}
.empty{text-align:center;color:var(--faint);padding:2.5rem 1rem;font-size:.9rem}
.tierbox{border:1px solid var(--border);border-radius:var(--radius);padding:1rem;position:relative}
.tierbox.cur{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.tierbox .tn{font-weight:800;font-size:1rem;text-transform:capitalize}
.check{color:var(--ok)} .cross{color:var(--faint)}
@media(max-width:820px){.sidebar{display:none}}
</style>
</head>
<body>
<div id="app"></div>
<div id="toasts"></div>

<script>
"use strict";
// ─────────────────────────────────────────────────────────── state + api
const S = {
  token: localStorage.getItem("k_token") || "",
  org: null, view: "overview", properties: [], notifications: [],
  activeProp: null, activeScan: null, authTab: "login",
};
const $ = (h) => { const t=document.createElement("template"); t.innerHTML=h.trim(); return t.content.firstElementChild; };
const esc = (s)=> String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function api(path, opts={}){
  const res = await fetch(path, {...opts, headers:{
    "Content-Type":"application/json",
    ...(S.token?{"Authorization":"Bearer "+S.token}:{}), ...(opts.headers||{})}});
  let data=null; try{ data=await res.json(); }catch(e){}
  if(!res.ok){
    const err=(data&&data.error)||{}; const msg=err.message||("خطأ "+res.status);
    if(res.status===401 && S.token && path!=="/v1/auth/login"){ logout(); }
    throw new Error(msg);
  }
  return data;
}
async function apiForm(path, formData){
  const res=await fetch(path,{method:"POST",headers:S.token?{"Authorization":"Bearer "+S.token}:{},body:formData});
  let data=null; try{data=await res.json();}catch(e){}
  if(!res.ok){ throw new Error(((data&&data.error)||{}).message||("خطأ "+res.status)); }
  return data;
}
function toast(msg,kind=""){ const t=$(`<div class="toast ${kind}">${esc(msg)}</div>`);
  document.getElementById("toasts").appendChild(t); setTimeout(()=>{t.style.opacity="0";setTimeout(()=>t.remove(),300);},3800); }
const ok=(m)=>toast(m,"ok"); const fail=(m)=>toast(m,"err");
async function guard(fn){ try{ return await fn(); }catch(e){ fail(e.message); } }

// ─────────────────────────────────────────────────────────── helpers
function rColor(v){ return v>=80?"var(--ok)":v>=50?"var(--warn)":"var(--bad)"; }
function gauge(v,size=92){ if(v==null) v=0; const r=(size/2)-8, c=2*Math.PI*r, off=c*(1-v/100);
  return `<div class="gauge"><svg width="${size}" height="${size}">
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--surface-2)" stroke-width="8"/>
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${rColor(v)}" stroke-width="8"
      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"/></svg>
    <div class="lbl" style="color:${rColor(v)}">${v}</div></div>`; }
function readinessPills(rc){ if(!rc||!Object.keys(rc).length) return `<span class="faint">—</span>`;
  return Object.entries(rc).map(([j,s])=>`<span class="pill"><span class="dot" style="background:${rColor(s)}"></span>${esc(j)} ${s}</span>`).join(" "); }
const ICON={
  overview:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>',
  props:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21V8l9-5 9 5v13"/><path d="M9 21v-6h6v6"/></svg>',
  bell:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>',
  billing:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
  settings:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H1a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 2.6 7"/></svg>',
};

// ─────────────────────────────────────────────────────────── auth screens
function renderAuth(){
  const app=document.getElementById("app");
  app.innerHTML="";
  const login=S.authTab==="login";
  app.appendChild($(`<div class="auth-wrap">
    <div class="auth-logo">🛡️ KonformOS</div>
    <div class="auth-tag">بنية الامتثال الرقمي للتجارة — WCAG · EN 301 549 · BFSG</div>
    <div class="card">
      <div class="tabs">
        <button class="${login?'active':''}" id="tab-login">دخول</button>
        <button class="${!login?'active':''}" id="tab-reg">تسجيل جديد</button>
      </div>
      <div id="auth-form"></div>
    </div>
    <p class="small faint" style="text-align:center;margin-top:1rem">
      كلمة المرور 12 محرفاً على الأقل · بياناتك معزولة بـ RLS لكل منظمة</p>
  </div>`));
  document.getElementById("tab-login").onclick=()=>{S.authTab="login";renderAuth();};
  document.getElementById("tab-reg").onclick=()=>{S.authTab="reg";renderAuth();};
  const f=document.getElementById("auth-form");
  if(login){
    f.appendChild($(`<div>
      <label class="fld"><span>البريد الإلكتروني</span><input class="input" id="l-email" type="email" placeholder="you@shop.de"></label>
      <label class="fld"><span>كلمة المرور</span><input class="input" id="l-pw" type="password" placeholder="••••••••••••"></label>
      <label class="fld"><span>رمز MFA (إن كان مفعّلاً)</span><input class="input" id="l-totp" placeholder="اختياري — 6 أرقام"></label>
      <button class="btn" id="do-login" style="width:100%">دخول</button></div>`));
    document.getElementById("do-login").onclick=doLogin;
  }else{
    f.appendChild($(`<div>
      <label class="fld"><span>اسم المنظمة</span><input class="input" id="r-org" placeholder="متجر برلين"></label>
      <label class="fld"><span>النوع</span><select class="input" id="r-type">
        <option value="merchant">تاجر (Merchant)</option><option value="agency">وكالة (Agency)</option></select></label>
      <label class="fld"><span>البريد الإلكتروني</span><input class="input" id="r-email" type="email" placeholder="you@shop.de"></label>
      <label class="fld"><span>كلمة المرور (12+ محرفاً)</span><input class="input" id="r-pw" type="password" placeholder="••••••••••••"></label>
      <button class="btn" id="do-reg" style="width:100%">إنشاء الحساب</button></div>`));
    document.getElementById("do-reg").onclick=doRegister;
  }
}
async function doLogin(){ await guard(async()=>{
  const body={email:val("l-email"),password:val("l-pw")};
  const totp=val("l-totp"); if(totp) body.totp_code=totp;
  const d=await api("/v1/auth/login",{method:"POST",body:JSON.stringify(body)});
  S.token=d.token; localStorage.setItem("k_token",S.token); ok("مرحباً بعودتك"); await boot();
});}
async function doRegister(){ await guard(async()=>{
  const d=await api("/v1/auth/register",{method:"POST",body:JSON.stringify({
    organization_name:val("r-org")||"My Shop", organization_type:val("r-type"),
    email:val("r-email"), password:val("r-pw")})});
  S.token=d.token; localStorage.setItem("k_token",S.token); ok("تم إنشاء الحساب"); await boot();
});}
const val=(id)=>{const e=document.getElementById(id);return e?e.value.trim():"";};
function logout(){ S.token=""; S.org=null; localStorage.removeItem("k_token"); renderAuth(); }

// ─────────────────────────────────────────────────────────── shell
function roles(){ return (S.org&&S.org.role)||"owner"; }
// ISO-01: internal portals live on the SEPARATE /admin console — this bundle
// contains zero admin code. Internal roles just get a doorway link.
function isInternal(){ return ["legal_curator","expert_reviewer","admin"].includes(roles()); }
function renderShell(){
  const app=document.getElementById("app");
  const nav=[
    ["overview","نظرة عامة",ICON.overview],
    ["props","المتاجر",ICON.props],
    ["notifications","الإشعارات",ICON.bell],
    ["billing","الاشتراك",ICON.billing],
    ["settings","الإعدادات",ICON.settings],
  ];
  const sub=S.org&&S.org.subscription;
  app.innerHTML="";
  app.appendChild($(`<div>
    <div class="topbar">
      <div class="brand" title="لوحة التحكم">🛡️ KonformOS <span class="v">SaaS</span></div>
      <div style="flex:1"></div>
      <span class="pill">${esc((S.org&&S.org.name)||"")}${sub?` · <span style="color:var(--accent)">${esc(sub.tier)}</span>`:""}</span>
      <button class="btn ghost sm" id="theme-btn" title="المظهر">🌓</button>
      <button class="btn ghost sm" id="logout-btn">خروج</button>
    </div>
    <div class="shell">
      <aside class="sidebar" id="sidebar"></aside>
      <main class="main" id="main"></main>
    </div>
    <div class="drawer-bg" id="drawer-bg"></div>
    <div class="drawer" id="drawer">
      <div class="drawer-head"><strong id="drawer-title"></strong>
        <button class="btn ghost sm" id="drawer-close">✕</button></div>
      <div class="drawer-body" id="drawer-body"></div>
    </div>
  </div>`));
  const sb=document.getElementById("sidebar");
  nav.forEach(([id,label,icon])=>sb.appendChild(navItem(id,label,icon)));
  if(isInternal()){ sb.appendChild($(`<div class="nav-sec">داخلي</div>`));
    const door=$(`<a class="nav-item" href="/admin">${ICON.settings}<span>لوحة التحكم الإدارية ↗</span></a>`);
    sb.appendChild(door); }
  document.getElementById("theme-btn").onclick=toggleTheme;
  document.getElementById("logout-btn").onclick=logout;
  document.getElementById("drawer-close").onclick=closeDrawer;
  document.getElementById("drawer-bg").onclick=closeDrawer;
  route();
}
function navItem(id,label,icon){ const el=$(`<a class="nav-item ${S.view===id?'active':''}">${icon}<span>${label}</span></a>`);
  el.onclick=()=>{S.view=id;route();document.querySelectorAll(".nav-item").forEach(n=>n.classList.remove("active"));el.classList.add("active");};
  return el; }
function toggleTheme(){ const r=document.documentElement; const t=r.getAttribute("data-theme")==="dark"?"light":"dark";
  r.setAttribute("data-theme",t); localStorage.setItem("k_theme",t); }
function openDrawer(title,html){ document.getElementById("drawer-title").textContent=title;
  document.getElementById("drawer-body").innerHTML=""; if(typeof html==="string") document.getElementById("drawer-body").innerHTML=html;
  else document.getElementById("drawer-body").appendChild(html);
  document.getElementById("drawer").classList.add("open"); document.getElementById("drawer-bg").classList.add("open"); }
function closeDrawer(){ document.getElementById("drawer").classList.remove("open"); document.getElementById("drawer-bg").classList.remove("open"); }

// ─────────────────────────────────────────────────────────── router
function route(){ const m=document.getElementById("main"); if(!m)return;
  ({overview:viewOverview,props:viewProps,notifications:viewNotifs,billing:viewBilling,
    settings:viewSettings,property:viewProperty}[S.view]||viewOverview)(m); }

// ─────────────────────────────────────────────────────────── overview
async function viewOverview(m){
  m.innerHTML=`<h1 class="page-title">نظرة عامة</h1><p class="page-sub">حالة الامتثال عبر متاجرك — موثّقة زمنياً وقابلة للتقديم للجهات الرقابية.</p><div id="ov"></div>`;
  await guard(async()=>{
    const [props,notifs]=await Promise.all([api("/v1/properties"),api("/v1/notifications")]);
    S.properties=props.properties; S.notifications=notifs.notifications;
    const scores=[]; props.properties.forEach(p=>{ if(p.readiness_current) Object.values(p.readiness_current).forEach(v=>scores.push(v)); });
    const avg=scores.length?Math.round(scores.reduce((a,b)=>a+b,0)/scores.length):null;
    const ov=document.getElementById("ov");
    ov.innerHTML=`<div class="tiles">
      <div class="tile"><div class="k">${ICON.props} المتاجر</div><div class="v">${props.properties.length}</div><div class="s">Properties خاضعة للمراقبة</div></div>
      <div class="tile"><div class="k">📊 متوسط الجاهزية</div><div class="v" style="color:${avg==null?'var(--faint)':rColor(avg)}">${avg==null?'—':avg}</div><div class="s">عبر كل الولايات</div></div>
      <div class="tile"><div class="k">🔔 الإشعارات</div><div class="v">${notifs.notifications.length}</div><div class="s">أحداث حديثة</div></div>
      <div class="tile"><div class="k">💳 المستوى</div><div class="v" style="font-size:1.3rem;text-transform:capitalize">${esc((S.org.subscription||{}).tier||'—')}</div><div class="s">${esc((S.org.subscription||{}).status||'')}</div></div>
    </div>
    <div class="grid" style="grid-template-columns:1.4fr 1fr">
      <div class="card"><h3>جاهزية المتاجر</h3><div id="ov-props"></div></div>
      <div class="card"><h3>آخر الأحداث</h3><div id="ov-notifs"></div></div>
    </div>`;
    const pd=document.getElementById("ov-props");
    if(!props.properties.length) pd.innerHTML=`<div class="empty">لا متاجر بعد — أضف متجرك الأول من قسم «المتاجر».</div>`;
    else pd.innerHTML=`<table><thead><tr><th>المتجر</th><th>الجاهزية</th><th></th></tr></thead><tbody>${
      props.properties.map(p=>`<tr><td><strong>${esc(p.label||"—")}</strong><br><span class="faint small">${esc(p.url)}</span></td>
        <td>${readinessPills(p.readiness_current)}</td>
        <td><button class="btn soft sm" onclick="openProp('${p.id}')">فتح</button></td></tr>`).join("")}</tbody></table>`;
    document.getElementById("ov-notifs").innerHTML=notifList(notifs.notifications.slice(0,6));
  });
}
function notifList(list){ if(!list.length) return `<div class="empty">لا إشعارات.</div>`;
  const emoji={scan_done:"✅",readiness_drop:"📉",legal_update:"⚖️",drift:"🔀"};
  return list.map(n=>`<div class="row" style="padding:.5rem 0;border-bottom:1px solid var(--border);align-items:flex-start">
    <span>${emoji[n.type]||"🔔"}</span><div style="flex:1"><div class="small"><strong>${esc(n.type)}</strong></div>
    <div class="faint small">${esc((n.payload&&(n.payload.message||JSON.stringify(n.payload)))||"").slice(0,90)}</div></div></div>`).join(""); }

// ─────────────────────────────────────────────────────────── properties
async function viewProps(m){
  m.innerHTML=`<div class="spread"><div><h1 class="page-title">المتاجر</h1>
    <p class="page-sub">كل متجر خاضع للفحص متعدد المدخلات والتقييم متعدد الولايات.</p></div></div>
    <div class="card" style="margin-bottom:1.2rem"><h3>إضافة متجر</h3>
      <div class="row"><input class="input" id="np-url" placeholder="https://www.shop.de" style="flex:2">
        <input class="input" id="np-label" placeholder="اسم ودّي" style="flex:1">
        <button class="btn" id="np-add">إضافة</button></div>
      <p class="faint small" style="margin:.6rem 0 0">النطاقات الخاصة/localhost مرفوضة (حماية SSRF) ما لم تُفعّل بيئة التطوير.</p></div>
    <div id="plist"></div>`;
  document.getElementById("np-add").onclick=()=>guard(async()=>{
    await api("/v1/properties",{method:"POST",body:JSON.stringify({url:val("np-url"),label:val("np-label")})});
    ok("أُضيف المتجر"); viewProps(m); });
  await guard(async()=>{
    const d=await api("/v1/properties"); S.properties=d.properties;
    const pl=document.getElementById("plist");
    if(!d.properties.length){ pl.innerHTML=`<div class="empty">لا متاجر بعد.</div>`; return; }
    pl.innerHTML=`<div class="card"><table><thead><tr><th>المتجر</th><th>الجاهزية</th><th>إجراءات</th></tr></thead><tbody>${
      d.properties.map(p=>`<tr>
        <td><strong>${esc(p.label||"—")}</strong><br><span class="faint small">${esc(p.url)}</span></td>
        <td>${readinessPills(p.readiness_current)}</td>
        <td><button class="btn soft sm" onclick="openProp('${p.id}')">فتح لوحة المتجر ←</button></td>
      </tr>`).join("")}</tbody></table></div>`;
  });
}
window.openProp=(id)=>{ S.activeProp=S.properties.find(p=>p.id===id)||{id}; S.view="property"; route(); };

// ─────────────────────────────────────────────────────────── property workspace
async function viewProperty(m){
  const p=S.activeProp; if(!p){ S.view="props"; return route(); }
  m.innerHTML=`<button class="btn ghost sm" onclick="S.view='props';route()">← رجوع للمتاجر</button>
    <h1 class="page-title" style="margin-top:.7rem">${esc(p.label||p.url||"المتجر")}</h1>
    <p class="page-sub">${esc(p.url||"")}</p>
    <div class="grid" style="grid-template-columns:1fr 1fr 1fr;margin-bottom:1.2rem">
      <div class="card"><h3>🔎 البصمة التقنية</h3><div id="fp-box"><span class="faint small">لم تُكشف بعد.</span></div>
        <button class="btn soft sm" id="fp-btn" style="margin-top:.8rem">كشف الـStack</button></div>
      <div class="card"><h3>⚖️ الملف القانوني</h3><div id="prof-box"></div></div>
      <div class="card"><h3>▶️ فحص</h3><div id="scan-box">
        <div class="row"><button class="btn" id="scan-url">فحص URL حيّ</button></div>
        <div class="progress hidden" id="scan-prog" style="margin-top:.8rem"><div></div></div>
        <div id="scan-status" class="small faint" style="margin-top:.5rem"></div>
        <div class="divider"></div>
        <div class="row small">
          <label class="btn ghost sm">📦 ثيم(zip)<input type="file" id="up-theme" class="hidden"></label>
          <label class="btn ghost sm">📄 PDF<input type="file" id="up-pdf" class="hidden"></label>
        </div><div class="faint small" style="margin-top:.4rem">مدخلات الكود تتطلب مستوى dev+</div>
      </div></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr;margin-bottom:1.2rem">
      <div class="card"><div class="spread"><h3 style="margin:0">📋 النتائج (Findings)</h3>
        <div class="row">
          <button class="btn soft sm" id="gen-dossier">🗂️ توليد Dossier</button>
          <button class="btn ghost sm" id="gen-statement">§ بيان الوصولية</button>
          <button class="btn ghost sm" id="show-timeline">🕓 السجل المختوم</button>
        </div></div>
        <div id="readiness-box" style="margin:1rem 0"></div>
        <div id="findings-box"><div class="empty">شغّل فحصاً لعرض النتائج.</div></div></div>
    </div>`;
  // fingerprint
  document.getElementById("fp-btn").onclick=()=>guard(async()=>{
    setBtn("fp-btn",true,"يكشف…");
    const d=await api(`/v1/properties/${p.id}/fingerprint`,{method:"POST"});
    document.getElementById("fp-box").innerHTML=`
      <div class="row"><span class="pill">🏷️ ${esc(d.platform_display||d.platform)}</span>
      ${d.platform_version?`<span class="pill">v${esc(d.platform_version)}</span>`:""}
      ${d.theme&&d.theme.name?`<span class="pill">🎨 ${esc(d.theme.name)}</span>`:""}</div>
      <div class="small faint" style="margin-top:.5rem">ثقة المنصة: ${Math.round((d.detection_confidence.platform||0)*100)}%
        ${d.drift?' · <span style="color:var(--warn)">⚠️ Drift مكتشف</span>':''}</div>
      <div id="ti-box" style="margin-top:.6rem"></div>`;
    setBtn("fp-btn",false,"إعادة الكشف");
    // proactive theme intelligence
    if(d.theme&&d.theme.name){ try{
      const ti=await api("/v1/preview",{method:"POST",body:JSON.stringify({platform:d.platform,theme_name:d.theme.name,
        theme_version:d.platform_version,theme_confidence:(d.detection_confidence.theme||0)})});
      document.getElementById("ti-box").innerHTML=`<div class="pill" style="background:var(--accent-soft);color:var(--accent)">
        🧠 ${esc(ti.statement)}</div>`;
    }catch(e){} }
  });
  // compliance profile
  renderProfileBox(p);
  // scan url
  document.getElementById("scan-url").onclick=()=>runScan(p,()=>api(`/v1/properties/${p.id}/scans`,{method:"POST",body:JSON.stringify({input_type:"url"})}));
  document.getElementById("up-theme").onchange=(e)=>uploadScan(p,e.target.files[0],"theme");
  document.getElementById("up-pdf").onchange=(e)=>uploadScan(p,e.target.files[0],"pdf");
  document.getElementById("gen-dossier").onclick=()=>genDossier(p);
  document.getElementById("gen-statement").onclick=()=>genStatement(p);
  document.getElementById("show-timeline").onclick=()=>showTimeline(p);
  // load latest completed scan if any
  loadLatestScan(p);
}
function renderProfileBox(p){
  const box=document.getElementById("prof-box");
  box.innerHTML=`<label class="fld"><span>الولايات</span>
    <div class="row small" id="jur">${["DE","EU","US"].map(j=>`<label class="pill"><input type="checkbox" value="${j}" ${j==="DE"?"checked":""}> ${j}</label>`).join("")}</div></label>
    <label class="fld"><span>الدمج</span><select class="input" id="cmode">
      <option value="strictest">strictest (الأشد)</option><option value="union">union (اجمع الكل)</option></select></label>
    <button class="btn soft sm" id="save-prof">حفظ الملف</button>`;
  document.getElementById("save-prof").onclick=()=>guard(async()=>{
    const jur=[...document.querySelectorAll("#jur input:checked")].map(c=>c.value);
    if(!jur.length) return fail("اختر ولاية واحدة على الأقل");
    await api(`/v1/properties/${p.id}/compliance-profile`,{method:"PUT",body:JSON.stringify({
      selected_jurisdictions:jur,pack_binding:"latest",combination_mode:val("cmode")})});
    ok("حُفظ الملف القانوني"); });
}
function setBtn(id,busy,txt){ const b=document.getElementById(id); if(!b)return;
  b.disabled=busy; b.innerHTML=busy?`<span class="spinner"></span> ${txt||""}`:(txt||b.textContent); }

async function runScan(p,starter){
  await guard(async()=>{
    const prog=document.getElementById("scan-prog"), st=document.getElementById("scan-status");
    prog.classList.remove("hidden"); const bar=prog.firstElementChild; bar.style.width="8%";
    st.textContent="الفحص في الطابور…";
    const d=await starter(); const sid=d.scan_id; let pct=8;
    const poll=setInterval(async()=>{ pct=Math.min(pct+9,88); bar.style.width=pct+"%";
      const s=await api(`/v1/scans/${sid}`);
      st.textContent="الحالة: "+s.status;
      if(s.status==="completed"||s.status==="failed"){ clearInterval(poll); bar.style.width="100%";
        if(s.status==="failed"){ fail("فشل الفحص: "+((s.error||{}).message||"")); }
        else { ok("اكتمل الفحص"); S.activeScan=sid; renderScanResult(p,sid,s); }
        setTimeout(()=>prog.classList.add("hidden"),700);
      }
    },1400);
  });
}
async function uploadScan(p,file,kind){ if(!file)return; await guard(async()=>{
  const fd=new FormData(); fd.append("input_type",kind); fd.append("file",file);
  document.getElementById("scan-status").textContent="جارٍ الرفع…";
  const d=await apiForm(`/v1/properties/${p.id}/scans/upload`,fd);
  const sid=d.scan_id; const st=document.getElementById("scan-status");
  const poll=setInterval(async()=>{ const s=await api(`/v1/scans/${sid}`); st.textContent="الحالة: "+s.status;
    if(s.status==="completed"||s.status==="failed"){ clearInterval(poll);
      if(s.status==="failed") fail("فشل الفحص"); else { ok("اكتمل فحص "+kind); S.activeScan=sid; renderScanResult(p,sid,s);} }
  },1400);
});}
async function loadLatestScan(p){ /* best-effort: show nothing until a scan runs */ }

async function renderScanResult(p,sid,s){
  const rb=document.getElementById("readiness-box");
  if(s.readiness){ rb.innerHTML=`<div class="row" style="gap:1.6rem">${
    Object.entries(s.readiness).map(([j,r])=>`<div style="text-align:center">${gauge(r.score)}
      <div class="small muted">${esc(j)}</div><div class="faint small">${esc(r.computed_against_pack)}</div></div>`).join("")}
    <div class="small faint" style="align-self:center">المحرّكات: ${esc(Object.keys(s.engine_versions||{}).join(", "))}</div></div>`; }
  await guard(async()=>{
    const f=await api(`/v1/scans/${sid}/findings`);
    const fb=document.getElementById("findings-box");
    if(!f.findings.length){ fb.innerHTML=`<div class="empty">🎉 لا عيوب مكتشفة في هذا الفحص.</div>`; return; }
    fb.innerHTML=`<table><thead><tr><th>القاعدة</th><th>الشدة</th><th>الموقع</th><th>الحالة</th><th></th></tr></thead><tbody>${
      f.findings.map(x=>`<tr>
        <td><code class="small">${esc(x.rule_code)}</code></td>
        <td><span class="badge sev-${x.severity}">${esc(x.severity)}</span></td>
        <td class="small faint">${esc((x.location&&(x.location.selector||x.location.page))||"—")}</td>
        <td><span class="pill small">${esc(x.status)}</span></td>
        <td><button class="btn soft sm" onclick='openFix(${JSON.stringify(JSON.stringify(x))})'>الإصلاح</button></td>
      </tr>`).join("")}</tbody></table>`;
  });
}
window.openFix=(raw)=>{ const x=JSON.parse(raw); guard(async()=>{
  openDrawer("إصلاح: "+x.rule_code,`<div class="row"><span class="spinner"></span> جارٍ جلب الإصلاح…</div>`);
  const d=await api(`/v1/findings/${x.id}/fix`);
  const srcLabel={ai_generated:"🤖 مولّد بـ Claude",knowledge_graph:"🧠 من قاعدة المعرفة",manual_guidance:"📖 إرشاد يدوي"}[d.source]||d.source;
  const body=$(`<div>
    <div class="row"><span class="pill">${srcLabel}</span>
      ${d.fix_success_rate!=null?`<span class="pill">نجاح ${Math.round(d.fix_success_rate*100)}%</span>`:""}
      ${d.seen_in_stores?`<span class="pill">${d.seen_in_stores} متجر</span>`:""}</div>
    <div class="card" style="margin-top:1rem;background:var(--surface-2)"><div class="small muted">الشرح</div>
      <div style="margin-top:.4rem;white-space:pre-wrap">${esc(d.fix.explanation||"")}</div></div>
    ${d.fix.diff?`<div class="card" style="margin-top:.8rem"><div class="small muted">Patch مقترح</div>
      <pre style="overflow-x:auto;font-size:.78rem;margin:.4rem 0 0">${esc(d.fix.diff)}</pre></div>`:""}
    <div class="pill" style="margin-top:1rem;background:rgba(224,163,37,.14);color:var(--warn)">${esc(d.notice||"")}</div>
    <div class="divider"></div>
    <div class="row">
      <button class="btn soft sm" onclick="markFinding('${x.id}','fixed')">✔ تم الإصلاح</button>
      <button class="btn ghost sm" onclick="markWontFix('${x.id}')">لن يُصلح</button>
      <button class="btn ghost sm" onclick="markFinding('${x.id}','false_positive')">إيجابي كاذب</button>
    </div></div>`);
  document.getElementById("drawer-body").innerHTML=""; document.getElementById("drawer-body").appendChild(body);
});};
window.markFinding=(id,status)=>guard(async()=>{ await api(`/v1/findings/${id}`,{method:"PATCH",body:JSON.stringify({status})});
  ok("حُدّثت الحالة"); closeDrawer(); if(S.activeScan) renderScanResult(S.activeProp,S.activeScan,await api(`/v1/scans/${S.activeScan}`)); });
window.markWontFix=(id)=>{ const reason=prompt("سبب عدم الإصلاح (يظهر في الـDossier):"); if(!reason)return;
  guard(async()=>{ await api(`/v1/findings/${id}`,{method:"PATCH",body:JSON.stringify({status:"wont_fix",reason})});
    ok("سُجّل"); closeDrawer(); }); };

async function genDossier(p){ await guard(async()=>{
  const d=await api(`/v1/properties/${p.id}/dossier`,{method:"POST"});
  openDrawer("Dossier مختوم",`<p class="muted">تم توليد حزمة تدقيق موثّقة زمنياً.</p>
    <label class="fld"><span>ختم الحزمة (SHA-256)</span><input class="input" readonly value="${esc(d.dossier_hash)}"></label>
    <div class="row"><a class="btn" href="${d.pdf}" target="_blank">⬇️ تحميل PDF</a>
      <a class="btn ghost" href="${d.verify_url}/page" target="_blank">🔗 صفحة التحقق العامة</a></div>
    <p class="faint small" style="margin-top:1rem">صفحة التحقق عامة بلا حساب — قابلة للتقديم لأي جهة رقابية.</p>`);
  ok("تم توليد الـDossier"); });
}
async function genStatement(p){ await guard(async()=>{
  const d=await api(`/v1/properties/${p.id}/statement`,{method:"POST"});
  openDrawer("بيان الوصولية",`<pre style="white-space:pre-wrap;font-family:var(--font);font-size:.85rem">${esc(d.statement)}</pre>`);
});}
async function showTimeline(p){ await guard(async()=>{
  const d=await api(`/v1/properties/${p.id}/timeline`);
  const rows=d.events.map(e=>`<div class="row" style="align-items:flex-start;padding:.5rem 0;border-bottom:1px solid var(--border)">
    <span class="pill small">#${e.sequence_number}</span><div style="flex:1"><strong class="small">${esc(e.event_type)}</strong>
    <div class="faint small">${esc(e.created_at)}</div><code class="faint" style="font-size:.68rem">${esc(e.content_hash.slice(0,24))}…</code></div></div>`).join("");
  openDrawer("السجل المختوم (Hash-Chain)",rows||`<div class="empty">لا أحداث بعد.</div>`);
});}

// ─────────────────────────────────────────────────────────── notifications
async function viewNotifs(m){
  m.innerHTML=`<h1 class="page-title">الإشعارات</h1><p class="page-sub">تحديثات القانون، هبوط الجاهزية، Drift، واكتمال الفحوصات.</p><div class="card" id="nb"></div>`;
  await guard(async()=>{ const d=await api("/v1/notifications");
    document.getElementById("nb").innerHTML=notifList(d.notifications); });
}

// ─────────────────────────────────────────────────────────── billing
function viewBilling(m){
  const sub=S.org.subscription||{}; const caps=sub.capabilities||{};
  const tiers=[
    ["free_scan","مجاني","فحص واحد + جاهزية"],
    ["report","تقرير","Dossier لمرة واحدة"],
    ["monitoring","مراقبة","فحص مستمر + Timeline حيّ"],
    ["dev","مطوّر","+ مدخلات Theme/Plugin/PDF"],
    ["agency","وكالة","مقاعد متعددة + عملاء"]];
  m.innerHTML=`<h1 class="page-title">الاشتراك</h1><p class="page-sub">مستواك الحالي:
    <strong style="text-transform:capitalize;color:var(--accent)">${esc(sub.tier||"—")}</strong> (${esc(sub.status||"")}).</p>
    <div class="tiles">${tiers.map(([id,name,desc])=>`<div class="tierbox ${sub.tier===id?'cur':''}">
      ${sub.tier===id?'<span class="pill" style="position:absolute;top:.7rem;left:.7rem;background:var(--accent);color:#fff">الحالي</span>':''}
      <div class="tn">${name}</div><div class="faint small" style="margin:.3rem 0 .6rem">${desc}</div></div>`).join("")}</div>
    <div class="card"><h3>قدرات مستواك الحالي</h3><table><tbody>
      ${Object.entries(caps).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${
        v===true?'<span class="check">✔</span>':v===false?'<span class="cross">✘</span>':esc(v)}</td></tr>`).join("")}
    </tbody></table>
    <p class="faint small" style="margin-top:1rem">الترقية تتم عبر Stripe (webhooks). في بيئة العرض تُحقن الحالة من الخادم.</p></div>`;
}

// ─────────────────────────────────────────────────────────── settings
function viewSettings(m){
  const org=S.org;
  m.innerHTML=`<h1 class="page-title">الإعدادات</h1><p class="page-sub">الخصوصية، المصادقة الثنائية، والـwebhooks الصادرة.</p>
    <div class="grid" style="grid-template-columns:1fr 1fr">
      <div class="card"><h3>🔐 مشاركة البيانات (الخندق)</h3>
        <p class="muted small">تفعيلها يسمح بتغذية الخندق المعرفي ببيانات مجهّلة تماماً (بلا هوية) لتحسين الإصلاحات للجميع.</p>
        <label class="row" style="margin-top:.6rem"><input type="checkbox" id="consent" ${org.data_sharing_consent?"checked":""}> موافقة المشاركة</label>
        <button class="btn soft sm" id="save-consent" style="margin-top:.8rem">حفظ</button></div>
      <div class="card"><h3>📱 المصادقة الثنائية (TOTP)</h3>
        <p class="muted small">إلزامية للأدوار الحسّاسة. أنشئ سرّاً ثم أدخِل الرمز من تطبيق المصادقة.</p>
        <button class="btn soft sm" id="mfa-setup" style="margin-top:.6rem">إنشاء سرّ MFA</button>
        <div id="mfa-box" style="margin-top:.8rem"></div></div>
      <div class="card"><h3>🔗 Webhook صادر</h3>
        <p class="muted small">يستقبل أحداث scan.completed / readiness.changed / legal.pack_published موقّعة HMAC.</p>
        <div class="row" style="margin-top:.6rem"><input class="input" id="wh-url" placeholder="https://you.example/hook">
          <button class="btn soft sm" id="wh-add">إضافة</button></div><div id="wh-box"></div></div>
      <div class="card"><h3>🧠 استعلام Theme Intelligence</h3>
        <p class="muted small">ماذا يعرف الخندق مسبقاً عن ثيم معيّن قبل أي فحص.</p>
        <div class="row" style="margin-top:.6rem"><input class="input" id="ti-plat" placeholder="shopware">
          <input class="input" id="ti-theme" placeholder="vision"><button class="btn soft sm" id="ti-go">استعلام</button></div>
        <div id="ti-out" style="margin-top:.6rem"></div></div>
    </div>`;
  document.getElementById("save-consent").onclick=()=>guard(async()=>{
    await api("/v1/orgs/me",{method:"PATCH",body:JSON.stringify({data_sharing_consent:document.getElementById("consent").checked})});
    S.org.data_sharing_consent=document.getElementById("consent").checked; ok("حُفظت الموافقة"); });
  document.getElementById("mfa-setup").onclick=()=>guard(async()=>{
    const d=await api("/v1/auth/mfa/setup",{method:"POST"});
    document.getElementById("mfa-box").innerHTML=`<label class="fld"><span>السرّ (أدخله في تطبيق المصادقة)</span>
      <input class="input" readonly value="${esc(d.secret)}"></label>
      <div class="row"><input class="input" id="mfa-code" placeholder="الرمز 6 أرقام"><button class="btn soft sm" id="mfa-verify">تأكيد</button></div>`;
    document.getElementById("mfa-verify").onclick=()=>guard(async()=>{
      const r=await api("/v1/auth/mfa/verify",{method:"POST",body:JSON.stringify({code:val("mfa-code")})});
      S.token=r.token; localStorage.setItem("k_token",S.token); ok("فُعّلت المصادقة الثنائية"); }); });
  document.getElementById("wh-add").onclick=()=>guard(async()=>{
    const d=await api("/v1/webhook-endpoints",{method:"POST",body:JSON.stringify({url:val("wh-url")})});
    document.getElementById("wh-box").innerHTML=`<div class="pill" style="margin-top:.6rem">السرّ (يُعرض مرة واحدة): <code>${esc(d.secret)}</code></div>`;
    ok("أُضيف الـendpoint"); });
  document.getElementById("ti-go").onclick=()=>guard(async()=>{
    const d=await api("/v1/preview",{method:"POST",body:JSON.stringify({platform:val("ti-plat"),theme_name:val("ti-theme"),theme_confidence:0.95})});
    document.getElementById("ti-out").innerHTML=`<div class="pill" style="background:var(--accent-soft);color:var(--accent)">🧠 ${esc(d.statement)}</div>
      <div class="faint small" style="margin-top:.4rem">التوقيع: ${esc(d.stack_signature)}</div>`; });
}

// ─────────────────────────────────────────────────────────── boot
async function boot(){
  try{ S.org=await api("/v1/orgs/me"); }catch(e){ return logout(); }
  renderShell();
}
(function init(){
  const t=localStorage.getItem("k_theme"); if(t) document.documentElement.setAttribute("data-theme",t);
  // ISO-04: admin "view as client" — session-scoped read-only token from the
  // URL hash. Never persisted; every write is refused server-side anyway.
  const m=location.hash.match(/^#imp=(.+)$/);
  if(m){ S.token=decodeURIComponent(m[1]); S.imp=true; history.replaceState(null,"","/app");
    const b=$(`<div style="position:sticky;top:0;z-index:99;background:rgba(251,191,36,.14);color:var(--warn,#fbbf24);
      border-bottom:1px solid rgba(251,191,36,.4);padding:.4rem 1rem;font-size:.85rem;text-align:center">
      🔭 جلسة انتحال للقراءة فقط — كل الكتابات مرفوضة، والجلسة مسجّلة في سجل التدقيق</div>`);
    document.body.prepend(b); }
  if(S.token) boot(); else renderAuth();
})();
</script>
</body>
</html>"""
