# C4D2GS — Cinema 4D to Gaussian Splat

A Cinema 4D Python plugin that generates synthetic COLMAP data for Gaussian Splatting.  
It automates the whole capture-rig pipeline:

1. Select target Object 
2. insert Output Path
3. build & export
4. render!

All in one solution for drag and drop of synthetic COLMAP data into any Gaussian Splatting editor of your choice.

## Installation

1. Copy the entire `c4d2gs` folder into your Cinema 4D *plugins* directory:

   | Platform | Path |
   |----------|------|
   | macOS    | `~/Library/Preferences/Maxon/Maxon Cinema 4D <version>/plugins/` |
   | Windows  | `%APPDATA%\Maxon\Maxon Cinema 4D <version>\plugins\` |

2. (Re-)start Cinema 4D.
3. The plugin appears in the menu bar under **Plugins ▸ C4D2GS**.

> **Python version note** — requires Cinema 4D 2023 or later (Python 3).

---

## Quick Start

1. Open a scene containing the object you want to splat.
2. Open the plugin: **Plugins ▸ C4D2GS**.
3. In the **Target Object** field at the top of the dialog, assign and confirm
   the object link.
4. Set the **Radius** control in the *Camera* section to the distance you want
   between the object centre and the capture cameras.
5. Set your **Output Path** in the *Output* section, for example
   `C:\renders\my_splat`. The plugin writes everything into that folder:
   the synthetic COLMAP data files (`cameras.txt`, `images.txt`, `points3D.txt`),
   the pose file `camera_poses.json`, and rendered images in `images/gs_####`.
6. Click **Build & Export**.
7. Render the animation in Cinema 4D (`Render ▸ Render to Picture Viewer`, or
   use the Command Line Renderer for batch rendering).
8. Import the output directory into your reconstruction tool that supports synthetic COLMAP data
   (synthetic COLMAP data files at root) and use the `images/` sub-folder as the image sequence.

---

## Dialog Reference

### Target Object
The object that cameras are placed around. Use the link-box to assign any
scene object. The plugin uses this dialog field as the authoritative target
and does not rely on Object Manager selection state.

### Camera Section
| Field | Description |
|-------|-------------|
| Camera Count | Number of viewpoints placed on the sphere. |
| Radius | Distance from the object centre to each camera, adjusted directly in the dialog. |
| Center Offset X/Y/Z | Shifts the sphere centre away from the selected center mode result. |
| Center Mode | Chooses how the plugin computes the rig center: **Geometry Center** (default) or **Axis Pivot**. |
| Sampling Mode | Algorithm used to distribute cameras: **Spiral** (default, even helical coverage), **Icosphere** (geodesic), **Fibonacci** (golden-angle). |
| Spiral Turns | Number of helical turns (Spiral mode only). |
| Pole Margin | Fraction of sphere height excluded near poles (Spiral mode only, 0–0.49). |

### Output Section
| Field | Description |
|-------|-------------|
| Output Path | Base path for all exports. The plugin writes synthetic COLMAP data files (`cameras.txt`, `images.txt`, `points3D.txt`) and `camera_poses.json` at root, plus rendered frames into `images/gs_####`. |
| Format | Image format: PNG, JPG, TIF, or EXR. |
| Resolution | Width × Height in pixels. |
| FPS | Frames per second (affects timeline length only). |

### Export Section
| Field | Description |
|-------|-------------|
| Create Animated Render Cam | Adds `GS_RenderCam_Animated` with step-interpolated position keys—one key per viewpoint. |
| Replace Existing Rig | Removes any previous `GS_CameraRig` null before building a new one. |
| Auto Update Rig | Automatically rebuilds the rig when you change rig-related parameters, for a faster iterative workflow. |
| Export Pose JSON | Writes a `camera_poses.json` file with per-frame transform matrices and intrinsics. |
| JSON Output | Written automatically as `<Output Path>/camera_poses.json`. |
| Export Synthetic COLMAP Data | Writes synthetic COLMAP data files (`cameras.txt`, `images.txt`, `points3D.txt`) for tools that support synthetic COLMAP data. |
| Auto Intrinsics from Cam | Derives `fx/fy/cx/cy` from the render camera's focal length and sensor width. |
| Manual Intrinsics | Override values used when auto-intrinsics is off or unavailable. The plugin automatically selects `SIMPLE_PINHOLE` or `PINHOLE` from the effective focal parameters. |
| Sparse Point Count | Number of surface sample points used to build the synthetic COLMAP data sparse reconstruction (default: 30000, manually adjustable). |

### Action Buttons
| Button | Action |
|--------|--------|
| **Create / Update Rig** | Builds or rebuilds only the camera rig from current parameters (no JSON/synthetic COLMAP data export), useful for iterative adjustments. |
| **Build & Export** | Builds the full camera rig, configures render settings, and writes all selected export files. |
| **COLMAP Only** | Re-exports just the synthetic COLMAP data files using the current settings and the existing rig/intrinsics—useful after tweaking sparse-point count. |
| **Close** | Closes the dialog (current settings are persisted and restored on next open/restart). |

---

## Example Workflow (Synthetic COLMAP Data)

```
Cinema 4D                           Reconstruction App
──────────────────────────────────  ─────────────────────────────────────
1. Build & Export  ──────────────>  output folder/
                                      cameras.txt
                                      images.txt
                                      points3D.txt
                                      images/
2. Render animation  ────────────>  images/gs_0000.png … images/gs_0119.png

3. In your reconstruction app:
   Import synthetic COLMAP data project      <──  point at output folder
   and select output folder/images
```

## Export Layout

```
C4D2GS exports:
   cameras.txt
   images.txt
   points3D.txt

   images/
      gs_0000.png
      gs_0001.png
      ...

   camera_poses.json <- for nerfstudio / instant-ngp style tools,
                                  optional for COLMAP-based workflows
```

---

## Compatibility Notes

- `points3D.txt` uses synthetic sparse points sampled from the target surface,
   with synthetic image tracks intended for robust COLMAP-style initialization.
- Visibility filtering includes a surface-normal facing check, so backfacing
   points are excluded from camera observations.
- Track observations are intentionally capped per point (instead of spanning all
   cameras) to stay closer to typical COLMAP visibility patterns.
- Point colors are written as white (`255 255 255`) because C4D2GS exports
   before image-based color sampling; downstream reconstruction/training tools
   optimize color during reconstruction.
- `camera_poses.json` uses NeRF-style `file_path` entries with relative image
   names for portability across machines.
- The JSON `transform_matrix` is converted from Cinema 4D world space to the
   axis convention expected by nerfstudio / instant-ngp.

---

## File Structure

```
c4d2gs/
├── c4d2gs.pyp   ← main plugin file (all logic + UI)
└── README.md    ← this file
```

---

## License

CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 International).
