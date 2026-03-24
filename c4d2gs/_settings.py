"""
C4D2GS — Settings container, defaults, and persistence helpers.

The Settings class is the single source of truth for all plugin parameters.
_save_settings / _load_settings persist the values between Cinema 4D sessions
using the C4D world plugin data store.
"""

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


# ---------------------------------------------------------------------------
# Default settings (used to initialise the dialog on first open)
# ---------------------------------------------------------------------------

_DEFAULTS = dict(
    camera_count=120,
    sphere_radius=300.0,
    center_x=0.0,
    center_y=0.0,
    center_z=0.0,
    center_mode=0,             # 0=geometry center, 1=axis/pivot center
    sampling_mode=0,           # 0=spiral, 1=icosphere, 2=fibonacci
    spiral_turns=6.0,
    spiral_pole_margin=0.06,
    output_path=os.path.join(os.path.expanduser("~"), "Documents",
                             "gs_capture"),
    output_format=getattr(c4d, "FILTER_PNG", 1023671),  # c4d.FILTER_PNG; overridden at runtime in Settings.__init__
    res_x=1920,
    res_y=1080,
    fps=30,
    create_anim_cam=True,
    replace_rig=True,
    auto_update_rig=False,
    export_json=True,
    json_path=os.path.join(os.path.expanduser("~"), "Documents",
                           "gs_capture", "camera_poses.json"),
    export_colmap=True,
    auto_intrinsics=True,
    fx=1500.0,
    fy=1500.0,
    cx=960.0,
    cy=540.0,
    sparse_count=30000,
    sparse_radius_factor=0.35,
    camera_type=0,             # 0=Standard C4D camera, 1=Redshift RSCamera
)


class Settings:
    """Plain-object container for all plugin settings.

    Keeps the plugin free of module-level mutable globals; each dialog
    instance owns its own Settings object.
    """

    def __init__(self):
        for k, v in _DEFAULTS.items():
            setattr(self, k, v)
        # resolve runtime default for output_format
        self.output_format = getattr(c4d, "FILTER_PNG", 1023671)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        # C4D appends frame numbers directly to this stem, yielding images/gs_0000.png.
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
