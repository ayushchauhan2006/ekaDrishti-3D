# EkaDrishti 3D

**One flight. Measurable spatial insight.**

EkaDrishti 3D is an AI-assisted, single-pass drone-video pipeline for producing a georeferenced 3D scene. It validates an original DJI video and matching SRT telemetry, selects usable frames, audits dynamic objects, reconstructs sparse and dense geometry, aligns the model to a local metric UTM frame, textures the mesh, and publishes a browser-based inspection and measurement experience.

This implementation is aligned to SIH problem statement 158 / SIH26158: *Single-Pass Drone Video to Accurate 3D Model Generation System*. It deliberately separates internal RTK/GPS consistency from independent ground-truth accuracy.

## Presentation mission: DJI_0289

| Result | Verified value |
|---|---:|
| Source | `data/raw/DJI_0289.MOV` + `data/raw/DJI_0289.srt` |
| Video duration | 81.68 s |
| Registered images | 164 |
| Feature observations | 724,130 |
| Mean reprojection error | 1.056 px |
| Sparse 3D points | 66,740 |
| Dense fused points | 2,332,930 |
| Textured mesh | 1,280,064 vertices / 2,513,538 triangles |
| Textured-model extent | 75.47 × 48.33 × 25.49 m |
| Coordinate frame | EPSG:32651 local UTM frame |
| Internal telemetry agreement | 0.0653 m horizontal RMSE / 0.2307 m 3D RMSE |
| AI dynamic-object audit | 164 frames checked; no qualifying dynamic objects at confidence ≥ 0.50 |
| Independent accuracy | Awaiting survey checkpoints or known reference dimensions |

The telemetry figures measure agreement between reconstructed camera centres and the supplied flight telemetry. They are **not** an independent ground-control result and must not be presented as a certified absolute-accuracy figure.

## Open the presentation

```bash
cd /home/ayush/repos/ekaDrishti-3D
.venv/bin/python dashboard/server.py
```

Open <http://127.0.0.1:4173>. The metric textured viewer supports 360° orbit, pan, zoom, and point-to-point surface measurements in metres. The dashboard also exposes **Rapid preview** and **Precision model** processing modes for a new MP4 + SRT mission.

Published artifacts are in `dashboard/dist/assets/`:

- `dense_textured_mesh.ply` and `dense_texture.png` — metric photo-textured surface
- `dense_point_cloud.ply` — browser-sized metric dense cloud
- `georeferenced_point_cloud.las` — UTM sparse-derived point cloud
- `surface_model.tif` — 2 m GeoTIFF DSM
- `presentation_mesh.glb` — portable presentation model
- `presentation_report.json`, `dense_report.json`, `ai_mask_report.json`, and `accuracy_validation.json` — traceable QA evidence

## Complete pipeline

1. Validate the drone video and parse the matching DJI SRT.
2. Select sharp, overlapping frames using the selected rapid or precision profile.
3. Use YOLOv4-tiny through OpenCV DNN to detect and mask people, vehicles, and animals before reconstruction.
4. Extract and sequentially match visual features with CUDA COLMAP.
5. Register cameras and build sparse geometry.
6. Synchronize video frames to telemetry and fit a metric Sim(3) transform.
7. Explicitly transform cameras and points into an EPSG:32651 local UTM frame and verify the transformed camera path.
8. Build dense depth maps, fuse a dense cloud, create a Poisson mesh, and project source imagery onto it.
9. Export PLY, LAS, GeoTIFF, GLB, confidence, benchmark, and QA reports.
10. Publish the model to the WebGL viewer for inspection and metric measurements.
11. Evaluate independent checkpoints or known dimensions before enabling an absolute-accuracy claim.

## Run a new mission

Install Python 3.12, FFmpeg, a CUDA-capable COLMAP build at `tools/colmap-cuda/build/src/colmap/exe/colmap`, and the Python dependencies:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```

Precision processing:

```bash
.venv/bin/python -m src.ekadrishti.full_pipeline \
  --video /path/to/mission.MP4 \
  --telemetry /path/to/mission.SRT \
  --workspace /path/to/mission-workspace \
  --project-root /home/ayush/repos/ekaDrishti-3D \
  --profile precision \
  --use-gpu
```

Use `--profile rapid` for a faster preview. Both modes retain full metric-alignment and validation gates; they differ in sampling density and dense reconstruction resolution.

## Independent accuracy validation

Two accepted schemas are provided:

- `docs/checkpoints_template.csv` for surveyed XYZ checkpoints
- `docs/reference_dimensions_template.csv` for independently measured distances

Validate either file with:

```bash
.venv/bin/python -m src.ekadrishti.accuracy_validation \
  --input /path/to/completed_checkpoints.csv \
  --output dashboard/dist/assets/accuracy_validation.json
```

Until real values are supplied, the UI displays **Checkpoint data required** and the generated report sets `claim_allowed` to `false`. This is the sole remaining external evidence needed before claiming a specific absolute metric-accuracy threshold.

## Validation

```bash
.venv/bin/pytest -q
node --check dashboard/dist/textured_viewer.js
node --check dashboard/dist/process.js
```

The tests cover metric transform recovery, binary PLY transformation, dynamic-frame handling, accuracy statistics, and processing profiles.

## Known reconstruction boundary

The system reconstructs surfaces visible in the single pass. Poisson filling may close small gaps, but genuinely occluded geometry is not presented as observed truth. Capture sufficient oblique overlap for façades and sides, and use the confidence/validation outputs when measurements matter.
