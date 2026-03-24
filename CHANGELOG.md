# Changelog

All notable changes to C4D2GS are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2026

### Added
- Initial public release of the C4D2GS Cinema 4D plugin.
- Camera rig builder: places N cameras on a sphere around any target object using
  **Spiral**, **Icosphere**, or **Fibonacci** distribution.
- Animated render camera (`GS_RenderCam_Animated`) with step-interpolated
  keyframes — one viewpoint per frame.
- Synthetic COLMAP data export (`cameras.txt`, `images.txt`, `points3D.txt`) for
  reconstruction tools that accept COLMAP-format input.
- Camera pose JSON export (`camera_poses.json`) in nerfstudio / instant-ngp format.
- Auto-intrinsics: derives `fx`, `fy`, `cx`, `cy` from the Cinema 4D render
  camera's focal length and sensor width when available.
- Surface-based sparse point sampling with area-weighted triangle selection and
  surface-normal visibility culling.
- Four-stage fallback pipeline for robust sparse-point export on assets with
  atypical geometry (flipped normals, non-polygon primitives, empty surfaces).
- Support for standard Cinema 4D cameras and Redshift RSCamera objects.
- Settings persistence across sessions via `c4d.plugins.SetWorldPluginData`.
- `c4d2gs_lite.py`: standalone no-UI script version for Script Manager use.
