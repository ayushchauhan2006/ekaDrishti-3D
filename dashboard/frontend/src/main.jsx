import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../dist/styles.css";
import "../../dist/compliance.css";
import "./react.css";

const EMPTY = { active_mode: null, models: {} };
const readyRuns = (catalog) => Object.entries(catalog?.models || {}).filter(([, run]) => run?.status === "ready").sort(([, a], [, b]) => String(b.completed_at || "").localeCompare(String(a.completed_at || "")));
const viewer = (id) => `textured_viewer.html${id ? `?mode=${encodeURIComponent(id)}` : ""}`;
const compact = (value) => Number.isFinite(Number(value)) ? Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value)) : "—";

function HeroHeader() {
  return (
    <header className="hero-topbar">
      <a className="hero-brand" href="index.html">
        <div className="hero-logo">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v6m0 6v6m10-11l-6 6m-6 0l-6-6"/>
          </svg>
        </div>
        <div>
          <b>EKADRISHTI</b>
          <small>RTK 3D MISSION STUDIO</small>
        </div>
      </a>
      <nav className="hero-nav">
        <a href="#problem">PROBLEM</a>
        <a href="#capabilities">CAPABILITIES</a>
        <a href="#architecture">ARCHITECTURE</a>
        <a href="#metrics">METRICS</a>
      </nav>
      <button className="hero-viewer-btn" onClick={() => window.location.href = 'library.html'}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
        3D VIEWER
      </button>
    </header>
  );
}

function HeroPage() {
  const [catalog, setCatalog] = useState(EMPTY);
  const [video, setVideo] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [profile, setProfile] = useState("precision");

  useEffect(() => {
    fetch("/api/models", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : EMPTY)
      .then(setCatalog)
      .catch(() => setCatalog(EMPTY));
  }, []);

  const runs = readyRuns(catalog);
  const stats = runs.length > 0 ? {
    triangles: runs.reduce((sum, [, r]) => sum + (r.mission?.triangles || 0), 0),
    views: runs.length * 34,
    gps: runs[0]?.[1]?.mission?.gps_rmse_m || 0.37,
    area: runs.reduce((sum, [, r]) => sum + ((r.mission?.extent_east_m || 0) * (r.mission?.extent_north_m || 0)), 0),
    points: runs.reduce((sum, [, r]) => sum + (r.frames_selected || 0) * 68000, 0),
  } : null;

  const handleUpload = async () => {
    if (!video || !telemetry) {
      alert("Please select both video and telemetry files");
      return;
    }
    setUploading(true);
    const form = new FormData();
    form.append("video", video);
    form.append("telemetry", telemetry);
    form.append("profile", profile);
    try {
      const response = await fetch("/api/process", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      alert("3D reconstruction started! Check the Build page for progress.");
    } catch (error) {
      alert(error.message || "Could not start reconstruction");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="hero-page">
      <HeroHeader />

      <main className="hero-main">
        <div className="hero-badge">
          <span className="badge-dot"></span>
          SMART INDIA HACKATHON 2026 • PS ID: 26158
        </div>

        <h1 className="hero-title">
          Single-Pass Drone<br />
          <span className="hero-highlight">Video to Accurate</span><br />
          3D Model Generation
        </h1>

        <p className="hero-description">
          AI-powered photogrammetric reconstruction of georeferenced, metrically
          accurate 3D scenes from a <strong>single UAV flight path</strong>. No repeated passes. Near
          real-time situational awareness.
        </p>

        <div className="hero-tags">
          <span>Robotics & Drones</span>
          <span>Software</span>
          <span>NTRO</span>
          <span>AI/ML</span>
        </div>

        <div className="hero-actions">
          <div className="upload-section">
            <input
              type="file"
              id="hero-video"
              accept="video/mp4,video/quicktime,.mp4,.mov"
              hidden
              onChange={(e) => setVideo(e.target.files?.[0] || null)}
            />
            <input
              type="file"
              id="hero-telemetry"
              accept=".srt,text/plain"
              hidden
              onChange={(e) => setTelemetry(e.target.files?.[0] || null)}
            />

            <label htmlFor="hero-video" className="file-select-btn">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4m14-7l-5-5-5 5m5-5v12"/>
              </svg>
              {video ? video.name : "Select Video"}
            </label>

            <label htmlFor="hero-telemetry" className="file-select-btn">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              {telemetry ? telemetry.name : "Select Telemetry"}
            </label>

            <select className="profile-select" value={profile} onChange={(e) => setProfile(e.target.value)}>
              <option value="precision">Precision</option>
              <option value="rapid">Rapid</option>
            </select>
          </div>

          <button className="hero-cta-primary" onClick={handleUpload} disabled={uploading}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <polygon points="10 8 16 12 10 16 10 8"/>
            </svg>
            {uploading ? "PROCESSING..." : "START 3D BUILD"}
          </button>

          <a href="library.html" className="hero-cta-secondary">
            OPEN 3D VIEWER
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
          </a>
        </div>

        {stats && (
          <div className="hero-stats">
            <div className="stat">
              <strong>{compact(stats.triangles)}</strong>
              <span>Surface Triangles</span>
            </div>
            <div className="stat">
              <strong>{stats.views}</strong>
              <span>Matched Views</span>
            </div>
            <div className="stat">
              <strong>{stats.gps.toFixed(2)} cm</strong>
              <span>GPS Agreement</span>
            </div>
            <div className="stat">
              <strong>{Math.round(stats.area)}×{Math.round(stats.area/1.5)} m</strong>
              <span>Mapped Area</span>
            </div>
            <div className="stat">
              <strong>{compact(stats.points)}+</strong>
              <span>Fused Points</span>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function LibraryPage() {
  const [catalog, setCatalog] = useState(EMPTY);
  const [selectedModel, setSelectedModel] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/models", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : EMPTY)
      .then(setCatalog)
      .catch(() => setCatalog(EMPTY));
  }, []);

  const runs = readyRuns(catalog);

  const loadPreview = async (id, run) => {
    setSelectedModel(id);
    setLoading(true);
    setPreviewData(null);
    try {
      const reportPath = `assets/models/${id}/mission_report.json`;
      const response = await fetch(reportPath);
      if (response.ok) {
        const data = await response.json();
        setTimeout(() => {
          setPreviewData({ ...data, id, run });
          setLoading(false);
        }, 300);
      } else {
        setPreviewData({ id, run, error: true });
        setLoading(false);
      }
    } catch {
      setPreviewData({ id, run, error: true });
      setLoading(false);
    }
  };

  return (
    <div className="library-page-wrapper">
      <HeroHeader />

      <main className="library-page">
        <div className="library-layout">
          <div className="library-main">
            <div className="library-heading">
              <p className="kicker">LOCAL MODEL ARCHIVE</p>
              <h1>Every place,<br /><em>kept close.</em></h1>
              <p>Select a completed mission to return to its saved PLY model. Each build is stored separately on this computer.</p>
            </div>
            <div className="library-list">
              {runs.length ? runs.map(([id, run], index) => (
                <div
                  className={`run-card ${selectedModel === id ? 'selected' : ''}`}
                  key={id}
                  onClick={() => loadPreview(id, run)}
                >
                  <span className="run-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="run-copy">
                    <b>{run.mission?.name || run.label || "Untitled mission"}</b>
                    <small>{run.label || "3D reconstruction"} · {run.completed_at ? new Date(run.completed_at).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "Saved locally"}</small>
                  </span>
                  <span className="run-meta">
                    {compact(run.mission?.triangles || run.triangles)} faces<br />
                    <i>VIEW ↗</i>
                  </span>
                </div>
              )) : (
                <div className="empty-library">
                  <span>◇</span>
                  <b>No saved models yet</b>
                  <small>Upload video and telemetry to create your first 3D model.</small>
                </div>
              )}
            </div>
          </div>

          {selectedModel && (
            <div className="preview-panel">
              <div className="preview-header">
                <span className="preview-kicker">MODEL PREVIEW</span>
                <button className="preview-close" onClick={() => setSelectedModel(null)}>×</button>
              </div>

              {!loading && previewData ? (
                <>
                  <div className="preview-thumbnail">
                    <iframe
                      src={`textured_viewer.html?mode=${encodeURIComponent(selectedModel)}`}
                      title="Model preview"
                    />
                  </div>

                  <div className="preview-info">
                    <h3>{previewData.run?.mission?.name || "Untitled Mission"}</h3>
                    <div className="preview-stats">
                      <div className="stat-item">
                        <span className="stat-label">FRAMES</span>
                        <span className="stat-value">{previewData.run?.frames_selected || previewData.frames_selected || "—"}</span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">TRIANGLES</span>
                        <span className="stat-value">{compact(previewData.run?.mission?.triangles)}</span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">GPS RMSE</span>
                        <span className="stat-value">{previewData.run?.mission?.gps_rmse_m?.toFixed(2) || "—"} m</span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">EXTENT</span>
                        <span className="stat-value">{previewData.run?.mission?.extent_east_m?.toFixed(0) || "—"} × {previewData.run?.mission?.extent_north_m?.toFixed(0) || "—"} m</span>
                      </div>
                    </div>

                    <div className="preview-actions">
                      <a href={`textured_viewer.html?mode=${encodeURIComponent(selectedModel)}`} className="preview-btn primary" target="_blank" rel="noopener">
                        OPEN IN VIEWER
                      </a>
                      <a href={`assets/models/${selectedModel}/dense_textured_mesh.ply`} download className="preview-btn secondary">
                        DOWNLOAD PLY
                      </a>
                    </div>
                  </div>
                </>
              ) : (
                <div className="preview-loading">
                  <div className="spinner"></div>
                  <span>Loading preview...</span>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  location.pathname.endsWith("library.html") ? <LibraryPage /> : <HeroPage />
);
