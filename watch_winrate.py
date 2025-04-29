#!/usr/bin/env python3
"""
Auto-pilot for Limbus Company battles.

Exit at any time with Ctrl+Shift+Q or by flinging the mouse to the
top-left corner (PyAutoGUI failsafe).

Dependencies: opencv-python, numpy, pyautogui, keyboard, pygetwindow
"""

import os
import threading
import time
from collections import namedtuple

import cv2
import numpy as np
import pyautogui
import keyboard
import pygetwindow as gw

# ─────────────────────────── Runtime safety ────────────────────────────
pyautogui.FAILSAFE = True           # mouse to top-left aborts
pyautogui.PAUSE    = 0.05           # 50 ms after every PyAutoGUI call

# ───────────────────────── Frame-grab throttle ─────────────────────────
CHECK_INTERVAL = 0.05               # seconds → one new screenshot every 50 ms
last_grab      = 0.0                # monotonic timestamp of last screenshot

# ───────────────────────── Template metadata ───────────────────────────
Tmpl = namedtuple("Tmpl", "img thresh roi")    # roi == (x, y, w, h) or None

TEMPLATE_SPEC = {
    # name               (filename,                threshold,  roi)
    "winrate"         : ("winrate.png",               0.82,      None),
    "speech_menu"     : ("Speech Menu.png",           0.75,      None),
    "fast_forward"    : ("Fast Forward.png",          0.75,      None),
    "confirm"         : ("Confirm.png",               0.70,      None),
    "black_confirm"   : ("Black Confirm.png",         0.70,      None),
    "battle"          : ("To Battle.png",             0.70,      None),
    "skip"            : ("Skip.png",                  0.70,      None),
    "enter"           : ("Enter.png",                 0.65,      None),
    "choice_needed"   : ("Choice Check.png",          0.70,      None),
    "fusion_check"    : ("Fusion Check.png",          0.70,      None),
    "ego_check"       : ("EGO Check.png",             0.70,      None),
    "commence"        : ("Battle Commence.png",       0.80,      None),
    "proceed"         : ("Proceed.png",               0.80,      None),
    "very_high"       : ("Very High.png",             0.80,      None),
    "commence"        : ("Commence.png",              0.80,      None),
    "commence_battle" : ("Commence Battle.png",       0.80,      None),
    "continue"        : ("Continue.png",              0.80,      None),
}

# ────────────────────────────  Helpers  ────────────────────────────────
def resource_path(fname: str) -> str:
    """Absolute path relative to the script location."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)

def load_templates() -> dict[str, Tmpl]:
    """Load images → grayscale, verify that all files exist."""
    out: dict[str, Tmpl] = {}
    for name, (file, thresh, roi) in TEMPLATE_SPEC.items():
        img = cv2.imread(resource_path(file), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"Template image not found: {file}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        out[name] = Tmpl(gray, thresh, roi)
    return out

TEMPLATES = load_templates()

def active_window_title() -> str:
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""

def best_match(screen_gray: np.ndarray, tmpl: Tmpl):
    """Return (x, y) centre of best match or None."""
    if tmpl.roi:
        x, y, w, h = tmpl.roi
        region = screen_gray[y:y+h, x:x+w]
    else:
        x = y = 0
        region = screen_gray

    res = cv2.matchTemplate(region, tmpl.img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < tmpl.thresh:
        return None

    tw, th = tmpl.img.shape[::-1]
    cx = max_loc[0] + tw // 2 + x
    cy = max_loc[1] + th // 2 + y
    return (cx, cy)

def click(pt: tuple[int, int],
          label: str | None = None,
          hold_ms: int = 0):          # 0 ms → ordinary click
    if label:
        print(f"{label} {pt}")
    pyautogui.moveTo(*pt)
    pyautogui.mouseDown()
    if hold_ms:
        time.sleep(hold_ms / 1000.0)  # 10 ms → 0.010 s
    pyautogui.mouseUp()

def refresh_screen():
    scr = pyautogui.screenshot()
    scr_np = np.asarray(scr)
    return cv2.cvtColor(scr_np, cv2.COLOR_BGR2GRAY)

# ───────────────────────────  Main loop  ───────────────────────────────
exit_event = threading.Event()    # set by hotkey → stops current run

def limbus_bot():
    """Runs until exit_event is set, then returns to caller."""
    need_refresh = True
    screen_gray: np.ndarray | None = None

    while not exit_event.is_set():
        if "LimbusCompany" in active_window_title():

            # ── grab a new frame only when 100 ms have passed OR we explicitly asked for one ──
            now = time.perf_counter()
            if need_refresh or now - last_grab >= CHECK_INTERVAL:
                screen_gray = refresh_screen()
                last_grab   = now
                need_refresh = False

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
                continue

            # 2) Speech-menu three-step sequence
            if (pt := best_match(screen_gray, TEMPLATES["speech_menu"])):
                print("Dialogue Skip – running…")
                # Step 1: click Speech Menu
                # (this is the Hamburger Menu found in dialogues)
                click(pt, "Speech Menu → click", hold_ms=10)
                time.sleep(0.1)
                screen_gray = refresh_screen()

                # Step 2: click Fast Forward (if present)
                # (this is the Fast Forward button in dialogues)
                if (ff := best_match(screen_gray, TEMPLATES["fast_forward"])):
                    click(ff, "Fast Forward → click", hold_ms=10)
                    time.sleep(0.1)
                    screen_gray = refresh_screen()

                # Step 3: only click Confirm if “Choice Check” is NOT present
                # (this is the Confirm button in dialogues [white])
                if not best_match(screen_gray, TEMPLATES["choice_needed"]):
                    if (cf := best_match(screen_gray, TEMPLATES["confirm"])):
                        click(cf, "Confirm → click", hold_ms=10)
                        time.sleep(0.1)

                need_refresh = True
                continue

            # 3) Choice Needed – bail early
            # (this is a Mirror Dungeon check to prevent skipping
            #  encounter rewards)
            if best_match(screen_gray, TEMPLATES["choice_needed"]):
                print("Choice Needed – waiting…")
                need_refresh = True
                continue

            # 4) EGO Gift Purchase/Enhance - bail early
            # (this is a Mirror Dungeon check to prevent spending
            #  cost on every E.G.O gift you click)
            if best_match(screen_gray, TEMPLATES["ego_check"]):
                print("EGO Gift Check – waiting…")
                need_refresh = True
                continue

            # 5) Fusion Check - bail early
            # (this is a Mirror Dungeon check to prevent automatically
            #  exiting the Fusion Keyword select menu)
            if best_match(screen_gray, TEMPLATES["fusion_check"]):
                print("Fusion Check – waiting…")
                need_refresh = True
                continue

            # 6) Confirm (black or white)
            # (Mirror Dungeon & Victory screens use black; dialogs use white)
            blocking = any(
                best_match(screen_gray, TEMPLATES[k])
                for k in ("choice_needed", "fusion_check", "ego_check")
            )

            if not blocking:
                black = best_match(screen_gray, TEMPLATES["black_confirm"])
                white = best_match(screen_gray, TEMPLATES["confirm"])

                if black or white:
                    print("Confirm – running…")
                    click(black or white, "Confirm → click", hold_ms=10)
                    time.sleep(0.1)
                    need_refresh = True
                    continue

            # 7) Skip button
            # (this is the Skip button in the Abnormality Event)
            abno_skip_print = False
            if (pt := best_match(screen_gray, TEMPLATES["skip"])):
                print("Skip Abno. Dialogue – running…")
                abno_skip_print = True
                click(pt, "Skip → click", hold_ms=10)
                time.sleep(0.25)
                screen_gray = refresh_screen()

                # If Continue is present, click that too
                # (this is the “Continue” button in the Abnormality Event)
                if (pt := best_match(screen_gray, TEMPLATES["continue"])):
                    click(pt, "Continue → click", hold_ms=10)
                    time.sleep(0.25)
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
                    time.sleep(0.25)
                    screen_gray = refresh_screen()

                # If Commence is present, click that too
                # (this is the Commence button in the Abnormality Event)
                if (pt := best_match(screen_gray, TEMPLATES["commence"])):
                    click(pt, "Commence → click", hold_ms=10)
                    time.sleep(0.25)
                    screen_gray = refresh_screen()

                # If Commence Battle is present, click that too
                # (this is the Commence Battle button in the Abnormality Event)
                if (pt := best_match(screen_gray, TEMPLATES["commence_battle"])):
                    click(pt, "Commence Battle → click", hold_ms=10)
                    time.sleep(0.25)
                    screen_gray = refresh_screen()

                need_refresh = True
                continue
            abno_skip_print = False

            # 8) To Battle
            # (this is the To Battle button in the party select screen)
            if (pt := best_match(screen_gray, TEMPLATES["battle"])):
                click(pt, "To Battle → click")
                time.sleep(0.1)
                need_refresh = True
                continue

            # 9) Enter
            # (this is the Enter button in the encounter select screen)
            if (pt := best_match(screen_gray, TEMPLATES["enter"])):
                click(pt, "Enter → click")
                time.sleep(0.1)
                need_refresh = True
                continue

        time.sleep(0.05)     # idle back-off (≈ 20 FPS)

# ──────────────────────── Supervisor / hotkey wrapper ──────────────────
def main():
    # Register global hotkey once
    keyboard.add_hotkey('ctrl+shift+d',
                        lambda: exit_event.set(),
                        suppress=True, trigger_on_release=True)

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