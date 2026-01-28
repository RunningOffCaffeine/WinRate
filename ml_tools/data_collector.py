# data_collector.py
import os, sys, time, keyboard, pyautogui, mss
from PIL import Image

SAVE_DIRECTORY = "dataset"
CAPTURE_SIZE = 512  # Updated to 512
HOTKEY = "~"
OFFSET = 3
pyautogui.FAILSAFE = False


def capture_5_offsets(sct, label):
    mx, my = pyautogui.position()
    pyautogui.moveTo(0, 0, duration=0)
    time.sleep(0.05)

    offsets = [(0, 0), (-OFFSET, 0), (OFFSET, 0), (0, -OFFSET), (0, OFFSET)]
    label_dir = os.path.join(SAVE_DIRECTORY, label)
    os.makedirs(label_dir, exist_ok=True)

    base_idx = 0
    while os.path.exists(os.path.join(label_dir, f"{label}_{base_idx}_0.png")):
        base_idx += 1

    half = CAPTURE_SIZE // 2
    for i, (ox, oy) in enumerate(offsets):
        # Ensure capture box is valid (mss handles cropping usually, but good to be safe)
        box = {
            "top": int(my - half + oy),
            "left": int(mx - half + ox),
            "width": CAPTURE_SIZE,
            "height": CAPTURE_SIZE,
        }
        try:
            sct_img = sct.grab(box)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.save(os.path.join(label_dir, f"{label}_{base_idx}_{i}.png"))
            print(f"Saved offset {i}")
        except Exception as e:
            print(f"Capture failed: {e}")

    pyautogui.moveTo(mx, my, duration=0)


def main():
    print(f"--- Data Collector (5-Shot, {CAPTURE_SIZE}px) ---")
    current_label = input("Label: ")
    if not current_label:
        return
    if not os.path.exists(SAVE_DIRECTORY):
        os.makedirs(SAVE_DIRECTORY)

    with mss.mss() as sct:
        while True:
            if keyboard.is_pressed(HOTKEY):
                capture_5_offsets(sct, current_label)
                while keyboard.is_pressed(HOTKEY):
                    time.sleep(0.05)
            time.sleep(0.01)


if __name__ == "__main__":
    main()
