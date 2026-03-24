# C4D2GS — Cinema 4D to Gaussian Splat

A Cinema 4D Python plugin that generates synthetic COLMAP data for Gaussian Splatting.
It automates the whole capture-rig pipeline:

1. Select target object
2. Insert output path
3. Build & Export
4. Render!

All in one solution for drag-and-drop of synthetic COLMAP data into any Gaussian Splatting editor of your choice.

---

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
8. Import the output directory into your reconstruction tool that supports synthetic
   COLMAP data (synthetic COLMAP data files at root) and use the `images/`
   sub-folder as the image sequence.

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
| Radius | Distance from the object centre to each camera. |
| Sampling Mode | Algorithm used to distribute cameras: **Spiral** (default, even helical coverage), **Icosphere** (geodesic), **Fibonacci** (golden-angle). |
| Spiral Turns | Number of helical turns (Spiral mode only). |
| Pole Margin | Fraction of sphere height excluded near poles (Spiral mode only, 0–0.49). |

### Output Section
| Field | Description |
|-------|-------------|
| Output Path | Base path for all exports. |
| Format | Image format: PNG, JPG, TIF, or EXR. |
| Resolution | Width × Height in pixels. |
| FPS | Frames per second (affects timeline length only). |

### Export Section
| Field | Description |
|-------|-------------|
| Create Animated Render Cam | Adds `GS_RenderCam_Animated` with step-interpolated position keys—one key per viewpoint. |
| Replace Existing Rig | Removes any previous `GS_CameraRig` null before building a new one. |
| Auto Update Rig | Automatically rebuilds the rig when you change rig-related parameters. |
| Export Pose JSON | Writes a `camera_poses.json` file with per-frame transform matrices and intrinsics. |
| Export Synthetic COLMAP Data | Writes synthetic COLMAP data files (`cameras.txt`, `images.txt`, `points3D.txt`). |
| Sparse Point Count | Number of surface sample points used to build the sparse reconstruction (default: 30 000). |

### Action Buttons
| Button | Action |
|--------|--------|
| **Build Rig** | Builds or rebuilds only the camera rig (no export). |
| **Export COLMAP** | Re-exports just the synthetic COLMAP data files using current settings. |
| **Build & Export** | Builds the full camera rig, configures render settings, and writes all selected export files. |

---

## Export Layout

```
output_folder/
├── cameras.txt           # COLMAP intrinsics
├── images.txt            # COLMAP extrinsics + 2-D tracks
├── points3D.txt          # COLMAP sparse points
├── camera_poses.json     # NeRF / instant-ngp format (optional)
└── images/
    ├── gs_0000.png
    ├── gs_0001.png
    └── ...
```

---

## Lite Script

`c4d2gs_lite.py` is a standalone, no-UI version of the plugin intended for
power users who prefer to set parameters directly in the script header.
Run it from the Cinema 4D Script Manager (**Script ▸ Script Manager ▸ Execute**).

---

## Compatibility Notes

- `points3D.txt` uses synthetic sparse points sampled from the target surface.
- Visibility filtering includes a surface-normal facing check.
- Track observations are capped per point to stay close to typical COLMAP patterns.
- Point colors are written as white (`255 255 255`); downstream tools optimise
  color during reconstruction.
- `camera_poses.json` uses NeRF-style `file_path` entries with relative image
  names for portability across machines.

---

## File Structure

```
c4d2gs/
├── c4d2gs.pyp      ← main plugin file (all logic + UI)
└── README.md       ← plugin-folder documentation

c4d2gs_lite.py      ← standalone script (no UI, no install required)
```

---

## License

[CC BY-NC 4.0](LICENSE) — Creative Commons Attribution-NonCommercial 4.0 International.
