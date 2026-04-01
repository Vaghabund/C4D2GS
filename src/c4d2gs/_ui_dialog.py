"""
C4D2GS — Plugin UI: dialog, widget IDs, and CommandData class.
"""

import c4d
import traceback
import os

from _constants import (
    PLUGIN_ID,
    PLUGIN_VERSION,
    RADIUS_MIN,
    RADIUS_MAX,
    ERROR_NO_DOCUMENT,
    ERROR_NO_TARGET,
    ERROR_NO_OUTPUT_PATH,
    ERROR_BUILD_FAILED,
    ERROR_COLMAP_FAILED,
)
from _settings import Settings, _load_settings, _save_settings, show_error_dialog
from _file_utils import _normalize_path
from _scene_builder import run_pipeline, create_or_update_rig, run_colmap_only


# ---------------------------------------------------------------------------
# Dialog — UI widget IDs
# ---------------------------------------------------------------------------

class _IDs:
    # ID ranges:
    # 1000–1099  core controls
    # 1100–1199  legacy tab controls (removed)
    # 1200–1299  mode selector and status fields (new)
    # 2000–2099  layout groups
    # 3000–3099  camera / distribution controls
    # 3100–3199  space tab controls
    # 4000–4099  additional cameras / anchor controls
    # 5000–5099  render/settings controls

    # 1000–1099: core controls
    TARGET_LINK = 1000
    CAM_COUNT = 1020
    RADIUS = 1021
    OBJ_SAMPLING_MODE = 1022  # Object-tab sphere sampling (was 1025; renamed to resolve duplicate)
    SPIRAL_TURNS = 1026
    SPIRAL_POLE = 1027
    OUTPUT_PATH = 1030
    OUTPUT_PATH_BROWSE = 1031
    OUTPUT_FORMAT = 1032
    RES_X = 1033
    RES_Y = 1034
    FPS = 1035
    STRAIGHT_ALPHA = 1036
    CREATE_ANIM_CAM = 1040
    REPLACE_RIG = 1041
    EXPORT_JSON = 1042
    EXPORT_COLMAP = 1045
    SPARSE_COUNT = 1052
    AUTO_UPDATE_RIG = 1053
    CAMERA_TYPE = 1055
    CHK_OVERWRITE = 1056
    BTN_CREATE_RIG = 1089
    BTN_EXECUTE = 1090
    BTN_COLMAP_ONLY = 1091
    BTN_CLOSE = 1092
    STATUS_TEXT = 1099

    # 1200–1299: mode selector and status fields (new)
    MODE_BTN_OBJECT = 1200
    MODE_BTN_SPACE = 1201
    STATUS_RENDER_CAM = 1202
    STATUS_LAST_EXPORT = 1203

    # 2000–2099: layout groups
    GRP_HEADER = 2000
    GRP_CAMERA_TAB = 2001
    GRP_OUTPUT_TAB = 2002
    GRP_EXPORT_TAB = 2003
    GRP_BUTTONS = 2004
    GRP_SPACE_TAB = 2005
    GRP_RENDER_TAB = 2006           # legacy; not created in new layout
    GRP_SPHERE = 2010
    GRP_DIST = 2011
    GRP_OUTPUT_PATH_ROW = 2012
    GRP_RES = 2014
    GRP_CONTENT = 2015              # dynamic content area (mode-swapped)
    GRP_SETTINGS = 2016             # settings panel (always visible)
    GRP_STATUS_FIELDS = 2017        # render-cam + last-export rows
    GRP_MODE_SELECTOR = 2018        # mode buttons row
    GRP_EXPORT_SETTINGS = 2019      # export checkboxes sub-group
    GRP_ADV_SETTINGS = 2020         # advanced sub-group
    GRP_ADDITIONAL_CAMS = 2021      # additional cameras sub-group
    GRP_AUTO_ANCHOR = 2022          # auto-anchor sub-group in space tab
    GRP_MANUAL_ANCHOR_WRAP = 2023   # manual-anchor sub-group in space tab
    GRP_CLUSTER = 2024              # cluster sub-group in space tab
    GRP_RIG = 2025                  # rig sub-group in object tab
    GRP_GRID_ROW = 2026             # grid N×M row
    GRP_SPARSE_ROW = 2027           # sparse points label+field row

    # 3000–3099: camera / distribution controls
    ANCHOR_MODE = 3005
    CLUSTER_CAM_COUNT = 3006
    CLUSTER_RADIUS = 3007
    SPACE_SAMPLING_MODE = 3008  # Space-tab cluster sampling (was SAMPLING_MODE=3008; renamed to resolve duplicate)
    AUTO_Y_HEIGHT = 3009
    # Legacy space controls (pre-refactor checkbox approach, no longer added to
    # the layout).  The IDs are retained so that any persisted settings from older
    # plugin versions can still be read safely in _read_ui via try/except.
    MANUAL_ANCHOR_CHECKBOX = 3013
    MANUAL_ANCHOR_GROUP = 3014
    MANUAL_ANCHOR_GROUP_FIELD = 3015
    MANUAL_Y_HEIGHT_CHECKBOX = 3016
    MANUAL_Y_HEIGHT_GROUP = 3017
    MANUAL_Y_HEIGHT_FIELD = 3018

    # 3100–3199: space tab controls (new)
    GRID_LAYOUT = 3100
    GRID_X = 3101
    GRID_Y = 3102

    # 4000–4099: additional cameras / anchor controls
    ADDITIONAL_CAMERAS_GROUP = 4000
    ADDITIONAL_CAMERAS_GROUP_FIELD = 4010

    # 5000–5099: render/settings controls
    RENDER_ENGINE = 5000
    RENDER_USE_GLOBAL = 5001
    RENDER_SAMPLES = 5002
    RENDER_CAMERA = 5003


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------

class C4D2GSDialog(c4d.gui.GeDialog):

    def __init__(self):
        super(C4D2GSDialog, self).__init__()
        self._settings = Settings()
        _load_settings(self._settings)
        self._target_obj = None
        self._target_link_gui = None
        self._additional_cameras_gui = None
        self._is_auto_updating = False
        self._values_ready = False
        self._current_mode = int(getattr(self._settings, "last_mode", 0))

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def CreateLayout(self):
        try:
            self.SetTitle("C4D2GS  —  Synthetic COLMAP Data Generator  v{}".format(PLUGIN_VERSION))

            # ---- Mode selector ----
            self.GroupBegin(_IDs.GRP_MODE_SELECTOR, c4d.BFH_SCALEFIT, cols=2, rows=1)
            self.GroupBorderSpace(6, 6, 6, 4)
            self.AddButton(_IDs.MODE_BTN_OBJECT, c4d.BFH_SCALEFIT, 0, 0, "Object Mode")
            self.AddButton(_IDs.MODE_BTN_SPACE, c4d.BFH_SCALEFIT, 0, 0, "Space Mode")
            self.GroupEnd()

            # ---- Content area (dynamically swapped on mode change) ----
            self.GroupBegin(_IDs.GRP_CONTENT, c4d.BFH_SCALEFIT, cols=1, rows=0)
            self.GroupBorderSpace(0, 0, 0, 0)
            self._build_mode_content(self._current_mode)
            self.GroupEnd()

            # ---- Settings panel (always visible) ----
            _fold_in = getattr(c4d, "BORDER_GROUP_IN", 0)
            self.GroupBegin(_IDs.GRP_SETTINGS, c4d.BFH_SCALEFIT, cols=1,
                            title="Settings", groupflags=_fold_in)
            self.GroupBorderSpace(6, 4, 6, 6)
            self._build_settings_panel()
            self.GroupEnd()

            # ---- Action buttons ----
            self.GroupBegin(_IDs.GRP_BUTTONS, c4d.BFH_SCALEFIT, cols=3, rows=1)
            self.GroupBorderSpace(6, 6, 6, 4)
            self.AddButton(_IDs.BTN_CREATE_RIG, c4d.BFH_SCALEFIT, 0, 0, "  Build Rig  ")
            self.AddButton(_IDs.BTN_COLMAP_ONLY, c4d.BFH_SCALEFIT, 0, 0, "  Export COLMAP  ")
            self.AddButton(_IDs.BTN_EXECUTE, c4d.BFH_SCALEFIT, 0, 0, "  Build & Export  ")
            self.GroupEnd()

            # ---- Render-camera and last-export status fields ----
            self.GroupBegin(_IDs.GRP_STATUS_FIELDS, c4d.BFH_SCALEFIT, cols=2)
            self.GroupBorderSpace(6, 2, 6, 2)
            self.AddStaticText(6300, c4d.BFH_LEFT, 100, 0, "Render Camera:")
            self.AddStaticText(_IDs.STATUS_RENDER_CAM, c4d.BFH_SCALEFIT, 0, 0, u"\u2014")
            self.AddStaticText(6301, c4d.BFH_LEFT, 100, 0, "Last Export:")
            self.AddStaticText(_IDs.STATUS_LAST_EXPORT, c4d.BFH_SCALEFIT, 0, 0, "")
            self.GroupEnd()

            # Legacy status text (compatibility with _refresh_status / auto-update)
            self.AddStaticText(_IDs.STATUS_TEXT, c4d.BFH_SCALEFIT, 0, 0,
                               "Select a target object and click Build & Export.")

            return True
        except Exception as exc:
            try:
                c4d.gui.MessageDialog("C4D2GS UI failed to build:\n{}".format(str(exc)))
            except Exception:
                pass
            try:
                self.GroupBegin(900, c4d.BFH_SCALEFIT, cols=1)
                self.AddStaticText(901, c4d.BFH_SCALEFIT, 0, 0,
                                   "C4D2GS — UI failed to build. See console.")
                self.GroupEnd()
            except Exception:
                pass
            return True

    # ------------------------------------------------------------------
    # Mode content builder
    # ------------------------------------------------------------------

    def _build_mode_content(self, mode):
        """Build Object (mode=0) or Space (mode=1) content into the current group context."""
        if mode == 0:
            self._build_object_tab()
        else:
            self._build_space_tab()

    # ------------------------------------------------------------------
    # Object mode content
    # ------------------------------------------------------------------

    def _build_object_tab(self):
        """Build Object-mode widgets.  Called inside GRP_CONTENT context."""
        _bi = getattr(c4d, "BORDER_GROUP_IN", 0)

        # Target Object
        self.GroupBegin(2040, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.GroupBorderSpace(6, 4, 6, 2)
        self.AddStaticText(6000, c4d.BFH_LEFT, 110, 0, "Target Object")
        self.AddCustomGui(
            _IDs.TARGET_LINK, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )
        try:
            self._target_link_gui = self.GetCustomGui(_IDs.TARGET_LINK)
        except Exception:
            self._target_link_gui = None
        self.GroupEnd()

        # — Rig —
        self.GroupBegin(_IDs.GRP_RIG, c4d.BFH_SCALEFIT, cols=2,
                        title="Rig", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6001, c4d.BFH_LEFT, 0, 0, "Camera Count")
        self.AddEditNumberArrows(_IDs.CAM_COUNT, c4d.BFH_SCALEFIT)

        self.AddStaticText(6002, c4d.BFH_LEFT, 0, 0, "Radius")
        if hasattr(self, "AddEditSlider"):
            self.AddEditSlider(_IDs.RADIUS, c4d.BFH_SCALEFIT)
        else:
            self.AddEditNumberArrows(_IDs.RADIUS, c4d.BFH_SCALEFIT)

        self.AddStaticText(6003, c4d.BFH_LEFT, 0, 0, "Camera Type")
        self.AddComboBox(_IDs.CAMERA_TYPE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.CAMERA_TYPE, 0, "Standard")
        self.AddChild(_IDs.CAMERA_TYPE, 1, "Redshift RSCamera")

        self.GroupEnd()  # GRP_RIG

        # — Distribution —
        self.GroupBegin(_IDs.GRP_DIST, c4d.BFH_SCALEFIT, cols=2,
                        title="Distribution", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6004, c4d.BFH_LEFT, 0, 0, "Sampling Mode")
        self.AddComboBox(_IDs.OBJ_SAMPLING_MODE, c4d.BFH_SCALEFIT)
        for mode_id, label in [(0, "Spiral"), (1, "Icosphere"), (2, "Fibonacci")]:
            self.AddChild(_IDs.OBJ_SAMPLING_MODE, mode_id, label)

        self.AddStaticText(6005, c4d.BFH_LEFT, 0, 0, "Spiral Turns")
        self.AddEditNumberArrows(_IDs.SPIRAL_TURNS, c4d.BFH_SCALEFIT)

        self.AddStaticText(6006, c4d.BFH_LEFT, 0, 0, "Pole Margin")
        self.AddEditNumberArrows(_IDs.SPIRAL_POLE, c4d.BFH_SCALEFIT)

        self.GroupEnd()  # GRP_DIST

        # — Additional Cameras — (collapsed by default)
        self.GroupBegin(_IDs.GRP_ADDITIONAL_CAMS, c4d.BFH_SCALEFIT, cols=2,
                        title="Additional Cameras", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6007, c4d.BFH_LEFT, 0, 0, "Camera Group")
        self.AddCustomGui(
            _IDs.ADDITIONAL_CAMERAS_GROUP_FIELD, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )
        try:
            self._additional_cameras_gui = self.GetCustomGui(
                _IDs.ADDITIONAL_CAMERAS_GROUP_FIELD
            )
        except Exception:
            self._additional_cameras_gui = None

        self.GroupEnd()  # GRP_ADDITIONAL_CAMS

    # ------------------------------------------------------------------
    # Space mode content
    # ------------------------------------------------------------------

    def _build_space_tab(self):
        """Build Space-mode widgets.  Called inside GRP_CONTENT context."""
        _bi = getattr(c4d, "BORDER_GROUP_IN", 0)

        # Anchor Mode row
        self.GroupBegin(2050, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.GroupBorderSpace(6, 4, 6, 2)
        self.AddStaticText(6100, c4d.BFH_LEFT, 110, 0, "Anchor Mode")
        self.AddComboBox(_IDs.ANCHOR_MODE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.ANCHOR_MODE, 0, "Auto")
        self.AddChild(_IDs.ANCHOR_MODE, 1, "Manual")
        self.GroupEnd()

        # — Auto — (visible when Auto selected)
        self.GroupBegin(_IDs.GRP_AUTO_ANCHOR, c4d.BFH_SCALEFIT, cols=2,
                        title="Auto", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6101, c4d.BFH_LEFT, 0, 0, "Y Height")
        self.AddEditNumberArrows(_IDs.AUTO_Y_HEIGHT, c4d.BFH_SCALEFIT)

        self.AddStaticText(6102, c4d.BFH_LEFT, 0, 0, "Layout")
        self.AddComboBox(_IDs.GRID_LAYOUT, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.GRID_LAYOUT, 0, "Grid")
        self.AddChild(_IDs.GRID_LAYOUT, 1, "Random")

        self.AddStaticText(6103, c4d.BFH_LEFT, 0, 0, "Grid")
        self.GroupBegin(_IDs.GRP_GRID_ROW, c4d.BFH_SCALEFIT, cols=3, rows=1)
        self.AddEditNumber(_IDs.GRID_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(6104, c4d.BFH_CENTER, 0, 0, u"\u00d7")
        self.AddEditNumber(_IDs.GRID_Y, c4d.BFH_SCALEFIT)
        self.GroupEnd()  # GRP_GRID_ROW

        self.GroupEnd()  # GRP_AUTO_ANCHOR

        # — Manual — (visible when Manual selected)
        self.GroupBegin(_IDs.GRP_MANUAL_ANCHOR_WRAP, c4d.BFH_SCALEFIT, cols=2,
                        title="Manual", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6105, c4d.BFH_LEFT, 0, 0, "Anchor Group")
        self.AddCustomGui(
            _IDs.MANUAL_ANCHOR_GROUP_FIELD, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )

        self.GroupEnd()  # GRP_MANUAL_ANCHOR_WRAP

        # — Cluster —
        self.GroupBegin(_IDs.GRP_CLUSTER, c4d.BFH_SCALEFIT, cols=2,
                        title="Cluster", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6106, c4d.BFH_LEFT, 0, 0, "Cameras per Cluster")
        self.AddEditNumberArrows(_IDs.CLUSTER_CAM_COUNT, c4d.BFH_SCALEFIT)

        self.AddStaticText(6107, c4d.BFH_LEFT, 0, 0, "Cluster Radius")
        self.AddEditNumberArrows(_IDs.CLUSTER_RADIUS, c4d.BFH_SCALEFIT)

        self.AddStaticText(6108, c4d.BFH_LEFT, 0, 0, "Sampling Mode")
        self.AddComboBox(_IDs.SPACE_SAMPLING_MODE, c4d.BFH_SCALEFIT)
        for mode_id, label in [(0, "Spiral"), (1, "Icosphere"), (2, "Fibonacci")]:
            self.AddChild(_IDs.SPACE_SAMPLING_MODE, mode_id, label)

        self.GroupEnd()  # GRP_CLUSTER

    # ------------------------------------------------------------------
    # Settings panel
    # ------------------------------------------------------------------

    def _build_settings_panel(self):
        """Build the always-visible settings panel (Output + Export + Advanced)."""
        _bi = getattr(c4d, "BORDER_GROUP_IN", 0)

        # — Output —
        self.GroupBegin(_IDs.GRP_OUTPUT_TAB, c4d.BFH_SCALEFIT, cols=2,
                        title="Output", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(6200, c4d.BFH_LEFT, 0, 0, "Path")
        self.GroupBegin(_IDs.GRP_OUTPUT_PATH_ROW, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.AddEditText(_IDs.OUTPUT_PATH, c4d.BFH_SCALEFIT)
        self.AddButton(_IDs.OUTPUT_PATH_BROWSE, c4d.BFH_RIGHT, 0, 0, "Browse\u2026")
        self.GroupEnd()

        self.AddStaticText(6201, c4d.BFH_LEFT, 0, 0, "Format")
        self.AddComboBox(_IDs.OUTPUT_FORMAT, c4d.BFH_SCALEFIT)
        for fmt_id, fmt_name in self._output_format_items():
            self.AddChild(_IDs.OUTPUT_FORMAT, int(fmt_id), fmt_name)

        self.AddStaticText(6202, c4d.BFH_LEFT, 0, 0, "Resolution")
        self.GroupBegin(_IDs.GRP_RES, c4d.BFH_SCALEFIT, cols=3, rows=1)
        self.AddEditNumber(_IDs.RES_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(6203, c4d.BFH_CENTER, 0, 0, u"\u00d7")
        self.AddEditNumber(_IDs.RES_Y, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.AddStaticText(6204, c4d.BFH_LEFT, 0, 0, "FPS")
        self.AddEditNumberArrows(_IDs.FPS, c4d.BFH_SCALEFIT)

        self.GroupEnd()  # GRP_OUTPUT_TAB

        # — Export —
        self.GroupBegin(_IDs.GRP_EXPORT_TAB, c4d.BFH_SCALEFIT, cols=1,
                        title="Export", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddCheckbox(_IDs.EXPORT_COLMAP, c4d.BFH_LEFT, 0, 0,
                         "Export COLMAP files")
        self.AddCheckbox(_IDs.EXPORT_JSON, c4d.BFH_LEFT, 0, 0,
                         "Export camera_poses.json")
        self.AddCheckbox(_IDs.CREATE_ANIM_CAM, c4d.BFH_LEFT, 0, 0,
                         "Create animated render camera")
        self.AddCheckbox(_IDs.REPLACE_RIG, c4d.BFH_LEFT, 0, 0,
                         "Replace existing rig on rebuild")
        self.AddCheckbox(_IDs.CHK_OVERWRITE, c4d.BFH_LEFT, 0, 0,
                         "Override existing export folder")

        self.GroupBegin(_IDs.GRP_SPARSE_ROW, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.AddStaticText(6205, c4d.BFH_LEFT, 0, 0, "Sparse Points")
        self.AddEditNumberArrows(_IDs.SPARSE_COUNT, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.GroupEnd()  # GRP_EXPORT_TAB

        # — Advanced — (collapsed by default)
        self.GroupBegin(_IDs.GRP_ADV_SETTINGS, c4d.BFH_SCALEFIT, cols=1,
                        title="Advanced", groupflags=_bi)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddCheckbox(_IDs.STRAIGHT_ALPHA, c4d.BFH_LEFT, 0, 0,
                         "Straight Alpha")
        self.AddCheckbox(_IDs.AUTO_UPDATE_RIG, c4d.BFH_LEFT, 0, 0,
                         "Auto Update Rig")

        self.GroupEnd()  # GRP_ADV_SETTINGS

    @staticmethod
    def _output_format_items():
        items = []
        for label, const_name in [("PNG", "FILTER_PNG"), ("JPG", "FILTER_JPG"),
                                   ("TIF", "FILTER_TIF"), ("EXR", "FILTER_EXR")]:
            val = getattr(c4d, const_name, None)
            if val is not None:
                items.append((val, label))
        return items

    # ------------------------------------------------------------------
    # Value initialisation
    # ------------------------------------------------------------------

    def InitValues(self):
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        # Restore mode from settings
        self._current_mode = int(getattr(s, "last_mode", 0))

        # Initialise mode-specific widgets
        self._init_mode_values(self._current_mode)

        # Settings panel widgets (always present)
        self.SetString(_IDs.OUTPUT_PATH, str(s.output_folder()))
        self.SetInt32(_IDs.OUTPUT_FORMAT, int(s.output_format))
        self._si(_IDs.RES_X, s.res_x, 1, 65535)
        self._si(_IDs.RES_Y, s.res_y, 1, 65535)
        self._si(_IDs.FPS, s.fps, 1, 1000)
        self.SetBool(_IDs.EXPORT_COLMAP, bool(s.export_colmap))
        self.SetBool(_IDs.EXPORT_JSON, bool(s.export_json))
        self.SetBool(_IDs.CREATE_ANIM_CAM, bool(s.create_anim_cam))
        self.SetBool(_IDs.REPLACE_RIG, bool(s.replace_rig))
        self.SetBool(_IDs.CHK_OVERWRITE, bool(getattr(s, "overwrite_export", False)))
        self._si(_IDs.SPARSE_COUNT, s.sparse_count, 8, 100000)
        self.SetBool(_IDs.STRAIGHT_ALPHA, bool(s.straight_alpha))
        self.SetBool(_IDs.AUTO_UPDATE_RIG, bool(s.auto_update_rig))

        # SetBool(grp_id, False) collapses BORDER_GROUP_IN groups on C4D versions
        # that expose the fold state as a bool.  Wrapped in try/except for versions
        # where this has no effect.
        for grp_id in [_IDs.GRP_ADV_SETTINGS, _IDs.GRP_ADDITIONAL_CAMS]:
            try:
                self.SetBool(grp_id, False)
            except Exception:
                pass

        # Restore last export path status field
        try:
            last_path = str(getattr(s, "last_export_path", ""))
            self.SetString(_IDs.STATUS_LAST_EXPORT, last_path)
        except Exception:
            pass

        self._refresh_status()
        self._values_ready = True
        return True

    def _init_mode_values(self, mode):
        """Initialise widget values for the given mode after content is built."""
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        if mode == 0:
            # Object mode
            self._target_obj = self._resolve_target_object(doc)
            if self._target_obj is not None:
                self._set_link_target(self._target_obj)
            self._si(_IDs.CAM_COUNT, s.camera_count, 1, 100000)
            self._sf(_IDs.RADIUS, s.sphere_radius, RADIUS_MIN, RADIUS_MAX, 1.0)
            self.SetInt32(_IDs.CAMERA_TYPE, int(getattr(s, "camera_type", 0)))
            self.SetInt32(_IDs.OBJ_SAMPLING_MODE, int(s.sampling_mode))
            self._sf(_IDs.SPIRAL_TURNS, s.spiral_turns, 0.01, 1e6, 0.1)
            self._sf(_IDs.SPIRAL_POLE, s.spiral_pole_margin, 0.0, 0.49, 0.001)
            self._update_spiral_ui()
        else:
            # Space mode
            try:
                self.SetInt32(_IDs.ANCHOR_MODE, int(getattr(s, "anchor_mode", 0)))
            except Exception:
                pass
            try:
                self._sf(_IDs.AUTO_Y_HEIGHT,
                         float(getattr(s, "auto_y_height", 0.0)), -1e6, 1e6, 0.1)
            except Exception:
                pass
            try:
                self.SetInt32(_IDs.GRID_LAYOUT, int(getattr(s, "grid_layout", 0)))
            except Exception:
                pass
            try:
                self._si(_IDs.GRID_X, int(getattr(s, "grid_x", 3)), 1, 1000)
            except Exception:
                pass
            try:
                self._si(_IDs.GRID_Y, int(getattr(s, "grid_y", 3)), 1, 1000)
            except Exception:
                pass
            try:
                self._si(_IDs.CLUSTER_CAM_COUNT,
                         int(getattr(s, "cluster_cam_count", 1)), 1, 10000)
            except Exception:
                pass
            try:
                self._sf(_IDs.CLUSTER_RADIUS,
                         float(getattr(s, "cluster_radius", 10.0)), 0.01, 1e6, 0.1)
            except Exception:
                pass
            try:
                self.SetInt32(_IDs.SPACE_SAMPLING_MODE, int(s.sampling_mode))
            except Exception:
                pass
            self._update_anchor_mode_ui()

    def _update_spiral_ui(self):
        """Enable/disable Spiral Turns and Pole Margin based on OBJ_SAMPLING_MODE."""
        try:
            spiral_enabled = int(self.GetInt32(_IDs.OBJ_SAMPLING_MODE)) == 0
        except Exception:
            spiral_enabled = (int(getattr(self._settings, "sampling_mode", 0)) == 0)
        for cid in [6005, _IDs.SPIRAL_TURNS, 6006, _IDs.SPIRAL_POLE]:
            try:
                self.Enable(cid, spiral_enabled)
            except Exception:
                pass

    def _update_anchor_mode_ui(self):
        """Show Auto or Manual sub-group based on ANCHOR_MODE dropdown."""
        try:
            anchor_mode = int(self.GetInt32(_IDs.ANCHOR_MODE))
        except Exception:
            anchor_mode = int(getattr(self._settings, "anchor_mode", 0))
        is_auto = (anchor_mode == 0)
        for grp_id, show in [(_IDs.GRP_AUTO_ANCHOR, is_auto),
                              (_IDs.GRP_MANUAL_ANCHOR_WRAP, not is_auto)]:
            try:
                self.HideElement(grp_id, not show)
            except Exception:
                try:
                    self.Enable(grp_id, show)
                except Exception:
                    pass
        try:
            self.LayoutChanged(_IDs.GRP_CONTENT)
        except Exception:
            pass

    def _si(self, cid, value, mn, mx):
        try:
            self.SetInt32(cid, int(value), int(mn), int(mx))
        except TypeError:
            self.SetInt32(cid, int(value))

    def _sf(self, cid, value, mn, mx, step=0.1):
        try:
            self.SetFloat(cid, float(value), float(mn), float(mx), float(step))
        except TypeError:
            self.SetFloat(cid, float(value))

    # ------------------------------------------------------------------
    # Read UI → Settings
    # ------------------------------------------------------------------

    def _read_ui(self):
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        # Object mode fields
        link_obj = self._get_link_target(doc)
        if link_obj is not None:
            self._target_obj = link_obj
        elif self._target_obj is None:
            self._target_obj = self._resolve_target_object(doc)
        if self._target_obj is not None:
            self._set_link_target(self._target_obj)

        try:
            s.camera_count = max(1, int(self.GetInt32(_IDs.CAM_COUNT)))
        except Exception:
            pass
        try:
            s.sphere_radius = max(RADIUS_MIN,
                                  min(RADIUS_MAX, float(self.GetFloat(_IDs.RADIUS))))
        except Exception:
            pass
        try:
            s.camera_type = int(self.GetInt32(_IDs.CAMERA_TYPE))
        except Exception:
            pass
        try:
            s.sampling_mode = int(self.GetInt32(_IDs.OBJ_SAMPLING_MODE))
        except Exception:
            pass
        try:
            s.spiral_turns = max(0.01, float(self.GetFloat(_IDs.SPIRAL_TURNS)))
        except Exception:
            pass
        try:
            s.spiral_pole_margin = max(0.0,
                                       min(0.49, float(self.GetFloat(_IDs.SPIRAL_POLE))))
        except Exception:
            pass

        # Space mode fields
        try:
            s.anchor_mode = int(self.GetInt32(_IDs.ANCHOR_MODE))
        except Exception:
            pass

        # Manual anchor group link
        manual_group = None
        try:
            manual_group = self.GetLink(_IDs.MANUAL_ANCHOR_GROUP_FIELD,
                                        getattr(c4d, "BaseObject", None))
        except Exception:
            manual_group = None
        s.anchor_null_group = manual_group

        try:
            s.auto_y_height = float(self.GetFloat(_IDs.AUTO_Y_HEIGHT))
        except Exception:
            pass
        try:
            s.grid_layout = int(self.GetInt32(_IDs.GRID_LAYOUT))
        except Exception:
            pass
        try:
            s.grid_x = max(1, int(self.GetInt32(_IDs.GRID_X)))
        except Exception:
            pass
        try:
            s.grid_y = max(1, int(self.GetInt32(_IDs.GRID_Y)))
        except Exception:
            pass
        try:
            s.cluster_cam_count = max(1, int(self.GetInt32(_IDs.CLUSTER_CAM_COUNT)))
        except Exception:
            pass
        try:
            s.cluster_radius = float(self.GetFloat(_IDs.CLUSTER_RADIUS))
        except Exception:
            pass
        try:
            # In space mode, SPACE_SAMPLING_MODE drives the cluster distribution via
            # generate_unit_points(settings), which reads settings.sampling_mode.
            # In object mode, OBJ_SAMPLING_MODE is already handled above; we skip
            # the space widget read so the object-mode value is not overwritten.
            if self._current_mode == 1:
                s.sampling_mode = int(self.GetInt32(_IDs.SPACE_SAMPLING_MODE))
        except Exception:
            pass

        # Legacy space fields (kept for backward compatibility; widgets may not exist)
        try:
            s.manual_anchor_enabled = bool(self.GetBool(_IDs.MANUAL_ANCHOR_CHECKBOX))
        except Exception:
            pass
        try:
            s.manual_y_height_enabled = bool(self.GetBool(_IDs.MANUAL_Y_HEIGHT_CHECKBOX))
        except Exception:
            pass
        try:
            s.manual_y_height = float(self.GetFloat(_IDs.MANUAL_Y_HEIGHT_FIELD))
        except Exception:
            pass

        # Settings panel fields (always present)
        try:
            s.overwrite_export = bool(self.GetBool(_IDs.CHK_OVERWRITE))
        except Exception:
            pass
        try:
            raw_path = self.GetString(_IDs.OUTPUT_PATH).strip()
            normalised = _normalize_path(raw_path)
            if normalised:
                s.output_path = normalised
                self.SetString(_IDs.OUTPUT_PATH, normalised)
        except Exception:
            pass
        try:
            s.output_format = int(self.GetInt32(_IDs.OUTPUT_FORMAT))
        except Exception:
            pass
        try:
            s.res_x = max(1, int(self.GetInt32(_IDs.RES_X)))
        except Exception:
            pass
        try:
            s.res_y = max(1, int(self.GetInt32(_IDs.RES_Y)))
        except Exception:
            pass
        try:
            s.fps = max(1, int(self.GetInt32(_IDs.FPS)))
        except Exception:
            pass
        try:
            s.export_colmap = bool(self.GetBool(_IDs.EXPORT_COLMAP))
        except Exception:
            pass
        try:
            s.export_json = bool(self.GetBool(_IDs.EXPORT_JSON))
        except Exception:
            pass
        try:
            s.create_anim_cam = bool(self.GetBool(_IDs.CREATE_ANIM_CAM))
        except Exception:
            pass
        try:
            s.replace_rig = bool(self.GetBool(_IDs.REPLACE_RIG))
        except Exception:
            pass
        try:
            s.sparse_count = max(8, int(self.GetInt32(_IDs.SPARSE_COUNT)))
        except Exception:
            pass
        try:
            s.straight_alpha = bool(self.GetBool(_IDs.STRAIGHT_ALPHA))
        except Exception:
            pass
        try:
            s.auto_update_rig = bool(self.GetBool(_IDs.AUTO_UPDATE_RIG))
        except Exception:
            pass

        # Legacy render tab fields (widgets not present in new layout; reads fall back
        # to cached settings values via try/except)
        try:
            s.render_engine = int(self.GetInt32(_IDs.RENDER_ENGINE))
        except Exception:
            pass
        try:
            s.render_use_global = bool(self.GetBool(_IDs.RENDER_USE_GLOBAL))
        except Exception:
            pass
        try:
            s.render_samples = max(1, int(self.GetInt32(_IDs.RENDER_SAMPLES)))
        except Exception:
            pass

        if self._current_mode == 0:
            self._update_spiral_ui()

    # ------------------------------------------------------------------
    # Mode switcher
    # ------------------------------------------------------------------

    def _switch_mode(self, new_mode):
        """Switch the content area to new_mode (0=Object, 1=Space)."""
        if self._values_ready:
            try:
                self._read_ui()
                _save_settings(self._settings)
            except Exception:
                pass

        self._current_mode = new_mode
        self._settings.last_mode = new_mode

        try:
            self.LayoutFlushChilds(_IDs.GRP_CONTENT)
            self._build_mode_content(new_mode)
            self.LayoutChanged(_IDs.GRP_CONTENT)
            self._init_mode_values(new_mode)
        except Exception:
            c4d.GePrint("[C4D2GS] _switch_mode error:\n{}".format(traceback.format_exc()))

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _refresh_status(self):
        status = "Version: {}".format(PLUGIN_VERSION)
        try:
            self.SetString(_IDs.STATUS_TEXT, status)
        except Exception:
            pass
        self._refresh_render_cam_status()

    def _refresh_render_cam_status(self):
        """Update the Render Camera status field from the active render data."""
        cam_name = u"\u2014"
        try:
            doc = c4d.documents.GetActiveDocument()
            if doc is not None:
                rd = doc.GetActiveRenderData()
                if rd is not None:
                    cam_obj = rd[c4d.RDATA_CAMERA]
                    if cam_obj is not None:
                        cam_name = cam_obj.GetName()
        except Exception:
            pass
        try:
            self.SetString(_IDs.STATUS_RENDER_CAM, cam_name)
        except Exception:
            pass

    def _refresh_last_export(self, folder_path):
        """Update the Last Export status field and persist it."""
        try:
            self._settings.last_export_path = str(folder_path)
            _save_settings(self._settings)
        except Exception:
            pass
        try:
            self.SetString(_IDs.STATUS_LAST_EXPORT, str(folder_path))
        except Exception:
            pass

    def _try_auto_update_rig(self, cid):
        if self._is_auto_updating:
            return
        if not bool(self._settings.auto_update_rig):
            return
        skip_ids = {
            _IDs.BTN_CREATE_RIG,
            _IDs.BTN_EXECUTE,
            _IDs.BTN_COLMAP_ONLY,
            _IDs.BTN_CLOSE,
            _IDs.OUTPUT_PATH_BROWSE,
        }
        if cid in skip_ids:
            return
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        obj = self._resolve_target_object(doc)
        if obj is None:
            return
        self._target_obj = obj
        self._is_auto_updating = True
        try:
            self.SetString(_IDs.STATUS_TEXT, "Auto-updating rig\u2026")
            create_or_update_rig(doc, self._settings, obj)
        except Exception:
            pass
        finally:
            self._is_auto_updating = False

    def _resolve_target_object(self, doc):
        link_obj = self._get_link_target(doc)
        for candidate in [link_obj, self._target_obj]:
            if candidate is not None:
                return candidate
        return None

    def _get_link_target(self, doc):
        if self._target_link_gui is not None:
            gui_get = getattr(self._target_link_gui, "GetLink", None)
            if callable(gui_get):
                link_args = []
                obase = getattr(c4d, "Obase", None)
                if doc is not None and obase is not None:
                    link_args.append((doc, obase))
                if doc is not None:
                    link_args.append((doc, getattr(c4d, "BaseObject", None)))
                    link_args.append((doc, getattr(c4d, "BaseList2D", None)))
                link_args.append(tuple())
                for args in link_args:
                    if len(args) == 2 and args[1] is None:
                        continue
                    try:
                        obj = gui_get(*args)
                    except Exception:
                        obj = None
                    if obj is not None:
                        return obj

        for arg in [doc, getattr(c4d, "BaseObject", None),
                    getattr(c4d, "BaseList2D", None)]:
            if arg is None:
                continue
            try:
                obj = self.GetLink(_IDs.TARGET_LINK, arg)
            except Exception:
                obj = None
            if obj is not None:
                return obj
        try:
            obj = self.GetLink(_IDs.TARGET_LINK)
        except Exception:
            obj = None
        if obj is not None:
            return obj
        try:
            obj = self.GetLink(_IDs.TARGET_LINK, None)
        except Exception:
            obj = None
        return obj

    def _set_link_target(self, obj):
        if obj is None:
            return
        if self._target_link_gui is not None:
            gui_set = getattr(self._target_link_gui, "SetLink", None)
            if callable(gui_set):
                try:
                    gui_set(obj)
                    return
                except Exception:
                    pass
        try:
            self.SetLink(_IDs.TARGET_LINK, obj)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def Command(self, cid, msg):
        # Mode selector buttons
        if cid == _IDs.MODE_BTN_OBJECT:
            self._switch_mode(0)
            if self._values_ready:
                _save_settings(self._settings)
            return True

        if cid == _IDs.MODE_BTN_SPACE:
            self._switch_mode(1)
            if self._values_ready:
                _save_settings(self._settings)
            return True

        if cid == _IDs.TARGET_LINK:
            doc = c4d.documents.GetActiveDocument()
            link_obj = self._get_link_target(doc)
            if link_obj is not None:
                self._target_obj = link_obj
                if self._values_ready:
                    self._read_ui()
                    _save_settings(self._settings)
            self._refresh_status()
            return True

        if cid == _IDs.ANCHOR_MODE:
            self._update_anchor_mode_ui()
            if self._values_ready:
                self._read_ui()
                _save_settings(self._settings)
            return True

        if cid == _IDs.OUTPUT_PATH_BROWSE:
            picked = c4d.storage.LoadDialog(
                flags=c4d.FILESELECT_DIRECTORY,
                title="Select Export Output Path",
            )
            if picked:
                self.SetString(_IDs.OUTPUT_PATH, _normalize_path(picked))
                if self._values_ready:
                    self._read_ui()
                    _save_settings(self._settings)
            return True

        # Legacy checkbox handlers (kept for backward compatibility)
        if cid == _IDs.MANUAL_ANCHOR_CHECKBOX:
            enabled = bool(self.GetBool(_IDs.MANUAL_ANCHOR_CHECKBOX))
            try:
                self.Enable(_IDs.MANUAL_ANCHOR_GROUP, enabled)
                self.Enable(_IDs.MANUAL_ANCHOR_GROUP_FIELD, enabled)
            except Exception:
                pass
            if self._values_ready:
                self._read_ui()
                _save_settings(self._settings)
            return True

        if cid == _IDs.MANUAL_Y_HEIGHT_CHECKBOX:
            enabled = bool(self.GetBool(_IDs.MANUAL_Y_HEIGHT_CHECKBOX))
            try:
                self.Enable(_IDs.MANUAL_Y_HEIGHT_GROUP, enabled)
                self.Enable(_IDs.MANUAL_Y_HEIGHT_FIELD, enabled)
            except Exception:
                pass
            if self._values_ready:
                self._read_ui()
                _save_settings(self._settings)
            return True

        if cid == _IDs.BTN_CREATE_RIG:
            self._read_ui()
            doc = c4d.documents.GetActiveDocument()
            if doc is None:
                show_error_dialog(ERROR_NO_DOCUMENT, "No active Cinema 4D document.")
                return True
            obj = self._resolve_target_object(doc)
            if obj is None:
                show_error_dialog(
                    ERROR_NO_TARGET,
                    "No target object selected.",
                    "Assign a target in the Target Object field in the dialog.",
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Creating rig\u2026")
            try:
                result = create_or_update_rig(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                c4d.gui.MessageDialog(
                    "Camera rig ready.\n\n"
                    "Object:  {}\n"
                    "Cameras: {}\n"
                    "Mode:    {}\n\n"
                    "Tip: tweak parameters and click Build Rig again to "
                    "iterate quickly.".format(
                        result.get("target_name", "?"),
                        result.get("camera_count", 0),
                        result.get("mode", "?"),
                    )
                )
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_BUILD_FAILED, "Rig creation failed.", exc)
            return True

        if cid == _IDs.BTN_EXECUTE:
            self._read_ui()
            doc = c4d.documents.GetActiveDocument()
            if doc is None:
                show_error_dialog(ERROR_NO_DOCUMENT, "No active Cinema 4D document.")
                return True
            obj = self._resolve_target_object(doc)
            if obj is None:
                show_error_dialog(
                    ERROR_NO_TARGET,
                    "No target object selected.",
                    "Assign a target in the Target Object field in the dialog.",
                )
                return True
            if not str(self._settings.output_path).strip():
                show_error_dialog(
                    ERROR_NO_OUTPUT_PATH,
                    "Output Path is empty.",
                    "Choose a folder such as C:\\renders\\my_splat before building.",
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Working\u2026")
            try:
                result = run_pipeline(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                # Update last export path
                if result.get("colmap") and result["colmap"].get("dir"):
                    self._refresh_last_export(result["colmap"]["dir"])
                self._show_success_dialog(result)
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_BUILD_FAILED, "Build failed.", exc)
            return True

        if cid == _IDs.BTN_COLMAP_ONLY:
            self._read_ui()
            doc = c4d.documents.GetActiveDocument()
            if doc is None:
                show_error_dialog(ERROR_NO_DOCUMENT, "No active Cinema 4D document.")
                return True
            obj = self._resolve_target_object(doc)
            if obj is None:
                show_error_dialog(
                    ERROR_NO_TARGET,
                    "No target object selected.",
                    "Assign a target in the Target Object field in the dialog.",
                )
                return True
            if not str(self._settings.output_path).strip():
                show_error_dialog(
                    ERROR_NO_OUTPUT_PATH,
                    "Output Path is empty.",
                    "Choose a folder such as C:\\renders\\my_splat before "
                    "exporting synthetic COLMAP data.",
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Exporting synthetic COLMAP data\u2026")
            try:
                result = run_colmap_only(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                # Update last export path
                if result.get("dir"):
                    self._refresh_last_export(result["dir"])
                c4d.gui.MessageDialog(
                    "Synthetic COLMAP data export complete.\n\n"
                    "Folder:  {}\n"
                    "Points:  {}\n"
                    "Intrinsics source:  {}\n"
                    "Images folder:  {}".format(
                        result["dir"],
                        result["points_count"],
                        result["intrinsics_source"],
                        result.get("images_dir",
                                   os.path.join(result["dir"], "images")),
                    )
                )
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_COLMAP_FAILED,
                                  "Synthetic COLMAP data export failed.", exc)
            return True

        if cid == _IDs.BTN_CLOSE:
            if self._values_ready:
                self._read_ui()
                _save_settings(self._settings)
            self.Close()
            return True

        # Generic handler: read & persist on any other control change
        if not self._values_ready:
            return True
        self._read_ui()
        _save_settings(self._settings)
        self._try_auto_update_rig(cid)
        if self._current_mode == 0:
            self._update_spiral_ui()
        self._refresh_status()
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _show_success_dialog(result):
        colmap = result.get("colmap")
        pose_file = result.get("pose_file")
        mode = result.get("mode", "?")
        extra = result.get("mode_extra", 0)
        extra_str = ""
        if mode == "icosphere" and extra:
            extra_str = " (subdivisions: {})".format(extra)

        msg_lines = [
            "Synthetic COLMAP data ready!",
            "",
            "Object:   {}".format(result.get("target_name", "?")),
            "Cameras:  {}  ({}{})".format(
                result.get("camera_count", 0), mode, extra_str),
            "",
        ]
        if pose_file and not str(pose_file).startswith("ERROR"):
            msg_lines.append("Pose JSON:  {}".format(pose_file))
        if colmap:
            msg_lines += [
                "Synthetic COLMAP data folder:  {}".format(colmap["dir"]),
                "Images folder:  {}".format(
                    colmap.get("images_dir",
                               os.path.join(colmap["dir"], "images"))),
                "Sparse points:  {}".format(colmap["points_count"]),
                "Intrinsics:     {}".format(colmap["intrinsics_source"]),
            ]
        msg_lines += [
            "",
            "Next step:  render the animation to produce the image sequence,",
            "then import the synthetic COLMAP data folder into your "
            "reconstruction app.",
        ]
        c4d.gui.MessageDialog("\n".join(msg_lines))


# ---------------------------------------------------------------------------
# CommandData plugin class
# ---------------------------------------------------------------------------

class C4D2GSCommand(c4d.plugins.CommandData):

    def __init__(self):
        self._dialog = None

    def Execute(self, doc):
        self._ensure_dialog()
        if not self._dialog.IsOpen():
            self._dialog.Open(
                dlgtype=c4d.DLG_TYPE_ASYNC,
                pluginid=PLUGIN_ID,
                defaultw=520,
                defaulth=680,
            )
        return True

    def RestoreLayout(self, sec_ref):
        self._ensure_dialog()
        return self._dialog.Restore(pluginid=PLUGIN_ID, secret=sec_ref)

    def _ensure_dialog(self):
        if self._dialog is None:
            self._dialog = C4D2GSDialog()
