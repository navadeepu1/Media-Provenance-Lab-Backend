const samples = document.querySelector("#samples");
const progress = document.querySelector("#progress");
const progressText = document.querySelector("#progress-text");
const progressBar = document.querySelector("#progress-bar");
const report = document.querySelector("#report");
const content = document.querySelector("#report-content");

async function start(url, options = {}) {
  report.hidden = true; progress.hidden = false; progressBar.value = 0;
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error?.message || "The analysis could not start.");
  await poll(payload.job_id);
}
async function poll(jobId) {
  for (;;) {
    const job = await (await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`)).json();
    progressBar.value = job.progress || 0;
    progressText.textContent = `${job.current_module || "queued"} (${job.progress || 0}%)`;
    if (job.status === "done") { await showReport(job.report_id); return; }
    if (job.status === "failed") throw new Error(job.error_message || "The analysis failed.");
    await new Promise(resolve => setTimeout(resolve, 600));
  }
}
async function showReport(id) {
  const r = await (await fetch(`/api/v1/reports/${encodeURIComponent(id)}`)).json();
  const rows = r.signals.map(s => `<tr><td>${escapeHtml(s.name)}</td><td>${s.strength}</td><td>${s.score ?? "—"}</td><td>${escapeHtml(s.reason)}</td></tr>`).join("");
  const maps = r.heatmaps.map(h => `<figure><img src="/api/v1/reports/${id}/heatmaps/${encodeURIComponent(h.name)}" alt="${escapeHtml(h.description)}"><figcaption>${escapeHtml(h.description)}</figcaption></figure>`).join("");
  content.innerHTML = `<div class="tier">${r.tier} <small>Rule ${r.applied_rule}</small></div><p>${escapeHtml(r.explanation)}</p>
    <p>Explanation source: <strong>${r.explanation_source}</strong></p><h3>Signals</h3><table><tr><th>Module</th><th>Strength</th><th>Score</th><th>Reason</th></tr>${rows}</table>
    <h3>Heatmaps</h3><div class="heatmaps">${maps || "<p>No heatmaps were produced.</p>"}</div>
    <h3>Context</h3><p>Known-item matches are context only. Reverse-search sites require you to upload the file yourself.</p>
    <p>${r.reverse_search.map(x => `<a target="_blank" rel="noopener noreferrer" href="${x.url}">${x.name}</a>`).join(" · ")}</p>
    <h3>Limitations</h3><ul>${r.limitations.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
    <p><a download="media-provenance-report.html" href="/api/v1/reports/${id}/export">Download offline HTML export</a> · <a href="/api/v1/methodology">Methodology</a></p>`;
  progress.hidden = true; report.hidden = false;
}
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" })[c]); }
async function loadSamples() {
  const items = await (await fetch("/api/v1/samples")).json();
  samples.innerHTML = items.map(s => `<button class="card" data-id="${s.id}"><strong>${escapeHtml(s.title)}</strong><br><span>${escapeHtml(s.description)}</span></button>`).join("");
  samples.querySelectorAll("button").forEach(button => button.addEventListener("click", () => start(`/api/v1/samples/${encodeURIComponent(button.dataset.id)}/analyze`)));
}
document.querySelector("#upload-form").addEventListener("submit", event => {
  event.preventDefault(); const data = new FormData(event.currentTarget);
  start("/api/v1/analyze", { method:"POST", body:data }).catch(error => { progressText.textContent = error.message; });
});
loadSamples().catch(error => { samples.textContent = error.message; });

