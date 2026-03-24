"""
C4D2GS — File path helpers.

All functions that translate between settings/frame-indices and file-system
paths live here.  No other c4d2gs sub-module is imported so this can be
loaded first without circular-import risk.
"""

import os
import c4d

from _constants import NUMERIC_CLEAN_EPS


def _normalize_path(path):
    p = os.path.expandvars(os.path.expanduser(str(path).strip()))
    if not p:
        return ""
    p = os.path.normpath(p)
    return p if os.path.isabs(p) else os.path.abspath(p)


def _output_extension(settings):
    ext_map = {}
    for name, ext in [("FILTER_PNG", ".png"), ("FILTER_JPG", ".jpg"),
                      ("FILTER_TIF", ".tif"), ("FILTER_EXR", ".exr")]:
        val = getattr(c4d, name, None)
        if val is not None:
            ext_map[val] = ext
    return ext_map.get(settings.output_format, ".png")


def _frame_image_path(settings, frame_index):
    # Rendered frames are always stored under <output>/images.
    base = os.path.join(settings.images_output_dir(), "gs_{:04d}".format(frame_index))
    ext = _output_extension(settings)
    return base if base.lower().endswith(ext.lower()) else base + ext


def _relative_frame_image_path(settings, frame_index):
    rel = os.path.join("images", os.path.basename(_frame_image_path(settings, frame_index)))
    return "./{}".format(rel.replace("\\", "/"))


def _nerf_file_path(settings, frame_index):
    return os.path.join("images", os.path.basename(_frame_image_path(settings, frame_index))).replace("\\", "/")
