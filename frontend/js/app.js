/* InvestLens frontend – talks to the Flask API (see backend/app.py). */
const $ = id => document.getElementById(id);
const fmt = n => Math.round(n).toLocaleString();
function esc(s){return String(s).replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]))}

/* ---------- API helper ---------- */
async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", credentials: "same-origin", headers: {} };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  let res;
  try { res = await fetch("/api" + path, init); }
  catch (e) { throw new Error("Cannot reach the server. Is the backend running?"); }
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const err = new Error(data.error || "Request failed (" + res.status + ")");
    err.status = res.status;
    throw err;
  }
  return data;
}

/* ---------- Login / account gate ---------- */
let loginMode = false;
let results = [];            // latest Layer-1 results (sorted by score)

function showAuth(){ $("app").classList.add("hide"); $("auth").classList.remove("hide"); }
function setAuthMode(existing){
  loginMode = existing;
  $("at").textContent = existing ? "Log in" : "Create your account";
  $("ah").textContent = existing
    ? "Enter your email and password to continue."
    : "Create an account with your name, email and password.";
  $("ab").textContent = existing ? "Log in" : "Create account";
  $("sw").textContent = existing ? "Create a new account" : "I already have an account";
  $("ap").setAttribute("autocomplete", existing ? "current-password" : "new-password");
  $("aul").classList.toggle("hide", existing);
  $("au").required = !existing;
  $("ae").textContent = "";
}

async function showApp(user){
  $("auth").classList.add("hide");
  $("app").classList.remove("hide");
  $("who").textContent = "Signed in as " + user.username;
  await loadPortfolio();
}

$("af").addEventListener("submit", async e => {
  e.preventDefault();
  const username = $("au").value.trim();
  const email = $("aeid").value.trim().toLowerCase();
  const password = $("ap").value;
  const error = $("ae");
  error.textContent = "";
  if (!email || !password || (!loginMode && !username)) { error.textContent = "Please enter your name, email ID and password."; return; }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { error.textContent = "Please enter a valid email ID."; return; }
  if (password.length < 4) { error.textContent = "Password must contain at least 4 characters."; return; }
  $("ab").disabled = true;
  try {
    const user = await api(loginMode ? "/auth/login" : "/auth/register", { method: "POST", body: { username, email, password } });
    $("ap").value = "";
    await showApp(user);
  } catch (err) {
    error.textContent = err.message;
    if (err.status === 409) { setAuthMode(true); $("aeid").value = email; $("ap").value = ""; }
  } finally { $("ab").disabled = false; }
});

$("sw").addEventListener("click", () => {
  const oldEmail = $("aeid").value.trim();
  setAuthMode(!loginMode);
  if (oldEmail) $("aeid").value = oldEmail;
});

$("out").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST", body: {} }); } catch (e) {}
  results = [];
  $("au").value = ""; $("aeid").value = ""; $("ap").value = "";
  $("rows").innerHTML = ""; $("out1").innerHTML = ""; $("out2").innerHTML = "";
  $("chatbox").innerHTML = "";
  sample.forEach(addRow);
  setAuthMode(true);
  tab(1);
  showAuth();
});

(async function initAuth(){
  try {
    const user = await api("/auth/me");
    await showApp(user);
  } catch (e) {
    let any = true;
    try { any = (await api("/accounts/exist")).exist; } catch (e2) {}
    setAuthMode(any);
    showAuth();
  }
})();

/* ---------- Page 1: screen and allocate ---------- */
const sample = [["Sample Co A",500,250,300,900,200,1500,180],["Sample Co B",400,350,900,300,40,1200,30],["Sample Co C",300,120,100,700,150,800,70]];
const F = ["name","ca","cl","debt","eq","cash","rev","ni"];

function addRow(v = ["",0,0,0,0,0,0,0]){
  const tr = document.createElement("tr");
  tr.innerHTML = v.map((x,i)=>`<td><input ${i?'type="number"':''} value="${esc(x)}" aria-label="${F[i]}"></td>`).join("")
    + '<td><button class="btn alt" aria-label="Remove">x</button></td>';
  tr.querySelector("button").onclick = () => tr.remove();
  $("rows").appendChild(tr);
}
sample.forEach(addRow);
$("add").onclick = () => addRow();

function readRows(){
  return [...$("rows").children].map(tr => {
    const i = [...tr.querySelectorAll("input")], o = {};
    F.forEach((k,n) => o[k] = n ? (+i[n].value || 0) : (i[n].value.trim() || "Unnamed"));
    return o;
  });
}

const LABEL = { G: "Safe", Y: "Moderate", R: "Risky" };
function renderResults(res, budget){
  let h = "<h2>Recommendation</h2><div class='res'>" + res.map(c => {
    const k = c.band;
    return `<div class="card"><b>${esc(c.name)}</b> <span class="pill ${k}">${LABEL[k]} · ${c.s}/100</span>
<div class="amt">${c.pct ? fmt(c.amount) : "Do not invest"}</div><div class="bar"><i style="width:${c.pct*100}%"></i></div><small>${c.pct ? (c.pct*100).toFixed(0) + "% of your amount" : "Balance sheet is too weak for your money"}</small>
<ul><li>Current ratio ${c.cr.toFixed(2)}</li><li>Debt to equity ${c.eq>0 ? c.de.toFixed(2) : "n/a (no equity)"}</li><li>Net margin ${(c.nm*100).toFixed(1)}%</li><li>Cash covers ${c.debt>0 ? (c.cd*100).toFixed(0) + "% of debt" : "all debt (none)"}</li></ul></div>`;
  }).join("") + "</div>";
  if (res.filter(c => c.s >= 45).length === 1) h += "<p><small>Only one company passed. Add more to spread your risk.</small></p>";
  $("out1").innerHTML = h;
  $("co").innerHTML = res.map((c,i)=>`<option value="${i}">${esc(c.name)}</option>`).join("");
}

$("go").onclick = async () => {
  const btn = $("go"); btn.disabled = true;
  try {
    const data = await api("/analyze", { method: "POST", body: {
      budget: +$("budget").value || 0, risk: +$("risk").value, companies: readRows() } });
    results = data.results;
    renderResults(results, data.budget);
    $("out2").innerHTML = "";
    tab(2);
    refreshAI();
  } catch (err) {
    $("out1").innerHTML = `<div class="card" role="alert">${esc(err.message)}</div>`;
  } finally { btn.disabled = false; }
};

async function loadPortfolio(){
  try {
    const p = await api("/portfolio");
    $("budget").value = p.settings.budget;
    $("risk").value = String(p.settings.risk);
    $("horizon").value = p.settings.horizon;
    if (p.companies.length) {
      $("rows").innerHTML = "";
      p.companies.forEach(c => addRow(F.map(k => c[k])));
    }
    if (p.latest_analysis) {
      results = p.latest_analysis.results;
      renderResults(results, p.latest_analysis.budget);
    }
  } catch (e) { /* keep defaults */ }
}

/* ---------- Page 2: buy signal ---------- */
$("chk").onclick = async () => {
  if (!results.length) { $("out2").innerHTML = '<div class="card">Run the analysis on page 1 first.</div>'; return; }
  const c = results[+$("co").value];
  const btn = $("chk"); btn.disabled = true;
  try {
    const r = await api("/signal", { method: "POST", body: { company: c.name, prices: $("px").value } });
    renderSignal(r);
  } catch (err) {
    $("out2").innerHTML = `<div class="card" role="alert">${esc(err.message)}</div>`;
  } finally { btn.disabled = false; }
};

function renderSignal(r){
  const k = r.signal, P = r.prices, n = P.length;
  const mn = Math.min(...P), mx = Math.max(...P);
  const pts = P.map((x,i)=>`${(i/(n-1)*400).toFixed(1)},${(140-(x-mn)/(mx-mn||1)*130).toFixed(1)}`).join(" ");
  $("out2").innerHTML = `<div class="card"><h2>${esc(r.company)}</h2><div class="sig"><div class="light" role="img" aria-label="Signal ${k}"><b class="${k} ${k=="R"?"on":""}"></b><b class="${k} ${k=="Y"?"on":""}"></b><b class="${k} ${k=="G"?"on":""}"></b></div>
<div style="flex:1;min-width:240px"><div class="amt">${esc(r.message)}</div><p>Price is ${r.rising?"rising":"not rising"}: ${r.change_pct.toFixed(1)}% over this period, recent average ${r.recent_above_avg?"above":"below"} the full-period average. Daily swings average ${r.volatility_pct.toFixed(1)}%.</p>
<p><small>Final score ${r.final_score}/100 = 60% balance-sheet safety (${r.safety_score}) + 40% price timing (${Math.round(r.timing_score)}). Red whenever the balance sheet is Risky.</small></p></div></div>
<svg viewBox="0 0 400 150" preserveAspectRatio="none" role="img" aria-label="Price chart"><polyline points="${pts}" fill="none" stroke="var(--acc)" stroke-width="3" vector-effect="non-scaling-stroke"/></svg></div>`;
}

/* ---------- Tabs ---------- */
function tab(n){
  [1,2,3].forEach(i => {
    $("p"+i).classList.toggle("hide", n != i);
    $("t"+i).setAttribute("aria-selected", n == i);
  });
  if (n == 3) refreshAI();
}
$("t1").onclick = () => tab(1);
$("t2").onclick = () => tab(2);
$("t3").onclick = () => tab(3);

/* ---------- Page 3: AI Investment Assistant ---------- */
function currentAIName(){
  const el = $("aiCo");
  return el.value !== "" && results.length ? results[Math.max(0, Math.min(results.length-1, +el.value || 0))].name : null;
}

async function refreshAI(){
  const prev = $("aiCo").value;
  $("aiCo").innerHTML = results.length
    ? results.map((c,i)=>`<option value="${i}">${esc(c.name)}</option>`).join("")
    : '<option value="">Run Page 1 analysis first</option>';
  if (prev !== "" && +prev < results.length) $("aiCo").value = prev;
  await Promise.all([renderAISummary(), loadHistory()]);
}

function addChat(role, msg){
  const d = document.createElement("div");
  d.className = "chatmsg " + role;
  d.textContent = msg;
  $("chatbox").appendChild(d);
  $("chatbox").scrollTop = $("chatbox").scrollHeight;
}

async function loadHistory(){
  $("chatbox").innerHTML = "";
  const name = currentAIName();
  if (!name) return;
  try {
    const h = await api("/assistant/history?company=" + encodeURIComponent(name));
    h.messages.forEach(m => addChat(m.role === "user" ? "user" : "bot", m.content));
  } catch (e) {}
}

async function renderAISummary(){
  const name = currentAIName();
  if (!name) { $("aiSummary").innerHTML = "<small>Run the analysis on Page 1 first.</small>"; return; }
  try {
    const s = await api(`/assistant/summary?company=${encodeURIComponent(name)}&horizon=${$("horizon").value}`);
    $("aiSummary").innerHTML = `<b>${esc(s.name)}</b><p>For <b>${esc(s.horizon_label)}</b>, the company currently shows a <b>${esc(s.outlook)}</b>.</p>
     <ul><li>Safety score: ${s.safety}/100</li>
     <li>Current ratio: ${s.current_ratio.toFixed(2)}</li>
     <li>Debt-to-equity: ${esc(s.debt_to_equity)}</li>
     <li>Net margin: ${s.net_margin_pct.toFixed(1)}%</li>
     <li>Price trend score: ${s.price_trend_score === null ? "Run Buy Signal" : s.price_trend_score}</li></ul>
     <small>Educational rule-based guidance, not a personalised financial recommendation.</small>`;
  } catch (e) { $("aiSummary").innerHTML = `<small>${esc(e.message)}</small>`; }
}

async function ask(){
  const q = $("aiQ").value.trim();
  const name = currentAIName();
  if (!q) return;
  if (!name) { addChat("bot", "Please run the company analysis on Page 1 first."); return; }
  addChat("user", q);
  $("aiQ").value = "";
  $("aiSend").disabled = true;
  try {
    const r = await api("/assistant", { method: "POST", body: { company: name, horizon: $("horizon").value, question: q } });
    addChat("bot", r.answer);
  } catch (err) { addChat("bot", err.message); }
  finally { $("aiSend").disabled = false; }
}

$("aiCo").addEventListener("change", () => { renderAISummary(); loadHistory(); });
$("horizon").addEventListener("change", renderAISummary);
$("aiSend").addEventListener("click", ask);
$("aiQ").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
document.querySelectorAll(".tag").forEach(t => t.addEventListener("click", () => {
  $("aiQ").value = t.dataset.q;
  ask();
}));
