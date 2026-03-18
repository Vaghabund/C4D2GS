"""
C4D2GS — Cinema 4D to Gaussian Splat
======================================
A Cinema 4D Python plugin that generates Postshot-compatible datasets for
Gaussian Splatting.  It places a sphere of cameras around any object,
configures the render settings to output one image per viewpoint, and writes
the accompanying COLMAP files (cameras.txt / images.txt / points3D.txt) that
Postshot needs to reconstruct the scene.

Installation
------------
Drop the entire ``c4d2gs`` folder into your Cinema 4D plugins directory:

    macOS  : ~/Library/Preferences/Maxon/Maxon Cinema 4D <version>/plugins/
    Windows: %APPDATA%\\Maxon\\Maxon Cinema 4D <version>\\plugins\\

Restart Cinema 4D.  The plugin appears under **Plugins ▸ C4D2GS**.

Plugin ID
---------
The plugin is registered under ID **1057843**.  If you plan to distribute this
plugin commercially you must request your own unique ID from Maxon at
https://developers.maxon.net — replace PLUGIN_ID below with that value.
"""

import c4d
import math
import json
import os
import random
import bisect

# ---------------------------------------------------------------------------
# Plugin registration constant
# ---------------------------------------------------------------------------
# NOTE: 1057843 is a placeholder ID for private/local testing only.
# Before any public or commercial distribution you MUST request your own unique
# ID from Maxon (https://developers.maxon.net) and replace this value.
PLUGIN_ID = 1057843
PLUGIN_NAME = "C4D2GS"
PLUGIN_HELP = "Generate a Postshot-compatible Gaussian Splat dataset from Cinema 4D"
PLUGIN_VERSION = "1.0.0"

ERROR_NO_DOCUMENT = "C4D2GS-E001"
ERROR_NO_TARGET = "C4D2GS-E002"
ERROR_NO_OUTPUT_PATH = "C4D2GS-E003"
ERROR_BUILD_FAILED = "C4D2GS-E100"
ERROR_COLMAP_FAILED = "C4D2GS-E200"
RADIUS_MIN = 0.0
RADIUS_MAX = 1000.0
PERSIST_KEY_JSON = 1
NUMERIC_CLEAN_EPS = 1e-10
MAX_TRACK_OBS_PER_POINT = 12
RS_CAMERA_TYPE_ID = 1057516   # Redshift RSCamera plugin object type


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
    output_format=None,        # filled at runtime from c4d.FILTER_PNG
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


# ---------------------------------------------------------------------------
# Math / geometry helpers
# ---------------------------------------------------------------------------

def fibonacci_sphere_points(count):
    if count <= 0:
        return []
    points = []
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(count):
        y = 1.0 - (2.0 * i) / float(max(1, count - 1))
        radius = max(0.0, 1.0 - y * y) ** 0.5
        theta = golden_angle * i
        points.append(c4d.Vector(math.sin(theta) * radius, y, math.cos(theta) * radius))
    return points


def spiral_sphere_points(count, turns=6.0, pole_margin=0.06):
    if count <= 0:
        return []
    if count == 1:
        return [c4d.Vector(0, 1, 0)]
    margin = max(0.0, min(0.49, float(pole_margin)))
    y_top = 1.0 - 2.0 * margin
    y_bottom = -y_top
    points = []
    for i in range(count):
        t = i / float(count - 1)
        y = y_top + (y_bottom - y_top) * t
        ring_r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = 2.0 * math.pi * turns * t
        points.append(c4d.Vector(math.cos(theta) * ring_r, y, math.sin(theta) * ring_r))
    return points


def _normalize(v):
    length = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    if length <= 0.0:
        return c4d.Vector(0, 1, 0)
    return c4d.Vector(v.x / length, v.y / length, v.z / length)


def _cross(a, b):
    return c4d.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


def look_at_matrix(camera_pos, target_pos, up_hint=None):
    """Build a camera-to-world matrix that looks at *target_pos*.

    C4D cameras look down local **-Z**, so local +Z points away from the
    target.
    """
    if up_hint is None:
        up_hint = c4d.Vector(0, 1, 0)
    z_axis = _normalize(camera_pos - target_pos)
    if abs(_dot(z_axis, up_hint)) > 0.999:
        up_hint = c4d.Vector(0, 0, 1)
    x_axis = _normalize(_cross(up_hint, z_axis))
    y_axis = _normalize(_cross(z_axis, x_axis))
    mg = c4d.Matrix()
    mg.off = camera_pos
    mg.v1 = x_axis
    mg.v2 = y_axis
    mg.v3 = z_axis
    return mg


def matrix_to_rows(mg):
    return [
        [mg.v1.x, mg.v2.x, mg.v3.x, mg.off.x],
        [mg.v1.y, mg.v2.y, mg.v3.y, mg.off.y],
        [mg.v1.z, mg.v2.z, mg.v3.z, mg.off.z],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _clean_small(value, eps=NUMERIC_CLEAN_EPS):
    try:
        v = float(value)
    except Exception:
        return value
    if abs(v) < float(eps):
        return 0.0
    return v


def _clean_vec3(v, eps=NUMERIC_CLEAN_EPS):
    return [_clean_small(v.x, eps), _clean_small(v.y, eps), _clean_small(v.z, eps)]


def _clean_matrix_rows(rows, eps=NUMERIC_CLEAN_EPS):
    return [[_clean_small(cell, eps) for cell in row] for row in rows]


def _relative_frame_image_path(settings, frame_index):
    rel = os.path.join("images", os.path.basename(_frame_image_path(settings, frame_index)))
    return "./{}".format(rel.replace("\\", "/"))


def _nerf_file_path(settings, frame_index):
    return os.path.join("images", os.path.basename(_frame_image_path(settings, frame_index))).replace("\\", "/")


def nerf_matrix_to_rows(mg):
    rows = matrix_to_rows(mg)
    # Convert the C4D camera-to-world basis to the NeRF/OpenGL convention
    # expected by nerfstudio/instant-ngp by flipping the Y and Z axes.
    for row in rows[:3]:
        row[1] *= -1.0
        row[2] *= -1.0
    return rows


def _cap_observations(candidates, max_count):
    if len(candidates) <= max_count:
        return candidates
    if max_count <= 0:
        return []
    # Keep a deterministic spread over the candidate list.
    out = []
    n = len(candidates)
    for i in range(max_count):
        idx = int(round(i * (n - 1) / float(max_count - 1))) if max_count > 1 else 0
        out.append(candidates[idx])
    return out


def rotation_matrix_to_quaternion(r):
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        return 0.25 * s, (r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s
    elif (r[0][0] > r[1][1]) and (r[0][0] > r[2][2]):
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2.0
        return (r[2][1] - r[1][2]) / s, 0.25 * s, (r[0][1] + r[1][0]) / s, (r[0][2] + r[2][0]) / s
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2.0
        return (r[0][2] - r[2][0]) / s, (r[0][1] + r[1][0]) / s, 0.25 * s, (r[1][2] + r[2][1]) / s
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2.0
        return (r[1][0] - r[0][1]) / s, (r[0][2] + r[2][0]) / s, (r[1][2] + r[2][1]) / s, 0.25 * s


def c2w_to_colmap_extrinsics(mg):
    c_pos = mg.off
    xw, yw, zw = mg.v1, mg.v2, mg.v3
    # C4D camera local frame uses +Y up and +Z backward.
    # COLMAP/OpenCV expects a handedness-aligned camera frame here.
    # Convert by applying S = diag(1, -1, -1) in camera space.
    r_local_w2c = [
        [xw.x, xw.y, xw.z],
        [yw.x, yw.y, yw.z],
        [zw.x, zw.y, zw.z],
    ]
    r_w2c = [
        [ r_local_w2c[0][0],  r_local_w2c[0][1],  r_local_w2c[0][2]],
        [-r_local_w2c[1][0], -r_local_w2c[1][1], -r_local_w2c[1][2]],
        [-r_local_w2c[2][0], -r_local_w2c[2][1], -r_local_w2c[2][2]],
    ]
    qw, qx, qy, qz = rotation_matrix_to_quaternion(r_w2c)
    tx = -(r_w2c[0][0] * c_pos.x + r_w2c[0][1] * c_pos.y + r_w2c[0][2] * c_pos.z)
    ty = -(r_w2c[1][0] * c_pos.x + r_w2c[1][1] * c_pos.y + r_w2c[1][2] * c_pos.z)
    tz = -(r_w2c[2][0] * c_pos.x + r_w2c[2][1] * c_pos.y + r_w2c[2][2] * c_pos.z)
    return (qw, qx, qy, qz), (tx, ty, tz), r_w2c


def project_world_to_image(mg, world_point, world_normal, fx, fy, cx, cy):
    cam_pos = mg.off
    to_cam = _normalize(cam_pos - world_point)
    if _dot(to_cam, world_normal) <= 0.0:
        return None
    local = (~mg) * world_point
    # Convert C4D local camera coordinates (x right, y up, z backward)
    # to COLMAP/OpenCV camera coordinates (x right, y down, z forward).
    x_cv = local.x
    y_cv = -local.y
    z_cv = -local.z
    if z_cv <= 1e-6:
        return None
    return (fx * (x_cv / z_cv)) + cx, (fy * (y_cv / z_cv)) + cy


# ---------------------------------------------------------------------------
# Object / mesh helpers
# ---------------------------------------------------------------------------

def center_of_object(op):
    """Return a geometry-based world-space center for *op*.

    Uses combined bounds over object/cache hierarchy where available,
    and falls back to the object's axis position.
    """
    if op is None:
        return c4d.Vector(0)

    mn = None
    mx = None
    for node in _iter_cache_hierarchy(op):
        try:
            rad = node.GetRad()
            if rad is None:
                continue
            if abs(rad.x) < 1e-9 and abs(rad.y) < 1e-9 and abs(rad.z) < 1e-9:
                continue
            mp = node.GetMp()
            mg = node.GetMg()
            corners = [
                c4d.Vector(mp.x - rad.x, mp.y - rad.y, mp.z - rad.z),
                c4d.Vector(mp.x + rad.x, mp.y - rad.y, mp.z - rad.z),
                c4d.Vector(mp.x - rad.x, mp.y + rad.y, mp.z - rad.z),
                c4d.Vector(mp.x + rad.x, mp.y + rad.y, mp.z - rad.z),
                c4d.Vector(mp.x - rad.x, mp.y - rad.y, mp.z + rad.z),
                c4d.Vector(mp.x + rad.x, mp.y - rad.y, mp.z + rad.z),
                c4d.Vector(mp.x - rad.x, mp.y + rad.y, mp.z + rad.z),
                c4d.Vector(mp.x + rad.x, mp.y + rad.y, mp.z + rad.z),
            ]
            for lp in corners:
                wp = lp * mg
                if mn is None:
                    mn = c4d.Vector(wp.x, wp.y, wp.z)
                    mx = c4d.Vector(wp.x, wp.y, wp.z)
                else:
                    mn.x = min(mn.x, wp.x)
                    mn.y = min(mn.y, wp.y)
                    mn.z = min(mn.z, wp.z)
                    mx.x = max(mx.x, wp.x)
                    mx.y = max(mx.y, wp.y)
                    mx.z = max(mx.z, wp.z)
        except Exception:
            continue

    if mn is not None and mx is not None:
        return (mn + mx) * 0.5
    return op.GetMg().off


def axis_center_of_object(op):
    if op is None:
        return c4d.Vector(0)
    return op.GetMg().off


def object_center_for_mode(op, center_mode):
    if int(center_mode) == 1:
        return axis_center_of_object(op)
    return center_of_object(op)


def center_offset_for_mode(settings):
    if int(getattr(settings, "center_mode", 0)) == 1:
        return c4d.Vector(0)
    return c4d.Vector(settings.center_x, settings.center_y, settings.center_z)


def _safe_object_name(target_obj, default_name="Object"):
    name = default_name
    if target_obj is not None:
        try:
            raw = str(target_obj.GetName()).strip()
            if raw:
                name = raw
        except Exception:
            pass
    return name.replace("\\", "_").replace("/", "_")


def rig_name_for_target(target_obj):
    return "GS_CameraRig_{}".format(_safe_object_name(target_obj, "Object"))


def target_name_for_target(target_obj):
    return "GS_Target_{}".format(_safe_object_name(target_obj, "Object"))


def get_object_bounding_radius(op):
    """Return a reasonable sphere radius that contains the object."""
    if op is None:
        return 300.0
    try:
        rad = op.GetRad()
        diag = math.sqrt(rad.x ** 2 + rad.y ** 2 + rad.z ** 2)
        return max(diag * 2.5, 10.0)
    except Exception:
        return 300.0


def find_object_by_name(start_obj, name):
    obj = start_obj
    while obj:
        if obj.GetName() == name:
            return obj
        child = obj.GetDown()
        if child:
            found = find_object_by_name(child, name)
            if found is not None:
                return found
        obj = obj.GetNext()
    return None


def _iter_hierarchy(op):
    node = op
    while node:
        yield node
        child = node.GetDown()
        if child:
            for sub in _iter_hierarchy(child):
                yield sub
        node = node.GetNext()


def _iter_cache_hierarchy(op):
    if op is None:
        return
    yield op
    deform = op.GetDeformCache()
    if deform is not None:
        for sub in _iter_hierarchy(deform):
            yield sub
    cache = op.GetCache()
    if cache is not None:
        for sub in _iter_hierarchy(cache):
            yield sub
    child = op.GetDown()
    if child is not None:
        for sub in _iter_hierarchy(child):
            yield sub


def _make_editable(op):
    if not op or op.CheckType(c4d.Opolygon) or op.CheckType(c4d.Ospline):
        return op
    tmp_doc = c4d.documents.BaseDocument()
    clone = op.GetClone()
    tmp_doc.InsertObject(clone, None, None)
    clone.SetMg(op.GetMg())
    try:
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_MAKEEDITABLE,
            list=[clone],
            mode=c4d.MODELINGCOMMANDMODE_ALL,
            doc=tmp_doc,
        )
    except Exception:
        return None
    return result[0] if result else None


def _get_current_state_object(doc, obj):
    try:
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
            list=[obj],
            mode=c4d.MODELINGCOMMANDMODE_ALL,
            doc=doc,
            flags=c4d.MODELINGCOMMANDFLAGS_NONE,
        )
    except Exception:
        return None
    return result[0] if result else None


def _triangle_area(a, b, c):
    return _cross(b - a, c - a).GetLength() * 0.5


def _sample_on_triangle_with_normal(a, b, c):
    r1 = random.random()
    r2 = random.random()
    s1 = math.sqrt(r1)
    point = a * (1.0 - s1) + b * (s1 * (1.0 - r2)) + c * (s1 * r2)
    normal = _normalize(_cross(b - a, c - a))
    return point, normal


def _collect_world_triangles(root_obj):
    # _iter_cache_hierarchy already yields root_obj, its deform/render caches,
    # and all descendant objects via _iter_hierarchy — no separate child walk needed.
    triangles = []
    for obj in _iter_cache_hierarchy(root_obj):
        if obj.CheckType(c4d.Opolygon):
            mg = obj.GetMg()
            pts = obj.GetAllPoints()
            if pts:
                wpts = [p * mg for p in pts]
                for poly in obj.GetAllPolygons():
                    triangles.append((wpts[poly.a], wpts[poly.b], wpts[poly.c]))
                    if poly.c != poly.d:
                        triangles.append((wpts[poly.a], wpts[poly.c], wpts[poly.d]))
    return triangles


def generate_sparse_points_from_surface(doc, target_obj, count=256):
    """Area-weighted sampling of *count* points on the target object surface.

    Returns ``(point, normal)`` tuples in world space.
    """
    count = max(8, int(count))
    triangles = []
    for bake_fn in [
        lambda: _make_editable(target_obj),
        lambda: _get_current_state_object(doc, target_obj),
        lambda: target_obj,
    ]:
        try:
            baked = bake_fn()
            if baked is not None:
                triangles = _collect_world_triangles(baked)
        except Exception:
            pass
        if triangles:
            break
    if not triangles:
        return None

    areas, cumulative, running = [], [], 0.0
    for tri in triangles:
        ar = _triangle_area(*tri)
        if ar <= 1e-12:
            continue
        areas.append(tri)
        running += ar
        cumulative.append(running)

    if running <= 0.0 or not areas:
        return None

    out = []
    for _ in range(count):
        r = random.random() * running
        idx = bisect.bisect_left(cumulative, r)
        if idx >= len(areas):
            idx = len(areas) - 1
        out.append(_sample_on_triangle_with_normal(*areas[idx]))
    return out


# ---------------------------------------------------------------------------
# Icosphere sampling
# ---------------------------------------------------------------------------

def _icosahedron():
    t = (1.0 + math.sqrt(5.0)) / 2.0
    verts = [
        c4d.Vector(-1, t, 0), c4d.Vector(1, t, 0), c4d.Vector(-1, -t, 0), c4d.Vector(1, -t, 0),
        c4d.Vector(0, -1, t), c4d.Vector(0, 1, t), c4d.Vector(0, -1, -t), c4d.Vector(0, 1, -t),
        c4d.Vector(t, 0, -1), c4d.Vector(t, 0, 1), c4d.Vector(-t, 0, -1), c4d.Vector(-t, 0, 1),
    ]
    verts = [_normalize(v) for v in verts]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    return verts, faces


def _icosphere_subdivisions_for(target_count):
    if target_count <= 12:
        return 0
    best_n, best_diff = 0, abs(12 - target_count)
    for n in range(1, 9):
        cnt = 10 * (4 ** n) + 2
        diff = abs(cnt - target_count)
        if diff < best_diff:
            best_n, best_diff = n, diff
        if cnt >= target_count and diff > best_diff:
            break
    return best_n


def icosphere_points(target_count):
    verts, faces = _icosahedron()
    subdivisions = _icosphere_subdivisions_for(target_count)
    for _ in range(subdivisions):
        cache = {}

        def midpoint(i1, i2):
            key = (min(i1, i2), max(i1, i2))
            if key in cache:
                return cache[key]
            mid = _normalize((verts[i1] + verts[i2]) * 0.5)
            verts.append(mid)
            cache[key] = len(verts) - 1
            return cache[key]

        new_faces = []
        for a, b, c in faces:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new_faces
    return verts, subdivisions


def generate_unit_points(settings):
    """Return (unit_points, mode_name, extra_info) based on *settings*."""
    mode = settings.sampling_mode
    count = settings.camera_count
    if mode == 1:
        pts, subdiv = icosphere_points(count)
        return pts, "icosphere", subdiv
    if mode == 2:
        return fibonacci_sphere_points(count), "fibonacci", 0
    return spiral_sphere_points(count, settings.spiral_turns, settings.spiral_pole_margin), "spiral", 0


# ---------------------------------------------------------------------------
# Intrinsics helpers
# ---------------------------------------------------------------------------

def get_colmap_intrinsics(settings, render_cam=None):
    if settings.auto_intrinsics and render_cam is not None:
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
        "source": "manual",
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
# File-path helpers
# ---------------------------------------------------------------------------

def _frame_image_path(settings, frame_index):
    # Rendered frames are always stored under <output>/images.
    base = os.path.join(settings.images_output_dir(), "gs_{:04d}".format(frame_index))
    ext = _output_extension(settings)
    return base if base.lower().endswith(ext.lower()) else base + ext


def _output_extension(settings):
    ext_map = {}
    for name, ext in [("FILTER_PNG", ".png"), ("FILTER_JPG", ".jpg"),
                      ("FILTER_TIF", ".tif"), ("FILTER_EXR", ".exr")]:
        val = getattr(c4d, name, None)
        if val is not None:
            ext_map[val] = ext
    return ext_map.get(settings.output_format, ".png")


def _normalize_path(path):
    p = os.path.expandvars(os.path.expanduser(str(path).strip()))
    if not p:
        return ""
    p = os.path.normpath(p)
    return p if os.path.isabs(p) else os.path.abspath(p)


# ---------------------------------------------------------------------------
# Export: camera poses JSON
# ---------------------------------------------------------------------------

def export_camera_poses_json(settings, world_points, target_pos, render_cam=None):
    if not world_points:
        return None
    intrinsics = get_colmap_intrinsics(settings, render_cam)
    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    w, h = int(settings.res_x), int(settings.res_y)

    frames = []
    for i, world_pos in enumerate(world_points):
        mg = look_at_matrix(world_pos, target_pos)
        hpb = c4d.utils.MatrixToHPB(mg)
        frames.append({
            "frame": i,
            "camera_name": "GS_Cam_{:04d}".format(i + 1),
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
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    return out_path


# ---------------------------------------------------------------------------
# Export: COLMAP files
# ---------------------------------------------------------------------------

def _write_cameras_txt(path, intrinsics, res_x, res_y):
    model = str(intrinsics["model"]).strip().upper()
    with open(path, "w") as f:
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


def export_colmap(settings, world_points, target_pos, output_dir,
                  render_cam=None, doc=None, target_obj=None):
    """Write cameras.txt / images.txt / points3D.txt for Postshot."""
    if not world_points:
        return None

    output_dir = _normalize_path(output_dir)
    if not output_dir:
        raise ValueError("COLMAP output path is empty.")
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
        raise ValueError("A target object is required for COLMAP export.")

    sparse_points_with_normals = generate_sparse_points_from_surface(doc, target_obj, settings.sparse_count)
    if not sparse_points_with_normals:
        raise ValueError(
            "Could not sample sparse points from the object surface. "
            "Ensure the object has polygonal geometry."
        )

    # Build image entries with look-at poses
    image_entries = []
    for i, world_pos in enumerate(world_points):
        mg = look_at_matrix(world_pos, target_pos)
        q, t, r_w2c = c2w_to_colmap_extrinsics(mg)
        image_name = os.path.relpath(_frame_image_path(settings, i), output_dir).replace("\\", "/")
        image_entries.append({
            "image_id": i + 1,
            "name": image_name,
            "q": q, "t": t, "r_w2c": r_w2c, "mg": mg, "obs": [],
        })

    # Build 2-D observations with capped track size per 3D point.
    tracks_by_pid = {}
    max_obs = max(2, int(MAX_TRACK_OBS_PER_POINT))
    for pid, (p3d, nrm) in enumerate(sparse_points_with_normals, start=1):
        tracks_by_pid[pid] = []
        candidates = []
        for entry in image_entries:
            projected = project_world_to_image(entry["mg"], p3d, nrm, fx, fy, cx, cy)
            if projected is None:
                continue
            u, v = projected
            if 0.0 <= u < width and 0.0 <= v < height:
                candidates.append((entry, u, v))

        for entry, u, v in _cap_observations(candidates, max_obs):
            p2d_idx = len(entry["obs"])
            entry["obs"].append((u, v, pid))
            tracks_by_pid[pid].append((entry["image_id"], p2d_idx))

    # images.txt
    with open(images_txt, "w") as f:
        f.write("# Image list with two lines of data per image:\n")
        f.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        f.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        f.write("# Number of images: {}\n".format(len(world_points)))
        for entry in image_entries:
            f.write("{} {} {} {} {} {} {} {} 1 {}\n".format(
                entry["image_id"],
                _clean_small(entry["q"][0]), _clean_small(entry["q"][1]), _clean_small(entry["q"][2]), _clean_small(entry["q"][3]),
                _clean_small(entry["t"][0]), _clean_small(entry["t"][1]), _clean_small(entry["t"][2]),
                entry["name"],
            ))
            if entry["obs"]:
                f.write(" ".join("{} {} {}".format(o[0], o[1], o[2]) for o in entry["obs"]) + "\n")
            else:
                f.write("\n")

    # points3D.txt — Postshot can initialize from points observed in >= 1 camera.
    valid_points = [
        (pid, p3d, tracks_by_pid[pid])
        for pid, (p3d, _nrm) in enumerate(sparse_points_with_normals, start=1)
        if len(tracks_by_pid.get(pid, [])) >= 1
    ]
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
        ]
        report = os.path.join(output_dir, "colmap_debug.txt")
        with open(report, "w") as f:
            f.write("\n".join(debug) + "\n")
        raise ValueError(
            "No sparse point had >= 1 observation after visibility checks. "
            "Try increasing the camera count, the sphere radius, or the sparse point count. "
            "Debug report: {}".format(report)
        )

    with open(points3d_txt, "w") as f:
        f.write("# 3D point list with one line of data per point:\n")
        f.write("#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]\n")
        f.write("# Number of points: {}\n".format(len(valid_points)))
        for pid, p3d, track in valid_points:
            track_flat = " ".join("{} {}".format(img_id, p2d) for img_id, p2d in track)
            f.write("{} {} {} {} 255 255 255 1.0 {}\n".format(
                pid, p3d.x, p3d.y, p3d.z, track_flat))

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


# ---------------------------------------------------------------------------
# Scene-building helpers
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


def _create_target_tag(cam, target):
    tag = c4d.BaseTag(c4d.Ttargetexpression)
    if tag is None:
        return
    tag[c4d.TARGETEXPRESSIONTAG_LINK] = target
    cam.InsertTag(tag)


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

    # C4D versions expose different camera focus-distance IDs.
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

    # Enable the "Use Target Object" checkbox so focus tracks the target tag.
    # Parameter name varies across C4D versions; try all known candidates.
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


def configure_render_settings(doc, settings, render_cam, frame_count):
    rd = doc.GetActiveRenderData()
    if rd is None:
        return
    images_dir = settings.images_output_dir()
    if not os.path.exists(images_dir):
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
    if render_cam is not None:
        if hasattr(c4d, "RDATA_CAMERA"):
            rd[c4d.RDATA_CAMERA] = render_cam
        else:
            bd = doc.GetActiveBaseDraw()
            if bd is not None:
                bd.SetSceneCamera(render_cam)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(doc, settings, target_obj):
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
            cam.SetName("GS_Cam_{:04d}".format(i + 1))
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

        configure_render_settings(doc, settings, render_cam, len(world_pts))

        # JSON export
        pose_file = None
        if settings.export_json:
            try:
                pose_file = export_camera_poses_json(settings, world_pts, target_pos, render_cam)
            except Exception as e:
                pose_file = "ERROR: {}".format(e)

        # COLMAP export
        colmap_result = None
        if settings.export_colmap:
            colmap_dir = settings.colmap_output_dir()
            colmap_result = export_colmap(
                settings, world_pts, target_pos, colmap_dir,
                render_cam=render_cam, doc=doc, target_obj=target_obj,
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
    """Create or rebuild camera rig without exporting JSON/COLMAP files."""
    temp = Settings()
    temp.__dict__.update(settings.__dict__)
    temp.export_json = False
    temp.export_colmap = False
    return run_pipeline(doc, temp, target_obj)


def run_colmap_only(doc, settings, target_obj):
    """Export COLMAP files without modifying the scene."""
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
    colmap_result = export_colmap(
        settings, world_pts, target_pos, colmap_dir,
        render_cam=render_cam, doc=doc, target_obj=target_obj,
    )
    return colmap_result


# ---------------------------------------------------------------------------
# Dialog — UI widget IDs
# ---------------------------------------------------------------------------

class _IDs:
    # Header
    TARGET_LINK = 1000

    # Camera
    CAM_COUNT = 1020
    RADIUS = 1021
    CENTER_X = 1022
    CENTER_Y = 1023
    CENTER_Z = 1024
    SAMPLING_MODE = 1025
    SPIRAL_TURNS = 1026
    SPIRAL_POLE = 1027
    CENTER_MODE = 1028

    # Tab: Output
    OUTPUT_PATH = 1030
    OUTPUT_PATH_BROWSE = 1031
    OUTPUT_FORMAT = 1032
    RES_X = 1033
    RES_Y = 1034
    FPS = 1035

    # Tab: Export
    CREATE_ANIM_CAM = 1040
    REPLACE_RIG = 1041
    AUTO_UPDATE_RIG = 1053
    EXPORT_JSON = 1042
    JSON_PATH = 1043
    JSON_PATH_BROWSE = 1044
    EXPORT_COLMAP = 1045
    AUTO_INTRINSICS = 1046
    FX = 1048
    FY = 1049
    CX = 1050
    CY = 1051
    SPARSE_COUNT = 1052
    CAMERA_TYPE = 1055

    # Action buttons
    BTN_CREATE_RIG = 1089
    BTN_EXECUTE = 1090
    BTN_COLMAP_ONLY = 1091
    BTN_CLOSE = 1092

    # Status
    STATUS_TEXT = 1099

    # Group IDs (non-interactive)
    GRP_HEADER = 2000
    GRP_CAMERA_TAB = 2001
    GRP_OUTPUT_TAB = 2002
    GRP_EXPORT_TAB = 2003
    GRP_BUTTONS = 2004
    GRP_SPHERE = 2010
    GRP_DIST = 2011
    GRP_OUTPUT_PATH_ROW = 2012
    GRP_JSON_PATH_ROW = 2013
    GRP_RES = 2014
    GRP_INTRINSICS = 2015


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------

class C4D2GSDialog(c4d.gui.GeDialog):

    def __init__(self):
        super(C4D2GSDialog, self).__init__()
        self._settings = Settings()
        _load_settings(self._settings)
        self._target_obj = None  # c4d.BaseObject or None
        self._target_link_gui = None
        self._is_auto_updating = False
        self._values_ready = False

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def CreateLayout(self):
        self.SetTitle("C4D2GS  —  Postshot Dataset Generator  v{}".format(PLUGIN_VERSION))

        # ---- Action buttons (top strip) ----
        self.GroupBegin(_IDs.GRP_BUTTONS, c4d.BFH_SCALEFIT, cols=4, rows=1)
        self.GroupBorderSpace(6, 6, 6, 4)
        self.AddButton(_IDs.BTN_CREATE_RIG, c4d.BFH_SCALEFIT, name="  Create / Update Rig  ")
        self.AddButton(_IDs.BTN_EXECUTE, c4d.BFH_SCALEFIT, name="  Build & Export  ")
        self.AddButton(_IDs.BTN_COLMAP_ONLY, c4d.BFH_SCALEFIT, name="  COLMAP Only  ")
        self.AddButton(_IDs.BTN_CLOSE, c4d.BFH_SCALEFIT, name="  Close  ")
        self.GroupEnd()

        # ---- Header: target object ----
        self.GroupBegin(_IDs.GRP_HEADER, c4d.BFH_SCALEFIT, cols=2, rows=1,
                        title="Target Object", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)
        self.AddStaticText(2999, c4d.BFH_LEFT, name="Object")
        self._target_link_gui = self.AddCustomGui(
            _IDs.TARGET_LINK, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )
        self.GroupEnd()

        # ---- Main sections ----
        self.GroupBegin(2100, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0)
        self.GroupBorderSpace(0, 4, 0, 4)

        self._build_camera_tab()
        self._add_section_divider()
        self._build_output_tab()
        self._add_section_divider()
        self._build_export_tab()

        self.GroupEnd()

        # ---- Status ----
        self.AddStaticText(_IDs.STATUS_TEXT, c4d.BFH_SCALEFIT,
                           name="Select a target object and click Build & Export.")

        return True

    def _build_camera_tab(self):
        self.GroupBegin(_IDs.GRP_CAMERA_TAB,
                        c4d.BFH_SCALEFIT,
                        cols=1, title="Camera", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)

        # Sphere section
        self.GroupBegin(_IDs.GRP_SPHERE, c4d.BFH_SCALEFIT, cols=2,
                        title="Sphere", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(3000, c4d.BFH_LEFT, name="Camera Count")
        self.AddEditNumberArrows(_IDs.CAM_COUNT, c4d.BFH_SCALEFIT)

        self.AddStaticText(3001, c4d.BFH_LEFT, name="Radius")
        if hasattr(self, "AddEditSlider"):
            self.AddEditSlider(_IDs.RADIUS, c4d.BFH_SCALEFIT)
        else:
            self.AddEditNumberArrows(_IDs.RADIUS, c4d.BFH_SCALEFIT)

        self.AddStaticText(3002, c4d.BFH_LEFT, name="Center Offset X")
        self.AddEditNumberArrows(_IDs.CENTER_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(3003, c4d.BFH_LEFT, name="Center Offset Y")
        self.AddEditNumberArrows(_IDs.CENTER_Y, c4d.BFH_SCALEFIT)
        self.AddStaticText(3004, c4d.BFH_LEFT, name="Center Offset Z")
        self.AddEditNumberArrows(_IDs.CENTER_Z, c4d.BFH_SCALEFIT)
        self.AddStaticText(3005, c4d.BFH_LEFT, name="Center Mode")
        self.AddComboBox(_IDs.CENTER_MODE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.CENTER_MODE, 0, "Geometry Center")
        self.AddChild(_IDs.CENTER_MODE, 1, "Axis Pivot")

        self.AddStaticText(3006, c4d.BFH_LEFT, name="Camera Type")
        self.AddComboBox(_IDs.CAMERA_TYPE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.CAMERA_TYPE, 0, "Standard")
        self.AddChild(_IDs.CAMERA_TYPE, 1, "Redshift RSCamera")
        self.GroupEnd()

        # Distribution section
        self.GroupBegin(_IDs.GRP_DIST, c4d.BFH_SCALEFIT, cols=2,
                        title="Distribution", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(3010, c4d.BFH_LEFT, name="Sampling Mode")
        self.AddComboBox(_IDs.SAMPLING_MODE, c4d.BFH_SCALEFIT)
        for mode_id, label in [(0, "Spiral"), (1, "Icosphere"), (2, "Fibonacci")]:
            self.AddChild(_IDs.SAMPLING_MODE, mode_id, label)

        self.AddStaticText(3011, c4d.BFH_LEFT, name="Spiral Turns")
        self.AddEditNumberArrows(_IDs.SPIRAL_TURNS, c4d.BFH_SCALEFIT)

        self.AddStaticText(3012, c4d.BFH_LEFT, name="Pole Margin")
        self.AddEditNumberArrows(_IDs.SPIRAL_POLE, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.GroupEnd()

    def _add_section_divider(self):
        self.GroupBegin(2090, c4d.BFH_SCALEFIT, cols=1, rows=1)
        self.GroupBorderSpace(0, 6, 0, 6)
        if hasattr(self, "AddSeparatorH"):
            try:
                self.AddSeparatorH(0)
                self.GroupEnd()
                return
            except Exception:
                pass
        self.AddStaticText(3090, c4d.BFH_SCALEFIT, name="")
        self.GroupEnd()

    def _build_output_tab(self):
        self.GroupBegin(_IDs.GRP_OUTPUT_TAB,
                        c4d.BFH_SCALEFIT,
                        cols=1, title="Output", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)

        self.GroupBegin(2030, c4d.BFH_SCALEFIT, cols=2,
                        title="Image Output", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(3020, c4d.BFH_LEFT, name="Output Path")
        self.GroupBegin(_IDs.GRP_OUTPUT_PATH_ROW, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.AddEditText(_IDs.OUTPUT_PATH, c4d.BFH_SCALEFIT)
        self.AddButton(_IDs.OUTPUT_PATH_BROWSE, c4d.BFH_RIGHT, name="Browse…")
        self.GroupEnd()

        self.AddStaticText(3025, c4d.BFH_LEFT, name="Generated Files")
        self.AddStaticText(3026, c4d.BFH_LEFT, name="cameras.txt + images.txt + points3D.txt + images/gs_####")

        self.AddStaticText(3021, c4d.BFH_LEFT, name="Format")
        self.AddComboBox(_IDs.OUTPUT_FORMAT, c4d.BFH_SCALEFIT)
        for fmt_id, fmt_name in self._output_format_items():
            self.AddChild(_IDs.OUTPUT_FORMAT, int(fmt_id), fmt_name)

        self.AddStaticText(3022, c4d.BFH_LEFT, name="Resolution")
        self.GroupBegin(_IDs.GRP_RES, c4d.BFH_SCALEFIT, cols=3, rows=1)
        self.AddEditNumber(_IDs.RES_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(3023, c4d.BFH_CENTER, name="×")
        self.AddEditNumber(_IDs.RES_Y, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.AddStaticText(3024, c4d.BFH_LEFT, name="FPS")
        self.AddEditNumberArrows(_IDs.FPS, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.GroupEnd()

    def _build_export_tab(self):
        self.GroupBegin(_IDs.GRP_EXPORT_TAB,
                        c4d.BFH_SCALEFIT,
                        cols=1, title="Export", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)

        # Scene options
        self.GroupBegin(2040, c4d.BFH_SCALEFIT, cols=2,
                        title="Scene Options", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)
        self.AddStaticText(3030, c4d.BFH_LEFT, name="Create Animated Render Cam")
        self.AddCheckbox(_IDs.CREATE_ANIM_CAM, c4d.BFH_LEFT, 0, 0, name="")
        self.AddStaticText(3031, c4d.BFH_LEFT, name="Replace Existing Rig")
        self.AddCheckbox(_IDs.REPLACE_RIG, c4d.BFH_LEFT, 0, 0, name="")
        self.AddStaticText(3035, c4d.BFH_LEFT, name="Auto Update Rig")
        self.AddCheckbox(_IDs.AUTO_UPDATE_RIG, c4d.BFH_LEFT, 0, 0, name="")
        self.GroupEnd()

        # Camera pose JSON
        self.GroupBegin(2041, c4d.BFH_SCALEFIT, cols=2,
                        title="Camera Pose JSON", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)
        self.AddStaticText(3032, c4d.BFH_LEFT, name="Export Pose JSON")
        self.AddCheckbox(_IDs.EXPORT_JSON, c4d.BFH_LEFT, 0, 0, name="")
        self.AddStaticText(3033, c4d.BFH_LEFT, name="JSON Output")
        self.AddStaticText(3034, c4d.BFH_LEFT, name="<Output Path>/camera_poses.json")
        self.GroupEnd()

        # Postshot COLMAP
        self.GroupBegin(2042, c4d.BFH_SCALEFIT, cols=2,
                        title="Postshot COLMAP", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)
        self.AddStaticText(3040, c4d.BFH_LEFT, name="Export COLMAP")
        self.AddCheckbox(_IDs.EXPORT_COLMAP, c4d.BFH_LEFT, 0, 0, name="")

        self.AddStaticText(3041, c4d.BFH_LEFT, name="Auto Intrinsics from Cam")
        self.AddCheckbox(_IDs.AUTO_INTRINSICS, c4d.BFH_LEFT, 0, 0, name="")

        self.GroupBegin(_IDs.GRP_INTRINSICS, c4d.BFH_SCALEFIT, cols=2,
                        title="Manual Intrinsics", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 2, 6, 2)
        self.AddStaticText(3043, c4d.BFH_LEFT, name="fx")
        self.AddEditNumberArrows(_IDs.FX, c4d.BFH_SCALEFIT)
        self.AddStaticText(3044, c4d.BFH_LEFT, name="fy")
        self.AddEditNumberArrows(_IDs.FY, c4d.BFH_SCALEFIT)
        self.AddStaticText(3045, c4d.BFH_LEFT, name="cx")
        self.AddEditNumberArrows(_IDs.CX, c4d.BFH_SCALEFIT)
        self.AddStaticText(3046, c4d.BFH_LEFT, name="cy")
        self.AddEditNumberArrows(_IDs.CY, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.AddStaticText(3047, c4d.BFH_LEFT, name="Sparse Point Count")
        self.AddEditNumberArrows(_IDs.SPARSE_COUNT, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.GroupEnd()

    @staticmethod
    def _output_format_items():
        items = []
        for label, const_name in [("PNG", "FILTER_PNG"), ("JPG", "FILTER_JPG"),
                                   ("TIF", "FILTER_TIF"), ("EXR", "FILTER_EXR")]:
            val = getattr(c4d, const_name, None)
            if val is not None:
                items.append((val, label))
        return items

    # ------------------------------------------------------------------
    # Value initialisation
    # ------------------------------------------------------------------

    def InitValues(self):
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        self._target_obj = self._resolve_target_object(doc)
        if self._target_obj is not None:
            self._set_link_target(self._target_obj)

        # Camera tab
        self._si(_IDs.CAM_COUNT, s.camera_count, 1, 100000)
        s.sphere_radius = max(RADIUS_MIN, min(RADIUS_MAX, float(s.sphere_radius)))
        self._sf(_IDs.RADIUS, s.sphere_radius, RADIUS_MIN, RADIUS_MAX, 1.0)
        self._sf(_IDs.CENTER_X, s.center_x, -1e9, 1e9, 1.0)
        self._sf(_IDs.CENTER_Y, s.center_y, -1e9, 1e9, 1.0)
        self._sf(_IDs.CENTER_Z, s.center_z, -1e9, 1e9, 1.0)
        self.SetInt32(_IDs.CENTER_MODE, int(getattr(s, "center_mode", 0)))
        self.SetInt32(_IDs.CAMERA_TYPE, int(getattr(s, "camera_type", 0)))
        self.SetInt32(_IDs.SAMPLING_MODE, s.sampling_mode)
        self._sf(_IDs.SPIRAL_TURNS, s.spiral_turns, 0.01, 1e6, 0.1)
        self._sf(_IDs.SPIRAL_POLE, s.spiral_pole_margin, 0.0, 0.49, 0.001)

        # Output tab
        self.SetString(_IDs.OUTPUT_PATH, str(s.output_folder()))
        self.SetInt32(_IDs.OUTPUT_FORMAT, int(s.output_format))
        self._si(_IDs.RES_X, s.res_x, 1, 65535)
        self._si(_IDs.RES_Y, s.res_y, 1, 65535)
        self._si(_IDs.FPS, s.fps, 1, 1000)

        # Export tab
        self.SetBool(_IDs.CREATE_ANIM_CAM, bool(s.create_anim_cam))
        self.SetBool(_IDs.REPLACE_RIG, bool(s.replace_rig))
        self.SetBool(_IDs.AUTO_UPDATE_RIG, bool(s.auto_update_rig))
        self.SetBool(_IDs.EXPORT_JSON, bool(s.export_json))
        self.SetBool(_IDs.EXPORT_COLMAP, bool(s.export_colmap))
        self.SetBool(_IDs.AUTO_INTRINSICS, bool(s.auto_intrinsics))
        self._sf(_IDs.FX, s.fx, 0.01, 1e9, 1.0)
        self._sf(_IDs.FY, s.fy, 0.01, 1e9, 1.0)
        self._sf(_IDs.CX, s.cx, -1e9, 1e9, 1.0)
        self._sf(_IDs.CY, s.cy, -1e9, 1e9, 1.0)
        self._si(_IDs.SPARSE_COUNT, s.sparse_count, 8, 100000)

        self._update_center_offset_ui()
        self._update_intrinsics_ui()
        self._refresh_status()
        self._values_ready = True
        return True

    def _si(self, cid, value, mn, mx):
        try:
            self.SetInt32(cid, int(value), int(mn), int(mx))
        except TypeError:
            self.SetInt32(cid, int(value))

    def _sf(self, cid, value, mn, mx, step=0.1):
        try:
            self.SetFloat(cid, float(value), float(mn), float(mx), float(step))
        except TypeError:
            self.SetFloat(cid, float(value))

    # ------------------------------------------------------------------
    # Read UI → Settings
    # ------------------------------------------------------------------

    def _read_ui(self):
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        link_obj = self._get_link_target(doc)
        if link_obj is not None:
            self._target_obj = link_obj
        elif self._target_obj is None:
            self._target_obj = self._resolve_target_object(doc)
        if self._target_obj is not None:
            self._set_link_target(self._target_obj)

        s.camera_count = max(1, int(self.GetInt32(_IDs.CAM_COUNT)))
        s.sphere_radius = max(RADIUS_MIN, min(RADIUS_MAX, float(self.GetFloat(_IDs.RADIUS))))
        s.center_x = float(self.GetFloat(_IDs.CENTER_X))
        s.center_y = float(self.GetFloat(_IDs.CENTER_Y))
        s.center_z = float(self.GetFloat(_IDs.CENTER_Z))
        s.center_mode = int(self.GetInt32(_IDs.CENTER_MODE))
        s.camera_type = int(self.GetInt32(_IDs.CAMERA_TYPE))
        s.sampling_mode = int(self.GetInt32(_IDs.SAMPLING_MODE))
        s.spiral_turns = max(0.01, float(self.GetFloat(_IDs.SPIRAL_TURNS)))
        s.spiral_pole_margin = max(0.0, min(0.49, float(self.GetFloat(_IDs.SPIRAL_POLE))))

        s.output_path = _normalize_path(self.GetString(_IDs.OUTPUT_PATH).strip())
        if s.output_path:
            self.SetString(_IDs.OUTPUT_PATH, s.output_path)
        s.output_format = int(self.GetInt32(_IDs.OUTPUT_FORMAT))
        s.res_x = max(1, int(self.GetInt32(_IDs.RES_X)))
        s.res_y = max(1, int(self.GetInt32(_IDs.RES_Y)))
        s.fps = max(1, int(self.GetInt32(_IDs.FPS)))

        s.create_anim_cam = bool(self.GetBool(_IDs.CREATE_ANIM_CAM))
        s.replace_rig = bool(self.GetBool(_IDs.REPLACE_RIG))
        s.auto_update_rig = bool(self.GetBool(_IDs.AUTO_UPDATE_RIG))
        s.export_json = bool(self.GetBool(_IDs.EXPORT_JSON))
        s.export_colmap = bool(self.GetBool(_IDs.EXPORT_COLMAP))
        s.auto_intrinsics = bool(self.GetBool(_IDs.AUTO_INTRINSICS))
        s.fx = float(self.GetFloat(_IDs.FX))
        s.fy = float(self.GetFloat(_IDs.FY))
        s.cx = float(self.GetFloat(_IDs.CX))
        s.cy = float(self.GetFloat(_IDs.CY))
        s.sparse_count = max(8, int(self.GetInt32(_IDs.SPARSE_COUNT)))

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _refresh_status(self):
        s = self._settings
        name = self._target_obj.GetName() if self._target_obj else "(none)"
        mode = s.sampling_mode_name()
        center_mode = "Geometry" if int(getattr(s, "center_mode", 0)) == 0 else "Axis"
        exports = []
        if s.export_json:
            exports.append("JSON")
        if s.export_colmap:
            exports.append("COLMAP")
        exp_str = " + ".join(exports) if exports else "none"
        status = (
            "Target: {}  |  Cameras: {}  |  Mode: {}  |  Center: {}  |  "
            "Res: {}×{}  |  Export: {}"
        ).format(name, s.camera_count, mode, center_mode, s.res_x, s.res_y, exp_str)
        self.SetString(_IDs.STATUS_TEXT, status)

    def _try_auto_update_rig(self, cid):
        if self._is_auto_updating:
            return
        if not bool(self._settings.auto_update_rig):
            return
        skip_ids = {
            _IDs.BTN_CREATE_RIG,
            _IDs.BTN_EXECUTE,
            _IDs.BTN_COLMAP_ONLY,
            _IDs.BTN_CLOSE,
            _IDs.OUTPUT_PATH_BROWSE,
        }
        if cid in skip_ids:
            return
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        obj = self._resolve_target_object(doc)
        if obj is None:
            return
        self._target_obj = obj
        self._is_auto_updating = True
        try:
            self.SetString(_IDs.STATUS_TEXT, "Auto-updating rig…")
            create_or_update_rig(doc, self._settings, obj)
        except Exception:
            # Keep auto-update silent to avoid interrupting slider/field edits.
            pass
        finally:
            self._is_auto_updating = False

    def _update_intrinsics_ui(self):
        manual_intrinsics_enabled = not bool(self.GetBool(_IDs.AUTO_INTRINSICS))
        for cid in [_IDs.FX, _IDs.FY, _IDs.CX, _IDs.CY]:
            try:
                self.Enable(cid, manual_intrinsics_enabled)
            except Exception:
                pass

    def _update_center_offset_ui(self):
        offsets_enabled = int(self.GetInt32(_IDs.CENTER_MODE)) == 0
        for cid in [3002, _IDs.CENTER_X, 3003, _IDs.CENTER_Y, 3004, _IDs.CENTER_Z]:
            try:
                self.Enable(cid, offsets_enabled)
            except Exception:
                pass

    def _resolve_target_object(self, doc):
        link_obj = self._get_link_target(doc)

        for candidate in [link_obj, self._target_obj]:
            if candidate is not None:
                return candidate
        return None

    def _get_link_target(self, doc):
        # Prefer the explicit LinkBox GUI object; GeDialog.GetLink can be
        # unreliable across C4D versions for custom link boxes.
        if self._target_link_gui is not None:
            gui_get = getattr(self._target_link_gui, "GetLink", None)
            if callable(gui_get):
                link_args = []
                obase = getattr(c4d, "Obase", None)
                if doc is not None and obase is not None:
                    link_args.append((doc, obase))
                if doc is not None:
                    link_args.append((doc, getattr(c4d, "BaseObject", None)))
                    link_args.append((doc, getattr(c4d, "BaseList2D", None)))
                link_args.append(tuple())

                for args in link_args:
                    if len(args) == 2 and args[1] is None:
                        continue
                    try:
                        obj = gui_get(*args)
                    except Exception:
                        obj = None
                    if obj is not None:
                        return obj

        for arg in [doc, getattr(c4d, "BaseObject", None), getattr(c4d, "BaseList2D", None)]:
            if arg is None:
                continue
            try:
                obj = self.GetLink(_IDs.TARGET_LINK, arg)
            except Exception:
                obj = None
            if obj is not None:
                return obj
        return None

    def _set_link_target(self, obj):
        if obj is None:
            return
        if self._target_link_gui is not None:
            gui_set = getattr(self._target_link_gui, "SetLink", None)
            if callable(gui_set):
                try:
                    gui_set(obj)
                    return
                except Exception:
                    pass
        try:
            self.SetLink(_IDs.TARGET_LINK, obj)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def Command(self, cid, msg):
        if cid == _IDs.TARGET_LINK:
            doc = c4d.documents.GetActiveDocument()
            link_obj = self._get_link_target(doc)
            if link_obj is not None:
                self._target_obj = link_obj
                if self._values_ready:
                    self._read_ui()
                    _save_settings(self._settings)
            self._refresh_status()
            return True

        if cid == _IDs.OUTPUT_PATH_BROWSE:
            picked = c4d.storage.LoadDialog(
                flags=c4d.FILESELECT_DIRECTORY,
                title="Select Export Output Path",
            )
            if picked:
                self.SetString(_IDs.OUTPUT_PATH, _normalize_path(picked))
                if self._values_ready:
                    self._read_ui()
                    _save_settings(self._settings)
            return True

        if cid == _IDs.BTN_CREATE_RIG:
            self._read_ui()
            doc = c4d.documents.GetActiveDocument()
            if doc is None:
                show_error_dialog(ERROR_NO_DOCUMENT, "No active Cinema 4D document.")
                return True
            obj = self._resolve_target_object(doc)
            if obj is None:
                show_error_dialog(
                    ERROR_NO_TARGET,
                    "No target object selected.",
                    "Assign a target in the Target Object field in the dialog."
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Creating rig…")
            try:
                result = create_or_update_rig(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                c4d.gui.MessageDialog(
                    "Camera rig ready.\n\n"
                    "Object:  {}\n"
                    "Cameras: {}\n"
                    "Mode:    {}\n\n"
                    "Tip: tweak parameters and click Create / Update Rig again to iterate quickly.".format(
                        result.get("target_name", "?"),
                        result.get("camera_count", 0),
                        result.get("mode", "?"),
                    )
                )
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_BUILD_FAILED, "Rig creation failed.", exc)
            return True

        if cid == _IDs.BTN_EXECUTE:
            self._read_ui()
            doc = c4d.documents.GetActiveDocument()
            if doc is None:
                show_error_dialog(ERROR_NO_DOCUMENT, "No active Cinema 4D document.")
                return True
            obj = self._resolve_target_object(doc)
            if obj is None:
                show_error_dialog(
                    ERROR_NO_TARGET,
                    "No target object selected.",
                    "Assign a target in the Target Object field in the dialog."
                )
                return True
            if not str(self._settings.output_path).strip():
                show_error_dialog(
                    ERROR_NO_OUTPUT_PATH,
                    "Output Path is empty.",
                    "Choose a folder such as C:\\renders\\my_splat before building."
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Working…")
            try:
                result = run_pipeline(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                self._show_success_dialog(result)
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_BUILD_FAILED, "Build failed.", exc)
            return True

        if cid == _IDs.BTN_COLMAP_ONLY:
            self._read_ui()
            doc = c4d.documents.GetActiveDocument()
            if doc is None:
                show_error_dialog(ERROR_NO_DOCUMENT, "No active Cinema 4D document.")
                return True
            obj = self._resolve_target_object(doc)
            if obj is None:
                show_error_dialog(
                    ERROR_NO_TARGET,
                    "No target object selected.",
                    "Assign a target in the Target Object field in the dialog."
                )
                return True
            if not str(self._settings.output_path).strip():
                show_error_dialog(
                    ERROR_NO_OUTPUT_PATH,
                    "Output Path is empty.",
                    "Choose a folder such as C:\\renders\\my_splat before exporting COLMAP."
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Exporting COLMAP…")
            try:
                result = run_colmap_only(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                c4d.gui.MessageDialog(
                    "COLMAP export complete.\n\n"
                    "Folder:  {}\n"
                    "Points:  {}\n"
                    "Intrinsics source:  {}\n"
                    "Images folder:  {}".format(
                        result["dir"],
                        result["points_count"],
                        result["intrinsics_source"],
                        result.get("images_dir", os.path.join(result["dir"], "images")),
                    )
                )
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_COLMAP_FAILED, "COLMAP export failed.", exc)
            return True

        if cid == _IDs.BTN_CLOSE:
            if self._values_ready:
                self._read_ui()
                _save_settings(self._settings)
            self.Close()
            return True

        # Refresh status on any field change
        if not self._values_ready:
            return True
        self._read_ui()
        _save_settings(self._settings)
        self._try_auto_update_rig(cid)
        self._update_center_offset_ui()
        self._update_intrinsics_ui()
        self._refresh_status()
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _show_success_dialog(result):
        colmap = result.get("colmap")
        pose_file = result.get("pose_file")
        mode = result.get("mode", "?")
        extra = result.get("mode_extra", 0)
        extra_str = ""
        if mode == "icosphere" and extra:
            extra_str = " (subdivisions: {})".format(extra)
        elif mode == "spiral":
            extra_str = ""

        msg_lines = [
            "Dataset ready for Postshot!",
            "",
            "Object:   {}".format(result.get("target_name", "?")),
            "Cameras:  {}  ({}{})".format(result.get("camera_count", 0), mode, extra_str),
            "",
        ]
        if pose_file and not str(pose_file).startswith("ERROR"):
            msg_lines.append("Pose JSON:  {}".format(pose_file))
        if colmap:
            msg_lines += [
                "COLMAP folder:  {}".format(colmap["dir"]),
                "Images folder:  {}".format(colmap.get("images_dir", os.path.join(colmap["dir"], "images"))),
                "Sparse points:  {}".format(colmap["points_count"]),
                "Intrinsics:     {}".format(colmap["intrinsics_source"]),
            ]
        msg_lines += [
            "",
            "Next step:  render the animation to produce the image sequence,",
            "then import the COLMAP folder into Postshot.",
        ]
        c4d.gui.MessageDialog("\n".join(msg_lines))


# ---------------------------------------------------------------------------
# CommandData plugin class
# ---------------------------------------------------------------------------

class C4D2GSCommand(c4d.plugins.CommandData):

    def __init__(self):
        self._dialog = None

    def Execute(self, doc):
        self._ensure_dialog()
        if not self._dialog.IsOpen():
            self._dialog.Open(
                dlgtype=c4d.DLG_TYPE_ASYNC,
                pluginid=PLUGIN_ID,
                defaultw=520,
                defaulth=680,
            )
        return True

    def RestoreLayout(self, sec_ref):
        self._ensure_dialog()
        return self._dialog.Restore(pluginid=PLUGIN_ID, secret=sec_ref)

    def _ensure_dialog(self):
        if self._dialog is None:
            self._dialog = C4D2GSDialog()


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str=PLUGIN_NAME,
        info=0,
        icon=None,
        help=PLUGIN_HELP,
        dat=C4D2GSCommand(),
    )
