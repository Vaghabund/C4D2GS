"""
C4D2GS — Synthetic COLMAP data export.

Writes cameras.txt, images.txt, and points3D.txt for use with COLMAP-based
Gaussian Splatting pipelines.
"""

import os

from _constants import MAX_TRACK_OBS_PER_POINT
from _math_utils import (
    look_at_matrix,
    c2w_to_colmap_extrinsics,
    rotation_matrix_to_quaternion,
    project_world_to_image,
    _clean_small,
    _cap_observations,
)
from _geometry_utils import (
    generate_sparse_points_from_surface,
    generate_sparse_points_in_core_volume,
)
from _camera_utils import get_colmap_intrinsics
from _file_utils import _normalize_path, _frame_image_path


# ---------------------------------------------------------------------------
# cameras.txt writer
# ---------------------------------------------------------------------------

def _write_cameras_txt(path, intrinsics, res_x, res_y):
    model = str(intrinsics["model"]).strip().upper()
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Camera list with one line of data per camera:\n")
        f.write("#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        f.write("# Number of cameras: 1\n")
        if model == "SIMPLE_PINHOLE":
            f.write("1 SIMPLE_PINHOLE {} {} {} {} {}\n".format(
                res_x, res_y, intrinsics["fx"], intrinsics["cx"], intrinsics["cy"]))
        else:
            f.write("1 PINHOLE {} {} {} {} {} {}\n".format(
                res_x, res_y,
                intrinsics["fx"], intrinsics["fy"],
                intrinsics["cx"], intrinsics["cy"]))


# ---------------------------------------------------------------------------
# Main COLMAP export
# ---------------------------------------------------------------------------

def export_colmap(settings, world_points, target_pos, output_dir,
                  render_cam=None, doc=None, target_obj=None,
                  camera_matrices=None):
    """Write synthetic COLMAP data files for COLMAP pipelines."""
    if not world_points:
        return None

    output_dir = _normalize_path(output_dir)
    if not output_dir:
        raise ValueError("Synthetic COLMAP data output path is empty.")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    images_dir = os.path.join(output_dir, "images")
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)

    cameras_txt = os.path.join(output_dir, "cameras.txt")
    images_txt = os.path.join(output_dir, "images.txt")
    points3d_txt = os.path.join(output_dir, "points3D.txt")

    intrinsics = get_colmap_intrinsics(settings, render_cam)
    _write_cameras_txt(cameras_txt, intrinsics, settings.res_x, settings.res_y)

    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    width, height = float(settings.res_x), float(settings.res_y)

    if doc is None or target_obj is None:
        raise ValueError("A target object is required for synthetic COLMAP data export.")

    sparse_points_with_normals = generate_sparse_points_from_surface(doc, target_obj, settings.sparse_count)
    if not sparse_points_with_normals:
        raise ValueError(
            "Could not sample sparse points from the object surface. "
            "Ensure the object has polygonal geometry."
        )

    def _build_image_entries(use_camera_matrices):
        entries = []
        for i, world_pos in enumerate(world_points):
            if use_camera_matrices and camera_matrices and i < len(camera_matrices):
                mg = camera_matrices[i]
            else:
                mg = look_at_matrix(world_pos, target_pos)
            q, t, r_w2c = c2w_to_colmap_extrinsics(mg)
            image_name = os.path.basename(_frame_image_path(settings, i))
            entries.append({
                "image_id": i + 1,
                "name": image_name,
                "q": q, "t": t, "r_w2c": r_w2c, "mg": mg, "obs": [],
            })
        return entries

    # Prefer evaluated render-camera matrices, but allow fallback below.
    image_entries = _build_image_entries(use_camera_matrices=True)
    image_entries = sorted(image_entries, key=lambda e: e["name"])
    for idx, entry in enumerate(image_entries, start=1):
        entry["image_id"] = idx

    max_obs = max(2, int(MAX_TRACK_OBS_PER_POINT))
    def _build_tracks(require_front_facing):
        tracks = {}
        for entry in image_entries:
            entry["obs"] = []
        for pid, (p3d, nrm) in enumerate(sparse_points_with_normals, start=1):
            tracks[pid] = []
            candidates = []
            for entry in image_entries:
                projected = project_world_to_image(
                    entry["mg"], p3d, nrm, fx, fy, cx, cy,
                    require_front_facing=require_front_facing,
                )
                if projected is None:
                    continue
                u, v = projected
                if 0.0 <= u < width and 0.0 <= v < height:
                    candidates.append((entry, u, v))

            for entry, u, v in _cap_observations(candidates, max_obs):
                p2d_idx = len(entry["obs"])
                entry["obs"].append((u, v, pid))
                tracks[pid].append((entry["image_id"], p2d_idx))
        return tracks

    # Build 2-D observations with capped track size per 3D point.
    tracks_by_pid = _build_tracks(require_front_facing=True)

    # points3D.txt — keep points observed in >= 1 camera.
    valid_points = [
        (pid, p3d, tracks_by_pid[pid])
        for pid, (p3d, _nrm) in enumerate(sparse_points_with_normals, start=1)
        if len(tracks_by_pid.get(pid, [])) >= 1
    ]

    # Some C4D assets have flipped or inconsistent normals.
    # If strict facing rejects everything, retry without that culling.
    fallback_without_facing = False
    fallback_analytic_poses = False
    fallback_core_volume_points = False
    if not valid_points:
        tracks_by_pid = _build_tracks(require_front_facing=False)
        valid_points = [
            (pid, p3d, tracks_by_pid[pid])
            for pid, (p3d, _nrm) in enumerate(sparse_points_with_normals, start=1)
            if len(tracks_by_pid.get(pid, [])) >= 1
        ]
        fallback_without_facing = True

    # If still nothing, evaluated matrices are likely invalid for this C4D
    # runtime path; retry with deterministic analytic look-at poses.
    if not valid_points and camera_matrices:
        image_entries = _build_image_entries(use_camera_matrices=False)
        image_entries = sorted(image_entries, key=lambda e: e["name"])
        for idx, entry in enumerate(image_entries, start=1):
            entry["image_id"] = idx
        tracks_by_pid = _build_tracks(require_front_facing=False)
        valid_points = [
            (pid, p3d, tracks_by_pid[pid])
            for pid, (p3d, _nrm) in enumerate(sparse_points_with_normals, start=1)
            if len(tracks_by_pid.get(pid, [])) >= 1
        ]
        fallback_analytic_poses = True

    # Final fallback: sample sparse points inside object core volume.
    if not valid_points:
        core_points = generate_sparse_points_in_core_volume(
            target_obj,
            target_pos,
            settings.sparse_count,
            getattr(settings, "sparse_radius_factor", 0.35),
        )
        if core_points:
            sparse_points_with_normals = core_points
            tracks_by_pid = _build_tracks(require_front_facing=False)
            valid_points = [
                (pid, p3d, tracks_by_pid[pid])
                for pid, (p3d, _nrm) in enumerate(sparse_points_with_normals, start=1)
                if len(tracks_by_pid.get(pid, [])) >= 1
            ]
            fallback_core_volume_points = True

    # images.txt
    with open(images_txt, "w", encoding="utf-8") as f:
        f.write("# Image list with two lines of data per image:\n")
        f.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        f.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        f.write("# Number of images: {}\n".format(len(world_points)))
        for entry in image_entries:
            qw, qx, qy, qz = rotation_matrix_to_quaternion(entry["r_w2c"])
            tx, ty, tz = entry["t"]

            f.write("{} {} {} {} {} {} {} {} 1 {}\n".format(
                entry["image_id"],
                _clean_small(qw), _clean_small(qx), _clean_small(qy), _clean_small(qz),
                _clean_small(tx), _clean_small(ty), _clean_small(tz),
                entry["name"],
            ))
            if entry["obs"]:
                f.write(" ".join("{} {} {}".format(o[0], o[1], o[2]) for o in entry["obs"]) + "\n")
            else:
                f.write("\n")

    if not valid_points:
        obs_counts = [len(v) for v in tracks_by_pid.values()]
        debug = [
            "COLMAP export debug",
            "sampled_points={}".format(len(sparse_points_with_normals)),
            "total_images={}".format(len(world_points)),
            "points_ge_1_obs={}".format(sum(1 for n in obs_counts if n >= 1)),
            "points_ge_2_obs={}".format(sum(1 for n in obs_counts if n >= 2)),
            "resolution={}x{}".format(int(width), int(height)),
            "fx={} fy={} cx={} cy={}".format(fx, fy, cx, cy),
            "fallback_without_facing={}".format(fallback_without_facing),
            "fallback_analytic_poses={}".format(fallback_analytic_poses),
            "fallback_core_volume_points={}".format(fallback_core_volume_points),
        ]
        report = os.path.join(output_dir, "colmap_debug.txt")
        with open(report, "w", encoding="utf-8") as f:
            f.write("\n".join(debug) + "\n")
        raise ValueError(
            "No sparse point had >= 1 observation after visibility checks. "
            "Try increasing the camera count, the sphere radius, or the sparse point count. "
            "Debug report: {}".format(report)
        )

    with open(points3d_txt, "w", encoding="utf-8") as f:
        f.write("# 3D point list with one line of data per point:\n")
        f.write("#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]\n")
        f.write("# Number of points: {}\n".format(len(valid_points)))
        for pid, p3d, track in valid_points:
            # Convert world-space point to COLMAP via importer-inverse: flip Y only.
            colmap_x = p3d.x
            colmap_y = -p3d.y
            colmap_z = p3d.z
            track_flat = " ".join("{} {}".format(img_id, p2d) for img_id, p2d in track)
            f.write("{} {} {} {} 255 255 255 1.0 {}\n".format(
                pid, colmap_x, colmap_y, colmap_z, track_flat))

    return {
        "dir": output_dir,
        "cameras_txt": cameras_txt,
        "images_txt": images_txt,
        "points3d_txt": points3d_txt,
        "images_dir": images_dir,
        "points_count": len(valid_points),
        "intrinsics_source": intrinsics.get("source", "manual"),
        "model": intrinsics.get("model", "PINHOLE"),
    }
