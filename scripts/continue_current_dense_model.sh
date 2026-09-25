#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 PATCH_MATCH_PROCESS_ID" >&2
  exit 2
fi

patch_pid="$1"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
colmap="$project_root/tools/colmap-cuda/build/src/colmap/exe/colmap"
dense="$project_root/outputs/colmap_500ms/dense"
assets="$project_root/dashboard/dist/assets"

echo "Waiting for dense GPU depth calculation (PID $patch_pid)."
while kill -0 "$patch_pid" 2>/dev/null; do
  sleep 20
done

map_count="$(find "$dense/stereo/depth_maps" -type f -name '*photometric.bin' | wc -l)"
if (( map_count < 242 )); then
  echo "Dense depth calculation stopped early: only $map_count of 242 maps were written." >&2
  exit 1
fi

echo "STEP: Fusing $map_count dense depth maps"
"$colmap" stereo_fusion \
  --workspace_path "$dense" --workspace_format COLMAP --input_type photometric \
  --output_path "$dense/fused.ply" --StereoFusion.num_threads 4

echo "STEP: Building triangle mesh"
"$colmap" poisson_mesher \
  --input_path "$dense/fused.ply" --output_path "$dense/meshed-poisson.ply" \
  --PoissonMeshing.depth 11 --PoissonMeshing.color 1 --PoissonMeshing.num_threads 4

echo "STEP: Applying original drone photographs as mesh texture"
mkdir -p "$dense/textured"
"$colmap" mesh_texturer \
  --workspace_path "$dense" --input_path "$dense/meshed-poisson.ply" \
  --output_path "$dense/textured" --MeshTextureMapping.num_threads 4

mkdir -p "$assets"
python3 -m src.ekadrishti.prepare_viewer_cloud \
  --input "$dense/fused.ply" --output "$assets/dense_point_cloud.ply" --max-points 750000
cp "$dense/meshed-poisson.ply" "$assets/dense_mesh.ply"
touch "$dense/.complete"
echo "COMPLETE: Dense point cloud, mesh, and textured model are ready."
