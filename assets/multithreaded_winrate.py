#!/usr/bin/env python3
"""
Auto-pilot for Limbus Company battles (Multithreaded Core Logic Version with GUI).
Includes runtime crash logging, robust import handling, and randomized delays to avoid detection.
"""

# ── std-lib imports ───────────────────────────────────────────────────
import os
import threading
import time
import sys
import json
import random
from collections import namedtuple
import copy
from concurrent.futures import ThreadPoolExecutor
import math
import traceback
from datetime import datetime


# ── auto-installer for third-party packages ───────────────────────────
def _require(pkg, import_as=None, pypi_name=None):
    import importlib
    import subprocess

    name_to_install = pypi_name or pkg
    module_name_to_import = import_as if import_as else pkg

    try:
        if import_as:
            return importlib.import_module(pkg, package=import_as)
        else:
            return importlib.import_module(pkg)
    except ModuleNotFoundError:
        print(
            f"[setup] '{module_name_to_import}' not found. Attempting to install '{name_to_install}'…"
        )
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", name_to_install]
            )
            if import_as:
                return importlib.import_module(pkg, package=import_as)
            else:
                return importlib.import_module(pkg)
        except Exception as e:
            sys.exit(
                f"Critical dependency '{name_to_install}' installation failed: {e}"
            )


# --- Conditional Imports ---
if getattr(sys, "frozen", False):
    import cv2
    import numpy as np
    import pyautogui
    import keyboard
    import pygetwindow as gw
    import mss
    from PIL import Image, ImageTk 
else:
    cv2 = _require("cv2", pypi_name="opencv-python")
    np        = _require("numpy")
    pyautogui = _require("pyautogui") 
    keyboard  = _require("keyboard")
    gw        = _require("pygetwindow", import_as="pygetwindow") 
    mss       = _require("mss")
    _require("PIL", pypi_name="Pillow") 
    from PIL import Image, ImageTk 

# --- GUI Import ---
try:
    from multithreaded_gui_config import launch_gui, get_tuner
except ImportError as e:
    sys.exit(
        f"CRITICAL ERROR: GUI module (multithreaded_gui_config.py) could not be imported. {e}"
    )

# --- Global Variables ---
pause_event = threading.Event()
delay_ms = 10
is_HDR = False
debug_flag = True
text_skip = False
lux_thread = False
lux_EXP = False
full_auto_mirror = False
CHECK_INTERVAL = delay_ms / 1000.0
DEBUG_MATCH = debug_flag
last_vals: dict[str, float] = {}
last_pass: dict[str, float] = {}
debug_log: list[str] = []
debug_log_lock = threading.Lock()
LAST_MOUSE_POS: tuple[int, int] | None = None
LAST_MOUSE_TIME: float = 0.0
MOUSE_SHAKE_DISTANCE_THRESHOLD: int = 1000
MOUSE_SHAKE_TIME_WINDOW: float = 0.15
MOUSE_SHAKES_DETECTED: int = 0
MOUSE_SHAKES_TO_PAUSE: int = 5
LAST_SHAKE_TIME: float = 0.0

Tmpl = namedtuple("Tmpl", "imgs masks thresh roi")
# Only checking for winrate now
TEMPLATE_SPEC = {
    "winrate": ("winrate", 0.75, (0.50, 0.70, 0.50, 0.30)),
}
DEFAULT_TEMPLATE_SPEC = copy.deepcopy(TEMPLATE_SPEC)
TEMPLATES: dict[str, Tmpl] = {}


# --- Anti-Detection Helper ---
def random_delay(min_s=0.5, max_s=1.0):
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)


# --- Config Callbacks ---
def set_delay_ms_config(ms):
    global delay_ms, CHECK_INTERVAL
    delay_ms = max(10, ms)
    CHECK_INTERVAL = delay_ms / 1000.0


def set_hdr_preview_config(state):
    global is_HDR
    is_HDR = state


def set_text_skip_config(state):
    global text_skip
    text_skip = state


def set_debug_mode_config(state):
    global debug_flag, DEBUG_MATCH
    debug_flag = DEBUG_MATCH = state


def set_lux_thread_config(state):
    global lux_thread
    lux_thread = state


def set_lux_exp_config(state):
    global lux_EXP
    lux_EXP = state


def set_full_auto_mirror_config(state):
    global full_auto_mirror
    full_auto_mirror = state


# --- Utilities ---
def get_application_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APPLICATION_BASE_PATH = get_application_path()


def resource_path(fname):
    base = (
        sys._MEIPASS
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        else os.path.dirname(os.path.abspath(__file__))
    )
    return os.path.join(base, fname)


def load_templates():
    out = {}
    for name, (base, thresh, roi) in TEMPLATE_SPEC.items():
        vars, masks = [], []
        for sfx in (" SDR.png", " HDR.png", ".png"):
            p = resource_path(os.path.join("images", base + sfx))
            if os.path.isfile(p):
                img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    if img.shape[2] == 4:
                        vars.append(cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY))
                        masks.append((img[:, :, 3] > 0).astype(np.uint8))
                    else:
                        vars.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
                        masks.append(None)
        if vars:
            out[name] = Tmpl(vars, masks, thresh, roi)
    return out


def _refresh_templates_from_gui():
    global TEMPLATES
    for name, tmpl_obj in TEMPLATES.items():
        if name in TEMPLATE_SPEC:
            _, nt, nr = TEMPLATE_SPEC[name]
            TEMPLATES[name] = tmpl_obj._replace(thresh=nt, roi=nr)


def active_window_title():
    try:
        return gw.getActiveWindow().title
    except:
        return ""


grabber = mss.mss()
mon = grabber.monitors[1] if len(grabber.monitors) > 1 else grabber.monitors[0]
scale_x, scale_y = (
    mon["width"] / pyautogui.size()[0],
    mon["height"] / pyautogui.size()[1],
)


def refresh_screen():
    try:
        return cv2.cvtColor(np.array(grabber.grab(mon))[:, :, :3], cv2.COLOR_BGR2GRAY)
    except:
        return None


def click(pt, hold_ms=0):
    if not pt:
        return
    try:
        pyautogui.moveTo(
            (mon["left"] + pt[0]) / scale_x, (mon["top"] + pt[1]) / scale_y
        )
        pyautogui.mouseDown()
        if hold_ms > 0:
            time.sleep(
                (hold_ms + random.randint(-2, 5)) / 1000.0
            )  # Randomized hold time slightly
        pyautogui.mouseUp()
    except:
        pass


def best_match(screen_gray, tmpl_obj):
    H_s, W_s = screen_gray.shape
    x_r, y_r, w_r, h_r = tmpl_obj.roi
    if any(isinstance(v, float) for v in (x_r, y_r, w_r, h_r)):
        x_r, y_r, w_r, h_r = (
            int(x_r * W_s),
            int(y_r * H_s),
            int(w_r * W_s),
            int(h_r * H_s),
        )

    region = cv2.equalizeHist(screen_gray[y_r : y_r + h_r, x_r : x_r + w_r])
    bv, bl, bz = -1.0, None, None
    for tpl in tmpl_obj.imgs:
        for s in [0.9, 1.0, 1.1]:
            tw, th = int(tpl.shape[1] * s), int(tpl.shape[0] * s)
            if tw > region.shape[1] or th > region.shape[0]:
                continue
            st = cv2.equalizeHist(cv2.resize(tpl, (tw, th)))
            res = cv2.matchTemplate(region, st, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(res)
            if mv > bv:
                bv, bl, bz = mv, ml, (tw, th)
    if bv >= tmpl_obj.thresh:
        return (x_r + bl[0] + bz[0] // 2, y_r + bl[1] + bz[1] // 2)
    return None


def limbus_bot():
    last_grab = 0.0
    need_refresh = True
    scr = None
    PRIO = ["winrate"]

    while True:
        if pause_event.is_set() or "LimbusCompany" not in active_window_title():
            time.sleep(0.5)
            continue

        now = time.perf_counter()
        if need_refresh or (now - last_grab >= CHECK_INTERVAL):
            scr = refresh_screen()
            last_grab, need_refresh = now, False
        if scr is None:
            continue

        batch = {n: TEMPLATES[n] for n in PRIO if n in TEMPLATES}
        results = {}
        with ThreadPoolExecutor() as exe:
            futs = {exe.submit(best_match, scr, obj): n for n, obj in batch.items()}
            for f in futs:
                results[futs[f]] = f.result()

        if results.get("winrate"):
            h, w = scr.shape

            # Apply jitter to coordinates to simulate human inaccuracy
            target_x = (w // 2) + random.randint(-15, 15)
            target_y = int(h * 0.1) + random.randint(-10, 10)

            pyautogui.click(target_x, target_y)

            # Randomized timing gaps
            random_delay(0.08, 0.25)
            keyboard.press_and_release("p")
            random_delay(0.35, 0.7)
            keyboard.press_and_release("enter")
            random_delay(0.5, 1.1)

            need_refresh = True
            continue

        # Add human-like random variance to the idle wait loop
        time.sleep(CHECK_INTERVAL + random.uniform(0.01, 0.08))


def main():
    global TEMPLATES
    TEMPLATES = load_templates()

    launch_gui(
        template_spec_from_bot=TEMPLATE_SPEC,
        default_template_spec_for_reset=DEFAULT_TEMPLATE_SPEC,
        refresh_templates_callback=_refresh_templates_from_gui,
        pause_event_from_bot=pause_event,
        initial_delay_ms=delay_ms,
        initial_is_HDR=is_HDR,
        initial_debug=debug_flag,
        initial_text_skip=text_skip,
        initial_lux_thread=lux_thread,
        initial_lux_EXP=lux_EXP,
        initial_mirror_full_auto=full_auto_mirror,
        set_delay_ms_cb=set_delay_ms_config,
        set_hdr_preview_cb=set_hdr_preview_config,
        set_debug_mode_cb=set_debug_mode_config,
        set_text_skip_cb=set_text_skip_config,
        set_lux_thread_cb=set_lux_thread_config,
        set_lux_EXP_cb=set_lux_exp_config,
        set_mirror_full_auto_cb=set_full_auto_mirror_config,
        get_last_vals_fn=lambda: last_vals,
        get_last_pass_fn=lambda: last_pass,
        get_debug_log_fn=lambda: debug_log,
    )

    limbus_bot()

if __name__ == "__main__":
    main()
