

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

    base = os.path.join(settings.images_output_dir(), "gs_{:04d}".format(frame_index))
    ext = _output_extension(settings)
    return base if base.lower().endswith(ext.lower()) else base + ext


def _relative_frame_image_path(settings, frame_index):
    rel = os.path.join("images", os.path.basename(_frame_image_path(settings, frame_index)))
    return "./{}".format(rel.replace("\\", "/"))


def _nerf_file_path(settings, frame_index):
    return os.path.join("images", os.path.basename(_frame_image_path(settings, frame_index))).replace("\\", "/")


def generate_output_folder_name(base_path, target_object_name, overwrite=False):
    
    folder_name = f"Object_{target_object_name}_COLMAP"
    output_path = os.path.join(base_path, folder_name)

    if overwrite:
        return output_path


    suffix = 1
    final_path = output_path
    while os.path.exists(final_path):
        final_path = f"{output_path}_{suffix:03d}"
        suffix += 1

    return final_path


def generate_space_folder_name(base_path, overwrite=False):
    
    folder_name = "Space_COLMAP"
    output_path = os.path.join(base_path, folder_name)

    if overwrite:
        return output_path


    suffix = 1
    final_path = output_path
    while os.path.exists(final_path):
        final_path = f"{output_path}_{suffix:03d}"
        suffix += 1

    return final_path
