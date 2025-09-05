#!/usr/bin/env python3
"""
Auto-pilot for Limbus Company battles (Multithreaded Core Logic Version with GUI).
Includes runtime crash logging and robust import handling.
"""

# ── std-lib imports ───────────────────────────────────────────────────
import os
import threading
import time
import sys
import json
from collections import namedtuple
import copy
from concurrent.futures import ThreadPoolExecutor
import math
import traceback  # For formatting tracebacks
from datetime import datetime  # For timestamping crash logs


# ── auto-installer for third-party packages ───────────────────────────
def _require(pkg, import_as=None, pypi_name=None):
    """
    Imports a package, installing it if not found.
    Exits script if a critical package fails to install or import.
    """
    import importlib
    import subprocess

    name_to_install = pypi_name or pkg
    module_name_to_import = import_as if import_as else pkg

    try:
        # First attempt to import
        if import_as:
            return importlib.import_module(
                pkg, package=import_as
            )  # For cases like "from package import module as alias"
        else:
            return importlib.import_module(pkg)
    except ModuleNotFoundError:
        print(
            f"[setup] '{module_name_to_import}' not found. Attempting to install '{name_to_install}'…"
        )
        try:
            # Attempt to install
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", name_to_install]
            )
            # Second attempt to import after installation
            print(
                f"[setup] Installation of '{name_to_install}' complete. Importing '{module_name_to_import}'..."
            )
            if import_as:
                return importlib.import_module(pkg, package=import_as)
            else:
                return importlib.import_module(pkg)
        except subprocess.CalledProcessError as e:
            print(
                f"ERROR: Failed to install package '{name_to_install}'. Pip command failed. Exception: {e}",
                file=sys.stderr,
            )
            print(
                f"Please try installing it manually: pip install {name_to_install}",
                file=sys.stderr,
            )
            sys.exit(f"Critical dependency '{name_to_install}' installation failed.")
        except ModuleNotFoundError:
            print(
                f"ERROR: Package '{name_to_install}' was reportedly installed, but module '{module_name_to_import}' still could not be imported.",
                file=sys.stderr,
            )
            sys.exit(
                f"Critical dependency '{module_name_to_import}' import failed after installation."
            )
        except (
            Exception
        ) as e:  # Catch any other unexpected errors during post-install import
            print(
                f"ERROR: An unexpected error occurred while trying to import '{module_name_to_import}' after installing '{name_to_install}'. Exception: {e}",
                file=sys.stderr,
            )
            sys.exit(
                f"Unexpected error with package '{module_name_to_import}' after installation."
            )
    except (
        Exception
    ) as e:  # Catch any other unexpected errors during initial import attempt
        print(
            f"ERROR: An unexpected error occurred while trying to import '{module_name_to_import}'. Exception: {e}",
            file=sys.stderr,
        )
        sys.exit(f"Unexpected error with package '{module_name_to_import}'.")


# --- Conditional Imports for PyInstaller and Normal Execution ---
if getattr(sys, 'frozen', False):  # Running as a PyInstaller bundle
    print("INFO: Running as a PyInstaller frozen executable.")
    import cv2
    import numpy as np
    import pyautogui
    import keyboard
    import pygetwindow 
    gw = pygetwindow 
    import mss
    from PIL import Image, ImageTk 
else:  # Running as a script
    print("INFO: Running as a Python script.")
    cv2       = _require("cv2",        pypi_name="opencv-python")
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
    # If GUI cannot be imported, print an error and exit.
    # This prevents the script from running in headless mode if the GUI is critical.
    error_message = f"CRITICAL ERROR: GUI module (multithreaded_gui_config.py) could not be imported. Exception: {e}"
    print(error_message, file=sys.stderr)
    # Optionally, write to a startup log or use the crash handler if it's already defined
    # For now, just print and exit.
    if "handle_exception" in globals() and callable(handle_exception):
        # If handle_exception is defined, use it to log this critical startup error
        try:
            handle_exception(
                ImportError, ImportError(f"GUI module failed to import: {e}"), None
            )
        except Exception as he_e:
            print(
                f"Error trying to use custom exception handler for GUI import failure: {he_e}",
                file=sys.stderr,
            )
    sys.exit(1)  # Exit with a non-zero status code to indicate an error

# --- Global Variables ---
# PyAutoGUI settings are now moved to main() after successful import.
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
MOUSE_SHAKE_DISTANCE_THRESHOLD: int = 200
MOUSE_SHAKE_TIME_WINDOW: float = 0.15
MOUSE_SHAKES_DETECTED: int = 0
MOUSE_SHAKES_TO_PAUSE: int = 5
LAST_SHAKE_TIME: float = 0.0
failsafe_timer: float = 5.0

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
    "selectable": ("Choice Check", 0.70, (0.45, 0.20, 0.45, 0.15)),
    "fusion_check": ("Fusion Check", 0.70, (0.20, 0.00, 0.60, 0.30)),
    # "ego_check": ("EGO Check", 0.80, (0.33, 0.22, 0.33, 0.10)),
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

# --- Path Helper ---
def get_application_path() -> str:
    """Returns the base path for the application (script directory or exe directory)."""
    if getattr(sys, 'frozen', False): # Running as a PyInstaller bundle
        return os.path.dirname(sys.executable)
    else: # Running as a script
        return os.path.dirname(os.path.abspath(__file__))

APPLICATION_BASE_PATH = get_application_path() # Define this once globally


# --- Crash Log Handler ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """Custom exception hook to log unhandled exceptions to a file."""
    global debug_log 
    # Use APPLICATION_BASE_PATH for log directory
    log_subdir = "crash_logs"; log_dir_path = os.path.join(APPLICATION_BASE_PATH, log_subdir)
    try:
        if not os.path.exists(log_dir_path): os.makedirs(log_dir_path)
    except Exception as e:
        print(f"CRITICAL: Could not create crash log directory at {log_dir_path}: {e}", file=sys.stderr)
        log_dir_path = APPLICATION_BASE_PATH 
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S"); log_file_name = f"crash_report_{timestamp}.log"
    log_file_path = os.path.join(log_dir_path, log_file_name)
    recent_debug_logs = []
    if 'debug_log' in globals() and isinstance(debug_log, list): 
        try: log_copy = list(debug_log); recent_debug_logs = log_copy[-50:] 
        except Exception as e_log: recent_debug_logs = [f"Error retrieving recent debug logs: {e_log}"]
    debug_log_section = "\n--- Recent Debug Log (Last 50 Lines) ---\n"
    if recent_debug_logs:
        for log_entry in recent_debug_logs: debug_log_section += f"{log_entry}\n"
    else: debug_log_section += "No recent debug logs available or debug_log is empty.\n"
    debug_log_section += "----------------------------------------\n"
    error_message_traceback = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    full_log_message = (
        f"--- CRASH REPORT ---\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Exception Type: {exc_type.__name__}\nException Value: {exc_value}\n"
        f"--- Traceback ---\n{error_message_traceback}{debug_log_section}---------------------\n"
    )
    try:
        with open(log_file_path, "w", encoding="utf-8") as f: f.write(full_log_message)
        print(f"CRITICAL ERROR: Unhandled exception. Crash report: {log_file_path}", file=sys.stderr)
    except Exception as e:
        print(f"CRITICAL: Could not write crash report to {log_file_path}: {e}", file=sys.stderr)
        print(f"--- Fallback Crash Info ---\n{full_log_message}", file=sys.stderr)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(full_log_message)
        print(f"CRITICAL ERROR: Unhandled exception. Crash report saved to: {log_file_path}", file=sys.stderr)
    except Exception as e:
        print(f"CRITICAL: Could not write crash report to {log_file_path}: {e}", file=sys.stderr)
        # Fallback: print the full message to stderr if file writing fails
        print(f"--- Fallback Crash Info (Not Written to File) ---\n{full_log_message}", file=sys.stderr)

    # Also call the default excepthook to print to stderr if possible
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# --- Helper Functions (resource_path, load_templates, active_window_title, etc.) ---
def resource_path(fname: str) -> str:
    """
    Returns the absolute path to a resource file.
    If frozen, it looks in sys._MEIPASS (PyInstaller's temp dir for bundled data).
    Otherwise, it looks relative to the script's directory.
    This is primarily for assets bundled with --add-data.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Path for bundled data files in PyInstaller
        base_path = sys._MEIPASS
    else:
        # Path for local script execution
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, fname)


def load_templates() -> dict[str, Tmpl]:
    out: dict[str, Tmpl] = {}
    for name, (base, thresh, roi) in TEMPLATE_SPEC.items():
        loaded_template_variants: list[np.ndarray] = []
        corresponding_masks: list[np.ndarray | None] = []
        preferred_suffixes = (" SDR.png", " HDR.png")
        for suffix in preferred_suffixes:
            # Look for the image inside the "images" subfolder
            path = resource_path(os.path.join("images", base + suffix))
            if os.path.isfile(path):
                try:
                    img_data = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                    if img_data is None:
                        if DEBUG_MATCH:
                            with debug_log_lock:
                                debug_log.append(
                                    f"Template Load: Failed read {path} for {name}"
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
                        with debug_log_lock:
                            debug_log.append(f"Template Load: Loaded {path} for {name}")
                except Exception as e:
                    if DEBUG_MATCH:
                        with debug_log_lock:
                            debug_log.append(
                                f"Template Load: Error processing {path} for {name}: {e}"
                            )
        if not loaded_template_variants:
            # Also check the fallback path inside the "images" subfolder
            fallback_path = resource_path(os.path.join("images", base + ".png"))
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
                            with debug_log_lock:
                                debug_log.append(
                                    f"Template Load: Loaded FALLBACK {fallback_path} for {name}"
                                )
                    elif DEBUG_MATCH:
                        with debug_log_lock:
                            debug_log.append(
                                f"Template Load: Failed read FALLBACK {fallback_path} for {name}"
                            )
                except Exception as e:
                    if DEBUG_MATCH:
                        with debug_log_lock:
                            debug_log.append(
                                f"Template Load: Error processing FALLBACK {fallback_path} for {name}: {e}"
                            )
        if not loaded_template_variants:
            with debug_log_lock:
                debug_log.append(
                    f"Critical: No image files for template '{name}' (base: '{base}'). Skipped."
                )
            continue
        out[name] = Tmpl(loaded_template_variants, corresponding_masks, thresh, roi)
    if not out and DEBUG_MATCH:
        with debug_log_lock:
            debug_log.append("Critical: No templates loaded at all.")
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
    primary_monitor_info = grabber.monitors[0]
MON_X, MON_Y = primary_monitor_info["left"], primary_monitor_info["top"]
MON_W, MON_H = primary_monitor_info["width"], primary_monitor_info["height"]
try:
    LOG_W, LOG_H = pyautogui.size()
    scale_x = MON_W / LOG_W if LOG_W > 0 else 1.0
    scale_y = MON_H / LOG_H if LOG_H > 0 else 1.0
except Exception:
    scale_x, scale_y = 1.0, 1.0


def refresh_screen() -> np.ndarray | None:
    try:
        sct_img = grabber.grab(primary_monitor_info)
        img = np.array(sct_img)
        return cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    except Exception as e:
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(f"Screen Grab Error: {e}")
            print(f"Screen Grab Error: {e}")
        return None


def click(pt: tuple[int, int] | None, hold_ms: int = 0):
    if pt is None:
        return
    try:
        phys_x = MON_X + pt[0]
        phys_y = MON_Y + pt[1]
        log_x = phys_x / scale_x
        log_y = phys_y / scale_y
        pyautogui.moveTo(log_x, log_y)
        pyautogui.mouseDown()
        if hold_ms > 0:
            time.sleep(hold_ms / 1000.0)
        pyautogui.mouseUp()
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(f"Clicked at physical:({pt[0]},{pt[1]})")
    except Exception as e:
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(f"Click Error: {e} at {pt}")


def _refresh_templates_from_gui():
    """
    Updates the 'thresh' and 'roi' in the live TEMPLATES dictionary
    based on the latest values in TEMPLATE_SPEC, without reloading images from disk.
    """
    global TEMPLATES, TEMPLATE_SPEC, DEBUG_MATCH

    updated_count = 0
    for name, tmpl_obj in TEMPLATES.items():
        if name in TEMPLATE_SPEC:
            # Get the latest settings from the spec dictionary (which the GUI modified)
            _base_filename, new_thresh, new_roi = TEMPLATE_SPEC[name]

            # If the settings are actually different, update them
            if tmpl_obj.thresh != new_thresh or tmpl_obj.roi != new_roi:
                # Use the efficient _replace method to create a new Tmpl tuple
                # with the new values, while reusing the existing 'imgs' and 'masks'.
                TEMPLATES[name] = tmpl_obj._replace(thresh=new_thresh, roi=new_roi)
                updated_count += 1

    if updated_count > 0 and DEBUG_MATCH:
        # Log a more accurate and less frequent message
        with debug_log_lock:
            debug_log.append(
                f"Synchronized {updated_count} template setting(s) from GUI."
            )


def set_delay_ms_config(ms: int):
    global delay_ms, CHECK_INTERVAL
    delay_ms = max(ms, 10)
    CHECK_INTERVAL = delay_ms / 1000.0
    with debug_log_lock:
        debug_log.append(f"Frame-grab interval set to {delay_ms} ms.")


def set_hdr_preview_config(is_hdr_active: bool):
    global is_HDR
    is_HDR = is_hdr_active
    with debug_log_lock:
        debug_log.append(f"GUI HDR Preview mode set to: {'ON' if is_HDR else 'OFF'}.")


def set_text_skip_config(skip: bool):
    global text_skip
    text_skip = skip
    with debug_log_lock:
        debug_log.append(f"Text skip {'enabled' if skip else 'disabled'}.")


def set_debug_mode_config(debug_mode: bool):
    global debug_flag, DEBUG_MATCH
    debug_flag = debug_mode
    DEBUG_MATCH = debug_mode
    with debug_log_lock:
        debug_log.append(f"Debug mode {'enabled' if debug_mode else 'disabled'}.")


def set_lux_thread_config(state: bool):
    global lux_thread
    lux_thread = state
    with debug_log_lock:
        debug_log.append(f"Thread Lux set to: {state}")


def set_lux_exp_config(state: bool):
    global lux_EXP
    lux_EXP = state
    with debug_log_lock:
        debug_log.append(f"EXP Lux set to: {state}")


def set_full_auto_mirror_config(state: bool):
    global full_auto_mirror
    full_auto_mirror = state
    with debug_log_lock:
        debug_log.append(f"Mirror Auto set to: {state}")


def best_match(screen_gray: np.ndarray, tmpl_obj: Tmpl) -> tuple[int, int] | None:
    global last_vals, last_pass, TEMPLATES, DEBUG_MATCH, debug_log
    template_name = "<unknown_template_error>"
    try:
        for name, t_obj_iter in TEMPLATES.items():
            if t_obj_iter is tmpl_obj:
                template_name = name
                break
    except NameError:
        with debug_log_lock:
            debug_log.append(
                f"Critical: Global TEMPLATES not found in best_match for {template_name}."
            )

    if tmpl_obj.roi:
        x_r, y_r, w_r, h_r = tmpl_obj.roi
        H_s, W_s = screen_gray.shape
        if any(isinstance(v, float) and v <= 1.0 for v in (x_r, y_r, w_r, h_r)):
            x_r = int(x_r * W_s)
            y_r = int(y_r * H_s)
            w_r = int(w_r * W_s)
            h_r = int(h_r * H_s)
        x_r = max(0, x_r)
        y_r = max(0, y_r)
        w_r = min(w_r, W_s - x_r)
        h_r = min(h_r, H_s - y_r)
        if w_r <= 0 or h_r <= 0:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        f"Match {template_name}: ROI invalid for screen {screen_gray.shape}"
                    )
            last_vals[template_name] = -1.0
            return None
        screen_region_raw = screen_gray[y_r : y_r + h_r, x_r : x_r + w_r]
    else:
        x_r, y_r = 0, 0
        screen_region_raw = screen_gray
    if screen_region_raw.size == 0:
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(
                    f"Match {template_name}: Screen region empty. ROI: {tmpl_obj.roi}"
                )
        last_vals[template_name] = -1.0
        return None
    try:
        screen_region_equalized = cv2.equalizeHist(screen_region_raw)
    except cv2.error as e:
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(
                    f"Match {template_name}: Error equalizing screen region: {e}"
                )
        last_vals[template_name] = -1.0
        return None
    rh, rw = screen_region_equalized.shape[:2]
    scales_to_try = [0.9, 1.0, 1.1]
    overall_best_val: float = -1.0
    overall_best_loc: tuple[int, int] | None = None
    overall_best_sz: tuple[int, int] | None = None
    if not tmpl_obj.imgs:
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(f"Match {template_name}: No image variants loaded.")
        last_vals[template_name] = -1.0
        return None
    for var_idx, orig_tpl_img in enumerate(tmpl_obj.imgs):
        if orig_tpl_img is None:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        f"Match {template_name}, Var {var_idx}: Image None."
                    )
            continue
        for scale in scales_to_try:
            if len(orig_tpl_img.shape) < 2:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            f"Match {template_name}, Var {var_idx}: Invalid shape."
                        )
                continue
            th_o, tw_o = orig_tpl_img.shape[:2]
            tw_s = int(tw_o * scale)
            th_s = int(th_o * scale)
            if tw_s <= 0 or th_s <= 0 or th_s > rh or tw_s > rw:
                continue
            try:
                scl_tpl = cv2.resize(
                    orig_tpl_img, (tw_s, th_s), interpolation=cv2.INTER_AREA
                )
                scl_tpl_eq = cv2.equalizeHist(scl_tpl)
            except cv2.error as e:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            f"Match {template_name}, Var {var_idx}, Scale {scale}: Resize/Eq error: {e}"
                        )
                continue
            if scl_tpl_eq.shape[0] > rh or scl_tpl_eq.shape[1] > rw:
                continue
            try:
                res = cv2.matchTemplate(
                    screen_region_equalized, scl_tpl_eq, cv2.TM_CCOEFF_NORMED
                )
                _, max_v_cur, _, max_l_cur = cv2.minMaxLoc(res)
            except cv2.error as e:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            f"Match {template_name}, Var {var_idx}, Scale {scale}: matchTemplate error: {e}"
                        )
                continue
            if max_v_cur > overall_best_val:
                overall_best_val = max_v_cur
                overall_best_loc = max_l_cur
                overall_best_sz = (tw_s, th_s)
    last_vals[template_name] = overall_best_val
    if overall_best_val < tmpl_obj.thresh:
        return None
    last_pass[template_name] = overall_best_val
    if DEBUG_MATCH:
        with debug_log_lock:
            debug_log.append(f"-------------")
        with debug_log_lock:
            debug_log.append(f"Match {template_name}: PASSED.")
        with debug_log_lock:
            debug_log.append(
                f"  Score: {overall_best_val:.3f} >= {tmpl_obj.thresh:.3f}"
            )
        with debug_log_lock:
            debug_log.append(f"-------------")
    if overall_best_loc is None or overall_best_sz is None:
        return None
    cx_reg = overall_best_loc[0] + overall_best_sz[0] // 2
    cy_reg = overall_best_loc[1] + overall_best_sz[1] // 2
    f_cx = x_r + cx_reg
    f_cy = y_r + cy_reg
    return (f_cx, f_cy)


def run_batch_template_checks(
    screen_gray_to_check: np.ndarray, templates_to_check: dict[str, Tmpl]
) -> dict[str, tuple[int, int] | None]:
    results: dict[str, tuple[int, int] | None] = {}
    num_workers = min(max(1, os.cpu_count() or 1), len(templates_to_check))
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_template_name = {
            executor.submit(best_match, screen_gray_to_check, tmpl_obj): name
            for name, tmpl_obj in templates_to_check.items()
        }
        for future in future_to_template_name:
            template_name_for_future = future_to_template_name[future]
            try:
                results[template_name_for_future] = future.result()
            except Exception as exc:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            f"[Bot Parallel Check] {template_name_for_future} exc: {exc}"
                        )
                results[template_name_for_future] = None
    return results


PRIMARY_CHECK_TEMPLATES = [
    "winrate",
    "speech_menu",
    "confirm",
    "black_confirm",
    "black_confirm_v2",
    "selectable",
    "fusion_check",
    # "ego_check",
    "ego_get",
    "skip",
    "battle",
    "chain_battle",
    "enter",
]


def mouse_shake_monitor():
    """
    Runs in a separate thread to constantly monitor for mouse shakes.
    If enough shakes are detected, it triggers the pause event.
    The shake counter is reset when the bot is resumed or after 5 seconds of no shaking.
    """
    global LAST_MOUSE_POS, LAST_MOUSE_TIME, MOUSE_SHAKES_DETECTED, pause_event, DEBUG_MATCH, debug_log, LAST_SHAKE_TIME

    was_paused = pause_event.is_set()

    while True:
        try:
            is_currently_paused = pause_event.is_set()
            current_time = time.perf_counter()

            # Detect when the bot is resumed (i.e., state changes from paused to not-paused)
            if was_paused and not is_currently_paused:
                MOUSE_SHAKES_DETECTED = 0
                LAST_MOUSE_POS = None  # Forget the last position to prevent false detection on resume
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "Bot resumed. Mouse shake counter and position reset."
                        )

            # Update the state for the next iteration
            was_paused = is_currently_paused

            # Only check for shakes if the bot is not paused
            if not is_currently_paused:
                # Reset counter if x seconds have passed since the last shake
                if MOUSE_SHAKES_DETECTED > 0 and (
                    current_time - LAST_SHAKE_TIME > failsafe_timer
                ):
                    if DEBUG_MATCH:
                        with debug_log_lock:
                            debug_log.append(
                                "Shake Timeout. Mouse shake counter reset."
                            )
                    MOUSE_SHAKES_DETECTED = 0

                current_pos = pyautogui.position()

                if LAST_MOUSE_POS is None:
                    LAST_MOUSE_POS = (current_pos.x, current_pos.y)
                    LAST_MOUSE_TIME = current_time
                    time.sleep(0.05)
                    continue

                dist_moved = math.sqrt(
                    (current_pos.x - LAST_MOUSE_POS[0]) ** 2
                    + (current_pos.y - LAST_MOUSE_POS[1]) ** 2
                )

                if dist_moved > MOUSE_SHAKE_DISTANCE_THRESHOLD:
                    MOUSE_SHAKES_DETECTED += 1
                    LAST_SHAKE_TIME = current_time  # Update time of the last shake
                    if DEBUG_MATCH:
                        with debug_log_lock:
                            debug_log.append(
                                f"Mouse shake ({MOUSE_SHAKES_DETECTED}/{MOUSE_SHAKES_TO_PAUSE}). Dist:{dist_moved:.0f}px"
                            )

                if MOUSE_SHAKES_DETECTED >= MOUSE_SHAKES_TO_PAUSE:
                    if not pause_event.is_set():
                        pause_event.set()
                        log_msg = "BOT PAUSED BY MOUSE SHAKE!"
                        print(log_msg)
                        with debug_log_lock:
                            debug_log.append(log_msg)

                        tuner = get_tuner()
                        if tuner:
                            tuner.after(
                                0,
                                lambda: tuner.btn_pause.config(
                                    text="Resume Bot", bg="red"
                                ),
                            )

                    MOUSE_SHAKES_DETECTED = 0

                LAST_MOUSE_POS = (current_pos.x, current_pos.y)

            time.sleep(0.05)

        except Exception as e:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(f"Error in mouse shake monitor thread: {e}")
            time.sleep(1)


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
                with debug_log_lock:
                    debug_log.append("LimbusCompany window not active. Bot idling.")
            game_inactive_logged_once = True
            time.sleep(1)
            local_need_refresh = True
            continue
        if game_inactive_logged_once:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "LimbusCompany window now active. Resuming checks."
                    )
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
                    with debug_log_lock:
                        debug_log.append(
                            "Error: Failed to capture screen. Retrying soon."
                        )
                time.sleep(0.5)
                local_need_refresh = True
                continue
            local_screen_gray = screen_gray_new
            local_last_grab = now
            local_need_refresh = False
        if local_screen_gray is None:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "Error: Screen data is None before checks. Forcing refresh."
                    )
            local_need_refresh = True
            time.sleep(0.1)
            continue

        templates_for_current_batch = {
            name: TEMPLATES[name]
            for name in PRIMARY_CHECK_TEMPLATES
            if name in TEMPLATES
        }
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(
                    f"Starting batch check for {len(templates_for_current_batch)} templates..."
                )
        batch_start_time = time.perf_counter()
        match_results = run_batch_template_checks(
            local_screen_gray, templates_for_current_batch
        )
        batch_end_time = time.perf_counter()
        if DEBUG_MATCH:
            with debug_log_lock:
                debug_log.append(
                    f"Batch check completed in {batch_end_time-batch_start_time:.4f} seconds."
                )

        if match_results.get("winrate"):
            if DEBUG_MATCH:
                with debug_log_lock:
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

        if text_skip and match_results.get("speech_menu"):
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append("[Bot Check [2-A] - SpeechMenu] Action triggered.")
            click(match_results["speech_menu"], hold_ms=10)
            time.sleep(0.5)
            local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                local_need_refresh = True
                continue
            fast_forward_pt = best_match(local_screen_gray, TEMPLATES["fast_forward"])
            if fast_forward_pt:
                if DEBUG_MATCH:
                    with debug_log_lock:
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
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Check [2-B] FAILED] FastForward (within SpeechMenu) not found."
                    )
            selectable_for_skip_pt = best_match(
                local_screen_gray, TEMPLATES["selectable"]
            )
            if not selectable_for_skip_pt:
                confirm_speech_pt = best_match(local_screen_gray, TEMPLATES["confirm"])
                if confirm_speech_pt:
                    if DEBUG_MATCH:
                        with debug_log_lock:
                            debug_log.append(
                                "[Bot Check [2-C] - Confirm (Speech)] Action triggered."
                            )
                    click(confirm_speech_pt, hold_ms=10)
                elif DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [2-C] FAILED] Confirm (Speech) not found."
                        )
            local_need_refresh = True
            continue

        # [3] Overlay Logic
        choice_overlay_pt = match_results.get("selectable")
        fusion_overlay_pt = match_results.get("fusion_check")
        # ego_overlay_pt = match_results.get("ego_check")
        ego_get_overlay_pt = match_results.get("ego_get")

        # is_ego_block_active = ego_overlay_pt and not ego_get_overlay_pt
        action_taken_in_overlay_block = False

        if not full_auto_mirror:
            # HIGHEST PRIORITY: EGO Get screen sequence
            if ego_get_overlay_pt:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [3-A] - EGO Gift Received] Action triggered."
                        )
                # (a) Press enter to dismiss initial screen
                keyboard.press_and_release("enter")
                time.sleep(0.5)  # Wait for UI to react

                # (b) After pressing enter, check for confirm buttons and click if found
                local_screen_gray = refresh_screen()
                time.sleep(0.3)  # Wait a bit more to ensure UI has updated
                if local_screen_gray is not None:
                    confirm_pt = best_match(local_screen_gray, TEMPLATES["confirm"])
                    black_confirm_pt = best_match(
                        local_screen_gray, TEMPLATES["black_confirm"]
                    )
                    black_confirm_v2_pt = best_match(
                        local_screen_gray, TEMPLATES["black_confirm_v2"]
                    )
                    time.sleep(0.2)  # Short pause before clicking

                    confirm_pt_after_ego = (
                        confirm_pt or black_confirm_pt or black_confirm_v2_pt
                    )

                    if confirm_pt_after_ego:
                        if DEBUG_MATCH:
                            with debug_log_lock:
                                debug_log.append(
                                    "[Bot Check [3-B] - Confirm (after EGO Get)] Action triggered."
                                )
                        click(confirm_pt_after_ego, hold_ms=10)
                        time.sleep(0.2)  # Give time for confirm to process

                local_need_refresh = True  # Screen has definitely changed
                continue  # Restart main loop after this entire sequence

            # If EGO Get was not found, check for other "waiting" overlays
            elif choice_overlay_pt:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append("[Bot Check [3-C] - Choice Needed] Waiting...")
                action_taken_in_overlay_block = True
            elif fusion_overlay_pt:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append("[Bot Check [3-D] - Fusion Check] Waiting...")
                action_taken_in_overlay_block = True
            # elif is_ego_block_active:
            # if DEBUG_MATCH:
            #     with debug_log_lock:
            #         debug_log.append("[Bot Check [3-E] - EGO Select (Pending)] Waiting...")
            #     action_taken_in_overlay_block = True

            if action_taken_in_overlay_block:
                time.sleep(CHECK_INTERVAL * 2)
                local_need_refresh = True
                continue

        # General Confirm button check (if no overlay logic above was triggered)
        confirm_button_to_click = (
            match_results.get("black_confirm")
            or match_results.get("black_confirm_v2")
            or match_results.get("confirm")
        )
        if confirm_button_to_click:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Check [3-F] - General Confirm Button] Action triggered."
                    )
            click(confirm_button_to_click, hold_ms=10)
            time.sleep(CHECK_INTERVAL * 2)
            local_need_refresh = True
            continue

        if match_results.get("skip"):
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Check [4-A] - Skip (Abno Start)] Action triggered."
                    )
            click(match_results["skip"], hold_ms=10)
            time.sleep(0.2)
            h_s, w_s = local_screen_gray.shape
            pyautogui.moveTo(w_s // 2, int(h_s * 0.10))
            local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                local_need_refresh = True
                continue
            continue_abno_pt = best_match(local_screen_gray, TEMPLATES["continue"])
            if continue_abno_pt:
                if DEBUG_MATCH:
                    with debug_log_lock:
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
                        with debug_log_lock:
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
                        with debug_log_lock:
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
                    with debug_log_lock:
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

        battle_action_pt = match_results.get("battle") or match_results.get(
            "chain_battle"
        )
        if battle_action_pt:
            action_name = "To Battle" if match_results.get("battle") else "Chain Battle"
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        f"[Bot Check [5] - {action_name}] Action triggered."
                    )
            click(battle_action_pt, hold_ms=10)
            time.sleep(1.0)
            local_need_refresh = True
            continue

        if match_results.get("enter"):
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Check [6] - Enter Encounter] Action triggered."
                    )
            click(match_results["enter"])
            pyautogui.moveTo(100, 100)  # Move mouse to avoid blocking new screen
            time.sleep(0.5)
            local_need_refresh = True
            continue

        if DEBUG_MATCH:
            made_primary_action = (
                any(
                    match_results.get(name)
                    for name in [
                        "winrate",
                        "speech_menu",
                        "black_confirm",
                        "black_confirm_v2",
                        "confirm",
                        "skip",
                        "battle",
                        "chain_battle",
                        "enter",
                    ]
                )
                or action_taken_in_overlay_block
            )
            if not made_primary_action and not (lux_thread or lux_EXP):
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Batch] No high-priority actions from primary checks this cycle."
                    )
        if lux_thread:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append("[Bot Mode Start - Thread Luxcavation]")
            if local_need_refresh:
                local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            drive_pt = best_match(local_screen_gray, TEMPLATES["drive"])
            if drive_pt:
                click(drive_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [A-1] FAILED] Drive (Thread Lux) not found."
                        )
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            lux_menu_pt = best_match(local_screen_gray, TEMPLATES["luxcavations"])
            if lux_menu_pt:
                click(lux_menu_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [A-2] FAILED] Luxcavations Menu (Thread Lux) not found."
                        )
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread_config(False)
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
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [A-3] FAILED] Select Thread Lux not found."
                        )
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            lux_enter_pt = best_match(local_screen_gray, TEMPLATES["lux_enter"])
            if lux_enter_pt:
                click(lux_enter_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [A-4] FAILED] Lux Enter (Thread Lux) not found."
                        )
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread_config(False)
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
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [A-5] FAILED] Thread Lux Battle Node not found."
                        )
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            to_battle_lux_pt = best_match(local_screen_gray, TEMPLATES["battle"])
            if to_battle_lux_pt:
                click(to_battle_lux_pt, hold_ms=10)
                time.sleep(2.0)
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [A-6] FAILED] To Battle (Thread Lux) not found."
                        )
                set_lux_thread_config(False)
                local_need_refresh = True
                continue
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Mode End - Thread Luxcavation] Sequence complete."
                    )
            set_lux_thread_config(False)
            local_need_refresh = True
            continue
        if lux_EXP:
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append("[Bot Mode Start - EXP Luxcavation]")
            if local_need_refresh:
                local_screen_gray = refresh_screen()
            if local_screen_gray is None:
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            drive_pt_exp = best_match(local_screen_gray, TEMPLATES["drive"])
            if drive_pt_exp:
                click(drive_pt_exp, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [B-1] FAILED] Drive (EXP Lux) not found."
                        )
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            lux_menu_pt_exp = best_match(local_screen_gray, TEMPLATES["luxcavations"])
            if lux_menu_pt_exp:
                click(lux_menu_pt_exp, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [B-2] FAILED] Luxcavations Menu (EXP Lux) not found."
                        )
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            select_exp_pt = best_match(local_screen_gray, TEMPLATES["select_exp_lux"])
            if select_exp_pt:
                click(select_exp_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [B-3] FAILED] Select EXP Lux not found."
                        )
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            exp_enter_pt = best_match(local_screen_gray, TEMPLATES["exp_lux_enter"])
            if exp_enter_pt:
                click(exp_enter_pt, hold_ms=10)
                time.sleep(1.0)
                local_screen_gray = refresh_screen()
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [B-4] FAILED] EXP Lux Enter not found."
                        )
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            if local_screen_gray is None:
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            to_battle_exp_lux_pt = best_match(local_screen_gray, TEMPLATES["battle"])
            if to_battle_exp_lux_pt:
                click(to_battle_exp_lux_pt, hold_ms=10)
                time.sleep(2.0)
            else:
                if DEBUG_MATCH:
                    with debug_log_lock:
                        debug_log.append(
                            "[Bot Check [B-5] FAILED] To Battle (EXP Lux) not found."
                        )
                set_lux_exp_config(False)
                local_need_refresh = True
                continue
            if DEBUG_MATCH:
                with debug_log_lock:
                    debug_log.append(
                        "[Bot Mode End - EXP Luxcavation] Sequence complete."
                    )
            set_lux_exp_config(False)
            local_need_refresh = True
            continue
        time.sleep(CHECK_INTERVAL)


# ──────────────────────── Supervisor / hotkey wrapper ──────────────────
def main():
    # --- SET CUSTOM EXCEPTION HOOK AT THE VERY BEGINNING OF MAIN ---
    sys.excepthook = handle_exception

    # --- Initialize PyAutoGUI Settings AFTER checking it's not None ---
    if pyautogui is None:
        critical_error_msg = (
            "CRITICAL: PyAutoGUI module could not be loaded. Bot cannot function."
        )
        print(critical_error_msg, file=sys.stderr)
        # Try to log this critical startup failure
        try:
            handle_exception(RuntimeError, RuntimeError(critical_error_msg), None)
        except:
            pass  # Avoid crashing the crash handler itself
        sys.exit(1)  # Exit: pyautogui is essential

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    global TEMPLATES, delay_ms, CHECK_INTERVAL, APPLICATION_BASE_PATH
    # APPLICATION_BASE_PATH is already defined at module level after get_application_path
    TEMPLATES = load_templates()
    if not TEMPLATES:
        critical_error_msg = (
            "CRITICAL: No templates loaded. Bot cannot function. Exiting."
        )
        print(critical_error_msg, file=sys.stderr)
        with debug_log_lock:
            debug_log.append(critical_error_msg)
        try:
            handle_exception(RuntimeError, RuntimeError(critical_error_msg), None)
        except:
            pass
        return

    # Use APPLICATION_BASE_PATH for the config file
    config_file_name = "saved_user_vars.json"

    # If running as PyInstaller bundle, check _internal folder for config
    if getattr(sys, "frozen", False):
        # Try _internal folder first (PyInstaller --add-data puts files here)
        internal_config_path = os.path.join(
            APPLICATION_BASE_PATH, "_internal", config_file_name
        )
        if os.path.isfile(internal_config_path):
            config_path = internal_config_path
        else:
            config_path = os.path.join(APPLICATION_BASE_PATH, config_file_name)
    else:
        config_path = os.path.join(APPLICATION_BASE_PATH, config_file_name)

    with debug_log_lock:
        debug_log.append(
            f"Attempting to load config from: {config_path}"
        )  # Log attempt path

    if os.path.isfile(config_path):
        try:
            with open(config_path, encoding="utf-8") as fp: 
                saved_config = json.load(fp)
            general_settings = saved_config.get("general_settings", {})
            loaded_delay_ms = general_settings.get("delay_ms")
            if isinstance(loaded_delay_ms, int):
                delay_ms = max(10, loaded_delay_ms) 
                CHECK_INTERVAL = delay_ms / 1000.0
                with debug_log_lock:
                    debug_log.append(f"Loaded delay_ms: {delay_ms} from config.")
            template_settings = saved_config.get("templates", {}) 
            if not template_settings and "winrate" in saved_config: 
                template_settings = saved_config 
            for name, vals in template_settings.items():
                if name in TEMPLATE_SPEC: 
                    base_cfg, _, _ = TEMPLATE_SPEC[name] 
                    new_thresh = vals.get("threshold", TEMPLATE_SPEC[name][1])
                    new_roi_list = vals.get("roi")
                    new_roi = tuple(new_roi_list) if isinstance(new_roi_list, list) else TEMPLATE_SPEC[name][2]
                    TEMPLATE_SPEC[name] = (base_cfg, new_thresh, new_roi)
            _refresh_templates_from_gui() 
            with debug_log_lock:
                debug_log.append(f"Loaded template settings from {config_path}")
        except Exception as e: 
            with debug_log_lock:
                debug_log.append(
                    f"Error loading {config_path}: {e}. Using default specs."
                )
            print(f"Error loading config: {e}", file=sys.stderr) 
    else: 
        with debug_log_lock:
            debug_log.append(f"{config_path} not found. Using default template specs.")

    # --- ADD A LINE HERE TO TEST CRASH LOGGING ---
    # To test, uncomment the line below, run the script (or compiled .exe).
    # It should crash, and a log file should appear in a 'crash_logs' directory.
    # Make sure to re-comment it after testing!
    # raise RuntimeError("This is a deliberate test crash to verify logging.") # <--- TEST CRASH LINE

    if launch_gui and get_tuner:
        print("Launching GUI...")
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
            failsafe_timer=failsafe_timer,
        )
    else:
        # If GUI cannot be launched (because launch_gui or get_tuner is None due to import failure),
        # print an error and exit. This enforces the "no headless" requirement.
        error_message = (
            "CRITICAL ERROR: GUI could not be launched. Bot requires GUI to run."
        )
        print(error_message, file=sys.stderr)
        with debug_log_lock:
            debug_log.append(error_message)
        if "handle_exception" in globals() and callable(handle_exception):
            try:
                handle_exception(RuntimeError, RuntimeError("GUI launch failed."), None)
            except Exception as he_e:
                print(
                    f"Error trying to use custom exception handler for GUI launch failure: {he_e}",
                    file=sys.stderr,
                )
        sys.exit(1)  # Exit with a non-zero status code

    # --- Start the mouse shake monitor in a separate daemon thread ---
    shake_monitor_thread = threading.Thread(target=mouse_shake_monitor, daemon=True)
    shake_monitor_thread.start()

    # --- Hotkey Definitions (ensure correct method names from GUI if interacting) ---
    def _on_pause_hotkey():
        tuner = get_tuner()
        if tuner and hasattr(tuner, "_toggle_bot_pause_state"):
            tuner.after(0, tuner._toggle_bot_pause_state)
        else:  # This fallback might not be hit if GUI is mandatory
            if pause_event.is_set():
                pause_event.clear()
                with debug_log_lock:
                    debug_log.append("Bot resumed via hotkey.")
            else:
                pause_event.set()
                with debug_log_lock:
                    debug_log.append("Bot paused via hotkey.")

    try:
        keyboard.add_hotkey(
            "ctrl+shift+d", _on_pause_hotkey, suppress=True, trigger_on_release=True
        )
    except Exception as e:
        print(f"Warning: Could not register pause hotkey (ctrl+shift+d): {e}")

    def _create_mode_toggle_hotkey_cb(
        setter_func, current_value_lambda, tuner_method_name_str
    ):
        def _callback_action():
            tuner = get_tuner()
            if tuner and hasattr(tuner, tuner_method_name_str):
                getattr(tuner, tuner_method_name_str)()
            else:  # Fallback if no GUI (though script might exit earlier if GUI is mandatory)
                setter_func(not current_value_lambda())

        return _callback_action

    try:
        keyboard.add_hotkey(
            "ctrl+shift+t",
            _create_mode_toggle_hotkey_cb(
                set_lux_thread_config, lambda: lux_thread, "_toggle_thread_lux_mode"
            ),
            suppress=True,
            trigger_on_release=True,
        )
    except Exception as e:
        print(f"Warning: Could not register Thread Lux hotkey (ctrl+shift+t): {e}")
    try:
        keyboard.add_hotkey(
            "ctrl+shift+e",
            _create_mode_toggle_hotkey_cb(
                set_lux_exp_config, lambda: lux_EXP, "_toggle_exp_lux_mode"
            ),
            suppress=True,
            trigger_on_release=True,
        )
    except Exception as e:
        print(f"Warning: Could not register EXP Lux hotkey (ctrl+shift+e): {e}")
    try:
        keyboard.add_hotkey(
            "ctrl+shift+m",
            _create_mode_toggle_hotkey_cb(
                set_full_auto_mirror_config,
                lambda: full_auto_mirror,
                "_toggle_mirror_full_auto_mode",
            ),
            suppress=True,
            trigger_on_release=True,
        )
    except Exception as e:
        print(f"Warning: Could not register Mirror hotkey (ctrl+shift+m): {e}")

    try:
        keyboard.add_hotkey(
            "ctrl+alt+d", lambda: os._exit(0), suppress=True, trigger_on_release=False
        )
    except Exception as e:
        print(f"Warning: Could not register quit hotkey (ctrl+alt+d): {e}")

    # Move the one-time messages here
    print(
        "Limbus bot initialized (Multithreaded Core). Press Ctrl+Alt+D to force quit."
    )
    print("Mouse shake detection is active. Shake mouse rapidly to pause.")
    with debug_log_lock:
        debug_log.append(
            "Limbus bot initialized (Multithreaded Core). Press Ctrl+Shift+D to pause/resume."
        )
        debug_log.append(
            "Mouse shake detection is active. Shake mouse rapidly to pause."
        )

    if DEBUG_MATCH:
        print("Debug logs will print to console if no GUI, or in GUI log panel.")

    try:
        limbus_bot()
    except KeyboardInterrupt:
        with debug_log_lock:
            ("Bot terminated by user (KeyboardInterrupt).")
        print("\nBot terminated by user.")
    finally:
        debug_log.append("Bot shutting down.")
        print("Bot shutting down.")
        os._exit(0)


if __name__ == "__main__":
    main()
