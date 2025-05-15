#!/usr/bin/env python3
"""
Auto-pilot for Limbus Company battles.

This script automates gameplay in Limbus Company by recognizing UI elements
on screen through template matching and simulating user input (mouse clicks,
keyboard presses).

Key Features:
- Automated battle progression (Win Rate button).
- Dialogue skipping.
- Handling of various overlays and confirmation prompts.
- Automated sequences for Luxcavation modes (Thread and EXP).
- Configurable via a GUI (gui_config.py) for thresholds, ROIs, and operational flags.
- Hotkeys for pausing/resuming, toggling modes, and quitting.

Exit at any time with Ctrl+Shift+Q or by flinging the mouse to the
top-left corner (PyAutoGUI failsafe).

Dependencies: opencv-python, numpy, pyautogui, keyboard, pygetwindow, mss
"""

# ── std-lib imports ───────────────────────────────────────────────────
import os
import threading
import traceback
import time
import sys
import json
from collections import namedtuple
import copy  # For deepcopy


# ── auto-installer for third-party packages ───────────────────────────
def _require(pkg, import_as=None, pypi_name=None):
    """
    Imports a package, installing it if not found.
    Args:
        pkg (str): The name of the package to import.
        import_as (str, optional): The name to import the package as. Defaults to None.
        pypi_name (str, optional): The name of the package on PyPI if different from import name. Defaults to None.
    Returns:
        module: The imported module.
    """
    import importlib
    import subprocess

    name = pypi_name or pkg
    try:
        return importlib.import_module(pkg if import_as is None else import_as)
    except ModuleNotFoundError:
        print(f"[setup] installing '{name}' …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", name])
        return importlib.import_module(pkg if import_as is None else import_as)


try:
    from gui_config import launch_gui, get_tuner
except ImportError as e:
    print(
        f"Warning: Could not import gui_config ({e}). GUI functionality will be unavailable."
    )
    launch_gui = None
    get_tuner = None

if getattr(sys, "frozen", False):
    import cv2
    import numpy as np
    import pyautogui
    import keyboard
    import pygetwindow as gw
    import mss
else:
    cv2 = _require("cv2", pypi_name="opencv-python")
    np = _require("numpy")
    pyautogui = _require("pyautogui")
    keyboard = _require("keyboard")
    gw = _require("pygetwindow", import_as="pygetwindow")
    mss = _require("mss")

# ───────────────────────── Runtime safety ──────────────────────────────
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

pause_event = threading.Event()

# ─────────────────────── User-configurable settings (MODULE LEVEL GLOBALS) ────────────────────
delay_ms = (
    10  # User reported 6s cycle with 10ms, so this is not the bottleneck currently
)
is_HDR = False
debug_flag = False
text_skip = False
lux_thread = False
lux_EXP = False
full_auto_mirror = False

CHECK_INTERVAL = delay_ms / 1000.0
DEBUG_MATCH = debug_flag
last_vals: dict[str, float] = {}
last_pass: dict[str, float] = {}
debug_log: list[str] = []

# ───────────────────────── Template metadata ───────────────────────────
Tmpl = namedtuple("Tmpl", "imgs masks thresh roi")

TEMPLATE_SPEC = {
    "winrate": ("winrate", 0.75, (0.50, 0.70, 0.50, 0.30)),
    "speech_menu": ("Speech Menu", 0.75, (0.50, 0.00, 0.50, 0.30)),
    "fast_forward": ("Fast Forward", 0.75, (0.45, 0.00, 0.35, 0.20)),
    "confirm": ("Confirm", 0.80, (0.35, 0.55, 0.35, 0.25)),
    "black_confirm": ("Black Confirm", 0.80, (0.36, 0.67, 0.26, 0.12)),
    "black_confirm_v2": ("Black Confirm Wide", 0.80, (0.70, 0.70, 0.30, 0.30)),
    "battle": ("To Battle", 0.70, (0.70, 0.70, 0.30, 0.30)),
    "chain_battle": ("Battle Chain", 0.82, (0.50, 0.50, 0.50, 0.50)),
    "skip": ("Skip", 0.80, (0.00, 0.30, 0.50, 0.40)),
    "enter": ("Enter", 0.80, (0.50, 0.60, 0.50, 0.40)),
    "choice_needed": ("Choice Check", 0.70, (0.45, 0.20, 0.45, 0.15)),
    "fusion_check": ("Fusion Check", 0.70, (0.20, 0.00, 0.60, 0.30)),
    "ego_check": ("EGO Check", 0.80, (0.33, 0.22, 0.33, 0.10)),
    "ego_get": ("EGO Get", 0.80, (0.33, 0.22, 0.33, 0.10)),
    "proceed": ("Proceed", 0.80, (0.50, 0.70, 0.50, 0.30)),
    "very_high": ("Very High", 0.85, (0.00, 0.70, 1.00, 0.30)),
    "commence": ("Commence", 0.80, (0.50, 0.70, 0.50, 0.30)),
    "commence_battle": ("Commence Battle", 0.80, (0.50, 0.70, 0.50, 0.30)),
    "continue": ("Continue", 0.80, (0.50, 0.70, 0.50, 0.30)),
    "luxcavations": ("Luxcavations", 0.80, (0.22, 0.08, 0.25, 0.40)),
    "select_exp_lux": ("Select EXP Lux", 0.80, (0.04, 0.30, 0.15, 0.12)),
    "select_thread_lux": ("Select Thread Lux", 0.80, (0.04, 0.40, 0.15, 0.12)),
    "lux_enter": ("Lux Enter", 0.80, (0.20, 0.55, 0.80, 0.25)),
    "exp_lux_enter": ("EXP Lux Enter", 0.80, (0.20, 0.60, 0.80, 0.20)),
    "thread_lux_battle": ("Thread Lux Battle Select", 0.80, (0.30, 0.30, 0.42, 0.45)),
    "drive": ("Drive", 0.92, (0.50, 0.80, 0.50, 0.20)),
}

DEFAULT_TEMPLATE_SPEC = copy.deepcopy(TEMPLATE_SPEC)
TEMPLATES: dict[str, Tmpl] = {}


# ────────────────────────────  Helper Functions  ────────────────────────────────
def resource_path(fname: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)


def load_templates() -> dict[str, Tmpl]:
    """
    Loads template images from files based on TEMPLATE_SPEC.
    Prioritizes "SDR.png" and "HDR.png" variants. If neither is found,
    it falls back to "<basename>.png".
    Loaded images are converted to grayscale.
    Returns:
        dict[str, Tmpl]: A dictionary mapping template names to Tmpl objects.
    """
    out: dict[str, Tmpl] = {}

    for name, (base, thresh, roi) in TEMPLATE_SPEC.items():
        loaded_template_variants: list[np.ndarray] = []
        corresponding_masks: list[np.ndarray | None] = []

        # Prioritize loading SDR and HDR variants
        # Suffix order defines loading preference if multiple exist.
        # For example, if both SDR and HDR exist, both will be loaded.
        preferred_suffixes = (" SDR.png", " HDR.png")

        for suffix in preferred_suffixes:
            path = resource_path(base + suffix)
            if os.path.isfile(path):
                try:
                    img_data = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                    if img_data is None:
                        if DEBUG_MATCH:
                            debug_log.append(
                                f"Template Load: Failed to read image at {path} for {name}"
                            )
                        continue
                    current_mask: np.ndarray | None = None
                    if img_data.shape[2] == 4:
                        bgr, alpha = img_data[:, :, :3], img_data[:, :, 3]
                        gray_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                        current_mask = (alpha > 0).astype(np.uint8)
                    else:
                        gray_img = cv2.cvtColor(img_data, cv2.COLOR_BGR2GRAY)

                    loaded_template_variants.append(gray_img)
                    corresponding_masks.append(current_mask)
                    if DEBUG_MATCH:
                        debug_log.append(
                            f"Template Load: Successfully loaded {path} for {name}"
                        )
                except Exception as e:
                    if DEBUG_MATCH:
                        debug_log.append(
                            f"Template Load: Error processing {path} for {name}: {e}"
                        )
                    continue

        # If no preferred (SDR/HDR) variants were loaded, try fallback to base .png
        if not loaded_template_variants:
            fallback_path = resource_path(base + ".png")
            if os.path.isfile(fallback_path):
                try:
                    img_data = cv2.imread(fallback_path, cv2.IMREAD_UNCHANGED)
                    if img_data is not None:
                        current_mask: np.ndarray | None = None
                        if img_data.shape[2] == 4:
                            bgr, alpha = img_data[:, :, :3], img_data[:, :, 3]
                            gray_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                            current_mask = (alpha > 0).astype(np.uint8)
                        else:
                            gray_img = cv2.cvtColor(img_data, cv2.COLOR_BGR2GRAY)

                        loaded_template_variants.append(gray_img)
                        corresponding_masks.append(current_mask)
                        if DEBUG_MATCH:
                            debug_log.append(
                                f"Template Load: Successfully loaded FALLBACK {fallback_path} for {name}"
                            )
                    elif DEBUG_MATCH:
                        debug_log.append(
                            f"Template Load: Failed to read FALLBACK image at {fallback_path} for {name}"
                        )
                except Exception as e:
                    if DEBUG_MATCH:
                        debug_log.append(
                            f"Template Load: Error processing FALLBACK {fallback_path} for {name}: {e}"
                        )

        if not loaded_template_variants:  # If still no variants loaded after fallback
            debug_log.append(
                f"Critical: No image files (SDR, HDR, or .png) found for template base: '{base}' (name: '{name}'). This template will be skipped."
            )
            continue

        out[name] = Tmpl(loaded_template_variants, corresponding_masks, thresh, roi)

    if not out and DEBUG_MATCH:
        debug_log.append(
            "Critical: No templates were loaded at all. Check template paths and files."
        )
    return out


def active_window_title() -> str:
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""


grabber = mss.mss()
try:
    primary_monitor_info = grabber.monitors[1]
except IndexError:
    print("Error: Could not find primary monitor. Falling back to all monitors.")
    primary_monitor_info = grabber.monitors[0]

MON_X, MON_Y = primary_monitor_info["left"], primary_monitor_info["top"]
MON_W, MON_H = primary_monitor_info["width"], primary_monitor_info["height"]

try:
    LOG_W, LOG_H = pyautogui.size()
    scale_x = MON_W / LOG_W if LOG_W > 0 else 1.0
    scale_y = MON_H / LOG_H if LOG_H > 0 else 1.0
except Exception as e:
    print(
        f"Warning: Could not get logical screen size from PyAutoGUI ({e}). Assuming no DPI scaling (1.0)."
    )
    scale_x, scale_y = 1.0, 1.0


def refresh_screen() -> np.ndarray | None:
    try:
        sct_img = grabber.grab(primary_monitor_info)
        img = np.array(sct_img)
        return cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    except Exception as e:
        if DEBUG_MATCH:
            debug_log.append(f"Screen Grab Error: {e}")
        return None


def click(pt: tuple[int, int] | None, hold_ms: int = 0):
    if pt is None:
        if DEBUG_MATCH:
            debug_log.append("Click attempt on None point skipped.")
        return
    try:
        phys_x_on_monitor = MON_X + pt[0]
        phys_y_on_monitor = MON_Y + pt[1]
        log_x = phys_x_on_monitor / scale_x
        log_y = phys_y_on_monitor / scale_y
        pyautogui.moveTo(log_x, log_y)
        pyautogui.mouseDown()
        if hold_ms > 0:
            time.sleep(hold_ms / 1000.0)
        pyautogui.mouseUp()
        if DEBUG_MATCH:
            debug_log.append(
                f"Clicked at physical:({pt[0]},{pt[1]}) -> logical:({log_x:.0f},{log_y:.0f}), hold:{hold_ms}ms"
            )
    except Exception as e:
        if DEBUG_MATCH:
            debug_log.append(f"Click Error: {e} at point {pt}")


def _refresh_templates():
    global TEMPLATES
    TEMPLATES = load_templates()
    if DEBUG_MATCH:
        debug_log.append("Templates reloaded.")


def set_delay_ms(ms: int):
    global delay_ms, CHECK_INTERVAL
    delay_ms = max(ms, 10)
    CHECK_INTERVAL = delay_ms / 1000.0
    debug_log.append(f"Frame-grab interval set to {delay_ms} ms.")
    tuner = get_tuner()
    if tuner:
        tuner.var_delay.set(delay_ms)


def set_is_HDR(is_hdr_param: bool):
    global is_HDR
    is_HDR = is_hdr_param
    debug_log.append(
        f"GUI HDR Preview mode set to: {'ON' if is_HDR else 'OFF'}. Note: Matching uses all variants."
    )
    tuner = get_tuner()
    if tuner:
        tuner.var_hdr.set(is_HDR)
        tuner._load_data()


def set_text_skip(skip: bool):
    global text_skip
    text_skip = skip
    debug_log.append(f"Text skip {'enabled' if skip else 'disabled'}.")
    tuner = get_tuner()
    if tuner:
        tuner.var_text_skip.set(skip)


def set_debug_mode(debug_mode: bool):
    global debug_flag, DEBUG_MATCH
    debug_flag = debug_mode
    DEBUG_MATCH = debug_mode
    debug_log.append(f"Debug mode {'enabled' if debug_mode else 'disabled'}.")
    tuner = get_tuner()
    if tuner:
        tuner.var_debug.set(debug_mode)


def set_lux_thread(lux_thr: bool):
    global lux_thread
    lux_thread = lux_thr
    debug_log.append(f"Thread Luxcavation {'enabled' if lux_thread else 'disabled'}.")
    tuner = get_tuner()
    if tuner:
        tuner.var_lux_thread.set(lux_thr)


def set_lux_exp(lux_exp_param: bool):
    global lux_EXP
    lux_EXP = lux_exp_param
    debug_log.append(f"EXP Luxcavation {'enabled' if lux_EXP else 'disabled'}.")
    tuner = get_tuner()
    if tuner:
        tuner.var_lux_EXP.set(lux_EXP)


def set_full_auto_mirror(full_auto: bool):
    global full_auto_mirror
    full_auto_mirror = full_auto
    debug_log.append(
        f"Full Auto Mirror Dungeon {'enabled' if full_auto else 'disabled'}."
    )
    tuner = get_tuner()
    if tuner:
        tuner.var_mirror_full_auto.set(full_auto)


def best_match(screen_gray: np.ndarray, tmpl: Tmpl) -> tuple[int, int] | None:
    global last_vals, last_pass, TEMPLATES, DEBUG_MATCH, debug_log
    template_name = "<unknown_template_error>"
    try:
        for name, t_obj in TEMPLATES.items():
            if t_obj is tmpl:
                template_name = name
                break
    except NameError:
        debug_log.append(
            f"Critical: Global TEMPLATES dictionary not found in best_match for {template_name}."
        )

    if tmpl.roi:
        x_roi, y_roi, w_roi, h_roi = tmpl.roi
        H_screen, W_screen = screen_gray.shape
        if any(isinstance(v, float) and v <= 1.0 for v in (x_roi, y_roi, w_roi, h_roi)):
            x_roi = int(x_roi * W_screen)
            y_roi = int(y_roi * H_screen)
            w_roi = int(w_roi * W_screen)
            h_roi = int(h_roi * H_screen)
        x_roi = max(0, x_roi)
        y_roi = max(0, y_roi)
        w_roi = min(w_roi, W_screen - x_roi)
        h_roi = min(h_roi, H_screen - y_roi)
        if w_roi <= 0 or h_roi <= 0:
            if DEBUG_MATCH:
                debug_log.append(
                    f"Match {template_name}: ROI invalid or zero size ({x_roi},{y_roi},{w_roi},{h_roi}) for screen {screen_gray.shape}"
                )
            last_vals[template_name] = -1.0
            return None
        screen_region_raw = screen_gray[y_roi : y_roi + h_roi, x_roi : x_roi + w_roi]
    else:
        x_roi, y_roi = 0, 0
        screen_region_raw = screen_gray

    if screen_region_raw.size == 0:
        if DEBUG_MATCH:
            debug_log.append(
                f"Match {template_name}: Screen region is empty. ROI: {tmpl.roi}"
            )
        last_vals[template_name] = -1.0
        return None
    try:
        screen_region_equalized = cv2.equalizeHist(screen_region_raw)
    except cv2.error as e:
        if DEBUG_MATCH:
            debug_log.append(
                f"Match {template_name}: Error equalizing screen region: {e}"
            )
        last_vals[template_name] = -1.0
        return None

    rh, rw = screen_region_equalized.shape[:2]

    # OPTIMIZATION: Reduced scales to try
    scales_to_try = [0.9, 1.0, 1.1]

    overall_best_val_for_template: float = -1.0
    overall_best_loc_for_template: tuple[int, int] | None = None
    overall_best_sz_for_template: tuple[int, int] | None = None

    if not tmpl.imgs:
        if DEBUG_MATCH:
            debug_log.append(
                f"Match {template_name}: No image variants loaded for this template."
            )
        last_vals[template_name] = -1.0
        return None

    for variant_idx, original_template_variant_img in enumerate(tmpl.imgs):
        if original_template_variant_img is None:
            if DEBUG_MATCH:
                debug_log.append(
                    f"Match {template_name}, Variant {variant_idx}: Image data is None."
                )
            continue
        for scale in scales_to_try:
            if len(original_template_variant_img.shape) < 2:
                if DEBUG_MATCH:
                    debug_log.append(
                        f"Match {template_name}, Variant {variant_idx}: Original template has invalid shape {original_template_variant_img.shape}"
                    )
                continue
            th_orig, tw_orig = original_template_variant_img.shape[:2]
            tw_scaled = int(tw_orig * scale)
            th_scaled = int(th_orig * scale)
            if tw_scaled <= 0 or th_scaled <= 0 or th_scaled > rh or tw_scaled > rw:
                continue
            try:
                scaled_template_variant = cv2.resize(
                    original_template_variant_img,
                    (tw_scaled, th_scaled),
                    interpolation=cv2.INTER_AREA,
                )
                scaled_template_variant_equalized = cv2.equalizeHist(
                    scaled_template_variant
                )
            except cv2.error as e:
                if DEBUG_MATCH:
                    debug_log.append(
                        f"Match {template_name}, Variant {variant_idx}, Scale {scale}: Error resizing/equalizing template: {e}"
                    )
                continue
            if (
                scaled_template_variant_equalized.shape[0] > rh
                or scaled_template_variant_equalized.shape[1] > rw
            ):
                continue
            try:
                res = cv2.matchTemplate(
                    screen_region_equalized,
                    scaled_template_variant_equalized,
                    cv2.TM_CCOEFF_NORMED,
                )
                _, max_val_current, _, max_loc_current = cv2.minMaxLoc(res)
            except cv2.error as e:
                if DEBUG_MATCH:
                    debug_log.append(
                        f"Match {template_name}, Variant {variant_idx}, Scale {scale}: cv2.matchTemplate error: {e}"
                    )
                continue
            if max_val_current > overall_best_val_for_template:
                overall_best_val_for_template = max_val_current
                overall_best_loc_for_template = max_loc_current
                overall_best_sz_for_template = (tw_scaled, th_scaled)
    last_vals[template_name] = overall_best_val_for_template
    if overall_best_val_for_template < tmpl.thresh:
        # REMOVED: Log for "Below threshold" as per user request.
        return None
    last_pass[template_name] = overall_best_val_for_template
    if DEBUG_MATCH:
        debug_log.append(f"-------------")
        debug_log.append(f"Match {template_name}: PASSED.")
        debug_log.append(
            f"  Score: {overall_best_val_for_template:.3f} >= {tmpl.thresh:.3f}"
        )
        debug_log.append(f"-------------")
    if overall_best_loc_for_template is None or overall_best_sz_for_template is None:
        return None
    center_x_in_region = (
        overall_best_loc_for_template[0] + overall_best_sz_for_template[0] // 2
    )
    center_y_in_region = (
        overall_best_loc_for_template[1] + overall_best_sz_for_template[1] // 2
    )
    final_cx = x_roi + center_x_in_region
    final_cy = y_roi + center_y_in_region
    return (final_cx, final_cy)


# ───────────────────────────  Main Bot Logic  ───────────────────────────────
def limbus_bot():
    local_last_grab = 0.0
    local_need_refresh = True
    local_screen_gray: np.ndarray | None = None
    game_inactive_logged_once = False

    while True:
        if pause_event.is_set():
            time.sleep(CHECK_INTERVAL)
            continue

        current_title = active_window_title()
        if "LimbusCompany" not in current_title:
            if not game_inactive_logged_once and DEBUG_MATCH:
                debug_log.append("LimbusCompany window not active. Bot idling...")
                game_inactive_logged_once = True
            time.sleep(1)
            local_need_refresh = True
            continue
        if game_inactive_logged_once:
            if DEBUG_MATCH:
                debug_log.append("LimbusCompany window now active. Resuming checks...")
            game_inactive_logged_once = False
            local_need_refresh = True

        now = time.perf_counter()
        if (
            local_need_refresh
            or local_screen_gray is None
            or (now - local_last_grab >= CHECK_INTERVAL)
        ):
            screen_gray_new = refresh_screen()
            if screen_gray_new is None:
                if DEBUG_MATCH:
                    debug_log.append("Error: Failed to capture screen. Retrying soon.")
                time.sleep(0.5)
                local_need_refresh = True
                continue
            local_screen_gray = screen_gray_new
            local_last_grab = now
            local_need_refresh = False

        if local_screen_gray is None:
            if DEBUG_MATCH:
                debug_log.append(
                    "Error: Screen data is None before checks. Forcing refresh."
                )
            local_need_refresh = True
            time.sleep(0.1)
            continue

        # [1] Win-rate check
        winrate_pt = best_match(local_screen_gray, TEMPLATES["winrate"])
        if winrate_pt:
            if DEBUG_MATCH:
                debug_log.append("[Bot Check [1] - WinRate] Action triggered.")
            h_s, w_s = local_screen_gray.shape
            pyautogui.moveTo(w_s // 2, int(h_s * 0.10))
            pyautogui.click()
            time.sleep(0.1)
            keyboard.press_and_release("p")
            time.sleep(0.25)
            keyboard.press_and_release("enter")
            time.sleep(0.25)
            local_need_refresh = True
            continue
        elif DEBUG_MATCH:
            debug_log.append("[Bot Check [1] FAILED] WinRate condition not met.")

        # [2] Speech-menu sequence
        if text_skip:
            speech_menu_pt = best_match(local_screen_gray, TEMPLATES["speech_menu"])
            if speech_menu_pt:
                if DEBUG_MATCH:
                    debug_log.append("[Bot Check [2-A] - SpeechMenu] Action triggered.")
                click(speech_menu_pt, hold_ms=10)
                time.sleep(0.5)
                local_screen_gray = refresh_screen()
                if local_screen_gray is None:
                    local_need_refresh = True
                    continue

                fast_forward_pt = best_match(
                    local_screen_gray, TEMPLATES["fast_forward"]
                )
                if fast_forward_pt:
                    if DEBUG_MATCH:
                        debug_log.append(
                            "[Bot Check [2-B] - FastForward] Action triggered."
                        )
                    click(fast_forward_pt, hold_ms=10)
                    time.sleep(0.5)
                    local_screen_gray = refresh_screen()
                    if local_screen_gray is None:
                        local_need_refresh = True
                        continue
                elif DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [2-B] FAILED] FastForward (within SpeechMenu) not found."
                    )

                choice_needed_for_skip_pt = best_match(
                    local_screen_gray, TEMPLATES["choice_needed"]
                )
                if not choice_needed_for_skip_pt:
                    confirm_speech_pt = best_match(
                        local_screen_gray, TEMPLATES["confirm"]
                    )
                    if confirm_speech_pt:
                        if DEBUG_MATCH:
                            debug_log.append(
                                "[Bot Check [2-C] - Confirm (Speech)] Action triggered."
                            )
                        click(confirm_speech_pt, hold_ms=10)
                    elif DEBUG_MATCH:
                        debug_log.append(
                            "[Bot Check [2-C] FAILED] Confirm (Speech) not found (Choice not needed)."
                        )
                elif DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [2-C] INFO] Confirm (Speech) skipped due to Choice Needed."
                    )
                local_need_refresh = True
                continue
            elif DEBUG_MATCH:
                debug_log.append(
                    "[Bot Check [2] FAILED] SpeechMenu (start of sequence) not found."
                )

        # [3] Overlays & Confirm Logic
        choice_overlay_pt = best_match(local_screen_gray, TEMPLATES["choice_needed"])
        fusion_overlay_pt = best_match(local_screen_gray, TEMPLATES["fusion_check"])
        ego_overlay_pt = best_match(local_screen_gray, TEMPLATES["ego_check"])
        ego_get_overlay_pt = best_match(local_screen_gray, TEMPLATES["ego_get"])
        is_ego_block_active = ego_overlay_pt and not ego_get_overlay_pt
        is_choice_skip_scenario = choice_overlay_pt and ego_get_overlay_pt
        action_taken_in_overlay_block = False

        if not full_auto_mirror:
            if ego_get_overlay_pt:
                if is_choice_skip_scenario:
                    if DEBUG_MATCH:
                        debug_log.append(
                            "[Bot Check [3-A] - EGO Get + Choice (Skip)] Action triggered."
                        )
                    keyboard.press_and_release("enter")
                    action_taken_in_overlay_block = True
                else:
                    if DEBUG_MATCH:
                        debug_log.append(
                            "[Bot Check [3-B] - EGO Gift Received] Action triggered."
                        )
                    keyboard.press_and_release("enter")
                    action_taken_in_overlay_block = True
            elif choice_overlay_pt:
                if DEBUG_MATCH:
                    debug_log.append("[Bot Check [3-C] - Choice Needed] Waiting...")
                action_taken_in_overlay_block = True
            elif fusion_overlay_pt:
                if DEBUG_MATCH:
                    debug_log.append("[Bot Check [3-D] - Fusion Check] Waiting...")
                action_taken_in_overlay_block = True
            elif is_ego_block_active:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [3-E] - EGO Select (Pending)] Waiting..."
                    )
                action_taken_in_overlay_block = True
            if action_taken_in_overlay_block:
                time.sleep(0.5)
                local_need_refresh = True
                continue

        black_confirm_pt = best_match(local_screen_gray, TEMPLATES["black_confirm"])
        black_confirm_v2_pt = best_match(
            local_screen_gray, TEMPLATES["black_confirm_v2"]
        )
        white_confirm_pt = best_match(local_screen_gray, TEMPLATES["confirm"])
        confirm_button_to_click = (
            black_confirm_pt or black_confirm_v2_pt or white_confirm_pt
        )
        if confirm_button_to_click:
            if DEBUG_MATCH:
                debug_log.append(
                    "[Bot Check [3-F] - General Confirm Button] Action triggered."
                )
            click(confirm_button_to_click, hold_ms=10)
            time.sleep(0.5)
            local_need_refresh = True
            continue
        elif DEBUG_MATCH and not action_taken_in_overlay_block:
            debug_log.append(
                "[Bot Check [3-F] FAILED] General Confirm Button not found."
            )

        # [4] Skip button (Abnormality events, etc.)
        skip_abno_pt = best_match(local_screen_gray, TEMPLATES["skip"])
        if skip_abno_pt:
            if DEBUG_MATCH:
                debug_log.append(
                    "[Bot Check [4-A] - Skip (Abno Start)] Action triggered."
                )
            click(skip_abno_pt, hold_ms=10)
            time.sleep(0.2)
            local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                local_need_refresh = True
                continue
            continue_abno_pt = best_match(local_screen_gray, TEMPLATES["continue"])
            if continue_abno_pt:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [4-B] - Continue (Abno)] Action triggered."
                    )
                click(continue_abno_pt, hold_ms=10)
                time.sleep(0.5)
                local_screen_gray = refresh_screen()
                if local_screen_gray is None:
                    local_need_refresh = True
                    continue
                continue_abno_pt_2 = best_match(
                    local_screen_gray, TEMPLATES["continue"]
                )
                if continue_abno_pt_2:
                    if DEBUG_MATCH:
                        debug_log.append(
                            "[Bot Check [4-B.2] - Continue x2 (Abno)] Action triggered."
                        )
                    click(continue_abno_pt_2, hold_ms=10)
                    time.sleep(0.5)
                    local_screen_gray = refresh_screen()
                    if local_screen_gray is None:
                        local_need_refresh = True
                        continue
            if full_auto_mirror:
                very_high_pt = best_match(local_screen_gray, TEMPLATES["very_high"])
                if very_high_pt:
                    if DEBUG_MATCH:
                        debug_log.append(
                            "[Bot Check [4-C] - Very High (Abno)] Action triggered."
                        )
                    click(very_high_pt, hold_ms=10)
                    time.sleep(0.5)
                    local_screen_gray = refresh_screen()
                    if local_screen_gray is None:
                        local_need_refresh = True
                        continue
            proceed_pt = best_match(local_screen_gray, TEMPLATES["proceed"])
            commence_pt = best_match(local_screen_gray, TEMPLATES["commence"])
            commence_battle_pt = best_match(
                local_screen_gray, TEMPLATES["commence_battle"]
            )
            final_abno_action_pt = proceed_pt or commence_pt or commence_battle_pt
            if final_abno_action_pt:
                action_name = (
                    "Proceed"
                    if proceed_pt
                    else "Commence" if commence_pt else "Commence Battle"
                )
                if DEBUG_MATCH:
                    debug_log.append(
                        f"[Bot Check [4-D] - {action_name} (Abno)] Action triggered."
                    )
                click(final_abno_action_pt, hold_ms=10)
                time.sleep(0.2)
                h_s, w_s = local_screen_gray.shape
                pyautogui.moveTo(w_s // 2, int(h_s * 0.90))
                pyautogui.click()
                time.sleep(0.1)
            local_need_refresh = True
            continue
        elif DEBUG_MATCH:
            debug_log.append("[Bot Check [4] FAILED] Skip (Abno Start) not found.")

        # [5] To Battle / Chain Battle
        battle_pt = best_match(local_screen_gray, TEMPLATES["battle"])
        chain_battle_pt = best_match(local_screen_gray, TEMPLATES["chain_battle"])
        if battle_pt or chain_battle_pt:
            action_name = "To Battle" if battle_pt else "Chain Battle"
            if DEBUG_MATCH:
                debug_log.append(f"[Bot Check [5] - {action_name}] Action triggered.")
            click(battle_pt or chain_battle_pt, hold_ms=10)
            time.sleep(1.0)
            local_need_refresh = True
            continue
        elif DEBUG_MATCH:
            debug_log.append("[Bot Check [5] FAILED] To Battle/Chain Battle not found.")

        # [6] Enter button
        enter_encounter_pt = best_match(local_screen_gray, TEMPLATES["enter"])
        if enter_encounter_pt:
            if DEBUG_MATCH:
                debug_log.append("[Bot Check [6] - Enter Encounter] Action triggered.")
            click(enter_encounter_pt)
            time.sleep(0.5)
            local_need_refresh = True
            continue
        elif DEBUG_MATCH:
            debug_log.append("[Bot Check [6] FAILED] Enter Encounter not found.")

        # [A] Thread Luxcavation Automation
        if lux_thread:
            if DEBUG_MATCH:
                debug_log.append("[Bot Mode Start - Thread Luxcavation]")
            if local_need_refresh:
                local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                set_lux_thread(False)
                local_need_refresh = True
                continue
            drive_pt = best_match(local_screen_gray, TEMPLATES["drive"])
            if drive_pt:
                click(drive_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [A-1] FAILED] Drive (Thread Lux) not found."
                    )
                set_lux_thread(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread(False)
                local_need_refresh = True
                continue
            lux_menu_pt = best_match(local_screen_gray, TEMPLATES["luxcavations"])
            if lux_menu_pt:
                click(lux_menu_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [A-2] FAILED] Luxcavations Menu (Thread Lux) not found."
                    )
                set_lux_thread(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread(False)
                local_need_refresh = True
                continue
            select_thread_pt = best_match(
                local_screen_gray, TEMPLATES["select_thread_lux"]
            )
            if select_thread_pt:
                click(select_thread_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [A-3] FAILED] Select Thread Lux not found."
                    )
                set_lux_thread(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread(False)
                local_need_refresh = True
                continue
            lux_enter_pt = best_match(local_screen_gray, TEMPLATES["lux_enter"])
            if lux_enter_pt:
                click(lux_enter_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [A-4] FAILED] Lux Enter (Thread Lux) not found."
                    )
                set_lux_thread(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread(False)
                local_need_refresh = True
                continue
            thread_battle_node_pt = best_match(
                local_screen_gray, TEMPLATES["thread_lux_battle"]
            )
            if thread_battle_node_pt:
                click(thread_battle_node_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [A-5] FAILED] Thread Lux Battle Node not found."
                    )
                set_lux_thread(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread(False)
                local_need_refresh = True
                continue
            to_battle_lux_pt = best_match(local_screen_gray, TEMPLATES["battle"])
            if to_battle_lux_pt:
                click(to_battle_lux_pt, hold_ms=10)
                time.sleep(2.0)
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [A-6] FAILED] To Battle (Thread Lux) not found."
                    )
                set_lux_thread(False)
                local_need_refresh = True
                continue
            if DEBUG_MATCH:
                debug_log.append(
                    "[Bot Mode End - Thread Luxcavation] Sequence complete."
                )
            set_lux_thread(False)
            local_need_refresh = True
            continue

        # [B] EXP Luxcavation Automation
        if lux_EXP:
            if DEBUG_MATCH:
                debug_log.append("[Bot Mode Start - EXP Luxcavation]")
            if local_need_refresh:
                local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                set_lux_exp(False)
                local_need_refresh = True
                continue
            drive_pt_exp = best_match(local_screen_gray, TEMPLATES["drive"])
            if drive_pt_exp:
                click(drive_pt_exp, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [B-1] FAILED] Drive (EXP Lux) not found."
                    )
                set_lux_exp(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp(False)
                local_need_refresh = True
                continue
            lux_menu_pt_exp = best_match(local_screen_gray, TEMPLATES["luxcavations"])
            if lux_menu_pt_exp:
                click(lux_menu_pt_exp, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [B-2] FAILED] Luxcavations Menu (EXP Lux) not found."
                    )
                set_lux_exp(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp(False)
                local_need_refresh = True
                continue
            select_exp_pt = best_match(local_screen_gray, TEMPLATES["select_exp_lux"])
            if select_exp_pt:
                click(select_exp_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [B-3] FAILED] Select EXP Lux not found."
                    )
                set_lux_exp(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp(False)
                local_need_refresh = True
                continue
            exp_enter_pt = best_match(local_screen_gray, TEMPLATES["exp_lux_enter"])
            if exp_enter_pt:
                click(exp_enter_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [B-4] FAILED] EXP Lux Enter not found."
                    )
                set_lux_exp(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp(False)
                local_need_refresh = True
                continue
            to_battle_exp_lux_pt = best_match(local_screen_gray, TEMPLATES["battle"])
            if to_battle_exp_lux_pt:
                click(to_battle_exp_lux_pt, hold_ms=10)
                time.sleep(2.0)
            else:
                if DEBUG_MATCH:
                    debug_log.append(
                        "[Bot Check [B-5] FAILED] To Battle (EXP Lux) not found."
                    )
                set_lux_exp(False)
                local_need_refresh = True
                continue
            if DEBUG_MATCH:
                debug_log.append("[Bot Mode End - EXP Luxcavation] Sequence complete.")
            set_lux_exp(False)
            local_need_refresh = True
            continue

        time.sleep(CHECK_INTERVAL)


# ──────────────────────── Supervisor / hotkey wrapper ──────────────────
def main():
    global TEMPLATES
    TEMPLATES = load_templates()
    if not TEMPLATES:
        print("CRITICAL: No templates loaded. Bot cannot function. Exiting.")
        debug_log.append("CRITICAL: No templates loaded. Bot cannot function. Exiting.")
        return

    config_path = resource_path("roi_thresholds.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path) as fp:
                saved_config = json.load(fp)
            for name, vals in saved_config.items():
                if name in TEMPLATE_SPEC:
                    base_cfg, _, _ = TEMPLATE_SPEC[name]
                    new_thresh = vals.get("threshold", TEMPLATE_SPEC[name][1])
                    new_roi_list = vals.get("roi")
                    new_roi = (
                        tuple(new_roi_list)
                        if isinstance(new_roi_list, list)
                        else TEMPLATE_SPEC[name][2]
                    )
                    TEMPLATE_SPEC[name] = (base_cfg, new_thresh, new_roi)
            _refresh_templates()
            debug_log.append("Loaded saved settings from roi_thresholds.json")
        except Exception as e:
            debug_log.append(
                f"Error loading roi_thresholds.json: {e}. Using default specs."
            )
    else:
        debug_log.append("roi_thresholds.json not found. Using default template specs.")

    if launch_gui and get_tuner:
        launch_gui(
            template_spec=TEMPLATE_SPEC,
            refresh_fn=_refresh_templates,
            pause_event=pause_event,
            initial_delay_ms=delay_ms,
            initial_is_HDR=is_HDR,
            initial_debug=debug_flag,
            initial_text_skip=text_skip,
            delay_cb=set_delay_ms,
            hdr_cb=set_is_HDR,
            debug_cb=set_debug_mode,
            text_skip_cb=set_text_skip,
            debug_vals_fn=lambda: last_vals,
            debug_pass_fn=lambda: last_pass,
            debug_log_fn=lambda: debug_log,
            default_spec=DEFAULT_TEMPLATE_SPEC,
            initial_lux_thread=lux_thread,
            initial_lux_EXP=lux_EXP,
            initial_mirror_full_auto=full_auto_mirror,
            lux_thread_cb=set_lux_thread,
            lux_EXP_cb=set_lux_exp,
            mirror_full_auto_cb=set_full_auto_mirror,
        )
    else:
        print("GUI is not available. Running in command-line mode.")
        debug_log.append("GUI is not available. Running in command-line mode.")

    def _on_pause_hotkey():
        tuner = get_tuner()
        if tuner:
            tuner.after(0, tuner._toggle_bot_pause_state)
        else:
            if pause_event.is_set():
                pause_event.clear()
                debug_log.append("Bot resumed via hotkey (no GUI).")
            else:
                pause_event.set()
                debug_log.append("Bot paused via hotkey (no GUI).")

    try:
        keyboard.add_hotkey(
            "ctrl+shift+d", _on_pause_hotkey, suppress=True, trigger_on_release=True
        )
    except Exception as e:
        print(f"Warning: Could not register pause hotkey (ctrl+shift+d): {e}")

    def _on_thread_hotkey():
        tuner = get_tuner()
        if tuner:
            current_state = tuner.var_lux_thread.get()
            tuner.after(
                0,
                lambda: (
                    tuner.var_lux_thread.set(not current_state),
                    tuner._toggle_thread_lux(),
                ),
            )
        else:
            set_lux_thread(not lux_thread)

    try:
        keyboard.add_hotkey(
            "ctrl+shift+t", _on_thread_hotkey, suppress=True, trigger_on_release=True
        )
    except Exception as e:
        print(f"Warning: Could not register Thread Lux hotkey (ctrl+shift+t): {e}")

    def _on_exp_hotkey():
        tuner = get_tuner()
        if tuner:
            current_state = tuner.var_lux_EXP.get()
            tuner.after(
                0,
                lambda: (
                    tuner.var_lux_EXP.set(not current_state),
                    tuner._toggle_exp_lux(),
                ),
            )
        else:
            set_lux_exp(not lux_EXP)

    try:
        keyboard.add_hotkey(
            "ctrl+shift+e", _on_exp_hotkey, suppress=True, trigger_on_release=True
        )
    except Exception as e:
        print(f"Warning: Could not register EXP Lux hotkey (ctrl+shift+e): {e}")

    try:
        keyboard.add_hotkey(
            "ctrl+alt+d", lambda: os._exit(0), suppress=True, trigger_on_release=False
        )
    except Exception as e:
        print(f"Warning: Could not register quit hotkey (ctrl+alt+d): {e}")

    debug_log.append(
        "Limbus bot initialized and ready. Press Ctrl+Shift+D to pause/resume."
    )
    print(
        "Limbus bot initialized. Check GUI or console for logs. Press Ctrl+Alt+D to force quit."
    )

    try:
        limbus_bot()
    except KeyboardInterrupt:
        debug_log.append("Bot terminated by user (KeyboardInterrupt).")
        print("\nBot terminated by user.")
    except Exception as e:
        debug_log.append(f"Bot crashed with an unhandled exception: {e}")
        import traceback

        traceback.print_exc()
        print(f"Bot crashed: {e}")
    finally:
        debug_log.append("Bot shutting down.")
        print("Bot shutting down.")
        os._exit(0)


if __name__ == "__main__":
    main()
