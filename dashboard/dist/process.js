(() => {
  const videoInput = document.querySelector("#mission-video");
  const telemetryInput = document.querySelector("#mission-telemetry");
  const originalButton = document.querySelector("#process-button");
  const button = originalButton.cloneNode(true);
  originalButton.replaceWith(button);
  const notice = document.querySelector("#upload-notice");
  const processingDetails = document.querySelector("#processing-details");
  const profileSelect = document.querySelector("#processing-profile");
  const uploadFeedback = document.querySelector("#upload-feedback");
  const videoUploadState = document.querySelector("#video-upload-state");
  const telemetryUploadState = document.querySelector("#telemetry-upload-state");
  const modelLibrary = document.querySelector("#model-library");
  const modelSwitches = document.querySelector("#model-switches");
  const activeModelLabel = document.querySelector("#active-model-label");
  const heroViewerLink = document.querySelector("#hero-viewer-link");
  const openModelLink = document.querySelector("#open-model-link");
  const fallbackCatalog = { active_mode: "precision", models: { precision: { label: "Precision model", status: "ready", asset_base: "assets" } } };
  const statusBox = document.createElement("div");
  statusBox.className = "run-indicator";
  statusBox.hidden = true;
  statusBox.setAttribute("aria-live", "polite");
  statusBox.innerHTML = "<span class=\"spinner\"></span><div><strong></strong><small></small></div>";
  button.insertAdjacentElement("afterend", statusBox);
  const stage = statusBox.querySelector("strong");
  const elapsed = statusBox.querySelector("small");
  let pollTimer;
  let elapsedTimer;
  let processingActive = false;
  let latestStatus;

  function viewerUrl(mode) { return "textured_viewer.html?mode=" + encodeURIComponent(mode); }

  function renderModelCatalog(catalog) {
    const models = catalog && catalog.models && typeof catalog.models === "object" ? catalog.models : fallbackCatalog.models;
    const available = ["rapid", "precision"].filter(mode => models[mode] && models[mode].status === "ready");
    const active = available.includes(catalog && catalog.active_mode) ? catalog.active_mode : (available.includes("precision") ? "precision" : available[0]);
    if (!active || available.length < 2) { modelLibrary.hidden = true; return; }
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

  function selectedFiles() {
    return { video: videoInput.files[0], telemetry: telemetryInput.files[0] };
  }

  function selectedProfileLabel() {
    return profileSelect.value === "rapid" ? "Rapid preview" : "Precision model";
  }

  function formatElapsed(seconds) {
    const whole = Math.max(0, Math.floor(seconds || 0));
    const minutes = Math.floor(whole / 60);
    const remaining = whole % 60;
    return minutes ? minutes + "m " + String(remaining).padStart(2, "0") + "s" : remaining + "s";
  }

  function renderRunIndicator(data) {
    const active = data && (data.status === "running" || data.status === "cancelling");
    processingActive = Boolean(active);
    statusBox.hidden = !active;
    button.classList.toggle("is-stop", data && data.status === "running");
    button.disabled = Boolean(data && data.status === "cancelling");
    if (!active) {
      button.textContent = "Build " + selectedProfileLabel();
      if (data && data.status === "cancelled") {
        notice.hidden = false;
        notice.textContent = "Reconstruction stopped. No partial model was published.";
      }
      return;
    }
    if (processingDetails) processingDetails.open = true;
    const isCancelling = data.status === "cancelling";
    stage.textContent = isCancelling ? "Stopping local reconstruction…" : (data.stage || "Preparing local reconstruction…");
    const startedAt = Number(data.started_at);
    const elapsedText = Number.isFinite(startedAt) ? "Elapsed " + formatElapsed(Date.now() / 1000 - startedAt) : "Working locally";
    const estimate = data.profile === "rapid" ? "Rapid usually takes 15–40 min" : "Precision usually takes 30–90 min";
    elapsed.textContent = isCancelling ? "Please wait a few seconds for local tools to close." : elapsedText + " · " + estimate;
    button.textContent = isCancelling ? "Stopping…" : "Stop processing";
  }

  function startPolling() {
    if (!pollTimer) pollTimer = setInterval(checkStatus, 2000);
    if (!elapsedTimer) elapsedTimer = setInterval(() => renderRunIndicator(latestStatus), 1000);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    if (elapsedTimer) clearInterval(elapsedTimer);
    pollTimer = undefined;
    elapsedTimer = undefined;
  }

  function showStatus(data) {
    latestStatus = data;
    renderRunIndicator(data);
    const active = data.status === "running" || data.status === "cancelling";
    if (active) startPolling();
    else stopPolling();
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
  }

  async function checkStatus() {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      if (response.ok) showStatus(await response.json());
    } catch { /* The static preview has no local job API. */ }
  }

  function refreshRunButton() {
    if (!processingActive) button.textContent = "Build " + selectedProfileLabel();
  }

  function showSelection() {
    const selection = selectedFiles();
    videoUploadState.textContent = selection.video ? "✓ Video: " + selection.video.name : "Video: waiting";
    telemetryUploadState.textContent = selection.telemetry ? "✓ SRT: " + selection.telemetry.name : "SRT: waiting";
    uploadFeedback.classList.toggle("complete", Boolean(selection.video && selection.telemetry));
    notice.hidden = false;
    if (!selection.video || !selection.telemetry) {
      const missing = !selection.video ? "video" : "matching DJI SRT";
      notice.textContent = "Choose the " + missing + " to complete this mission package.";
      return;
    }
    notice.textContent = "Mission package ready: " + selection.video.name + " + " + selection.telemetry.name + ". Build " + selectedProfileLabel() + " to create a separately saved result.";
  }

  async function cancelProcessing() {
    button.disabled = true;
    button.textContent = "Stopping…";
    try {
      const response = await fetch("/api/cancel", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not stop the local reconstruction.");
      showStatus(data);
      startPolling();
    } catch (error) {
      button.disabled = false;
      button.textContent = "Stop processing";
      notice.hidden = false;
      notice.textContent = "Could not stop processing: " + error.message;
    }
  }

  videoInput.addEventListener("change", showSelection);
  telemetryInput.addEventListener("change", showSelection);
  profileSelect.addEventListener("change", () => { refreshRunButton(); if (videoInput.files[0] || telemetryInput.files[0]) showSelection(); });

  button.addEventListener("click", async () => {
    if (processingActive) {
      await cancelProcessing();
      return;
    }
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
    } catch (error) {
      notice.hidden = false;
      notice.textContent = "Could not start processing: " + error.message + ". Run the dashboard using python3 dashboard/server.py.";
      button.disabled = false;
      button.textContent = "Build " + selectedProfileLabel();
    }
  });

  addEventListener("pagehide", () => {
    if (processingActive && navigator.sendBeacon) {
      navigator.sendBeacon("/api/cancel", new Blob([], { type: "text/plain" }));
    }
  });

  refreshRunButton();
  loadModelCatalog();
  checkStatus();
})();
