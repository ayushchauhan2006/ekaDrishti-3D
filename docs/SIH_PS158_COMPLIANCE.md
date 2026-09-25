# SIH PS-158 / SIH26158 compliance record

Problem statement: **Single-Pass Drone Video to Accurate 3D Model Generation System** (NTRO).

Assessment date: 25 September 2026. Reference mission: `DJI_0289.MOV` with matching `DJI_0289.srt`.

## Requirement matrix

| Problem-statement expectation | Implementation evidence | Status |
|---|---|---|
| Single-pass drone-video input | The pipeline accepts one DJI MP4/MOV plus its matching SRT and extracts overlapping frames. | Implemented |
| AI-enabled processing | YOLOv4-tiny COCO/OpenCV DNN audits and masks people, vehicles, and animals before feature extraction and dense reconstruction. | Implemented |
| Georeferenced 3D output | Camera centres and geometry are explicitly transformed with a verified Sim(3) into an EPSG:32651 local UTM frame. | Implemented |
| Dense terrain/structure representation | The current mission contains 2,332,930 fused points and a 2,513,538-triangle textured mesh. | Implemented |
| Roofs, roads, vegetation and obstacles | These visible scene classes are present in the photo-textured model; no semantic-class claim is made. | Implemented visually |
| Visualization, measurement and analysis | The WebGL viewer supports orbit, pan, zoom and two-point 3D surface measurements in metres; LAS, GeoTIFF, PLY and GLB support analysis tools. | Implemented |
| Motion blur/compression handling | Frame selection scores sharpness and discards unsuitable frames before reconstruction. | Implemented |
| Illumination and shadow robustness | Multi-view matching and dense stereo use overlapping observations; no guarantee is made for severely underexposed surfaces. | Implemented within photogrammetric limits |
| Dynamic objects | AI masking is active. The presentation flight audit found no qualifying object at confidence ≥ 0.50, so no pixels were altered. | Implemented and audited |
| GPS noise | Robust video/telemetry synchronization and similarity fitting report residuals and verify transformed camera centres. | Implemented |
| Limited angles and occlusion | Confidence output identifies weakly supported observed areas. Genuinely unobserved geometry is not hallucinated or labelled as measured truth. | Honest boundary; capture dependent |
| Near-real-time processing | Rapid and precision profiles exist and every new full run records stage timings plus processing/video ratio. | Implemented, performance claim not yet certified |
| Metric accuracy without many GCPs | Scale and frame are obtained from telemetry; the reference flight has 0.0653 m internal horizontal RMSE and 0.2307 m internal 3D RMSE across 17 references. | Internally verified |
| Independent absolute-accuracy evidence | Evaluator and CSV templates exist for surveyed checkpoints or known dimensions. No real independent observations have been supplied. | External evidence pending |

## What can be presented now

The project is ready for a live technical demonstration as an **AI-assisted, telemetry-aligned metric 3D reconstruction**. The current model, metric measurement tool, AI audit, processing modes, reports and downloadable geospatial artifacts are operational.

Use this precise accuracy wording:

> The reconstructed camera path agrees with the supplied DJI telemetry at 6.53 cm horizontal RMSE and 23.07 cm 3D RMSE across 17 matched references. Independent surveyed checkpoints are required before claiming absolute ground accuracy.

Do not call the 6.53 cm value “survey accuracy” or “ground-truth accuracy.” It is an internal telemetry-consistency result.

## Final external acceptance tasks

Only evidence that cannot be truthfully generated from the repository remains:

1. Survey at least 5–10 well-distributed checkpoints, or measure several clearly identifiable scene dimensions independently.
2. Fill `checkpoints_template.csv` or `reference_dimensions_template.csv` and run `src.ekadrishti.accuracy_validation`.
3. Record one clean Rapid and one Precision run on the presentation hardware and retain the generated benchmark fields. Use those measured results for any near-real-time statement.
4. Repeat the evaluation on at least one additional flight with oblique façade coverage to demonstrate generalization beyond the reference clip.

Without those field measurements, the software is demo-ready but must not be described as independently certified for a particular absolute-accuracy threshold.
