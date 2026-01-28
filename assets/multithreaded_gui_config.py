# multithreaded_gui_config.py
"""
Live-tuning GUI for Limbus bot (compatible with multithreaded winrate.py)
──────────────────────────────
• Shows a dropdown of all template names.
• Slider adjusts that template’s threshold (0.10→1.00), with live numeric display.
• “Pick ROI” button lets you draw a rectangle on screen.
• “Pause Bot” / “Quit” below.
• When Debug mode is ON, a table on the right shows each template’s
  last match-score and its threshold.
• [UPDATED] Dark Mode enabled.
"""

# ── std-lib imports ───────────────────────────────────────────────────
import os
import threading
import time
import sys
import json

# ── GUI library imports ───────────────────────────────────────────────
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk
import pyautogui

# ──────────────────────────────────────────────────────────────────────
class Tuner(tk.Tk):

    def __init__(
        self,
        live_spec,
        orig_spec_for_reset,
        update_cb_to_bot,
        pause_event_shared,
        initial_delay_ms,
        initial_is_HDR_for_preview,
        initial_debug_state,
        initial_text_skip_state,
        initial_lux_thread_state,
        initial_lux_EXP_state,
        initial_mirror_full_auto_state,
        delay_cb,
        hdr_preview_cb,
        debug_cb,
        text_skip_cb,
        lux_thread_cb,
        lux_EXP_cb,
        mirror_full_auto_cb,
        debug_vals_fn,
        debug_pass_fn,
        debug_log_fn,
        failsafe_timer,
        failsafe_timer_cb,
        initial_failsafe_enabled,
        failsafe_enabled_cb,
    ):
        super().__init__(className="Limbus tuner")
        self.title("Limbus tuner")

        # --- COLOR PALETTE (Dark Mode) ---
        self.BG_COLOR = "#1e1e1e"  # Main Window Background
        self.FG_COLOR = "#d4d4d4"  # Main Text Color
        self.ACCENT_BG = "#2d2d2d"  # Secondary Background (Entries, etc)
        self.STRIPE_ODD = "#1e1e1e"  # Treeview Odd Rows
        self.STRIPE_EVEN = "#252526"  # Treeview Even Rows
        self.HEADER_BG = "#3e3e42"  # Treeview Header

        # Configure Main Window
        self.configure(bg=self.BG_COLOR)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._quit_tuner_application)
        self.resizable(True, True)

        # --- THEME CONFIGURATION ---
        self.style = ttk.Style(self)
        self.style.theme_use("clam")  # 'clam' allows easier custom coloring

        # Configure generic TWidget styles to match Dark Mode
        self.style.configure(
            ".", background=self.BG_COLOR, foreground=self.FG_COLOR, borderwidth=0
        )
        self.style.configure("TFrame", background=self.BG_COLOR)
        self.style.configure(
            "TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR
        )
        self.style.configure(
            "TButton",
            background=self.HEADER_BG,
            foreground=self.FG_COLOR,
            borderwidth=1,
            focuscolor=self.BG_COLOR,
        )
        self.style.map(
            "TButton", background=[("active", "#4e4e52"), ("pressed", "#007acc")]
        )
        self.style.configure(
            "TCheckbutton", background=self.BG_COLOR, foreground=self.FG_COLOR
        )
        self.style.map(
            "TCheckbutton",
            background=[("active", self.BG_COLOR)],
            indicatorcolor=[("selected", "#007acc")],
        )
        self.style.configure(
            "TEntry",
            fieldbackground=self.ACCENT_BG,
            foreground=self.FG_COLOR,
            insertcolor=self.FG_COLOR,
            borderwidth=1,
        )
        self.style.configure(
            "TMenubutton", background=self.HEADER_BG, foreground=self.FG_COLOR
        )

        # Specific Treeview Style
        self.style.configure(
            "Debug.Treeview",
            background=self.BG_COLOR,
            foreground=self.FG_COLOR,
            fieldbackground=self.BG_COLOR,
            rowheight=24,
            borderwidth=0,
        )
        self.style.configure(
            "Debug.Treeview.Heading",
            background=self.HEADER_BG,
            foreground=self.FG_COLOR,
            relief="flat",
        )
        self.style.map("Debug.Treeview.Heading", background=[("active", "#4e4e52")])

        self.initial_debug_state = initial_debug_state

        # Store references
        self.spec = live_spec
        self.orig_spec = orig_spec_for_reset
        self.update_cb = update_cb_to_bot
        self.pause_event = pause_event_shared

        self.delay_cb = delay_cb
        self.hdr_preview_cb = hdr_preview_cb
        self.is_HDR_preview_active = initial_is_HDR_for_preview
        self.debug_cb = debug_cb
        self.failsafe_timer_cb = failsafe_timer_cb
        self.failsafe_enabled_cb = failsafe_enabled_cb

        self.debug_vals_fn = debug_vals_fn
        self.debug_pass_fn = debug_pass_fn
        self.debug_log_fn = debug_log_fn

        self.text_skip_cb = text_skip_cb
        self.lux_thread_cb = lux_thread_cb
        self.lux_EXP_cb = lux_EXP_cb
        self.mirror_full_auto_cb = mirror_full_auto_cb

        # Tkinter variables
        self.var_delay = tk.IntVar(value=initial_delay_ms)
        self.var_hdr_preview = tk.BooleanVar(value=initial_is_HDR_for_preview)
        self.var_debug = tk.BooleanVar(value=initial_debug_state)
        self.var_text_skip = tk.BooleanVar(value=initial_text_skip_state)
        self.var_lux_thread = tk.BooleanVar(value=initial_lux_thread_state)
        self.var_lux_EXP = tk.BooleanVar(value=initial_lux_EXP_state)
        self.var_mirror_full_auto = tk.BooleanVar(value=initial_mirror_full_auto_state)
        self.var_failsafe_timer = tk.DoubleVar(value=float(failsafe_timer))
        self.var_failsafe_enabled = tk.BooleanVar(value=initial_failsafe_enabled)

        self.DEBUG_PANEL = None
        self._last_log_len = 0

        # --- Build GUI Layout ---
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

        # Failsafe timer UI
        dfs = ttk.Frame(controls)
        dfs.pack(fill="x", pady=2)
        ttk.Checkbutton(
            dfs,
            text="Failsafe On",
            variable=self.var_failsafe_enabled,
            command=self._toggle_failsafe_enabled,
        ).pack(side="left", padx=(0, 8))

        ttk.Label(dfs, text="Timer (s):").pack(side="left")
        ttk.Entry(dfs, width=5, textvariable=self.var_failsafe_timer).pack(
            side="left", padx=4
        )
        ttk.Button(dfs, text="Apply", command=self._apply_failsafe_timer_setting).pack(
            side="left"
        )

        # Checkboxes
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
            text="Mirror Auto",
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

        # Dropdown
        first_template_name = next(iter(self.spec)) if self.spec else ""
        self.var_name = tk.StringVar(value=first_template_name)
        # OptionMenu in ttk needs style handling implicitly via TMenubutton
        ttk.OptionMenu(
            controls,
            self.var_name,
            self.var_name.get(),
            *self.spec.keys(),
            command=self._load_data_for_selected_template,
        ).pack(fill="x", pady=2)

        # Threshold UI
        sf = ttk.Frame(controls)
        sf.pack(fill="x", pady=4)
        initial_thr_val = 0.75
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

        # Standard tk.Label needs explicit colors for dark mode
        self.img_label = tk.Label(sf, bg=self.BG_COLOR, fg=self.FG_COLOR)
        self.img_label.pack(side="right", padx=4)

        # ROI UI
        self.lab_roi = ttk.Label(controls, text="ROI : None")
        self.lab_roi.pack(pady=4)
        ttk.Button(controls, text="Pick ROI", command=self._pick_roi_on_screen).pack()

        # Bottom buttons
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

        # Manual TK buttons with explicit colors
        self.btn_pause = tk.Button(
            bottom_buttons_frame,
            text="Pause Bot",
            bg="#228B22",
            fg="white",
            activebackground="#32CD32",
            activeforeground="white",
            relief="flat",
            command=self._toggle_bot_pause_state,
        )
        self.btn_pause.pack(fill="x", pady=(0, 6))
        tk.Button(
            bottom_buttons_frame,
            text="Quit",
            bg="#B22222",
            fg="white",
            activebackground="#FF0000",
            activeforeground="white",
            relief="flat",
            command=self._quit_tuner_application,
        ).pack(fill="x")
        ttk.Button(
            bottom_buttons_frame,
            text="Save Config",
            command=self._save_current_config_to_json,
        ).pack(fill="x", pady=(4, 0))

        # Create Debug Panel
        self._build_debug_panel_widgets(container)

        # Load initial data
        if first_template_name:
            self._load_data_for_selected_template()

        # --- SIZING LOGIC: Auto-fit on startup ---
        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())
        self.geometry("")

    def _build_debug_panel_widgets(self, parent_container):
        self.DEBUG_PANEL = ttk.Frame(parent_container, relief="sunken", borderwidth=0.5)
        self.DEBUG_PANEL.columnconfigure(0, weight=1)
        self.DEBUG_PANEL.rowconfigure(1, weight=6)
        self.DEBUG_PANEL.rowconfigure(3, weight=4)

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

        # --- COMPACT WIDTHS (Aggressively reduced) ---
        # Template=95, Data=45. Total width approx 230px + padding.
        for col_id, heading_text, col_width in [
            ("name", "Tmpl", 95),  # Shortened header
            ("value", "Scr", 45),  # Shortened header
            ("threshold", "Thr", 45),
            ("last_pass", "Lst", 45),
        ]:
            self.tree.heading(col_id, text=heading_text)
            self.tree.column(
                col_id, width=col_width, anchor="w" if col_id == "name" else "e"
            )

        # --- Dark Mode Stripes ---
        self.tree.tag_configure(
            "odd", background=self.STRIPE_ODD, foreground=self.FG_COLOR
        )
        self.tree.tag_configure(
            "even", background=self.STRIPE_EVEN, foreground=self.FG_COLOR
        )

        self.tree.grid(row=1, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))
        self.score_vsb = ttk.Scrollbar(
            self.DEBUG_PANEL, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self.score_vsb.set)
        self.score_vsb.grid(row=1, column=1, sticky="ns", pady=(0, 4))
        self.score_vsb.grid_remove()

        lbl_log = ttk.Label(
            self.DEBUG_PANEL, text="Log", font=("TkDefaultFont", 10, "bold")
        )
        lbl_log.grid(row=2, column=0, sticky="n", pady=(4, 2))

        # Standard tk.Text needs explicit colors for Dark Mode
        self.log_console = tk.Text(
            self.DEBUG_PANEL,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=8,
            borderwidth=0,
            relief="flat",
            bg=self.ACCENT_BG,  # Dark Grey Input
            fg=self.FG_COLOR,  # Light Text
            insertbackground=self.FG_COLOR,  # White Cursor
        )
        self.log_console.grid(row=3, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))
        self.log_vsb_console = ttk.Scrollbar(
            self.DEBUG_PANEL, orient="vertical", command=self.log_console.yview
        )
        self.log_console.configure(yscrollcommand=self.log_vsb_console.set)
        self.log_vsb_console.grid(row=3, column=1, sticky="ns", pady=(0, 4))
        self.log_vsb_console.grid_remove()

    def _refresh_debug_panel_data(self):
        if not self.var_debug.get():
            return
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        scores_data = self.debug_vals_fn()
        passes_data = self.debug_pass_fn()

        if not self.spec:
            self.after(50, self._refresh_debug_panel_data)
            return

        # --- Logic to Insert with Alternating Tags ---
        row_idx = 0
        for template_name, spec_details in self.spec.items():
            if not isinstance(spec_details, tuple) or len(spec_details) < 2:
                continue
            current_threshold = spec_details[1]
            current_score = scores_data.get(template_name, 0.0)
            last_pass_score = passes_data.get(template_name, 0.0)

            # Determine tag based on even/odd index
            row_tag = "even" if row_idx % 2 == 0 else "odd"

            self.tree.insert(
                "",
                "end",
                values=(
                    template_name,
                    f"{current_score:.3f}",
                    f"{current_threshold:.3f}",
                    f"{last_pass_score:.3f}",
                ),
                tags=(row_tag,),  # Apply the tag
            )
            row_idx += 1

        total_rows = len(self.tree.get_children())
        visible_rows = int(self.tree["height"])
        if total_rows > visible_rows:
            self.score_vsb.grid()
        else:
            self.score_vsb.grid_remove()

        all_log_messages = list(self.debug_log_fn())
        new_log_messages = all_log_messages[self._last_log_len :]
        if new_log_messages:
            self.log_console.config(state=tk.NORMAL)
            for msg in new_log_messages:
                self.log_console.insert(tk.END, msg + "\n")
            self.log_console.config(state=tk.DISABLED)
            self.log_console.see(tk.END)
        self._last_log_len = len(all_log_messages)

        num_lines_cons = int(self.log_console.index("end-1c").split(".")[0])
        vis_lines_cons = self.log_console.cget("height")
        if num_lines_cons > vis_lines_cons:
            self.log_vsb_console.grid()
        else:
            self.log_vsb_console.grid_remove()

        self.after(50, self._refresh_debug_panel_data)

    def _apply_delay_setting(self):
        ms = self.var_delay.get()
        self.delay_cb(max(10, ms))

    def _apply_failsafe_timer_setting(self):
        seconds = self.var_failsafe_timer.get()
        self.failsafe_timer_cb(max(0.5, seconds))

    def _toggle_hdr_preview_mode(self):
        self.is_HDR_preview_active = self.var_hdr_preview.get()
        self.hdr_preview_cb(self.is_HDR_preview_active)
        self._log_to_gui_console(
            f"HDR Preview mode set to {self.is_HDR_preview_active}"
        )
        self._load_data_for_selected_template()

    def _toggle_debug_panel_visibility(self):
        """Toggles the debug mode and adjusts window size dynamically."""
        is_debug_enabled = self.var_debug.get()
        self.debug_cb(is_debug_enabled)

        if is_debug_enabled:
            self.DEBUG_PANEL.pack(
                side="right", fill="both", expand=True, padx=(8, 0), pady=8
            )
            self._refresh_debug_panel_data()
        else:
            self.DEBUG_PANEL.pack_forget()

        self.geometry("")

    def _toggle_text_skip_mode(self):
        self.text_skip_cb(self.var_text_skip.get())

    def _toggle_thread_lux_mode(self):
        is_enabled = self.var_lux_thread.get()
        if is_enabled:
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)
        self.lux_thread_cb(is_enabled)

    def _toggle_exp_lux_mode(self):
        is_enabled = self.var_lux_EXP.get()
        if is_enabled:
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)
        self.lux_EXP_cb(is_enabled)

    def _toggle_mirror_full_auto_mode(self):
        is_enabled = self.var_mirror_full_auto.get()
        if is_enabled:
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)
        self.mirror_full_auto_cb(is_enabled)

    def _toggle_failsafe_enabled(self):
        state = self.var_failsafe_enabled.get()
        self.failsafe_enabled_cb(state)
        self._log_to_gui_console(f"Failsafe logic {'ENABLED' if state else 'DISABLED'}")

    PREVIEW_SIZE = (128, 128)

    def _load_data_for_selected_template(self, *_args):
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

        preview_suffix_order = [
            f" {st}.png"
            for st in (("HDR", "SDR") if self.is_HDR_preview_active else ("SDR", "HDR"))
        ]
        preview_suffix_order.append(".png")

        script_dir = os.path.dirname(__file__)
        img_path_to_load = None
        for suffix in preview_suffix_order:
            candidate_path = os.path.join(
                script_dir, "images", base_filename + suffix.strip()
            )
            if os.path.isfile(candidate_path):
                img_path_to_load = candidate_path
                break

        if not img_path_to_load:
            self.img_label.config(image="", text="No preview")
            return

        try:
            raw_image = Image.open(img_path_to_load)
            raw_image.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
            bg_image = Image.new("RGBA", self.PREVIEW_SIZE, (0, 0, 0, 0))
            x_offset = (self.PREVIEW_SIZE[0] - raw_image.width) // 2
            y_offset = (self.PREVIEW_SIZE[1] - raw_image.height) // 2
            alpha_mask = raw_image.split()[3] if raw_image.mode == "RGBA" else None
            bg_image.paste(raw_image, (x_offset, y_offset), mask=alpha_mask)
            self._photo_image_preview = ImageTk.PhotoImage(bg_image)
            self.img_label.config(image=self._photo_image_preview, text="")
        except Exception as e:
            self.img_label.config(image="", text="Preview Error")
            self._log_to_gui_console(f"Error loading preview {img_path_to_load}: {e}")

    def _set_threshold_from_slider(self, *_args):
        template_name = self.var_name.get()
        if template_name not in self.spec:
            return
        base_filename, _, current_roi = self.spec[template_name]
        new_threshold = round(self.var_thr.get(), 3)
        self.spec[template_name] = (base_filename, new_threshold, current_roi)
        self.var_thr_entry.set(f"{new_threshold:.3f}")
        self.update_cb()

    def _set_threshold_from_entry(self, _event):
        template_name = self.var_name.get()
        if template_name not in self.spec:
            return
        base_filename, _, current_roi = self.spec[template_name]
        try:
            entered_value = float(self.var_thr_entry.get())
        except ValueError:
            current_slider_val = round(self.var_thr.get(), 3)
            self.var_thr_entry.set(f"{current_slider_val:.3f}")
            return
        clamped_value = max(0.1, min(1.0, entered_value))
        self.var_thr.set(clamped_value)
        self.spec[template_name] = (base_filename, clamped_value, current_roi)
        self.update_cb()
        self.var_thr_entry.set(f"{clamped_value:.3f}")
        self._log_to_gui_console(
            f"Set threshold for {template_name} to {clamped_value:.3f}"
        )

    def _reset_selected_threshold(self):
        template_name = self.var_name.get()
        if template_name not in self.orig_spec or template_name not in self.spec:
            return
        base_filename, default_threshold, _ = self.orig_spec[template_name]
        _, _, current_roi = self.spec[template_name]
        self.spec[template_name] = (base_filename, default_threshold, current_roi)
        self.var_thr.set(default_threshold)
        self.var_thr_entry.set(f"{default_threshold:.3f}")
        self.update_cb()
        self._log_to_gui_console(
            f"Reset threshold for {template_name} to {default_threshold:.3f}"
        )

    def _reset_selected_roi(self):
        template_name = self.var_name.get()
        if template_name not in self.orig_spec or template_name not in self.spec:
            return
        base_filename, _, default_roi = self.orig_spec[template_name]
        _, current_threshold, _ = self.spec[template_name]
        self.spec[template_name] = (base_filename, current_threshold, default_roi)
        self.lab_roi.config(text=f"ROI : {default_roi if default_roi else 'None'}")
        self.update_cb()
        self._log_to_gui_console(
            f"Reset ROI for {template_name} to {default_roi if default_roi else 'None'}"
        )

    def _save_current_config_to_json(self):
        config_data = {
            "general_settings": {
                "delay_ms": self.var_delay.get(),
                "failsafe_timer_s": round(self.var_failsafe_timer.get(), 2),
                "failsafe_enabled": self.var_failsafe_enabled.get(),  # <--- Save state
            },
            "templates": {},
        }
        for name, (base, thresh, roi) in self.spec.items():
            config_data["templates"][name] = {
                "base": base,
                "threshold": round(thresh, 4),
                "roi": (list(roi) if roi else None),
            }
        try:
            if getattr(sys, "frozen", False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.dirname(__file__)
            file_path = os.path.join(base_path, "saved_user_vars.json")
            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(config_data, fp, indent=2)
            self._log_to_gui_console(f"Config saved to {file_path}")
        except Exception as e:
            self._log_to_gui_console(f"Error saving config: {e}")

    def _toggle_bot_pause_state(self):
        if not self.pause_event.is_set():
            self.pause_event.set()
            self.btn_pause.config(text="Resume Bot", bg="#B22222")  # Red
            log_msg = "Bot paused"
        else:
            self.pause_event.clear()
            self.btn_pause.config(text="Pause Bot", bg="#228B22")  # Green
            log_msg = "Bot resumed"
        self._log_to_gui_console(log_msg)

    def _quit_tuner_application(self):
        self._log_to_gui_console("Tuner quitting...")
        os._exit(0)

    def _pick_roi_on_screen(self):
        self.withdraw()
        time.sleep(0.15)
        try:
            screen_w, screen_h = pyautogui.size()
            overlay_win = tk.Toplevel(self)
            overlay_win.attributes("-fullscreen", True)
            overlay_win.attributes("-topmost", True)
            overlay_win.attributes("-alpha", 0.25)
            overlay_win.configure(bg="black")

            canvas = tk.Canvas(
                overlay_win, cursor="crosshair", bg="black", highlightthickness=0
            )
            canvas.pack(fill="both", expand=True)
            rect_draw_info = {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "id": None}

            def on_press(e):
                rect_draw_info["x0"], rect_draw_info["y0"] = e.x, e.y
                if rect_draw_info["id"]:
                    canvas.delete(rect_draw_info["id"])
                rect_draw_info["id"] = canvas.create_rectangle(
                    e.x, e.y, e.x, e.y, outline="red", width=2
                )

            def on_drag(e):
                if rect_draw_info["id"]:
                    canvas.coords(
                        rect_draw_info["id"],
                        rect_draw_info["x0"],
                        rect_draw_info["y0"],
                        e.x,
                        e.y,
                    )
                    rect_draw_info["x1"], rect_draw_info["y1"] = e.x, e.y

            def on_release(e):
                if not rect_draw_info["id"]:
                    return
                fx0 = min(rect_draw_info["x0"], rect_draw_info["x1"])
                fy0 = min(rect_draw_info["y0"], rect_draw_info["y1"])
                fx1 = max(rect_draw_info["x0"], rect_draw_info["x1"])
                fy1 = max(rect_draw_info["y0"], rect_draw_info["y1"])
                if fx0 == fx1 or fy0 == fy1:
                    self._log_to_gui_console("ROI selection cancelled or zero size.")
                else:
                    fr_x = fx0 / screen_w
                    fr_y = fy0 / screen_h
                    fr_w = (fx1 - fx0) / screen_w
                    fr_h = (fy1 - fy0) / screen_h
                    sel_tpl_name = self.var_name.get()
                    base_fname, cur_thr, _ = self.spec[sel_tpl_name]
                    new_roi_tpl = tuple(round(v, 3) for v in (fr_x, fr_y, fr_w, fr_h))
                    self.spec[sel_tpl_name] = (base_fname, cur_thr, new_roi_tpl)
                    self._log_to_gui_console(
                        f"Set ROI for {sel_tpl_name} to {new_roi_tpl}"
                    )
                    self.lab_roi.config(text=f"ROI : {new_roi_tpl}")
                    self.update_cb()
                overlay_win.destroy()
                self.deiconify()

            canvas.bind("<ButtonPress-1>", on_press)
            canvas.bind("<B1-Motion>", on_drag)
            canvas.bind("<ButtonRelease-1>", on_release)
        except Exception as e:
            self._log_to_gui_console(f"Error in ROI snipping: {e}")
            if "overlay_win" in locals() and overlay_win.winfo_exists():
                overlay_win.destroy()
            self.deiconify()

    def _log_to_gui_console(self, message: str):
        if hasattr(self, "log_console") and self.log_console:
            self.log_console.config(state=tk.NORMAL)
            self.log_console.insert(tk.END, message + "\n")
            self.log_console.config(state=tk.DISABLED)
            self.log_console.see(tk.END)
        else:
            print(f"GUI_LOG_FALLBACK: {message}")

# --- Global instance of the Tuner (GUI window) ---
_tuner_instance: "Tuner | None" = None


def get_tuner() -> "Tuner | None":
    return _tuner_instance


# --- Function to launch the GUI (called from winrate.py) ---
def launch_gui(
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
    failsafe_timer,
    set_failsafe_timer_cb,
    initial_failsafe_enabled,
    set_failsafe_enabled_cb,
):
    import copy

    orig_spec_copy_for_gui_reset = copy.deepcopy(default_template_spec_for_reset)

    def _run_gui_thread_target():
        global _tuner_instance
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
            failsafe_timer=failsafe_timer,
            failsafe_timer_cb=set_failsafe_timer_cb,
            initial_failsafe_enabled=initial_failsafe_enabled,
            failsafe_enabled_cb=set_failsafe_enabled_cb,
        )
        if _tuner_instance.initial_debug_state:
            _tuner_instance.DEBUG_PANEL.pack(
                side="right", fill="both", expand=True, padx=(8, 0), pady=8
            )
            _tuner_instance._refresh_debug_panel_data()
        else:
            _tuner_instance.DEBUG_PANEL.pack_forget()

        _tuner_instance.mainloop()

    gui_thread = threading.Thread(target=_run_gui_thread_target, daemon=True)
    gui_thread.start()
    return gui_thread
