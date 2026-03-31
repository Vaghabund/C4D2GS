

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






class _IDs:

    TARGET_LINK = 1000


    CAM_COUNT = 1020
    RADIUS = 1021
    SAMPLING_MODE = 1025
    SPIRAL_TURNS = 1026
    SPIRAL_POLE = 1027
    ADDITIONAL_CAMERAS_GROUP = 4000
    ADDITIONAL_CAMERAS_GROUP_FIELD = 4010


    OUTPUT_PATH = 1030
    OUTPUT_PATH_BROWSE = 1031
    OUTPUT_FORMAT = 1032
    RES_X = 1033
    RES_Y = 1034
    FPS = 1035
    STRAIGHT_ALPHA = 1036


    CREATE_ANIM_CAM = 1040
    REPLACE_RIG = 1041
    AUTO_UPDATE_RIG = 1053
    EXPORT_JSON = 1042
    EXPORT_COLMAP = 1045
    SPARSE_COUNT = 1052
    CAMERA_TYPE = 1055
    CHK_OVERWRITE = 1056


    GRP_SPACE_TAB = 2005
    ANCHOR_MODE = 3005
    CLUSTER_CAM_COUNT = 3006
    CLUSTER_RADIUS = 3007
    SAMPLING_MODE = 3008
    AUTO_Y_HEIGHT = 3009

    MANUAL_ANCHOR_CHECKBOX = 3013
    MANUAL_ANCHOR_GROUP = 3014
    MANUAL_ANCHOR_GROUP_FIELD = 3015
    MANUAL_Y_HEIGHT_CHECKBOX = 3016
    MANUAL_Y_HEIGHT_GROUP = 3017
    MANUAL_Y_HEIGHT_FIELD = 3018


    BTN_CREATE_RIG = 1089
    BTN_EXECUTE = 1090
    BTN_COLMAP_ONLY = 1091
    BTN_CLOSE = 1092

    TAB_SELECTOR = 1100

    TAB_BTN_OBJECT = 1110
    TAB_BTN_SPACE = 1111
    TAB_BTN_OUTPUT = 1112
    TAB_BTN_EXPORT = 1113
    TAB_BTN_IMPORT = 1114
    TAB_BTN_RENDER = 1115


    STATUS_TEXT = 1099


    GRP_HEADER = 2000
    GRP_CAMERA_TAB = 2001
    GRP_OUTPUT_TAB = 2002
    GRP_EXPORT_TAB = 2003
    GRP_BUTTONS = 2004
    GRP_SPHERE = 2010
    GRP_DIST = 2011
    GRP_OUTPUT_PATH_ROW = 2012
    GRP_RES = 2014

    GRP_RENDER_TAB = 2006
    RENDER_ENGINE = 5000
    RENDER_USE_GLOBAL = 5001
    RENDER_SAMPLES = 5002
    RENDER_CAMERA = 5003






class C4D2GSDialog(c4d.gui.GeDialog):

    def __init__(self):
        super(C4D2GSDialog, self).__init__()
        self._settings = Settings()
        _load_settings(self._settings)
        self._target_obj = None
        self._target_link_gui = None
        self._is_auto_updating = False
        self._values_ready = False
        self._divider_counter = 0





    def CreateLayout(self):
        try:
            self.SetTitle("C4D2GS  —  Synthetic COLMAP Data Generator  v{}".format(PLUGIN_VERSION))



            use_native_tabs = hasattr(c4d, "TAB_CHILD") and hasattr(c4d, "TAB_TABS")
            if use_native_tabs:
                try:

                    self.GroupBegin(_IDs.GRP_HEADER, c4d.BFH_SCALEFIT, cols=1, groupflags=c4d.TAB_TABS)
                    self.GroupBorderSpace(6, 6, 6, 4)


                    self.GroupBegin(101, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0, title="Object", groupflags=c4d.TAB_CHILD)
                    self._build_object_tab()
                    self.GroupEnd()

                    self.GroupBegin(102, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0, title="Space", groupflags=c4d.TAB_CHILD)
                    self._build_space_tab()
                    self.GroupEnd()

                    self.GroupBegin(106, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0, title="Export", groupflags=c4d.TAB_CHILD)
                    self._build_export_tab()
                    self.GroupEnd()

                    self.GroupEnd()
                    c4d.GePrint("[C4D2GS] CreateLayout: using native tab group (Object, Space, Export)")
                except Exception:
                    c4d.GePrint("[C4D2GS] CreateLayout: native tabs failed, falling back. Exception:\n{}".format(traceback.format_exc()))

                    use_native_tabs = False

            if not use_native_tabs:

                self.GroupBegin(_IDs.GRP_HEADER, c4d.BFH_SCALEFIT, cols=3)
                self.GroupBorderSpace(6, 6, 6, 4)
                self.AddButton(_IDs.TAB_BTN_OBJECT, c4d.BFH_SCALEFIT, 0, 0, "Object")
                self.AddButton(_IDs.TAB_BTN_SPACE, c4d.BFH_SCALEFIT, 0, 0, "Space")
                self.AddButton(_IDs.TAB_BTN_EXPORT, c4d.BFH_SCALEFIT, 0, 0, "Export")

                self.AddComboBox(_IDs.TAB_SELECTOR, c4d.BFH_LEFT)
                self.AddChild(_IDs.TAB_SELECTOR, 0, "Object")
                self.AddChild(_IDs.TAB_SELECTOR, 1, "Space")
                self.AddChild(_IDs.TAB_SELECTOR, 2, "Export")
                self.GroupEnd()
                c4d.GePrint("[C4D2GS] CreateLayout: using header-button fallback (Object, Space, Export)")


                self.GroupBegin(101, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0, title="Object")
                self._build_object_tab()
                self.GroupEnd()


                self.GroupBegin(102, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0, title="Space")
                self._build_space_tab()
                self.GroupEnd()


                self.GroupBegin(106, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, cols=1, rows=0, title="Export")
                self._build_export_tab()
                self.GroupEnd()


            self.GroupBegin(_IDs.GRP_BUTTONS, c4d.BFH_SCALEFIT, cols=3, rows=1)
            self.GroupBorderSpace(6, 6, 6, 4)
            self.AddButton(_IDs.BTN_CREATE_RIG, c4d.BFH_SCALEFIT, 0, 0, "  Build Rig  ")
            self.AddButton(_IDs.BTN_COLMAP_ONLY, c4d.BFH_SCALEFIT, 0, 0, "  Export COLMAP  ")
            self.AddButton(_IDs.BTN_EXECUTE, c4d.BFH_SCALEFIT, 0, 0, "  Build & Export  ")
            self.GroupEnd()


            self.AddStaticText(_IDs.STATUS_TEXT, c4d.BFH_SCALEFIT, 0, 0,
                               "Select a target object and click Build & Export.")

            return True
        except Exception as exc:

            try:
                err = traceback.format_exc()
                c4d.gui.MessageDialog("C4D2GS UI failed to build:\n{}".format(str(exc)))
            except Exception:
                pass

            try:
                self.GroupBegin(900, c4d.BFH_SCALEFIT, cols=1)
                self.AddStaticText(901, c4d.BFH_SCALEFIT, 0, 0, "C4D2GS — UI failed to build. See console.")
                self.GroupEnd()
            except Exception:
                pass
            return True

    def _build_object_tab(self):

        self.GroupBegin(_IDs.GRP_CAMERA_TAB, c4d.BFH_SCALEFIT, cols=1, title="Camera", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)



        self.AddStaticText(1001, c4d.BFH_LEFT, 0, 0, "Target Object")
        self.AddCustomGui(
            _IDs.TARGET_LINK, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )
        try:
            self._target_link_gui = self.GetCustomGui(_IDs.TARGET_LINK)
        except Exception:
            self._target_link_gui = None

        self.GroupBegin(_IDs.GRP_SPHERE, c4d.BFH_SCALEFIT, cols=2,
                        title="Sphere", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(3000, c4d.BFH_LEFT, 0, 0, "Camera Count")
        self.AddEditNumberArrows(_IDs.CAM_COUNT, c4d.BFH_SCALEFIT)

        self.AddStaticText(3001, c4d.BFH_LEFT, 0, 0, "Radius")
        if hasattr(self, "AddEditSlider"):
            self.AddEditSlider(_IDs.RADIUS, c4d.BFH_SCALEFIT)
        else:
            self.AddEditNumberArrows(_IDs.RADIUS, c4d.BFH_SCALEFIT)


        self.AddStaticText(3006, c4d.BFH_LEFT, 0, 0, "Camera Type")
        self.AddComboBox(_IDs.CAMERA_TYPE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.CAMERA_TYPE, 0, "Standard")
        self.AddChild(_IDs.CAMERA_TYPE, 1, "Redshift RSCamera")
        self.GroupEnd()


        self.GroupBegin(_IDs.ADDITIONAL_CAMERAS_GROUP, c4d.BFH_SCALEFIT, cols=1,
                        title="Additional Camera Group", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(4001, c4d.BFH_LEFT, 0, 0, "Camera Group")
        self.AddCustomGui(
            _IDs.ADDITIONAL_CAMERAS_GROUP_FIELD, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )
        try:
            self._additional_cameras_gui = self.GetCustomGui(_IDs.ADDITIONAL_CAMERAS_GROUP_FIELD)
        except Exception:
            self._additional_cameras_gui = None
        self.GroupEnd()


        self.GroupBegin(_IDs.GRP_DIST, c4d.BFH_SCALEFIT, cols=2,
                        title="Distribution", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(3010, c4d.BFH_LEFT, 0, 0, "Sampling Mode")
        self.AddComboBox(_IDs.SAMPLING_MODE, c4d.BFH_SCALEFIT)
        for mode_id, label in [(0, "Spiral"), (1, "Icosphere"), (2, "Fibonacci")]:
            self.AddChild(_IDs.SAMPLING_MODE, mode_id, label)

        self.AddStaticText(3011, c4d.BFH_LEFT, 0, 0, "Spiral Turns")
        self.AddEditNumberArrows(_IDs.SPIRAL_TURNS, c4d.BFH_SCALEFIT)

        self.AddStaticText(3012, c4d.BFH_LEFT, 0, 0, "Pole Margin")
        self.AddEditNumberArrows(_IDs.SPIRAL_POLE, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.GroupEnd()

    def _add_section_divider(self):
        self._divider_counter += 1
        grp_id = 2090 + self._divider_counter
        txt_id = 3090 + self._divider_counter
        self.GroupBegin(grp_id, c4d.BFH_SCALEFIT, cols=1, rows=1)
        self.GroupBorderSpace(0, 6, 0, 6)
        if hasattr(self, "AddSeparatorH"):
            try:
                self.AddSeparatorH(0)
                self.GroupEnd()
                return
            except Exception:
                pass
        self.AddStaticText(txt_id, c4d.BFH_SCALEFIT, 0, 0, "")
        self.GroupEnd()

    def _build_space_tab(self):

        self.GroupBegin(_IDs.GRP_SPACE_TAB, c4d.BFH_SCALEFIT, cols=1, title="Space", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)


        self.AddStaticText(4000, c4d.BFH_LEFT, 0, 0, "Anchor Placement Mode")
        self.AddComboBox(_IDs.ANCHOR_MODE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.ANCHOR_MODE, 0, "Auto Placement")
        self.AddChild(_IDs.ANCHOR_MODE, 1, "Manual Placement")


        self.AddStaticText(4001, c4d.BFH_LEFT, 0, 0, "Manual Anchor Placement")
        self.AddCheckbox(_IDs.MANUAL_ANCHOR_CHECKBOX, c4d.BFH_LEFT, 0, 0, "Enable Manual Anchors")


        self.GroupBegin(_IDs.MANUAL_ANCHOR_GROUP, c4d.BFH_SCALEFIT, cols=1,
                        title="Manual Anchor Group", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(4002, c4d.BFH_LEFT, 0, 0, "Anchor Group")
        self.AddCustomGui(
            _IDs.MANUAL_ANCHOR_GROUP_FIELD, c4d.CUSTOMGUI_LINKBOX, "",
            c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer(),
        )
        self.GroupEnd()

    def _build_render_tab(self):

        self.GroupBegin(_IDs.GRP_RENDER_TAB, c4d.BFH_SCALEFIT, cols=1, title="Render Settings", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)


        self.AddStaticText(5004, c4d.BFH_LEFT, 0, 0, "Renderer")
        self.AddComboBox(_IDs.RENDER_ENGINE, c4d.BFH_SCALEFIT)
        self.AddChild(_IDs.RENDER_ENGINE, 0, "Standard")
        self.AddChild(_IDs.RENDER_ENGINE, 1, "Physical")
        self.AddChild(_IDs.RENDER_ENGINE, 2, "Redshift")


        self.AddStaticText(5005, c4d.BFH_LEFT, 0, 0, "Use Global Render Settings")
        self.AddCheckbox(_IDs.RENDER_USE_GLOBAL, c4d.BFH_LEFT, 0, 0, "Use Global")


        self.AddStaticText(5006, c4d.BFH_LEFT, 0, 0, "Render Samples")
        self.AddEditNumberArrows(_IDs.RENDER_SAMPLES, c4d.BFH_SCALEFIT)


        self.AddStaticText(5007, c4d.BFH_LEFT, 0, 0, "Render Camera")
        self.AddCustomGui(_IDs.RENDER_CAMERA, c4d.CUSTOMGUI_LINKBOX, "", c4d.BFH_SCALEFIT, 0, 0, c4d.BaseContainer())
        try:
            self._render_camera_gui = self.GetCustomGui(_IDs.RENDER_CAMERA)
        except Exception:
            self._render_camera_gui = None

        self.GroupEnd()


        self.AddStaticText(4003, c4d.BFH_LEFT, 0, 0, "Manual Y Height")
        self.AddCheckbox(_IDs.MANUAL_Y_HEIGHT_CHECKBOX, c4d.BFH_LEFT, 0, 0, "Enable Manual Y Height")


        self.GroupBegin(_IDs.MANUAL_Y_HEIGHT_GROUP, c4d.BFH_SCALEFIT, cols=1,
                        title="Y Height Parameter", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(4004, c4d.BFH_LEFT, 0, 0, "Y Height")
        self.AddEditNumberArrows(_IDs.MANUAL_Y_HEIGHT_FIELD, c4d.BFH_SCALEFIT)
        self.GroupEnd()


        self.AddStaticText(4005, c4d.BFH_LEFT, 0, 0, "Cameras per Cluster")
        self.AddEditNumberArrows(_IDs.CLUSTER_CAM_COUNT, c4d.BFH_SCALEFIT)

        self.AddStaticText(4006, c4d.BFH_LEFT, 0, 0, "Cluster Radius")
        self.AddEditNumberArrows(_IDs.CLUSTER_RADIUS, c4d.BFH_SCALEFIT)

        self.AddStaticText(4007, c4d.BFH_LEFT, 0, 0, "Sampling Mode")
        self.AddComboBox(_IDs.SAMPLING_MODE, c4d.BFH_SCALEFIT)
        for mode_id, label in [(0, "Spiral"), (1, "Icosphere"), (2, "Fibonacci")]:
            self.AddChild(_IDs.SAMPLING_MODE, mode_id, label)


        self.AddStaticText(4008, c4d.BFH_LEFT, 0, 0, "Auto Y-Height")
        self.AddEditNumberArrows(_IDs.AUTO_Y_HEIGHT, c4d.BFH_SCALEFIT)

        self.GroupEnd()

    def _build_output_tab(self):

        self.GroupBegin(_IDs.GRP_OUTPUT_TAB,
                        c4d.BFH_SCALEFIT,
                        cols=1, title="Output", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 6, 6, 6)

        self.GroupBegin(2030, c4d.BFH_SCALEFIT, cols=2,
                        title="Image Output", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)

        self.AddStaticText(3020, c4d.BFH_LEFT, 0, 0, "Output Path")
        self.GroupBegin(_IDs.GRP_OUTPUT_PATH_ROW, c4d.BFH_SCALEFIT, cols=2, rows=1)
        self.AddEditText(_IDs.OUTPUT_PATH, c4d.BFH_SCALEFIT)
        self.AddButton(_IDs.OUTPUT_PATH_BROWSE, c4d.BFH_RIGHT, 0, 0, "Browse…")
        self.GroupEnd()

        self.AddStaticText(3025, c4d.BFH_LEFT, 0, 0, "Generated Files")
        self.AddStaticText(3026, c4d.BFH_LEFT, 0, 0, "cameras.txt + images.txt + points3D.txt + images/gs_####")

        self.AddStaticText(3021, c4d.BFH_LEFT, 0, 0, "Format")
        self.AddComboBox(_IDs.OUTPUT_FORMAT, c4d.BFH_SCALEFIT)
        for fmt_id, fmt_name in self._output_format_items():
            self.AddChild(_IDs.OUTPUT_FORMAT, int(fmt_id), fmt_name)

        self.AddStaticText(3022, c4d.BFH_LEFT, 0, 0, "Resolution")
        self.GroupBegin(_IDs.GRP_RES, c4d.BFH_SCALEFIT, cols=3, rows=1)
        self.AddEditNumber(_IDs.RES_X, c4d.BFH_SCALEFIT)
        self.AddStaticText(3023, c4d.BFH_CENTER, 0, 0, "×")
        self.AddEditNumber(_IDs.RES_Y, c4d.BFH_SCALEFIT)
        self.GroupEnd()

        self.AddStaticText(3024, c4d.BFH_LEFT, 0, 0, "FPS")
        self.AddEditNumberArrows(_IDs.FPS, c4d.BFH_SCALEFIT)

        self.AddStaticText(3027, c4d.BFH_LEFT, 0, 0, "Straight Alpha")
        self.AddCheckbox(_IDs.STRAIGHT_ALPHA, c4d.BFH_LEFT, 0, 0, "")

        self.GroupEnd()

        self.GroupEnd()

    def _build_export_tab(self):
        self.GroupBegin(_IDs.GRP_EXPORT_TAB, c4d.BFH_SCALEFIT, cols=1, rows=0,
                        title="Export Settings", groupflags=c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(6, 4, 6, 4)


        self.AddCheckbox(_IDs.CHK_OVERWRITE, c4d.BFH_LEFT, 0, 0, "Override existing export folder")

        self.GroupEnd()

    @staticmethod
    def _output_format_items():
        items = []
        for label, const_name in [("PNG", "FILTER_PNG"), ("JPG", "FILTER_JPG"),
                                   ("TIF", "FILTER_TIF"), ("EXR", "FILTER_EXR")]:
            val = getattr(c4d, const_name, None)
            if val is not None:
                items.append((val, label))
        return items





    def InitValues(self):
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        self._target_obj = self._resolve_target_object(doc)
        if self._target_obj is not None:
            self._set_link_target(self._target_obj)


        self._si(_IDs.CAM_COUNT, s.camera_count, 1, 100000)
        s.sphere_radius = float(self.GetFloat(_IDs.RADIUS))
        self._sf(_IDs.RADIUS, s.sphere_radius, RADIUS_MIN, RADIUS_MAX, 1.0)
        self.SetInt32(_IDs.CAMERA_TYPE, int(getattr(s, "camera_type", 0)))
        self.SetInt32(_IDs.SAMPLING_MODE, s.sampling_mode)
        self._sf(_IDs.SPIRAL_TURNS, s.spiral_turns, 0.01, 1e6, 0.1)
        self._sf(_IDs.SPIRAL_POLE, s.spiral_pole_margin, 0.0, 0.49, 0.001)


        self.SetString(_IDs.OUTPUT_PATH, str(s.output_folder()))
        self.SetInt32(_IDs.OUTPUT_FORMAT, int(s.output_format))
        self._si(_IDs.RES_X, s.res_x, 1, 65535)
        self._si(_IDs.RES_Y, s.res_y, 1, 65535)
        self._si(_IDs.FPS, s.fps, 1, 1000)
        self.SetBool(_IDs.STRAIGHT_ALPHA, bool(s.straight_alpha))


        self.SetBool(_IDs.CREATE_ANIM_CAM, bool(s.create_anim_cam))
        self.SetBool(_IDs.REPLACE_RIG, bool(s.replace_rig))
        self.SetBool(_IDs.AUTO_UPDATE_RIG, bool(s.auto_update_rig))
        self.SetBool(_IDs.EXPORT_JSON, bool(s.export_json))
        self.SetBool(_IDs.EXPORT_COLMAP, bool(s.export_colmap))
        self.SetBool(_IDs.CHK_OVERWRITE, bool(getattr(s, "overwrite_export", False)))
        self._si(_IDs.SPARSE_COUNT, s.sparse_count, 8, 100000)


        try:
            self.SetInt32(_IDs.ANCHOR_MODE, getattr(s, "anchor_mode", 0))
            self.SetBool(_IDs.MANUAL_ANCHOR_CHECKBOX, bool(getattr(s, "manual_anchor_enabled", False)))

            try:
                self.SetLink(_IDs.MANUAL_ANCHOR_GROUP_FIELD, getattr(s, "manual_anchor_group", None))
            except Exception:
                pass
            self.SetBool(_IDs.MANUAL_Y_HEIGHT_CHECKBOX, bool(getattr(s, "manual_y_height_enabled", False)))
            self._sf(_IDs.MANUAL_Y_HEIGHT_FIELD, getattr(s, "manual_y_height", 0.0), -1e6, 1e6, 0.1)


            try:
                self.Enable(_IDs.MANUAL_ANCHOR_GROUP, bool(getattr(s, "manual_anchor_enabled", False)))
                self.Enable(_IDs.MANUAL_ANCHOR_GROUP_FIELD, bool(getattr(s, "manual_anchor_enabled", False)))
                self.Enable(_IDs.MANUAL_Y_HEIGHT_GROUP, bool(getattr(s, "manual_y_height_enabled", False)))
                self.Enable(_IDs.MANUAL_Y_HEIGHT_FIELD, bool(getattr(s, "manual_y_height_enabled", False)))
            except Exception:
                pass

        except Exception:

            pass

        self._update_spiral_ui()

        try:
            self.SetInt32(_IDs.RENDER_ENGINE, int(getattr(s, "render_engine", 0)))
            self.SetBool(_IDs.RENDER_USE_GLOBAL, bool(getattr(s, "render_use_global", True)))
            self._si(_IDs.RENDER_SAMPLES, getattr(s, "render_samples", 8), 1, 65535)
            try:
                self.SetLink(_IDs.RENDER_CAMERA, getattr(s, "render_camera", None))
            except Exception:
                pass
        except Exception:
            pass

        try:
            self.SetInt32(_IDs.TAB_SELECTOR, int(getattr(s, "last_tab", 0)))
        except Exception:
            self.SetInt32(_IDs.TAB_SELECTOR, 0)
        try:
            self._update_tab_visibility()
        except Exception:
            pass
        try:
            c4d.GePrint("[C4D2GS] InitValues: last_tab={}".format(int(getattr(s, "last_tab", 0))))
        except Exception:
            pass
        self._refresh_status()
        self._values_ready = True
        return True

    def _update_spiral_ui(self):
        spiral_enabled = int(self.GetInt32(_IDs.SAMPLING_MODE)) == 0
        for cid in [3011, _IDs.SPIRAL_TURNS, 3012, _IDs.SPIRAL_POLE]:
            try:
                self.Enable(cid, spiral_enabled)
            except Exception:
                pass

    def _update_tab_visibility(self):
        try:
            sel = int(self.GetInt32(_IDs.TAB_SELECTOR))
        except Exception:
            sel = 0
        try:
            c4d.GePrint("[C4D2GS] _update_tab_visibility: sel={}".format(sel))
        except Exception:
            pass

        try:
            self.Enable(101, sel == 0)
            self.Enable(102, sel == 1)
            self.Enable(106, sel == 2)

            try:
                self.Enable(105, False)
                self.Enable(103, False)
                self.Enable(104, False)
            except Exception:
                pass
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





    def _read_ui(self):
        s = self._settings
        doc = c4d.documents.GetActiveDocument()

        link_obj = self._get_link_target(doc)
        if link_obj is not None:
            self._target_obj = link_obj
        elif self._target_obj is None:
            self._target_obj = self._resolve_target_object(doc)
        if self._target_obj is not None:
            self._set_link_target(self._target_obj)

        s.camera_count = max(1, int(self.GetInt32(_IDs.CAM_COUNT)))
        s.sphere_radius = max(RADIUS_MIN, min(RADIUS_MAX, float(self.GetFloat(_IDs.RADIUS))))
        s.camera_type = int(self.GetInt32(_IDs.CAMERA_TYPE))
        s.sampling_mode = int(self.GetInt32(_IDs.SAMPLING_MODE))
        s.spiral_turns = max(0.01, float(self.GetFloat(_IDs.SPIRAL_TURNS)))
        s.spiral_pole_margin = max(0.0, min(0.49, float(self.GetFloat(_IDs.SPIRAL_POLE))))


        try:
            s.anchor_mode = int(self.GetInt32(_IDs.ANCHOR_MODE))
        except Exception:
            s.anchor_mode = getattr(s, "anchor_mode", 0)

        try:
            s.manual_anchor_enabled = bool(self.GetBool(_IDs.MANUAL_ANCHOR_CHECKBOX))
        except Exception:
            s.manual_anchor_enabled = getattr(s, "manual_anchor_enabled", False)


        manual_group = None
        try:

            try:
                manual_group = self.GetLink(_IDs.MANUAL_ANCHOR_GROUP_FIELD, getattr(c4d, "BaseObject", None))
            except Exception:
                manual_group = None
        except Exception:
            manual_group = None

        s.anchor_null_group = manual_group

        try:
            s.manual_y_height_enabled = bool(self.GetBool(_IDs.MANUAL_Y_HEIGHT_CHECKBOX))
        except Exception:
            s.manual_y_height_enabled = getattr(s, "manual_y_height_enabled", False)

        try:
            s.manual_y_height = float(self.GetFloat(_IDs.MANUAL_Y_HEIGHT_FIELD))
        except Exception:
            s.manual_y_height = getattr(s, "manual_y_height", 0.0)

        try:
            s.cluster_cam_count = max(1, int(self.GetInt32(_IDs.CLUSTER_CAM_COUNT)))
        except Exception:
            s.cluster_cam_count = getattr(s, "cluster_cam_count", 1)

        try:
            s.cluster_radius = float(self.GetFloat(_IDs.CLUSTER_RADIUS))
        except Exception:
            s.cluster_radius = getattr(s, "cluster_radius", 10.0)

        try:
            s.auto_y_height = float(self.GetFloat(_IDs.AUTO_Y_HEIGHT))
        except Exception:
            s.auto_y_height = getattr(s, "auto_y_height", 0.0)

        try:
            s.overwrite_export = bool(self.GetBool(_IDs.CHK_OVERWRITE))
        except Exception:
            s.overwrite_export = getattr(s, "overwrite_export", False)

        s.output_path = _normalize_path(self.GetString(_IDs.OUTPUT_PATH).strip())
        if s.output_path:
            self.SetString(_IDs.OUTPUT_PATH, s.output_path)
        s.output_format = int(self.GetInt32(_IDs.OUTPUT_FORMAT))
        s.res_x = max(1, int(self.GetInt32(_IDs.RES_X)))
        s.res_y = max(1, int(self.GetInt32(_IDs.RES_Y)))
        s.fps = max(1, int(self.GetInt32(_IDs.FPS)))


        try:
            s.render_engine = int(self.GetInt32(_IDs.RENDER_ENGINE))
        except Exception:
            s.render_engine = getattr(s, "render_engine", 0)
        try:
            s.render_use_global = bool(self.GetBool(_IDs.RENDER_USE_GLOBAL))
        except Exception:
            s.render_use_global = getattr(s, "render_use_global", True)
        try:
            s.render_samples = max(1, int(self.GetInt32(_IDs.RENDER_SAMPLES)))
        except Exception:
            s.render_samples = getattr(s, "render_samples", 8)

        try:
            cam = None
            if getattr(self, "_render_camera_gui", None) is not None:
                gui_get = getattr(self._render_camera_gui, "GetLink", None)
                if callable(gui_get):
                    try:
                        cam = gui_get()
                    except Exception:
                        cam = None
            if cam is None:
                try:
                    cam = self.GetLink(_IDs.RENDER_CAMERA)
                except Exception:
                    cam = None
            s.render_camera = cam
        except Exception:
            s.render_camera = getattr(s, "render_camera", None)

        s.create_anim_cam = bool(self.GetBool(_IDs.CREATE_ANIM_CAM))
        s.replace_rig = bool(self.GetBool(_IDs.REPLACE_RIG))
        s.auto_update_rig = bool(self.GetBool(_IDs.AUTO_UPDATE_RIG))
        s.export_json = bool(self.GetBool(_IDs.EXPORT_JSON))
        s.export_colmap = bool(self.GetBool(_IDs.EXPORT_COLMAP))
        s.straight_alpha = bool(self.GetBool(_IDs.STRAIGHT_ALPHA))
        s.sparse_count = max(8, int(self.GetInt32(_IDs.SPARSE_COUNT)))

        self._update_spiral_ui()





    def _refresh_status(self):
        status = "Version: {}".format(PLUGIN_VERSION)
        self.SetString(_IDs.STATUS_TEXT, status)

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
            self.SetString(_IDs.STATUS_TEXT, "Auto-updating rig…")
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

        for arg in [doc, getattr(c4d, "BaseObject", None), getattr(c4d, "BaseList2D", None)]:
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
        if obj is not None:
            return obj
        return None

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





    def Command(self, cid, msg):

        if cid in (_IDs.TAB_BTN_OBJECT, _IDs.TAB_BTN_SPACE, _IDs.TAB_BTN_EXPORT):
            mapping = {
                _IDs.TAB_BTN_OBJECT: 0,
                _IDs.TAB_BTN_SPACE: 1,
                _IDs.TAB_BTN_EXPORT: 2,
            }
            sel = mapping.get(cid, 0)

            try:
                self.Enable(101, sel == 0)
                self.Enable(102, sel == 1)
                self.Enable(106, sel == 2)

                try:
                    self.Enable(105, False)
                    self.Enable(103, False)
                    self.Enable(104, False)
                except Exception:
                    pass
            except Exception:
                pass

            try:
                self.SetInt32(_IDs.TAB_SELECTOR, sel)
            except Exception:
                pass
            try:
                c4d.GePrint("[C4D2GS] Command: header button pressed, sel={}".format(sel))
            except Exception:
                pass
            if self._values_ready:
                try:
                    self._settings.last_tab = sel
                    _save_settings(self._settings)
                except Exception:
                    pass
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
                    "Assign a target in the Target Object field in the dialog."
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Creating rig…")
            try:
                result = create_or_update_rig(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                c4d.gui.MessageDialog(
                    "Camera rig ready.\n\n"
                    "Object:  {}\n"
                    "Cameras: {}\n"
                    "Mode:    {}\n\n"
                    "Tip: tweak parameters and click Build Rig again to iterate quickly.".format(
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
                    "Assign a target in the Target Object field in the dialog."
                )
                return True
            if not str(self._settings.output_path).strip():
                show_error_dialog(
                    ERROR_NO_OUTPUT_PATH,
                    "Output Path is empty.",
                    "Choose a folder such as C:\\renders\\my_splat before building."
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Working…")
            try:
                result = run_pipeline(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
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
                    "Assign a target in the Target Object field in the dialog."
                )
                return True
            if not str(self._settings.output_path).strip():
                show_error_dialog(
                    ERROR_NO_OUTPUT_PATH,
                    "Output Path is empty.",
                    "Choose a folder such as C:\\renders\\my_splat before exporting synthetic COLMAP data."
                )
                return True
            self._target_obj = obj
            self.SetString(_IDs.STATUS_TEXT, "Exporting synthetic COLMAP data…")
            try:
                result = run_colmap_only(doc, self._settings, obj)
                self._refresh_status()
                _save_settings(self._settings)
                c4d.gui.MessageDialog(
                    "Synthetic COLMAP data export complete.\n\n"
                    "Folder:  {}\n"
                    "Points:  {}\n"
                    "Intrinsics source:  {}\n"
                    "Images folder:  {}".format(
                        result["dir"],
                        result["points_count"],
                        result["intrinsics_source"],
                        result.get("images_dir", os.path.join(result["dir"], "images")),
                    )
                )
            except Exception as exc:
                self._refresh_status()
                show_error_dialog(ERROR_COLMAP_FAILED, "Synthetic COLMAP data export failed.", exc)
            return True

        if cid == _IDs.BTN_CLOSE:
            if self._values_ready:
                self._read_ui()
                _save_settings(self._settings)
            self.Close()
            return True

        if cid == _IDs.TAB_SELECTOR:

            try:
                sel = int(self.GetInt32(_IDs.TAB_SELECTOR))
            except Exception:
                sel = 0
            try:
                c4d.GePrint("[C4D2GS] Command: TAB_SELECTOR changed -> sel={}".format(sel))
            except Exception:
                pass
            try:
                self._update_tab_visibility()
            except Exception:
                pass
            if self._values_ready:
                try:
                    self._settings.last_tab = sel
                    _save_settings(self._settings)
                except Exception:
                    pass
            return True


        if not self._values_ready:
            return True
        self._read_ui()
        _save_settings(self._settings)
        self._try_auto_update_rig(cid)
        self._update_spiral_ui()
        self._refresh_status()
        return True





    @staticmethod
    def _show_success_dialog(result):
        colmap = result.get("colmap")
        pose_file = result.get("pose_file")
        mode = result.get("mode", "?")
        extra = result.get("mode_extra", 0)
        extra_str = ""
        if mode == "icosphere" and extra:
            extra_str = " (subdivisions: {})".format(extra)
        elif mode == "spiral":
            extra_str = ""

        msg_lines = [
            "Synthetic COLMAP data ready!",
            "",
            "Object:   {}".format(result.get("target_name", "?")),
            "Cameras:  {}  ({}{})".format(result.get("camera_count", 0), mode, extra_str),
            "",
        ]
        if pose_file and not str(pose_file).startswith("ERROR"):
            msg_lines.append("Pose JSON:  {}".format(pose_file))
        if colmap:
            msg_lines += [
                "Synthetic COLMAP data folder:  {}".format(colmap["dir"]),
                "Images folder:  {}".format(colmap.get("images_dir", os.path.join(colmap["dir"], "images"))),
                "Sparse points:  {}".format(colmap["points_count"]),
                "Intrinsics:     {}".format(colmap["intrinsics_source"]),
            ]
        msg_lines += [
            "",
            "Next step:  render the animation to produce the image sequence,",
            "then import the synthetic COLMAP data folder into your reconstruction app.",
        ]
        c4d.gui.MessageDialog("\n".join(msg_lines))






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
