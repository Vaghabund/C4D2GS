"""
C4D2GS — Math and geometry helpers.

Pure computational functions: sphere-point generation, vector / matrix
arithmetic, COLMAP coordinate conversion, and icosphere subdivision.
No other c4d2gs sub-module is imported here.
"""

import c4d
import math

from _constants import NUMERIC_CLEAN_EPS


# ---------------------------------------------------------------------------
# Sphere-point sampling
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
# Vector / matrix helpers
# ---------------------------------------------------------------------------

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


def _copy_matrix(mg):
    out = c4d.Matrix()
    out.off = c4d.Vector(mg.off.x, mg.off.y, mg.off.z)
    out.v1 = c4d.Vector(mg.v1.x, mg.v1.y, mg.v1.z)
    out.v2 = c4d.Vector(mg.v2.x, mg.v2.y, mg.v2.z)
    out.v3 = c4d.Vector(mg.v3.x, mg.v3.y, mg.v3.z)
    return out


def nerf_matrix_to_rows(mg):
    rows = matrix_to_rows(mg)
    # Convert the C4D camera-to-world basis to the NeRF/OpenGL convention
    # expected by nerfstudio/instant-ngp by flipping the Y and Z axes.
    for row in rows[:3]:
        row[1] *= -1.0
        row[2] *= -1.0
    return rows


# ---------------------------------------------------------------------------
# Numeric cleanup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Observation capping
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# COLMAP coordinate conversion
# ---------------------------------------------------------------------------

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
    # Match the published COLMAP importer: two Y flips (world and camera-local), no Z flip.
    # Steps (invert importer):
    #   1) Undo camera-local flip: mg1 = mg * diag(1, -1, 1)
    #   2) Undo world flip:      mg2 = diag(1, -1, 1) * mg1 (apply to basis + position)
    #   3) mg2 is COLMAP c2w; R_w2c = transpose(mg2); t = -R * C
    flip_y = c4d.Matrix()
    flip_y.v1 = c4d.Vector(1, 0, 0)
    flip_y.v2 = c4d.Vector(0,-1, 0)
    flip_y.v3 = c4d.Vector(0, 0, 1)
    flip_y.off = c4d.Vector(0, 0, 0)

    mg1 = mg * flip_y  # undo camera-local Y flip

    def _apply_flip_y(mat):
        out = c4d.Matrix()
        out.v1 = c4d.Vector(mat.v1.x, -mat.v1.y, mat.v1.z)
        out.v2 = c4d.Vector(mat.v2.x, -mat.v2.y, mat.v2.z)
        out.v3 = c4d.Vector(mat.v3.x, -mat.v3.y, mat.v3.z)
        out.off = c4d.Vector(mat.off.x, -mat.off.y, mat.off.z)
        return out

    mg2 = _apply_flip_y(mg1)  # undo world Y flip

    c_pos = mg2.off
    r_w2c = [
        [mg2.v1.x, mg2.v1.y, mg2.v1.z],
        [mg2.v2.x, mg2.v2.y, mg2.v2.z],
        [mg2.v3.x, mg2.v3.y, mg2.v3.z],
    ]
    tx = -(r_w2c[0][0] * c_pos.x + r_w2c[0][1] * c_pos.y + r_w2c[0][2] * c_pos.z)
    ty = -(r_w2c[1][0] * c_pos.x + r_w2c[1][1] * c_pos.y + r_w2c[1][2] * c_pos.z)
    tz = -(r_w2c[2][0] * c_pos.x + r_w2c[2][1] * c_pos.y + r_w2c[2][2] * c_pos.z)
    qw, qx, qy, qz = rotation_matrix_to_quaternion(r_w2c)

    return (qw, qx, qy, qz), (tx, ty, tz), r_w2c


def project_world_to_image(mg, world_point, world_normal, fx, fy, cx, cy,
                           require_front_facing=True):
    # Mirror importer pipeline (invert two Y flips, no Z flip) for projection.
    flip_y = c4d.Matrix()
    flip_y.v1 = c4d.Vector(1, 0, 0)
    flip_y.v2 = c4d.Vector(0, -1, 0)
    flip_y.v3 = c4d.Vector(0, 0, 1)
    flip_y.off = c4d.Vector(0, 0, 0)

    def _apply_flip_y_vec(v):
        return c4d.Vector(v.x, -v.y, v.z)

    def _apply_flip_y_mat(mat):
        out = c4d.Matrix()
        out.v1 = c4d.Vector(mat.v1.x, -mat.v1.y, mat.v1.z)
        out.v2 = c4d.Vector(mat.v2.x, -mat.v2.y, mat.v2.z)
        out.v3 = c4d.Vector(mat.v3.x, -mat.v3.y, mat.v3.z)
        out.off = c4d.Vector(mat.off.x, -mat.off.y, mat.off.z)
        return out

    mg1 = mg * flip_y
    mg2 = _apply_flip_y_mat(mg1)  # c2w in COLMAP frame

    p_col = _apply_flip_y_vec(world_point)  # world → COLMAP
    if world_normal is not None:
        n_col = _apply_flip_y_vec(world_normal)
        if require_front_facing:
            to_cam_col = _normalize(mg2.off - p_col)
            if _dot(to_cam_col, n_col) <= 0.0:
                return None

    local = (~mg2) * p_col
    x_cv = local.x
    y_cv = local.y  # already Y-down from flip
    z_cv = local.z  # forward
    if z_cv <= 1e-6:
        return None
    return (fx * (x_cv / z_cv)) + cx, (fy * (y_cv / z_cv)) + cy


# ---------------------------------------------------------------------------
# Camera matrix evaluation
# ---------------------------------------------------------------------------

def _camera_matrices_for_export(doc, render_cam, frame_count, fps):
    """Return evaluated camera global matrices for each export frame.

    This keeps exported poses aligned with Cinema 4D's actual target-tag
    evaluation used during rendering.
    """
    if doc is None or render_cam is None or frame_count <= 0:
        return None

    current_time = doc.GetTime()
    out = []
    try:
        for frame in range(frame_count):
            doc.SetTime(c4d.BaseTime(frame, fps))
            try:
                doc.ExecutePasses(None, True, True, True, getattr(c4d, "BUILDFLAGS_NONE", 0))
            except Exception:
                pass
            out.append(_copy_matrix(render_cam.GetMg()))
    finally:
        doc.SetTime(current_time)
        try:
            doc.ExecutePasses(None, True, True, True, getattr(c4d, "BUILDFLAGS_NONE", 0))
        except Exception:
            pass

    if len(out) != frame_count:
        return None
    return out
