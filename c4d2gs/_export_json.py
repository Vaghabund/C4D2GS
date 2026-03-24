"""
C4D2GS — Camera poses JSON export (NeRF / nerfstudio format).
"""

import c4d
import json
import os

from _math_utils import look_at_matrix, nerf_matrix_to_rows, _clean_vec3, _clean_matrix_rows
from _camera_utils import get_colmap_intrinsics
from _file_utils import _nerf_file_path


def export_camera_poses_json(settings, world_points, target_pos, render_cam=None, camera_matrices=None):
    if not world_points:
        return None
    intrinsics = get_colmap_intrinsics(settings, render_cam)
    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    w, h = int(settings.res_x), int(settings.res_y)

    frames = []
    for i, world_pos in enumerate(world_points):
        if camera_matrices and i < len(camera_matrices):
            mg = camera_matrices[i]
        else:
            mg = look_at_matrix(world_pos, target_pos)
        hpb = c4d.utils.MatrixToHPB(mg)
        frames.append({
            "frame": i,
            "camera_name": "GS_Cam_{:04d}".format(i),
            "file_path": _nerf_file_path(settings, i),
            "position": _clean_vec3(world_pos),
            "rotation_hpb_rad": [hpb.x, hpb.y, hpb.z],
            "transform_matrix": _clean_matrix_rows(nerf_matrix_to_rows(mg)),
            "fx": fx, "fy": fy, "cx": cx, "cy": cy,
            "fl_x": fx, "fl_y": fy, "w": w, "h": h, "focal_length": fx,
        })

    payload = {
        "coordinate_system": "Cinema4D_Yup_RightHanded",
        "camera_looks_along": "-Z",
        "camera_model": str(intrinsics["model"]).upper(),
        "fx": fx, "fy": fy, "cx": cx, "cy": cy,
        "width": w, "height": h,
        "focal_length": fx, "fl_x": fx, "fl_y": fy, "w": w, "h": h,
        "frame_count": len(world_points),
        "frames": frames,
    }

    out_path = settings.pose_json_path()
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out_path
