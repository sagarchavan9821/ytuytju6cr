const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = s => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
let S = null, timer = null, attemptId = null, busy = false;
try { S = JSON.parse(localStorage.getItem("exam-session")); } catch (e) {}

async function api(path, body) {
  try { return await apiCall(path, body); }
  catch (e) {
    if (e instanceof TypeError) throw new Error("Cannot reach the server. Run uvicorn, then open http://127.0.0.1:8000 in your browser.");
    throw e;
  }
}
async function apiCall(path, body) {
  const r = await fetch("/api" + path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", ...(S ? { Authorization: "Bearer " + S.token } : {}) },
    body: body ? JSON.stringify(body) : undefined
  });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401 && S) logout();
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Please check the details you entered");
  return d;
}
const show = id => document.querySelectorAll(".view").forEach(v => v.hidden = v.id !== id);
function logout() { S = null; localStorage.removeItem("exam-session"); clearInterval(timer); window.onbeforeunload = null; $("#nav").hidden = true; show("auth"); }
$("#logout").onclick = logout;

$("#authForm").onsubmit = async e => {
  e.preventDefault();
  try {
    const d = await api("/login", { name: $("#name").value, phone: $("#phone").value, password: $("#password").value });
    S = d; localStorage.setItem("exam-session", JSON.stringify(d));
    $("#authMsg").textContent = ""; $("#password").hidden = true; $("#password").value = "";
    home();
  } catch (x) {
    if (/admin password/i.test(x.message)) { $("#password").hidden = false; $("#password").focus(); }
    $("#authMsg").textContent = x.message;
  }
};

async function home() {
  try {
    show("home"); $("#nav").hidden = false; $("#who").textContent = S.name;
    const [ex, res] = await Promise.all([api("/exams"), api("/results")]);
    $("#exams").innerHTML = ex.length ? ex.map(e => `<div class="card"><div><b>${esc(e.title)}</b><div class="muted">${e.n} questions, ${e.minutes} minutes</div></div><button data-start="${e.id}" ${e.n ? "" : "disabled"}>Start exam</button></div>`).join("") : "<p class='muted'>No exams yet.</p>";
    $("#results").innerHTML = res.length ? res.map(r => `<tr><td>${esc(r.title)}</td><td>${r.score}/${r.total}</td><td>${new Date(r.finished * 1000).toLocaleString()}</td></tr>`).join("") : `<tr><td colspan="3" class="muted">No results yet. Take an exam to see your score here.</td></tr>`;
    $("#admin").hidden = S.role !== "admin";
    if (S.role === "admin") {
      $("#examSel").innerHTML = ex.map(e => `<option value="${e.id}">${esc(e.title)}</option>`).join("");
      const all = await api("/admin/results");
      $("#allResults").innerHTML = all.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.title)}</td><td>${r.score}/${r.total}</td><td>${new Date(r.finished * 1000).toLocaleString()}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">No submissions yet.</td></tr>`;
    }
  } catch (x) { if (S) alert(x.message); }
}

$("#exams").onclick = async e => {
  const id = e.target.dataset.start; if (!id) return;
  try {
    const d = await api(`/exams/${id}/start`, {});
    attemptId = d.attempt_id; busy = false;
    $("#title").textContent = d.title;
    $("#qs").innerHTML = d.questions.map((q, i) => `<fieldset class="card q"><legend>${i + 1}. ${esc(q.text)}</legend>${q.options.map((o, j) => `<label><input type="radio" name="q${q.id}" value="${j}"> ${esc(o)}</label>`).join("")}</fieldset>`).join("");
    show("exam"); window.onbeforeunload = () => true;
    const end = Date.now() + d.seconds_left * 1000;
    clearInterval(timer);
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      $("#timer").textContent = fmt(left); $("#timer").classList.toggle("low", left <= 60);
      if (left <= 0) { clearInterval(timer); submit(true); }
    };
    tick(); timer = setInterval(tick, 500);
  } catch (x) { alert(x.message); }
};

async function submit() {
  if (busy) return; busy = true; clearInterval(timer);
  const answers = {};
  document.querySelectorAll("#qs input:checked").forEach(i => answers[i.name.slice(1)] = +i.value);
  try {
    const r = await api(`/attempts/${attemptId}/submit`, { answers });
    window.onbeforeunload = null; showResult(r);
  } catch (x) { alert(x.message); busy = false; }
}
$("#finish").onclick = () => confirm("Submit your answers now?") && submit();

function showResult(r) {
  show("result");
  $("#score").textContent = `${r.score} / ${r.total}`;
  $("#verdict").textContent = `${r.percent}% - ${r.percent >= 50 ? "Passed" : "Not passed yet. Review the answers below and try again."}`;
  $("#review").innerHTML = r.review.map((q, i) => `<div class="card rv"><b>${i + 1}. ${esc(q.text)}</b>${q.options.map((o, j) => `<div class="${j === q.correct ? "good" : j === q.chosen ? "wrong" : ""}">${esc(o)}${j === q.correct ? " (correct)" : j === q.chosen ? " (your answer)" : ""}</div>`).join("")}${q.chosen == null ? "<div class='muted'>Not answered</div>" : ""}</div>`).join("");
}
$("#back").onclick = home;

$("#examForm").onsubmit = async e => {
  e.preventDefault();
  try { await api("/admin/exams", { title: $("#exTitle").value, minutes: +$("#exMin").value }); e.target.reset(); home(); } catch (x) { alert(x.message); }
};
$("#qForm").onsubmit = async e => {
  e.preventDefault();
  const options = [...document.querySelectorAll(".opt")].map(i => i.value);
  try {
    await api(`/admin/exams/${$("#examSel").value}/questions`, { text: $("#qText").value, options, answer: +$("#qAns").value });
    $("#adminMsg").className = "msg ok"; $("#adminMsg").textContent = "Question added.";
    $("#qText").value = ""; document.querySelectorAll(".opt").forEach(i => i.value = ""); home();
  } catch (x) { $("#adminMsg").className = "msg"; $("#adminMsg").textContent = x.message; }
};

S ? home() : show("auth");
