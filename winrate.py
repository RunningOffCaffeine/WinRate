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
        # print(f"[setup] installing '{name}' …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", name])
        return importlib.import_module(pkg if import_as is None else import_as)

from gui_config import launch_gui
from gui_config import get_tuner

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
pyautogui.PAUSE    = 0.05 # 50 ms between actions

pause_event = threading.Event()    # set by hotkey → pauses current run

# ────────────────────────── ORB MATCHER SETUP ──────────────────────────
# ORB detector (max 100000 keypoints) + Hamming brute-force matcher
_orb   = cv2.ORB_create(nfeatures=100000)
_bf    = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
ORB_SCALE = 1000

# ─────────────────────── user-configurable settings ────────────────────
delay_ms = 50
is_HDR = False
debug_flag = False
text_skip = False
lux_thread = False
lux_EXP = False
full_auto_mirror = False

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
    debug_log.append(f"Frame-grab interval set to {delay_ms} ms.")
    _refresh_templates() # reload templates
    tuner = get_tuner()
    if tuner:
        tuner.var_delay.set(delay_ms)

def set_is_HDR(is_hdr: bool):
    global is_HDR
    is_HDR = is_hdr
    debug_log.append(f"Mode == {'HDR' if is_HDR else 'SDR'}.")
    _refresh_templates() # reload templates
    tuner = get_tuner()
    if tuner:
        tuner.after(0, tuner._refresh_debug)

def set_text_skip(skip: bool):
    global text_skip
    text_skip = skip
    debug_log.append(f"Text skip {'enabled' if skip else 'disabled'}.")
    _refresh_templates()
    tuner = get_tuner()
    if tuner:
        tuner.var_text_skip.set(skip)

def set_debug_mode(debug_mode: bool):
    global debug_flag, DEBUG_MATCH
    debug_flag = debug_mode
    DEBUG_MATCH = debug_mode
    debug_log.append(f"Debug mode {'enabled' if debug_mode else 'disabled'}.")
    _refresh_templates()
    tuner = get_tuner()
    if tuner:
        tuner.var_debug.set(debug_mode)
        # optionally re–show or hide the panel:
        if debug_mode:
            tuner.DEBUG_PANEL.pack(side="right", fill="y", padx=(8,0))
            tuner._refresh_debug()
        else:
            tuner.DEBUG_PANEL.pack_forget()

def set_lux_thread(lux_thr: bool):
    global lux_thread
    lux_thread = lux_thr
    debug_log.append(f"Thread Luxcavation {'enabled' if lux_thread else 'disabled'}.")
    _refresh_templates()

    # make the GUI checkbox reflect the new state:
    tuner = get_tuner()
    if tuner:
        tuner.var_lux_thread.set(lux_thr)

def set_lux_exp(lux_exp: bool):
    global lux_EXP
    lux_EXP = lux_exp
    debug_log.append(f"EXP Luxcavation {'enabled' if lux_EXP else 'disabled'}.")
    _refresh_templates()
    tuner = get_tuner()
    if tuner:
        tuner.var_lux_EXP.set(lux_exp)

def set_full_auto_mirror(full_auto: bool):
    global full_auto_mirror
    full_auto_mirror = full_auto
    debug_log.append(f"Full auto mirror {'enabled' if full_auto else 'disabled'}.")
    _refresh_templates()
    tuner = get_tuner()
    if tuner:
        tuner.var_mirror_full_auto.set(full_auto)

# ───────────────────────── Template metadata ───────────────────────────
Tmpl = namedtuple("Tmpl", "imgs masks thresh roi")    # roi == (x, y, w, h) or None

# name                      : (basename-no-suffix,     threshold,                            roi)
TEMPLATE_SPEC = {
    "winrate"            : ("winrate",                     0.75,       (0.50, 0.70, 0.50, 0.30)),
    "speech_menu"        : ("Speech Menu",                 0.75,       (0.50, 0.00, 0.50, 0.30)),
    "fast_forward"       : ("Fast Forward",                0.75,       (0.45, 0.00, 0.35, 0.20)),
    "confirm"            : ("Confirm",                     0.80,       (0.35, 0.55, 0.35, 0.25)),
    "black_confirm"      : ("Black Confirm",               0.80,       (0.36, 0.67, 0.26, 0.12)),
    "battle"             : ("To Battle",                   0.70,       (0.70, 0.70, 0.30, 0.30)),
    "chain_battle"       : ("Battle Chain",                0.82,       (0.50, 0.50, 0.50, 0.50)),
    "skip"               : ("Skip",                        0.80,       (0.00, 0.30, 0.50, 0.40)),
    "enter"              : ("Enter",                       0.80,       (0.50, 0.60, 0.50, 0.40)),
    "choice_needed"      : ("Choice Check",                0.70,       (0.45, 0.20, 0.45, 0.15)),
    "fusion_check"       : ("Fusion Check",                0.70,       (0.20, 0.00, 0.60, 0.30)),
    "ego_check"          : ("EGO Check",                   0.80,       (0.33, 0.22, 0.33, 0.10)),
    "ego_get"            : ("EGO Get",                     0.80,       (0.33, 0.22, 0.33, 0.10)),
    "proceed"            : ("Proceed",                     0.80,       (0.50, 0.70, 0.50, 0.30)),
    "very_high"          : ("Very High",                   0.85,       (0.00, 0.70, 1.00, 0.30)),
    "commence"           : ("Commence",                    0.80,       (0.50, 0.70, 0.50, 0.30)),
    "commence_battle"    : ("Commence Battle",             0.80,       (0.50, 0.70, 0.50, 0.30)),
    "continue"           : ("Continue",                    0.80,       (0.50, 0.70, 0.50, 0.30)),
    # # Full Auto Mirror Dungeon
    # "mirror_dungeon"     : ("Mirror Dungeon",              0.70,       (0.25, 0.35, 0.20, 0.25)),
    # "mirror_enter"       : ("Mirror Enter",                0.80,       (0.65, 0.60, 0.35, 0.20)),
    # # "mirror_theme"       : ("Mirror Theme",                0.80,       (0.50, 0.50, 0.50, 0.50)),
    # # Abno. Events
    # "abno_choice_check"  : ("Abnormality Choice Check",    0.80,       (0.50, 0.50, 0.50, 0.50)),
    # "abno_level"         : ("Abnormality Level",           0.80,       (0.50, 0.50, 0.50, 0.50)),
    # "abno_earn"          : ("Abnormality Earn",            0.80,       (0.50, 0.50, 0.50, 0.50)),
    # "abno_gain"          : ("Abnormality Gain",            0.80,       (0.50, 0.50, 0.50, 0.50)),
    # # Encounter Rewards
    # "ego_gift_choice"    : ("EGO Gift Choice",             0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "gift_reward_1"      : ("Gift Reward Rank 1",          0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "gift_reward_2"      : ("Gift Reward Rank 2",          0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "gift_reward_3"      : ("Gift Reward Rank 3",          0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "gift_reward_4"      : ("Gift Reward Rank 4",          0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward"   : ("Encounter Reward",            0.80,       (0.15, 0.15, 0.55, 0.15)),
    # "encounter_reward_1" : ("Encounter Reward Rank 1",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_2" : ("Encounter Reward Rank 2",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_3" : ("Encounter Reward Rank 3",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_4" : ("Encounter Reward Rank 4",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_5" : ("Encounter Reward Rank 5",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_6" : ("Encounter Reward Rank 6",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_7" : ("Encounter Reward Rank 7",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_8" : ("Encounter Reward Rank 8",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_9" : ("Encounter Reward Rank 9",     0.80,       (0.15, 0.15, 0.70, 0.50)),
    # "encounter_reward_10": ("Encounter Reward Rank 10",    0.80,       (0.15, 0.15, 0.70, 0.50)),
    # # Mirror Dungeon Stages
    # "md_sword"           : ("MD Sword",                    0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_twosword"        : ("MD Two Sword",                0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_coin"            : ("MD Coin",                     0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_question"        : ("MD Question",                 0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_ex_question"     : ("MD Exclamation",              0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_monster"         : ("MD Monster",                  0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_abno"            : ("MD Abnormality",              0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_boss"            : ("MD Boss",                     0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_shop"            : ("MD Shop",                     0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "md_supershop"       : ("MD Super Shop",               0.80,       (0.50, 0.00, 0.20, 0.80)),
    # "leave"              : ("Leave",                       0.80,       (0.50, 0.50, 0.50, 0.50)),
    # Auto Luxcavations
    "luxcavations"       : ("Luxcavations",                0.80,       (0.22, 0.08, 0.25, 0.40)),
    "select_exp_lux"     : ("Select EXP Lux",              0.80,       (0.04, 0.30, 0.15, 0.12)),
    "select_thread_lux"  : ("Select Thread Lux",           0.80,       (0.04, 0.40, 0.15, 0.12)),
    "lux_enter"          : ("Lux Enter",                   0.80,       (0.20, 0.55, 0.80, 0.25)),
    "exp_lux_enter"      : ("EXP Lux Enter",               0.80,       (0.20, 0.60, 0.80, 0.20)),
    "thread_lux_battle"  : ("Thread Lux Battle Select",    0.80,       (0.30, 0.30, 0.42, 0.45)),
    "drive"              : ("Drive",                       0.92,       (0.50, 0.80, 0.50, 0.20)),
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
    """Load both HDR and SDR (plus fallback) for every template."""
    out: dict[str, Tmpl] = {}

    for name, (base, thresh, roi) in TEMPLATE_SPEC.items():
        imgs: list[np.ndarray] = []
        masks: list[np.ndarray|None] = []

        # try HDR then SDR
        for suffix in (" HDR.png", " SDR.png"):
            path = resource_path(base + suffix)
            if os.path.isfile(path):
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                # split off alpha channel if present
                if img.shape[2] == 4:
                    bgr, alpha = img[:, :, :3], img[:, :, 3]
                    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                    mask = (alpha > 0).astype(np.uint8)
                else:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    mask = None
                gray = cv2.equalizeHist(gray)
                imgs.append(gray)
                masks.append(mask)

        # if neither HDR nor SDR found, fall back to base.png
        if not imgs:
            path = resource_path(base + ".png")
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Template not found: {base}.png")
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img.shape[2] == 4:
                bgr, alpha = img[:, :, :3], img[:, :, 3]
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                mask = (alpha > 0).astype(np.uint8)
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                mask = None
            gray = cv2.equalizeHist(gray)
            imgs.append(gray)
            masks.append(mask)

        out[name] = Tmpl(imgs, masks, thresh, roi)

    return out


TEMPLATES = load_templates()

def active_window_title() -> str:
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""

# Debug Log
debug_log: list[str] = []

def best_match(screen_gray: np.ndarray, tmpl: Tmpl, *, label: str = ""):
    """
    Try every variant in tmpl.imgs (HDR + SDR), pick the best match.
    Return centre-of-match or None.
    """
    global last_vals, last_pass

    # 1) Extract ROI
    if tmpl.roi:
        x, y, w, h = tmpl.roi
        H, W = screen_gray.shape
        # fractional → pixels
        if any(isinstance(v, float) and v <= 1.0 for v in (x, y, w, h)):
            x, y, w, h = int(x * W), int(y * H), int(w * W), int(h * H)
        region = screen_gray[y:y+h, x:x+w]
    else:
        x = y = 0
        region = screen_gray

    rh, rw = region.shape

    # 2) Slide over every variant, track highest score
    best_val: float = -1.0
    best_loc: tuple[int,int] = (0, 0)
    best_sz: tuple[int,int] = (0, 0)

    for img in tmpl.imgs:
        th, tw = img.shape
        if rh < th or rw < tw:
            continue
        res = cv2.matchTemplate(region, img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_sz = (tw, th)

    # record raw score for GUI
    try:
        key = label or next(k for k,v in TEMPLATES.items() if v is tmpl)
    except StopIteration:
        key = label or "<unknown>"
    last_vals[key] = best_val

    # 3) threshold check
    if best_val < tmpl.thresh:
        return None

    # record last passing score
    last_pass[key] = best_val

    # 4) compute centre in full‐screen coords
    cx = x + best_loc[0] + best_sz[0] // 2
    cy = y + best_loc[1] + best_sz[1] // 2
    return (cx, cy)

def _tm_center(region, x, y, tmpl):
    res = cv2.matchTemplate(region, tmpl.img, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(res)
    tw, th = tmpl.img.shape[::-1]
    return (x + max_loc[0] + tw//2, y + max_loc[1] + th//2)

def _tm_fallback(region, x, y, tmpl, key):
    res = cv2.matchTemplate(region, tmpl.img, cv2.TM_CCOEFF_NORMED)
    _, mx, _, _ = cv2.minMaxLoc(res)
    last_vals[key] = mx
    if mx < tmpl.thresh:
        return None
    last_pass[key] = mx
    return _tm_center(region, x, y, tmpl)

def click(pt, label=None, hold_ms=0):
    # if label:
        # print(label, pt)          # pt is (x,y) in mss / physical pixels
    # step-1 : translate from monitor-local to absolute physical
    if pt is None:
        return
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
    TEMPLATE_SPEC,          # initial_template_spec,
    _refresh_templates,     # refresh_templates_cb,
    pause_event,            # pause_event,
    delay_ms,               # initial_delay_ms
    is_HDR,                 # initial_is_HDR
    debug_flag,             # initial_debug
    text_skip,              # initial_text_skip
    set_delay_ms,           # delay_cb
    set_is_HDR,             # hdr_cb
    set_debug_mode,         # debug_cb
    set_text_skip,          # text_skip_cb
    lambda: last_vals,      # debug_vals_fn
    lambda: last_pass,      # debug_pass_fn
    lambda: debug_log,      # debug_log_fn
    DEFAULT_TEMPLATE_SPEC,  # default_spec
    lux_thread,             # initial_lux_thread
    lux_EXP,                # initial_lux_EXP
    full_auto_mirror,       # initial_mirror_full_auto
    set_lux_thread,         # lux_thread_cb
    set_lux_exp,            # lux_EXP_cb
    set_full_auto_mirror    # mirror_full_auto_cb
)


# ───────────────────────────  Main loop  ───────────────────────────────
def limbus_bot():
    """Runs until pause_event or os.exit(), then returns to caller."""
    global last_grab
    global lux_thread, lux_EXP, full_auto_mirror
    need_refresh = True
    screen_gray: np.ndarray | None = None

    while True:
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


            # 1) Win-rate check
            if (pt := best_match(screen_gray, TEMPLATES["winrate"])):
                debug_log.append("[1] Auto-Battle (WinRate) check")
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
                time.sleep(0.25)

                need_refresh = True

                continue

            # 2) Speech-menu three-step sequence
            if text_skip:
                if (pt := best_match(screen_gray, TEMPLATES["speech_menu"])):
                    debug_log.append("[2-1] Dialogue Skip check")
                    # Step 1: click Speech Menu
                    # (this is the Hamburger Menu found in dialogues)
                    click(pt, "Speech Menu → click", hold_ms=10)
                    time.sleep(CHECK_INTERVAL)
                    screen_gray = refresh_screen()

                    # Step 2: click Fast Forward (if present)
                    # (this is the Fast Forward button in dialogues)
                    if (ff := best_match(screen_gray, TEMPLATES["fast_forward"])):
                        debug_log.append("[2-2] Fast Forward check")
                        click(ff, "Fast Forward → click", hold_ms=10)
                        time.sleep(CHECK_INTERVAL)
                        screen_gray = refresh_screen()

                    # Step 3: only click Confirm if “Choice Check” is NOT present
                    # (this is the Confirm button in dialogues [white])
                    if not best_match(screen_gray, TEMPLATES["choice_needed"]):
                        if (cf := best_match(screen_gray, TEMPLATES["confirm"])):
                            debug_log.append("[2-3] Confirm check")
                            click(cf, "Confirm → click", hold_ms=10)
                            time.sleep(CHECK_INTERVAL)

                    need_refresh = True

                    continue

            # 3) Overlays & Confirm  ─ unified logic
            choice_overlay   = best_match(screen_gray, TEMPLATES["choice_needed"])
            fusion_overlay   = best_match(screen_gray, TEMPLATES["fusion_check"])
            ego_overlay      = best_match(screen_gray, TEMPLATES["ego_check"])
            ego_get_overlay  = best_match(screen_gray, TEMPLATES["ego_get"])
            ego_block        = ego_overlay and not ego_get_overlay   # block only when Get is absent
            choice_skip      = choice_overlay and ego_get_overlay    # skip if both are present

            # ── Bail-early overlays ──────────────────────────────────────────────
            if not full_auto_mirror:
                if choice_overlay and not choice_skip:
                    debug_log.append("[3-1] Choice Check – waiting…")
                    need_refresh = True

                    continue

                elif ego_block:
                    debug_log.append("[3-2] EGO Check – waiting…")
                    need_refresh = True

                    continue

                elif fusion_overlay:
                    debug_log.append("[3-3] Fusion Check – waiting…")
                    need_refresh = True

                    continue

                elif ego_get_overlay:
                    debug_log.append("[3-4] EGO Gift Recieved – running…")
                    # # Move pointer to a clear spot: center-x, 80% down
                    # h, w = screen_gray.shape
                    # pyautogui.moveTo(w // 2, int(h * 0.75))
                    # pyautogui.click()
                    keyboard.press_and_release("enter")
                    time.sleep(CHECK_INTERVAL)

                    continue

                elif choice_skip:
                    debug_log.append("[3-5] Choice Skip – running…")
                    # # Move pointer to a clear spot: centre-x, 80% down
                    # h, w = screen_gray.shape
                    # pyautogui.moveTo(w // 2, int(h * 0.75))
                    # pyautogui.click()
                    keyboard.press_and_release("enter")
                    time.sleep(CHECK_INTERVAL)

                    continue

            # ── Confirm (no blocking overlays, no undesired EGO-Continue scenario) ──
            black = best_match(screen_gray, TEMPLATES["black_confirm"])
            white = best_match(screen_gray, TEMPLATES["confirm"])
            if black or white:
                debug_log.append("[3-6] Confirm – running…")
                click(black or white, "Confirm → click", hold_ms=10)
                time.sleep(CHECK_INTERVAL)
                need_refresh = True

                continue

            # 4) Skip button
            # (this is the Skip button in the Abnormality Event)
            if (pt := best_match(screen_gray, TEMPLATES["skip"])):
                debug_log.append("[4-1] Skip Abno. Dialogue – running…")
                click(pt, "Skip → click", hold_ms=10)
                h, w = screen_gray.shape
                pyautogui.moveTo(w // 2, int(h * 0.10)) # move away to avoid hiding skip button
                time.sleep(0.2)
                screen_gray = refresh_screen()

                # Abnormality Event: Select Event Type
                if full_auto_mirror:
                    events = [
                        TEMPLATES["abno_level"],
                        TEMPLATES["abno_earn"],
                        TEMPLATES["abno_gain"],
                        TEMPLATES["abno_restore"],
                        TEMPLATES["abno_blank"],
                    ]
                    for event in events:
                        if (pt := best_match(screen_gray, event)):
                            debug_log.append(f"[4-1A] Abno. Event {event} – running…")
                            click(pt, "Abno. Event → click", hold_ms=10)
                            time.sleep(CHECK_INTERVAL)
                            screen_gray = refresh_screen()
                            break


                # If Continue is present, click that too
                # (this is the “Continue” button in the Abnormality Event)
                # clicks twice to auto advance the dialogue
                if (pt := best_match(screen_gray, TEMPLATES["continue"])):
                    debug_log.append("[4-2] Continue Abno. Dialogue – running…")
                    click(pt, "Continue → click", hold_ms=10)
                    time.sleep(CHECK_INTERVAL)
                    click(pt, "Continue → click", hold_ms=10)
                    time.sleep(CHECK_INTERVAL)
                    screen_gray = refresh_screen()

                # If Very High is present, click that too
                # (this selects the first sinner with Very High chance of
                #  passing the Abnormality Event Check)
                if full_auto_mirror:
                    if (pt := best_match(screen_gray, TEMPLATES["very_high"])):
                        debug_log.append("[4-3] Very High Abno. Dialogue – running…")
                        click(pt, "Very High → click", hold_ms=10)
                        time.sleep(0.25)
                        screen_gray = refresh_screen()

                    # If Proceed is present, click that too
                    # (this is the Proceed button in the Abnormality Event)
                    # clicks twice to auto advance the dialogue
                    if (pt := best_match(screen_gray, TEMPLATES["proceed"])):
                        debug_log.append("[4-4] Proceed Abno. Dialogue – running…")
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
                    debug_log.append("[4-5] Commence Abno. Dialogue – running…")
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
                    debug_log.append("[4-6] Commence Battle Abno. Dialogue – running…")
                    click(pt, "Commence Battle → click", hold_ms=10)
                    time.sleep(0.2)
                    screen_gray = refresh_screen()

                need_refresh = True

                continue

            # 5) To Battle
            # (this is the To Battle button in the party select screen)
            # (also checks for blue chain battle button)
            battle = best_match(screen_gray, TEMPLATES["battle"])
            chain  = best_match(screen_gray, TEMPLATES["chain_battle"])
            if battle or chain:
                debug_log.append("[5] To Battle / Chain Battle – running…")
                click(battle or chain, "To Battle → click", hold_ms=10)
                time.sleep(1.0)
                need_refresh = True

                continue

            # 6) Enter
            # (this is the Enter button in the encounter select screen)
            if (pt := best_match(screen_gray, TEMPLATES["enter"])):
                debug_log.append("[6] Enter – running…")
                click(pt, "Enter → click")
                time.sleep(CHECK_INTERVAL)
                need_refresh = True

                continue

            # A) Thread Luxcavation automation
            if lux_thread:
                # 1) select Drive
                screen_gray = refresh_screen()
                drive_pt = best_match(screen_gray, TEMPLATES["drive"])
                debug_log.append("[A-1] Drive check")
                if drive_pt is not None:
                    click(drive_pt, "Drive → click", hold_ms=10)
                    time.sleep(1.0)

                # 2) enter Luxcavations mode
                screen_gray = refresh_screen()
                lux_pt = best_match(screen_gray, TEMPLATES["luxcavations"])
                debug_log.append("[A-2] Luxcavations check")
                if lux_pt is not None:
                    click(lux_pt, "Luxcavations → click", hold_ms=10)
                    time.sleep(1.0)

                # 3) select Thread Lux
                screen_gray = refresh_screen()
                thr_pt = best_match(screen_gray, TEMPLATES["select_thread_lux"])
                debug_log.append("[A-3] Select Thread Lux check")
                if thr_pt is not None:
                    click(thr_pt, "Select Thread Lux → click", hold_ms=10)
                    time.sleep(1.0)

                # 4) hit the Enter button
                screen_gray = refresh_screen()
                enter_pt = best_match(screen_gray, TEMPLATES["lux_enter"])
                debug_log.append("[A-4] Lux Enter check")
                if enter_pt is not None:
                    click(enter_pt, "Lux Enter → click", hold_ms=10)
                    time.sleep(1.0)

                # 5) choose the best battle
                screen_gray = refresh_screen()
                battle_pts = best_match(screen_gray, TEMPLATES["thread_lux_battle"])
                battle_pt = None
                debug_log.append("[A-5] Thread Lux Battle check")
                if isinstance(battle_pts, list) and battle_pts:
                    # pick the lowest one (highest y)
                    battle_pts.sort(key=lambda p: p[1])
                    battle_pt = battle_pts[-1]
                elif battle_pts is not None:
                    battle_pt = battle_pts
                if battle_pt is not None:
                    click(battle_pt, "Thread Lux Battle Select → click", hold_ms=10)
                    time.sleep(1.0)

                # 6) To Battle button
                screen_gray = refresh_screen()
                battle_pt = best_match(screen_gray, TEMPLATES["battle"])
                debug_log.append("[A-6] To Battle check")
                if battle_pt is not None:
                    click(battle_pt, "To Battle → click", hold_ms=10)
                    time.sleep(2.0)

                # 7) Set back to false, run main loop
                lux_thread = set_lux_thread(False)
                need_refresh = True
                continue

            # B) EXP Luxcavation automation
            if lux_EXP:
                # 1) open Drive menu
                drive_pt = best_match(screen_gray, TEMPLATES["drive"])
                debug_log.append("[B-1] Drive check")
                if drive_pt is not None:
                    click(drive_pt, "Drive → click", hold_ms=10)
                    time.sleep(1.0)

                # 2) enter Luxcavations mode
                screen_gray = refresh_screen()
                lux_pt = best_match(screen_gray, TEMPLATES["luxcavations"])
                debug_log.append("[B-2] Luxcavations check")
                if lux_pt is not None:
                    click(lux_pt, "Luxcavations → click", hold_ms=10)
                    time.sleep(1.0)

                # 3) select EXP Lux
                screen_gray = refresh_screen()
                exp_pt = best_match(screen_gray, TEMPLATES["select_exp_lux"])
                debug_log.append("[B-3] Select EXP Lux check")
                if exp_pt is not None:
                    click(exp_pt, "Select EXP Lux → click", hold_ms=10)
                    time.sleep(1.0)

                # 4) choose which “Enter” to click (if multiple, pick the rightmost)
                screen_gray = refresh_screen()
                enter_pts = best_match(screen_gray, TEMPLATES["exp_lux_enter"])
                enter_pt = None
                debug_log.append("[B-4] EXP Lux Enter check")
                if isinstance(enter_pts, list) and enter_pts:
                    # sort by x descending and pick the first
                    enter_pts.sort(key=lambda p: p[0], reverse=True)
                    enter_pt = enter_pts[0]

                elif enter_pts is not None:
                    enter_pt = enter_pts

                if enter_pt is not None:
                    click(enter_pt, "EXP Lux Enter → click", hold_ms=10)
                    time.sleep(1.0)

                # 5) Enter the battle
                screen_gray = refresh_screen()
                battle_pt = best_match(screen_gray, TEMPLATES["battle"])
                debug_log.append("[B-5] To Battle check")
                if battle_pt is not None:
                    click(battle_pt, "To Battle → click", hold_ms=10)
                    time.sleep(2.0)
                
                # 6) Set back to false, run main loop
                lux_EXP = set_lux_exp(False)
                need_refresh = True
                continue


            # # needs images, will get when mirror dungeon resets again
            # # C) Full Auto Mirror Dungeon
            # if full_auto_mirror:
            
            #     # # 1) open Drive menu
            #     # if (pt := best_match(screen_gray, TEMPLATES["drive"])):
            #     #     debug_log.append("[C-1] Drive check")
            #     #     click(pt, "Drive → click", hold_ms=10)
            #     #     time.sleep(CHECK_INTERVAL)
            #     #     screen_gray = refresh_screen()
            #     #     need_refresh = True
            
            #     # # 2) enter Mirror Dungeon mode
            #     # if (pt := best_match(screen_gray, TEMPLATES["mirror_dungeon"])):
            #     #     debug_log.append("[C-2] Mirror Dungeon check")
            #     #     click(pt, "Mirror Dungeon → click", hold_ms=10)
            #     #     time.sleep(CHECK_INTERVAL)
            #     #     screen_gray = refresh_screen()
            #     #     need_refresh = True
            
            #     # # 3) Enter Mirror Dungeon Actual
            #     # if (pt := best_match(screen_gray, TEMPLATES["mirror_enter"])):
            #     #     debug_log.append("[C-3] Mirror Enter check")
            #     #     click(pt, "Mirror Enter → click", hold_ms=10)
            #     #     time.sleep(CHECK_INTERVAL)
            #     #     screen_gray = refresh_screen()
            #     #     need_refresh = True
            
            #     # check for stage
            #     stages = [
            #         TEMPLATES["md_supershop"],
            #         TEMPLATES["md_shop"],
            #         TEMPLATES["md_boss"],
            #         TEMPLATES["md_abno"],
            #         TEMPLATES["md_question"],
            #         TEMPLATES["md_monster"],
            #         TEMPLATES["md_coin"],
            #         TEMPLATES["md_twosword"],
            #         TEMPLATES["md_sword"],
            #     ]
            #     for stage in stages:
            #         if (pt := best_match(screen_gray, stage)):
            #             debug_log.append(f"[C-4] Entering Next {stage} Stage")
            #             click(pt, f"{stage} → click", hold_ms=10)
            #             time.sleep(CHECK_INTERVAL)
            #             screen_gray = refresh_screen()
            #             need_refresh = True

            #     # leave store
            #     if (pt := best_match(screen_gray, TEMPLATES["leave"])):
            #         debug_log.append("[C-5] Leaving Store")
            #         click(pt, "Leave → click", hold_ms=10)
            #         time.sleep(CHECK_INTERVAL)
            #         screen_gray = refresh_screen()
            #         need_refresh = True

            #     # # check for theme pack
            #     # if (pt := best_match(screen_gray, TEMPLATES["mirror_theme"])):
            #     #     debug_log.append("[C-6] Entering Theme Pack")
            #     #     click(pt, "Mirror Theme Pack → click", hold_ms=10)
            #     #     time.sleep(CHECK_INTERVAL)
            #     #     screen_gray = refresh_screen()
            #     #     need_refresh = True

            #     # check for gift reward
            #     if (pt := best_match(screen_gray, TEMPLATES["ego_gift_choice"])):
            #         # Check for multiple matches and select the highest rank reward
            #         reward_ranks = [f"gift_reward_{i}" for i in range(4, 1, -1)]
            #         for rank in reward_ranks:
            #             if (ranked_reward := best_match(screen_gray, TEMPLATES.get(rank))):
            #                 debug_log.append(f"[C-7] {rank.capitalize()} check")
            #                 click(ranked_reward, f"{rank.capitalize()} → click", hold_ms=10)
            #                 time.sleep(CHECK_INTERVAL)
            #                 screen_gray = refresh_screen()
            #                 need_refresh = True

            #     # check for encounter rewards
            #     if (pt := best_match(screen_gray, TEMPLATES["encounter_reward"])):
            #         # Check for multiple matches and select the highest rank reward
            #         reward_ranks = [f"encounter_reward_{i}" for i in range(10, 1, -1)]
            #         for rank in reward_ranks:
            #             if (ranked_reward := best_match(screen_gray, TEMPLATES.get(rank))):
            #                 debug_log.append(f"[C-8] {rank.capitalize()} Aquisition")
            #                 click(ranked_reward, f"{rank.capitalize()} → click", hold_ms=10)
            #                 time.sleep(CHECK_INTERVAL)
            #                 screen_gray = refresh_screen()
            #                 need_refresh = True

            #     if need_refresh:
            #         continue
            

        time.sleep(CHECK_INTERVAL)     # idle back-off to prevent CPU hogging

# ──────────────────────── Supervisor / hotkey wrapper ──────────────────
def main():
    # Register global hotkeys once
    # Pause / resume the bot with Ctrl+Shift+D
    def _on_pause_hotkey():
        tuner = get_tuner()
        if tuner:
            # schedule the toggle on the GUI thread
            tuner.after(0, tuner._toggle_bot)

    keyboard.add_hotkey(
        'ctrl+shift+d',
        _on_pause_hotkey,
        suppress=True, trigger_on_release=True
    )

    # HARD QUIT  → Ctrl + Alt + D
    keyboard.add_hotkey(
        'ctrl+alt+d',
        lambda: os._exit(0),
        suppress=True, trigger_on_release=False
    )

    # print("Limbus bot ready.")
    
    while True:
        limbus_bot()                     # returns when exit_event is set
        break

# ───────────────────────────── Entrypoint loop ─────────────────────────
if __name__ == "__main__":
    main()