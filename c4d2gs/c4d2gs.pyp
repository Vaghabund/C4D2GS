"""
C4D2GS — Cinema 4D to Gaussian Splat
======================================
A Cinema 4D Python plugin that generates synthetic COLMAP data for
Gaussian Splatting.  It places a sphere of cameras around any object,
configures the render settings to output one image per viewpoint, and writes
the accompanying synthetic COLMAP data files (cameras.txt / images.txt / points3D.txt) that
reconstruction tools can use to reconstruct the scene.

Installation
------------
Drop the entire ``c4d2gs`` folder into your Cinema 4D plugins directory:

    macOS  : ~/Library/Preferences/Maxon/Maxon Cinema 4D <version>/plugins/
    Windows: %APPDATA%\\Maxon\\Maxon Cinema 4D <version>\\plugins\\

Restart Cinema 4D.  The plugin appears under **Plugins ▸ C4D2GS**.

Plugin ID
---------
The plugin is registered under ID **1067868**.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Make the plugin directory importable so sub-modules can be found.
# ---------------------------------------------------------------------------
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import c4d

from _constants import PLUGIN_ID, PLUGIN_NAME, PLUGIN_HELP
from _ui_dialog import C4D2GSCommand

# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str=PLUGIN_NAME,
        info=0,
        icon=None,
        help=PLUGIN_HELP,
        dat=C4D2GSCommand(),
    )
