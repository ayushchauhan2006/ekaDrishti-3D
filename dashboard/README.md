# EkaDrishti 3D dashboard

This is the local visual console for the current reconstruction. It shows the
validated mission facts, the flight path, the sparse-model result, and the
ordered work still required before measurements are reliable.

## Open it

From the project folder, run:

```bash
python3 dashboard/server.py
```

Then open `http://localhost:4173` in a browser.

The dashboard runs locally only. Select a drone MP4 and its matching DJI SRT, then choose **Process mission**. The job runner creates a separate mission folder, validates the telemetry, selects sharp frames, and runs COLMAP to create a real sparse 3D point cloud. It never sends the drone files online.

The next reconstruction stages after this sparse model are geographic calibration, dense points, a mesh, texture, and AI cleanup.
