import c4d
import math
import json
import os
import random
import bisect

# -------------------------------
# User settings
# -------------------------------
CAMERA_COUNT = 120
SPHERE_RADIUS = 300.0
SPHERE_CENTER_OFFSET = c4d.Vector(0, 0, 0)
SAMPLING_MODE = "spiral"  # "spiral", "icosphere", or "fibonacci"
SPIRAL_TURNS = 6.0
SPIRAL_POLE_MARGIN = 0.06  # 0..0.49, avoids exact poles for cleaner reconstruction

# Output settings for Render Settings (Save)
OUTPUT_PATH = r"C:\temp\gs_capture\gs_####"
OUTPUT_FORMAT = c4d.FILTER_PNG
RESOLUTION_X = 1920
RESOLUTION_Y = 1080
FPS = 30

# If True, creates one animated camera that visits every generated viewpoint,
# so rendering an animation outputs one image per viewpoint.
CREATE_ANIMATED_RENDER_CAMERA = True
REPLACE_EXISTING_RIG = True
EXPORT_CAMERA_POSES = True
CAMERA_POSE_OUTPUT_PATH = r"C:\temp\gs_capture\camera_poses.json"
EXPORT_POSTSHOT_COLMAP = True
COLMAP_SUBFOLDER_NAME = "postshot_colmap"
AUTO_COLMAP_INTRINSICS_FROM_RENDER_CAMERA = True
COLMAP_MODEL = "PINHOLE"  # SIMPLE_PINHOLE or PINHOLE
COLMAP_FX_PX = 1500.0
COLMAP_FY_PX = 1500.0
COLMAP_CX_PX = RESOLUTION_X * 0.5
COLMAP_CY_PX = RESOLUTION_Y * 0.5
COLMAP_SPARSE_POINT_COUNT = 256
COLMAP_SPARSE_POINT_RADIUS_FACTOR = 0.35
OPEN_UI_ON_RUN = True
_HAS_RUN = False
_DIALOG_INSTANCE = None
TARGET_OBJECT_LINK = None


def fibonacci_sphere_points(count):
    if count <= 0:
        return []

    points = []
    golden_angle = 3.141592653589793 * (3.0 - 5.0 ** 0.5)

    for i in range(count):
        y = 1.0 - (2.0 * i) / float(max(1, count - 1))
        radius = max(0.0, 1.0 - y * y) ** 0.5
        theta = golden_angle * i
        x = math.sin(theta) * radius
        z = math.cos(theta) * radius
        points.append(c4d.Vector(x, y, z))

    return points


def spiral_sphere_points(count, turns=6.0, pole_margin=0.06):
    if count <= 0:
        return []
    if count == 1:
        return [c4d.Vector(0, 1, 0)]

    margin = max(0.0, min(0.49, float(pole_margin)))
    y_top = 1.0 - (2.0 * margin)
    y_bottom = -y_top

    points = []
    for i in range(count):
        t = i / float(count - 1)
        y = y_top + (y_bottom - y_top) * t
        ring_r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = (2.0 * math.pi * turns) * t
        x = math.cos(theta) * ring_r
        z = math.sin(theta) * ring_r
        points.append(c4d.Vector(x, y, z))

    return points


def _normalize(v):
    l = math.sqrt((v.x * v.x) + (v.y * v.y) + (v.z * v.z))
    if l <= 0.0:
        return c4d.Vector(0, 1, 0)
    return c4d.Vector(v.x / l, v.y / l, v.z / l)


def _cross(a, b):
    return c4d.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _dot(a, b):
    return (a.x * b.x) + (a.y * b.y) + (a.z * b.z)


def look_at_matrix(camera_pos, target_pos, up_hint=None):
    # C4D cameras look down local -Z. Therefore local +Z points away from target.
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


def get_output_extension():
    ext_map = {}
    known = [
        ("FILTER_PNG", ".png"),
        ("FILTER_JPG", ".jpg"),
        ("FILTER_TIF", ".tif"),
        ("FILTER_B3D", ".b3d"),
        ("FILTER_EXR", ".exr"),
        ("FILTER_PSD", ".psd"),
        ("FILTER_PSB", ".psb"),
    ]
    for name, ext in known:
        value = getattr(c4d, name, None)
        if value is not None:
            ext_map[value] = ext
    return ext_map.get(OUTPUT_FORMAT, ".png")


def build_frame_image_path(frame_index):
    token = "{:04d}".format(frame_index)
    if "####" in OUTPUT_PATH:
        base = OUTPUT_PATH.replace("####", token)
    else:
        base = "{}_{}".format(OUTPUT_PATH, token)

    ext = get_output_extension()
    if base.lower().endswith(ext.lower()):
        return base
    return base + ext


def get_render_output_directory():
    path = str(OUTPUT_PATH).strip()
    if not path:
        return ""

    # OUTPUT_PATH usually points to a filename pattern like ...\gs_####.
    if os.path.isdir(path):
        return path
    return os.path.dirname(path)


def resolve_colmap_output_dir():
    render_dir = get_render_output_directory()
    sub = COLMAP_SUBFOLDER_NAME.strip() or "postshot_colmap"
    if render_dir:
        return os.path.join(render_dir, sub)

    fallback_base = os.path.join(os.path.expanduser("~"), "Documents", "gs_capture")
    return os.path.join(fallback_base, sub)


def normalize_output_dir(path):
    p = str(path).strip()
    p = os.path.expandvars(os.path.expanduser(p))
    if not p:
        return ""
    p = os.path.normpath(p)
    if not os.path.isabs(p):
        p = os.path.abspath(p)
    return p


def write_colmap_debug_report(output_dir, lines):
    report_path = os.path.join(output_dir, "colmap_export_debug.txt")
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return report_path


def matrix_to_rows(mg):
    # 4x4 row-major matrix for easier downstream parsing.
    return [
        [mg.v1.x, mg.v2.x, mg.v3.x, mg.off.x],
        [mg.v1.y, mg.v2.y, mg.v3.y, mg.off.y],
        [mg.v1.z, mg.v2.z, mg.v3.z, mg.off.z],
        [0.0, 0.0, 0.0, 1.0],
    ]


def rotation_matrix_to_quaternion(r):
    # Returns quaternion as (qw, qx, qy, qz).
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (r[2][1] - r[1][2]) / s
        qy = (r[0][2] - r[2][0]) / s
        qz = (r[1][0] - r[0][1]) / s
    elif (r[0][0] > r[1][1]) and (r[0][0] > r[2][2]):
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2.0
        qw = (r[2][1] - r[1][2]) / s
        qx = 0.25 * s
        qy = (r[0][1] + r[1][0]) / s
        qz = (r[0][2] + r[2][0]) / s
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2.0
        qw = (r[0][2] - r[2][0]) / s
        qx = (r[0][1] + r[1][0]) / s
        qy = 0.25 * s
        qz = (r[1][2] + r[2][1]) / s
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2.0
        qw = (r[1][0] - r[0][1]) / s
        qx = (r[0][2] + r[2][0]) / s
        qy = (r[1][2] + r[2][1]) / s
        qz = 0.25 * s
    return qw, qx, qy, qz


def camera_center_and_axes_from_matrix(mg):
    c = mg.off
    # C4D camera local axes in world space (camera-to-world basis as columns).
    xw = mg.v1
    yw = mg.v2
    zw = mg.v3
    return c, xw, yw, zw


def c2w_to_colmap_extrinsics(mg):
    c, xw, yw, zw = camera_center_and_axes_from_matrix(mg)

    # C4D camera local frame: +X right, +Y up, +Z backward.
    # COLMAP/OpenCV camera frame: +X right, +Y down, +Z forward.
    # Convert by applying S = diag(1, -1, -1) to the camera-space rows,
    # i.e. negate the Y and Z rows of R_w2c.
    r_w2c = [
        [ xw.x,  xw.y,  xw.z],
        [-yw.x, -yw.y, -yw.z],
        [-zw.x, -zw.y, -zw.z],
    ]

    qw, qx, qy, qz = rotation_matrix_to_quaternion(r_w2c)

    tx = -(r_w2c[0][0] * c.x + r_w2c[0][1] * c.y + r_w2c[0][2] * c.z)
    ty = -(r_w2c[1][0] * c.x + r_w2c[1][1] * c.y + r_w2c[1][2] * c.z)
    tz = -(r_w2c[2][0] * c.x + r_w2c[2][1] * c.y + r_w2c[2][2] * c.z)

    return (qw, qx, qy, qz), (tx, ty, tz), r_w2c


def world_to_camera_point(r_w2c, t_w2c, world_point):
    x = world_point.x
    y = world_point.y
    z = world_point.z
    xc = (r_w2c[0][0] * x) + (r_w2c[0][1] * y) + (r_w2c[0][2] * z) + t_w2c[0]
    yc = (r_w2c[1][0] * x) + (r_w2c[1][1] * y) + (r_w2c[1][2] * z) + t_w2c[1]
    zc = (r_w2c[2][0] * x) + (r_w2c[2][1] * y) + (r_w2c[2][2] * z) + t_w2c[2]
    return xc, yc, zc


def project_world_to_image_from_camera_matrix(mg, world_point, fx, fy, cx, cy):
    local = (~mg) * world_point
    # C4D camera looks down -Z, so points in front have negative local z.
    if local.z >= -1e-6:
        return None

    depth = -local.z
    u = (fx * (local.x / depth)) + cx
    # C4D camera Y is up; COLMAP/image Y is down — negate local.y.
    v = (fy * (-local.y / depth)) + cy
    return u, v


def get_target_object(doc, target_obj_override=None):
    if target_obj_override is not None and isinstance(target_obj_override, c4d.BaseObject):
        return target_obj_override
    if TARGET_OBJECT_LINK is not None and isinstance(TARGET_OBJECT_LINK, c4d.BaseObject):
        return TARGET_OBJECT_LINK
    return doc.GetActiveObject()


def iter_hierarchy(op, include_siblings=True):
    node = op
    while node:
        yield node
        child = node.GetDown()
        if child:
            for sub in iter_hierarchy(child, include_siblings=True):
                yield sub
        if include_siblings:
            node = node.GetNext()
        else:
            node = None


def iter_cache_hierarchy(op):
    if op is None:
        return

    # Yield the node itself.
    yield op

    # Walk deform/cache trees and regular children.
    deform = op.GetDeformCache()
    if deform is not None:
        for sub in iter_hierarchy(deform, include_siblings=True):
            yield sub

    cache = op.GetCache()
    if cache is not None:
        for sub in iter_hierarchy(cache, include_siblings=True):
            yield sub

    child = op.GetDown()
    if child is not None:
        for sub in iter_hierarchy(child, include_siblings=True):
            yield sub


def GetNextObjectOnlyDown(parent, op):
    """Get the next object only if it is a sibling or child of parent. (Adapted from Eric Eastwood)"""
    if (op is None) or (parent is None):
        return None

    # If there are children, go to the first child
    if op.GetDown():
        return op.GetDown()

    if op == parent:
        return None

    # If there is no next object and there is parent that is not the overarching parent, then go to the parent
    while not op.GetNext() and op.GetUp() and op.GetUp() != parent:
        op = op.GetUp()

    # Return the next object
    return op.GetNext()


def GetSiblingObjectOnlyDown(parent, op):
    """Get the next sibling only if inside of parent. (Adapted from Eric Eastwood)"""
    if (op is None) or (parent is None):
        return None

    # If there is not `next` then go up (then try to go down) until we can. Stops at parent
    while not op.GetNext() and op.GetUp() and op.GetUp() != parent:
        op = op.GetUp()
        if op == parent:
            return None

    if op == parent:
        return None

    # Return the next object
    return op.GetNext()


def MakeEditable(op):
    """Bake an object to editable polygonal/spline form. (Adapted from Eric Eastwood)"""
    if (not op) or op.CheckType(c4d.Opolygon) or op.CheckType(c4d.Ospline):
        return op

    doc = c4d.documents.BaseDocument()

    clone = op.GetClone()
    doc.InsertObject(clone, None, None)
    clone.SetMg(op.GetMg())  # Set the clone at the same position as the object was before

    try:
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_MAKEEDITABLE,
            list=[clone],
            mode=c4d.MODELINGCOMMANDMODE_ALL,
            doc=doc
        )
    except Exception:
        return None

    if result:
        return result[0]
    else:
        return None


def GetPointsFromCloner(clonerObject):
    """Extract and transform all points from a cloner's instances. (Adapted from Eric Eastwood)"""
    try:
        moData = c4d.modules.mograph.GeGetMoData(clonerObject)
        if not moData:
            return []
    except Exception:
        return []

    moCount = moData.GetCount()
    if moCount <= 0:
        return []

    try:
        moMatrixArray = moData.GetArray(c4d.MODATA_MATRIX)
        moCloneArray = moData.GetArray(c4d.MODATA_CLONE)
    except Exception:
        return []

    # Assemble list of points for each object in the cloner
    myobject = clonerObject.GetDown()
    if myobject is None:
        return []

    clonePointList = []
    numObjectsInHierarchy = 0

    while myobject:
        fixedClone = False
        if clonerObject[c4d.MGCLONER_FIX_CLONES]:
            fixedClone = True

        # Make the `Transform` tab matrix
        clonerTransormMatrix = (
            c4d.utils.MatrixMove(clonerObject[c4d.ID_MG_TRANSFORM_POSITION])
            * c4d.utils.MatrixScale(clonerObject[c4d.ID_MG_TRANSFORM_SCALE])
            * c4d.utils.HPBToMatrix(clonerObject[c4d.ID_MG_TRANSFORM_ROTATE])
        )
        # Apply the `Transform` tab matrix and the cloner object Matrix itself
        adjusted_objectpoints = [
            (clonerObject.GetMg() if fixedClone else c4d.Matrix()) * clonerTransormMatrix * x
            for x in GetAllPointsFromObjectForCloner(myobject, not fixedClone)
        ]
        clonePointList.append(adjusted_objectpoints)

        numObjectsInHierarchy += 1
        myobject = myobject.GetNext()

    # Now assemble the final point list
    pointList = []

    for cloneIndex in range(0, moCount):
        # Find what index we need from the cloner clone array
        if moCloneArray[cloneIndex] == 0:
            clonePointListIndex = 0
        else:
            clonePointListIndex = int(math.ceil(moCloneArray[cloneIndex] / (float(1) / numObjectsInHierarchy))) - 1

        # Apply the matrix that the cloner puts on this clone
        if clonePointListIndex < len(clonePointList):
            adjusted_allpoints = [moMatrixArray[cloneIndex] * x for x in clonePointList[clonePointListIndex]]
            pointList.extend(adjusted_allpoints)

    return pointList


def GetAllPointsFromObjectForCloner(op, includeObjectMatrix=True):
    """Recursively collect all points from an object and children. (Adapted from Eric Eastwood)"""
    pointList = []
    myobject = op

    while myobject:
        if myobject.GetTypeName() == "Cloner":
            pointList.extend(GetPointsFromCloner(myobject))
            myobject = GetSiblingObjectOnlyDown(op, myobject)
        else:
            editable_myobject = MakeEditable(myobject)
            if editable_myobject and isinstance(editable_myobject, c4d.PointObject):
                if includeObjectMatrix:
                    myobject_pos = editable_myobject.GetMg()
                    adjusted_allpoints = [myobject_pos * x for x in editable_myobject.GetAllPoints()]
                    pointList.extend(adjusted_allpoints)
                else:
                    pointList.extend(editable_myobject.GetAllPoints())

            myobject = GetNextObjectOnlyDown(op, myobject)

    return pointList


def get_current_state_object(doc, obj):
    """Bake object to current state. Simplified wrapper for MakeEditable pattern."""
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

    if not result:
        return None
    return result[0]


def collect_world_triangles_from_object(root_obj):
    """Collect all triangles from object, including cloners and deformers."""
    triangles = []

    # First, handle the main object and its caches/deformers
    for obj in iter_cache_hierarchy(root_obj):
        if obj.CheckType(c4d.Opolygon):
            mg = obj.GetMg()
            points = obj.GetAllPoints()
            if points:
                world_points = [p * mg for p in points]
                polys = obj.GetAllPolygons()
                for poly in polys:
                    a = world_points[poly.a]
                    b = world_points[poly.b]
                    c = world_points[poly.c]
                    d = world_points[poly.d]
                    triangles.append((a, b, c))
                    if poly.c != poly.d:
                        triangles.append((a, c, d))

    # Handle children using robust hierarchy traversal
    child = root_obj.GetDown()
    while child:
        if child.GetTypeName() == "Cloner":
            # For cloners, extract their transformed instances and collect points
            try:
                clone_points = GetPointsFromCloner(child)
                if clone_points:
                    # Create virtual "triangles" from point pairs (fallback for point-cloud cloners)
                    for i in range(0, len(clone_points) - 1):
                        # This is a heuristic; ideally we'd bake the cloner content
                        pass  # Skip cloner-only point clouds; rely on baked state
            except Exception:
                pass
        else:
            # Recursively collect from children
            for sub_tri in collect_world_triangles_from_object(child):
                triangles.append(sub_tri)

        child = child.GetNext()

    return triangles


def triangle_area(a, b, c):
    return ((_cross(b - a, c - a)).GetLength()) * 0.5


def sample_point_on_triangle(a, b, c):
    # Uniform sampling on a triangle surface.
    r1 = random.random()
    r2 = random.random()
    s1 = math.sqrt(r1)
    wa = 1.0 - s1
    wb = s1 * (1.0 - r2)
    wc = s1 * r2
    return (a * wa) + (b * wb) + (c * wc)


def generate_sparse_points_from_object_surface(doc, target_obj):
    """Generate sparse points by area-weighted sampling from object surface triangles."""
    count = max(8, int(COLMAP_SPARSE_POINT_COUNT))
    triangles = []

    # Try baking with robust MakeEditable first
    try:
        baked = MakeEditable(target_obj)
        if baked is not None:
            triangles = collect_world_triangles_from_object(baked)
    except Exception:
        pass

    # Fallback to Current State To Object
    if not triangles:
        try:
            baked = get_current_state_object(doc, target_obj)
            if baked is not None:
                triangles = collect_world_triangles_from_object(baked)
        except Exception:
            pass

    # Fallback to direct object geometry/caches
    if not triangles:
        triangles = collect_world_triangles_from_object(target_obj)

    if not triangles:
        return None

    areas = []
    cumulative = []
    running = 0.0
    for tri in triangles:
        ar = triangle_area(tri[0], tri[1], tri[2])
        if ar <= 1e-12:
            continue
        areas.append((tri, ar))
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
        tri = areas[idx][0]
        out.append(sample_point_on_triangle(tri[0], tri[1], tri[2]))

    return out


def export_colmap_for_postshot(world_points, target_pos, output_dir, render_cam=None, doc=None, target_obj=None):
    if not world_points:
        return None

    output_dir = normalize_output_dir(output_dir)
    if not output_dir:
        raise ValueError("COLMAP output path is empty. Set a valid Render Output Path.")

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception as exc:
            raise ValueError("Could not create COLMAP output directory '{}': {}".format(output_dir, exc))

    cameras_txt = os.path.join(output_dir, "cameras.txt")
    images_txt = os.path.join(output_dir, "images.txt")
    points3d_txt = os.path.join(output_dir, "points3D.txt")

    intrinsics = get_colmap_intrinsics(render_cam)
    write_colmap_camera_file(cameras_txt, intrinsics)

    fx = float(intrinsics["fx"])
    fy = float(intrinsics["fy"])
    cx = float(intrinsics["cx"])
    cy = float(intrinsics["cy"])
    width = float(RESOLUTION_X)
    height = float(RESOLUTION_Y)

    if doc is None or target_obj is None:
        raise ValueError("True object-surface sparse points require an active document and selected target object.")

    sparse_points = generate_sparse_points_from_object_surface(doc, target_obj)
    if not sparse_points:
        raise ValueError(
            "Could not generate sparse points from the selected object surface. "
            "Make sure the selected object has polygonal geometry (or can be baked to polygons)."
        )

    points_source = "object_surface"

    image_entries = []
    for i, world_pos in enumerate(world_points):
        image_id = i + 1
        mg = look_at_matrix(world_pos, target_pos)
        q, t, r_w2c = c2w_to_colmap_extrinsics(mg)
        image_entries.append({
            "image_id": image_id,
            "name": os.path.basename(build_frame_image_path(i)),
            "q": q,
            "t": t,
            "r_w2c": r_w2c,
            "mg": mg,
            "obs": [],
        })

    # Build 2D observations and track lists for each sampled object-surface 3D point.
    tracks_by_pid = {}
    total_observations = 0
    for pid, p3d in enumerate(sparse_points, start=1):
        tracks_by_pid[pid] = []
        for entry in image_entries:
            projected = project_world_to_image_from_camera_matrix(entry["mg"], p3d, fx, fy, cx, cy)
            if projected is None:
                continue
            u, v = projected

            if u < 0.0 or u >= width or v < 0.0 or v >= height:
                continue

            point2d_idx = len(entry["obs"])
            entry["obs"].append((u, v, pid))
            tracks_by_pid[pid].append((entry["image_id"], point2d_idx))
            total_observations += 1

    with open(images_txt, "w") as f:
        f.write("# Image list with two lines of data per image:\n")
        f.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        f.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        f.write("# Number of images: {}\n".format(len(world_points)))

        for entry in image_entries:
            f.write("{} {} {} {} {} {} {} {} 1 {}\n".format(
                entry["image_id"],
                entry["q"][0], entry["q"][1], entry["q"][2], entry["q"][3],
                entry["t"][0], entry["t"][1], entry["t"][2],
                entry["name"],
            ))
            if entry["obs"]:
                line = " ".join(["{} {} {}".format(o[0], o[1], o[2]) for o in entry["obs"]])
                f.write(line + "\n")
            else:
                f.write("\n")

    valid_points = []
    for pid, p3d in enumerate(sparse_points, start=1):
        track = tracks_by_pid.get(pid, [])
        if len(track) < 2:
            continue
        valid_points.append((pid, p3d, track))

    if not valid_points:
        obs_per_point = [len(v) for v in tracks_by_pid.values()]
        at_least_1 = sum(1 for n in obs_per_point if n >= 1)
        at_least_2 = sum(1 for n in obs_per_point if n >= 2)
        debug_lines = [
            "COLMAP export debug",
            "source=object_surface",
            "sampled_points={}".format(len(sparse_points)),
            "total_observations={}".format(total_observations),
            "points_with_ge_1_obs={}".format(at_least_1),
            "points_with_ge_2_obs={}".format(at_least_2),
            "camera_count={}".format(len(world_points)),
            "resolution={}x{}".format(RESOLUTION_X, RESOLUTION_Y),
            "fx={} fy={} cx={} cy={}".format(fx, fy, cx, cy),
        ]
        report_path = write_colmap_debug_report(output_dir, debug_lines)
        raise ValueError(
            "No valid sparse point tracks could be built from object-surface points. "
            "Try increasing camera coverage or sparse point count. "
            "Debug report: {}".format(report_path)
        )

    with open(points3d_txt, "w") as f:
        f.write("# 3D point list with one line of data per point:\n")
        f.write("#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]\n")
        f.write("# Number of points: {}\n".format(len(valid_points)))
        for pid, p3d, track in valid_points:
            # Mirror the exported point cloud on world Z only.
            mirrored_z = -p3d.z
            track_flat = " ".join(["{} {}".format(img_id, p2d_idx) for img_id, p2d_idx in track])
            f.write("{} {} {} {} 255 255 255 1.0 {}\n".format(
                pid,
                p3d.x,
                p3d.y,
                mirrored_z,
                track_flat,
            ))

    # Marker file helps to quickly spot the output folder in Explorer.
    marker = os.path.join(output_dir, "_exported_by_gs_camera_setup.txt")
    with open(marker, "w") as f:
        f.write("COLMAP files exported by gs_splat_camera_setup.py\n")

    for required in [cameras_txt, images_txt, points3d_txt]:
        if not os.path.isfile(required):
            raise ValueError("Export finished but required file is missing: {}".format(required))

    obs_per_point = [len(v) for v in tracks_by_pid.values()]
    at_least_1 = sum(1 for n in obs_per_point if n >= 1)
    at_least_2 = sum(1 for n in obs_per_point if n >= 2)
    debug_lines = [
        "COLMAP export debug",
        "source=object_surface",
        "sampled_points={}".format(len(sparse_points)),
        "valid_points_written={}".format(len(valid_points)),
        "total_observations={}".format(total_observations),
        "points_with_ge_1_obs={}".format(at_least_1),
        "points_with_ge_2_obs={}".format(at_least_2),
        "camera_count={}".format(len(world_points)),
        "resolution={}x{}".format(RESOLUTION_X, RESOLUTION_Y),
        "fx={} fy={} cx={} cy={}".format(fx, fy, cx, cy),
    ]
    report_path = write_colmap_debug_report(output_dir, debug_lines)

    return {
        "dir": output_dir,
        "intrinsics_source": intrinsics.get("source", "manual"),
        "model": intrinsics.get("model", "PINHOLE"),
        "cameras_txt": cameras_txt,
        "images_txt": images_txt,
        "points3d_txt": points3d_txt,
        "points_count": len(valid_points),
        "points_source": points_source,
        "debug_report": report_path,
    }


def get_colmap_intrinsics_from_camera(render_cam):
    if render_cam is None:
        return None

    def get_param(pid):
        try:
            return render_cam[pid]
        except Exception:
            return None

    # Common C4D camera parameters (mm).
    focus_pid = getattr(c4d, "CAMERA_FOCUS", None)
    aperture_pid = getattr(c4d, "CAMERAOBJECT_APERTURE", None)

    if focus_pid is None or aperture_pid is None:
        return None

    focal_mm = get_param(focus_pid)
    aperture_w_mm = get_param(aperture_pid)
    if focal_mm is None or aperture_w_mm is None:
        return None

    try:
        focal_mm = float(focal_mm)
        aperture_w_mm = float(aperture_w_mm)
    except Exception:
        return None

    if focal_mm <= 0.0 or aperture_w_mm <= 0.0:
        return None

    # Derive aperture height from render aspect if no explicit sensor-height parameter is used.
    if RESOLUTION_X <= 0 or RESOLUTION_Y <= 0:
        return None
    aperture_h_mm = aperture_w_mm * (float(RESOLUTION_Y) / float(RESOLUTION_X))

    fx = (focal_mm / aperture_w_mm) * float(RESOLUTION_X)
    fy = (focal_mm / aperture_h_mm) * float(RESOLUTION_Y)
    cx = float(RESOLUTION_X) * 0.5
    cy = float(RESOLUTION_Y) * 0.5

    return {
        "model": "PINHOLE",
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "source": "render_camera",
    }


def get_colmap_intrinsics(render_cam):
    if AUTO_COLMAP_INTRINSICS_FROM_RENDER_CAMERA:
        auto_vals = get_colmap_intrinsics_from_camera(render_cam)
        if auto_vals is not None:
            return auto_vals

    return {
        "model": COLMAP_MODEL,
        "fx": float(COLMAP_FX_PX),
        "fy": float(COLMAP_FY_PX),
        "cx": float(COLMAP_CX_PX),
        "cy": float(COLMAP_CY_PX),
        "source": "manual",
    }


def write_colmap_camera_file(cameras_txt, intrinsics):
    with open(cameras_txt, "w") as f:
        f.write("# Camera list with one line of data per camera:\n")
        f.write("#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        f.write("# Number of cameras: 1\n")

        model = str(intrinsics["model"]).strip().upper()
        if model == "SIMPLE_PINHOLE":
            focal = float(intrinsics["fx"])
            f.write("1 SIMPLE_PINHOLE {} {} {} {} {}\n".format(
                int(RESOLUTION_X), int(RESOLUTION_Y), focal, float(intrinsics["cx"]), float(intrinsics["cy"])
            ))
        else:
            f.write("1 PINHOLE {} {} {} {} {} {}\n".format(
                int(RESOLUTION_X),
                int(RESOLUTION_Y),
                float(intrinsics["fx"]),
                float(intrinsics["fy"]),
                float(intrinsics["cx"]),
                float(intrinsics["cy"]),
            ))


def export_camera_poses(world_points, target_pos, output_path, render_cam=None):
    if not world_points:
        return None

    intrinsics = get_colmap_intrinsics(render_cam)
    fx = float(intrinsics["fx"])
    fy = float(intrinsics["fy"])
    cx = float(intrinsics["cx"])
    cy = float(intrinsics["cy"])
    w = int(RESOLUTION_X)
    h = int(RESOLUTION_Y)

    payload = {
        "coordinate_system": "Cinema4D_Yup_RightHanded",
        "camera_looks_along": "-Z",
        "camera_model": str(intrinsics["model"]).upper(),
        # Generic intrinsics keys.
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "width": w,
        "height": h,
        "focal_length": fx,
        # Common NeRF-style aliases.
        "fl_x": fx,
        "fl_y": fy,
        "w": w,
        "h": h,
        "frame_count": len(world_points),
        "frames": [],
    }

    for frame, world_pos in enumerate(world_points):
        mg = look_at_matrix(world_pos, target_pos)
        hpb = c4d.utils.MatrixToHPB(mg)

        payload["frames"].append({
            "frame": frame,
            "camera_name": "GS_Cam_{:04d}".format(frame + 1),
            "image_path": build_frame_image_path(frame),
            "position": [world_pos.x, world_pos.y, world_pos.z],
            "rotation_hpb_rad": [hpb.x, hpb.y, hpb.z],
            "transform_matrix": matrix_to_rows(mg),
            "fx": fx,
            "fy": fy,
            "cx": cx,
            "cy": cy,
            "focal_length": fx,
            "fl_x": fx,
            "fl_y": fy,
            "w": w,
            "h": h,
        })

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    return output_path


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


def _pick_icosphere_subdivisions(target_count):
    # Icosphere vertex counts are 10 * 4^n + 2.
    if target_count <= 12:
        return 0

    best_n = 0
    best_diff = abs(12 - target_count)
    n = 1
    while n <= 8:
        cnt = (10 * (4 ** n)) + 2
        diff = abs(cnt - target_count)
        if diff < best_diff:
            best_n = n
            best_diff = diff
        if cnt >= target_count and diff > best_diff:
            break
        n += 1

    return best_n


def icosphere_points_for_target(target_count):
    if target_count <= 0:
        return [], 0

    verts, faces = _icosahedron()
    subdivisions = _pick_icosphere_subdivisions(target_count)

    for _ in range(subdivisions):
        midpoint_cache = {}

        def get_midpoint_index(i1, i2):
            key = (i1, i2) if i1 < i2 else (i2, i1)
            cached = midpoint_cache.get(key)
            if cached is not None:
                return cached

            mid = _normalize((verts[i1] + verts[i2]) * 0.5)
            verts.append(mid)
            idx = len(verts) - 1
            midpoint_cache[key] = idx
            return idx

        new_faces = []
        for a, b, c in faces:
            ab = get_midpoint_index(a, b)
            bc = get_midpoint_index(b, c)
            ca = get_midpoint_index(c, a)

            new_faces.append((a, ab, ca))
            new_faces.append((b, bc, ab))
            new_faces.append((c, ca, bc))
            new_faces.append((ab, bc, ca))

        faces = new_faces

    return verts, subdivisions


def generate_unit_points(target_count):
    mode = SAMPLING_MODE.strip().lower()
    if mode == "spiral":
        points = spiral_sphere_points(target_count, SPIRAL_TURNS, SPIRAL_POLE_MARGIN)
        return points, "spiral", 0
    if mode == "fibonacci":
        return fibonacci_sphere_points(target_count), "fibonacci", 0

    points, subdivisions = icosphere_points_for_target(target_count)
    return points, "icosphere", subdivisions


def make_track(op, descid):
    track = op.FindCTrack(descid)
    if track is None:
        track = c4d.CTrack(op, descid)
        op.InsertTrackSorted(track)
    return track


def add_float_key(op, descid, time, value, interpolation=c4d.CINTERPOLATION_LINEAR):
    track = make_track(op, descid)
    curve = track.GetCurve()
    key_data = curve.AddKey(time)
    if not key_data:
        return
    key = key_data["key"]
    key.SetValue(curve, float(value))
    key.SetInterpolation(curve, interpolation)


def center_of_object(op):
    # Uses world matrix plus local center offset for a robust target position.
    return op.GetMg().off + op.GetMp()


def create_target_tag(cam, target):
    tag = c4d.BaseTag(c4d.Ttargetexpression)
    if tag is None:
        return
    tag[c4d.TARGETEXPRESSIONTAG_LINK] = target
    cam.InsertTag(tag)


def configure_render_settings(doc, render_cam, frame_count):
    rd = doc.GetActiveRenderData()
    if rd is None:
        return

    rd[c4d.RDATA_XRES] = RESOLUTION_X
    rd[c4d.RDATA_YRES] = RESOLUTION_Y
    rd[c4d.RDATA_FRAMERATE] = FPS

    rd[c4d.RDATA_SAVEIMAGE] = True
    rd[c4d.RDATA_PATH] = OUTPUT_PATH
    rd[c4d.RDATA_FORMAT] = OUTPUT_FORMAT

    rd[c4d.RDATA_FRAMESEQUENCE] = c4d.RDATA_FRAMESEQUENCE_ALLFRAMES
    rd[c4d.RDATA_FRAMEFROM] = c4d.BaseTime(0, FPS)
    rd[c4d.RDATA_FRAMETO] = c4d.BaseTime(max(0, frame_count - 1), FPS)

    if render_cam is not None:
        # `RDATA_CAMERA` is not available in all C4D versions.
        if hasattr(c4d, "RDATA_CAMERA"):
            rd[c4d.RDATA_CAMERA] = render_cam
        else:
            bd = doc.GetActiveBaseDraw()
            if bd is not None:
                bd.SetSceneCamera(render_cam)


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


def get_sampling_mode_items():
    return [(0, "spiral"), (1, "icosphere"), (2, "fibonacci")]


def get_output_format_items():
    items = []
    for label, const_name in [
        ("PNG", "FILTER_PNG"),
        ("JPG", "FILTER_JPG"),
        ("TIF", "FILTER_TIF"),
        ("EXR", "FILTER_EXR"),
    ]:
        value = getattr(c4d, const_name, None)
        if value is not None:
            items.append((value, label))
    return items


def get_colmap_model_items():
    return [(0, "PINHOLE"), (1, "SIMPLE_PINHOLE")]


class GSCameraSetupDialog(c4d.gui.GeDialog):
    ID_TARGET_LINK = 1000
    ID_CAM_COUNT = 1001
    ID_RADIUS = 1002
    ID_CENTER_X = 1003
    ID_CENTER_Y = 1004
    ID_CENTER_Z = 1005
    ID_SAMPLING_MODE = 1006
    ID_SPIRAL_TURNS = 1007
    ID_SPIRAL_POLE = 1008

    ID_OUTPUT_PATH = 1010
    ID_OUTPUT_PATH_BROWSE = 1015
    ID_OUTPUT_FORMAT = 1011
    ID_RES_X = 1012
    ID_RES_Y = 1013
    ID_FPS = 1014

    ID_CREATE_ANIM_CAM = 1020
    ID_REPLACE_RIG = 1021
    ID_EXPORT_JSON = 1022
    ID_JSON_PATH = 1023
    ID_JSON_PATH_BROWSE = 1026
    ID_EXPORT_COLMAP = 1024

    ID_AUTO_INTRINSICS = 1030
    ID_COLMAP_MODEL = 1031
    ID_FX = 1032
    ID_FY = 1033
    ID_CX = 1034
    ID_CY = 1035
    ID_SPARSE_COUNT = 1036
    ID_SPARSE_RADIUS_FACTOR = 1037

    ID_BUILD = 1090
    ID_EXPORT_COLMAP_ONLY = 1092
    ID_CLOSE = 1091

    def CreateLayout(self):
        self.SetTitle("GS Camera Setup")

        self.GroupBegin(1999, c4d.BFH_SCALEFIT, cols=3, rows=1)
        self.GroupBorderSpace(8, 8, 8, 4)
        self.AddButton(self.ID_BUILD, c4d.BFH_SCALEFIT, name="Execute")
        self.AddButton(self.ID_EXPORT_COLMAP_ONLY, c4d.BFH_SCALEFIT, name="Export COLMAP Only")
        self.AddButton(self.ID_CLOSE, c4d.BFH_SCALEFIT, name="Close")
        self.GroupEnd()

        self.GroupBegin(2000, c4d.BFH_SCALEFIT, cols=2, rows=0)
        self.GroupBorderSpace(8, 8, 8, 8)

        self.AddStaticText(2999, c4d.BFH_LEFT, name="Target Object")
        self.AddCustomGui(
            self.ID_TARGET_LINK,
            c4d.CUSTOMGUI_LINKBOX,
            "",
            c4d.BFH_SCALEFIT,
            0,
            0,
            c4d.BaseContainer(),
        )

        self.AddStaticText(3000, c4d.BFH_LEFT, name="Camera Count")
        self.AddEditNumberArrows(self.ID_CAM_COUNT, c4d.BFH_SCALEFIT)

        self.AddStaticText(3001, c4d.BFH_LEFT, name="Sphere Radius")
        self.AddEditNumberArrows(self.ID_RADIUS, c4d.BFH_SCALEFIT)

        self.AddStaticText(3002, c4d.BFH_LEFT, name="Center Offset X")
        self.AddEditNumberArrows(self.ID_CENTER_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(3003, c4d.BFH_LEFT, name="Center Offset Y")
        self.AddEditNumberArrows(self.ID_CENTER_Y, c4d.BFH_SCALEFIT)
        self.AddStaticText(3004, c4d.BFH_LEFT, name="Center Offset Z")
        self.AddEditNumberArrows(self.ID_CENTER_Z, c4d.BFH_SCALEFIT)

        self.AddStaticText(3005, c4d.BFH_LEFT, name="Sampling Mode")
        self.AddComboBox(self.ID_SAMPLING_MODE, c4d.BFH_SCALEFIT)
        for mode_id, mode_name in get_sampling_mode_items():
            self.AddChild(self.ID_SAMPLING_MODE, mode_id, mode_name)

        self.AddStaticText(3006, c4d.BFH_LEFT, name="Spiral Turns")
        self.AddEditNumberArrows(self.ID_SPIRAL_TURNS, c4d.BFH_SCALEFIT)
        self.AddStaticText(3007, c4d.BFH_LEFT, name="Spiral Pole Margin")
        self.AddEditNumberArrows(self.ID_SPIRAL_POLE, c4d.BFH_SCALEFIT)

        self.AddStaticText(3008, c4d.BFH_LEFT, name="Output Path")
        self.GroupBegin(2100, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.AddEditText(self.ID_OUTPUT_PATH, c4d.BFH_SCALEFIT)
        self.AddButton(self.ID_OUTPUT_PATH_BROWSE, c4d.BFH_RIGHT, name="Browse")
        self.GroupEnd()

        self.AddStaticText(3009, c4d.BFH_LEFT, name="Output Format")
        self.AddComboBox(self.ID_OUTPUT_FORMAT, c4d.BFH_SCALEFIT)
        for fmt_id, fmt_name in get_output_format_items():
            self.AddChild(self.ID_OUTPUT_FORMAT, int(fmt_id), fmt_name)

        self.AddStaticText(3010, c4d.BFH_LEFT, name="Resolution X")
        self.AddEditNumberArrows(self.ID_RES_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(3011, c4d.BFH_LEFT, name="Resolution Y")
        self.AddEditNumberArrows(self.ID_RES_Y, c4d.BFH_SCALEFIT)
        self.AddStaticText(3012, c4d.BFH_LEFT, name="FPS")
        self.AddEditNumberArrows(self.ID_FPS, c4d.BFH_SCALEFIT)

        self.AddStaticText(3013, c4d.BFH_LEFT, name="Create Animated Render Cam")
        self.AddCheckbox(self.ID_CREATE_ANIM_CAM, c4d.BFH_LEFT)
        self.AddStaticText(3014, c4d.BFH_LEFT, name="Replace Existing Rig")
        self.AddCheckbox(self.ID_REPLACE_RIG, c4d.BFH_LEFT)
        self.AddStaticText(3015, c4d.BFH_LEFT, name="Export Pose JSON")
        self.AddCheckbox(self.ID_EXPORT_JSON, c4d.BFH_LEFT)

        self.AddStaticText(3016, c4d.BFH_LEFT, name="Pose JSON Path")
        self.GroupBegin(2101, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.AddEditText(self.ID_JSON_PATH, c4d.BFH_SCALEFIT)
        self.AddButton(self.ID_JSON_PATH_BROWSE, c4d.BFH_RIGHT, name="Browse")
        self.GroupEnd()

        self.AddStaticText(3017, c4d.BFH_LEFT, name="Export Postshot COLMAP")
        self.AddCheckbox(self.ID_EXPORT_COLMAP, c4d.BFH_LEFT)
        self.AddStaticText(3018, c4d.BFH_LEFT, name="COLMAP Destination")
        self.AddStaticText(30180, c4d.BFH_LEFT, name="<Render Output Folder>/postshot_colmap")

        self.AddStaticText(3019, c4d.BFH_LEFT, name="Auto Intrinsics from Cam")
        self.AddCheckbox(self.ID_AUTO_INTRINSICS, c4d.BFH_LEFT)

        self.AddStaticText(3020, c4d.BFH_LEFT, name="COLMAP Model")
        self.AddComboBox(self.ID_COLMAP_MODEL, c4d.BFH_SCALEFIT)
        for model_id, model_name in get_colmap_model_items():
            self.AddChild(self.ID_COLMAP_MODEL, model_id, model_name)

        self.AddStaticText(3021, c4d.BFH_LEFT, name="fx")
        self.AddEditNumberArrows(self.ID_FX, c4d.BFH_SCALEFIT)
        self.AddStaticText(3022, c4d.BFH_LEFT, name="fy")
        self.AddEditNumberArrows(self.ID_FY, c4d.BFH_SCALEFIT)
        self.AddStaticText(3023, c4d.BFH_LEFT, name="cx")
        self.AddEditNumberArrows(self.ID_CX, c4d.BFH_SCALEFIT)
        self.AddStaticText(3024, c4d.BFH_LEFT, name="cy")
        self.AddEditNumberArrows(self.ID_CY, c4d.BFH_SCALEFIT)

        self.AddStaticText(3025, c4d.BFH_LEFT, name="Sparse Point Count")
        self.AddEditNumberArrows(self.ID_SPARSE_COUNT, c4d.BFH_SCALEFIT)
        self.AddStaticText(3026, c4d.BFH_LEFT, name="Sparse Radius Factor")
        self.AddEditNumberArrows(self.ID_SPARSE_RADIUS_FACTOR, c4d.BFH_SCALEFIT)

        self.GroupEnd()
        return True

    def _set_int_value(self, cid, value, min_value, max_value):
        try:
            self.SetInt32(cid, int(value), int(min_value), int(max_value))
        except TypeError:
            self.SetInt32(cid, int(value))

    def _set_float_value(self, cid, value, min_value, max_value, step=0.1):
        try:
            self.SetFloat(cid, float(value), float(min_value), float(max_value), float(step))
        except TypeError:
            self.SetFloat(cid, float(value))

    def InitValues(self):
        doc = c4d.documents.GetActiveDocument()
        target = TARGET_OBJECT_LINK
        if target is None and doc is not None:
            target = doc.GetActiveObject()
        if target is not None:
            self.SetLink(self.ID_TARGET_LINK, target)

        self._set_int_value(self.ID_CAM_COUNT, CAMERA_COUNT, 1, 1000000)
        self._set_float_value(self.ID_RADIUS, SPHERE_RADIUS, 0.000001, 1000000000.0, 1.0)
        self._set_float_value(self.ID_CENTER_X, SPHERE_CENTER_OFFSET.x, -1000000000.0, 1000000000.0, 1.0)
        self._set_float_value(self.ID_CENTER_Y, SPHERE_CENTER_OFFSET.y, -1000000000.0, 1000000000.0, 1.0)
        self._set_float_value(self.ID_CENTER_Z, SPHERE_CENTER_OFFSET.z, -1000000000.0, 1000000000.0, 1.0)

        mode_lookup = {"spiral": 0, "icosphere": 1, "fibonacci": 2}
        self.SetInt32(self.ID_SAMPLING_MODE, mode_lookup.get(SAMPLING_MODE.lower(), 0))
        self._set_float_value(self.ID_SPIRAL_TURNS, SPIRAL_TURNS, 0.01, 1000000.0, 0.1)
        self._set_float_value(self.ID_SPIRAL_POLE, SPIRAL_POLE_MARGIN, 0.0, 0.49, 0.001)

        self.SetString(self.ID_OUTPUT_PATH, str(OUTPUT_PATH))
        self.SetInt32(self.ID_OUTPUT_FORMAT, int(OUTPUT_FORMAT))
        self._set_int_value(self.ID_RES_X, RESOLUTION_X, 1, 65535)
        self._set_int_value(self.ID_RES_Y, RESOLUTION_Y, 1, 65535)
        self._set_int_value(self.ID_FPS, FPS, 1, 1000)

        self.SetBool(self.ID_CREATE_ANIM_CAM, bool(CREATE_ANIMATED_RENDER_CAMERA))
        self.SetBool(self.ID_REPLACE_RIG, bool(REPLACE_EXISTING_RIG))
        self.SetBool(self.ID_EXPORT_JSON, bool(EXPORT_CAMERA_POSES))
        self.SetString(self.ID_JSON_PATH, str(CAMERA_POSE_OUTPUT_PATH))
        self.SetBool(self.ID_EXPORT_COLMAP, bool(EXPORT_POSTSHOT_COLMAP))

        self.SetBool(self.ID_AUTO_INTRINSICS, bool(AUTO_COLMAP_INTRINSICS_FROM_RENDER_CAMERA))
        self.SetInt32(self.ID_COLMAP_MODEL, 0 if COLMAP_MODEL.upper() == "PINHOLE" else 1)
        self._set_float_value(self.ID_FX, COLMAP_FX_PX, 0.01, 1000000000.0, 1.0)
        self._set_float_value(self.ID_FY, COLMAP_FY_PX, 0.01, 1000000000.0, 1.0)
        self._set_float_value(self.ID_CX, COLMAP_CX_PX, -1000000000.0, 1000000000.0, 1.0)
        self._set_float_value(self.ID_CY, COLMAP_CY_PX, -1000000000.0, 1000000000.0, 1.0)
        self._set_int_value(self.ID_SPARSE_COUNT, COLMAP_SPARSE_POINT_COUNT, 8, 1000000)
        self._set_float_value(self.ID_SPARSE_RADIUS_FACTOR, COLMAP_SPARSE_POINT_RADIUS_FACTOR, 0.0001, 100.0, 0.01)
        return True

    def apply_ui_to_globals(self):
        global CAMERA_COUNT, SPHERE_RADIUS, SPHERE_CENTER_OFFSET
        global TARGET_OBJECT_LINK
        global SAMPLING_MODE, SPIRAL_TURNS, SPIRAL_POLE_MARGIN
        global OUTPUT_PATH, OUTPUT_FORMAT, RESOLUTION_X, RESOLUTION_Y, FPS
        global CREATE_ANIMATED_RENDER_CAMERA, REPLACE_EXISTING_RIG
        global EXPORT_CAMERA_POSES, CAMERA_POSE_OUTPUT_PATH
        global EXPORT_POSTSHOT_COLMAP
        global AUTO_COLMAP_INTRINSICS_FROM_RENDER_CAMERA
        global COLMAP_MODEL, COLMAP_FX_PX, COLMAP_FY_PX, COLMAP_CX_PX, COLMAP_CY_PX
        global COLMAP_SPARSE_POINT_COUNT, COLMAP_SPARSE_POINT_RADIUS_FACTOR

        CAMERA_COUNT = max(1, int(self.GetInt32(self.ID_CAM_COUNT)))
        doc = c4d.documents.GetActiveDocument()
        try:
            TARGET_OBJECT_LINK = self.GetLink(self.ID_TARGET_LINK, doc)
        except Exception:
            TARGET_OBJECT_LINK = None

        SPHERE_RADIUS = max(0.001, float(self.GetFloat(self.ID_RADIUS)))
        SPHERE_CENTER_OFFSET = c4d.Vector(
            float(self.GetFloat(self.ID_CENTER_X)),
            float(self.GetFloat(self.ID_CENTER_Y)),
            float(self.GetFloat(self.ID_CENTER_Z)),
        )

        sampling_mode_id = int(self.GetInt32(self.ID_SAMPLING_MODE))
        sampling_lookup = {0: "spiral", 1: "icosphere", 2: "fibonacci"}
        SAMPLING_MODE = sampling_lookup.get(sampling_mode_id, "spiral")
        SPIRAL_TURNS = max(0.01, float(self.GetFloat(self.ID_SPIRAL_TURNS)))
        SPIRAL_POLE_MARGIN = max(0.0, min(0.49, float(self.GetFloat(self.ID_SPIRAL_POLE))))

        OUTPUT_PATH = self.GetString(self.ID_OUTPUT_PATH).strip()
        OUTPUT_FORMAT = int(self.GetInt32(self.ID_OUTPUT_FORMAT))
        RESOLUTION_X = max(1, int(self.GetInt32(self.ID_RES_X)))
        RESOLUTION_Y = max(1, int(self.GetInt32(self.ID_RES_Y)))
        FPS = max(1, int(self.GetInt32(self.ID_FPS)))

        CREATE_ANIMATED_RENDER_CAMERA = bool(self.GetBool(self.ID_CREATE_ANIM_CAM))
        REPLACE_EXISTING_RIG = bool(self.GetBool(self.ID_REPLACE_RIG))

        EXPORT_CAMERA_POSES = bool(self.GetBool(self.ID_EXPORT_JSON))
        CAMERA_POSE_OUTPUT_PATH = self.GetString(self.ID_JSON_PATH).strip()

        EXPORT_POSTSHOT_COLMAP = bool(self.GetBool(self.ID_EXPORT_COLMAP))

        AUTO_COLMAP_INTRINSICS_FROM_RENDER_CAMERA = bool(self.GetBool(self.ID_AUTO_INTRINSICS))
        model_id = int(self.GetInt32(self.ID_COLMAP_MODEL))
        COLMAP_MODEL = "PINHOLE" if model_id == 0 else "SIMPLE_PINHOLE"
        COLMAP_FX_PX = float(self.GetFloat(self.ID_FX))
        COLMAP_FY_PX = float(self.GetFloat(self.ID_FY))
        COLMAP_CX_PX = float(self.GetFloat(self.ID_CX))
        COLMAP_CY_PX = float(self.GetFloat(self.ID_CY))
        COLMAP_SPARSE_POINT_COUNT = max(8, int(self.GetInt32(self.ID_SPARSE_COUNT)))
        COLMAP_SPARSE_POINT_RADIUS_FACTOR = max(0.0001, float(self.GetFloat(self.ID_SPARSE_RADIUS_FACTOR)))

    def Command(self, cid, msg):
        if cid == self.ID_OUTPUT_PATH_BROWSE:
            picked = c4d.storage.LoadDialog(flags=c4d.FILESELECT_DIRECTORY, title="Select Render Output Folder")
            if picked:
                self.SetString(self.ID_OUTPUT_PATH, os.path.join(picked, "gs_####"))
            return True

        if cid == self.ID_JSON_PATH_BROWSE:
            picked = c4d.storage.SaveDialog(
                def_path=self.GetString(self.ID_JSON_PATH),
                force_suffix="json",
                title="Save Camera Pose JSON"
            )
            if picked:
                if not picked.lower().endswith(".json"):
                    picked += ".json"
                self.SetString(self.ID_JSON_PATH, picked)
            return True

        if cid == self.ID_BUILD:
            self.apply_ui_to_globals()
            try:
                main(force_run=True, target_obj_override=TARGET_OBJECT_LINK)
            except Exception as exc:
                c4d.gui.MessageDialog("Build failed: {}".format(exc))
            return True

        if cid == self.ID_EXPORT_COLMAP_ONLY:
            self.apply_ui_to_globals()
            try:
                export_colmap_only(target_obj_override=TARGET_OBJECT_LINK)
            except Exception as exc:
                c4d.gui.MessageDialog("COLMAP export failed: {}".format(exc))
            return True

        if cid == self.ID_CLOSE:
            self.Close()
            return True

        return True


def open_ui():
    global _DIALOG_INSTANCE
    if _DIALOG_INSTANCE is None:
        _DIALOG_INSTANCE = GSCameraSetupDialog()

    return _DIALOG_INSTANCE.Open(
        dlgtype=c4d.DLG_TYPE_ASYNC,
        defaultw=520,
        defaulth=760,
    )


def main(doc=None, force_run=False, target_obj_override=None):
    global _HAS_RUN
    if _HAS_RUN and not force_run:
        return
    _HAS_RUN = True

    if doc is None:
        doc = c4d.documents.GetActiveDocument()
    if doc is None:
        c4d.gui.MessageDialog("No active Cinema 4D document found.")
        return

    if CAMERA_COUNT < 1:
        c4d.gui.MessageDialog("CAMERA_COUNT must be >= 1")
        return

    target_obj = get_target_object(doc, target_obj_override=target_obj_override)
    if target_obj is None:
        c4d.gui.MessageDialog("Select or link the target object before running this script.")
        return

    doc.StartUndo()

    try:
        target_pos = center_of_object(target_obj) + SPHERE_CENTER_OFFSET

        if REPLACE_EXISTING_RIG:
            existing = find_object_by_name(doc.GetFirstObject(), "GS_CameraRig")
            if existing is not None:
                doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, existing)
                existing.Remove()

        rig = c4d.BaseObject(c4d.Onull)
        rig.SetName("GS_CameraRig")
        rig.SetAbsPos(target_pos)
        doc.InsertObject(rig)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, rig)

        target_null = c4d.BaseObject(c4d.Onull)
        target_null.SetName("GS_Target")
        target_null.InsertUnder(rig)
        target_null.SetAbsPos(target_pos)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, target_null)

        unit_points, mode_used, subdivisions = generate_unit_points(CAMERA_COUNT)
        world_points = [target_pos + p * SPHERE_RADIUS for p in unit_points]

        for i, world_pos in enumerate(world_points):
            cam = c4d.BaseObject(c4d.Ocamera)
            cam.SetName("GS_Cam_{:04d}".format(i + 1))
            cam.InsertUnder(rig)
            cam.SetAbsPos(world_pos)
            create_target_tag(cam, target_null)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, cam)

        render_cam = None
        if CREATE_ANIMATED_RENDER_CAMERA:
            render_cam = c4d.BaseObject(c4d.Ocamera)
            render_cam.SetName("GS_RenderCam_Animated")
            render_cam.InsertUnder(rig)
            render_cam.SetAbsPos(world_points[0])
            create_target_tag(render_cam, target_null)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, render_cam)

            # Animate position with one key per frame/viewpoint.
            desc_x = c4d.DescID(
                c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                c4d.DescLevel(c4d.VECTOR_X, c4d.DTYPE_REAL, 0)
            )
            desc_y = c4d.DescID(
                c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                c4d.DescLevel(c4d.VECTOR_Y, c4d.DTYPE_REAL, 0)
            )
            desc_z = c4d.DescID(
                c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                c4d.DescLevel(c4d.VECTOR_Z, c4d.DTYPE_REAL, 0)
            )

            for frame, world_pos in enumerate(world_points):
                local_pos = world_pos - target_pos
                t = c4d.BaseTime(frame, FPS)
                add_float_key(render_cam, desc_x, t, local_pos.x, c4d.CINTERPOLATION_STEP)
                add_float_key(render_cam, desc_y, t, local_pos.y, c4d.CINTERPOLATION_STEP)
                add_float_key(render_cam, desc_z, t, local_pos.z, c4d.CINTERPOLATION_STEP)

        configure_render_settings(doc, render_cam, len(world_points))

        pose_file = None
        if EXPORT_CAMERA_POSES:
            pose_file = export_camera_poses(
                world_points,
                target_pos,
                CAMERA_POSE_OUTPUT_PATH,
                render_cam=render_cam
            )

        postshot_colmap = None
        if EXPORT_POSTSHOT_COLMAP:
            colmap_dir = resolve_colmap_output_dir()
            postshot_colmap = export_colmap_for_postshot(
                world_points,
                target_pos,
                colmap_dir,
                render_cam=render_cam,
                doc=doc,
                target_obj=target_obj,
            )

        doc.SetTime(c4d.BaseTime(0, FPS))
        c4d.EventAdd()

        c4d.gui.MessageDialog(
            "Created {} cameras on a sphere around '{}'.\n"
            "Sampling mode: {}{}\n"
            "Render settings configured for {} frames.\n"
            "Camera pose export: {}\n"
            "Postshot COLMAP export: {}\n"
            "Sparse point source: {}\n"
            "COLMAP intrinsics source: {}\n"
            "COLMAP debug report: {}\n"
            "Now render animation to output image sequence.".format(
                len(world_points),
                target_obj.GetName(),
                mode_used,
                " (subdivisions: {})".format(subdivisions) if mode_used == "icosphere"
                else " (turns: {:.2f})".format(SPIRAL_TURNS) if mode_used == "spiral" else "",
                len(world_points),
                pose_file if pose_file else "disabled",
                postshot_colmap["dir"] if postshot_colmap else "disabled",
                postshot_colmap["points_source"] if postshot_colmap else "n/a",
                postshot_colmap["intrinsics_source"] if postshot_colmap else "n/a",
                postshot_colmap["debug_report"] if postshot_colmap else "n/a"
            )
        )

    finally:
        doc.EndUndo()


def export_colmap_only(doc=None, target_obj_override=None):
    if doc is None:
        doc = c4d.documents.GetActiveDocument()
    if doc is None:
        c4d.gui.MessageDialog("No active Cinema 4D document found.")
        return

    if CAMERA_COUNT < 1:
        c4d.gui.MessageDialog("CAMERA_COUNT must be >= 1")
        return

    target_obj = get_target_object(doc, target_obj_override=target_obj_override)
    if target_obj is None:
        c4d.gui.MessageDialog("Select or link the target object before exporting COLMAP.")
        return

    target_pos = center_of_object(target_obj) + SPHERE_CENTER_OFFSET
    unit_points, mode_used, subdivisions = generate_unit_points(CAMERA_COUNT)
    world_points = [target_pos + p * SPHERE_RADIUS for p in unit_points]

    render_cam = None
    rig = find_object_by_name(doc.GetFirstObject(), "GS_CameraRig")
    if rig is not None:
        child = rig.GetDown()
        while child:
            if child.CheckType(c4d.Ocamera) and child.GetName() == "GS_RenderCam_Animated":
                render_cam = child
                break
            child = child.GetNext()

    if render_cam is None:
        bd = doc.GetActiveBaseDraw()
        if bd is not None:
            scene_cam = bd.GetSceneCamera(doc)
            if scene_cam is not None and scene_cam.CheckType(c4d.Ocamera):
                render_cam = scene_cam

    colmap_dir = resolve_colmap_output_dir()
    postshot_colmap = export_colmap_for_postshot(
        world_points,
        target_pos,
        colmap_dir,
        render_cam=render_cam,
        doc=doc,
        target_obj=target_obj,
    )

    c4d.gui.MessageDialog(
        "Exported COLMAP poses only.\n"
        "Sampling mode: {}{}\n"
        "Images listed: {}\n"
        "Sparse points: {}\n"
        "Sparse point source: {}\n"
        "Folder: {}\n"
        "cameras.txt: {}\n"
        "images.txt: {}\n"
        "points3D.txt: {}\n"
        "debug report: {}\n"
        "Intrinsics source: {}".format(
            mode_used,
            " (subdivisions: {})".format(subdivisions) if mode_used == "icosphere"
            else " (turns: {:.2f})".format(SPIRAL_TURNS) if mode_used == "spiral" else "",
            len(world_points),
            postshot_colmap["points_count"] if postshot_colmap else 0,
            postshot_colmap["points_source"] if postshot_colmap else "n/a",
            postshot_colmap["dir"] if postshot_colmap else "n/a",
            postshot_colmap["cameras_txt"] if postshot_colmap else "n/a",
            postshot_colmap["images_txt"] if postshot_colmap else "n/a",
            postshot_colmap["points3d_txt"] if postshot_colmap else "n/a",
            postshot_colmap["debug_report"] if postshot_colmap else "n/a",
            postshot_colmap["intrinsics_source"] if postshot_colmap else "n/a",
        )
    )


if __name__ == '__main__':
    if OPEN_UI_ON_RUN:
        open_ui()
    else:
        main()

