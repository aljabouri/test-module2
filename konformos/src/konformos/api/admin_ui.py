"""KonformOS admin console — the isolated control plane SPA served at /admin.

ISO-01 by construction: a SEPARATE bundle from the customer app. Login is
step-up: password → app token → fresh TOTP → 15-minute aud=admin token.
The console keeps BOTH tokens: the admin token drives /v1/admin/* (clients,
audit, system) and the app token drives the legacy internal portals
(/v1/legal/*, /v1/expert/*) which remain role-guarded server-side.

Self-contained: no build step, no CDN (CSP/offline safe), RTL, dark
command-center identity distinct from the customer workspace."""

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KonformOS Admin — غرفة العمليات</title>
<style>
:root{
  --bg:#0b0e14;--bg2:#11151f;--card:#151b28;--card2:#1a2133;--border:#232c42;
  --text:#e6ebf5;--muted:#8b96ad;--faint:#5b6478;
  --accent:#a78bfa;--accent-soft:rgba(167,139,250,.14);
  --amber:#fbbf24;--green:#34d399;--red:#f87171;--blue:#60a5fa;
  --shadow:0 10px 30px rgba(0,0,0,.45);
  --r:14px;--r-sm:9px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;background:var(--bg);color:var(--text);font-size:15px;line-height:1.6}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(900px 400px at 85% -5%,rgba(167,139,250,.09),transparent),
             radial-gradient(700px 380px at 10% 110%,rgba(96,165,250,.07),transparent)}
#app{position:relative;z-index:1;min-height:100vh}
a{color:var(--accent)}
button{font:inherit;cursor:pointer}
input,select,textarea{font:inherit;background:var(--bg2);border:1px solid var(--border);color:var(--text);border-radius:var(--r-sm);padding:.55rem .8rem;width:100%}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.btn{background:var(--accent);color:#12081f;border:none;border-radius:var(--r-sm);padding:.55rem 1.1rem;font-weight:700}
.btn:hover{filter:brightness(1.1)}
.btn.soft{background:var(--accent-soft);color:var(--accent)}
.btn.ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn.danger{background:rgba(248,113,113,.15);color:var(--red)}
.btn.sm{padding:.3rem .7rem;font-size:.82rem}
.topbar{display:flex;align-items:center;gap:.8rem;padding:.7rem 1.2rem;border-bottom:1px solid var(--border);background:rgba(11,14,20,.85);backdrop-filter:blur(8px);position:sticky;top:0;z-index:20}
.brand{font-weight:800;display:flex;align-items:center;gap:.5rem}
.brand .v{font-size:.62rem;background:var(--accent-soft);color:var(--accent);padding:.1rem .45rem;border-radius:99px;letter-spacing:.06em}
.ttl{font-size:.7rem;color:var(--amber);border:1px solid rgba(251,191,36,.35);border-radius:99px;padding:.12rem .55rem}
.shell{display:grid;grid-template-columns:230px 1fr;min-height:calc(100vh - 57px)}
.sidebar{border-inline-end:1px solid var(--border);padding:1rem .7rem;background:var(--bg2)}
.nav-item{display:flex;align-items:center;gap:.6rem;padding:.55rem .8rem;border-radius:var(--r-sm);color:var(--muted);cursor:pointer;font-size:.92rem;text-decoration:none;margin-bottom:2px}
.nav-item:hover{background:var(--card);color:var(--text)}
.nav-item.active{background:var(--accent-soft);color:var(--accent);font-weight:700}
.nav-sec{font-size:.68rem;color:var(--faint);letter-spacing:.1em;margin:1rem .8rem .3rem}
.main{padding:1.4rem 1.8rem;max-width:1220px}
.page-title{font-size:1.35rem;font-weight:800;margin-bottom:.15rem}
.page-sub{color:var(--muted);font-size:.9rem;margin-bottom:1.2rem}
.grid{display:grid;gap:1rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.8rem;margin-bottom:1rem}
.tile{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:.9rem 1rem}
.tile .k{font-size:1.5rem;font-weight:800}
.tile .l{color:var(--muted);font-size:.78rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1.1rem;box-shadow:var(--shadow)}
.card h3{font-size:.95rem;margin-bottom:.7rem}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th{text-align:right;color:var(--faint);font-size:.72rem;letter-spacing:.05em;padding:.45rem .6rem;border-bottom:1px solid var(--border)}
td{padding:.55rem .6rem;border-bottom:1px solid var(--border);vertical-align:middle}
tr:hover td{background:rgba(255,255,255,.02)}
.pill{display:inline-flex;align-items:center;gap:.3rem;background:var(--bg2);border:1px solid var(--border);border-radius:99px;padding:.14rem .6rem;font-size:.78rem}
.small{font-size:.82rem}.faint{color:var(--faint)}.muted{color:var(--muted)}
.hbar{height:7px;border-radius:99px;background:var(--bg2);overflow:hidden;min-width:70px}
.hbar>i{display:block;height:100%;border-radius:99px}
.lc{font-size:.72rem;border-radius:99px;padding:.1rem .5rem;font-weight:700}
.lc.onboarding{background:rgba(96,165,250,.15);color:var(--blue)}
.lc.active{background:rgba(52,211,153,.15);color:var(--green)}
.lc.at_risk{background:rgba(251,191,36,.15);color:var(--amber)}
.lc.dormant{background:rgba(139,150,173,.15);color:var(--muted)}
.lc.churned,.lc.suspended{background:rgba(248,113,113,.15);color:var(--red)}
.empty{color:var(--faint);padding:1.2rem;text-align:center;border:1px dashed var(--border);border-radius:var(--r-sm)}
.drawer-bg{position:fixed;inset:0;background:rgba(0,0,0,.55);opacity:0;pointer-events:none;transition:.2s;z-index:30}
.drawer-bg.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;bottom:0;inset-inline-start:auto;inset-inline-end:-620px;width:min(600px,94vw);background:var(--bg2);border-inline-start:1px solid var(--border);z-index:31;transition:.25s;display:flex;flex-direction:column}
.drawer.open{inset-inline-end:0}
.drawer-head{display:flex;align-items:center;justify-content:space-between;padding:.9rem 1.2rem;border-bottom:1px solid var(--border)}
.drawer-body{padding:1.1rem 1.2rem;overflow-y:auto;flex:1}
.toast-wrap{position:fixed;bottom:1rem;inset-inline-start:1rem;z-index:99;display:flex;flex-direction:column;gap:.5rem}
.toast{background:var(--card2);border:1px solid var(--border);border-radius:var(--r-sm);padding:.6rem 1rem;box-shadow:var(--shadow);animation:pop .18s}
.toast.err{border-color:rgba(248,113,113,.5)}
@keyframes pop{from{transform:translateY(8px);opacity:0}}
.auth-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1rem}
.auth-card{width:min(430px,94vw)}
.auth-logo{font-size:1.5rem;font-weight:800;text-align:center;margin-bottom:.3rem}
.auth-tag{color:var(--muted);text-align:center;font-size:.85rem;margin-bottom:1.2rem}
.field{margin-bottom:.8rem}
.field label{display:block;font-size:.8rem;color:var(--muted);margin-bottom:.25rem}
.sig{display:flex;gap:.5rem;flex-wrap:wrap;margin:.3rem 0}
.step{display:flex;align-items:center;gap:.5rem;font-size:.8rem;color:var(--faint);margin-bottom:1rem}
.step b{color:var(--accent)}
.tabs{display:flex;gap:.3rem;border-bottom:1px solid var(--border);margin-bottom:.9rem;flex-wrap:wrap}
.tab{padding:.45rem .9rem;border:none;background:none;color:var(--muted);border-bottom:2px solid transparent;font-size:.88rem}
.tab.active{color:var(--accent);border-color:var(--accent);font-weight:700}
code{background:var(--bg2);border-radius:5px;padding:.08rem .35rem;direction:ltr;display:inline-block}
@media(max-width:900px){.shell{grid-template-columns:1fr}.sidebar{display:flex;overflow-x:auto;border-inline-end:none;border-bottom:1px solid var(--border)}}
</style>
</head>
<body>
<div id="app"></div>
<div class="toast-wrap" id="toasts"></div>
<script>
"use strict";
const S={app:localStorage.getItem("ka_app")||"",adm:localStorage.getItem("ka_adm")||"",
         admExp:+(localStorage.getItem("ka_exp")||0),view:"overview",me:null};
const $=h=>{const t=document.createElement("template");t.innerHTML=h.trim();return t.content.firstChild;};
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function toast(m,err){const t=$(`<div class="toast ${err?"err":""}">${esc(m)}</div>`);
  document.getElementById("toasts").appendChild(t);setTimeout(()=>t.remove(),4200);}
const ok=m=>toast(m,false), fail=m=>toast(m,true);

// two token lanes — admin lane expires in minutes by design (ISO-01)
async function call(path,opts={},lane){
  const token=lane==="admin"?S.adm:S.app;
  const r=await fetch(path,{...opts,headers:{"Content-Type":"application/json",
    ...(token?{"Authorization":"Bearer "+token}:{}),...(opts.headers||{})}});
  let d=null; try{d=await r.json();}catch(e){}
  if(!r.ok){
    const code=d&&d.error&&d.error.code;
    if(lane==="admin"&&(code==="admin_token_required"||code==="token_expired")){renderElevate();throw new Error("انتهت جلسة الإدارة — أعد التصعيد.");}
    if(r.status===401&&lane!=="admin"){logout();throw new Error("انتهت الجلسة.");}
    throw new Error((d&&d.error&&d.error.message)||("HTTP "+r.status));
  }
  return d;
}
const adm=(p,o)=>call(p,o,"admin"), app=(p,o)=>call(p,o,"app");
async function guard(fn){try{await fn();}catch(e){fail(e.message);}}
function logout(){["ka_app","ka_adm","ka_exp"].forEach(k=>localStorage.removeItem(k));S.app=S.adm="";renderLogin();}

// ── auth: password → app token → TOTP step-up → admin token ─────────────
function renderLogin(){
  document.getElementById("app").innerHTML="";
  document.getElementById("app").appendChild($(`<div class="auth-wrap"><div class="auth-card">
    <div class="auth-logo">🛰️ KonformOS <span style="color:var(--accent)">Admin</span></div>
    <div class="auth-tag">غرفة العمليات — لوحة التحكم الإدارية المعزولة</div>
    <div class="card">
      <div class="step"><b>1</b> اعتماد الدخول <span>→</span> <span>2 تصعيد TOTP</span></div>
      <div class="field"><label>البريد</label><input id="em" dir="ltr" autocomplete="username"></div>
      <div class="field"><label>كلمة المرور</label><input id="pw" type="password" dir="ltr" autocomplete="current-password"></div>
      <div class="field"><label>رمز TOTP (إن كان الدخول يتطلبه)</label><input id="tt" dir="ltr" inputmode="numeric" placeholder="اختياري هنا"></div>
      <button class="btn" style="width:100%" id="go">دخول</button>
      <p class="faint small" style="margin-top:.7rem">الأدوار المخوّلة فقط: admin · legal_curator · expert_reviewer — وبMFA مفعّل إلزاماً (RBAC-02).</p>
    </div></div></div>`));
  document.getElementById("go").onclick=()=>guard(async()=>{
    const body={email:val("em"),password:val("pw")}; if(val("tt"))body.totp_code=val("tt");
    const d=await call("/v1/auth/login",{method:"POST",body:JSON.stringify(body)});
    S.app=d.token;localStorage.setItem("ka_app",S.app);renderElevate();});
}
function renderElevate(){
  document.getElementById("app").innerHTML="";
  document.getElementById("app").appendChild($(`<div class="auth-wrap"><div class="auth-card">
    <div class="auth-logo">🛰️ KonformOS <span style="color:var(--accent)">Admin</span></div>
    <div class="auth-tag">تصعيد الجلسة — توكن إدارة قصير العمر (15 دقيقة)</div>
    <div class="card">
      <div class="step"><span>1 اعتماد الدخول ✓</span> <span>→</span> <b>2</b> تصعيد TOTP</div>
      <div class="field"><label>رمز TOTP الحالي</label><input id="code" dir="ltr" inputmode="numeric" autofocus></div>
      <button class="btn" style="width:100%" id="up">تصعيد إلى لوحة التحكم</button>
      <button class="btn ghost sm" style="width:100%;margin-top:.5rem" id="back">رجوع</button>
      <p class="faint small" style="margin-top:.7rem">التوكن المصعَّد لا يعمل على واجهة العملاء، وتوكن العملاء لا يفتح هذه اللوحة — عزل بالجمهور (aud) لا بالإخفاء.</p>
    </div></div></div>`));
  document.getElementById("up").onclick=()=>guard(async()=>{
    const d=await call("/v1/admin/auth/elevate",{method:"POST",body:JSON.stringify({totp_code:val("code")})});
    S.adm=d.token;S.admExp=Date.now()+d.expires_in_seconds*1000;
    localStorage.setItem("ka_adm",S.adm);localStorage.setItem("ka_exp",S.admExp);boot();});
  document.getElementById("back").onclick=logout;
}
const val=id=>{const e=document.getElementById(id);return e?e.value.trim():"";};

// ── shell ────────────────────────────────────────────────────────────────
const NAV=[["overview","نظرة عامة","📊"],["clients","العملاء","🏢"],["legal","القانون","⚖️"],
           ["expert","الخبير","🖊️"],["audit","التدقيق","🔏"],["system","النظام","🧭"]];
function renderShell(){
  const el=document.getElementById("app");el.innerHTML="";
  el.appendChild($(`<div>
    <div class="topbar">
      <div class="brand">🛰️ KonformOS <span class="v">ADMIN</span></div>
      <span class="ttl" id="ttl"></span>
      <div style="flex:1"></div>
      <a class="btn ghost sm" href="/app">واجهة العملاء ↗</a>
      <button class="btn ghost sm" id="lo">خروج</button>
    </div>
    <div class="shell"><aside class="sidebar" id="sb"></aside><main class="main" id="main"></main></div>
    <div class="drawer-bg" id="dbg"></div>
    <div class="drawer" id="dr"><div class="drawer-head"><strong id="dt"></strong>
      <button class="btn ghost sm" id="dc">✕</button></div><div class="drawer-body" id="db"></div></div>
  </div>`));
  const sb=document.getElementById("sb");
  sb.appendChild($(`<div class="nav-sec">التحكم</div>`));
  NAV.forEach(([id,label,ico])=>{const n=$(`<a class="nav-item ${S.view===id?"active":""}"><span>${ico}</span><span>${label}</span></a>`);
    n.onclick=()=>{S.view=id;route();document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));n.classList.add("active");};
    sb.appendChild(n);});
  document.getElementById("lo").onclick=logout;
  document.getElementById("dc").onclick=closeDrawer;document.getElementById("dbg").onclick=closeDrawer;
  setInterval(()=>{const s=Math.max(0,Math.round((S.admExp-Date.now())/1000));
    const t=document.getElementById("ttl");if(t)t.textContent=`جلسة الإدارة: ${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;
    if(s<=0){renderElevate();}},1000);
  route();
}
function openDrawer(title,node){document.getElementById("dt").textContent=title;
  const b=document.getElementById("db");b.innerHTML="";
  typeof node==="string"?b.innerHTML=node:b.appendChild(node);
  document.getElementById("dr").classList.add("open");document.getElementById("dbg").classList.add("open");}
function closeDrawer(){document.getElementById("dr").classList.remove("open");document.getElementById("dbg").classList.remove("open");}
function route(){const m=document.getElementById("main");if(!m)return;
  ({overview:vOverview,clients:vClients,legal:vLegal,expert:vExpert,audit:vAudit,system:vSystem}[S.view]||vOverview)(m);}

const hcolor=h=>h>=70?"var(--green)":h>=40?"var(--amber)":"var(--red)";
const hbar=h=>`<div class="hbar" title="${h}/100"><i style="width:${h}%;background:${hcolor(h)}"></i></div>`;
const lcs={onboarding:"تهيئة",active:"نشط",at_risk:"خطر",dormant:"خامل",churned:"مغادر"};
const lc=(s,susp)=>susp?`<span class="lc suspended">موقوف</span>`:`<span class="lc ${s}">${lcs[s]||s}</span>`;

// ── overview ─────────────────────────────────────────────────────────────
async function vOverview(m){
  m.innerHTML=`<h1 class="page-title">نظرة عامة على المنصّة</h1>
    <p class="page-sub">كل المنظمات، كل الفحوصات، صحة المحفظة — قراءة عابرة للمنظمات (admin_ro) بلا أي صلاحية كتابة.</p><div id="ov"></div>`;
  await guard(async()=>{
    const d=await adm("/v1/admin/overview");
    document.getElementById("ov").innerHTML=`
      <div class="tiles">
        <div class="tile"><div class="k">${d.organizations}</div><div class="l">منظمة</div></div>
        <div class="tile"><div class="k">${d.scans_30d}</div><div class="l">فحص آخر 30 يوماً</div></div>
        <div class="tile"><div class="k">${d.findings.open}</div><div class="l">Finding مفتوح</div></div>
        <div class="tile"><div class="k">${d.findings.fixed}</div><div class="l">مُصلَح</div></div>
        <div class="tile"><div class="k">${d.knowledge_entries}</div><div class="l">الخندق المعرفي</div></div>
        <div class="tile"><div class="k">${d.avg_health??"—"}</div><div class="l">متوسط الصحة</div></div>
      </div>
      <div class="grid" style="grid-template-columns:1.2fr .8fr">
        <div class="card"><h3>عملاء يحتاجون تدخلاً (at-risk / خامل)</h3>${
          d.at_risk_clients.length?`<table><thead><tr><th>العميل</th><th>الصحة</th><th>الحالة</th><th>إشارات</th></tr></thead><tbody>${
            d.at_risk_clients.map(c=>`<tr style="cursor:pointer" onclick="openClient('${c.organization_id}')">
              <td><strong>${esc(c.name)}</strong></td><td>${hbar(c.health)}</td>
              <td>${lc(c.lifecycle,c.suspended)}</td>
              <td class="faint small">${c.signals.slice(0,2).map(esc).join(" · ")}</td></tr>`).join("")}</tbody></table>`
          :`<div class="empty">لا عملاء في خطر 🎉</div>`}</div>
        <div class="card"><h3>التوزيع</h3>
          <div class="sig">${Object.entries(d.lifecycle_breakdown).map(([k,v])=>`<span class="pill">${lcs[k]||k}: <strong>${v}</strong></span>`).join("")}</div>
          <div class="sig">${Object.entries(d.tiers).map(([k,v])=>`<span class="pill">${esc(k)}: <strong>${v}</strong></span>`).join("")||'<span class="faint small">لا اشتراكات نشطة</span>'}</div>
          <h3 style="margin-top:1rem">الحزم النشطة</h3>
          <div class="sig">${d.active_packs.map(p=>`<span class="pill">${esc(p.jurisdiction)} <code class="small">${esc(p.version)}</code></span>`).join("")||"—"}</div>
          <div class="small" style="margin-top:.8rem">${d.rls_enforceable===false?'<span style="color:var(--red)">⚠️ RLS غير مُنفَذ — دور القاعدة superuser</span>':'<span style="color:var(--green)">🛡️ RLS مُنفَذ</span>'} · طابور الفحص: ${d.scan_queue}</div>
        </div>
      </div>`;
  });
}

// ── clients (CRM) ────────────────────────────────────────────────────────
async function vClients(m){
  m.innerHTML=`<h1 class="page-title">إدارة العملاء</h1>
    <p class="page-sub">Client 360 — صحة قابلة للتفسير، دورة حياة، ملاحظات، وإجراءات مدقَّقة بسلسلة hash.</p>
    <div class="sig" id="segs"></div><div class="card" style="margin-top:.6rem"><div id="list"></div></div>`;
  const segs=[["","الكل"],["active","نشط"],["onboarding","تهيئة"],["at_risk","خطر"],["dormant","خامل"],["churned","مغادر"],["suspended","موقوف"]];
  const wrap=document.getElementById("segs");
  segs.forEach(([v,label])=>{const b=$(`<button class="btn ${v===""?"soft":"ghost"} sm">${label}</button>`);
    b.onclick=()=>{wrap.querySelectorAll(".btn").forEach(x=>x.className="btn ghost sm");b.className="btn soft sm";loadClients(v);};
    wrap.appendChild(b);});
  const q=$(`<input placeholder="بحث بالاسم/الدولة…" style="max-width:220px">`);
  q.oninput=()=>loadClients(undefined,q.value);wrap.appendChild(q);
  await loadClients("");
}
async function loadClients(seg,q){
  await guard(async()=>{
    const params=new URLSearchParams();if(seg)params.set("segment",seg);if(q)params.set("q",q);
    const d=await adm("/v1/admin/clients?"+params);
    document.getElementById("list").innerHTML=d.clients.length?`<table>
      <thead><tr><th>العميل</th><th>الصحة</th><th>الحالة</th><th>الاشتراك</th><th>عقارات</th><th>فحوصات</th><th>مستخدمون</th></tr></thead>
      <tbody>${d.clients.map(c=>`<tr style="cursor:pointer" onclick="openClient('${c.organization_id}')">
        <td><strong>${esc(c.name)}</strong><div class="faint small">${esc(c.country||"—")} · ${esc(c.type)}</div></td>
        <td>${hbar(c.health)}<span class="faint small">${c.health}</span></td>
        <td>${lc(c.lifecycle,c.suspended)}${c.lifecycle_pinned?' 📌':''}</td>
        <td><span class="pill small">${esc(c.tier||"—")}</span></td>
        <td>${c.properties}</td><td>${c.scans}</td><td>${c.users}</td></tr>`).join("")}</tbody></table>`
      :`<div class="empty">لا نتائج.</div>`;
  });
}
window.openClient=async(id)=>{
  await guard(async()=>{
    const c=await adm("/v1/admin/clients/"+id);
    const comp=c.health_breakdown;
    const node=$(`<div>
      <div class="sig">${lc(c.lifecycle,c.suspended)}<span class="pill">${esc(c.tier||"—")}</span>
        <span class="pill">صحة <strong style="color:${hcolor(c.health)}">${c.health}</strong>/100</span></div>
      <div class="tabs" id="ctabs">
        <button class="tab active" data-t="sum">الملخص</button>
        <button class="tab" data-t="team">الفريق</button>
        <button class="tab" data-t="props">العقارات</button>
        <button class="tab" data-t="notes">الملاحظات</button>
        <button class="tab" data-t="act">إجراءات</button>
      </div><div id="cbody"></div></div>`);
    const bodies={
      sum:()=>`
        <h3 class="small">مكوّنات الصحة (قابلة للتفسير)</h3>
        ${Object.entries(comp).map(([k,v])=>`<div style="display:flex;align-items:center;gap:.6rem;margin:.35rem 0">
          <span class="small" style="width:90px">${{activity:"النشاط",readiness:"الجاهزية",adoption:"التبنّي",billing:"الفوترة"}[k]||k}</span>
          <div class="hbar" style="flex:1"><i style="width:${Math.round(v.score/v.max*100)}%;background:var(--accent)"></i></div>
          <span class="faint small">${v.score}/${v.max}</span></div>`).join("")}
        ${c.signals.length?`<h3 class="small" style="margin-top:.8rem">إشارات الخطر</h3><div class="sig">${c.signals.map(s=>`<span class="pill" style="color:var(--amber)">${esc(s)}</span>`).join("")}</div>`:""}
        ${c.playbook.length?`<h3 class="small" style="margin-top:.8rem">Playbook مقترح</h3>${c.playbook.map(p=>`<div class="small" style="padding:.3rem 0">💡 ${esc(p)}</div>`).join("")}`:""}
        <h3 class="small" style="margin-top:.8rem">آخر الفحوصات</h3>
        ${c.recent_scans.length?c.recent_scans.slice(0,5).map(s=>`<div class="small faint" style="padding:.2rem 0"><code class="small">${s.id.slice(0,8)}</code> ${esc(s.status)} · ${esc(s.trigger)} · ${esc((s.created_at||"").slice(0,16))}</div>`).join(""):'<div class="faint small">لا فحوصات.</div>'}`,
      team:()=>c.members.length?`<table><thead><tr><th>البريد</th><th>الدور</th><th>MFA</th></tr></thead><tbody>${
        c.members.map(u=>`<tr><td dir="ltr">${esc(u.email)}</td><td><span class="pill small">${esc(u.role)}</span></td>
        <td>${u.mfa_enabled?"✅":"—"}</td></tr>`).join("")}</tbody></table>`:'<div class="empty">لا مستخدمين.</div>',
      props:()=>c.properties.length?c.properties.map(p=>`<div style="padding:.5rem 0;border-bottom:1px solid var(--border)">
        <strong class="small">${esc(p.label||p.url)}</strong><div class="faint small" dir="ltr">${esc(p.url)}</div>
        <div class="sig">${Object.entries(p.readiness||{}).map(([j,s])=>`<span class="pill small">${esc(j)} ${s}</span>`).join("")||'<span class="faint small">لا جاهزية بعد</span>'}</div></div>`).join(""):'<div class="empty">لا عقارات.</div>',
      notes:()=>`
        <div class="field"><select id="nk"><option value="note">ملاحظة</option><option value="call">مكالمة</option>
          <option value="email">بريد</option><option value="escalation">تصعيد</option><option value="decision">قرار</option></select></div>
        <div class="field"><textarea id="nb" rows="3" placeholder="سجّل التفاعل… (سجل إلحاقي لا يُعدَّل)"></textarea></div>
        <button class="btn sm" onclick="addNote('${c.organization_id}')">إضافة (append-only)</button>
        <div style="margin-top:.8rem">${c.notes.length?c.notes.map(n=>`<div style="padding:.45rem 0;border-bottom:1px solid var(--border)">
          <span class="pill small">${esc(n.kind)}</span> <span class="faint small">${esc((n.created_at||"").slice(0,16))}</span>
          <div class="small" style="margin-top:.2rem">${esc(n.body)}</div></div>`).join(""):'<div class="faint small">لا ملاحظات بعد.</div>'}</div>`,
      act:()=>`
        <h3 class="small">دورة الحياة (SM-CLIENT)</h3>
        <div class="sig">${Object.entries(lcs).map(([k,l])=>`<button class="btn ghost sm" onclick="setLC('${c.organization_id}','${k}')">${l}</button>`).join("")}</div>
        <p class="faint small">التعيين اليدوي يثبَّت 📌 ويتغلب على الاشتقاق الآلي — كل تغيير مدقَّق.</p>
        <h3 class="small" style="margin-top:.9rem">تغيير المستوى</h3>
        <div class="sig"><select id="tiersel" style="max-width:200px">${(c.capabilities?Object.keys({free_scan:1,report:1,protection:1,enterprise:1}):["free_scan","report","protection","enterprise"]).map(t=>`<option ${t===c.tier?"selected":""}>${t}</option>`).join("")}</select>
        <input id="tierwhy" placeholder="السبب (إلزامي — يُدقَّق)" style="max-width:220px">
        <button class="btn sm" onclick="setTier('${c.organization_id}')">تطبيق</button></div>
        <h3 class="small" style="margin-top:.9rem">انتحال للقراءة فقط (ISO-04)</h3>
        <button class="btn soft sm" onclick="imp('${c.organization_id}')">🔭 عرض كالعميل — 15 دقيقة، قراءة فقط، مدقَّق</button>
        <h3 class="small" style="margin-top:.9rem">مفتاح الإيقاف</h3>
        ${c.suspended?`<button class="btn sm" onclick="react('${c.organization_id}')">إعادة تفعيل الحساب</button>`
          :`<div class="sig"><input id="suswhy" placeholder="سبب الإيقاف (إلزامي)" style="max-width:260px">
             <button class="btn danger sm" onclick="susp('${c.organization_id}')">إيقاف الحساب</button></div>`}`,
    };
    const body=node.querySelector("#cbody");
    const show=t=>{body.innerHTML=bodies[t]();};
    node.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{node.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));b.classList.add("active");show(b.dataset.t);});
    show("sum");
    openDrawer(c.name,node);
  });
};
window.addNote=(id)=>guard(async()=>{const body=val("nb");if(!body)return fail("اكتب الملاحظة أولاً.");
  await adm(`/v1/admin/clients/${id}/notes`,{method:"POST",body:JSON.stringify({kind:val("nk")||"note",body})});
  ok("سُجّلت — سجل إلحاقي");openClient(id);});
window.setLC=(id,state)=>guard(async()=>{await adm(`/v1/admin/clients/${id}/lifecycle`,{method:"POST",body:JSON.stringify({state})});
  ok("حُدّثت دورة الحياة");openClient(id);loadClients("");});
window.setTier=(id)=>guard(async()=>{const reason=val("tierwhy");if(!reason)return fail("السبب إلزامي — يدخل سجل التدقيق.");
  const d=await adm(`/v1/admin/clients/${id}/tier`,{method:"POST",body:JSON.stringify({tier:val("tiersel"),reason})});
  ok(`المستوى: ${d.previous} → ${d.tier}`);openClient(id);});
window.imp=(id)=>guard(async()=>{const d=await adm(`/v1/admin/clients/${id}/impersonate`,{method:"POST"});
  const url=`/app#imp=${encodeURIComponent(d.token)}`;
  const node=$(`<div><p class="small">توكن قراءة-فقط لمدة 15 دقيقة (مدقَّق). افتح واجهة العميل بجلسة معزولة:</p>
    <div class="sig"><button class="btn sm" id="cp">نسخ التوكن</button>
    <a class="btn soft sm" href="${url}" target="_blank" rel="noopener">فتح /app ↗</a></div>
    <p class="faint small">كل محاولة كتابة سترفض بـ impersonation_read_only.</p></div>`);
  node.querySelector("#cp").onclick=()=>{navigator.clipboard.writeText(d.token);ok("نُسخ");};
  openDrawer("انتحال للقراءة فقط",node);});
window.susp=(id)=>guard(async()=>{const reason=val("suswhy");if(!reason)return fail("سبب الإيقاف إلزامي.");
  await adm(`/v1/admin/clients/${id}/suspend`,{method:"POST",body:JSON.stringify({reason})});
  ok("أُوقف الحساب — كل نداءات العميل سترجع org_suspended");openClient(id);loadClients("");});
window.react=(id)=>guard(async()=>{await adm(`/v1/admin/clients/${id}/reactivate`,{method:"POST"});
  ok("أُعيد التفعيل");openClient(id);loadClients("");});

// ── legal portal (app-token lane — server-side role-guarded) ────────────
async function vLegal(m){
  m.innerHTML=`<h1 class="page-title">بوابة القانون</h1><p class="page-sub">حزم القواعد والتغييرات القانونية — Legal Curator.</p>
    <div class="grid" style="grid-template-columns:1fr 1fr">
      <div class="card"><h3>حزم القواعد</h3><div id="packs"></div></div>
      <div class="card"><h3>تغييرات بانتظار المراجعة</h3><div id="events"></div></div></div>`;
  await guard(async()=>{
    const [packs,events]=await Promise.all([app("/v1/legal/rule-packs"),app("/v1/legal/change-events?status=pending_review")]);
    document.getElementById("packs").innerHTML=packs.rule_packs.length?`<table><thead><tr><th>الإصدار</th><th>الحالة</th><th>قواعد</th><th></th></tr></thead><tbody>${
      packs.rule_packs.map(p=>`<tr><td><code class="small">${esc(p.version)}</code></td>
        <td><span class="pill small">${esc(p.status)}</span></td><td>${p.rule_count}</td>
        <td>${p.status==="draft"?`<button class="btn soft sm" onclick="publishPack('${p.version}')">نشر</button>`:""}</td></tr>`).join("")}</tbody></table>`
      :`<div class="empty">لا حزم.</div>`;
    document.getElementById("events").innerHTML=events.change_events.length?events.change_events.map(e=>
      `<div style="padding:.5rem 0;border-bottom:1px solid var(--border)"><strong class="small">${esc(e.change_type)}</strong>
       <div class="faint small">${esc(e.llm_summary||"")}</div></div>`).join("")
      :`<div class="empty">لا تغييرات معلّقة.</div>`;
  });
}
window.publishPack=(v)=>guard(async()=>{const d=await app(`/v1/legal/rule-packs/${v}/publish`,{method:"POST"});
  ok(`نُشرت ${v}`+(d.recomputed_properties?` — أُعيد حساب ${d.recomputed_properties} عقار`:""));vLegal(document.getElementById("main"));});

// ── expert portal ────────────────────────────────────────────────────────
async function vExpert(m){
  m.innerHTML=`<h1 class="page-title">بوابة الخبير</h1><p class="page-sub">مراجعة Prüfstelle البشرية والتوقيع المؤمَّن.</p>
    <div class="card"><h3>طابور المراجعة</h3><div id="queue"></div></div>`;
  await guard(async()=>{const d=await app("/v1/expert/review-queue");
    document.getElementById("queue").innerHTML=d.queue.length?`<table><thead><tr><th>الفحص</th><th>التاريخ</th><th></th></tr></thead><tbody>${
      d.queue.map(q=>`<tr><td><code class="small">${esc(q.scan_id.slice(0,12))}…</code></td>
        <td class="faint small">${esc(q.created_at)}</td>
        <td><button class="btn soft sm" onclick="signReview('${q.scan_id}')">توقيع المراجعة</button></td></tr>`).join("")}</tbody></table>`
      :`<div class="empty">لا فحوصات بانتظار المراجعة.</div>`;});
}
window.signReview=(sid)=>{const ins=prompt("مرجع التأمين المهني (insurance_ref):","VS-2026-001");if(ins===null)return;
  guard(async()=>{await app(`/v1/expert/scans/${sid}/sign`,{method:"POST",body:JSON.stringify({
    signature:{qualification:"BITV-Test Prüfer"},insurance_ref:ins})});
    ok("وُقّعت وخُتمت في الـTimeline");vExpert(document.getElementById("main"));});};

// ── audit ────────────────────────────────────────────────────────────────
async function vAudit(m){
  m.innerHTML=`<h1 class="page-title">سجل التدقيق</h1>
    <p class="page-sub">كل فعل إداري، مختوم بسلسلة hash كما تُختم أدلة العملاء — العبث قابل للكشف.</p>
    <div class="sig"><button class="btn soft sm" id="vf">🔏 تحقق من السلسلة</button><span id="vres"></span></div>
    <div class="card" style="margin-top:.6rem"><div id="log"></div></div>`;
  document.getElementById("vf").onclick=()=>guard(async()=>{
    const r=await adm("/v1/admin/audit/verify");
    document.getElementById("vres").innerHTML=r.valid
      ?`<span class="pill" style="color:var(--green)">✅ السلسلة سليمة (${r.entries} قيداً)</span>`
      :`<span class="pill" style="color:var(--red)">⚠️ مكسورة عند #${r.broken_at} — ${esc(r.reason)}</span>`;});
  await guard(async()=>{
    const d=await adm("/v1/admin/audit?limit=200");
    document.getElementById("log").innerHTML=d.entries.length?`<table>
      <thead><tr><th>#</th><th>الفعل</th><th>الهدف</th><th>بيانات</th><th>التوقيت</th><th>hash</th></tr></thead><tbody>${
      d.entries.map(e=>`<tr><td>${e.seq}</td><td><code class="small">${esc(e.action)}</code></td>
        <td class="faint small">${esc(e.target_type||"")} ${e.target_id?`<code class="small">${esc(e.target_id.slice(0,8))}</code>`:""}</td>
        <td class="faint small">${esc(JSON.stringify(e.data||{}).slice(0,60))}</td>
        <td class="faint small">${esc((e.created_at||"").slice(0,19).replace("T"," "))}</td>
        <td><code class="small">${esc(e.content_hash.slice(0,10))}…</code></td></tr>`).join("")}</tbody></table>`
      :`<div class="empty">لا قيود بعد.</div>`;
  });
}

// ── system ───────────────────────────────────────────────────────────────
async function vSystem(m){
  m.innerHTML=`<h1 class="page-title">النظام</h1><p class="page-sub">صحة المنصّة والضبط التشغيلي.</p><div id="sys"></div>`;
  await guard(async()=>{
    const d=await adm("/v1/admin/system");
    document.getElementById("sys").innerHTML=`
      <div class="tiles">
        <div class="tile"><div class="k">${d.db?"✅":"❌"}</div><div class="l">قاعدة البيانات</div></div>
        <div class="tile"><div class="k">${d.rls_enforceable===false?"⚠️":"🛡️"}</div><div class="l">RLS ${d.rls_enforceable===false?"غير منفذ":"منفذ"}</div></div>
        <div class="tile"><div class="k">${d.catalog.rules}</div><div class="l">قاعدة في الكتالوج</div></div>
        <div class="tile"><div class="k">${d.rate_limit_per_min}</div><div class="l">طلب/دقيقة</div></div>
        <div class="tile"><div class="k">${Math.round(d.admin_token_ttl_seconds/60)}د</div><div class="l">عمر توكن الإدارة</div></div>
      </div>
      <div class="grid" style="grid-template-columns:1fr 1fr">
        <div class="card"><h3>طابور الفحص</h3><div class="sig">${Object.entries(d.scan_queue).map(([k,v])=>`<span class="pill">${esc(k)}: <strong>${v}</strong></span>`).join("")}</div></div>
        <div class="card"><h3>الكتالوج</h3><div class="sig">${d.catalog.packs.map(p=>`<code class="small">${esc(p)}</code>`).join(" ")}</div></div>
      </div>`;
  });
}

// ── boot ─────────────────────────────────────────────────────────────────
async function boot(){
  if(!S.app){return renderLogin();}
  if(!S.adm||Date.now()>S.admExp){return renderElevate();}
  renderShell();
}
boot();
</script>
</body>
</html>
"""
