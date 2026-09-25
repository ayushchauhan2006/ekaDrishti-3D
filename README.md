# EkaDrishti 3D

**One flight. Complete spatial insight.**

EkaDrishti 3D reconstructs a geo-referenced 3D scene from an original DJI drone MP4 and its matching readable DJI SRT telemetry file. Both files are required so the system can place the reconstruction on a map and keep inspection measurements traceable.

## Required mission package

| Required input | What EkaDrishti produces | Why it is required |
|---|---|---|
| Original DJI MP4 + matching readable DJI SRT | Geo-referenced sparse and dense reconstruction, map placement, and an inspection viewer | Visual overlap produces geometry; SRT provides time and geographic context |

## Current mission result

| Result | Verified value |
|---|---:|
| Registered images | 242 / 242 |
| Feature observations | 1,752,582 |
| Mean reprojection error | 0.806 px |
| Filtered 3D points | 125,207 |
| Presentation mesh | 220,000 triangles |
| Metric scene extent | 1,253.6 × 1,939.78 × 380.22 m |
| GPS camera-path consistency | 1.28 m median horizontal; 1.79 m 3D RMSE |
| Coordinate system | EPSG:32611 (UTM zone 11N) |
| DSM | 2 m resolution, 628 × 971 cells |

The GPS figures measure agreement with the flight telemetry. They are not an independent ground-control check. Survey-grade or sub-metre absolute accuracy must be validated using GCPs/checkpoints.

## Open the presentation

```bash
cd /home/ayush/repos/ekaDrishti-3D
.venv/bin/python dashboard/server.py
```

Open <http://127.0.0.1:4173>. Choose **Open metric 3D viewer** to explore the colored surface, source points, and confidence layer.

The presentation page works locally and includes downloads for:

- `presentation_mesh.glb` — portable 3D model
- `georeferenced_point_cloud.las` — UTM point cloud
- `surface_model.tif` — 2 m GeoTIFF DSM
- `presentation_report.json` — reproducible quality and alignment report

## Rebuild the current presentation

Install the native prerequisites first: Python 3.12, FFmpeg, and COLMAP. Then create the project environment:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```

To regenerate the final products from the existing sparse model:

```bash
.venv/bin/python -m src.ekadrishti.finalize_model \
  --sparse-model outputs/colmap_500ms/sparse/1 \
  --video data/raw/DJI_20230912190109_0001_W.MP4 \
  --telemetry data/raw/DJI_20230912190109_0001_W.SRT \
  --output-directory outputs/presentation \
  --publish-directory dashboard/dist/assets
```

To run a new mission from MP4 and SRT through the complete pipeline:

```bash
.venv/bin/python -m src.ekadrishti.full_pipeline \
  --video /path/to/mission.MP4 \
  --telemetry /path/to/mission.SRT \
  --workspace /path/to/mission-workspace \
  --project-root /home/ayush/repos/ekaDrishti-3D \
  --interval-seconds 0.5
```

The dashboard requires the original DJI MP4 and a matching readable SRT. It rejects incomplete or unreadable telemetry rather than publishing an uncalibrated model.

## Pipeline

1. Validate the MP4 and parse DJI telemetry.
2. Select sharp frames at the configured interval.
3. Extract and match visual features with COLMAP.
4. Register camera poses and sparse 3D points.
5. Estimate the video/telemetry offset.
6. Fit and verify a metric UTM similarity transform.
7. Remove statistical outliers and calculate confidence.
8. Reconstruct and simplify the presentation surface.
9. Export PLY, OBJ, GLB, LAS, GeoTIFF, and JSON QA products.
10. Publish the latest mission to the interactive dashboard.

## Important implementation note

The Ubuntu COLMAP 3.9.1 package has known regressions in its model alignment/transform helpers. EkaDrishti therefore computes the Sim(3) fit itself, explicitly transforms every camera pose and 3D point, reconverts the COLMAP model, and verifies all matched camera centers against projected telemetry. This avoids a false-success alignment state.

## Validation

```bash
.venv/bin/pytest -q
```

The tests cover recovery of a known metric similarity transform and consistent transformation of camera centers and 3D points.
