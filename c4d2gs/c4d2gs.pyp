import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import c4d

from _constants import PLUGIN_ID, PLUGIN_NAME, PLUGIN_HELP
from _ui_dialog import C4D2GSCommand

if __name__ == "__main__":
    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str=PLUGIN_NAME,
        info=0,
        icon=None,
        help=PLUGIN_HELP,
        dat=C4D2GSCommand(),
    )
