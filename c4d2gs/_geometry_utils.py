"""
C4D2GS — Object and mesh geometry helpers.

Functions for computing object centres, navigating the C4D object hierarchy,
converting objects to polygons, and generating sparse point clouds used for
synthetic COLMAP track generation.
"""

import c4d
import math
import random
import bisect

from _math_utils import _normalize, _cross, _dot


# ---------------------------------------------------------------------------
# Object centre helpers
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


# ---------------------------------------------------------------------------
# Object naming helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Object hierarchy traversal
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Object-to-polygon conversion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Triangle / surface sampling
# ---------------------------------------------------------------------------

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


def generate_sparse_points_in_core_volume(target_obj, target_pos, count=256,
                                          radius_factor=0.35):
    """Fallback sparse points sampled inside a core sphere of the target bounds."""
    if target_obj is None:
        return None
    count = max(8, int(count))
    try:
        base_radius = max(1.0, float(get_object_bounding_radius(target_obj)))
    except Exception:
        base_radius = 100.0

    core_radius = max(1.0, base_radius * max(0.05, float(radius_factor)))
    out = []
    for _ in range(count):
        # Uniform sample in sphere volume.
        u = random.random()
        v = random.random()
        w = random.random()
        theta = 2.0 * math.pi * u
        phi = math.acos(max(-1.0, min(1.0, 2.0 * v - 1.0)))
        r = core_radius * (w ** (1.0 / 3.0))
        sx = r * math.sin(phi) * math.cos(theta)
        sy = r * math.cos(phi)
        sz = r * math.sin(phi) * math.sin(theta)
        out.append((target_pos + c4d.Vector(sx, sy, sz), None))
    return out
