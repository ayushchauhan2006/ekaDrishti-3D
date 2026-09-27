"""Local EkaDrishti dashboard server and one-mission-at-a-time job runner."""

from __future__ import annotations

import cgi
import json
import mimetypes
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "dashboard" / "dist"
MISSIONS_ROOT = PROJECT_ROOT / "data" / "missions"
MAX_UPLOAD_BYTES = 2_500 * 1024 * 1024


class JobState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, object] = {"status": "idle", "message": "Choose a new MP4 and SRT mission package to begin."}

    def update(self, **changes: object) -> None:
        with self._lock:
            self._data.update(changes)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return dict(self._data)


JOB = JobState()


def _safe_filename(filename: str, suffix: str) -> str:
    clean = "".join(char for char in Path(filename).name if char.isalnum() or char in "._-")
    return clean if clean.lower().endswith(suffix) else f"mission{suffix}"


def _run_reconstruction(job_id: str, video: Path, telemetry: Path, workspace: Path) -> None:
    python_exe = sys.executable
    if os.name == 'nt' and (PROJECT_ROOT / ".venv/Scripts/python.exe").is_file():
        python_exe = str(PROJECT_ROOT / ".venv/Scripts/python.exe")
    elif (PROJECT_ROOT / ".venv/bin/python").is_file():
        python_exe = str(PROJECT_ROOT / ".venv/bin/python")

    command = [
        python_exe, "-u", "-m", "src.ekadrishti.full_pipeline",
        "--video", str(video), "--telemetry", str(telemetry), "--workspace", str(workspace),
        "--project-root", str(PROJECT_ROOT), "--interval-seconds", "0.5",
    ]
    log: list[str] = []
    try:
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            log.append(line)
            log = log[-30:]
            if line.startswith("STEP:"):
                JOB.update(status="running", stage=line.removeprefix("STEP:").strip(), log=log)
            else:
                JOB.update(log=log)
        if process.wait() != 0:
            raise RuntimeError(log[-1] if log else "The reconstruction process stopped unexpectedly.")
        report_path = workspace / "outputs" / "reconstruction_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        JOB.update(status="complete", stage="Presentation-ready 3D reconstruction complete", result=report, log=log)
    except Exception as error:  # Keep the server alive so the dashboard can show the failure.
        JOB.update(status="failed", stage="Processing stopped", message=str(error), log=log)


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "EkaDrishtiDashboard/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dashboard] {format % args}")

    def _json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"error": message}, status)

    def do_GET(self) -> None:
        request_path = urlparse(self.path).path
        if request_path == "/api/status":
            self._json(JOB.snapshot())
            return
        relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
        candidate = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT not in candidate.parents and candidate != STATIC_ROOT:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/process":
            self._error("Unknown endpoint", HTTPStatus.NOT_FOUND)
            return
        if JOB.snapshot().get("status") == "running":
            self._error("Another mission is already being processed. Please wait for it to finish.", HTTPStatus.CONFLICT)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_UPLOAD_BYTES:
            self._error("Upload must contain both files and be smaller than 2.5 GB.")
            return
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._error("Use a multipart form containing video and telemetry.")
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(length)},
        )
        video_field = form["video"] if "video" in form else None
        telemetry_field = form["telemetry"] if "telemetry" in form else None
        if not getattr(video_field, "filename", None) or not getattr(telemetry_field, "filename", None):
            self._error("Select both a drone MP4 and its matching DJI SRT file.")
            return
        if not video_field.filename.lower().endswith(".mp4") or not telemetry_field.filename.lower().endswith(".srt"):
            self._error("The video must be an .mp4 and telemetry must be an .srt file.")
            return
        job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        raw_directory = MISSIONS_ROOT / job_id / "raw"
        raw_directory.mkdir(parents=True, exist_ok=False)
        video_path = raw_directory / _safe_filename(video_field.filename, ".mp4")
        telemetry_path = raw_directory / _safe_filename(telemetry_field.filename, ".srt")
        with video_path.open("wb") as target:
            shutil.copyfileobj(video_field.file, target)
        with telemetry_path.open("wb") as target:
            shutil.copyfileobj(telemetry_field.file, target)
        workspace = MISSIONS_ROOT / job_id / "work"
        JOB.update(status="running", job_id=job_id, stage="Mission received", message="Starting local reconstruction", result={}, log=[])
        thread = threading.Thread(target=_run_reconstruction, args=(job_id, video_path, telemetry_path, workspace), daemon=True)
        thread.start()
        self._json(JOB.snapshot(), HTTPStatus.ACCEPTED)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 4173), DashboardHandler)
    print("EkaDrishti dashboard is running at http://127.0.0.1:4173")
    print("Press Ctrl+C here to stop it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
