import os
import threading
import time
import sys
import tkinter as tk
from tkinter import ttk

class MLTuner(tk.Tk):
    def __init__(
        self,
        pause_event_shared,
        initial_delay_ms,
        initial_debug_state,
        initial_text_skip_state,
        initial_confidence,
        initial_failsafe_timer, # UPDATED: Now takes seconds (float)
        set_delay_ms_cb,
        set_debug_mode_cb,
        set_text_skip_cb,
        set_confidence_cb,
        set_failsafe_timer_cb, # UPDATED: Callback for timer
        get_debug_log_fn,
        get_model_predictions_fn,
    ):
        super().__init__(className="Limbus ML Bot")
        self.title("Limbus ML Bot")
        
        # --- COLOR PALETTE (Dark Mode) ---
        self.BG_COLOR = "#1e1e1e"
        self.FG_COLOR = "#d4d4d4"
        self.ACCENT_BG = "#252526"
        self.HEADER_BG = "#3e3e42"
        self.BUTTON_BG = "#3e3e42"
        
        self.configure(bg=self.BG_COLOR)
        self.base_width = 400
        self.debug_extra = 350
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._quit_tuner_application)
        self.resizable(True, True)

        # --- THEME CONFIGURATION ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, borderwidth=0)
        self.style.configure("TFrame", background=self.BG_COLOR)
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.configure("TLabelframe", background=self.BG_COLOR, foreground=self.FG_COLOR, bordercolor=self.HEADER_BG)
        self.style.configure("TLabelframe.Label", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.configure("TButton", background=self.BUTTON_BG, foreground=self.FG_COLOR, borderwidth=1, focuscolor=self.BG_COLOR)
        self.style.map("TButton", background=[('active', '#4e4e52'), ('pressed', '#007acc')])
        self.style.configure("TCheckbutton", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.map("TCheckbutton", background=[('active', self.BG_COLOR)], indicatorcolor=[('selected', '#007acc')])
        self.style.configure("TEntry", fieldbackground=self.ACCENT_BG, foreground=self.FG_COLOR, insertcolor=self.FG_COLOR, borderwidth=1)
        self.style.configure("Horizontal.TScale", background=self.BG_COLOR, troughcolor=self.ACCENT_BG)

        self.initial_debug_state = initial_debug_state

        # Store references
        self.pause_event = pause_event_shared
        self.set_delay_ms_cb = set_delay_ms_cb
        self.set_debug_mode_cb = set_debug_mode_cb
        self.set_text_skip_cb = set_text_skip_cb
        self.set_confidence_cb = set_confidence_cb
        self.set_failsafe_timer_cb = set_failsafe_timer_cb
        self.get_debug_log_fn = get_debug_log_fn
        self.get_model_predictions_fn = get_model_predictions_fn

        # Tkinter variables
        self.var_delay = tk.IntVar(value=initial_delay_ms)
        self.var_confidence = tk.DoubleVar(value=initial_confidence)
        self.var_failsafe_timer = tk.DoubleVar(value=initial_failsafe_timer) # UPDATED
        self.var_debug = tk.BooleanVar(value=initial_debug_state)
        self.var_text_skip = tk.BooleanVar(value=initial_text_skip_state)

        self.DEBUG_PANEL = None
        self._last_log_len = 0
        self._last_predictions = []
        
        self._build_gui()
        
        self.update_idletasks()
        required_height = self.winfo_reqheight()
        self.minsize(self.base_width, required_height)
        current_width = self.base_width + (self.debug_extra if self.initial_debug_state else 0)
        self.geometry(f"{current_width}x{required_height}")
        
        if self.initial_debug_state:
            self._toggle_debug_panel_visibility()

    def _build_gui(self):
        container = ttk.Frame(self, padding="10")
        container.pack(fill="both", expand=True)
        controls = ttk.Frame(container)
        controls.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # --- Settings Section ---
        settings_frame = ttk.LabelFrame(controls, text="Settings", padding="10")
        settings_frame.pack(fill="x", pady=5)

        # Delay setting
        delay_frame = ttk.Frame(settings_frame)
        delay_frame.pack(fill="x", pady=2)
        ttk.Label(delay_frame, text="Scan Delay (ms):").pack(side="left", padx=(0, 5))
        delay_entry = ttk.Entry(delay_frame, width=7, textvariable=self.var_delay)
        delay_entry.pack(side="left")
        delay_entry.bind("<Return>", lambda e: self._apply_delay())
        ttk.Button(delay_frame, text="Apply", command=self._apply_delay).pack(side="left", padx=(5, 0))

        # Failsafe setting (UPDATED to Timer Interface)
        failsafe_frame = ttk.Frame(settings_frame)
        failsafe_frame.pack(fill="x", pady=2)
        ttk.Label(failsafe_frame, text="Failsafe (s):").pack(side="left", padx=(0, 5))
        failsafe_entry = ttk.Entry(failsafe_frame, width=7, textvariable=self.var_failsafe_timer)
        failsafe_entry.pack(side="left")
        failsafe_entry.bind("<Return>", lambda e: self._apply_failsafe_timer())
        ttk.Button(failsafe_frame, text="Apply", command=self._apply_failsafe_timer).pack(side="left", padx=(5, 0))

        # Checkboxes
        chk_frame = ttk.Frame(settings_frame)
        chk_frame.pack(fill="x", pady=8, anchor='w')
        ttk.Checkbutton(chk_frame, text="Skip Dialogue/Cutscenes", variable=self.var_text_skip, command=self._toggle_text_skip_mode).pack(anchor='w')
        ttk.Checkbutton(chk_frame, text="Show Debug Panel & Live View", variable=self.var_debug, command=self._toggle_debug_panel_visibility).pack(anchor='w')
        
        # --- ML Parameters Section ---
        ml_frame = ttk.LabelFrame(controls, text="ML Parameters", padding="10")
        ml_frame.pack(fill="x", pady=5)
        
        confidence_frame = ttk.Frame(ml_frame)
        confidence_frame.pack(fill="x", pady=2)
        ttk.Label(confidence_frame, text="Confidence Threshold:").pack(side="left", padx=(0,5))
        self.var_confidence_entry = tk.StringVar(value=f"{self.var_confidence.get():.4f}")
        confidence_entry = ttk.Entry(confidence_frame, width=6, textvariable=self.var_confidence_entry)
        confidence_entry.pack(side="right")
        confidence_entry.bind("<Return>", self._update_confidence_from_entry)
        self.confidence_scale = ttk.Scale(confidence_frame, from_=0.50, to=1.0, orient="horizontal", variable=self.var_confidence, command=self._update_confidence_from_slider)
        self.confidence_scale.pack(side="right", fill="x", expand=True, padx=5)

        # --- Status Section ---
        status_frame = ttk.LabelFrame(controls, text="Status", padding="10")
        status_frame.pack(fill="x", expand=True, pady=5)
        self.status_label = ttk.Label(status_frame, text="Status: Running", font=("Segoe UI", 10))
        self.status_label.pack(anchor='w')

        # --- Main Controls ---
        buttons_frame = ttk.Frame(controls)
        buttons_frame.pack(side="bottom", fill="x", pady=(10, 0))
        self.btn_pause = tk.Button(buttons_frame, text="Pause Bot", bg="#228B22", fg="white", activebackground="#32CD32", activeforeground="white", font=("Segoe UI", 10, "bold"), relief="flat", command=self._toggle_bot_pause_state)
        self.btn_pause.pack(fill="x", ipady=5, pady=(0, 5))
        tk.Button(buttons_frame, text="Quit Bot", bg="#B22222", fg="white", activebackground="#FF0000", activeforeground="white", font=("Segoe UI", 10, "bold"), relief="flat", command=self._quit_tuner_application).pack(fill="x", ipady=5)
        
        self._build_debug_panel_widgets(container)

    def _apply_failsafe_timer(self):
        """Applies the failsafe timer value."""
        try:
            val = float(self.var_failsafe_timer.get())
            self.set_failsafe_timer_cb(max(0.5, val))
        except ValueError:
            self.var_failsafe_timer.set(5.0)
            self.set_failsafe_timer_cb(5.0)

    def _update_confidence_from_slider(self, value):
        confidence_val = round(float(value), 2)
        self.var_confidence_entry.set(f"{confidence_val:.4f}")
        self.set_confidence_cb(confidence_val)

    def _update_confidence_from_entry(self, event):
        try:
            val = float(self.var_confidence_entry.get())
            clamped_val = max(0.5, min(1.0, val))
            self.var_confidence.set(clamped_val)
            self.var_confidence_entry.set(f"{clamped_val:.4f}")
            self.set_confidence_cb(clamped_val)
            self.focus()
        except ValueError:
            self.var_confidence_entry.set(f"{self.var_confidence.get():.4f}")

    def _build_debug_panel_widgets(self, parent_container):
        self.DEBUG_PANEL = ttk.Frame(parent_container, relief="sunken", borderwidth=1)
        self.DEBUG_PANEL.rowconfigure(1, weight=3) 
        self.DEBUG_PANEL.rowconfigure(3, weight=2) 
        self.DEBUG_PANEL.columnconfigure(0, weight=1)
        ttk.Label(self.DEBUG_PANEL, text="Live Detections", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="nw", padx=5, pady=(5,2))
        self.pred_list = tk.Text(self.DEBUG_PANEL, height=6, wrap=tk.WORD, state=tk.DISABLED, relief="flat", borderwidth=0, bg=self.ACCENT_BG, fg=self.FG_COLOR, insertbackground=self.FG_COLOR)
        self.pred_list.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        pred_vsb = ttk.Scrollbar(self.DEBUG_PANEL, orient="vertical", command=self.pred_list.yview)
        pred_vsb.grid(row=1, column=1, sticky="ns")
        self.pred_list.configure(yscrollcommand=pred_vsb.set)
        ttk.Label(self.DEBUG_PANEL, text="Event Log", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="nw", padx=5, pady=(5,2))
        self.log_console = tk.Text(self.DEBUG_PANEL, wrap=tk.WORD, state=tk.DISABLED, relief="flat", borderwidth=0, bg=self.ACCENT_BG, fg=self.FG_COLOR, insertbackground=self.FG_COLOR)
        self.log_console.grid(row=3, column=0, sticky="nsew", padx=5, pady=(0, 5))
        log_vsb = ttk.Scrollbar(self.DEBUG_PANEL, orient="vertical", command=self.log_console.yview)
        log_vsb.grid(row=3, column=1, sticky="ns", pady=(0,5))
        self.log_console.configure(yscrollcommand=log_vsb.set)

    def _apply_delay(self):
        try:
            ms = int(self.var_delay.get())
            self.set_delay_ms_cb(max(20, ms))
        except ValueError:
            self.var_delay.set(100)
            self.set_delay_ms_cb(100)

    def _toggle_text_skip_mode(self):
        self.set_text_skip_cb(self.var_text_skip.get())
    
    def _toggle_debug_panel_visibility(self):
        is_debug_enabled = self.var_debug.get()
        self.set_debug_mode_cb(is_debug_enabled)
        if is_debug_enabled:
            if not self.DEBUG_PANEL.winfo_ismapped():
                self.DEBUG_PANEL.pack(side="right", fill="both", expand=True)
                self.geometry(f"{self.base_width + self.debug_extra}x{self.winfo_height()}")
                self._refresh_debug_panel_data()
        else:
            if self.DEBUG_PANEL.winfo_ismapped():
                self.DEBUG_PANEL.pack_forget()
                self.geometry(f"{self.base_width}x{self.winfo_height()}")

    def _refresh_debug_panel_data(self):
        if not self.var_debug.get(): return
        predictions = self.get_model_predictions_fn()
        if predictions != self._last_predictions:
            self._last_predictions = predictions
            self.pred_list.config(state=tk.NORMAL)
            self.pred_list.delete('1.0', tk.END)
            if predictions: self.pred_list.insert(tk.END, "\n".join(predictions))
            else: self.pred_list.insert(tk.END, "No confident detections...")
            self.pred_list.config(state=tk.DISABLED)
        all_logs = self.get_debug_log_fn()
        if len(all_logs) != self._last_log_len:
            self.log_console.config(state=tk.NORMAL)
            self.log_console.delete('1.0', tk.END)
            self.log_console.insert(tk.END, "\n".join(all_logs))
            self.log_console.see(tk.END)
            self.log_console.config(state=tk.DISABLED)
            self._last_log_len = len(all_logs)
        self.after(250, self._refresh_debug_panel_data)

    def _toggle_bot_pause_state(self):
        if not self.pause_event.is_set():
            self.pause_event.set()
            self.btn_pause.config(text="Resume Bot", bg="#B22222")
            self.status_label.config(text="Status: Paused")
        else:
            self.pause_event.clear()
            self.btn_pause.config(text="Pause Bot", bg="#228B22")
            self.status_label.config(text="Status: Running")

    def _quit_tuner_application(self):
        print("GUI initiated shutdown.")
        os._exit(0)

_tuner_instance: "MLTuner | None" = None

def get_tuner() -> "MLTuner | None":
    return _tuner_instance

def launch_gui(**kwargs):
    def _run_gui_thread_target():
        global _tuner_instance
        _tuner_instance = MLTuner(**kwargs)
        _tuner_instance.mainloop()
    gui_thread = threading.Thread(target=_run_gui_thread_target, daemon=True)
    gui_thread.start()