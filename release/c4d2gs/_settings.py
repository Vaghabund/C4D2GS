

import c4d
import json
import os

from _constants import PLUGIN_ID, PERSIST_KEY_JSON
from _file_utils import _normalize_path


def show_error_dialog(code, summary, details=None):
    lines = ["[{}] {}".format(code, summary)]
    if details:
        lines.extend(["", str(details)])
    c4d.gui.MessageDialog("\n".join(lines))






_DEFAULTS = dict(
    camera_count=120,
    sphere_radius=300.0,
    sampling_mode=0,
    spiral_turns=6.0,
    spiral_pole_margin=0.06,

    anchor_mode=0,
    manual_anchor_enabled=False,
    anchor_null_group=None,
    manual_y_height_enabled=False,
    manual_y_height=0.0,
    cluster_cam_count=1,
    cluster_radius=10.0,
    auto_y_height=0.0,

    overwrite_export=False,

    last_tab=0,
    output_path=os.path.join(os.path.expanduser("~"), "Documents",
                             "gs_capture"),
    output_format=getattr(c4d, "FILTER_PNG", 1023671),
    res_x=1920,
    res_y=1080,
    fps=30,
    straight_alpha=False,
    create_anim_cam=True,
    replace_rig=True,
    auto_update_rig=False,
    export_json=True,
    export_colmap=True,
    fx=1500.0,
    fy=1500.0,
    cx=960.0,
    cy=540.0,
    sparse_count=30000,
    sparse_radius_factor=0.35,
    camera_type=0,

    render_engine=0,
    render_use_global=True,
    render_samples=8,
)


class Settings:
    

    def __init__(self):
        for k, v in _DEFAULTS.items():
            setattr(self, k, v)

        self.output_format = getattr(c4d, "FILTER_PNG", 1023671)





    def sampling_mode_name(self):
        return {0: "spiral", 1: "icosphere", 2: "fibonacci"}.get(
            self.sampling_mode, "spiral"
        )

    def output_folder(self):
        path = _normalize_path(self.output_path)
        if path:
            return path
        return os.path.join(os.path.expanduser("~"), "Documents", "gs_capture")

    def render_output_pattern(self):

        return os.path.join(self.images_output_dir(), "gs_")

    def images_output_dir(self):
        return os.path.join(self.output_folder(), "images")

    def pose_json_path(self):
        return os.path.join(self.output_folder(), "camera_poses.json")

    def colmap_output_dir(self):
        return self.output_folder()


def _save_settings(settings):
    data = {}
    for key in _DEFAULTS.keys():
        value = getattr(settings, key, None)
        if isinstance(value, (bool, int, float, str)) or value is None:
            data[key] = value
    bc = c4d.BaseContainer()
    bc.SetString(PERSIST_KEY_JSON, json.dumps(data))
    c4d.plugins.SetWorldPluginData(PLUGIN_ID, bc, True)


def _load_settings(settings):
    bc = c4d.plugins.GetWorldPluginData(PLUGIN_ID)
    if bc is None:
        return
    raw = bc.GetString(PERSIST_KEY_JSON)
    if not raw:
        return
    try:
        data = json.loads(raw)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    for key, default in _DEFAULTS.items():
        if key not in data:
            continue
        value = data.get(key)
        try:
            if isinstance(default, bool):
                setattr(settings, key, bool(value))
            elif isinstance(default, int):
                setattr(settings, key, int(value))
            elif isinstance(default, float):
                setattr(settings, key, float(value))
            elif isinstance(default, str):
                setattr(settings, key, str(value))
        except Exception:
            pass
