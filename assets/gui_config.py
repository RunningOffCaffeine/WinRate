# gui_config.py
"""
Live-tuning GUI for Limbus bot
──────────────────────────────
• Shows a dropdown of all template names.
• Slider adjusts that template’s threshold (0.10→1.00), with live numeric display.
• “Pick ROI” button lets you draw a rectangle on screen; the fractional ROI
  is written into TEMPLATE_SPEC[name][2].
• “Pause Bot” / “Quit” below.
• When Debug mode is ON, a table on the right shows each template’s
  last match-score and its threshold.
"""

# ── std-lib imports ───────────────────────────────────────────────────
import os
import threading
import time
import sys
import json
from collections import namedtuple


# ── auto-installer for third-party packages ───────────────────────────
def _require(pkg, import_as=None, pypi_name=None):
    import importlib
    import subprocess

    name = pypi_name or pkg
    try:
        return importlib.import_module(pkg if import_as is None else import_as)
    except ModuleNotFoundError:
        print(f"[setup] installing '{name}' …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", name])
        return importlib.import_module(pkg if import_as is None else import_as)


# ── pull in all non-stdlib deps ───────────────────────────────────────
if getattr(sys, "frozen", False):
    import cv2
    import numpy as np
    import pyautogui
    import keyboard
    import pygetwindow as gw
    import mss
    from PIL import Image, ImageTk
    import tkinter as tk
    from tkinter import ttk
else:
    cv2 = _require("cv2", pypi_name="opencv-python")
    np = _require("numpy")
    pyautogui = _require("pyautogui")
    keyboard = _require("keyboard")
    gw = _require("pygetwindow", import_as="pygetwindow")
    mss = _require("mss")
    _require("PIL", pypi_name="Pillow")
    from PIL import Image, ImageTk
    import tkinter as tk
    from tkinter import ttk


# ──────────────────────────────────────────────────────────────────────
class Tuner(tk.Tk):

    def __init__(
        self,
        live_spec,
        orig_spec,
        update_cb,
        pause_event,
        initial_delay_ms,
        initial_is_HDR,
        initial_debug,
        delay_cb,
        hdr_cb,
        debug_cb,
        debug_vals_fn,
        debug_pass_fn,
        debug_log_fn,
        text_skip_cb,
        initial_text_skip,
        default_spec,
        initial_lux_thread,
        initial_lux_EXP,
        initial_mirror_full_auto,
        lux_thread_cb,
        lux_EXP_cb,
        mirror_full_auto_cb,
    ):
        super().__init__(className="Limbus tuner")
        self.title("Limbus tuner")
        self.base_width = 500
        self.debug_extra = 450
        self.base_height = 620
        self.attributes("-topmost", True)

        self.initial_debug_state = initial_debug  # Store initial debug state

        w = self.base_width + (self.debug_extra if self.initial_debug_state else 0)
        self.geometry(f"{w}x{self.base_height}")
        self.minsize(self.base_width, self.base_height)

        self.spec = live_spec  # This is TEMPLATE_SPEC from winrate.py
        self.orig_spec = orig_spec  # For reset functionality
        self.update_cb = update_cb  # Callback to winrate.py to refresh templates
        self.pause_event = pause_event

        self.delay_cb = delay_cb
        self.hdr_cb = hdr_cb  # For GUI preview, bot matching is independent
        self.is_HDR_preview = initial_is_HDR  # For GUI template preview image selection
        self.debug_cb = debug_cb  # Callback to winrate.py's set_debug_mode

        self.debug_vals_fn = debug_vals_fn  # lambda: last_vals
        self.debug_pass_fn = debug_pass_fn  # lambda: last_pass
        self.debug_log_fn = debug_log_fn  # lambda: debug_log

        self.text_skip_cb = text_skip_cb
        self.default_spec = default_spec

        self.lux_thread_cb = lux_thread_cb
        self.lux_EXP_cb = lux_EXP_cb
        self.mirror_full_auto_cb = mirror_full_auto_cb

        # Tkinter variables for GUI elements
        self.var_delay = tk.IntVar(value=initial_delay_ms)
        self.var_hdr_preview = tk.BooleanVar(
            value=initial_is_HDR
        )  # For GUI preview checkbox
        self.var_debug = tk.BooleanVar(value=initial_debug)  # For Debug mode checkbox
        self.var_text_skip = tk.BooleanVar(value=initial_text_skip)
        self.var_lux_thread = tk.BooleanVar(value=initial_lux_thread)
        self.var_lux_EXP = tk.BooleanVar(value=initial_lux_EXP)
        self.var_mirror_full_auto = tk.BooleanVar(value=initial_mirror_full_auto)

        self.DEBUG_PANEL = None  # Placeholder for the debug panel frame
        self._last_log_len = 0  # For updating log console efficiently

        style = ttk.Style(self)
        style.configure(
            "Debug.Treeview", rowheight=24
        )  # Custom style for the scores table

        # --- Build GUI Layout ---
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        controls = ttk.Frame(container)  # Main controls on the left
        controls.pack(side="left", fill="both", expand=True)

        # Delay control
        df = ttk.Frame(controls)
        df.pack(fill="x", pady=2)
        ttk.Label(df, text="Delay (ms):").pack(side="left")
        ttk.Entry(df, width=5, textvariable=self.var_delay).pack(side="left", padx=4)
        ttk.Button(df, text="Apply", command=self._apply_delay).pack(side="left")

        # Checkboxes for modes and settings
        chk_frame = ttk.Frame(controls)
        chk_frame.pack(fill="x", pady=4)
        ttk.Checkbutton(
            chk_frame,
            text="HDR Preview",
            variable=self.var_hdr_preview,
            command=self._toggle_hdr_preview,
        ).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Skip Text",
            variable=self.var_text_skip,
            command=self._toggle_text_skip,
        ).grid(row=1, column=0, sticky="w", padx=2, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Debug mode",
            variable=self.var_debug,
            command=self._toggle_debug,
        ).grid(row=2, column=0, sticky="w", padx=2, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Mirror Full Auto",
            variable=self.var_mirror_full_auto,
            command=self._toggle_mirror_full_auto,
        ).grid(row=0, column=1, sticky="w", padx=20, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Thread Luxcavation",
            variable=self.var_lux_thread,
            command=self._toggle_thread_lux,
        ).grid(row=1, column=1, sticky="w", padx=20, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="EXP Luxcavation",
            variable=self.var_lux_EXP,
            command=self._toggle_exp_lux,
        ).grid(row=2, column=1, sticky="w", padx=20, pady=2)

        # Template selector dropdown
        # Ensure self.spec is not empty before trying to get the first key
        first_template_name = next(iter(self.spec)) if self.spec else ""
        self.var_name = tk.StringVar(value=first_template_name)
        ttk.OptionMenu(
            controls,
            self.var_name,
            self.var_name.get(),
            *self.spec.keys(),
            command=self._load_data_for_selected_template,
        ).pack(fill="x")

        # Threshold slider and entry
        sf = ttk.Frame(controls)
        sf.pack(fill="x", pady=4)
        initial_thr_val = 0.75  # Default threshold
        if first_template_name and first_template_name in self.spec:
            _, initial_thr_val, _ = self.spec[first_template_name]
        self.var_thr = tk.DoubleVar(value=initial_thr_val)
        self.scale = ttk.Scale(
            sf,
            from_=0.1,
            to=1.0,
            variable=self.var_thr,
            command=self._set_threshold_from_slider,
        )
        self.scale.pack(side="left", fill="x", expand=True)
        self.var_thr_entry = tk.StringVar(value=f"{initial_thr_val:.3f}")
        entry = ttk.Entry(sf, width=6, textvariable=self.var_thr_entry)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", self._set_threshold_from_entry)

        self.img_label = tk.Label(sf)  # For template preview image
        self.img_label.pack(side="right", padx=4)

        # ROI display and picker button
        self.lab_roi = ttk.Label(controls, text="ROI : None")
        self.lab_roi.pack(pady=4)
        ttk.Button(controls, text="Pick ROI", command=self._pick_roi_on_screen).pack()

        # Bottom buttons: Reset, Pause, Quit, Save
        bottom_buttons_frame = ttk.Frame(controls)
        bottom_buttons_frame.pack(side="bottom", fill="x", pady=(8, 4))
        reset_buttons_bar = ttk.Frame(bottom_buttons_frame)
        reset_buttons_bar.pack(fill="x", pady=(0, 4))  # Corrected pady
        ttk.Button(
            reset_buttons_bar, text="Reset thr", command=self._reset_threshold
        ).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(reset_buttons_bar, text="Reset ROI", command=self._reset_roi).pack(
            side="left", expand=True, fill="x", padx=(2, 2)
        )

        self.btn_pause = tk.Button(
            bottom_buttons_frame,
            text="Pause Bot",
            bg="green",
            fg="white",
            command=self._toggle_bot_pause_state,
        )
        self.btn_pause.pack(fill="x", pady=(0, 6))
        tk.Button(
            bottom_buttons_frame,
            text="Quit",
            bg="red",
            fg="white",
            command=self._quit_tuner,
        ).pack(fill="x")
        ttk.Button(
            bottom_buttons_frame, text="Save Config", command=self._save_config_to_json
        ).pack(fill="x", pady=(4, 0))

        # Build the debug panel (initially hidden or shown based on initial_debug_state)
        self._build_debug_panel(container)

        # Initial load of data for the selected template (threshold, ROI, preview image)
        if first_template_name:  # Ensure there's a template selected
            self._load_data_for_selected_template()

    def _build_debug_panel(self, parent_container):
        """Creates the debug panel frame and its contents (scores table, log console)."""
        self.DEBUG_PANEL = ttk.Frame(parent_container, relief="sunken", borderwidth=0.5)
        # Grid configuration for the debug panel itself
        self.DEBUG_PANEL.columnconfigure(0, weight=1)  # Main content column
        self.DEBUG_PANEL.rowconfigure(
            1, weight=6
        )  # Scores table row (takes more space)
        self.DEBUG_PANEL.rowconfigure(3, weight=4)  # Log console row

        # Scores Table Header
        lbl_scores = ttk.Label(
            self.DEBUG_PANEL, text="Debug Scores", font=("TkDefaultFont", 10, "bold")
        )
        lbl_scores.grid(row=0, column=0, sticky="n", pady=(4, 2))

        # Scores Table (Treeview)
        cols = ("name", "value", "threshold", "last_pass")
        self.tree = ttk.Treeview(
            self.DEBUG_PANEL,
            columns=cols,
            show="headings",
            height=15,
            style="Debug.Treeview",
        )
        for col_id, heading_text, col_width in [
            ("name", "Template", 160),
            ("value", "Score", 80),
            ("threshold", "Thresh", 80),
            ("last_pass", "Last Pass", 80),
        ]:
            self.tree.heading(col_id, text=heading_text)
            self.tree.column(
                col_id, width=col_width, anchor="w" if col_id == "name" else "e"
            )
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))

        # Scrollbar for Scores Table
        self.score_vsb = ttk.Scrollbar(
            self.DEBUG_PANEL, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self.score_vsb.set)
        self.score_vsb.grid(
            row=1, column=1, sticky="ns", pady=(0, 4)
        )  # Place next to tree
        self.score_vsb.grid_remove()  # Initially hidden, shown if content overflows

        # Log Console Header
        lbl_log = ttk.Label(
            self.DEBUG_PANEL, text="Log", font=("TkDefaultFont", 10, "bold")
        )
        lbl_log.grid(row=2, column=0, sticky="n", pady=(4, 2))

        # Log Console (Text widget for wrapping)
        self.log_console = tk.Text(
            self.DEBUG_PANEL,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=8,
            borderwidth=0.5,
            relief="solid",  # Basic styling
        )
        self.log_console.grid(row=3, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))

        # Scrollbar for Log Console
        self.log_vsb_console = ttk.Scrollbar(
            self.DEBUG_PANEL, orient="vertical", command=self.log_console.yview
        )  # Renamed to avoid conflict
        self.log_console.configure(yscrollcommand=self.log_vsb_console.set)
        self.log_vsb_console.grid(
            row=3, column=1, sticky="ns", pady=(0, 4)
        )  # Place next to log console
        self.log_vsb_console.grid_remove()  # Initially hidden

    def _refresh_debug(self):
        """Periodically updates the scores table and log console in the debug panel."""
        # Diagnostic print to console (can be commented out)
        # print(f"GUI_Config: _refresh_debug running at {time.time()}. var_debug: {self.var_debug.get()}")

        if not self.var_debug.get():  # If debug mode is turned off, stop refreshing.
            return

        # --- Update Scores Table ---
        for iid in self.tree.get_children():  # Clear old entries from the tree
            self.tree.delete(iid)

        scores_data = self.debug_vals_fn()  # Calls lambda: last_vals from winrate.py
        passes_data = self.debug_pass_fn()  # Calls lambda: last_pass from winrate.py

        # Diagnostic print (can be commented out)
        # print(f"GUI_Config: Fetched scores: {scores_data}, Fetched passes: {passes_data}")
        # print(f"GUI_Config: Current self.spec keys: {list(self.spec.keys())}")

        if not self.spec:  # If self.spec (TEMPLATE_SPEC) is somehow empty
            # print("GUI_Config: self.spec is empty, no scores to display in table.")
            self.after(
                50, self._refresh_debug
            )  # Still reschedule to keep the loop alive
            return

        # Populate the tree with current scores and thresholds
        for template_name, spec_details in self.spec.items():
            if not isinstance(spec_details, tuple) or len(spec_details) < 2:
                # print(f"GUI_Config: Invalid spec_details for {template_name}: {spec_details}")
                continue  # Skip malformed spec item

            current_threshold = spec_details[1]  # Assuming (base, threshold, roi)

            current_score = scores_data.get(template_name, 0.0)
            last_pass_score = passes_data.get(template_name, 0.0)

            self.tree.insert(
                "",
                "end",
                values=(
                    template_name,
                    f"{current_score:.3f}",
                    f"{current_threshold:.3f}",
                    f"{last_pass_score:.3f}",
                ),
            )

        # Auto-show/hide scrollbar for scores table
        total_rows = len(self.tree.get_children())
        visible_rows = int(self.tree["height"])  # Height is in number of rows
        if total_rows > visible_rows:
            self.score_vsb.grid()
        else:
            self.score_vsb.grid_remove()

        # --- Update Log Console ---
        all_log_messages = list(self.debug_log_fn())  # Get all log messages from bot
        new_log_messages = all_log_messages[
            self._last_log_len :
        ]  # Get only new messages

        if new_log_messages:  # If there are new messages
            self.log_console.config(state=tk.NORMAL)  # Enable editing to insert
            for msg in new_log_messages:
                self.log_console.insert(
                    tk.END, msg + "\n"
                )  # Add message with a newline
            self.log_console.config(state=tk.DISABLED)  # Disable editing
            self.log_console.see(tk.END)  # Scroll to the end to show latest messages

        self._last_log_len = len(all_log_messages)  # Update count of displayed messages

        # Auto-show/hide scrollbar for log console
        # This checks if content height exceeds widget height; an approximation for Text widget
        num_lines_in_console = int(self.log_console.index("end-1c").split(".")[0])
        visible_lines_in_console = self.log_console.cget("height")
        if num_lines_in_console > visible_lines_in_console:
            self.log_vsb_console.grid()
        else:
            self.log_vsb_console.grid_remove()

        # Schedule this method to run again after 50ms
        self.after(50, self._refresh_debug)

    def _apply_delay(self):
        """Applies the delay value entered by the user."""
        ms = self.var_delay.get()
        if ms < 10:
            ms = 10
            self.var_delay.set(ms)  # Enforce minimum delay
        self.delay_cb(ms)  # Call the callback in winrate.py

    def _toggle_hdr_preview(self):
        """Toggles the HDR preview mode for template images in the GUI."""
        self.is_HDR_preview = self.var_hdr_preview.get()
        # self.hdr_cb(self.is_HDR_preview) # Bot matching is independent of this GUI flag.
        # This callback might be removed if it only affected bot template loading.
        self._log_to_console(f"HDR Preview mode set to {self.is_HDR_preview}")
        self._load_data_for_selected_template()  # Reload preview image

    def _toggle_debug(self):
        """Toggles the debug mode and visibility of the debug panel."""
        is_debug_enabled = self.var_debug.get()
        self.debug_cb(is_debug_enabled)  # Inform the bot (winrate.py)

        if is_debug_enabled:
            self.DEBUG_PANEL.pack(
                side="right", fill="both", expand=True, padx=(8, 0), pady=8
            )
            current_height = self.winfo_height()
            self.geometry(
                f"{self.base_width + self.debug_extra}x{max(current_height, self.base_height)}"
            )
            self._refresh_debug()  # Start the refresh loop for debug panel
        else:
            self.DEBUG_PANEL.pack_forget()
            current_height = self.winfo_height()
            self.geometry(f"{self.base_width}x{max(current_height, self.base_height)}")
            # The _refresh_debug loop will stop itself as self.var_debug.get() will be false.

    def _toggle_text_skip(self):
        """Toggles the text skip mode."""
        is_text_skip_enabled = self.var_text_skip.get()
        self.text_skip_cb(is_text_skip_enabled)  # Inform the bot

    def _toggle_thread_lux(self):
        """Toggles Thread Luxcavation mode, ensuring exclusivity with other modes."""
        is_thread_lux_enabled = self.var_lux_thread.get()
        if is_thread_lux_enabled:  # If turning ON Thread Lux
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)
        self.lux_thread_cb(is_thread_lux_enabled)  # Inform the bot

    def _toggle_exp_lux(self):
        """Toggles EXP Luxcavation mode, ensuring exclusivity."""
        is_exp_lux_enabled = self.var_lux_EXP.get()
        if is_exp_lux_enabled:  # If turning ON EXP Lux
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)
        self.lux_EXP_cb(is_exp_lux_enabled)  # Inform the bot

    def _toggle_mirror_full_auto(self):
        """Toggles Mirror Dungeon Full Auto mode, ensuring exclusivity."""
        is_mirror_auto_enabled = self.var_mirror_full_auto.get()
        if is_mirror_auto_enabled:  # If turning ON Mirror Full Auto
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)
        self.mirror_full_auto_cb(is_mirror_auto_enabled)  # Inform the bot

    PREVIEW_SIZE = (128, 128)  # Standard size for template preview images

    def _load_data_for_selected_template(self, *_args):  # Renamed for clarity
        """Loads and displays the threshold, ROI, and preview image for the currently selected template."""
        current_template_name = self.var_name.get()
        spec_item = self.spec.get(current_template_name)  # Get data from live spec

        if (
            not spec_item
        ):  # If template name not found in spec (should not happen if list is synced)
            self._log_to_console(
                f"Error: No spec found for template '{current_template_name}'"
            )
            self.img_label.config(image="", text="Error")
            return

        base_filename, current_threshold, current_roi = spec_item
        self.var_thr.set(current_threshold)  # Update slider
        self.var_thr_entry.set(f"{current_threshold:.3f}")  # Update entry box
        self.lab_roi.config(
            text=f"ROI : {current_roi if current_roi else 'None'}"
        )  # Update ROI label

        # --- Load and display template preview image ---
        # Preview image selection is based on self.is_HDR_preview (GUI preview flag)
        # It tries the preferred suffix (HDR/SDR based on flag), then the other, then plain .png
        preview_suffix_order = [
            f" {suffix_type}.png"
            for suffix_type in (
                ("HDR", "SDR") if self.is_HDR_preview else ("SDR", "HDR")
            )
        ]
        preview_suffix_order.append(".png")  # Fallback to no suffix

        folder = os.path.dirname(
            __file__
        )  # Assumes templates are in the same dir as this script
        img_path_to_load = None

        for suffix in preview_suffix_order:
            candidate_path = os.path.join(
                folder, base_filename + suffix.strip()
            )  # Strip leading space for .png
            if os.path.isfile(candidate_path):
                img_path_to_load = candidate_path
                break

        if not img_path_to_load:  # If no preview image file found
            self.img_label.config(image="", text="No preview")
            return

        try:
            raw_image = Image.open(img_path_to_load)
            raw_image.thumbnail(
                self.PREVIEW_SIZE, Image.Resampling.LANCZOS
            )  # Resize for preview

            # Create a transparent background for centered pasting
            bg_image = Image.new("RGBA", self.PREVIEW_SIZE, (0, 0, 0, 0))
            x_offset = (self.PREVIEW_SIZE[0] - raw_image.width) // 2
            y_offset = (self.PREVIEW_SIZE[1] - raw_image.height) // 2

            # Use alpha mask if image has one for proper transparency
            alpha_mask = raw_image.split()[3] if raw_image.mode == "RGBA" else None
            bg_image.paste(raw_image, (x_offset, y_offset), mask=alpha_mask)

            self._photo_image_preview = ImageTk.PhotoImage(
                bg_image
            )  # Store reference to avoid GC
            self.img_label.config(image=self._photo_image_preview, text="")
        except Exception as e:
            self.img_label.config(image="", text="Preview Error")
            self._log_to_console(f"Error loading preview {img_path_to_load}: {e}")

    def _set_threshold_from_slider(self, *_args):
        """Updates the threshold for the selected template when the slider is moved."""
        template_name = self.var_name.get()
        if template_name not in self.spec:
            return  # Should not happen

        base_filename, _, current_roi = self.spec[template_name]
        new_threshold = round(self.var_thr.get(), 3)  # Get value from slider, round it

        self.spec[template_name] = (
            base_filename,
            new_threshold,
            current_roi,
        )  # Update live spec
        self.var_thr_entry.set(f"{new_threshold:.3f}")  # Sync entry box
        self.update_cb()  # Notify bot (winrate.py) to refresh its templates/thresholds

    def _set_threshold_from_entry(self, _event):
        """Updates the threshold when a value is entered in the entry box and Enter is pressed."""
        template_name = self.var_name.get()
        if template_name not in self.spec:
            return

        base_filename, _, current_roi = self.spec[template_name]
        try:
            entered_value = float(self.var_thr_entry.get())
        except ValueError:  # If invalid float, revert entry to current slider value
            current_slider_val = round(self.var_thr.get(), 3)
            self.var_thr_entry.set(f"{current_slider_val:.3f}")
            return

        clamped_value = max(0.1, min(1.0, entered_value))  # Clamp value to [0.1, 1.0]

        self.var_thr.set(clamped_value)  # Update slider to reflect clamped value
        self.spec[template_name] = (
            base_filename,
            clamped_value,
            current_roi,
        )  # Update live spec
        self.update_cb()  # Notify bot
        self.var_thr_entry.set(
            f"{clamped_value:.3f}"
        )  # Ensure entry box shows clamped/rounded value
        self._log_to_console(
            f"Set threshold for {template_name} to {clamped_value:.3f}"
        )

    def _reset_threshold(self):
        """Resets the threshold of the selected template to its default value."""
        template_name = self.var_name.get()
        if template_name not in self.default_spec or template_name not in self.spec:
            return

        base_filename, default_threshold, _ = self.default_spec[template_name]
        _, _, current_roi = self.spec[template_name]  # Keep the current ROI

        self.spec[template_name] = (
            base_filename,
            default_threshold,
            current_roi,
        )  # Update live spec
        self.var_thr.set(default_threshold)  # Update slider
        self.var_thr_entry.set(f"{default_threshold:.3f}")  # Update entry box
        self.update_cb()  # Notify bot
        self._log_to_console(
            f"Reset threshold for {template_name} to {default_threshold:.3f}"
        )

    def _reset_roi(self):
        """Resets the ROI of the selected template to its default value."""
        template_name = self.var_name.get()
        if template_name not in self.default_spec or template_name not in self.spec:
            return

        base_filename, _, default_roi = self.default_spec[template_name]
        _, current_threshold, _ = self.spec[template_name]  # Keep current threshold

        self.spec[template_name] = (
            base_filename,
            current_threshold,
            default_roi,
        )  # Update live spec
        self.lab_roi.config(
            text=f"ROI : {default_roi if default_roi else 'None'}"
        )  # Update ROI label
        self.update_cb()  # Notify bot
        self._log_to_console(
            f"Reset ROI for {template_name} to {default_roi if default_roi else 'None'}"
        )

    def _save_config_to_json(self):
        """Saves the current template configurations (thresholds, ROIs) to a JSON file."""
        config_data = {}
        for name, (base, thresh, roi) in self.spec.items():  # Iterate over live spec
            config_data[name] = {
                "base": base,
                "threshold": round(thresh, 4),
                "roi": list(roi) if roi else None,
            }

        file_path = os.path.join(os.path.dirname(__file__), "saved_user_vars.json")
        try:
            with open(file_path, "w") as fp:
                json.dump(config_data, fp, indent=2)
            self._log_to_console(f"Config saved to {file_path}")
        except Exception as e:
            self._log_to_console(f"Error saving config: {e}")

    def _toggle_bot_pause_state(self):
        """Toggles the bot's pause/resume state."""
        if not self.pause_event.is_set():  # If bot is running, pause it
            self.pause_event.set()
            self.btn_pause.config(text="Resume Bot", bg="red")
            log_message = "Bot paused"
        else:  # If bot is paused, resume it
            self.pause_event.clear()
            self.btn_pause.config(text="Pause Bot", bg="green")
            log_message = "Bot resumed"
        self._log_to_console(log_message)

    def _quit_tuner(self):
        """Closes the tuner GUI and exits the application."""
        self._log_to_console("Tuner quitting...")
        # self.destroy() # Attempt graceful Tkinter exit first
        os._exit(0)  # Force exit if destroy() is slow or hangs

    def _pick_roi_on_screen(self):  # Renamed for clarity
        """Allows the user to draw a rectangle on screen to define an ROI."""
        self.withdraw()  # Hide main GUI window
        time.sleep(0.15)  # Brief pause for window to hide

        try:
            # PyAutoGUI is used here for screen dimensions; ensure it's available.
            # If PyAutoGUI is problematic, mss or other screen info methods could be alternatives.
            screen_width, screen_height = pyautogui.size()

            # Create a transparent, fullscreen overlay window for drawing
            overlay_window = tk.Toplevel(self)
            overlay_window.attributes("-fullscreen", True)
            overlay_window.attributes("-topmost", True)
            overlay_window.attributes("-alpha", 0.25)  # Make window semi-transparent
            overlay_window.configure(bg="black")  # Background for transparent effect

            canvas = tk.Canvas(
                overlay_window, cursor="crosshair", bg="black", highlightthickness=0
            )
            canvas.pack(fill="both", expand=True)

            # Dictionary to store rectangle coordinates during drawing
            rect_draw_info = {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "id": None}

            def on_mouse_press(event):
                rect_draw_info["x0"], rect_draw_info["y0"] = event.x, event.y
                if rect_draw_info["id"]:
                    canvas.delete(rect_draw_info["id"])  # Delete old rect if any
                # Create new rectangle (initially a point)
                rect_draw_info["id"] = canvas.create_rectangle(
                    event.x, event.y, event.x, event.y, outline="red", width=2
                )

            def on_mouse_drag(event):
                if rect_draw_info["id"]:  # If drawing has started
                    # Update rectangle's bottom-right corner as mouse moves
                    canvas.coords(
                        rect_draw_info["id"],
                        rect_draw_info["x0"],
                        rect_draw_info["y0"],
                        event.x,
                        event.y,
                    )
                    rect_draw_info["x1"], rect_draw_info["y1"] = (
                        event.x,
                        event.y,
                    )  # Store current end point

            def on_mouse_release(event):
                if not rect_draw_info["id"]:
                    return  # No rectangle drawn

                # Ensure x0 < x1 and y0 < y1 for correct fractional calculation
                final_x0 = min(rect_draw_info["x0"], rect_draw_info["x1"])
                final_y0 = min(rect_draw_info["y0"], rect_draw_info["y1"])
                final_x1 = max(rect_draw_info["x0"], rect_draw_info["x1"])
                final_y1 = max(rect_draw_info["y0"], rect_draw_info["y1"])

                # Prevent zero-size ROI if points are the same
                if final_x0 == final_x1 or final_y0 == final_y1:
                    self._log_to_console("ROI selection cancelled or zero size.")
                else:
                    # Convert absolute pixel coordinates to fractional values
                    frac_x = final_x0 / screen_width
                    frac_y = final_y0 / screen_height
                    frac_w = (final_x1 - final_x0) / screen_width
                    frac_h = (final_y1 - final_y0) / screen_height

                    selected_template_name = self.var_name.get()
                    base_filename, current_threshold, _ = self.spec[
                        selected_template_name
                    ]
                    new_roi_tuple = tuple(
                        round(v, 3) for v in (frac_x, frac_y, frac_w, frac_h)
                    )

                    self.spec[selected_template_name] = (
                        base_filename,
                        current_threshold,
                        new_roi_tuple,
                    )  # Update live spec

                    self._log_to_console(
                        f"Set ROI for {selected_template_name} to {new_roi_tuple}"
                    )
                    self.lab_roi.config(
                        text=f"ROI : {new_roi_tuple}"
                    )  # Update ROI label in GUI
                    self.update_cb()  # Notify bot of ROI change

                overlay_window.destroy()  # Close the drawing overlay
                self.deiconify()  # Show main GUI window again

            # Bind mouse events to the canvas
            canvas.bind("<ButtonPress-1>", on_mouse_press)
            canvas.bind("<B1-Motion>", on_mouse_drag)
            canvas.bind("<ButtonRelease-1>", on_mouse_release)
        except Exception as e:  # Catch any errors during ROI picking
            self._log_to_console(f"Error in ROI snipping: {e}")
            if "overlay_window" in locals() and overlay_window.winfo_exists():
                overlay_window.destroy()
            self.deiconify()  # Ensure main window is shown even if error occurs

    def _log_to_console(self, message: str):
        """Helper function to append messages to the GUI's log console."""
        if hasattr(self, "log_console") and self.log_console:
            self.log_console.config(state=tk.NORMAL)
            self.log_console.insert(tk.END, message + "\n")
            self.log_console.config(state=tk.DISABLED)
            self.log_console.see(tk.END)
        else:  # Fallback if console not ready (e.g. during early init)
            print(f"GUI_LOG: {message}")


# Module-level holder for the Tuner instance
_tuner_instance: "Tuner | None" = None


def get_tuner() -> "Tuner | None":
    """Returns the running Tuner instance, or None if not initialized."""
    return _tuner_instance


def launch_gui(
    template_spec,  # Live spec dict from bot
    refresh_fn,  # Bot's callback to reload templates/thresholds
    pause_event,  # Shared threading.Event for pausing
    # Initial values for GUI controls
    initial_delay_ms,
    initial_is_HDR,
    initial_debug,
    initial_text_skip,
    # Callbacks from GUI to bot's setter functions
    delay_cb,
    hdr_cb,
    debug_cb,
    text_skip_cb,
    # Functions for GUI to get data from bot for display
    debug_vals_fn,
    debug_pass_fn,
    debug_log_fn,
    default_spec,  # Bot's original template spec for resets
    # Initial states for mode toggles
    initial_lux_thread,
    initial_lux_EXP,
    initial_mirror_full_auto,
    # Callbacks for mode toggles
    lux_thread_cb,
    lux_EXP_cb,
    mirror_full_auto_cb,
):
    """
    Launches the Tuner GUI in a separate thread.
    Args:
        template_spec: The live dictionary of template specifications used by the bot.
        refresh_fn: Callback function in the bot to be called when GUI updates specs.
        *// Other args are initial states or callbacks for various GUI interactions.
    Returns:
        threading.Thread: The thread object running the GUI.
    """
    import copy  # Ensure copy is available

    orig_spec_for_gui_reset = copy.deepcopy(template_spec)

    def _run_gui_thread():
        global _tuner_instance
        _tuner_instance = Tuner(
            live_spec=template_spec,
            orig_spec=orig_spec_for_gui_reset,
            update_cb=refresh_fn,
            pause_event=pause_event,
            initial_delay_ms=initial_delay_ms,
            initial_is_HDR=initial_is_HDR,
            initial_debug=initial_debug,  # This is the crucial initial state
            # Callbacks to bot
            delay_cb=delay_cb,
            hdr_cb=hdr_cb,
            debug_cb=debug_cb,
            # Data functions from bot
            debug_vals_fn=debug_vals_fn,
            debug_pass_fn=debug_pass_fn,
            debug_log_fn=debug_log_fn,
            # Text skip
            text_skip_cb=text_skip_cb,
            initial_text_skip=initial_text_skip,
            default_spec=default_spec,
            # Lux/Mirror initial states and callbacks
            initial_lux_thread=initial_lux_thread,
            initial_lux_EXP=initial_lux_EXP,
            initial_mirror_full_auto=initial_mirror_full_auto,
            lux_thread_cb=lux_thread_cb,
            lux_EXP_cb=lux_EXP_cb,
            mirror_full_auto_cb=mirror_full_auto_cb,
        )

        # After Tuner is initialized, explicitly show/hide debug panel based on its initial state
        # This ensures _refresh_debug starts if initial_debug was true.
        if _tuner_instance.initial_debug_state:  # Use the stored initial state
            _tuner_instance.DEBUG_PANEL.pack(
                side="right", fill="both", expand=True, padx=(8, 0), pady=8
            )
            _tuner_instance._refresh_debug()  # Start the refresh loop
        else:
            _tuner_instance.DEBUG_PANEL.pack_forget()

        _tuner_instance.mainloop()  # Start Tkinter event loop for the GUI

    gui_thread = threading.Thread(target=_run_gui_thread, daemon=True)
    gui_thread.start()
    return gui_thread
