const state = { schemes: {}, selectedScheme: "scholarship", busy: false };
const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try { payload = await response.json(); } catch { throw new Error("The server returned an unreadable response."); }
  if (!response.ok) throw new Error(payload.error || "The request could not be completed.");
  return payload;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function renderChecklist(schemeId) {
  const scheme = state.schemes[schemeId];
  if (!scheme) return;
  state.selectedScheme = schemeId;
  $("#checklistTitle").textContent = scheme.label;
  $("#checklistNote").textContent = scheme.note;
  $("#sourceNote").textContent = scheme.source_note;
  $("#checklistItems").innerHTML = scheme.documents.map((item) => `<li>${escapeHTML(item)}</li>`).join("");
  $("#schemeSelect").value = schemeId;
  document.querySelectorAll(".service-card").forEach((card) => card.classList.toggle("selected", card.dataset.scheme === schemeId));
}

async function loadSchemes() {
  try {
    const data = await apiRequest("/api/schemes");
    state.schemes = Object.fromEntries(data.schemes.map((scheme) => [scheme.id, scheme]));
    renderChecklist("scholarship");
  } catch (error) {
    $("#checklistNote").textContent = "Could not load the checklist. Check that the Flask server is running and refresh the page.";
    showToast(error.message);
  }
}

document.querySelectorAll(".service-card").forEach((card) => {
  card.addEventListener("click", () => renderChecklist(card.dataset.scheme));
});
$("#schemeSelect").addEventListener("change", (event) => renderChecklist(event.target.value));

function renderSelectedFiles() {
  const files = Array.from($("#documents").files || []);
  const container = $("#selectedFiles");
  if (!files.length) {
    container.innerHTML = '<span class="empty-file-state">No files selected yet.</span>';
    return;
  }
  container.innerHTML = files.map((file) => `<div class="selected-file"><span>▤ ${escapeHTML(file.name)}</span><span>${(file.size / 1024).toFixed(0)} KB</span></div>`).join("");
}
$("#documents").addEventListener("change", renderSelectedFiles);

function renderReport(report) {
  const findings = (report.findings || []).map((finding) => {
    const evidence = (finding.evidence || []).map((item) => `${item.document}: ${item.value}`).join(" · ");
    return `<div class="finding ${escapeHTML(finding.severity)}"><div class="finding-title">${finding.severity === "ok" ? "✓" : finding.severity === "review" ? "⚠" : "ⓘ"} ${escapeHTML(finding.title)}</div><p>${escapeHTML(finding.message)}</p>${evidence ? `<small>Extracted evidence: ${escapeHTML(evidence)}</small>` : ""}</div>`;
  }).join("");
  const docs = (report.documents || []).map((doc) => `<li><strong>${escapeHTML(doc.name)}</strong>: ${escapeHTML(doc.status)}${doc.text_found ? ` Fields read: ${escapeHTML(Object.entries(doc.fields || {}).map(([key, value]) => `${key}=${value}`).join(", ") || "No labelled name/DOB found")}` : ""}</li>`).join("");
  const limitations = (report.limitations || []).map((item) => `<li>${escapeHTML(item)}</li>`).join("");
  const errors = (report.file_errors || []).map((item) => `<li>${escapeHTML(item)}</li>`).join("");
  $("#reportArea").innerHTML = `<div class="report-card"><h4>Document readiness report</h4><div class="report-summary">${escapeHTML(report.scheme)} · ${report.documents.length} file(s) processed</div>${findings}${docs ? `<div class="finding"><div class="finding-title">Files reviewed</div><ul class="report-list">${docs}</ul></div>` : ""}${errors ? `<div class="finding review"><div class="finding-title">Files not processed</div><ul class="report-list">${errors}</ul></div>` : ""}<div class="finding info"><div class="finding-title">Please keep in mind</div><ul class="report-list">${limitations}</ul></div></div>`;
  $("#reportArea").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function submitFiles(event) {
  event.preventDefault();
  if (state.busy) return;
  const files = Array.from($("#documents").files || []);
  if (!files.length) { showToast("Choose at least one sample PDF, JPG or PNG file."); return; }
  if (files.length > 4) { showToast("Please select no more than 4 files."); return; }
  const allowed = /\.(pdf|png|jpe?g)$/i;
  if (files.some((file) => !allowed.test(file.name))) { showToast("One or more files have an unsupported extension."); return; }
  if (files.some((file) => file.size > 8 * 1024 * 1024)) { showToast("Each file must be 8 MB or smaller."); return; }
  const formData = new FormData();
  formData.append("scheme_id", $("#schemeSelect").value);
  files.forEach((file) => formData.append("documents", file));
  state.busy = true;
  const button = $("#checkButton");
  button.disabled = true; button.textContent = "Reviewing files…";
  $("#reportArea").innerHTML = '<div class="report-card">Reading available text and comparing labelled fields. Please wait…</div>';
  try {
    const report = await apiRequest("/api/check", { method: "POST", body: formData });
    renderReport(report);
  } catch (error) {
    $("#reportArea").innerHTML = `<div class="error-box">${escapeHTML(error.message)} Check that the server is running, then try again.</div>`;
  } finally {
    state.busy = false; button.disabled = false; button.innerHTML = 'Review documents <span>→</span>';
  }
}
$("#uploadForm").addEventListener("submit", submitFiles);

async function tryDemo() {
  const buttons = [$("#tryDemo"), $("#tryDemoTop")];
  buttons.forEach((button) => { if (button) button.disabled = true; });
  $("#reportArea").innerHTML = '<div class="report-card">Preparing synthetic sample report…</div>';
  try {
    const report = await apiRequest("/api/demo", { method: "POST" });
    renderReport(report);
    $("#checker").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    $("#reportArea").innerHTML = `<div class="error-box">${escapeHTML(error.message)}</div>`;
  } finally {
    buttons.forEach((button) => { if (button) button.disabled = false; });
  }
}
$("#tryDemo").addEventListener("click", tryDemo);
$("#tryDemoTop").addEventListener("click", tryDemo);

function appendMessage(role, text, detail = "") {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role === "user" ? "user-message" : "bot-message"}`;
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "YOU" : "DS";
  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = role === "user" ? "You" : "DocuSahayak";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  content.append(title, paragraph);
  if (detail) {
    const small = document.createElement("small");
    small.textContent = detail;
    content.appendChild(small);
  }
  wrapper.append(avatar, content);
  $("#chatMessages").appendChild(wrapper);
  $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
}

async function sendQuestion(question) {
  if (!question.trim() || state.busy) return;
  state.busy = true;
  appendMessage("user", question);
  const button = $("#sendButton"); button.disabled = true; button.textContent = "…";
  const loading = document.createElement("div"); loading.className = "message bot-message"; loading.id = "assistantLoading";
  loading.innerHTML = '<span class="message-avatar">DS</span><div><strong>DocuSahayak</strong><p>Preparing guidance…</p></div>';
  $("#chatMessages").appendChild(loading);
  try {
    const data = await apiRequest("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, scheme_id: $("#schemeSelect").value }) });
    loading.remove();
    appendMessage("bot", data.answer, data.notice);
    $("#assistantMode").textContent = data.mode === "gemini" ? "AI guidance connected" : "Local guidance fallback";
  } catch (error) {
    loading.remove();
    appendMessage("bot", "I could not reach the guidance service just now. Please try again. The checklist and sample report can still be used.", error.message);
  } finally {
    state.busy = false; button.disabled = false; button.innerHTML = 'Send <span>↑</span>';
  }
}
$("#chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#chatInput"); const question = input.value.trim();
  if (!question) { showToast("Type a question first."); return; }
  input.value = "";
  sendQuestion(question);
});
document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => sendQuestion(button.dataset.question || "")));

loadSchemes();
