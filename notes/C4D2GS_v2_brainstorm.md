# C4D2GS — Plugin Expansion Brainstorm
**Version:** Post-v1.0.0 Planning Document  
**Status:** Updated — Implementation in Progress  
**Date:** 2026-03-31

---

## Overview

This document captures a full brainstorming session for expanding the C4D2GS Cinema 4D plugin beyond its current v1.0.0 Object-centric workflow. The expansion introduces a tabbed UI structure, a new spatial scanning mode, camera group appending, multi-object support, and a revised output folder convention.

---

## 1. New UI Structure — Tabs

The dialog is restructured into three top-level tabs:

| Tab | Status | Description |
|-----|--------|-------------|
| **Object** | Implemented | Single or multi-object inward-facing rig |
| **Space** | Implemented | Outward-facing cluster scanning for room/environment capture |
| **Import** | Deferred — not yet decided if included | COLMAP data import and scene reconstruction |

---

## 2. Object Tab — Changes & Additions

### 2.1 Additional Camera Groups

- **Status:** Implemented
- The user can drag and drop a **null object group** containing custom Cinema 4D cameras into a new object link field in the Object tab.
- For each camera in the group, the plugin reads its world matrix (`GetMg()`) and **appends one keyframe per camera to the existing animated render camera**.
- This means additional cameras are just extra frames at the end of the existing animation sequence — no new camera objects, no changes to `cameras.txt` intrinsics, no new image sequences.
- The intrinsics of the render camera remain constant throughout, including the appended frames.
- Cameras can be freely positioned in C4D to capture detail shots, wide shots, macro views, etc.
- Naming: appended frames continue the `gs_####` sequence without a prefix change.

### 2.2 Multi-Object Support

- **Status:** Deferred
- A new **"Add Object"** button in the Object tab creates additional target object link fields dynamically.
- Each target object runs the full pipeline independently (its own rig, its own COLMAP export).
- Each target writes to its own subfolder under the root output path (see Section 4 for naming convention).

---

## 3. Space Tab — New Feature

The Space tab handles **environment/room-scale scanning** using outward-facing camera clusters rather than a single inward-facing object rig.

### 3.1 Core Concept

- **Status:** Implemented
- Instead of one sphere rig orbiting an object, **multiple camera clusters** are distributed throughout a space.
- Each cluster is a small icosphere (or sphere-sampled) arrangement of cameras pointing **outward** from the cluster center.
- All clusters are combined into a **single animated render camera** using the same keyframe-append logic as the Object tab — one frame per camera position across all clusters.
- All rendered images go into the same `images/` folder.
- COLMAP files (`cameras.txt`, `images.txt`, `points3D.txt`) are written to the Space subfolder (see Section 4).

### 3.2 Anchor Placement Modes

- **Status:** Implemented
- Anchor points define where each cluster is centered. Two modes:

#### Auto Placement
- The user defines a **bounding area** (likely a bounding box or XZ extents).
- Anchors are distributed within that area either:
  - **Random** — randomized positions within the bounds.
  - **Grid** — regular NxM grid layout within the bounds.
- A single **Y-height parameter** sets the vertical position of all auto-generated anchors uniformly. One value, applies to all.
- Manual anchor mode does not use this parameter (nulls are positioned freely).

#### Manual Placement
- The user drags a **null group** into an object link field.
- Each child null in the group becomes one cluster anchor point.
- Nulls can be positioned freely on all axes — full spatial freedom.
- The plugin reads each null's world position and generates one icosphere camera cluster centered on that position.

### 3.3 Spherical Camera Option

- **Status:** Implemented
- Users can choose to use spherical cameras as anchors instead of clusters.
- Each anchor point has a single spherical camera, reducing the number of cameras per anchor.
- Spherical cameras render equirectangular images for environment mapping.

---

## 4. Output Folder Convention

### 4.1 New Subfolder Structure

- **Status:** In Progress
- All exports now write into a named subfolder under the user-defined root output path, rather than directly into the root:

```
<Output Path>/
    Object_<TargetObjectName>_COLMAP/
        cameras.txt
        images.txt
        points3D.txt
        camera_poses.json
        images/
            gs_0000.png
            gs_0001.png
            ...

    Space_COLMAP/
        cameras.txt
        images.txt
        points3D.txt
        camera_poses.json
        images/
            gs_0000.png
            ...
```

- **Object mode:** `Object_<TargetObjectName>_COLMAP`
- **Space mode:** `Space_COLMAP` (no differentiating name needed)
- `camera_poses.json` lives inside the respective subfolder, not at the root output path.

### 4.2 Override / Increment Behavior

- A **checkbox in the dialog** controls overwrite behavior: **"Override existing export folder"**.
- If **unchecked** (default): if the target folder already exists, a numeric suffix is appended — `_001`, `_002`, etc. — determined at export time by checking what exists on disk.
- If **checked**: existing folder is overwritten.
- The suffix check happens at export time, not at dialog open time, so it reflects the actual state of the filesystem at the moment of export.

---

## 5. Deferred / Potential Features (not in immediate scope)

These were discussed but not prioritized for the next version:

| Feature | Notes |
|---------|-------|
| **COLMAP Import Tab** | Parse `cameras.txt`, `images.txt`, `points3D.txt` and build an animated camera in C4D. Coordinate conversion is already consistent with the exporter. Single animated camera, respects existing Camera Type setting (Standard/RS). Optional sparse point cloud import as PolygonObject + MoGraph Matrix previs. Not yet decided whether to include. |
| **Hemisphere Mode** | Clip the sphere to top/bottom/front half. Simple clipping parameter in `generate_unit_points`. |
| **Adaptive Radius** | Auto-compute sphere radius from `get_object_bounding_radius` with a user multiplier. Function already exists, just not surfaced. |
| **Camera Path Smoothing** | Optional spline interpolation instead of step keys for the animated render camera. Useful for preview flythroughs. |

---

## 6. Architectural Notes

### What stays the same
- `generate_unit_points` — reused for both Object clusters and Space clusters.
- `look_at_matrix` — still used for Object mode; inverted / removed for Space outward-facing.
- `_make_camera_object` — reused, respects Standard/RS camera type setting.
- `_add_step_key` with `CINTERPOLATION_STEP` — keyframe append logic is the same for additional cameras and spatial clusters.
- `export_colmap`, `export_camera_poses_json` — largely unchanged, just pointed at new subfolder paths.

### What needs new code
- `_import_colmap.py` — if Import tab is added.
- `_space_builder.py` or equivalent — anchor point generation (auto grid/random + manual null reading), cluster assembly, outward-facing matrix logic.
- Subfolder naming and increment logic — probably a utility function in `_file_utils.py`.
- Dynamic multi-object UI — addable list of target link fields in the Object tab.
- New tab structure in `_ui_dialog.py` — `_build_object_tab()`, `_build_space_tab()`, `_build_import_tab()`.
- Auto Y-height anchor parameter in Space tab.

---

## 7. Open Questions

1. **Sparse points for Space mode** — how to sample scene-level geometry rather than a single object surface.
2. **Import tab** — include in v2 or defer to v3?
3. **Multi-object UI** — how many targets should be supported, and is there a reasonable cap?
4. **Space mode folder naming** — `Space_COLMAP` is fixed for now; revisit if multiple space exports under one root path become a use case.

---

*End of brainstorm document.*
