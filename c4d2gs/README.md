# C4D2GS — Cinema 4D to Gaussian Splat

A Cinema 4D Python plugin that generates **Postshot-compatible datasets** for
Gaussian Splatting.  It automates the whole capture-rig pipeline:

1. Places a configurable sphere of cameras around any object in your scene.
2. Sets up an **animated render camera** so rendering the animation produces
   one image per viewpoint automatically.
3. Writes **COLMAP files** (`cameras.txt`, `images.txt`, `points3D.txt`)
   that Postshot uses to initialise its reconstruction.
4. Optionally writes a **camera-pose JSON** with full intrinsics/extrinsics
   for custom pipelines.

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
2. Select the object in the viewport or Object Manager.
3. Open the plugin: **Plugins ▸ C4D2GS**.
4. In the **Target Object** field at the top of the dialog, confirm the object
   is linked (it is pre-filled from the active selection).
5. Click **Auto-Fit Radius** to compute a good sphere radius from the object's
   bounding box.
6. Set your **Output Folder** on the *Output* tab.  Type the full path including
   the filename pattern, e.g. `C:\renders\my_splat\gs_####`.  The `####` token
   is replaced by the zero-padded frame number for each image.  If you end the
   path with a directory separator (e.g. `C:\renders\my_splat\`), the plugin
   automatically appends `gs_####` for you — identical to clicking **Browse…**.
7. Click **Build & Export**.
8. Render the animation in Cinema 4D (`Render ▸ Render to Picture Viewer`, or
   use the Command Line Renderer for batch rendering).
9. Import the `postshot_colmap` sub-folder of your output directory into
   Postshot alongside the rendered image sequence.

---

## Dialog Reference

### Target Object
The object that cameras are placed around.  Use the link-box to assign any
scene object.  **Auto-Fit Radius** calculates a sphere radius 2.5× the
diagonal of the object's bounding box.

### Camera Tab
| Field | Description |
|-------|-------------|
| Camera Count | Number of viewpoints placed on the sphere. |
| Radius | Distance from the object centre to each camera. |
| Center Offset X/Y/Z | Shifts the sphere centre away from the object's pivot. |
| Sampling Mode | Algorithm used to distribute cameras: **Spiral** (default, even helical coverage), **Icosphere** (geodesic), **Fibonacci** (golden-angle). |
| Spiral Turns | Number of helical turns (Spiral mode only). |
| Pole Margin | Fraction of sphere height excluded near poles (Spiral mode only, 0–0.49). |

### Output Tab
| Field | Description |
|-------|-------------|
| Output Folder / Pattern | Base path for rendered images; `####` is the frame-number placeholder (e.g. `C:\renders\splat\gs_####`). |
| Format | Image format: PNG, JPG, TIF, or EXR. |
| Resolution | Width × Height in pixels. |
| FPS | Frames per second (affects timeline length only). |

### Export Tab
| Field | Description |
|-------|-------------|
| Create Animated Render Cam | Adds `GS_RenderCam_Animated` with step-interpolated position keys—one key per viewpoint. |
| Replace Existing Rig | Removes any previous `GS_CameraRig` null before building a new one. |
| Export Pose JSON | Writes a `camera_poses.json` file with per-frame transform matrices and intrinsics. |
| JSON File Path | Where to save the JSON file. |
| Export COLMAP | Writes `cameras.txt`, `images.txt`, and `points3D.txt` for Postshot. |
| Auto Intrinsics from Cam | Derives `fx/fy/cx/cy` from the render camera's focal length and sensor width. |
| Manual Intrinsics | Override values used when auto-intrinsics is off or unavailable. |
| Sparse Point Count | Number of surface sample points used to build the COLMAP sparse reconstruction (default: 256). |

### Action Buttons
| Button | Action |
|--------|--------|
| **Build & Export** | Builds the full camera rig, configures render settings, and writes all selected export files. |
| **COLMAP Only** | Re-exports just the COLMAP files using the current settings and the existing rig/intrinsics—useful after tweaking sparse-point count. |
| **Close** | Closes the dialog (settings are not persisted across restarts in this MVP). |

---

## Postshot Workflow

```
Cinema 4D                           Postshot
──────────────────────────────────  ─────────────────────────────────────
1. Build & Export  ──────────────>  postshot_colmap/
                                      cameras.txt
                                      images.txt
                                      points3D.txt
2. Render animation  ────────────>  gs_0000.png … gs_0119.png

3. In Postshot:
   File > New Project > COLMAP  <──  point at postshot_colmap folder
   and select the image folder
```

---

## Plugin ID

The plugin is registered under ID **1057843**.  This is a placeholder.  If you
plan to distribute the plugin commercially or share it publicly, request a
unique ID from Maxon at <https://developers.maxon.net> and replace the value of
`PLUGIN_ID` in `c4d2gs.pyp`.

---

## File Structure

```
c4d2gs/
├── c4d2gs.pyp   ← main plugin file (all logic + UI)
└── README.md    ← this file
```

---

## License

MIT — use freely, modify at will.
