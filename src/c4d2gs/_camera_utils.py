import c4d
import os

from _constants import RS_CAMERA_TYPE_ID


# ---------------------------------------------------------------------------
# Intrinsics helpers
# ---------------------------------------------------------------------------

def get_colmap_intrinsics(settings, render_cam=None):
    if render_cam is not None:
        auto = _intrinsics_from_camera(render_cam, settings.res_x, settings.res_y)
        if auto is not None:
            return auto
    fx = float(settings.fx)
    fy = float(settings.fy)
    return {
        "model": _auto_colmap_model(fx, fy),
        "fx": fx,
        "fy": fy,
        "cx": float(settings.cx),
        "cy": float(settings.cy),
        "source": "fallback",
    }


def _auto_colmap_model(fx, fy):
    if abs(float(fx) - float(fy)) <= 1e-6:
        return "SIMPLE_PINHOLE"
    return "PINHOLE"


def _intrinsics_from_camera(cam, res_x, res_y):
    focus_pid = getattr(c4d, "CAMERA_FOCUS", None)
    aperture_pid = getattr(c4d, "CAMERAOBJECT_APERTURE", None)
    if focus_pid is None or aperture_pid is None:
        return None
    try:
        focal_mm = float(cam[focus_pid])
        aperture_w_mm = float(cam[aperture_pid])
    except Exception:
        return None
    if focal_mm <= 0.0 or aperture_w_mm <= 0.0 or res_x <= 0 or res_y <= 0:
        return None
    aperture_h_mm = aperture_w_mm * (float(res_y) / float(res_x))
    fx = (focal_mm / aperture_w_mm) * float(res_x)
    fy = (focal_mm / aperture_h_mm) * float(res_y)
    return {"model": _auto_colmap_model(fx, fy), "fx": fx, "fy": fy,
            "cx": res_x * 0.5, "cy": res_y * 0.5, "source": "render_camera"}


# ---------------------------------------------------------------------------
# Camera object creation
# ---------------------------------------------------------------------------

def _make_camera_object(camera_type):
    """Return a new camera BaseObject of the requested type.

    Falls back to the standard C4D camera if Redshift is not installed.
    """
    if int(camera_type) == 1:
        plugin = c4d.plugins.FindPlugin(RS_CAMERA_TYPE_ID, c4d.PLUGINTYPE_OBJECT)
        if plugin is not None:
            cam = c4d.BaseObject(RS_CAMERA_TYPE_ID)
            if cam is not None:
                return cam
    return c4d.BaseObject(c4d.Ocamera)


def _is_camera_obj(obj):
    """True if *obj* is any recognised camera type (standard or Redshift)."""
    return obj.CheckType(c4d.Ocamera) or obj.CheckType(RS_CAMERA_TYPE_ID)


def _set_focus_distance_to_target(cam, target_pos):
    if cam is None or target_pos is None:
        return
    try:
        dist = float((target_pos - cam.GetAbsPos()).GetLength())
    except Exception:
        return

    focus_distance_ids = [
        "CAMERAOBJECT_TARGETDISTANCE",
        "CAMERAOBJECT_FOCUSDISTANCE",
        "CAMERA_FOCUSDISTANCE",
        "CAMERAOBJECT_TARGETDIST",
        "CAMERA_FOCUSDIST",
    ]
    for name in focus_distance_ids:
        pid = getattr(c4d, name, None)
        if pid is None:
            continue
        try:
            cam[pid] = dist
            break
        except Exception:
            continue

    use_target_ids = [
        "CAMERAOBJECT_DEPTHOFFIELD_USETARGET",
        "CAMERAOBJECT_TARGETDISTANCE_ON",
        "CAMERAOBJECT_FOCUS_USE_TARGET",
        "CAMERA_DOFUSE",
    ]
    for name in use_target_ids:
        pid = getattr(c4d, name, None)
        if pid is None:
            continue
        try:
            cam[pid] = True
            break
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Animation track helpers
# ---------------------------------------------------------------------------

def _make_track(op, descid):
    track = op.FindCTrack(descid)
    if track is None:
        track = c4d.CTrack(op, descid)
        op.InsertTrackSorted(track)
    return track


def _add_step_key(op, descid, time, value):
    track = _make_track(op, descid)
    curve = track.GetCurve()
    kd = curve.AddKey(time)
    if not kd:
        return
    key = kd["key"]
    key.SetValue(curve, float(value))
    key.SetInterpolation(curve, c4d.CINTERPOLATION_STEP)


# ---------------------------------------------------------------------------
# Target-expression tag
# ---------------------------------------------------------------------------

def _create_target_tag(cam, target):
    tag = c4d.BaseTag(c4d.Ttargetexpression)
    if tag is None:
        return
    tag[c4d.TARGETEXPRESSIONTAG_LINK] = target
    cam.InsertTag(tag)


# ---------------------------------------------------------------------------
# Render settings
# ---------------------------------------------------------------------------

def configure_render_settings(doc, settings, render_cam, frame_count, create_output_dirs=True):
    rd = doc.GetActiveRenderData()
    if rd is None:
        return
    images_dir = settings.images_output_dir()
    if create_output_dirs and not os.path.exists(images_dir):
        os.makedirs(images_dir)
    rd[c4d.RDATA_XRES] = settings.res_x
    rd[c4d.RDATA_YRES] = settings.res_y
    rd[c4d.RDATA_FRAMERATE] = settings.fps
    rd[c4d.RDATA_SAVEIMAGE] = True
    rd[c4d.RDATA_PATH] = settings.render_output_pattern()
    rd[c4d.RDATA_FORMAT] = settings.output_format
    rd[c4d.RDATA_FRAMESEQUENCE] = c4d.RDATA_FRAMESEQUENCE_ALLFRAMES
    rd[c4d.RDATA_FRAMEFROM] = c4d.BaseTime(0, settings.fps)
    rd[c4d.RDATA_FRAMETO] = c4d.BaseTime(max(0, frame_count - 1), settings.fps)

    try:
        rd[c4d.RDATA_FILMASPECT] = c4d.RDATA_FILMASPECT_CUSTOM
        if settings.res_y > 0:
            rd[c4d.RDATA_PIXELASPECT] = float(settings.res_x) / float(settings.res_y)
        else:
            rd[c4d.RDATA_PIXELASPECT] = 1.0
    except Exception:
        try:
            rd[c4d.RDATA_PIXELASPECT] = 1.0
        except Exception:
            pass

    if settings.straight_alpha:
        for alpha_cid in ["RDATA_ALPHACHANNEL", "RDATA_ALPHA_CHANNEL"]:
            pid = getattr(c4d, alpha_cid, None)
            if pid is not None:
                try:
                    rd[pid] = True
                    break
                except Exception:
                    continue
        for straight_cid in ["RDATA_STRAIGHTALPHA", "RDATA_STRAIGHT_ALPHA"]:
            pid = getattr(c4d, straight_cid, None)
            if pid is not None:
                try:
                    rd[pid] = True
                    break
                except Exception:
                    continue

    if render_cam is not None:
        if hasattr(c4d, "RDATA_CAMERA"):
            rd[c4d.RDATA_CAMERA] = render_cam
        else:
            bd = doc.GetActiveBaseDraw()
            if bd is not None:
                bd.SetSceneCamera(render_cam)
