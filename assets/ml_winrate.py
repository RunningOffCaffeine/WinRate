#!/usr/bin/env python3
"""
Auto-pilot for Limbus Company battles (Machine Learning Core Version with GUI).
Includes runtime crash logging and robust import handling.
"""
# ── std-lib imports ───────────────────────────────────────────────────
import os
import threading
import time
import sys
import json
import math
import traceback
from datetime import datetime
from collections import deque

# ── auto-installer for third-party packages ───────────────────────────
def _require(pkg, import_as=None, pypi_name=None):
    """Imports a package, installing it if not found."""
    import importlib, subprocess
    name_to_install = pypi_name or pkg
    module_name_to_import = import_as if import_as else pkg
    try:
        return importlib.import_module(module_name_to_import)
    except ModuleNotFoundError:
        print(f"[setup] '{module_name_to_import}' not found. Attempting to install '{name_to_install}'…")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", name_to_install])
            return importlib.import_module(module_name_to_import)
        except (subprocess.CalledProcessError, ModuleNotFoundError) as e:
            print(f"ERROR: Failed to install or import '{name_to_install}'. Please install it manually.", file=sys.stderr)
            sys.exit(f"Critical dependency failure: {e}")

# --- Conditional Imports ---
if getattr(sys, 'frozen', False):
    print("INFO: Running as a PyInstaller frozen executable.")
    import cv2
    import numpy as np
    import pyautogui
    import keyboard
    import pygetwindow as gw
    import mss
    from PIL import Image
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    import tensorflow as tf
else:
    print("INFO: Running as a Python script.")
    cv2       = _require("cv2", pypi_name="opencv-python")
    np        = _require("numpy")
    pyautogui = _require("pyautogui")
    keyboard  = _require("keyboard")
    gw        = _require("pygetwindow")
    mss       = _require("mss")
    tf        = _require("tensorflow")
    _require("PIL", pypi_name="Pillow")
    from PIL import Image

# --- GUI Import ---
try:
    from ml_gui_config import launch_gui, get_tuner
except ImportError:
    print("CRITICAL ERROR: ml_gui_config.py not found. Ensure it is inside the 'ml_tools' folder.", file=sys.stderr)
    sys.exit(1)


# --- Global Variables & Configuration ---
pause_event = threading.Event()
delay_ms = 100
CHECK_INTERVAL = delay_ms / 1000.0
debug_flag = True
text_skip = False
debug_log = deque(maxlen=200)
debug_log_lock = threading.Lock()

# Mouse Shake Failsafe
LAST_MOUSE_POS: tuple[int, int] | None = None
MOUSE_SHAKE_DISTANCE_THRESHOLD: float = 200.0
MOUSE_SHAKES_DETECTED: int = 0
MOUSE_SHAKES_TO_PAUSE: int = 5
LAST_SHAKE_TIME: float = 0.0

# ML Model Objects
MODEL = None
LABEL_MAP = None
CONFIDENCE_THRESHOLD = 0.9850
IMG_SIZE = 128
latest_ml_predictions = []

# Debug Visualization
debug_frame = None
DEBUG_WINDOW_ENABLED = False

# Monitor configuration
MON_X, MON_Y, MON_W, MON_H = 0, 0, 0, 0

# --- Path & Crash Handling ---
def resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller. """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)

APPLICATION_BASE_PATH = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def handle_exception(exc_type, exc_value, exc_traceback):
    """Custom exception hook to log unhandled exceptions to a file."""
    log_dir = os.path.join(APPLICATION_BASE_PATH, "crash_logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"crash_report_{timestamp}.log")

    with debug_log_lock:
        recent_logs = "\n".join(list(debug_log))
    
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    full_report = (
        f"--- CRASH REPORT ---\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Exception: {exc_type.__name__}: {exc_value}\n"
        f"--- Traceback ---\n{tb_str}"
        f"\n--- Recent Debug Log ---\n{recent_logs}\n---------------------\n"
    )
    
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(full_report)
        print(f"CRITICAL ERROR: Unhandled exception. Crash report saved to: {log_file}", file=sys.stderr)
    except Exception as e:
        print(f"CRITICAL: Could not write crash report. Error: {e}", file=sys.stderr)
        print(full_report, file=sys.stderr)
    
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# --- Config Setters for GUI ---
def set_confidence_threshold_config(threshold: float):
    """Callback function for the GUI to update the confidence threshold."""
    global CONFIDENCE_THRESHOLD
    CONFIDENCE_THRESHOLD = threshold
    with debug_log_lock:
        debug_log.append(f"Confidence threshold set to {CONFIDENCE_THRESHOLD:.4f}")

def set_debug_mode_config(state: bool):
    """Callback to enable/disable debug mode and the visual debug window."""
    global debug_flag, DEBUG_WINDOW_ENABLED
    debug_flag = state
    DEBUG_WINDOW_ENABLED = state
    with debug_log_lock:
        debug_log.append(f"Debug mode {'enabled' if state else 'disabled'}.")

# --- Core Bot & ML Functions ---
def load_ml_model():
    """Loads the trained Keras model and label map."""
    global MODEL, LABEL_MAP
    try:
        model_path = resource_path('ml_tools/models/limbus_classifier.keras')
        label_map_path = resource_path('ml_tools/models/label_map.json')

        if not os.path.exists(model_path) or not os.path.exists(label_map_path):
             with debug_log_lock:
                debug_log.append("ML model or label map not found in ml_tools/models/.")
             return False

        MODEL = tf.keras.models.load_model(model_path)
        with open(label_map_path, 'r') as f:
            LABEL_MAP = {int(k): v for k, v in json.load(f).items()}
        
        with debug_log_lock:
            debug_log.append(f"ML model loaded successfully. Classes: {list(LABEL_MAP.values())}")
        return True

    except Exception as e:
        with debug_log_lock:
            debug_log.append(f"Error loading ML model: {e}")
        return False

def get_contours_from_screen(screen_gray):
    """Finds potential button-like contours on the screen."""
    thresh = cv2.adaptiveThreshold(screen_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    potential_buttons = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if 50 < w < 400 and 20 < h < 150 and (0.2 < w/h < 5.0):
             potential_buttons.append((x, y, w, h))
    return potential_buttons

def predict_buttons(screen_full_color, potential_buttons):
    """Takes screen and button locations, returns predictions for each."""
    global latest_ml_predictions
    
    if MODEL is None or not potential_buttons:
        latest_ml_predictions = []
        return {}, []

    batch_images = []
    for (x, y, w, h) in potential_buttons:
        roi = screen_full_color[y:y+h, x:x+w]
        resized_roi = cv2.resize(roi, (IMG_SIZE, IMG_SIZE))
        preprocessed_roi = resized_roi.astype('float32') / 255.0
        batch_images.append(preprocessed_roi)
    
    if not batch_images:
        latest_ml_predictions = []
        return {}, []

    predictions = MODEL.predict(np.array(batch_images), verbose=0)
    
    high_confidence_results = {}
    all_predictions_for_debug = []
    gui_predictions = []
    num_classes = len(LABEL_MAP)

    for i, pred in enumerate(predictions):
        if num_classes == 2:
            confidence = pred[0] if pred[0] > 0.5 else 1 - pred[0]
            class_id = int(pred[0] > 0.5)
        else:
            confidence = np.max(pred)
            class_id = np.argmax(pred)

        label = LABEL_MAP.get(class_id, "Unknown")
        box_coords = potential_buttons[i]
        
        all_predictions_for_debug.append((box_coords, label, confidence))
        gui_predictions.append(f"{label}: {confidence:.4f}")

        if confidence > CONFIDENCE_THRESHOLD:
            if label not in high_confidence_results or confidence > high_confidence_results[label][1]:
                x, y, w, h = box_coords
                center_pt = (x + w // 2, y + h // 2)
                high_confidence_results[label] = (center_pt, confidence)

    latest_ml_predictions = sorted(gui_predictions)
    return high_confidence_results, all_predictions_for_debug

def active_window_title() -> str:
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""

def refresh_screen_ml(grabber, monitor_info) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Captures the screen and returns both grayscale and color versions."""
    try:
        sct_img = grabber.grab(monitor_info)
        img_bgr = np.array(sct_img)[:, :, :3]
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        return img_gray, img_rgb
    except Exception as e:
        with debug_log_lock:
            debug_log.append(f"Screen Grab Error: {e}")
        return None, None

def click(pt: tuple[int, int] | None, hold_ms: int = 0):
    if pt is None: return
    try:
        absolute_x = MON_X + pt[0]
        absolute_y = MON_Y + pt[1]
        pyautogui.moveTo(absolute_x, absolute_y, duration=0.1)
        pyautogui.mouseDown()
        if hold_ms > 0:
            time.sleep(hold_ms / 1000.0)
        pyautogui.mouseUp()
        with debug_log_lock:
            debug_log.append(f"Clicked at ({pt[0]}, {pt[1]})")
    except Exception as e:
        with debug_log_lock:
            debug_log.append(f"Click Error: {e} at {pt}")

def mouse_shake_monitor():
    """Monitors for rapid mouse movement to pause the bot."""
    global LAST_MOUSE_POS, MOUSE_SHAKES_DETECTED, LAST_SHAKE_TIME, pause_event
    
    was_paused = pause_event.is_set()
    while True:
        try:
            is_currently_paused = pause_event.is_set()
            current_time = time.time()
            if was_paused and not is_currently_paused:
                MOUSE_SHAKES_DETECTED = 0
                LAST_MOUSE_POS = None
                with debug_log_lock:
                    debug_log.append("Bot resumed. Mouse shake counter and position reset.")
            was_paused = is_currently_paused
            if not is_currently_paused:
                if MOUSE_SHAKES_DETECTED > 0 and (current_time - LAST_SHAKE_TIME > 5):
                    with debug_log_lock:
                        debug_log.append("5-second timeout. Mouse shake counter reset.")
                    MOUSE_SHAKES_DETECTED = 0
                current_pos = pyautogui.position()
                if LAST_MOUSE_POS is not None:
                    dist_moved = math.sqrt(
                        (current_pos.x - LAST_MOUSE_POS[0])**2 + (current_pos.y - LAST_MOUSE_POS[1])**2
                    )
                    if dist_moved > MOUSE_SHAKE_DISTANCE_THRESHOLD:
                        MOUSE_SHAKES_DETECTED += 1
                        LAST_SHAKE_TIME = current_time
                        with debug_log_lock:
                            debug_log.append(f"Mouse shake ({MOUSE_SHAKES_DETECTED}/{MOUSE_SHAKES_TO_PAUSE}).")
                    if MOUSE_SHAKES_DETECTED >= MOUSE_SHAKES_TO_PAUSE:
                        if not pause_event.is_set():
                            pause_event.set()
                            log_msg = "BOT PAUSED BY MOUSE SHAKE!"
                            print(log_msg)
                            with debug_log_lock:
                                debug_log.append(log_msg)
                            tuner = get_tuner()
                            if tuner:
                                tuner.after(0, lambda: tuner.btn_pause.config(text="Resume Bot", bg="red"))
                        MOUSE_SHAKES_DETECTED = 0
                LAST_MOUSE_POS = (current_pos.x, current_pos.y)
            time.sleep(0.05)
        except Exception as e:
            with debug_log_lock:
                debug_log.append(f"Error in mouse shake monitor: {e}")
            time.sleep(1)

def show_debug_window():
    """Displays the debug frame in an OpenCV window if enabled."""
    global debug_frame
    while True:
        if DEBUG_WINDOW_ENABLED and debug_frame is not None:
            try:
                cv2.imshow("Limbus Bot - Live View", debug_frame)
                if cv2.waitKey(50) & 0xFF == 27: # Allow closing with ESC
                    cv2.destroyWindow("Limbus Bot - Live View")
            except Exception:
                # This can happen if the frame is being written to while being read
                pass 
        else:
            # If the window should be closed
            try:
                cv2.destroyWindow("Limbus Bot - Live View")
            except cv2.error:
                # Window was already closed, which is fine
                pass
        time.sleep(0.05)


def limbus_bot():
    """Main bot logic loop."""
    global debug_frame
    local_last_grab = 0.0
    game_inactive_logged_once = False
    
    with mss.mss() as grabber:
        try:
            monitor_info = grabber.monitors[1]
        except IndexError:
            monitor_info = grabber.monitors[0]

        while True:
            if pause_event.is_set():
                time.sleep(0.1)
                continue
            if "LimbusCompany" not in active_window_title():
                if not game_inactive_logged_once:
                    with debug_log_lock:
                        debug_log.append("LimbusCompany window not active. Bot idling.")
                    game_inactive_logged_once = True
                time.sleep(1)
                continue
            if game_inactive_logged_once:
                with debug_log_lock:
                    debug_log.append("LimbusCompany window now active. Resuming checks.")
                game_inactive_logged_once = False

            now = time.time()
            if (now - local_last_grab) < CHECK_INTERVAL:
                time.sleep(max(0, CHECK_INTERVAL - (now - local_last_grab)))
            
            screen_gray, screen_color = refresh_screen_ml(grabber, monitor_info)
            local_last_grab = time.time()
            
            if screen_gray is None or screen_color is None:
                with debug_log_lock:
                    debug_log.append("Failed to capture screen.")
                time.sleep(0.5)
                continue
                
            contours = get_contours_from_screen(screen_gray)
            predictions, all_detections = predict_buttons(screen_color, contours)

            if DEBUG_WINDOW_ENABLED:
                frame_for_display = cv2.cvtColor(screen_color, cv2.COLOR_RGB2BGR)
                for (x,y,w,h), label, confidence in all_detections:
                    color = (0, 255, 0) if confidence > CONFIDENCE_THRESHOLD else (0, 0, 255)
                    cv2.rectangle(frame_for_display, (x, y), (x+w, y+h), color, 2)
                    text = f"{label}: {confidence:.4f}"
                    cv2.putText(frame_for_display, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                debug_frame = frame_for_display


            action_taken = False
            priority_order = ["winrate", "confirm", "battle", "skip"]

            if "winrate" in predictions:
                point, confidence = predictions["winrate"]
                with debug_log_lock:
                    debug_log.append(f"Action: Found 'winrate' with {confidence:.4f} confidence. Clicking.")
                click(point)
                keyboard.press_and_release("p")
                time.sleep(0.1)
                keyboard.press_and_release("enter")
                action_taken = True
            else:
                for label in priority_order:
                    if label in predictions:
                        point, confidence = predictions[label]
                        with debug_log_lock:
                            debug_log.append(f"Action: Found '{label}' with {confidence:.4f} confidence. Clicking.")
                        click(point)
                        action_taken = True
                        break 
            
            if action_taken:
                time.sleep(1.0)
            elif debug_flag and predictions:
                 with debug_log_lock:
                    debug_log.append(f"Saw {list(predictions.keys())} but no priority action.")

def main():
    sys.excepthook = handle_exception
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    global MON_X, MON_Y, MON_W, MON_H, MOUSE_SHAKE_DISTANCE_THRESHOLD
    
    with mss.mss() as sct:
        try:
            primary_monitor_info = sct.monitors[1]
        except IndexError:
            primary_monitor_info = sct.monitors[0]
            
    MON_X, MON_Y = primary_monitor_info["left"], primary_monitor_info["top"]
    MON_W, MON_H = primary_monitor_info["width"], primary_monitor_info["height"]

    BASE_RES_DIAG = math.sqrt(1920**2 + 1080**2)
    current_res_diag = math.sqrt(MON_W**2 + MON_H**2)
    scaling_factor = current_res_diag / BASE_RES_DIAG
    MOUSE_SHAKE_DISTANCE_THRESHOLD *= scaling_factor
    
    print(f"Screen resolution {MON_W}x{MON_H}. Shake threshold scaled to {int(MOUSE_SHAKE_DISTANCE_THRESHOLD)}px.")

    if not load_ml_model():
        print("CRITICAL: Failed to load ML model. Bot cannot function.", file=sys.stderr)
        try:
            raise RuntimeError("CRITICAL: ML model files not found. Ensure training was successful.")
        except RuntimeError:
            handle_exception(*sys.exc_info())
        sys.exit(1)
        
    print("Launching GUI...")
    launch_gui(
        pause_event_shared=pause_event,
        initial_delay_ms=delay_ms,
        initial_debug_state=debug_flag,
        initial_text_skip_state=text_skip,
        initial_confidence=CONFIDENCE_THRESHOLD,
        set_delay_ms_cb=lambda ms: globals().update(delay_ms=ms, CHECK_INTERVAL=ms/1000.0),
        set_debug_mode_cb=set_debug_mode_config, # Use the new callback
        set_text_skip_cb=lambda state: globals().update(text_skip=state),
        set_confidence_cb=set_confidence_threshold_config,
        get_debug_log_fn=lambda: list(debug_log),
        get_model_predictions_fn=lambda: latest_ml_predictions
    )
    
    shake_thread = threading.Thread(target=mouse_shake_monitor, daemon=True)
    shake_thread.start()
    
    debug_view_thread = threading.Thread(target=show_debug_window, daemon=True)
    debug_view_thread.start()

    print("Limbus ML bot initialized. Press Ctrl+Alt+D to force quit.")
    print("Mouse shake detection is active. Shake mouse rapidly to pause.")
    with debug_log_lock:
        debug_log.append("Limbus ML bot initialized.")
        debug_log.append("Mouse shake detection is active.")

    try:
        limbus_bot_thread = threading.Thread(target=limbus_bot, daemon=True)
        limbus_bot_thread.start()
        while limbus_bot_thread.is_alive():
            limbus_bot_thread.join(timeout=0.5)
            
    except KeyboardInterrupt:
        print("\nBot terminated by user.")
    finally:
        print("Bot shutting down.")
        os._exit(0)

if __name__ == "__main__":
    main()

