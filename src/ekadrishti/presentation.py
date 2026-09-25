"""Create presentation-ready 3D and geospatial artifacts."""

from __future__ import annotations

import json
import math
from pathlib import Path
import time

import laspy
import numpy as np
import open3d as o3d
from pyproj import CRS
import rasterio
from rasterio.transform import from_origin
from scipy import ndimage
from scipy.spatial import cKDTree
import trimesh


def _write_las(points: np.ndarray, colors: np.ndarray, path: Path, *, epsg: int, origin: tuple[float, float, float]) -> None:
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.add_crs(CRS.from_epsg(epsg))
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.array(origin)
    cloud = laspy.LasData(header)
    cloud.x = points[:, 0] + origin[0]
    cloud.y = points[:, 1] + origin[1]
    cloud.z = points[:, 2] + origin[2]
    rgb = np.clip(colors * 65535, 0, 65535).astype(np.uint16)
    cloud.red, cloud.green, cloud.blue = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    cloud.write(path)


def _write_dsm(points: np.ndarray, path: Path, *, epsg: int, origin: tuple[float, float, float], resolution_m: float = 2.0) -> dict[str, float | int]:
    absolute_x = points[:, 0] + origin[0]
    absolute_y = points[:, 1] + origin[1]
    absolute_z = points[:, 2] + origin[2]
    min_x, max_x = float(absolute_x.min()), float(absolute_x.max())
    min_y, max_y = float(absolute_y.min()), float(absolute_y.max())
    width = max(1, int(math.ceil((max_x - min_x) / resolution_m)) + 1)
    height = max(1, int(math.ceil((max_y - min_y) / resolution_m)) + 1)
    raster = np.full((height, width), np.nan, dtype=np.float32)
    columns = np.clip(((absolute_x - min_x) / resolution_m).astype(int), 0, width - 1)
    rows = np.clip(((max_y - absolute_y) / resolution_m).astype(int), 0, height - 1)
    for row, column, elevation in zip(rows, columns, absolute_z, strict=True):
        if np.isnan(raster[row, column]) or elevation > raster[row, column]:
            raster[row, column] = elevation
    missing = np.isnan(raster)
    if np.any(~missing):
        distance, indices = ndimage.distance_transform_edt(missing, return_indices=True)
        near_holes = missing & (distance <= 4)
        raster[near_holes] = raster[tuple(index[near_holes] for index in indices)]
    nodata = -9999.0
    raster[np.isnan(raster)] = nodata
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=f"EPSG:{epsg}",
        transform=from_origin(min_x, max_y, resolution_m, resolution_m),
        nodata=nodata,
        compress="deflate",
        tiled=True,
    ) as target:
        target.write(raster, 1)
        target.set_band_description(1, "Digital surface elevation (m)")
    valid = raster != nodata
    return {"resolution_m": resolution_m, "width": width, "height": height, "coverage_percent": round(float(valid.mean() * 100), 2)}


def _color_mesh(mesh: o3d.geometry.TriangleMesh, points: np.ndarray, colors: np.ndarray) -> None:
    nearest = cKDTree(points).query(np.asarray(mesh.vertices), workers=-1)[1]
    mesh.vertex_colors = o3d.utility.Vector3dVector(colors[nearest])


def _confidence_colors(points: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    distances = cKDTree(points).query(points, k=8, workers=-1)[0][:, -1]
    low, high = np.quantile(distances, [0.1, 0.9])
    confidence = 1.0 - np.clip((distances - low) / max(high - low, 1e-6), 0, 1)
    colors = np.column_stack((1.0 - confidence, confidence, 0.18 + confidence * 0.35))
    return colors, {
        "median_neighbor_radius_m": round(float(np.median(distances)), 3),
        "high_confidence_percent": round(float(np.mean(confidence >= 0.65) * 100), 2),
    }


def generate_presentation_artifacts(
    aligned_ply: Path,
    output_directory: Path,
    *,
    utm_epsg: int,
    utm_origin: tuple[float, float, float],
    target_triangles: int = 220_000,
) -> dict[str, object]:
    """Clean, mesh and export an aligned photogrammetry point cloud."""
    started = time.perf_counter()
    output_directory.mkdir(parents=True, exist_ok=True)
    cloud = o3d.io.read_point_cloud(str(aligned_ply))
    if cloud.is_empty():
        raise RuntimeError(f"Open3D could not read any points from {aligned_ply}")
    raw_points = np.asarray(cloud.points).copy()
    cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=24, std_ratio=2.2)
    points = np.asarray(cloud.points)
    colors = np.asarray(cloud.colors)
    if len(colors) != len(points):
        colors = np.full_like(points, [0.18, 0.62, 0.58])
        cloud.colors = o3d.utility.Vector3dVector(colors)
    nearest_distances = np.asarray(cloud.compute_nearest_neighbor_distance())
    spacing = max(float(np.median(nearest_distances)), 0.05)
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=spacing * 8, max_nn=60))
    cloud.orient_normals_to_align_with_direction(np.array([0.0, 0.0, 1.0]))
    o3d.io.write_point_cloud(str(output_directory / "georeferenced_point_cloud.ply"), cloud, write_ascii=False)

    confidence_colors, confidence_report = _confidence_colors(points)
    confidence_cloud = o3d.geometry.PointCloud(cloud)
    confidence_cloud.colors = o3d.utility.Vector3dVector(confidence_colors)
    o3d.io.write_point_cloud(str(output_directory / "confidence_point_cloud.ply"), confidence_cloud, write_ascii=False)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(cloud, depth=9, scale=1.04, linear_fit=True, n_threads=-1)
    density_values = np.asarray(densities)
    if len(density_values):
        mesh.remove_vertices_by_mask(density_values < np.quantile(density_values, 0.035))
    bounds = cloud.get_axis_aligned_bounding_box()
    padding = max(spacing * 5, 1.0)
    mesh = mesh.crop(o3d.geometry.AxisAlignedBoundingBox(bounds.min_bound - padding, bounds.max_bound + padding))
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()
    if len(mesh.triangles) > target_triangles:
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_triangles)
    mesh.compute_vertex_normals()
    _color_mesh(mesh, points, colors)

    mesh_ply = output_directory / "presentation_mesh.ply"
    mesh_obj = output_directory / "presentation_mesh.obj"
    mesh_glb = output_directory / "presentation_mesh.glb"
    o3d.io.write_triangle_mesh(str(mesh_ply), mesh, write_ascii=False, write_vertex_colors=True)
    o3d.io.write_triangle_mesh(str(mesh_obj), mesh, write_ascii=True, write_vertex_colors=True)
    tri_mesh = trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices),
        faces=np.asarray(mesh.triangles),
        vertex_normals=np.asarray(mesh.vertex_normals),
        vertex_colors=np.clip(np.asarray(mesh.vertex_colors) * 255, 0, 255).astype(np.uint8),
        process=False,
    )
    mesh_glb.write_bytes(tri_mesh.export(file_type="glb"))

    las_path = output_directory / "georeferenced_point_cloud.las"
    _write_las(points, colors, las_path, epsg=utm_epsg, origin=utm_origin)
    dsm_report = _write_dsm(points, output_directory / "surface_model.tif", epsg=utm_epsg, origin=utm_origin)
    extents = np.ptp(points, axis=0)
    report: dict[str, object] = {
        "status": "presentation_ready",
        "source": "single-pass video photogrammetry",
        "geometry_class": "confidence-filtered sparse-derived surface",
        "points_raw": int(len(raw_points)),
        "points_retained": int(len(points)),
        "mesh_vertices": int(len(mesh.vertices)),
        "mesh_triangles": int(len(mesh.triangles)),
        "extent_east_m": round(float(extents[0]), 2),
        "extent_north_m": round(float(extents[1]), 2),
        "extent_vertical_m": round(float(extents[2]), 2),
        "median_point_spacing_m": round(spacing, 3),
        "processing_seconds": round(time.perf_counter() - started, 2),
        "crs": f"EPSG:{utm_epsg}",
        "artifacts": {
            "point_cloud_ply": "georeferenced_point_cloud.ply",
            "confidence_ply": "confidence_point_cloud.ply",
            "mesh_ply": mesh_ply.name,
            "mesh_obj": mesh_obj.name,
            "mesh_glb": mesh_glb.name,
            "point_cloud_las": las_path.name,
            "surface_geotiff": "surface_model.tif",
        },
        "confidence": confidence_report,
        "dsm": dsm_report,
        "measurement_policy": "Measurements apply to observed photogrammetric geometry; inferred surfaces must be labelled separately.",
    }
    (output_directory / "presentation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
