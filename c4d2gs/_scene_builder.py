"""
C4D2GS — Main scene-building pipeline.

run_pipeline      — build camera rig and export JSON + COLMAP data.
create_or_update_rig — rebuild rig only (no export).
run_colmap_only   — export COLMAP data without modifying the scene.
"""

import c4d

from _settings import Settings
from _math_utils import generate_unit_points, _camera_matrices_for_export
from _geometry_utils import (
    object_center_for_mode,
    center_offset_for_mode,
    rig_name_for_target,
    target_name_for_target,
    find_object_by_name,
)
from _camera_utils import (
    _make_camera_object,
    _is_camera_obj,
    _create_target_tag,
    _set_focus_distance_to_target,
    _add_step_key,
    configure_render_settings,
)
from _export_json import export_camera_poses_json
from _export_colmap import export_colmap


def run_pipeline(doc, settings, target_obj, create_output_dirs=True):
    """Build camera rig + export files.  Returns a result dict."""
    doc.StartUndo()
    try:
        target_pos = object_center_for_mode(
            target_obj, getattr(settings, "center_mode", 0)
        ) + center_offset_for_mode(settings)

        rig_name = rig_name_for_target(target_obj)

        # Remove existing rig if requested
        if settings.replace_rig:
            for candidate in [rig_name, "GS_CameraRig"]:
                existing = find_object_by_name(doc.GetFirstObject(), candidate)
                if existing is not None:
                    doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, existing)
                    existing.Remove()

        # Build rig null
        rig = c4d.BaseObject(c4d.Onull)
        rig.SetName(rig_name)
        rig.SetAbsPos(target_pos)
        doc.InsertObject(rig)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, rig)

        target_null = c4d.BaseObject(c4d.Onull)
        target_null.SetName(target_name_for_target(target_obj))
        target_null.InsertUnder(rig)
        target_null.SetAbsPos(target_pos)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, target_null)

        # Generate view-point positions
        unit_pts, mode_used, mode_extra = generate_unit_points(settings)
        world_pts = [target_pos + p * settings.sphere_radius for p in unit_pts]

        # Static reference cameras (one per viewpoint)
        for i, wpos in enumerate(world_pts):
            cam = _make_camera_object(settings.camera_type)
            cam.SetName("GS_Cam_{:04d}".format(i))
            cam.InsertUnder(rig)
            cam.SetAbsPos(wpos)
            _create_target_tag(cam, target_null)
            _set_focus_distance_to_target(cam, target_pos)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, cam)

        # Animated render camera
        render_cam = None
        if settings.create_anim_cam:
            render_cam = _make_camera_object(settings.camera_type)
            render_cam.SetName("GS_RenderCam_Animated")
            render_cam.InsertUnder(rig)
            render_cam.SetAbsPos(world_pts[0])
            _create_target_tag(render_cam, target_null)
            _set_focus_distance_to_target(render_cam, target_pos)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, render_cam)

            desc_x = c4d.DescID(
                c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                c4d.DescLevel(c4d.VECTOR_X, c4d.DTYPE_REAL, 0),
            )
            desc_y = c4d.DescID(
                c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                c4d.DescLevel(c4d.VECTOR_Y, c4d.DTYPE_REAL, 0),
            )
            desc_z = c4d.DescID(
                c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                c4d.DescLevel(c4d.VECTOR_Z, c4d.DTYPE_REAL, 0),
            )
            for frame, wpos in enumerate(world_pts):
                local_pos = wpos - target_pos
                t = c4d.BaseTime(frame, settings.fps)
                _add_step_key(render_cam, desc_x, t, local_pos.x)
                _add_step_key(render_cam, desc_y, t, local_pos.y)
                _add_step_key(render_cam, desc_z, t, local_pos.z)

        configure_render_settings(
            doc,
            settings,
            render_cam,
            len(world_pts),
            create_output_dirs=create_output_dirs,
        )

        camera_matrices = _camera_matrices_for_export(
            doc, render_cam, len(world_pts), settings.fps
        )

        # JSON export
        pose_file = None
        if settings.export_json:
            try:
                pose_file = export_camera_poses_json(
                    settings, world_pts, target_pos, render_cam,
                    camera_matrices=camera_matrices,
                )
            except Exception as e:
                pose_file = "ERROR: {}".format(e)

        # COLMAP export
        colmap_result = None
        if settings.export_colmap:
            colmap_dir = settings.colmap_output_dir()
            colmap_result = export_colmap(
                settings, world_pts, target_pos, colmap_dir,
                render_cam=render_cam, doc=doc, target_obj=target_obj,
                camera_matrices=camera_matrices,
            )

        doc.SetTime(c4d.BaseTime(0, settings.fps))
        c4d.EventAdd()

        return {
            "ok": True,
            "camera_count": len(world_pts),
            "mode": mode_used,
            "mode_extra": mode_extra,
            "target_name": target_obj.GetName(),
            "pose_file": pose_file,
            "colmap": colmap_result,
        }
    finally:
        doc.EndUndo()


def create_or_update_rig(doc, settings, target_obj):
    """Create or rebuild camera rig without exporting JSON/synthetic COLMAP data files."""
    temp = Settings()
    temp.__dict__.update(settings.__dict__)
    temp.export_json = False
    temp.export_colmap = False
    return run_pipeline(doc, temp, target_obj, create_output_dirs=False)


def run_colmap_only(doc, settings, target_obj):
    """Export synthetic COLMAP data files without modifying the scene."""
    target_pos = object_center_for_mode(
        target_obj, getattr(settings, "center_mode", 0)
    ) + center_offset_for_mode(settings)
    unit_pts, mode_used, mode_extra = generate_unit_points(settings)
    world_pts = [target_pos + p * settings.sphere_radius for p in unit_pts]

    # Try to find existing render camera
    render_cam = None
    rig = find_object_by_name(doc.GetFirstObject(), rig_name_for_target(target_obj))
    if rig is None:
        rig = find_object_by_name(doc.GetFirstObject(), "GS_CameraRig")
    if rig is not None:
        child = rig.GetDown()
        while child:
            if _is_camera_obj(child) and "RenderCam" in child.GetName():
                render_cam = child
                break
            child = child.GetNext()
    if render_cam is None:
        bd = doc.GetActiveBaseDraw()
        if bd is not None:
            sc = bd.GetSceneCamera(doc)
            if sc is not None and _is_camera_obj(sc):
                render_cam = sc

    colmap_dir = settings.colmap_output_dir()
    camera_matrices = _camera_matrices_for_export(
        doc, render_cam, len(world_pts), settings.fps
    )
    colmap_result = export_colmap(
        settings, world_pts, target_pos, colmap_dir,
        render_cam=render_cam, doc=doc, target_obj=target_obj,
        camera_matrices=camera_matrices,
    )
    return colmap_result
