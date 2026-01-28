# ml_winrate.py
# ... (Standard imports same as before) ...
import os, threading, time, sys, json, math, traceback
from datetime import datetime
from collections import deque


def _require(pkg, import_as=None, pypi_name=None):
    import importlib, subprocess
    try:
        return importlib.import_module(import_as or pkg)
    except:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pypi_name or pkg]
        )
        return importlib.import_module(import_as or pkg)


if getattr(sys, 'frozen', False):
    import cv2, numpy as np, pyautogui, keyboard, pygetwindow as gw, mss, tensorflow as tf
    from PIL import Image
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
else:
    cv2 = _require("cv2", pypi_name="opencv-python")
    np = _require("numpy")
    pyautogui = _require("pyautogui")
    keyboard = _require("keyboard")
    gw = _require("pygetwindow")
    mss = _require("mss")
    tf = _require("tensorflow")
    _require("PIL", pypi_name="Pillow")
    from PIL import Image

try:
    from ml_gui_config import launch_gui, get_tuner
except ImportError:
    sys.exit("CRITICAL: ml_gui_config.py not found.")

pause_event = threading.Event()
delay_ms = 100
CHECK_INTERVAL = 0.1
debug_flag = True
text_skip = False
debug_log = deque(maxlen=200)
debug_log_lock = threading.Lock()

LAST_MOUSE_POS = None
MOUSE_SHAKE_DISTANCE_THRESHOLD = 200.0
MOUSE_SHAKES_DETECTED = 0
MOUSE_SHAKES_TO_PAUSE = 5
LAST_SHAKE_TIME = 0.0
FAILSAFE_TIMER = 5.0

MODEL = None
LABEL_MAP = None
CONFIDENCE_THRESHOLD = 0.9850
IMG_SIZE = 512  # Updated to 512
latest_ml_predictions = []
debug_frame = None
DEBUG_WINDOW_ENABLED = False
MON_X, MON_Y, MON_W, MON_H = 0, 0, 0, 0


def set_confidence_threshold_config(threshold: float):
    global CONFIDENCE_THRESHOLD
    CONFIDENCE_THRESHOLD = threshold


def set_debug_mode_config(state: bool):
    global debug_flag, DEBUG_WINDOW_ENABLED
    debug_flag = state
    DEBUG_WINDOW_ENABLED = state


def set_failsafe_timer_config(val: float):
    global FAILSAFE_TIMER
    FAILSAFE_TIMER = val
    with debug_log_lock:
        debug_log.append(f"Failsafe timer set to: {val}s")


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)


def handle_exception(exc_type, exc_value, exc_traceback):
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def load_ml_model():
    global MODEL, LABEL_MAP
    try:
        model_path = resource_path('ml_tools/models/limbus_classifier.keras')
        label_map_path = resource_path('ml_tools/models/label_map.json')
        if not os.path.exists(model_path):
            return False
        MODEL = tf.keras.models.load_model(model_path)
        with open(label_map_path, "r") as f:
            LABEL_MAP = {int(k): v for k, v in json.load(f).items()}
        return True
    except Exception as e:
        with debug_log_lock:
            debug_log.append(f"Model Load Error: {e}")
        return False


def get_contours_from_screen(screen_gray):
    thresh = cv2.adaptiveThreshold(
        screen_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Filter for larger contours given 512px context, but actually contours are found on full screen
    # The filtering logic remains the same as buttons are same size on screen
    return [
        cv2.boundingRect(cnt)
        for cnt in contours
        if 50 < cv2.boundingRect(cnt)[2] < 400 and 20 < cv2.boundingRect(cnt)[3] < 150
    ]


def predict_buttons(screen_full_color, potential_buttons):
    global latest_ml_predictions
    if MODEL is None or not potential_buttons:
        latest_ml_predictions = []
        return {}, []
    batch = []
    for (x, y, w, h) in potential_buttons:
        roi = cv2.resize(screen_full_color[y : y + h, x : x + w], (IMG_SIZE, IMG_SIZE))
        batch.append(roi.astype("float32") / 255.0)
    preds = MODEL.predict(np.array(batch), verbose=0)
    results, debug_preds, gui_preds = {}, [], []
    for i, pred in enumerate(preds):
        conf = (
            np.max(pred)
            if len(pred) > 1
            else (pred[0] if pred[0] > 0.5 else 1 - pred[0])
        )
        lbl = LABEL_MAP.get(
            np.argmax(pred) if len(pred) > 1 else int(pred[0] > 0.5), "Unknown"
        )
        gui_preds.append(f"{lbl}: {conf:.4f}")
        debug_preds.append((potential_buttons[i], lbl, conf))
        if conf > CONFIDENCE_THRESHOLD:
            if lbl not in results or conf > results[lbl][1]:
                results[lbl] = (
                    (
                        potential_buttons[i][0] + potential_buttons[i][2] // 2,
                        potential_buttons[i][1] + potential_buttons[i][3] // 2,
                    ),
                    conf,
                )
    latest_ml_predictions = sorted(gui_preds)
    return results, debug_preds


def refresh_screen_ml(grabber, monitor):
    try:
        sct = grabber.grab(monitor)
        img = np.array(sct)[:, :, :3]
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.cvtColor(
            img, cv2.COLOR_BGR2RGB
        )
    except:
        return None, None


def click(pt):
    if not pt:
        return
    pyautogui.moveTo(MON_X + pt[0], MON_Y + pt[1], duration=0.1)
    pyautogui.click()


def mouse_shake_monitor():
    global LAST_MOUSE_POS, MOUSE_SHAKES_DETECTED, LAST_SHAKE_TIME
    while True:
        try:
            if not pause_event.is_set():
                if MOUSE_SHAKES_DETECTED > 0 and (
                    time.time() - LAST_SHAKE_TIME > FAILSAFE_TIMER
                ):
                    MOUSE_SHAKES_DETECTED = 0
                cur = pyautogui.position()
                if LAST_MOUSE_POS:
                    if (
                        math.sqrt(
                            (cur.x - LAST_MOUSE_POS[0]) ** 2
                            + (cur.y - LAST_MOUSE_POS[1]) ** 2
                        )
                        > MOUSE_SHAKE_DISTANCE_THRESHOLD
                    ):
                        MOUSE_SHAKES_DETECTED += 1
                        LAST_SHAKE_TIME = time.time()
                        if MOUSE_SHAKES_DETECTED >= MOUSE_SHAKES_TO_PAUSE:
                            pause_event.set()
                            tuner = get_tuner()
                            if tuner:
                                tuner.after(
                                    0,
                                    lambda: tuner.btn_pause.config(
                                        text="Resume Bot", bg="red"
                                    ),
                                )
                            MOUSE_SHAKES_DETECTED = 0
                LAST_MOUSE_POS = (cur.x, cur.y)
            time.sleep(0.05)
        except:
            pass


def show_debug_window():
    global debug_frame
    while True:
        if DEBUG_WINDOW_ENABLED and debug_frame is not None:
            cv2.imshow("Debug", debug_frame)
            if cv2.waitKey(50) & 0xFF == 27:
                cv2.destroyWindow("Debug")
        else:
            try:
                cv2.destroyWindow("Debug")
            except:
                pass
        time.sleep(0.05)


def limbus_bot():
    global debug_frame
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        while True:
            if (
                pause_event.is_set()
                or "LimbusCompany" not in gw.getActiveWindow().title
            ):
                time.sleep(1)
                continue
            gray, color = refresh_screen_ml(sct, mon)
            if gray is None:
                continue
            contours = get_contours_from_screen(gray)
            preds, all_preds = predict_buttons(color, contours)
            if DEBUG_WINDOW_ENABLED:
                disp = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
                for (x, y, w, h), l, c in all_preds:
                    col = (0, 255, 0) if c > CONFIDENCE_THRESHOLD else (0, 0, 255)
                    cv2.rectangle(disp, (x, y), (x + w, y + h), col, 2)
                    cv2.putText(
                        disp,
                        f"{l} {c:.2f}",
                        (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        col,
                        2,
                    )
                debug_frame = disp
            if "winrate" in preds:
                click(preds["winrate"][0])
                keyboard.press_and_release("p")
                time.sleep(0.1)
                keyboard.press_and_release("enter")
                time.sleep(1.0)
            else:
                for t in ["confirm", "battle", "skip"]:
                    if t in preds:
                        click(preds[t][0])
                        time.sleep(1.0)
                        break
            time.sleep(CHECK_INTERVAL)


def main():
    sys.excepthook = handle_exception
    pyautogui.FAILSAFE = True
    global MON_X, MON_Y, MOUSE_SHAKE_DISTANCE_THRESHOLD
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        MON_X, MON_Y = mon["left"], mon["top"]
        MOUSE_SHAKE_DISTANCE_THRESHOLD *= (
            math.sqrt(mon["width"] ** 2 + mon["height"] ** 2) / 2202.0
        )
    if not load_ml_model():
        return
    print("Launching GUI...")
    launch_gui(
        pause_event_shared=pause_event,
        initial_delay_ms=delay_ms,
        initial_debug_state=debug_flag,
        initial_text_skip_state=text_skip,
        initial_confidence=CONFIDENCE_THRESHOLD,
        initial_failsafe_timer=FAILSAFE_TIMER,
        set_delay_ms_cb=lambda ms: globals().update(
            delay_ms=ms, CHECK_INTERVAL=ms / 1000.0
        ),
        set_debug_mode_cb=set_debug_mode_config,
        set_text_skip_cb=lambda state: globals().update(text_skip=state),
        set_confidence_cb=set_confidence_threshold_config,
        set_failsafe_timer_cb=set_failsafe_timer_config,
        get_debug_log_fn=lambda: list(debug_log),
        get_model_predictions_fn=lambda: latest_ml_predictions,
    )
    threading.Thread(target=mouse_shake_monitor, daemon=True).start()
    threading.Thread(target=show_debug_window, daemon=True).start()
    threading.Thread(target=limbus_bot, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        os._exit(0)

if __name__ == "__main__":
    main()
