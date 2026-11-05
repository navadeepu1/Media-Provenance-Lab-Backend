const $ = selector => document.querySelector(selector);
const progress = $("#progress"), progressText = $("#progress-text"), progressBar = $("#progress-bar");
const errorMessage = $("#error-message"), report = $("#report"), content = $("#report-content");
const cancelButton = $("#cancel-analysis");
let activeJobId = null, activeCaseId = "", timelineCursor = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" })[c]);
}
async function readJson(response) {
  try { return await response.json(); } catch { throw new Error("The server returned an invalid response."); }
}
function showError(error) { errorMessage.textContent = error instanceof Error ? error.message : "The request failed."; errorMessage.hidden = false; }
function clearError() { errorMessage.hidden = true; }
function setStatus(message, bad = false) { const node = $("#case-status"); node.textContent = message; node.className = bad ? "error" : "notice"; node.hidden = !message; }
async function api(url, options = {}) {
  const response = await fetch(url, options), payload = await readJson(response);
  if (!response.ok) throw new Error(payload.error?.message || payload.detail || "The request failed.");
  return payload;
}
function setLocked(locked) {
  document.querySelectorAll(".locked").forEach(section => {
    section.classList.toggle("locked", locked || !activeCaseId);
    section.querySelectorAll("input,select,textarea,button").forEach(control => { control.disabled = locked || !activeCaseId; });
  });
}
function caseUrl(path = "") { return `/api/v2/cases/${encodeURIComponent(activeCaseId)}${path}`; }

async function loadHealth() {
  try {
    const [v1, v2] = await Promise.all([api("/api/v1/health"), api("/api/v2/health")]);
    $("#health-status").textContent = `Services ready · ${v1.database} · ${v2.rules.length} activity rules`;
  } catch (error) { $("#health-status").textContent = "Local service check failed"; showError(error); }
}
async function loadCases(selectId = "") {
  const payload = await api("/api/v2/cases");
  $("#case-select").innerHTML = `<option value="">Create or select a case</option>${payload.cases.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)} · ${escapeHtml(item.status)}</option>`).join("")}`;
  if (selectId) { $("#case-select").value = selectId; await selectCase(); }
}
async function selectCase() {
  activeCaseId = $("#case-select").value;
  const enabled = Boolean(activeCaseId);
  document.querySelectorAll(".locked").forEach(section => {
    section.classList.toggle("locked", !enabled);
    section.querySelectorAll("input,select,textarea,button").forEach(control => { control.disabled = !enabled; });
  });
  if (!enabled) { $("#case-summary").hidden = true; return; }
  const item = await api(`/api/v2/cases/${encodeURIComponent(activeCaseId)}`);
  $("#case-summary").hidden = false;
  $("#case-summary").innerHTML = `<strong>${escapeHtml(item.title)}</strong><span>Status: ${escapeHtml(item.status)}</span><span>Created: ${escapeHtml(item.created_at)}</span>`;
  $("#case-status-select").value = item.status;
  await Promise.all([loadEvidence(), loadReview(), loadCloseout()]);
}
async function loadEvidence() {
  const payload = await api(caseUrl("/evidence"));
  $("#evidence-list").innerHTML = payload.evidence.length ? `<table><caption class="sr-only">Evidence register</caption><tr><th>File</th><th>Parser</th><th>SHA-256</th><th>State</th><th>Actions</th></tr>${payload.evidence.map(item => `<tr><td>${escapeHtml(item.filename)}</td><td>${escapeHtml(item.parser)}</td><td><code>${escapeHtml(item.sha256)}</code></td><td>${escapeHtml(item.status)}</td><td><button class="small danger" data-delete-evidence="${escapeHtml(item.id)}">Soft delete</button></td></tr>`).join("")}</table>` : "<p>No evidence imported yet.</p>";
  document.querySelectorAll("[data-delete-evidence]").forEach(button => button.addEventListener("click", async () => {
    if (!confirm("Soft-delete this evidence? Its events will leave the timeline.")) return;
    try { await api(`/api/v2/evidence/${encodeURIComponent(button.dataset.deleteEvidence)}`, {method:"DELETE"}); setStatus("Evidence soft-deleted."); await loadEvidence(); await loadReview(); } catch (error) { showError(error); }
  }));
}
function timelineQuery() {
  const params = new URLSearchParams();
  [["actor","filter-actor"],["host","filter-host"],["source_type","filter-source"],["action","filter-action"]].forEach(([key, id]) => { if ($( "#" + id).value) params.set(key, $("#" + id).value); });
  if (timelineCursor) params.set("cursor", timelineCursor);
  params.set("limit", "25");
  return params.toString();
}
async function loadTimeline(reset = true) {
  if (reset) timelineCursor = null;
  const payload = await api(`${caseUrl("/timeline")}?${timelineQuery()}`);
  const rows = payload.events.map(event => `<tr><td>${escapeHtml(event.timestamp_utc)}</td><td>${escapeHtml(event.action)}</td><td>${escapeHtml(event.actor || "—")}</td><td>${escapeHtml(event.host || "—")}</td><td>${escapeHtml(event.source_type)}</td><td>${escapeHtml(event.object || event.raw_text || "—")}<button class="bookmark" data-bookmark-event="${escapeHtml(event.id)}" title="Bookmark event">☆</button></td></tr>`).join("");
  $("#timeline").innerHTML = rows ? `<table><caption class="sr-only">Normalized investigation timeline</caption><tr><th>Time</th><th>Action</th><th>Actor</th><th>Host</th><th>Source</th><th>Object / detail</th></tr>${rows}</table>` : "<p>No events match the current filters.</p>";
  $("#timeline-count").textContent = `${payload.events.length} event(s)`;
  timelineCursor = payload.next_cursor;
  $("#load-more").hidden = !timelineCursor;
  document.querySelectorAll("[data-bookmark-event]").forEach(button => button.addEventListener("click", () => bookmark({event_id: button.dataset.bookmarkEvent})));
}
async function loadReview() {
  await loadTimeline();
  const findings = await api(`${caseUrl("/findings")}`);
  $("#findings-list").innerHTML = findings.findings.length ? findings.findings.map(item => `<article class="finding ${escapeHtml(item.severity)}"><div class="finding-head"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.severity)} · ${escapeHtml(item.status)}</span></div><p>${escapeHtml(item.explanation)}</p><small>${item.event_ids.length} cited event(s) · Rule ${escapeHtml(item.rule_id)}</small><div class="finding-actions"><select data-finding-status="${escapeHtml(item.id)}"><option value="new">New</option><option value="confirmed">Confirmed</option><option value="dismissed">Dismissed</option></select><input data-finding-reason="${escapeHtml(item.id)}" placeholder="Reason required when dismissed"><button class="small" data-save-finding="${escapeHtml(item.id)}">Save review</button><button class="bookmark small secondary" data-bookmark-finding="${escapeHtml(item.id)}">Bookmark</button></div></article>`).join("") : "<p>No suspicious findings were generated.</p>";
  findings.findings.forEach(item => { const select = $(`[data-finding-status="${item.id}"]`); if (select) select.value = item.status; });
  document.querySelectorAll("[data-save-finding]").forEach(button => button.addEventListener("click", async () => {
    const id = button.dataset.saveFinding, status = $(`[data-finding-status="${id}"]`).value, reason = $(`[data-finding-reason="${id}"]`).value;
    try { await api(`/api/v2/findings/${encodeURIComponent(id)}/status`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({status, reason: reason || null})}); setStatus("Finding review saved."); await loadReview(); } catch (error) { showError(error); }
  }));
  document.querySelectorAll("[data-bookmark-finding]").forEach(button => button.addEventListener("click", () => bookmark({finding_id: button.dataset.bookmarkFinding})));
  const incidents = await api(caseUrl("/incidents"));
  $("#incidents-list").innerHTML = incidents.incidents.length ? incidents.incidents.map(item => `<article class="incident"><strong>${escapeHtml(item.title || item.id)}</strong><span>${escapeHtml(item.event_ids?.length || 0)} events</span><small>${escapeHtml(item.start || "")} – ${escapeHtml(item.end || "")}</small></article>`).join("") : "<p>No grouped incidents.</p>";
}
async function bookmark(value) { try { await api(caseUrl("/bookmarks"), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(value)}); setStatus("Bookmark added."); await loadCloseout(); } catch (error) { showError(error); } }
async function loadCloseout() {
  const [notes, tags, bookmarks] = await Promise.all([api(caseUrl("/notes")), api(caseUrl("/tags")), api(caseUrl("/bookmarks"))]);
  $("#notes-tags").innerHTML = `<h4>Notes</h4>${notes.notes.map(item => `<p class="note"><strong>${escapeHtml(item.author_id)}</strong> · ${escapeHtml(item.created_at)}<br>${escapeHtml(item.text)}</p>`).join("") || "<p>No notes yet.</p>"}<h4>Tags</h4><p>${tags.tags.map(item => `<span class="tag">${escapeHtml(item.name)}</span>`).join(" ") || "No tags yet."}</p>`;
  $("#bookmarks-list").innerHTML = bookmarks.bookmarks.map(item => `<span class="tag">${escapeHtml(item.event_id || item.finding_id)}</span>`).join(" ") || "<p>No bookmarks yet.</p>";
}

async function start(url, options = {}) {
  report.hidden = true; progress.hidden = false; clearError(); progressBar.value = 0;
  try { const payload = await api(url, options); activeJobId = payload.job_id; await poll(payload.job_id); }
  finally { if (!activeJobId) progress.hidden = true; }
}
async function poll(jobId) {
  for (;;) {
    const job = await api(`/api/v1/jobs/${encodeURIComponent(jobId)}`); progressBar.value = job.progress || 0; progressText.textContent = `${job.current_module || "queued"} (${job.progress || 0}%)`;
    if (job.status === "done") { await showReport(job.report_id); return; }
    if (job.status === "failed") throw new Error(job.error_message || "The analysis failed.");
    await new Promise(resolve => setTimeout(resolve, 600));
  }
}
async function showReport(id) {
  const r = await api(`/api/v1/reports/${encodeURIComponent(id)}`);
  const rows = r.signals.map(s => `<tr><td>${escapeHtml(s.name)}</td><td>${escapeHtml(s.strength)}</td><td>${escapeHtml(s.score ?? "—")}</td><td>${escapeHtml(s.reason)}</td></tr>`).join("");
  const maps = (r.heatmaps || []).map(item => `<figure><img src="/api/v1/reports/${encodeURIComponent(id)}/heatmaps/${encodeURIComponent(item.name)}" alt="${escapeHtml(item.description)}"><figcaption>${escapeHtml(item.description)}</figcaption></figure>`).join("");
  content.innerHTML = `<div class="tier" role="status">${escapeHtml(r.tier)} <small>Rule ${escapeHtml(r.applied_rule)}</small></div><p>${escapeHtml(r.explanation)}</p><p><strong>Uncertainty:</strong> ${escapeHtml(r.uncertainty?.level || "unknown")} — ${escapeHtml(r.uncertainty?.reason || "")}</p><h4>Signals</h4><div class="report-table"><table><tr><th>Module</th><th>Strength</th><th>Score</th><th>Reason</th></tr>${rows}</table></div><h4>Heatmaps</h4><div class="heatmaps">${maps || "<p>No heatmaps were produced.</p>"}</div><h4>Limitations</h4><ul>${r.limitations.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul><p><a download="media-provenance-report.html" href="/api/v1/reports/${encodeURIComponent(id)}/export">Download offline HTML export</a></p>`;
  progress.hidden = true; report.hidden = false; activeJobId = null;
}

$("#upload-form").addEventListener("submit", event => { event.preventDefault(); const file = $("#file").files[0]; if (!file) return showError(new Error("Select media before analyzing.")); start("/api/v1/analyze", {method:"POST", body:new FormData(event.currentTarget)}).catch(showError); });
cancelButton.addEventListener("click", async () => { if (!activeJobId) return; try { await api(`/api/v1/jobs/${encodeURIComponent(activeJobId)}/cancel`, {method:"POST"}); progressText.textContent = "Cancellation requested…"; } catch (error) { showError(error); } });
$("#case-form").addEventListener("submit", async event => { event.preventDefault(); try { const item = await api("/api/v2/cases", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({title:$("#case-title").value})}); event.target.reset(); setStatus("Case created."); await loadCases(item.id); } catch (error) { showError(error); } });
$("#case-select").addEventListener("change", () => selectCase().catch(showError));
$("#evidence-form").addEventListener("submit", async event => { event.preventDefault(); const file = $("#evidence-file").files[0]; if (!file) return; const data = new FormData(); data.append("parser", $("#evidence-kind").value); data.append("file", file); try { const item = await api(caseUrl("/evidence"), {method:"POST", body:data}); event.target.reset(); setStatus(`Imported ${item.event_count} event(s); SHA-256 ${item.sha256}.`); await Promise.all([loadEvidence(), loadReview()]); } catch (error) { showError(error); } });
$("#refresh-evidence").addEventListener("click", () => loadEvidence().catch(showError));
$("#apply-filters").addEventListener("click", () => loadTimeline().catch(showError));
$("#load-more").addEventListener("click", () => loadTimeline(false).catch(showError));
$("#refresh-findings").addEventListener("click", () => loadReview().catch(showError));
$("#note-form").addEventListener("submit", async event => { event.preventDefault(); try { await api(caseUrl("/notes"), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text:$("#note-text").value})}); event.target.reset(); setStatus("Note added."); await loadCloseout(); } catch (error) { showError(error); } });
$("#tag-form").addEventListener("submit", async event => { event.preventDefault(); try { await api(caseUrl("/tags"), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name:$("#tag-name").value})}); event.target.reset(); setStatus("Tag added."); await loadCloseout(); } catch (error) { showError(error); } });
$("#verify-custody").addEventListener("click", async () => { try { const items = await api(caseUrl("/evidence")); if (!items.evidence.length) { $("#custody-status").textContent = "Import evidence before verifying custody."; return; } const results = await Promise.all(items.evidence.map(item => api(`/api/v2/evidence/${encodeURIComponent(item.id)}/custody`))); $("#custody-status").textContent = results.every(item => item.valid) ? "All evidence custody chains are valid." : "One or more custody chains require attention."; } catch (error) { showError(error); } });
$("#update-case-status").addEventListener("click", async () => { try { await api(caseUrl("/status"), {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({status:$("#case-status-select").value, reason:$("#status-reason").value || null})}); setStatus("Case status updated."); await loadCases(activeCaseId); } catch (error) { showError(error); } });
loadHealth(); loadCases().catch(showError);
