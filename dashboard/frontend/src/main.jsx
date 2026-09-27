import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../dist/styles.css";
import "../../dist/compliance.css";
import "./react.css";

const EMPTY_CATALOG = { active_mode: null, models: {} };

function formatMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (Math.abs(number) >= 1000000) return (number / 1000000).toFixed(2).replace(/\.?0+$/, "") + "M";
  if (Math.abs(number) >= 1000) return (number / 1000).toFixed(1).replace(/\.?0+$/, "") + "K";
  return String(Math.round(number));
}

function missionNameFromFile(file) {
  const filename = typeof file === "string" ? file : file?.name;
  const basename = String(filename || "Drone mission").split(/[\\/]/).pop();
  return basename.replace(/\.[^.]+$/, "") || "Drone mission";
}

function friendlyMissionName(name) {
  return String(name || "your mission").replaceAll("_", " ");
}

function viewerUrl(mode) {
  return mode ? "textured_viewer.html?mode=" + encodeURIComponent(mode) : "#";
}

function modelModes(catalog) {
  const models = catalog?.models && typeof catalog.models === "object" ? catalog.models : {};
  return ["rapid", "precision"].filter((mode) => models[mode]?.status === "ready");
}

function statusIsActive(status) {
  return status === "running" || status === "cancelling";
}

function formatElapsed(seconds) {
  const whole = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(whole / 60);
  const remaining = whole % 60;
  return minutes ? minutes + "m " + String(remaining).padStart(2, "0") + "s" : remaining + "s";
}

function SummaryMetrics({ summary }) {
  const frames = Number(summary?.frames_selected);
  const triangles = Number(summary?.triangles);
  const gps = Number(summary?.gps_rmse_m);
  const east = Number(summary?.extent_east_m);
  const north = Number(summary?.extent_north_m);
  const frameText = Number.isFinite(frames) ? formatMetric(frames) : "—";
  const triangleText = Number.isFinite(triangles) ? formatMetric(triangles) : "—";
  const gpsText = Number.isFinite(gps) ? Math.round(gps * 100) + " cm" : "—";
  const areaText = Number.isFinite(east) && Number.isFinite(north) ? Math.round(east) + " × " + Math.round(north) + " m" : "—";
  return {
    frameText,
    triangleText,
    gpsText,
    areaText,
  };
}

function MissionMetrics({ summary }) {
  const metrics = SummaryMetrics({ summary });
  return (
    <section className="metric-grid mission-metrics" aria-label="Mission results">
      <article className="metric"><span>3D surface</span><strong>{metrics.triangleText}</strong><small>photo-textured triangles</small></article>
      <article className="metric"><span>Visual coverage</span><strong>{metrics.frameText}</strong><small>registered DJI frames</small></article>
      <article className="metric"><span>GPS consistency</span><strong>{metrics.gpsText}</strong><small>internal horizontal agreement</small></article>
      <article className="metric"><span>Mapped area</span><strong>{metrics.areaText}</strong><small>observed terrain footprint</small></article>
    </section>
  );
}

function MissionHero({ catalog, activeModel, activeMode, pendingName, profile, onProfileChange, video, telemetry, onVideoChange, onTelemetryChange, onProcess, onCancel, status, sending }) {
  const pending = Boolean(pendingName);
  const label = pending
    ? pendingName + " · " + (profile === "rapid" ? "RAPID PREVIEW" : "PRECISION MODEL") + " SELECTED"
    : activeModel?.mission?.name
      ? activeModel.mission.name + " · " + (activeModel.label || "PRECISION MODEL").toUpperCase() + " READY"
      : "MISSION READY";
  const name = pending ? friendlyMissionName(pendingName) : friendlyMissionName(activeModel?.mission?.name);
  const heading = pending ? "Build " + name + " in 3D." : activeModel?.mission?.name ? "Explore " + name + " in 3D." : "Explore your mission in 3D.";
  const description = pending
    ? "Ready to build a photo-textured 3D reconstruction from " + pendingName + " and its matching DJI telemetry."
    : activeModel?.mission?.name
      ? "Photo-textured 3D reconstruction built from " + activeModel.mission.name + " and its matching DJI telemetry. Inspect the real scene geometry visible in the uploaded flight."
      : "Upload a drone video and matching DJI telemetry to build a photo-textured metric reconstruction.";
  const metrics = SummaryMetrics({ summary: pending ? null : activeModel?.mission });
  const isCancelling = status?.status === "cancelling";
  const active = statusIsActive(status?.status);
  const buttonText = sending ? "Sending mission…" : isCancelling ? "Stopping…" : active ? "Stop processing" : "Build " + (profile === "rapid" ? "Rapid preview" : "Precision model");
  const canProcess = Boolean(video && telemetry);

  return (
    <section className="mission-hero" aria-labelledby="mission-heading">
      <div className="hero-copy">
        <p className="eyebrow" id="mission-label">{label}</p>
        <h1 id="mission-heading">{heading}</h1>
        <p id="mission-description">{description}</p>
        <div className="hero-proof">
          <span><b>{metrics.frameText}</b> matched views</span>
          <span><b>{metrics.triangleText}</b> surface triangles</span>
          <span><b>{metrics.gpsText}</b> GPS agreement</span>
          <span><b>AI</b> frame audit</span>
        </div>
      </div>
      <div className="hero-actions">
        <a className="viewer-feature" id="hero-viewer-link" href={viewerUrl(activeMode)} target="_blank" rel="noopener">
          <span className="viewer-orbit">3D</span>
          <span><strong>Explore interactive 3D model</strong><small>Orbit 360°, zoom close, and inspect every visible surface</small></span>
          <b>→</b>
        </a>
        <div className="mission-tools">
          <div className="new-run-settings">
            <label className="profile-control">
              <span>New run quality</span>
              <select value={profile} onChange={(event) => onProfileChange(event.target.value)}>
                <option value="rapid">Rapid preview</option>
                <option value="precision">Precision model</option>
              </select>
            </label>
            <small>Upload an original DJI video and matching SRT. The selected mode creates its own saved model.</small>
          </div>
          <div className="upload-inputs">
            <label className="button secondary" htmlFor="mission-video">1. Choose video
              <input id="mission-video" type="file" accept="video/mp4,video/quicktime,.mp4,.mov" hidden onChange={onVideoChange} />
            </label>
            <label className="button secondary" htmlFor="mission-telemetry">2. Choose DJI SRT
              <input id="mission-telemetry" type="file" accept=".srt,text/plain" hidden onChange={onTelemetryChange} />
            </label>
          </div>
          <p className={"upload-feedback" + (video && telemetry ? " complete" : "")} aria-live="polite">
            <span>{video ? "✓ Video: " + video.name : "Video: waiting"}</span>
            <span>{telemetry ? "✓ SRT: " + telemetry.name : "SRT: waiting"}</span>
          </p>
          {active && (
            <div className="run-indicator" aria-live="polite">
              <span className="spinner"></span>
              <div><strong>{isCancelling ? "Stopping local reconstruction…" : (status.stage || "Preparing local reconstruction…")}</strong><small>{isCancelling ? "Please wait a few seconds for local tools to close." : "Elapsed " + formatElapsed(Date.now() / 1000 - Number(status.started_at || Date.now() / 1000)) + " · " + (profile === "rapid" ? "Rapid usually takes 15–40 min" : "Precision usually takes 30–90 min")}</small></div>
            </div>
          )}
          <button className={"button primary" + (active && !isCancelling ? " is-stop" : "")} type="button" disabled={sending || isCancelling} onClick={active ? onCancel : onProcess}>{buttonText}</button>
        </div>
        <ModelLibrary catalog={catalog} />
      </div>
    </section>
  );
}

function ModelLibrary({ catalog }) {
  const available = modelModes(catalog);
  if (available.length < 2) return null;
  const active = catalog.active_mode;
  return (
    <section className="model-library" aria-label="Available 3D model results">
      <div className="model-library-copy"><p className="eyebrow">AVAILABLE 3D RESULTS</p><strong>{catalog.models[active]?.label || "Model"} is the latest completed model</strong><small>Choose a completed reconstruction to inspect it in the 3D viewer.</small></div>
      <div className="model-switches">
        {available.map((mode) => <a key={mode} className={"model-choice" + (mode === active ? " active" : "")} href={viewerUrl(mode)} target="_blank" rel="noopener"><strong>{catalog.models[mode].label}</strong><small>{mode === active ? "Latest completed · Open viewer" : "Completed result · Open viewer"}</small></a>)}
      </div>
    </section>
  );
}

function OutcomePanels({ activeMode, onAccuracy }) {
  return (
    <section className="outcome-grid">
      <article className="panel explore-panel">
        <div className="panel-heading"><div><p className="eyebrow">MAIN FEATURE</p><h2>Your interactive 3D world</h2></div><span className="pill success">Ready now</span></div>
        <p className="panel-copy">The primary experience is the metric textured 3D viewer. Rotate above or below the model, zoom into a roof, pan across the compound, and measure two observed surface points.</p>
        <a className="open-model-button" href={viewerUrl(activeMode)} target="_blank" rel="noopener">Open the 3D viewer <span>→</span></a>
        <div className="feature-list"><span>360° free orbit</span><span>Metric measurement</span><span>AI frame audit</span><span>RTK-aligned</span></div>
      </article>
      <article className="panel trust-panel">
        <div className="panel-heading"><div><p className="eyebrow">MISSION CONFIDENCE</p><h2>What the result means</h2></div></div>
        <div className="trust-row"><b>✓</b><div><strong>Real scene geometry</strong><small>Built from overlapping drone frames, not generated imagery.</small></div></div>
        <div className="trust-row"><b>✓</b><div><strong>AI dynamic-object audit</strong><small>People, vehicles, and animals are audited before reconstruction.</small></div></div>
        <div className="trust-row"><b>✓</b><div><strong>Located by RTK telemetry</strong><small>Camera path is aligned to the original DJI flight data.</small></div></div>
        <div className="trust-row"><b>!</b><div><strong>Use checkpoints for surveying</strong><small>Ground control is still needed before making an absolute accuracy claim.</small></div></div>
        <button className="text-button" type="button" onClick={onAccuracy}>How to present accuracy <span>→</span></button>
      </article>
    </section>
  );
}

function ProcessingRecord({ summary }) {
  const frameText = summary?.frames_selected ? formatMetric(summary.frames_selected) : "Selected frames";
  return (
    <details className="processing-details">
      <summary>Mission processing record <span>View technical steps</span></summary>
      <ol className="pipeline">
        <li className="done"><span className="step-icon">✓</span><div><strong>Mission input validated</strong><small>Original DJI video and matching RTK SRT accepted</small></div><time>Ready</time></li>
        <li className="done"><span className="step-icon">✓</span><div><strong>AI frame audit</strong><small>{frameText} checked for people, vehicles, and animals</small></div><time>Verified</time></li>
        <li className="done"><span className="step-icon">✓</span><div><strong>Visual reconstruction</strong><small>Overlapping camera views registered into one scene</small></div><time>Done</time></li>
        <li className="done"><span className="step-icon">✓</span><div><strong>RTK alignment</strong><small>Telemetry consistency is measured in the completed report</small></div><time>Verified</time></li>
        <li className="done"><span className="step-icon">✓</span><div><strong>Dense model and texture</strong><small>Photo-textured metric surface produced locally</small></div><time>Done</time></li>
      </ol>
    </details>
  );
}

function App() {
  const [catalog, setCatalog] = useState(EMPTY_CATALOG);
  const [status, setStatus] = useState({ status: "idle", message: "Choose a new MP4 and SRT mission package to begin." });
  const [profile, setProfile] = useState("precision");
  const [video, setVideo] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const dialogRef = useRef(null);

  const available = modelModes(catalog);
  const activeMode = available.includes(catalog.active_mode) ? catalog.active_mode : available.includes("precision") ? "precision" : available[0];
  const activeModel = activeMode ? catalog.models[activeMode] : null;
  const pendingName = video && status.status !== "complete" ? missionNameFromFile(video) : null;

  const loadCatalog = async () => {
    try {
      const response = await fetch("/api/models", { cache: "no-store" });
      if (!response.ok) throw new Error("No model catalog");
      setCatalog(await response.json());
    } catch {
      setCatalog(EMPTY_CATALOG);
    }
  };

  const checkStatus = async () => {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      if (response.ok) {
        const data = await response.json();
        setStatus(data);
        if (data.status === "complete") {
          setNotice((data.profile === "rapid" ? "Rapid preview" : "Precision model") + " is ready. The completed result is available in the 3D viewer.");
          await loadCatalog();
        } else if (data.status === "failed") {
          setNotice("Processing stopped: " + (data.message || "Check the dashboard terminal."));
        } else if (data.status === "cancelled") {
          setNotice("Reconstruction stopped. No partial model was published.");
        }
      }
    } catch {
      // The static page remains usable when the local job API is unavailable.
    }
  };

  useEffect(() => {
    loadCatalog();
    checkStatus();
  }, []);

  useEffect(() => {
    if (!statusIsActive(status.status)) return undefined;
    const poll = setInterval(checkStatus, 2000);
    const ticker = setInterval(() => setClock(Date.now()), 1000);
    return () => { clearInterval(poll); clearInterval(ticker); };
  }, [status.status]);

  useEffect(() => {
    if (statusIsActive(status.status)) setClock(Date.now());
  }, [status.stage, status.status]);

  const handleProcess = async () => {
    if (!video || !telemetry) {
      setNotice("Choose the original DJI video and its matching DJI SRT before starting reconstruction.");
      return;
    }
    const payload = new FormData();
    payload.append("video", video);
    payload.append("telemetry", telemetry);
    payload.append("profile", profile);
    setSending(true);
    setNotice("");
    try {
      const response = await fetch("/api/process", { method: "POST", body: payload });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The local server rejected this mission.");
      setStatus(data);
    } catch (error) {
      setNotice("Could not start processing: " + error.message + ". Run the dashboard using python dashboard/server.py.");
    } finally {
      setSending(false);
    }
  };

  const handleCancel = async () => {
    setSending(true);
    try {
      const response = await fetch("/api/cancel", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not stop the local reconstruction.");
      setStatus(data);
    } catch (error) {
      setNotice("Could not stop processing: " + error.message);
    } finally {
      setSending(false);
    }
  };

  const selectedSummary = pendingName ? null : activeModel?.mission;
  const showNotice = notice || (status.status === "failed" ? status.message : "");
  const elapsedNow = clock;

  return (
    <main className="shell focused-shell">
      <header className="topbar">
        <div className="brand" aria-label="EkaDrishti 3D"><span className="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><div><strong>EkaDrishti</strong><span>RTK 3D Mission Studio</span></div></div>
        <div className="top-status"><span className="dot"></span>{activeModel ? "Model ready" : "Ready for mission"}</div>
      </header>
      <MissionHero
        catalog={catalog}
        activeModel={activeModel}
        activeMode={activeMode}
        pendingName={pendingName}
        profile={profile}
        onProfileChange={setProfile}
        video={video}
        telemetry={telemetry}
        onVideoChange={(event) => { setVideo(event.target.files?.[0] || null); setStatus((current) => current.status === "complete" ? { status: "idle", message: "Choose a new MP4 and SRT mission package to begin." } : current); }}
        onTelemetryChange={(event) => setTelemetry(event.target.files?.[0] || null)}
        onProcess={handleProcess}
        onCancel={handleCancel}
        status={{ ...status, clock: elapsedNow }}
        sending={sending}
      />
      {showNotice && <section className="upload-notice" aria-live="polite">{showNotice}</section>}
      <MissionMetrics summary={selectedSummary} />
      <OutcomePanels activeMode={activeMode} onAccuracy={() => dialogRef.current?.showModal()} />
      <ProcessingRecord summary={selectedSummary} />
      <dialog ref={dialogRef} id="details-dialog">
        <button className="dialog-close" type="button" aria-label="Close" onClick={() => dialogRef.current?.close()}>×</button>
        <p className="eyebrow">ACCURACY NOTE</p><h2>How to present this result</h2>
        <p>EkaDrishti reconstructs the visible scene from overlapping drone frames, then aligns the camera path using the matching DJI RTK telemetry.</p>
        <p>For any stated absolute-accuracy threshold, complete one of the supplied checkpoint or reference-dimension CSV templates and run the independent evaluator.</p>
      </dialog>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
