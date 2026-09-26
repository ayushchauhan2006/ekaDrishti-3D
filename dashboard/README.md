# EkaDrishti 3D dashboard

This is the local visual console for the current reconstruction. It shows the
validated mission facts, the flight path, the sparse-model result, and the
ordered work still required before measurements are reliable.

## Open it

Build the React frontend once after installing Node.js:

```bash
npm install --prefix dashboard
npm run build --prefix dashboard
```

From the project folder, run:

```bash
.venv/bin/python dashboard/server.py
```

Then open `http://localhost:4173` in a browser.

The dashboard runs locally only. Select a drone MP4 and its matching DJI SRT,
choose **Rapid preview** or **Precision model**, then start the mission. The
job runner creates a separate mission folder, validates the telemetry, selects
sharp frames, and runs COLMAP to create a real sparse 3D point cloud. It never
sends the drone files online.

For UI development, run `npm run dev --prefix dashboard` while the Python server
is running. Open `http://127.0.0.1:5173`; the Vite dev server proxies API and
viewer requests to the Python server.

The next reconstruction stages after this sparse model are geographic calibration, dense points, a mesh, texture, and AI cleanup.
