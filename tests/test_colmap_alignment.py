"""
Regression test: COLMAP 3D-point / camera-extrinsics alignment.

Verifies that every 3D point in TestDataset/points3D.txt reprojects
to its recorded 2D observation with sub-pixel accuracy using the
camera poses stored in TestDataset/images.txt.

The bug this guards against: points3D.txt was written with negated Y
and Z coordinates (-p3d.y, -p3d.z) while the camera extrinsics were
derived from C4D world-space matrices without any world-coordinate
flip.  That sign mismatch produced ~200–350 px reprojection errors.
The fix is to write the world-space coordinates unchanged (p3d.x,
p3d.y, p3d.z) so that R_w2c * p_world + t gives the correct
COLMAP camera-space point for every observation.
"""

import math
import os
import unittest

# ---------------------------------------------------------------------------
# Helpers (pure Python – no Cinema 4D dependency)
# ---------------------------------------------------------------------------

def _quat_to_rot(qw, qx, qy, qz):
    """Return the 3×3 rotation matrix corresponding to unit quaternion."""
    return [
        [1 - 2*(qy*qy + qz*qz),  2*(qx*qy - qz*qw),    2*(qx*qz + qy*qw)],
        [2*(qx*qy + qz*qw),      1 - 2*(qx*qx + qz*qz), 2*(qy*qz - qx*qw)],
        [2*(qx*qz - qy*qw),      2*(qy*qz + qx*qw),     1 - 2*(qx*qx + qy*qy)],
    ]


def _project(R, t, fx, fy, cx, cy, X, Y, Z):
    """
    Project world point (X, Y, Z) through a COLMAP camera (R, t, intrinsics).

    Returns (u, v, z_cam) or (None, None, z_cam) if behind the camera.
    The COLMAP convention requires z_cam > 0 for visible points.
    """
    xc = R[0][0]*X + R[0][1]*Y + R[0][2]*Z + t[0]
    yc = R[1][0]*X + R[1][1]*Y + R[1][2]*Z + t[1]
    zc = R[2][0]*X + R[2][1]*Y + R[2][2]*Z + t[2]
    if zc <= 0.0:
        return None, None, zc
    return fx * (xc / zc) + cx, fy * (yc / zc) + cy, zc


# ---------------------------------------------------------------------------
# Dataset paths (relative to this file's parent directory)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATASET = os.path.join(_HERE, "..", "TestDataset")


def _dataset_path(name):
    return os.path.join(_DATASET, name)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestColmapAlignment(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load cameras.txt, images.txt and points3D.txt once for all tests."""
        # cameras.txt — one shared camera model
        fx = fy = cx = cy = None
        with open(_dataset_path("cameras.txt")) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                model = parts[1]
                if model == "SIMPLE_PINHOLE":
                    fx = fy = float(parts[4])
                    cx, cy = float(parts[5]), float(parts[6])
                elif model == "PINHOLE":
                    fx, fy = float(parts[4]), float(parts[5])
                    cx, cy = float(parts[6]), float(parts[7])
                else:
                    raise ValueError("Unsupported camera model: " + model)
        assert fx is not None and fy is not None and cx is not None and cy is not None, (
            "cameras.txt contained no parseable camera entry; "
            "fx/fy/cx/cy were never assigned."
        )
        cls.fx, cls.fy, cls.cx, cls.cy = fx, fy, cx, cy

        # points3D.txt
        cls.points = {}
        with open(_dataset_path("points3D.txt")) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.split()
                cls.points[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))

        # images.txt — parse pose + observation pairs
        cls.image_data = []
        with open(_dataset_path("images.txt")) as f:
            raw = [l for l in f if not l.startswith("#")]
        i = 0
        while i < len(raw):
            pose_line = raw[i].strip()
            obs_line  = raw[i + 1].strip() if i + 1 < len(raw) else ""
            i += 2
            if not pose_line:
                continue
            parts = pose_line.split()
            if len(parts) < 9:
                continue
            qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            tx, ty, tz      = float(parts[5]), float(parts[6]), float(parts[7])
            R = _quat_to_rot(qw, qx, qy, qz)
            t = [tx, ty, tz]

            obs = []
            if obs_line:
                op = obs_line.split()
                for j in range(0, len(op), 3):
                    obs.append((float(op[j]), float(op[j+1]), int(op[j+2])))

            cls.image_data.append({"R": R, "t": t, "obs": obs})

    # ------------------------------------------------------------------
    # Shared projection helper
    # ------------------------------------------------------------------

    def _compute_projection_stats(self):
        """Iterate every tracked observation once and return aggregate stats.

        Returns a dict with:
          total        – number of (point, camera) pairs checked
          behind_count – pairs where z_cam <= 0
          rms_err      – RMS reprojection error in pixels (over visible pairs)
          max_err      – maximum per-observation reprojection error in pixels
        """
        total = 0
        behind_count = 0
        total_sq_err = 0.0
        max_err = 0.0

        for cam in self.image_data:
            R, t = cam["R"], cam["t"]
            for u_obs, v_obs, pid in cam["obs"]:
                if pid not in self.points:
                    continue
                X, Y, Z = self.points[pid]
                u_p, v_p, zc = _project(
                    R, t, self.fx, self.fy, self.cx, self.cy, X, Y, Z
                )
                total += 1
                if zc <= 0.0:
                    behind_count += 1
                    continue
                err = math.sqrt((u_obs - u_p) ** 2 + (v_obs - v_p) ** 2)
                total_sq_err += err * err
                if err > max_err:
                    max_err = err

        visible = total - behind_count
        rms_err = math.sqrt(total_sq_err / visible) if visible > 0 else float("inf")
        return {
            "total": total,
            "behind_count": behind_count,
            "rms_err": rms_err,
            "max_err": max_err,
        }

    # ------------------------------------------------------------------

    def test_reprojection_error_is_zero(self):
        """
        Every (point3D_id, 2D-observation) pair must reproject to within
        0.1 px (RMS) of the stored observation using the COLMAP camera
        extrinsics.

        A large RMS error (>> 1 px) indicates a world-coordinate sign
        mismatch between points3D.txt and images.txt (the original bug).
        """
        stats = self._compute_projection_stats()
        self.assertGreater(stats["total"], 0, "No observations were checked.")
        self.assertLess(
            stats["rms_err"],
            0.1,
            msg="RMS reprojection error is {:.4f} px (threshold 0.1 px). "
                "Large errors indicate a Y/Z sign mismatch in points3D.txt.".format(
                    stats["rms_err"]),
        )
        self.assertLess(
            stats["max_err"],
            0.5,
            msg="Max reprojection error is {:.4f} px (threshold 0.5 px).".format(
                stats["max_err"]),
        )

    def test_points_in_front_of_cameras(self):
        """
        All tracked 3D points must project to positive z_cam (in front of camera).

        Before the fix, negated Y/Z coordinates caused many points to land
        behind the camera (z_cam <= 0) for their assigned observations.
        """
        stats = self._compute_projection_stats()
        self.assertGreater(stats["total"], 0, "No observations were checked.")
        self.assertEqual(
            stats["behind_count"],
            0,
            msg="{}/{} point-observations have z_cam <= 0 (behind camera). "
                "This is caused by a coordinate sign error in points3D.txt.".format(
                    stats["behind_count"], stats["total"]),
        )

    def test_centroid_alignment(self):
        """
        The centroid of the 3D sparse points should be geometrically close
        to the centroid of the camera centres (both representing the same
        scene region).  A large offset signals a coordinate mismatch.
        """
        self.assertGreater(len(self.image_data), 0, "No cameras were loaded.")
        self.assertGreater(len(self.points), 0, "No 3D points were loaded.")

        # camera centres: c = -R^T t
        cam_cx = cam_cy = cam_cz = 0.0
        for cam in self.image_data:
            R, t = cam["R"], cam["t"]
            # c_k = -sum_j R[j][k] * t[j]
            cam_cx += -sum(R[j][0] * t[j] for j in range(3))
            cam_cy += -sum(R[j][1] * t[j] for j in range(3))
            cam_cz += -sum(R[j][2] * t[j] for j in range(3))
        n_cams = len(self.image_data)
        cam_cx /= n_cams; cam_cy /= n_cams; cam_cz /= n_cams

        pts = list(self.points.values())
        pt_cx = sum(p[0] for p in pts) / len(pts)
        pt_cy = sum(p[1] for p in pts) / len(pts)
        pt_cz = sum(p[2] for p in pts) / len(pts)

        # Measure the mean radius of the camera sphere (approx)
        cam_radii = []
        for cam in self.image_data:
            R, t = cam["R"], cam["t"]
            cx = -sum(R[j][0] * t[j] for j in range(3))
            cy = -sum(R[j][1] * t[j] for j in range(3))
            cz = -sum(R[j][2] * t[j] for j in range(3))
            cam_radii.append(math.sqrt((cx - cam_cx) ** 2 + (cy - cam_cy) ** 2 + (cz - cam_cz) ** 2))
        self.assertGreater(len(cam_radii), 0, "Camera radii could not be computed.")
        radius = sum(cam_radii) / len(cam_radii)

        offset = math.sqrt(
            (cam_cx - pt_cx) ** 2 + (cam_cy - pt_cy) ** 2 + (cam_cz - pt_cz) ** 2
        )
        # The point-cloud centroid may differ from the camera-sphere centre by
        # up to half the sphere radius (object is not necessarily centred exactly
        # on the camera-orbit origin), so allow 60 % of the sphere radius.
        threshold = 0.6 * radius
        self.assertLess(
            offset,
            threshold,
            msg="Centroid offset {:.2f} exceeds {:.2f} (60% of sphere radius "
                "{:.2f}). Points and cameras appear misaligned.".format(
                    offset, threshold, radius),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
