#!/usr/bin/env python3
"""
Auto-pilot for Limbus Company battles.

Exit at any time with Ctrl+Shift+Q or by flinging the mouse to the
top-left corner (PyAutoGUI failsafe).

Dependencies: opencv-python, numpy, pyautogui, keyboard, pygetwindow
"""

# ── std-lib imports ───────────────────────────────────────────────────
import os, threading, time, sys, json
from collections import namedtuple

# ── auto-installer for third-party packages ───────────────────────────
def _require(pkg, import_as=None, pypi_name=None):
    import importlib, subprocess
    name = pypi_name or pkg
    try:
        return importlib.import_module(pkg if import_as is None else import_as)
    except ModuleNotFoundError:
        print(f"[setup] installing '{name}' …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", name])
        return importlib.import_module(pkg if import_as is None else import_as)

from roi_threshold_gui import launch_gui

if getattr(sys, 'frozen', False):
    # running in PyInstaller bundle
    import cv2, numpy as np, pyautogui, keyboard, pygetwindow as gw, mss
else:
    # normal script mode: install missing deps
    cv2       = _require("cv2",        pypi_name="opencv-python")
    np        = _require("numpy")
    pyautogui = _require("pyautogui")
    keyboard  = _require("keyboard")
    gw        = _require("pygetwindow", import_as="pygetwindow")
    mss       = _require("mss")

# ───────────────────────── Runtime safety ──────────────────────────────
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.05

exit_event = threading.Event()
pause_event = threading.Event()

# ─────────────────────── user-configurable settings ────────────────────
# moved to GUI
# try:
#     delay_ms = int(input("Frame-grab interval in ms (default 50, min 10): ") or 50)
#     if delay_ms < 10:
#         raise ValueError("Minimum delay is 10 ms.")
#     else:
#         # print(f"Frame-grab interval set to {delay_ms} ms")
#         pass
#     print(f"Frame-grab interval set to {delay_ms} ms")
# except ValueError:
#     delay_ms = 50
#     print("Defaulting to 50 ms.")

# CHECK_INTERVAL = max(delay_ms, 10) / 1000.0   # never < 10 ms
# last_grab      = 0.0

# try:
#     hdr_flag = input("Is the game in HDR mode? [t/f] (default f): ").strip().lower()
#     is_HDR = (hdr_flag == 't')
#     if is_HDR:
#         print("Mode == HDR")
#     else:
#         print("Mode == SDR")
# except ValueError:
#     is_HDR = False
#     print("Defaulting to SDR mode.")

# try:
#     debug_flag = input("Print Debug Thresholds? [t/f] (default f): ").strip().lower()
#     DEBUG_MATCH = (debug_flag == 't')
#     if DEBUG_MATCH:
#         DEBUG_MATCH = True
#         print("Debug mode enabled.")
#     else:
#         DEBUG_MATCH = False
#         print("Debug mode disabled.")
# except ValueError:
#     DEBUG_MATCH = False
#     print("Defaulting to Debug mode disabled.")

delay_ms = 50
is_HDR = False
debug_flag = False

# ── INITIALIZE SLEEP INTERVAL & LAST GRAB ─────────────────────────
CHECK_INTERVAL = delay_ms / 1000.0
last_grab      = 0.0
DEBUG_MATCH    = debug_flag
last_vals: dict[str, float] = {}
last_pass: dict[str, float] = {}

def set_delay_ms(ms: int):
    global delay_ms, CHECK_INTERVAL
    delay_ms = max(ms, 10)  # never < 10 ms
    CHECK_INTERVAL = delay_ms / 1000.0
    print(f"Frame-grab interval set to {CHECK_INTERVAL:.3f} s")

def set_is_HDR(is_hdr: bool):
    global is_HDR
    is_HDR = is_hdr
    print(f"Mode == {'HDR' if is_HDR else 'SDR'}")
    _refresh_templates() # reload templates

def set_debug_mode(debug_mode: bool):
    global debug_flag, DEBUG_MATCH
    debug_flag = debug_mode
    DEBUG_MATCH = debug_mode
    print(f"Debug mode {'enabled' if DEBUG_MATCH else 'disabled'}.")
    _refresh_templates() # reload templates

skip_debug = False
printed_this_loop = False

# ───────────────────────── Template metadata ───────────────────────────
Tmpl = namedtuple("Tmpl", "img mask thresh roi")    # roi == (x, y, w, h) or None

# name                : (basename-no-suffix,  threshold,        roi)
TEMPLATE_SPEC = {
    "winrate"         : ("winrate",                0.82,        (0.50, 0.70, 0.50, 0.30)),
    "speech_menu"     : ("Speech Menu",            0.75,        (0.50, 0.00, 1.00, 0.20)),
    "fast_forward"    : ("Fast Forward",           0.75,        (0.50, 0.00, 1.00, 0.20)),
    "confirm"         : ("Confirm",                0.80,        (0.44, 0.60, 0.12, 0.12)),
    "black_confirm"   : ("Black Confirm",          0.80,        (0.36, 0.67, 0.26, 0.12)),
    "battle"          : ("To Battle",              0.70,        (0.50, 0.50, 0.50, 0.50)),
    "chain_battle"    : ("Battle Chain",           0.70,        (0.50, 0.50, 0.50, 0.50)),
    "skip"            : ("Skip",                   0.70,        (0.00, 0.30, 0.50, 0.40)),
    "enter"           : ("Enter",                  0.75,        (0.50, 0.60, 0.50, 0.40)),
    "choice_needed"   : ("Choice Check",           0.70,        None                    ),
    "fusion_check"    : ("Fusion Check",           0.70,        (0.00, 0.00, 1.00, 0.40)),
    "ego_check"       : ("EGO Check",              0.80,        (0.00, 0.00, 1.00, 0.40)),
    "ego_get"         : ("EGO Get",                0.80,        (0.00, 0.00, 1.00, 0.40)),
    "proceed"         : ("Proceed",                0.80,        (0.50, 0.70, 0.50, 0.30)),
    "very_high"       : ("Very High",              0.80,        (0.00, 0.70, 1.00, 0.30)),
    "commence"        : ("Commence",               0.80,        (0.50, 0.70, 0.50, 0.30)),
    "commence_battle" : ("Commence Battle",        0.80,        (0.50, 0.70, 0.50, 0.30)),
    "continue"        : ("Continue",               0.80,        (0.50, 0.70, 0.50, 0.30)),
}

from copy import deepcopy
DEFAULT_TEMPLATE_SPEC = deepcopy(TEMPLATE_SPEC)


# FAST_GATES = (
#     "winrate",
#     "speech_menu", "fast_forward",
#     "confirm",
# )

# ────────────────────────────  Helpers  ────────────────────────────────
def resource_path(fname: str) -> str:
    """Absolute path relative to the script location."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)

def load_templates() -> dict[str, Tmpl]:
    """Load images → grayscale + optional mask, verify files exist."""
    suffix = {True: " HDR.png", False: " SDR.png"}[is_HDR]
    out: dict[str, Tmpl] = {}

    for name, (base, thresh, roi) in TEMPLATE_SPEC.items():
        file = base + suffix
        if not os.path.isfile(resource_path(file)):
            file = base + ".png"

        img = cv2.imread(resource_path(file), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"Template not found: {file}")

        # split off alpha channel (if present)
        if img.shape[2] == 4:
            bgr, alpha = img[:, :, :3], img[:, :, 3]
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            mask = (alpha > 0).astype(np.uint8)
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            mask = None

        gray = cv2.equalizeHist(gray)
        out[name] = Tmpl(gray, mask, thresh, roi)

    return out

TEMPLATES = load_templates()

def active_window_title() -> str:
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""

def best_match(screen_gray: np.ndarray, tmpl: Tmpl, *, label: str = ""):
    global last_vals, last_pass

    # unpack roi (could be None or a 4‐tuple)
    if tmpl.roi:
        x, y, w, h = tmpl.roi
        H, W = screen_gray.shape
        # if fractional, convert to pixels
        if any(isinstance(v, float) and v <= 1.0 for v in (x, y, w, h)):
            x, y, w, h = int(x*W), int(y*H), int(w*W), int(h*H)
        region = screen_gray[y:y+h, x:x+w]
    else:
        region = screen_gray
        x = y = 0

    rh, rw = region.shape
    th, tw = tmpl.img.shape

    # if the region is too small, skip
    key = label or next(k for k,v in TEMPLATES.items() if v is tmpl)
    if rh < th or rw < tw:
        last_vals[key] = 0.0
        return None

    # optional: histogram equalize for better contrast
    region_eq   = cv2.equalizeHist(region)
    template_eq = cv2.equalizeHist(tmpl.img)

    # match
    res = cv2.matchTemplate(region_eq, template_eq, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    # record raw score
    last_vals[key] = max_val

    if max_val < tmpl.thresh:
        return None

    # record last passing score
    last_pass[key] = max_val

    # return center‐of‐match in full‐screen coords
    cx = x + max_loc[0] + tw//2
    cy = y + max_loc[1] + th//2
    return (cx, cy)

def click(pt, label=None, hold_ms=0):
    if label:
        print(label, pt)          # pt is (x,y) in mss / physical pixels
    # step-1 : translate from monitor-local to absolute physical
    phys_x = MON_X + pt[0]
    phys_y = MON_Y + pt[1]
    # step-2 : convert physical → logical (DPI-scaled) for PyAutoGUI
    log_x  = phys_x / scale_x
    log_y  = phys_y / scale_y
    pyautogui.moveTo(log_x, log_y)
    pyautogui.mouseDown()
    if hold_ms:
        time.sleep(hold_ms / 1000.0)
    pyautogui.mouseUp()

# ── fast screenshot with mss (≈3 ms) ───────────────────────────────────
grabber  = mss.mss()
monitor   = grabber.monitors[1]    # primary capture
MON_X, MON_Y = monitor["left"], monitor["top"]
MON_W, MON_H = monitor["width"], monitor["height"]

LOG_W, LOG_H = pyautogui.size()    # what PyAutoGUI sees (scaled)
scale_x = MON_W / LOG_W            # 1.00, 1.25, 1.50, 2.00 …
scale_y = MON_H / LOG_H

def refresh_screen() -> np.ndarray:
    # full‐sized grab, we’ll crop later per‐ROI
    img = pyautogui.screenshot()              # PIL image
    arr = np.asarray(img)                     # H×W×3 BGR
    return cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

def _refresh_templates():
    global TEMPLATES
    TEMPLATES = load_templates()

config_path = os.path.join(os.path.dirname(__file__), "roi_thresholds.json")
if os.path.isfile(config_path):
    with open(config_path) as fp:
        saved = json.load(fp)
    for name, vals in saved.items():
        if name in TEMPLATE_SPEC:
            base, _, _ = TEMPLATE_SPEC[name]
            TEMPLATE_SPEC[name] = (base,
                                   vals["threshold"],
                                   tuple(vals["roi"]) if vals["roi"] else None)

launch_gui(
    TEMPLATE_SPEC,
    _refresh_templates,
    pause_event,
    initial_delay_ms=delay_ms,
    initial_is_HDR=is_HDR,
    initial_debug=debug_flag,
    delay_cb=set_delay_ms,
    hdr_cb=set_is_HDR,
    debug_cb=set_debug_mode,
    debug_vals_fn=lambda: last_vals,
    debug_pass_fn=lambda: last_pass,
    default_spec=DEFAULT_TEMPLATE_SPEC
)


# ───────────────────────────  Main loop  ───────────────────────────────
exit_event = threading.Event()    # set by hotkey → stops current run

def limbus_bot():
    """Runs until exit_event is set, then returns to caller."""
    global last_grab
    global skip_debug
    global printed_this_loop
    need_refresh = True
    screen_gray: np.ndarray | None = None

    while not exit_event.is_set():
        # Bot is paused: do nothing but loop
        if pause_event.is_set():
            time.sleep(CHECK_INTERVAL)
            continue

        if "LimbusCompany" in active_window_title():

            # ── grab a new frame only when CHECK_INTERVAL ms have passed OR we explicitly asked for one ──
            now = time.perf_counter()
            if need_refresh or now - last_grab >= CHECK_INTERVAL:
                screen_gray = refresh_screen()
                last_grab   = now
                need_refresh = False
                skip_debug  = False          # ← allow debug prints again
                printed_this_loop = False    # ← reset printed flag

            # 1) Win-rate check
            if (pt := best_match(screen_gray, TEMPLATES["winrate"])):
                print("Auto-Battle (WinRate) – running…")
                # Move pointer to a clear spot: centre-x, 10 % down
                # (this is to skip boss encounter text that appears
                #  in certain fights, especially in Mirror Dungeons,
                #  ex. [So That No One Will Cry (T-04-11-20)])
                h, w = screen_gray.shape
                pyautogui.moveTo(w // 2, int(h * 0.10))
                pyautogui.click()
                time.sleep(0.1)
                keyboard.press_and_release("p")
                time.sleep(0.25)
                keyboard.press_and_release("enter")

                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            # 2) Speech-menu three-step sequence
            if (pt := best_match(screen_gray, TEMPLATES["speech_menu"])):
                print("Dialogue Skip – running…")
                # Step 1: click Speech Menu
                # (this is the Hamburger Menu found in dialogues)
                click(pt, "Speech Menu → click", hold_ms=10)
                time.sleep(CHECK_INTERVAL)
                screen_gray = refresh_screen()

                # Step 2: click Fast Forward (if present)
                # (this is the Fast Forward button in dialogues)
                if (ff := best_match(screen_gray, TEMPLATES["fast_forward"])):
                    click(ff, "Fast Forward → click", hold_ms=10)
                    time.sleep(CHECK_INTERVAL)
                    screen_gray = refresh_screen()

                # Step 3: only click Confirm if “Choice Check” is NOT present
                # (this is the Confirm button in dialogues [white])
                if not best_match(screen_gray, TEMPLATES["choice_needed"]):
                    if (cf := best_match(screen_gray, TEMPLATES["confirm"])):
                        click(cf, "Confirm → click", hold_ms=10)
                        time.sleep(CHECK_INTERVAL)

                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            # 3) Overlays & Confirm  ─ unified logic
            choice_overlay   = best_match(screen_gray, TEMPLATES["choice_needed"])
            fusion_overlay   = best_match(screen_gray, TEMPLATES["fusion_check"])
            ego_overlay      = best_match(screen_gray, TEMPLATES["ego_check"])
            ego_get_overlay  = best_match(screen_gray, TEMPLATES["ego_get"])
            ego_block        = ego_overlay and not ego_get_overlay   # block only when Get is absent
            choice_skip      = choice_overlay and ego_get_overlay    # skip if both are present

            # ── Bail-early overlays ──────────────────────────────────────────────
            if choice_overlay and not choice_skip:
                print("Choice Needed – waiting…")
                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            elif ego_block:
                print("EGO Gift Check – waiting…")
                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            elif fusion_overlay:
                print("Fusion Check – waiting…")
                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            elif ego_get_overlay:
                print("EGO Gift Recieved - running...")
                # Move pointer to a clear spot: centre-x, 80% down
                h, w = screen_gray.shape
                pyautogui.moveTo(w // 2, int(h * 0.75))
                pyautogui.click()
                time.sleep(0.1)

                continue

            elif choice_skip:
                print("EGO Gift Recieved - running...")
                # Move pointer to a clear spot: centre-x, 80% down
                h, w = screen_gray.shape
                pyautogui.moveTo(w // 2, int(h * 0.75))
                pyautogui.click()
                time.sleep(0.1)

                continue

            # ── Confirm (no blocking overlays, no undesired EGO-Continue scenario) ──
            black = best_match(screen_gray, TEMPLATES["black_confirm"])
            white = best_match(screen_gray, TEMPLATES["confirm"])
            if black or white:
                print("Confirm – running…")
                click(black or white, "Confirm → click", hold_ms=10)
                time.sleep(CHECK_INTERVAL)
                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            # 4) Skip button
            # (this is the Skip button in the Abnormality Event)
            if (pt := best_match(screen_gray, TEMPLATES["skip"])):
                print("Skip Abno. Dialogue – running…")
                click(pt, "Skip → click", hold_ms=10)
                time.sleep(0.2)
                screen_gray = refresh_screen()

                # If Continue is present, click that too
                # (this is the “Continue” button in the Abnormality Event)
                # clicks twice to auto advance the dialogue
                if (pt := best_match(screen_gray, TEMPLATES["continue"])):
                    click(pt, "Continue → click", hold_ms=10)
                    time.sleep(CHECK_INTERVAL)
                    click(pt, "Continue → click", hold_ms=10)
                    time.sleep(CHECK_INTERVAL)
                    screen_gray = refresh_screen()

                # If Very High is present, click that too
                # (this selects the first sinner with Very High chance of
                #  passing the Abnormality Event Check)
                if (pt := best_match(screen_gray, TEMPLATES["very_high"])):
                    click(pt, "Very High → click", hold_ms=10)
                    time.sleep(0.25)
                    screen_gray = refresh_screen()

                # If Proceed is present, click that too
                # (this is the Proceed button in the Abnormality Event)
                # clicks twice to auto advance the dialogue
                if (pt := best_match(screen_gray, TEMPLATES["proceed"])):
                    click(pt, "Proceed → click", hold_ms=10)
                    time.sleep(0.2)
                    h, w = screen_gray.shape
                    pyautogui.moveTo(w // 2, int(h * 0.90))
                    pyautogui.click()
                    time.sleep(0.1)
                    time.sleep(CHECK_INTERVAL)
                    screen_gray = refresh_screen()

                # If Commence is present, click that too
                # (this is the Commence button in the Abnormality Event)
                if (pt := best_match(screen_gray, TEMPLATES["commence"])):
                    click(pt, "Commence → click", hold_ms=10)
                    time.sleep(0.2)
                    h, w = screen_gray.shape
                    pyautogui.moveTo(w // 2, int(h * 0.90))
                    pyautogui.click()
                    time.sleep(0.1)
                    time.sleep(CHECK_INTERVAL)
                    screen_gray = refresh_screen()

                # If Commence Battle is present, click that too
                # (this is the Commence Battle button in the Abnormality Event)
                if (pt := best_match(screen_gray, TEMPLATES["commence_battle"])):
                    click(pt, "Commence Battle → click", hold_ms=10)
                    time.sleep(0.2)
                    screen_gray = refresh_screen()

                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            # 5) To Battle
            # (this is the To Battle button in the party select screen)
            # (also checks for blue chain battle button)
            battle = best_match(screen_gray, TEMPLATES["battle"])
            chain  = best_match(screen_gray, TEMPLATES["chain_battle"])
            if battle or chain:
                print("To Battle – running…")
                click(battle or chain, "To Battle → click", hold_ms=10)
                time.sleep(CHECK_INTERVAL)
                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

            # 6) Enter
            # (this is the Enter button in the encounter select screen)
            if (pt := best_match(screen_gray, TEMPLATES["enter"])):
                click(pt, "Enter → click")
                time.sleep(CHECK_INTERVAL)
                need_refresh = True
                skip_debug  = True          # ← skip debug prints until next refresh

                continue

        time.sleep(CHECK_INTERVAL)     # idle back-off to prevent CPU hogging

        # ───────── extra newline after each full debug pass ─────────
        if printed_this_loop:          # print exactly one blank line
            print()
            printed_this_loop = False  # ← reset so we don’t print again next loop

# ──────────────────────── Supervisor / hotkey wrapper ──────────────────
def main():
    # Register global hotkeys once
    # Pause / resume the bot with Ctrl+Shift+D
    keyboard.add_hotkey('ctrl+shift+d',
                        lambda: exit_event.set(),
                        suppress=True, trigger_on_release=True)

    # HARD BREAK  → Ctrl + Alt + D
    keyboard.add_hotkey('ctrl+alt+d',
                        lambda: os._exit(0),       # exits immediately, no clean-up
                        suppress=True, trigger_on_release=False)   # fire on key-down

    print("Limbus bot ready.")
    
    while True:
        exit_event.clear()
        print("\nStarting bot — Ctrl+Shift+D to pause.")
        limbus_bot()                     # returns when exit_event is set
        print("\nBot paused.  Press Enter to restart or Ctrl+C to quit.")
        try:
            input()                      # wait for a single line
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

# ───────────────────────────── Entrypoint loop ─────────────────────────
if __name__ == "__main__":
    main()