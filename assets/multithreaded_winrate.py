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
import random
from collections import namedtuple
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import ctypes
from ctypes import wintypes

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
else:
    cv2 = _require("cv2", pypi_name="opencv-python")
    np        = _require("numpy")
    pyautogui = _require("pyautogui") 
    keyboard  = _require("keyboard")
    gw        = _require("pygetwindow", import_as="pygetwindow") 
    mss       = _require("mss")
    _require("PIL", pypi_name="Pillow") 


# --- GUI Import ---
try:
    from multithreaded_gui_config import launch_gui, get_tuner
except ImportError as e:
    sys.exit(
        f"CRITICAL ERROR: GUI module (multithreaded_gui_config.py) could not be imported. {e}"
    )


# --- Windows API for Background Input ---
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_P = 0x50
VK_RETURN = 0x0D

user32 = ctypes.windll.user32

# Cache for window handle
_cached_hwnd = None
_cached_hwnd_lock = threading.Lock()


def find_game_window():
    """Find the Limbus Company game window handle."""
    try:
        # First try exact title match using Windows API
        hwnd = user32.FindWindowW(None, "LimbusCompany")
        if hwnd:
            return hwnd

        # Try partial match with pygetwindow
        windows = gw.getWindowsWithTitle("LimbusCompany")
        if windows:
            return windows[0]._hWnd

        # Try other common window titles
        for title in ["Limbus", "limbus"]:
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                return hwnd
            windows = gw.getWindowsWithTitle(title)
            if windows:
                return windows[0]._hWnd

        return None
    except Exception:
        return None


def send_key_with_focus_pulse(key_str):
    """Temporarily focuses the game, sends ONE key, and restores focus instantly."""
    global _cached_hwnd
    hwnd = _cached_hwnd if _cached_hwnd else find_game_window()
    if not hwnd:
        return False

    try:
        with _cached_hwnd_lock:
            _cached_hwnd = hwnd

        # Get current foreground window
        current_fg = user32.GetForegroundWindow()

        # If game is already in foreground, just send inputs directly
        if current_fg == hwnd:
            keyboard.press_and_release(key_str)
            return True

        # Bring game to front (SW_RESTORE=9 in case it's minimized)
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.03)  # Lightning fast wait for window switch

        # Hardware key simulation to the now-foreground game
        keyboard.press_and_release(key_str)

        time.sleep(0.02)  # Tiny wait for game engine to read input

        # Restore previous foreground window instantly
        if current_fg and current_fg != hwnd:
            user32.SetForegroundWindow(current_fg)

        return True
    except Exception as e:
        try:
            append_debug_log(f"Focus pulse failed: {e}")
        except:
            pass
        return False


# --- Global Variables ---
pause_event = threading.Event()
delay_ms = 10
is_HDR = False
debug_flag = True
text_skip = False
lux_thread = False
lux_EXP = False
full_auto_mirror = False
background_mode = False  # Allow bot to run even when window is not foreground
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


def set_background_mode_config(state):
    global background_mode
    background_mode = state


# --- Utilities ---
def get_application_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APPLICATION_BASE_PATH = get_application_path()


def resource_path(fname):
    base = (
        getattr(sys, "_MEIPASS")
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
        window = gw.getActiveWindow()
        return window.title if window else ""
    except:
        return ""


def append_debug_log(message: str):
    """Append a timestamped message for the GUI debug log."""
    if not DEBUG_MATCH:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    with debug_log_lock:
        debug_log.append(f"[{timestamp}] {message}")
        # Keep the GUI responsive during long sessions.
        if len(debug_log) > 500:
            del debug_log[: len(debug_log) - 500]


grabber = mss.MSS()
mon = grabber.monitors[1] if len(grabber.monitors) > 1 else grabber.monitors[0]
scale_x, scale_y = (
    mon["width"] / pyautogui.size()[0],
    mon["height"] / pyautogui.size()[1],
)

gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def capture_window_cv2(hwnd):
    """Captures a specific window's contents directly using PrintWindow."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        return None

    hwndDC = user32.GetWindowDC(hwnd)
    mfcDC = gdi32.CreateCompatibleDC(hwndDC)
    saveBitMap = gdi32.CreateCompatibleBitmap(hwndDC, width, height)
    gdi32.SelectObject(mfcDC, saveBitMap)

    # PW_RENDERFULLCONTENT (2) | PW_CLIENTONLY (1) = 3
    # This flag allows capturing hardware-accelerated windows in Windows 8.1+
    result = user32.PrintWindow(hwnd, mfcDC, 3)

    if result == 0:
        gdi32.DeleteObject(saveBitMap)
        gdi32.DeleteDC(mfcDC)
        user32.ReleaseDC(hwnd, hwndDC)
        return None

    bmp_info = BITMAPINFO()
    bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmp_info.bmiHeader.biWidth = width
    bmp_info.bmiHeader.biHeight = -height  # Negative for Top-down
    bmp_info.bmiHeader.biPlanes = 1
    bmp_info.bmiHeader.biBitCount = 32
    bmp_info.bmiHeader.biCompression = 0  # BI_RGB

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mfcDC, saveBitMap, 0, height, buffer, ctypes.byref(bmp_info), 0)

    gdi32.DeleteObject(saveBitMap)
    gdi32.DeleteDC(mfcDC)
    user32.ReleaseDC(hwnd, hwndDC)

    # Convert raw BGRA buffer to numpy array, then to grayscale
    img = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)


def refresh_screen():
    global _cached_hwnd

    if background_mode:
        hwnd = _cached_hwnd if _cached_hwnd else find_game_window()
        if hwnd:
            with _cached_hwnd_lock:
                _cached_hwnd = hwnd
            img = capture_window_cv2(hwnd)
            if img is not None:
                return img

    # Fallback to standard monitor capture if not in background mode or PrintWindow fails
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
    if bl is not None and bz is not None:
        pt = (x_r + bl[0] + bz[0] // 2, y_r + bl[1] + bz[1] // 2)
    else:
        pt = None

    return pt, float(bv)


def limbus_bot():
    last_grab = 0.0
    need_refresh = True
    scr = None
    append_debug_log("Debug log started.")

    while True:
        if pause_event.is_set():
            time.sleep(0.5)
            continue

        # If not in background mode, check if window is active
        if not background_mode and "LimbusCompany" not in active_window_title():
            time.sleep(0.5)
            continue

        now = time.perf_counter()
        if need_refresh or (now - last_grab >= CHECK_INTERVAL):
            scr = refresh_screen()
            last_grab, need_refresh = now, False
        if scr is None:
            continue

        # Check whatever templates are currently loaded. This supports winrate-only
        # configs and any other combination of tests added to TEMPLATE_SPEC.
        active_tests = [name for name in TEMPLATE_SPEC.keys() if name in TEMPLATES]
        batch = {name: TEMPLATES[name] for name in active_tests}
        results = {}

        if batch:
            with ThreadPoolExecutor(max_workers=max(1, len(batch))) as exe:
                futs = {
                    exe.submit(best_match, scr, obj): name
                    for name, obj in batch.items()
                }

                for f in futs:
                    name = futs[f]
                    try:
                        res = f.result()
                        if res is None:
                            point, score = None, 0.0
                        else:
                            point, score = res
                    except Exception as exc:
                        point, score = None, 0.0
                        append_debug_log(f"{name}: match error: {exc}")

                    score = max(0.0, min(1.0, float(score)))
                    threshold = max(0.0, min(1.0, float(TEMPLATES[name].thresh)))

                    last_vals[name] = score

                    if score >= threshold:
                        results[name] = point
                        last_pass[name] = score
                        append_debug_log(f"{name}: PASS {score:.3f}>={threshold:.3f}")
        else:
            append_debug_log(
                "No templates loaded. Check image filenames and TEMPLATE_SPEC."
            )
            time.sleep(0.5)
            continue

        if results.get("winrate"):
            # h, w = scr.shape

            # # Apply jitter to coordinates to simulate human inaccuracy
            # target_x = (w // 2) + random.randint(-15, 15)
            # target_y = int(h * 0.1) + random.randint(-10, 10)

            # random_delay(0.75, 1.5)
            # pyautogui.click(target_x, target_y)

            # Randomized timing gaps (bot avoidance)
            random_delay(0.5, 3.0)

            if background_mode:
                # Use lightning-fast focus stealing pulses to minimize interruption
                append_debug_log("Pulsing P key")
                success_p = send_key_with_focus_pulse("p")

                # Do the random bot-avoidance delay while focus is safely restored to your app!
                random_delay(0.4, 0.9)

                append_debug_log("Pulsing ENTER key")
                success_enter = send_key_with_focus_pulse("enter")

                if not success_p or not success_enter:
                    append_debug_log(
                        "Focus method failed, falling back to foreground inputs"
                    )
                    keyboard.press_and_release("p")
                    random_delay(0.4, 0.9)
                    keyboard.press_and_release("enter")
            else:
                # Send inputs to foreground window (traditional method)
                keyboard.press_and_release("p")
                random_delay(0.2, 0.5)
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
        initial_background_mode=background_mode,
        set_delay_ms_cb=set_delay_ms_config,
        set_hdr_preview_cb=set_hdr_preview_config,
        set_debug_mode_cb=set_debug_mode_config,
        set_text_skip_cb=set_text_skip_config,
        set_lux_thread_cb=set_lux_thread_config,
        set_lux_EXP_cb=set_lux_exp_config,
        set_mirror_full_auto_cb=set_full_auto_mirror_config,
        set_background_mode_cb=set_background_mode_config,
        get_last_vals_fn=lambda: last_vals,
        get_last_pass_fn=lambda: last_pass,
        get_debug_log_fn=lambda: debug_log,
    )

    limbus_bot()

if __name__ == "__main__":
    main()
