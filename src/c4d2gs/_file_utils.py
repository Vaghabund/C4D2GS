"""
C4D2GS — File path helpers.

All functions that translate between settings/frame-indices and file-system
paths live here.  No other c4d2gs sub-module is imported so this can be
loaded first without circular-import risk.
"""

import os
import c4d


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


def generate_output_folder_name(base_path, target_object_name, overwrite=False):
    """
    Generate a folder name for Object mode exports.

    Args:
        base_path (str): The root output path.
        target_object_name (str): The name of the target object.
        overwrite (bool): Whether to overwrite existing folders.

    Returns:
        str: The full path to the output folder.
    """
    folder_name = f"Object_{target_object_name}_COLMAP"
    output_path = os.path.join(base_path, folder_name)

    if overwrite:
        return output_path

    # Check for existing folders and append a numeric suffix if needed
    suffix = 1
    final_path = output_path
    while os.path.exists(final_path):
        final_path = f"{output_path}_{suffix:03d}"
        suffix += 1

    return final_path
