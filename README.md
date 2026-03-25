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
3. The plugin appears in the menu bar under **Extensions ▸ C4D2GS**.

> **Python version note** — requires Cinema 4D 2023 or later (Python 3).

---

## Quick Start

1. Open a scene containing the object you want to splat.
2. Open the plugin: **Extensions ▸ C4D2GS**.
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

## License

CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 International).
