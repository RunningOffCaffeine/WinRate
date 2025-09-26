import os
import sys
import time
from PIL import Image
import mss
import keyboard
import pyautogui

# --- Configuration ---
SAVE_DIRECTORY = "dataset"
CAPTURE_SIZE = 128  # Capture a 128x128 pixel area
HOTKEY = "~"  # The key to press to capture an image

def get_limbus_window_region():
    """Finds the Limbus Company window and returns its region."""
    try:
        # We need pygetwindow for this part
        import pygetwindow as gw
        limbus_windows = gw.getWindowsWithTitle('LimbusCompany')
        if not limbus_windows:
            print("ERROR: Limbus Company window not found. Is the game running?")
            return None
        window = limbus_windows[0]
        # Return a dictionary formatted for mss
        return {"top": window.top, "left": window.left, "width": window.width, "height": window.height}
    except Exception as e:
        print(f"An error occurred while trying to find the game window: {e}")
        print("Please ensure pygetwindow is installed ('pip install pygetwindow').")
        return None

def capture_and_save(sct, region, label):
    """Captures the screen region around the mouse and saves it."""
    original_position = None # store original mouse position
    try:
        original_position = pyautogui.position()
        mouse_x, mouse_y = original_position

        # Define the capture box centered on the mouse
        box_half = CAPTURE_SIZE // 2
        capture_box = {
            "top": mouse_y - box_half,
            "left": mouse_x - box_half,
            "width": CAPTURE_SIZE,
            "height": CAPTURE_SIZE,
        }

        # move to corner to avoid cursor in capture
        pyautogui.moveTo(0, 0, duration=0)

        # wait a moment for the cursor to move
        time.sleep(0.05)
        
        # take the screenshot
        sct_img = sct.grab(capture_box)

        # Create the label directory if it doesn't exist
        label_dir = os.path.join(SAVE_DIRECTORY, label)
        os.makedirs(label_dir, exist_ok=True)

        # Find the next available file number
        file_num = 0
        while True:
            filename = os.path.join(label_dir, f"{label}_{file_num}.png")
            if not os.path.exists(filename):
                break
            file_num += 1

        # Grab the data and save it
        sct_img = sct.grab(capture_box)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.save(filename)
        print(f"Saved {filename}")

    except Exception as e:
        print(f"Error during capture: {e}")
    finally:
        # Move the mouse back to its original position
        if original_position:
            pyautogui.moveTo(original_position.x, original_position.y, duration=0)

def main():
    """Main function to run the data collector."""
    print("--- Limbus ML Data Collector ---")
    pyautogui.FAILSAFE = False
    
    # Check for pygetwindow before starting
    try:
        import pygetwindow
    except ImportError:
        print("Required package 'pygetwindow' not found.")
        print("Please install it by running: pip install pygetwindow")
        sys.exit(1)

    if not os.path.exists(SAVE_DIRECTORY):
        os.makedirs(SAVE_DIRECTORY)
        print(f"Created save directory: '{SAVE_DIRECTORY}'")

    current_label = input("Enter the label for the images you are about to capture (e.g., 'winrate', 'confirm'): ")
    if not current_label:
        print("Label cannot be empty. Exiting.")
        return

    print("\n-------------------------------------------------------------")
    print(f"OK. The current label is '{current_label}'.")
    print("Switch to the Limbus Company window.")
    print(f"Move your mouse over the element and press the '{HOTKEY}' key to capture.")
    print("Press CTRL+C in this terminal to stop.")
    print("-------------------------------------------------------------\n")
    
    # latch
    is_capturing = False

    with mss.mss() as sct:
        while True:
            try:
                # This checks for the hotkey press
                if keyboard.is_pressed(HOTKEY) and not is_capturing:
                    is_capturing = True # set latch
                    capture_and_save(sct, get_limbus_window_region(), current_label)
                    while keyboard.is_pressed(HOTKEY):
                        time.sleep(0.05) # wait for key release
                    is_capturing = False # reset latch
                time.sleep(0.01) # Small delay to prevent high CPU usage

            except KeyboardInterrupt:
                print("\nExiting data collector.")
                break
            except Exception as e:
                print(f"An unexpected error occurred in the main loop: {e}")
                break

if __name__ == "__main__":
    main()
