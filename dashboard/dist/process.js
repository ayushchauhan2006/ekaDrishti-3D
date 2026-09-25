(() => {
  const originalInput = document.querySelector("#mission-files");
  const input = originalInput.cloneNode(true);
  originalInput.replaceWith(input);
  const originalButton = document.querySelector("#process-button");
  const button = originalButton.cloneNode(true);
  originalButton.replaceWith(button);
  const notice = document.querySelector("#upload-notice");
  const pipeline = document.querySelector("#pipeline");
  const processingDetails = document.querySelector("#processing-details");
  const profileSelect = document.querySelector("#processing-profile");
  const modelLibrary = document.querySelector("#model-library");
  const modelSwitches = document.querySelector("#model-switches");
  const activeModelLabel = document.querySelector("#active-model-label");
  const heroViewerLink = document.querySelector("#hero-viewer-link");
  const openModelLink = document.querySelector("#open-model-link");
  const fallbackCatalog = { active_mode: "precision", models: { precision: { label: "Precision model", status: "ready", asset_base: "assets" } } };
  const statusBox = document.createElement("div");
  statusBox.className = "job-status";
  statusBox.hidden = true;
  statusBox.setAttribute("aria-live", "polite");
  statusBox.innerHTML = "<span class=\"spinner\"></span><div><strong></strong><small></small></div>";
  pipeline.insertAdjacentElement("afterend", statusBox);
  const stage = statusBox.querySelector("strong");
  const log = statusBox.querySelector("small");
  let pollTimer;

  function viewerUrl(mode) { return "textured_viewer.html?mode=" + encodeURIComponent(mode); }

  function renderModelCatalog(catalog) {
    const models = catalog && catalog.models && typeof catalog.models === "object" ? catalog.models : fallbackCatalog.models;
    const available = ["rapid", "precision"].filter(mode => models[mode] && models[mode].status === "ready");
    const active = available.includes(catalog && catalog.active_mode) ? catalog.active_mode : (available.includes("precision") ? "precision" : available[0]);
    if (!active) { modelLibrary.hidden = true; return; }
    const activeModel = models[active];
    const activeLabel = activeModel.label || (active === "rapid" ? "Rapid preview" : "Precision model");
    activeModelLabel.textContent = activeLabel + " is the latest completed model";
    heroViewerLink.href = viewerUrl(active);
    openModelLink.href = viewerUrl(active);
    modelSwitches.replaceChildren();
    available.forEach(mode => {
      const model = models[mode];
      const link = document.createElement("a");
      link.className = "model-choice" + (mode === active ? " active" : "");
      link.href = viewerUrl(mode);
      const title = document.createElement("strong");
      title.textContent = model.label || (mode === "rapid" ? "Rapid preview" : "Precision model");
      const detail = document.createElement("small");
      const frames = Number(model.frames_selected);
      detail.textContent = mode === active ? "Latest completed · Open viewer" : (Number.isFinite(frames) && frames > 0 ? frames + " retained frames · Open viewer" : "Completed result · Open viewer");
      link.append(title, detail);
      modelSwitches.append(link);
    });
    modelLibrary.hidden = false;
  }

  async function loadModelCatalog() {
    try {
      const response = await fetch("/api/models", { cache: "no-store" });
      if (!response.ok) throw new Error("No model catalog");
      renderModelCatalog(await response.json());
    } catch {
      renderModelCatalog(fallbackCatalog);
    }
  }

  function showStatus(data) {
    const active = data.status === "running";
    if (active && processingDetails) processingDetails.open = true;
    statusBox.hidden = !data.stage;
    stage.textContent = data.stage || "";
    log.textContent = Array.isArray(data.log) && data.log.length ? data.log.at(-1) : (data.message || "");
    button.disabled = active;
    button.textContent = active ? "Processing locally…" : "Process mission";
    if (data.status === "complete") {
      const label = data.profile === "rapid" ? "Rapid preview" : "Precision model";
      notice.hidden = false;
      notice.textContent = label + " is ready. Both completed quality modes are kept separately in Available 3D results.";
      loadModelCatalog();
    }
    if (data.status === "failed") {
      notice.hidden = false;
      notice.textContent = "Processing stopped: " + (data.message || "Check the dashboard terminal.");
    }
    if (!active && pollTimer) { clearInterval(pollTimer); pollTimer = undefined; }
  }

  async function checkStatus() {
    try { showStatus(await (await fetch("/api/status", { cache: "no-store" })).json()); }
    catch { /* A static preview has no local job API. */ }
  }

  function selectedFiles() {
    const files = Array.from(input.files);
    return {
      video: files.find(file => file.name.toLowerCase().endsWith(".mp4") || file.name.toLowerCase().endsWith(".mov")),
      telemetry: files.find(file => file.name.toLowerCase().endsWith(".srt")),
    };
  }

  input.addEventListener("change", () => {
    const selection = selectedFiles();
    notice.hidden = false;
    if (!selection.video || !selection.telemetry) {
      notice.textContent = "Choose the original DJI MP4 and its matching DJI SRT file.";
      return;
    }
    const profileLabel = profileSelect.value === "rapid" ? "Rapid preview" : "Precision model";
    notice.textContent = "Mission selected: " + selection.video.name + " + " + selection.telemetry.name + ". It will be processed as a separate " + profileLabel + " result.";
  });

  button.addEventListener("click", async () => {
    const selection = selectedFiles();
    if (!selection.video || !selection.telemetry) {
      notice.hidden = false;
      notice.textContent = "Choose the original DJI MP4 and its matching DJI SRT before starting reconstruction.";
      return;
    }
    const payload = new FormData();
    payload.append("video", selection.video);
    payload.append("telemetry", selection.telemetry);
    payload.append("profile", profileSelect.value || "precision");
    button.disabled = true;
    button.textContent = "Sending mission…";
    try {
      const response = await fetch("/api/process", { method: "POST", body: payload });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The local server rejected this mission.");
      showStatus(data);
      pollTimer = setInterval(checkStatus, 2000);
    } catch (error) {
      notice.hidden = false;
      notice.textContent = "Could not start processing: " + error.message + ". Run the dashboard using python3 dashboard/server.py.";
      button.disabled = false;
      button.textContent = "Process mission";
    }
  });

  loadModelCatalog();
  checkStatus();
})();
