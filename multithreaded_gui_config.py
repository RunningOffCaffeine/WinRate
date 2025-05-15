# multithreaded_gui_config.py
"""
Live-tuning GUI for Limbus bot (compatible with multithreaded winrate.py)
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
import threading  # Not strictly used in this file but often associated with GUI apps
import time  # For _pick_roi_on_screen delay
import sys  # Not strictly used but good practice for GUI apps
import json

# from collections import namedtuple # Not needed here as Tmpl is defined in winrate.py

# ── GUI library imports ───────────────────────────────────────────────
# Assuming these are installed in the environment.
# If using _require, it would be in the main winrate.py script.
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk
import pyautogui  # For ROI picker screen dimensions


# ──────────────────────────────────────────────────────────────────────
class Tuner(tk.Tk):
    def __init__(
        self,
        live_spec,  # The TEMPLATE_SPEC dict from winrate.py (mutable, shared)
        orig_spec_for_reset,  # A deepcopy of the original TEMPLATE_SPEC for reset functionality
        update_cb_to_bot,  # Callback to winrate.py to _refresh_templates_from_gui
        pause_event_shared,  # Shared threading.Event for pausing the bot
        # Initial values for GUI controls, sourced from winrate.py's global state
        initial_delay_ms,
        initial_is_HDR_for_preview,  # For GUI template preview image selection
        initial_debug_state,
        initial_text_skip_state,
        initial_lux_thread_state,
        initial_lux_EXP_state,
        initial_mirror_full_auto_state,
        # Callbacks from GUI to winrate.py's setter functions (e.g., set_delay_ms_config)
        delay_cb,
        hdr_preview_cb,  # Callback for when GUI's HDR preview toggle changes
        debug_cb,
        text_skip_cb,
        lux_thread_cb,
        lux_EXP_cb,
        mirror_full_auto_cb,
        # Functions for GUI to get data from winrate.py for display in debug panel
        debug_vals_fn,  # Typically lambda: last_vals from winrate.py
        debug_pass_fn,  # Typically lambda: last_pass from winrate.py
        debug_log_fn,  # Typically lambda: debug_log from winrate.py
    ):
        super().__init__(className="Limbus tuner")
        self.title("Limbus tuner")
        self.base_width = 500  # Base width of the GUI window
        self.debug_extra = 450  # Extra width added when debug panel is shown
        self.base_height = 620  # Base height of the GUI window
        self.attributes("-topmost", True)  # Keep GUI window on top of others

        self.initial_debug_state = (
            initial_debug_state  # Store for setting initial panel visibility
        )

        # Calculate initial window width based on debug state
        current_width = self.base_width + (
            self.debug_extra if self.initial_debug_state else 0
        )
        self.geometry(f"{current_width}x{self.base_height}")  # Set initial size
        self.minsize(self.base_width, self.base_height)  # Set minimum resizable size

        # Store references to shared objects and callbacks from the main bot script
        self.spec = live_spec
        self.orig_spec = orig_spec_for_reset
        self.update_cb = update_cb_to_bot
        self.pause_event = pause_event_shared

        self.delay_cb = delay_cb
        self.hdr_preview_cb = hdr_preview_cb
        self.is_HDR_preview_active = (
            initial_is_HDR_for_preview  # Internal state for GUI's preview choice
        )
        self.debug_cb = debug_cb

        self.debug_vals_fn = debug_vals_fn
        self.debug_pass_fn = debug_pass_fn
        self.debug_log_fn = debug_log_fn

        self.text_skip_cb = text_skip_cb

        self.lux_thread_cb = lux_thread_cb
        self.lux_EXP_cb = lux_EXP_cb
        self.mirror_full_auto_cb = mirror_full_auto_cb

        # Tkinter variables bound to GUI controls, initialized with states from winrate.py
        self.var_delay = tk.IntVar(value=initial_delay_ms)
        self.var_hdr_preview = tk.BooleanVar(value=initial_is_HDR_for_preview)
        self.var_debug = tk.BooleanVar(value=initial_debug_state)
        self.var_text_skip = tk.BooleanVar(value=initial_text_skip_state)
        self.var_lux_thread = tk.BooleanVar(value=initial_lux_thread_state)
        self.var_lux_EXP = tk.BooleanVar(value=initial_lux_EXP_state)
        self.var_mirror_full_auto = tk.BooleanVar(value=initial_mirror_full_auto_state)

        self.DEBUG_PANEL = None  # Frame for the debug panel, created later
        self._last_log_len = 0  # Tracks displayed log lines for efficient updates

        # Apply custom styling to the Treeview widget used for scores
        style = ttk.Style(self)
        style.configure("Debug.Treeview", rowheight=24)

        # --- Build GUI Layout ---
        # Main container frame
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        # Left panel for main controls
        controls = ttk.Frame(container)
        controls.pack(side="left", fill="both", expand=True)

        # Delay setting UI
        df = ttk.Frame(controls)
        df.pack(fill="x", pady=2)
        ttk.Label(df, text="Delay (ms):").pack(side="left")
        ttk.Entry(df, width=5, textvariable=self.var_delay).pack(side="left", padx=4)
        ttk.Button(df, text="Apply", command=self._apply_delay_setting).pack(
            side="left"
        )

        # Checkboxes for various modes and settings
        chk_frame = ttk.Frame(controls)
        chk_frame.pack(fill="x", pady=4)
        ttk.Checkbutton(
            chk_frame,
            text="HDR Preview",
            variable=self.var_hdr_preview,
            command=self._toggle_hdr_preview_mode,
        ).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Skip Text",
            variable=self.var_text_skip,
            command=self._toggle_text_skip_mode,
        ).grid(row=1, column=0, sticky="w", padx=2, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Debug mode",
            variable=self.var_debug,
            command=self._toggle_debug_panel_visibility,
        ).grid(row=2, column=0, sticky="w", padx=2, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Mirror Full Auto",
            variable=self.var_mirror_full_auto,
            command=self._toggle_mirror_full_auto_mode,
        ).grid(row=0, column=1, sticky="w", padx=20, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="Thread Lux",
            variable=self.var_lux_thread,
            command=self._toggle_thread_lux_mode,
        ).grid(row=1, column=1, sticky="w", padx=20, pady=2)
        ttk.Checkbutton(
            chk_frame,
            text="EXP Lux",
            variable=self.var_lux_EXP,
            command=self._toggle_exp_lux_mode,
        ).grid(row=2, column=1, sticky="w", padx=20, pady=2)

        # Dropdown menu to select a template for editing
        first_template_name = (
            next(iter(self.spec)) if self.spec else ""
        )  # Get first key if spec is not empty
        self.var_name = tk.StringVar(value=first_template_name)
        ttk.OptionMenu(
            controls,
            self.var_name,
            self.var_name.get(),
            *self.spec.keys(),
            command=self._load_data_for_selected_template,
        ).pack(fill="x")

        # UI for threshold adjustment (slider and entry box)
        sf = ttk.Frame(controls)
        sf.pack(fill="x", pady=4)
        initial_thr_val = 0.75  # Default threshold if template not found initially
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

        self.img_label = tk.Label(sf)  # Displays template preview image
        self.img_label.pack(side="right", padx=4)

        # UI for ROI display and picking
        self.lab_roi = ttk.Label(controls, text="ROI : None")
        self.lab_roi.pack(pady=4)
        ttk.Button(controls, text="Pick ROI", command=self._pick_roi_on_screen).pack()

        # Bottom buttons section (Reset, Pause/Resume, Quit, Save)
        bottom_buttons_frame = ttk.Frame(controls)
        bottom_buttons_frame.pack(side="bottom", fill="x", pady=(8, 4))
        reset_buttons_bar = ttk.Frame(bottom_buttons_frame)
        reset_buttons_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(
            reset_buttons_bar, text="Reset thr", command=self._reset_selected_threshold
        ).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(
            reset_buttons_bar, text="Reset ROI", command=self._reset_selected_roi
        ).pack(side="left", expand=True, fill="x", padx=(2, 2))

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
            command=self._quit_tuner_application,
        ).pack(fill="x")
        ttk.Button(
            bottom_buttons_frame,
            text="Save Config",
            command=self._save_current_config_to_json,
        ).pack(fill="x", pady=(4, 0))

        # Create the debug panel (widgets are built here)
        self._build_debug_panel_widgets(container)

        # Load initial data for the first selected template (if any)
        if first_template_name:
            self._load_data_for_selected_template()

    def _build_debug_panel_widgets(self, parent_container):
        """Creates the widgets for the debug panel (scores table and log console)."""
        self.DEBUG_PANEL = ttk.Frame(parent_container, relief="sunken", borderwidth=0.5)
        # Grid layout for the debug panel itself
        self.DEBUG_PANEL.columnconfigure(0, weight=1)
        self.DEBUG_PANEL.rowconfigure(1, weight=6)
        self.DEBUG_PANEL.rowconfigure(3, weight=4)

        # Scores Table
        lbl_scores = ttk.Label(
            self.DEBUG_PANEL, text="Debug Scores", font=("TkDefaultFont", 10, "bold")
        )
        lbl_scores.grid(row=0, column=0, sticky="n", pady=(4, 2))
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
        self.score_vsb = ttk.Scrollbar(
            self.DEBUG_PANEL, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self.score_vsb.set)
        self.score_vsb.grid(row=1, column=1, sticky="ns", pady=(0, 4))
        self.score_vsb.grid_remove()

        # Log Console
        lbl_log = ttk.Label(
            self.DEBUG_PANEL, text="Log", font=("TkDefaultFont", 10, "bold")
        )
        lbl_log.grid(row=2, column=0, sticky="n", pady=(4, 2))
        self.log_console = tk.Text(
            self.DEBUG_PANEL,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=8,
            borderwidth=0.5,
            relief="solid",
        )
        self.log_console.grid(row=3, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))
        self.log_vsb_console = ttk.Scrollbar(
            self.DEBUG_PANEL, orient="vertical", command=self.log_console.yview
        )
        self.log_console.configure(yscrollcommand=self.log_vsb_console.set)
        self.log_vsb_console.grid(row=3, column=1, sticky="ns", pady=(0, 4))
        self.log_vsb_console.grid_remove()

    def _refresh_debug_panel_data(self):
        """Periodically updates the scores table and log console in the debug panel."""
        if not self.var_debug.get():
            return  # Stop refreshing if debug mode is off

        # Update Scores Table
        for iid in self.tree.get_children():
            self.tree.delete(iid)  # Clear previous entries
        scores_data = self.debug_vals_fn()
        passes_data = self.debug_pass_fn()  # Fetch current data from bot
        if not self.spec:
            self.after(50, self._refresh_debug_panel_data)
            return  # Reschedule if spec is empty

        for template_name, spec_details in self.spec.items():
            if not isinstance(spec_details, tuple) or len(spec_details) < 2:
                continue  # Skip malformed entries
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

        # Manage scrollbar visibility for scores table
        total_rows = len(self.tree.get_children())
        visible_rows = int(self.tree["height"])
        if total_rows > visible_rows:
            self.score_vsb.grid()
        else:
            self.score_vsb.grid_remove()

        # Update Log Console
        all_log_messages = list(self.debug_log_fn())
        new_log_messages = all_log_messages[self._last_log_len :]
        if new_log_messages:
            self.log_console.config(state=tk.NORMAL)  # Enable to insert text
            for msg in new_log_messages:
                self.log_console.insert(tk.END, msg + "\n")
            self.log_console.config(state=tk.DISABLED)
            self.log_console.see(tk.END)  # Disable and scroll
        self._last_log_len = len(all_log_messages)

        # Manage scrollbar visibility for log console
        num_lines_cons = int(self.log_console.index("end-1c").split(".")[0])
        vis_lines_cons = self.log_console.cget("height")
        if num_lines_cons > vis_lines_cons:
            self.log_vsb_console.grid()
        else:
            self.log_vsb_console.grid_remove()

        self.after(50, self._refresh_debug_panel_data)  # Schedule next refresh

    def _apply_delay_setting(self):
        """Applies the delay value from the entry box to the bot."""
        ms = self.var_delay.get()
        self.delay_cb(max(10, ms))  # Call bot's setter, ensuring min 10ms

    def _toggle_hdr_preview_mode(self):
        """Toggles the HDR preview mode for template images in the GUI and informs the bot."""
        self.is_HDR_preview_active = self.var_hdr_preview.get()
        self.hdr_preview_cb(
            self.is_HDR_preview_active
        )  # Inform bot (winrate.py's set_hdr_preview_config)
        self._log_to_gui_console(
            f"HDR Preview mode set to {self.is_HDR_preview_active}"
        )
        self._load_data_for_selected_template()  # Reload preview image with new preference

    def _toggle_debug_panel_visibility(self):
        """Toggles the debug mode and the visibility of the debug panel."""
        is_debug_enabled = self.var_debug.get()
        self.debug_cb(is_debug_enabled)  # Inform bot of debug state change
        if is_debug_enabled:
            self.DEBUG_PANEL.pack(
                side="right", fill="both", expand=True, padx=(8, 0), pady=8
            )
            current_h = self.winfo_height()
            self.geometry(
                f"{self.base_width + self.debug_extra}x{max(current_h, self.base_height)}"
            )
            self._refresh_debug_panel_data()  # Start or ensure refresh loop is running
        else:
            self.DEBUG_PANEL.pack_forget()  # Hide panel
            current_h = self.winfo_height()
            self.geometry(f"{self.base_width}x{max(current_h, self.base_height)}")
            # _refresh_debug_panel_data will stop itself as var_debug is now false.

    def _toggle_text_skip_mode(self):
        """Toggles text skip mode and informs the bot."""
        self.text_skip_cb(self.var_text_skip.get())

    def _toggle_thread_lux_mode(self):
        """Toggles Thread Lux mode, ensuring exclusivity with other Lux/Mirror modes."""
        is_enabled = self.var_lux_thread.get()
        if is_enabled:  # If turning ON Thread Lux
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)  # Turn off EXP Lux
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)  # Turn off Mirror Auto
        self.lux_thread_cb(is_enabled)  # Inform bot

    def _toggle_exp_lux_mode(self):
        """Toggles EXP Lux mode, ensuring exclusivity."""
        is_enabled = self.var_lux_EXP.get()
        if is_enabled:  # If turning ON EXP Lux
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)  # Turn off Thread Lux
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)  # Turn off Mirror Auto
        self.lux_EXP_cb(is_enabled)  # Inform bot

    def _toggle_mirror_full_auto_mode(self):
        """Toggles Mirror Dungeon Full Auto mode, ensuring exclusivity."""
        is_enabled = self.var_mirror_full_auto.get()
        if is_enabled:  # If turning ON Mirror Full Auto
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)  # Turn off Thread Lux
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)  # Turn off EXP Lux
        self.mirror_full_auto_cb(is_enabled)  # Inform bot

    PREVIEW_SIZE = (128, 128)  # Dimensions for template preview images

    def _load_data_for_selected_template(self, *_args):
        """Loads and displays data (threshold, ROI, preview) for the currently selected template."""
        current_template_name = self.var_name.get()
        spec_item = self.spec.get(current_template_name)
        if not spec_item:
            self._log_to_gui_console(
                f"Error: No spec found for template '{current_template_name}'"
            )
            self.img_label.config(image="", text="Error")
            return

        base_filename, current_threshold, current_roi = spec_item
        self.var_thr.set(current_threshold)
        self.var_thr_entry.set(f"{current_threshold:.3f}")
        self.lab_roi.config(text=f"ROI : {current_roi if current_roi else 'None'}")

        # Determine preview image path based on HDR_preview flag and availability
        preview_suffix_order = [
            f" {st}.png"
            for st in (("HDR", "SDR") if self.is_HDR_preview_active else ("SDR", "HDR"))
        ]
        preview_suffix_order.append(".png")  # Fallback to plain .png
        folder = os.path.dirname(
            __file__
        )  # Assumes template images are in the same directory
        img_path_to_load = None
        for suffix in preview_suffix_order:
            candidate_path = os.path.join(
                folder, base_filename + suffix.strip()
            )  # .strip() for plain .png
            if os.path.isfile(candidate_path):
                img_path_to_load = candidate_path
                break

        if not img_path_to_load:
            self.img_label.config(image="", text="No preview")
            return

        try:  # Load, resize, and display the preview image
            raw_image = Image.open(img_path_to_load)
            raw_image.thumbnail(
                self.PREVIEW_SIZE, Image.Resampling.LANCZOS
            )  # Use LANCZOS for quality
            bg_image = Image.new(
                "RGBA", self.PREVIEW_SIZE, (0, 0, 0, 0)
            )  # Transparent background
            x_offset = (self.PREVIEW_SIZE[0] - raw_image.width) // 2
            y_offset = (self.PREVIEW_SIZE[1] - raw_image.height) // 2
            alpha_mask = (
                raw_image.split()[3] if raw_image.mode == "RGBA" else None
            )  # Use alpha for transparency
            bg_image.paste(raw_image, (x_offset, y_offset), mask=alpha_mask)
            self._photo_image_preview = ImageTk.PhotoImage(bg_image)  # Keep reference
            self.img_label.config(image=self._photo_image_preview, text="")
        except Exception as e:
            self.img_label.config(image="", text="Preview Error")
            self._log_to_gui_console(f"Error loading preview {img_path_to_load}: {e}")

    def _set_threshold_from_slider(self, *_args):
        """Updates template threshold from slider value."""
        template_name = self.var_name.get()
        if template_name not in self.spec:
            return
        base_filename, _, current_roi = self.spec[template_name]
        new_threshold = round(self.var_thr.get(), 3)
        self.spec[template_name] = (
            base_filename,
            new_threshold,
            current_roi,
        )  # Update live spec
        self.var_thr_entry.set(f"{new_threshold:.3f}")  # Sync entry box
        self.update_cb()  # Notify bot to refresh its internal template data

    def _set_threshold_from_entry(self, _event):
        """Updates template threshold from entry box value (on Enter key)."""
        template_name = self.var_name.get()
        if template_name not in self.spec:
            return
        base_filename, _, current_roi = self.spec[template_name]
        try:
            entered_value = float(self.var_thr_entry.get())
        except ValueError:  # If not a valid float, revert to current slider value
            current_slider_val = round(self.var_thr.get(), 3)
            self.var_thr_entry.set(f"{current_slider_val:.3f}")
            return
        clamped_value = max(
            0.1, min(1.0, entered_value)
        )  # Ensure value is within [0.1, 1.0]
        self.var_thr.set(clamped_value)  # Update slider
        self.spec[template_name] = (
            base_filename,
            clamped_value,
            current_roi,
        )  # Update live spec
        self.update_cb()  # Notify bot
        self.var_thr_entry.set(
            f"{clamped_value:.3f}"
        )  # Ensure entry box shows final value
        self._log_to_gui_console(
            f"Set threshold for {template_name} to {clamped_value:.3f}"
        )

    def _reset_selected_threshold(self):
        """Resets the selected template's threshold to its default value."""
        template_name = self.var_name.get()
        if template_name not in self.orig_spec or template_name not in self.spec:
            return
        base_filename, default_threshold, _ = self.orig_spec[
            template_name
        ]  # Get default from original spec
        _, _, current_roi = self.spec[template_name]  # Keep current ROI
        self.spec[template_name] = (base_filename, default_threshold, current_roi)
        self.var_thr.set(default_threshold)
        self.var_thr_entry.set(f"{default_threshold:.3f}")
        self.update_cb()
        self._log_to_gui_console(
            f"Reset threshold for {template_name} to {default_threshold:.3f}"
        )

    def _reset_selected_roi(self):
        """Resets the selected template's ROI to its default value."""
        template_name = self.var_name.get()
        if template_name not in self.orig_spec or template_name not in self.spec:
            return
        base_filename, _, default_roi = self.orig_spec[template_name]  # Get default ROI
        _, current_threshold, _ = self.spec[template_name]  # Keep current threshold
        self.spec[template_name] = (base_filename, current_threshold, default_roi)
        self.lab_roi.config(text=f"ROI : {default_roi if default_roi else 'None'}")
        self.update_cb()
        self._log_to_gui_console(
            f"Reset ROI for {template_name} to {default_roi if default_roi else 'None'}"
        )

    def _save_current_config_to_json(self): 
        """Saves current configurations (delay, template specs) to saved_user_vars.json."""
        # Prepare the data to be saved
        config_data = {
            "general_settings": {
                "delay_ms": self.var_delay.get() # Get current delay from the Tkinter variable
            },
            "templates": {} # Placeholder for template-specific settings
        }
        
        # Populate template-specific settings (thresholds and ROIs)
        # self.spec refers to the live TEMPLATE_SPEC dictionary shared with winrate.py
        for name, (base, thresh, roi) in self.spec.items(): 
            config_data["templates"][name] = {
                "base": base, 
                "threshold": round(thresh, 4), # Round threshold for cleaner JSON
                "roi": list(roi) if roi else None # Convert ROI tuple to list for JSON, or None
            }
        
        # Determine the path to the configuration file
        # Assumes saved_user_vars.json is in the same directory as multithreaded_gui_config.py
        file_path = os.path.join(os.path.dirname(__file__), "saved_user_vars.json")
        
        try:
            # Write the configuration data to the JSON file
            with open(file_path, "w", encoding="utf-8") as fp: # Specify encoding
                json.dump(config_data, fp, indent=2) # Use indent for readability
            self._log_to_gui_console(f"Config saved to {file_path}")
        except Exception as e:
            self._log_to_gui_console(f"Error saving config: {e}")

    def _toggle_bot_pause_state(self):
        """Toggles the bot's pause/resume state and updates the pause button."""
        if not self.pause_event.is_set():
            self.pause_event.set()
            self.btn_pause.config(text="Resume Bot", bg="red")
            log_msg = "Bot paused"
        else:
            self.pause_event.clear()
            self.btn_pause.config(text="Pause Bot", bg="green")
            log_msg = "Bot resumed"
        self._log_to_gui_console(log_msg)

    def _quit_tuner_application(self):
        """Logs quitting message and forcefully exits the application."""
        self._log_to_gui_console("Tuner quitting...")
        os._exit(0)  # Force exit

    def _pick_roi_on_screen(self):
        """Hides GUI, creates a fullscreen overlay for user to draw an ROI rectangle."""
        self.withdraw()
        time.sleep(0.15)  # Hide main window, wait for it to disappear
        try:
            screen_w, screen_h = (
                pyautogui.size()
            )  # Get screen dimensions for fractional calculation
            overlay_win = tk.Toplevel(self)  # Create a new top-level window for overlay
            overlay_win.attributes("-fullscreen", True)
            overlay_win.attributes("-topmost", True)
            overlay_win.attributes("-alpha", 0.25)
            overlay_win.configure(bg="black")  # Semi-transparent

            canvas = tk.Canvas(
                overlay_win, cursor="crosshair", bg="black", highlightthickness=0
            )
            canvas.pack(fill="both", expand=True)
            rect_draw_info = {
                "x0": 0,
                "y0": 0,
                "x1": 0,
                "y1": 0,
                "id": None,
            }  # Store drawing state

            def on_press(e):  # Mouse button press: start drawing
                rect_draw_info["x0"], rect_draw_info["y0"] = e.x, e.y
                if rect_draw_info["id"]:
                    canvas.delete(rect_draw_info["id"])  # Delete previous rect if any
                rect_draw_info["id"] = canvas.create_rectangle(
                    e.x, e.y, e.x, e.y, outline="red", width=2
                )

            def on_drag(e):  # Mouse drag: resize rectangle
                if rect_draw_info["id"]:
                    canvas.coords(
                        rect_draw_info["id"],
                        rect_draw_info["x0"],
                        rect_draw_info["y0"],
                        e.x,
                        e.y,
                    )
                    rect_draw_info["x1"], rect_draw_info["y1"] = (
                        e.x,
                        e.y,
                    )  # Update current end point

            def on_release(e):  # Mouse button release: finalize ROI
                if not rect_draw_info["id"]:
                    return
                # Ensure coordinates are ordered (x0<x1, y0<y1)
                fx0 = min(rect_draw_info["x0"], rect_draw_info["x1"])
                fy0 = min(rect_draw_info["y0"], rect_draw_info["y1"])
                fx1 = max(rect_draw_info["x0"], rect_draw_info["x1"])
                fy1 = max(rect_draw_info["y0"], rect_draw_info["y1"])

                if fx0 == fx1 or fy0 == fy1:
                    self._log_to_gui_console("ROI selection cancelled or zero size.")
                else:  # Calculate fractional ROI and update
                    fr_x = fx0 / screen_w
                    fr_y = fy0 / screen_h
                    fr_w = (fx1 - fx0) / screen_w
                    fr_h = (fy1 - fy0) / screen_h
                    sel_tpl_name = self.var_name.get()
                    base_fname, cur_thr, _ = self.spec[sel_tpl_name]
                    new_roi_tpl = tuple(round(v, 3) for v in (fr_x, fr_y, fr_w, fr_h))
                    self.spec[sel_tpl_name] = (
                        base_fname,
                        cur_thr,
                        new_roi_tpl,
                    )  # Update live spec in winrate.py
                    self._log_to_gui_console(
                        f"Set ROI for {sel_tpl_name} to {new_roi_tpl}"
                    )
                    self.lab_roi.config(text=f"ROI : {new_roi_tpl}")
                    self.update_cb()  # Notify bot
                overlay_win.destroy()
                self.deiconify()  # Close overlay, show main window

            canvas.bind("<ButtonPress-1>", on_press)
            canvas.bind("<B1-Motion>", on_drag)
            canvas.bind("<ButtonRelease-1>", on_release)
        except Exception as e:
            self._log_to_gui_console(f"Error in ROI snipping: {e}")
            if "overlay_win" in locals() and overlay_win.winfo_exists():
                overlay_win.destroy()
            self.deiconify()  # Ensure main window is re-shown on error

    def _log_to_gui_console(self, message: str):
        """Helper function to safely append messages to the GUI's log console."""
        if hasattr(self, "log_console") and self.log_console:  # Check if console exists
            self.log_console.config(state=tk.NORMAL)  # Enable to insert
            self.log_console.insert(tk.END, message + "\n")  # Add message
            self.log_console.config(state=tk.DISABLED)
            self.log_console.see(tk.END)  # Disable and scroll
        else:
            print(f"GUI_LOG_FALLBACK: {message}")  # Fallback if console not ready


# --- Global instance of the Tuner (GUI window) ---
_tuner_instance: "Tuner | None" = None


def get_tuner() -> "Tuner | None":
    """Public function to access the single Tuner instance."""
    return _tuner_instance


# --- Function to launch the GUI (called from winrate.py) ---
def launch_gui(
    # Arguments match the parameters passed from winrate.py's main()
    template_spec_from_bot,
    default_template_spec_for_reset,
    refresh_templates_callback,
    pause_event_from_bot,
    initial_delay_ms,
    initial_is_HDR,
    initial_debug,
    initial_text_skip,
    initial_lux_thread,
    initial_lux_EXP,
    initial_mirror_full_auto,
    set_delay_ms_cb,
    set_hdr_preview_cb,
    set_debug_mode_cb,
    set_text_skip_cb,
    set_lux_thread_cb,
    set_lux_EXP_cb,
    set_mirror_full_auto_cb,
    get_last_vals_fn,
    get_last_pass_fn,
    get_debug_log_fn,
):
    """
    Launches the Tuner GUI in a separate thread.
    This ensures the GUI runs independently and doesn't block the main bot logic.
    """
    import copy  # For deepcopying the default spec

    # Create a deepcopy of the default spec to ensure the GUI's reset functionality
    # uses a true original version, not a reference that might get modified elsewhere.
    orig_spec_copy_for_gui_reset = copy.deepcopy(default_template_spec_for_reset)

    def _run_gui_thread_target():  # Target function for the GUI thread
        global _tuner_instance  # Allows this thread to set the global _tuner_instance
        _tuner_instance = Tuner(
            live_spec=template_spec_from_bot,
            orig_spec_for_reset=orig_spec_copy_for_gui_reset,
            update_cb_to_bot=refresh_templates_callback,
            pause_event_shared=pause_event_from_bot,
            initial_delay_ms=initial_delay_ms,
            initial_is_HDR_for_preview=initial_is_HDR,
            initial_debug_state=initial_debug,
            initial_text_skip_state=initial_text_skip,
            initial_lux_thread_state=initial_lux_thread,
            initial_lux_EXP_state=initial_lux_EXP,
            initial_mirror_full_auto_state=initial_mirror_full_auto,
            delay_cb=set_delay_ms_cb,
            hdr_preview_cb=set_hdr_preview_cb,
            debug_cb=set_debug_mode_cb,
            text_skip_cb=set_text_skip_cb,
            lux_thread_cb=set_lux_thread_cb,
            lux_EXP_cb=set_lux_EXP_cb,
            mirror_full_auto_cb=set_mirror_full_auto_cb,
            debug_vals_fn=get_last_vals_fn,
            debug_pass_fn=get_last_pass_fn,
            debug_log_fn=get_debug_log_fn,
        )
        # After Tuner is initialized, show/hide debug panel based on its initial state.
        # This ensures _refresh_debug_panel_data starts if initial_debug was true.
        if _tuner_instance.initial_debug_state:
            _tuner_instance.DEBUG_PANEL.pack(
                side="right", fill="both", expand=True, padx=(8, 0), pady=8
            )
            _tuner_instance._refresh_debug_panel_data()  # Start the refresh loop for debug panel
        else:
            _tuner_instance.DEBUG_PANEL.pack_forget()  # Ensure it's hidden if debug is off

        _tuner_instance.mainloop()  # Start Tkinter event loop for the GUI

    # Create and start the GUI thread. Daemon=True means it will exit when main program exits.
    gui_thread = threading.Thread(target=_run_gui_thread_target, daemon=True)
    gui_thread.start()
    return gui_thread  # Return the thread object (optional, for potential future management)
