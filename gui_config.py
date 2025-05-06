# roi_threshold_gui.py
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

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading, time, os
import json
import copy

# ──────────────────────────────────────────────────────────────────────
class Tuner(tk.Tk):
    def __init__(
        self,
        live_spec, orig_spec, update_cb, pause_event,
        initial_delay_ms, initial_is_HDR, initial_debug,
        initial_text_skip, delay_cb, hdr_cb, debug_cb,
        text_skip_cb, debug_vals_fn, debug_pass_fn,
        debug_log_fn, default_spec, lux_thread, lux_EXP,
        mirror_full_auto, lux_thread_cb, lux_EXP_cb,
        mirror_full_auto_cb
    ):
        super().__init__(className="Limbus tuner")
        self.title("Limbus tuner")
        self.base_width     = 500               # width when DEBUG off
        self.debug_extra    = 450               # extra width for the debug panel
        self.base_height    = 620               # whatever you set
        self.attributes('-topmost', True)       # <— keep on top
        # start at the correct size for initial_debug:
        w = self.base_width + (self.debug_extra if initial_debug else 0)
        self.geometry(f"{w}x{self.base_height}")
        self.minsize(self.base_width, self.base_height)

        self.pause_event            = pause_event
        self.delay_cb               = delay_cb
        self.hdr_cb                 = hdr_cb
        self.is_HDR                 = initial_is_HDR
        self.debug_cb               = debug_cb
        self.debug_vals_fn          = debug_vals_fn
        self.debug_pass_fn          = debug_pass_fn
        self.debug_log_fn           = debug_log_fn
        self.text_skip_cb           = text_skip_cb
        self.text_skip              = initial_text_skip
        self.default_spec           = default_spec
        self.lux_thread_cb          = lux_thread_cb
        self.lux_EXP_cb             = lux_EXP_cb
        self.mirror_full_auto_cb    = mirror_full_auto_cb
        self.lux_thread             = lux_thread
        self.lux_EXP                = lux_EXP
        self.mirror_full_auto       = mirror_full_auto

        # ─── state vars ─────────────────────────────────────
        self.spec                   = live_spec
        self.orig                   = orig_spec
        self.update_cb              = update_cb
        self.var_delay              = tk.IntVar(value=initial_delay_ms)
        self.var_hdr                = tk.BooleanVar(value=initial_is_HDR)
        self.var_debug              = tk.BooleanVar(value=initial_debug)
        self.var_text_skip          = tk.BooleanVar(value=initial_text_skip)
        self.var_lux_thread         = tk.BooleanVar(value=self.lux_thread)
        self.var_lux_EXP            = tk.BooleanVar(value=self.lux_EXP)
        self.var_mirror_full_auto   = tk.BooleanVar(value=self.mirror_full_auto)
        self.DEBUG_PANEL            = None

        style = ttk.Style(self)
        style.configure("Debug.Treeview", rowheight=24)

        self._last_log_len = 0    # track how many lines we last drew

        # ─── top layout ─────────────────────────────────────
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        controls = ttk.Frame(container)
        controls.pack(side="left", fill="both", expand=True)

        # ── Frame-grab delay control ──────────────────────────────────
        df = ttk.Frame(controls); df.pack(fill="x", pady=2)
        ttk.Label(df, text="Delay (ms):").pack(side="left")
        ttk.Entry(df, width=5, textvariable=self.var_delay).pack(side="left", padx=4)
        ttk.Button(df, text="Apply", command=self._apply_delay).pack(side="left")

        # ── HDR / Debug toggles ───────────────────────────────────────
        # put all of our toggles into a little grid frame:
        chk_frame = ttk.Frame(controls)
        chk_frame.pack(fill="x", pady=4)

        # column 0
        ttk.Checkbutton(chk_frame,
                        text="HDR mode",
                        variable=self.var_hdr,
                        command=self._toggle_hdr
                    ).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        
        ttk.Checkbutton(chk_frame,
                        text="Debug mode",
                        variable=self.var_debug,
                        command=self._toggle_debug
                    ).grid(row=1, column=0, sticky="w", padx=2, pady=2)
        
        ttk.Checkbutton(chk_frame,
                        text="Skip Text",
                        variable=self.var_text_skip,
                        command=self._toggle_text_skip
                    ).grid(row=2, column=0, sticky="w", padx=2, pady=2)

        # column 1
        ttk.Checkbutton(chk_frame,
                        text="Mirror Full Auto",
                        variable=self.var_mirror_full_auto,
                        command=self._toggle_mirror_full_auto
                    ).grid(row=0, column=1, sticky="w", padx=20, pady=2)

        ttk.Checkbutton(chk_frame,
                        text="Thread Luxcavation",
                        variable=self.var_lux_thread,
                        command=self._toggle_thread_lux
                    ).grid(row=1, column=1, sticky="w", padx=20, pady=2)
        
        ttk.Checkbutton(chk_frame,
                        text="EXP Luxcavation",
                        variable=self.var_lux_EXP,
                        command=self._toggle_exp_lux
                    ).grid(row=2, column=1, sticky="w", padx=20, pady=2)

        # ── template selector ─────────────────────────────────────────
        self.var_name = tk.StringVar(value=next(iter(self.spec)))
        ttk.OptionMenu(controls, self.var_name, self.var_name.get(),
                       *self.spec.keys(), command=self._load_data).pack(fill="x")

        # ── threshold slider & display ──────────────────
        sf = ttk.Frame(self)
        base, initial_thr, _ = self.spec[self.var_name.get()]
        sf = ttk.Frame(controls); sf.pack(fill="x", pady=4)
        self.var_thr = tk.DoubleVar(value=initial_thr)
        self.scale   = ttk.Scale(sf, from_=0.1, to=1.0,
                                 variable=self.var_thr, command=self._set_thr)
        self.scale.pack(side="left", fill="x", expand=True)
        self.var_thr_entry = tk.StringVar(value=f"{initial_thr:.3f}")
        entry = ttk.Entry(sf, width=6, textvariable=self.var_thr_entry)
        entry.pack(side="left", padx=4)
        # when the user types and presses Enter, call our handler:
        entry.bind("<Return>", self._on_thr_entry)
        self.img_label = tk.Label(sf)
        self.img_label.pack(side="right", padx=4)
        # ttk.Label(self, text="threshold").pack()

        # ── ROI display & pick ─────────────────────────
        self.lab_roi = ttk.Label(controls, text="ROI : None")
        self.lab_roi.pack(pady=4)
        ttk.Button(controls, text="Pick ROI", command=self._snip).pack()

        # ── Reset / Pause / Quit / Save ────────────────
        bottom = ttk.Frame(controls)
        bottom.pack(side="bottom", fill="x", pady=(8,4))

        bar = ttk.Frame(bottom); bar.pack(fill="x", pady=(8,4))
        ttk.Button(bar, text="Reset thr",  command=self._reset_thr) .pack(side="left", expand=True, fill="x", padx=(0,2))
        ttk.Button(bar, text="Reset ROI",  command=self._reset_roi) .pack(side="left", expand=True, fill="x", padx=(2,2))

        self.btn_pause = tk.Button(bottom, text="Pause Bot", bg="green", fg="white",
                                   command=self._toggle_bot)
        self.btn_pause.pack(fill="x", pady=(0,6))
        tk.Button(bottom, text="Quit", bg="red", fg="white",
                  command=self._quit).pack(fill="x")
        ttk.Button(bottom, text="Save Config", command=self._save_config) \
            .pack(fill="x", pady=(4,0))

        # ── debug table placeholder ─────────────────────
        self._build_debug_panel(container)

        # ── initial load ───────────────────────────────
        self._load_data()

    def _build_debug_panel(self, parent):
        """create but hide the debug panel"""
        self.DEBUG_PANEL = ttk.Frame(parent, relief="sunken", borderwidth=0.5)
        self.DEBUG_PANEL.pack(side="right", fill="both", padx=(8,0), pady=8)

        # configure grid: one column, four rows. row1 weight=3, row3 weight=2
        self.DEBUG_PANEL.columnconfigure(0, weight=1)
        self.DEBUG_PANEL.rowconfigure(1, weight=6)
        self.DEBUG_PANEL.rowconfigure(3, weight=4)

        # — Scores header —
        lbl_scores = ttk.Label(
            self.DEBUG_PANEL,
            text="Debug Scores",
            font=("TkDefaultFont", 10, "bold")
        )
        lbl_scores.grid(row=0, column=0, sticky="n", pady=(4,2))

        # — Scores table —
        cols = ("name", "value", "threshold", "last_pass")
        self.tree = ttk.Treeview(
            self.DEBUG_PANEL,
            columns=cols,
            show="headings",
            height=15,
            style="Debug.Treeview"
        )
        for col, heading, width in [
            ("name",      "Template",    160),
            ("value",     "Score",        80),
            ("threshold", "Thresh",       80),
            ("last_pass", "Last Pass",    80),
        ]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w" if col=="name" else "e")

        self.tree.grid(
            row=1, column=0,
            sticky="nsew",
            padx=(4,0), pady=(0,4)
        )

        # — Scores scrollbar (initially hidden) —
        self.score_vsb = ttk.Scrollbar(
            self.DEBUG_PANEL,
            orient="vertical",
            command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self.score_vsb.set)
        self.score_vsb.grid(row=1, column=1, sticky="ns", pady=(0,4))
        self.score_vsb.grid_remove()

        # — Log header —
        lbl_log = ttk.Label(
            self.DEBUG_PANEL,
            text="Log",
            font=("TkDefaultFont", 10, "bold")
        )
        lbl_log.grid(row=2, column=0, sticky="n", pady=(4,2))

        # — Log console —
        self.log_console = tk.Listbox(
            self.DEBUG_PANEL,
            activestyle="none"
        )
        self.log_console.grid(
            row=3, column=0,
            sticky="nsew",
            padx=(4,0), pady=(0,4)
        )

        # — Log scrollbar (initially hidden) —
        self.log_vsb = ttk.Scrollbar(
            self.DEBUG_PANEL,
            orient="vertical",
            command=self.log_console.yview
        )
        self.log_console.configure(yscrollcommand=self.log_vsb.set)
        self.log_vsb.grid(row=3, column=1, sticky="ns", pady=(0,4))
        self.log_vsb.grid_remove()

        # start hidden
        self.DEBUG_PANEL.pack_forget()

    def _refresh_debug(self):
        if not self.var_debug.get():
            return

        # --- update the tree as before ---
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        scores = self.debug_vals_fn()
        passes = self.debug_pass_fn()
        for name, (_, thr, _) in self.spec.items():
            val     = scores.get(name, 0.0)
            last_ok = passes.get(name, 0.0)
            self.tree.insert("", "end",
                values=(name, f"{val:.3f}", f"{thr:.3f}", f"{last_ok:.3f}")
            )

        # auto–show/hide tree scrollbar
        total_rows   = len(self.tree.get_children())
        visible_rows = int(self.tree['height'])
        if total_rows > visible_rows:
            self.score_vsb.grid()
        else:
            self.score_vsb.grid_remove()

        # --- update the log console without always resetting its view ---
        logs = list(self.debug_log_fn())   # ensure it's a list
        # grab current scroll fraction (0.0=top … 1.0=bottom)
        top_frac, _ = self.log_console.yview()

        # repopulate
        self.log_console.delete(0, tk.END)
        for line in logs:
            self.log_console.insert(tk.END, line)

        # only auto-scroll if new lines were added
        curr_len = len(logs)
        if curr_len > self._last_log_len:
            self.log_console.see(tk.END)
        else:
            # restore whatever fraction was showing before
            self.log_console.yview_moveto(top_frac)
        self._last_log_len = curr_len

        # auto–show/hide log scrollbar
        total_lines   = self.log_console.size()
        visible_lines = int(self.log_console['height'])
        if total_lines > visible_lines:
            self.log_vsb.grid()
        else:
            self.log_vsb.grid_remove()

        # schedule next update
        self.after(50, self._refresh_debug)

    # ────────────────────────────────────────────────────────────────
    def _apply_delay(self):
        ms = self.var_delay.get()
        if ms < 10: 
            ms = 10; self.var_delay.set(ms)
        self.delay_cb(ms)

    def _toggle_hdr(self):
        # pull the new state out of the checkbox
        new_hdr = self.var_hdr.get()
        # update our own copy
        self.is_HDR = new_hdr
        # notify the bot to reload its templates
        self.hdr_cb(new_hdr)            

        # and redraw the thumbnail in the GUI
        self._load_data()

    def _toggle_debug(self):
        dbg = self.var_debug.get()
        self.debug_cb(dbg)

        if dbg:
            # show panel
            self.DEBUG_PANEL.pack(side="right", fill="y", padx=(8,0))
            # grow window
            new_w = self.base_width + self.debug_extra
            self.geometry(f"{new_w}x{self.winfo_height()}")
            self._refresh_debug()
        else:
            # hide panel
            self.DEBUG_PANEL.pack_forget()
            # shrink back
            self.geometry(f"{self.base_width}x{self.winfo_height()}")            

    def _toggle_text_skip(self):
        # pull the new state out of the checkbox
        sel = self.var_text_skip.get()
        # update our own copy
        self.text_skip = sel
        self.text_skip_cb(sel)            

    def _toggle_thread_lux(self):
        sel = self.var_lux_thread.get()
        if sel:
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)
        self.lux_thread = sel
        self.lux_thread_cb(sel)

    def _toggle_exp_lux(self):
        sel = self.var_lux_EXP.get()
        if sel:
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)
            if self.var_mirror_full_auto.get():
                self.var_mirror_full_auto.set(False)
                self.mirror_full_auto_cb(False)          
        self.lux_EXP = sel
        self.lux_EXP_cb(sel)

    def _toggle_mirror_full_auto(self):
        sel = self.var_mirror_full_auto.get()
        if sel:
            if self.var_lux_thread.get():
                self.var_lux_thread.set(False)
                self.lux_thread_cb(False)
            if self.var_lux_EXP.get():
                self.var_lux_EXP.set(False)
                self.lux_EXP_cb(False)
        self.mirror_full_auto = sel
        self.mirror_full_auto_cb(sel)

    PREVIEW_SIZE = (128, 128)

    def _load_data(self, *_):
        base, thr, roi = self.spec[self.var_name.get()]
        self.var_thr.set(thr)
        self.var_thr_entry.set(f"{thr:.3f}")
        self.lab_roi.config(text=f"ROI : {roi}")

        # update image preview
        # pick HDR vs SDR suffix, fallback to plain .png
        suffix = " HDR.png" if self.is_HDR else " SDR.png"
        folder = os.path.dirname(__file__)
        candidate1 = os.path.join(folder, base + suffix)
        candidate2 = os.path.join(folder, base + ".png")
        img_path = os.path.join(folder, base + suffix)

        # pick whichever exists first
        if os.path.isfile(candidate1):
            img_path = candidate1
        elif os.path.isfile(candidate2):
            img_path = candidate2
        else:
            # print(f"[Tuner] no preview file found for {base!r}")
            self.img_label.config(image="", text="No preview")
            return

        # now actually load and show
        try:
            raw = Image.open(img_path)
        except Exception:
            self.img_label.config(image="", text="No preview")
            return

        # thumbnail into our box
        raw.thumbnail(self.PREVIEW_SIZE, Image.LANCZOS)

        # create a transparent (or colored) background
        bg = Image.new("RGBA", self.PREVIEW_SIZE, (0,0,0,0))

        # compute offsets to center it
        x_off = (self.PREVIEW_SIZE[0] - raw.width)  // 2
        y_off = (self.PREVIEW_SIZE[1] - raw.height) // 2

        # if raw has an alpha channel, use it as mask
        mask = raw.split()[3] if raw.mode == "RGBA" else None
        bg.paste(raw, (x_off, y_off), mask=mask)

        # now hand it off to Tk
        self._photo = ImageTk.PhotoImage(bg)
        self.img_label.config(image=self._photo, text="")

    def _set_thr(self, *_):
        """
        Called when the slider moves.
        Update the spec and also sync the entry box.
        """
        name = self.var_name.get()
        base, _, roi = self.spec[name]

        # round to 3 decimals
        val = round(self.var_thr.get(), 3)
        self.spec[name] = (base, val, roi)

        # sync the entry to show the new value
        self.var_thr_entry.set(f"{val:.3f}")

        # notify bot to reload thresholds if needed
        self.update_cb()

    def _on_thr_entry(self, event):
        """
        Called when the user types a number and hits Enter.
        Validate, clamp between 0.1 and 1.0, then update slider & spec.
        """
        name = self.var_name.get()
        base, _, roi = self.spec[name]

        try:
            # try to parse what they typed
            val = float(self.var_thr_entry.get())
        except ValueError:
            # if invalid, restore the entry to the current slider value
            current = round(self.var_thr.get(), 3)
            self.var_thr_entry.set(f"{current:.3f}")
            return

        # clamp to the slider’s range
        val = max(0.1, min(1.0, val))

        # update both slider and spec
        self.var_thr.set(val)
        self.spec[name] = (base, val, roi)
        self.update_cb()

        # make sure the entry also shows the clamped/rounded value
        self.var_thr_entry.set(f"{val:.3f}")

    def _reset_thr(self):
        name = self.var_name.get()
        base, orig_thr, _ = self.default_spec[name]
        # keep whatever ROI the user currently has
        _, _, roi = self.spec[name]
        self.spec[name] = (base, orig_thr, roi)
        self.var_thr.set(orig_thr)
        self.var_thr_entry.set(f"{orig_thr:.3f}")
        self.update_cb()

    def _reset_roi(self):
        name = self.var_name.get()
        base, _, orig_roi = self.default_spec[name]
        # keep whatever threshold the user currently has
        _, thr, _ = self.spec[name]
        self.spec[name] = (base, thr, orig_roi)
        self.lab_roi.config(text=f"ROI : {orig_roi}")
        self.update_cb()

    def _save_config(self):
        """
        Write out a JSON file mapping each template name to its
        current threshold and ROI.  Saved as roi_thresholds.json
        next to the tuner script.
        """
        cfg = {}
        for name, (base, thresh, roi) in self.spec.items():
            cfg[name] = {
                "base":     base,
                "threshold": round(thresh, 4),
                "roi":      list(roi) if roi is not None else None
            }
        path = os.path.join(os.path.dirname(__file__), "roi_thresholds.json")
        try:
            with open(path, "w") as fp:
                json.dump(cfg, fp, indent=2)
            # print(f"Configuration saved → {path}")
        except Exception as e:
            # print(f"[Tuner] failed to save config: {e}")
            return

    def _toggle_bot(self):
        if not self.pause_event.is_set():
            self.pause_event.set()
            self.btn_pause.config(text="Resume Bot", bg="red")
            # print("Program paused")
        else:
            self.pause_event.clear()
            self.btn_pause.config(text="Pause Bot", bg="green")
            # print("Program resumed")


    def _quit(self):
        # print("Quitting program…")
        os._exit(0)

    # ── snipping-style ROI picker ───────────────────────────────────
    def _snip(self):
        self.withdraw(); time.sleep(0.15)        # hide control window

        import pyautogui
        W, H = pyautogui.size()

        # full-screen transparent top-level
        ov = tk.Toplevel()
        ov.attributes('-fullscreen', True)
        ov.attributes('-topmost', True)
        ov.attributes('-alpha', 0.25)
        ov.configure(bg='black')
        canvas = tk.Canvas(ov, cursor="crosshair", bg='black', highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        rect = [None]            # mutable holder
        start = [0, 0]

        def on_press(e):
            start[:] = [e.x, e.y]
            if rect[0]:
                canvas.delete(rect[0])
            rect[0] = canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                              outline='red', width=2)

        def on_drag(e):
            if rect[0]:
                canvas.coords(rect[0], start[0], start[1], e.x, e.y)

        def on_release(e):
            if not rect[0]:
                return
            x0, y0, x1, y1 = canvas.coords(rect[0])
            if x1 < x0: x0, x1 = x1, x0
            if y1 < y0: y0, y1 = y1, y0
            fx, fy = x0 / W, y0 / H
            fw, fh = (x1 - x0) / W, (y1 - y0) / H
            name = self.var_name.get()
            base, thr, _ = self.spec[name]
            self.spec[name] = (base, thr,
                               tuple(round(v, 3) for v in (fx, fy, fw, fh)))
            self.lab_roi.config(text=f"ROI : {self.spec[name][2]}")
            self.update_cb()
            ov.destroy()
            self.deiconify()       # show main window again

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>",     on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

# ──────────────────────────────────────────────────────────────
# module-level holder
_tuner_instance: "Tuner | None" = None

def get_tuner() -> "Tuner | None":
    """Once it’s up, returns the running Tuner instance."""
    return _tuner_instance

def launch_gui(
    template_spec,
    refresh_fn,
    pause_event,
    initial_delay_ms,
    initial_is_HDR,
    initial_debug,
    delay_cb,                   # fn: int -> None
    hdr_cb,                     # fn: bool -> None
    debug_cb,                   # fn: bool -> None
    debug_vals_fn,              # fn: None -> dict[name,score]
    debug_pass_fn,              # fn: None -> dict[name,score]
    debug_log_fn,               # fn: None -> list[str]
    text_skip_cb,               # fn: bool -> None
    initial_text_skip,          # bool
    default_spec,               # your `DEFAULT_TEMPLATE_SPEC`
    initial_lux_thread,         # bool
    initial_lux_EXP,            # bool
    initial_mirror_full_auto,   # bool
    lux_thread_cb,              # fn: bool -> None
    lux_EXP_cb,                 # fn: bool -> None
    mirror_full_auto_cb         # fn: bool -> None
):
    import copy, threading
    orig = copy.deepcopy(template_spec)
    def _run():
        global _tuner_instance
        # instantiate the Tuner and store it to the module‐level variable
        _tuner_instance = Tuner(
            template_spec,
            orig,
            refresh_fn,
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
            mirror_full_auto_cb
        )
        _tuner_instance.mainloop()
    threading.Thread(target=_run, daemon=True).start()

def get_tuner() -> Tuner | None:
    """Retrieve the single Tuner instance once it's up."""
    return _tuner_instance