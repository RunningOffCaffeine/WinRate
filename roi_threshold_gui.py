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
        initial_delay_ms, initial_is_HDR,
        initial_debug, delay_cb, hdr_cb, debug_cb,
        debug_vals_fn, debug_pass_fn, default_spec,
        lux_thread, lux_EXP, mirror_full_auto, 
        lux_thread_cb, lux_EXP_cb, mirror_full_auto_cb
    ):
        super().__init__(className="Limbus tuner")
        self.title("Limbus tuner")
        self.base_width     = 500               # width when DEBUG off
        self.debug_extra    = 400               # extra width for the debug panel
        self.base_height    = 460               # whatever you set
        self.attributes('-topmost', True)       # <— keep on top
        # start at the correct size for initial_debug:
        w = self.base_width + (self.debug_extra if initial_debug else 0)
        self.geometry(f"{w}x{self.base_height}")
        self.minsize(self.base_width, self.base_height)

        self.pause_event = pause_event
        self.delay_cb = delay_cb
        self.hdr_cb   = hdr_cb
        self.is_HDR = initial_is_HDR
        self.debug_cb = debug_cb
        self.debug_vals_fn  = debug_vals_fn
        self.debug_pass_fn  = debug_pass_fn
        self.default_spec = default_spec
        self.lux_thread_cb = lux_thread_cb
        self.lux_EXP_cb = lux_EXP_cb
        self.mirror_full_auto_cb = mirror_full_auto_cb
        self.lux_thread = lux_thread
        self.lux_EXP = lux_EXP
        self.mirror_full_auto = mirror_full_auto

        # ─── state vars ─────────────────────────────────────
        self.spec        = live_spec
        self.orig        = orig_spec
        self.update_cb   = update_cb
        self.var_delay   = tk.IntVar(value=initial_delay_ms)
        self.var_hdr     = tk.BooleanVar(value=initial_is_HDR)
        self.var_debug   = tk.BooleanVar(value=initial_debug)
        self.var_lux_thread = tk.BooleanVar(value=self.lux_thread)
        self.var_lux_EXP = tk.BooleanVar(value=self.lux_EXP)
        self.var_mirror_full_auto = tk.BooleanVar(value=self.mirror_full_auto)
        self.DEBUG_PANEL  = None

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
        ttk.Label(self, text="threshold").pack()

        # ── ROI display & pick ─────────────────────────
        self.lab_roi = ttk.Label(controls, text="ROI : None")
        self.lab_roi.pack(pady=4)
        ttk.Button(controls, text="Pick ROI", command=self._snip).pack()

        # ── Reset / Pause / Quit / Save ────────────────
        bar = ttk.Frame(controls); bar.pack(fill="x", pady=(8,4))
        ttk.Button(bar, text="Reset thr",  command=self._reset_thr) .pack(side="left", expand=True, fill="x", padx=(0,2))
        ttk.Button(bar, text="Reset ROI",  command=self._reset_roi) .pack(side="left", expand=True, fill="x", padx=(2,2))

        self.btn_pause = tk.Button(controls, text="Pause Bot", bg="green", fg="white",
                                   command=self._toggle_bot)
        self.btn_pause.pack(fill="x", pady=(0,6))
        tk.Button(controls, text="Quit", bg="red", fg="white",
                  command=self._quit).pack(fill="x")
        ttk.Button(controls, text="Save Config", command=self._save_config) \
            .pack(fill="x", pady=(4,0))

        # ── debug table placeholder ─────────────────────
        self._build_debug_panel(container)

        # ── initial load ───────────────────────────────
        self._load_data()

    def _build_debug_panel(self, parent):
        """create but hide the debug panel"""
        self.DEBUG_PANEL = ttk.Frame(parent, relief="sunken", borderwidth=1)
        self.DEBUG_PANEL.pack(side="right", fill="y", padx=(8,0))
        ttk.Label(self.DEBUG_PANEL, text="Debug Scores", font=("TkDefaultFont", 10, "bold"))\
            .pack(pady=(4,2))
        cols = ("name", "value","threshold", "last_pass")
        self.tree = ttk.Treeview(self.DEBUG_PANEL, columns=cols, show="headings", height=15)
        self.tree.heading("name",       text="Template")
        self.tree.heading("value",      text="Score")
        self.tree.heading("threshold",  text="Thresh")
        self.tree.heading("last_pass",  text="Last Pass")
        self.tree.column("name",      width=160, anchor="w")
        self.tree.column("value",     width= 80, anchor="e")
        self.tree.column("threshold", width= 80, anchor="e")
        self.tree.column("last_pass", width= 80, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=4, pady=(0,4))
        hscroll = ttk.Scrollbar(self.DEBUG_PANEL, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=hscroll.set)
        hscroll.pack(fill="x", side="bottom")
        self.DEBUG_PANEL.pack_forget()  # start hidden

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

    def _toggle_thread_lux(self):
        sel = self.var_lux_thread.get()
        if sel:
            # uncheck the other two
            self.var_lux_EXP.set(False)
            self.var_mirror_full_auto.set(False)
            # notify their callbacks
            self.lux_EXP_cb(False)
            self.mirror_full_auto_cb(False)
        self.lux_thread = sel
        self.lux_thread_cb(sel)

    def _toggle_exp_lux(self):
        sel = self.var_lux_EXP.get()
        if sel:
            self.var_lux_thread.set(False)
            self.var_mirror_full_auto.set(False)
            self.lux_thread_cb(False)
            self.mirror_full_auto_cb(False)
        self.lux_EXP = sel
        self.lux_EXP_cb(sel)

    def _toggle_mirror_full_auto(self):
        sel = self.var_mirror_full_auto.get()
        if sel:
            self.var_lux_thread.set(False)
            self.var_lux_EXP.set(False)
            self.lux_thread_cb(False)
            self.lux_EXP_cb(False)
        self.mirror_full_auto = sel
        self.mirror_full_auto_cb(sel)

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
            print(f"[Tuner] no preview file found for {base!r}")
            self.img_label.config(image="", text="No preview")
            return

        # now actually load and show
        try:
            img = Image.open(img_path)
            img.thumbnail((256,256), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.img_label.config(image=self._photo, text="")
        except Exception as e:
            print(f"[Tuner] error loading preview for {base!r}: {e}")
            if hasattr(self, "img_label"):
                self.img_label.config(image="", text="No preview")
            else:
                print(f"[Tuner] no img_label to show preview for {base!r}")

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
            print(f"Configuration saved → {path}")
        except Exception as e:
            print(f"[Tuner] failed to save config: {e}")

    def _toggle_bot(self):
        if not self.pause_event.is_set():
            self.pause_event.set()
            self.btn_pause.config(text="Resume Bot", bg="red")
            print("Program paused")
        else:
            self.pause_event.clear()
            self.btn_pause.config(text="Pause Bot", bg="green")
            print("Program resumed")


    def _quit(self):
        print("Quitting program…")
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

    # ── Debug panel refresher ─────────────────────────────────
    def _refresh_debug(self):
        if not self.var_debug.get():
            return
        scores   = self.debug_vals_fn()     # name → last raw score
        passes   = self.debug_pass_fn()     # name → last passing score
        # clear old rows
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        # repopulate
        for name, (_, thr, _) in self.spec.items():
            val     = scores.get(name, 0.0)
            last_ok = passes.get(name, 0.0)
            # include 'name' as the first column, then score, threshold, last pass
            self.tree.insert("", "end",
                values=(
                    name,
                    f"{val:.3f}",
                    f"{thr:.3f}",
                    f"{last_ok:.3f}"
                )
            )
        # schedule next update
        self.after(100, self._refresh_debug)

# ──────────────────────────────────────────────────────────────
def launch_gui(
    template_spec,
    refresh_fn,
    pause_event,
    initial_delay_ms,
    initial_is_HDR,
    initial_debug,
    delay_cb,               # fn: int -> None
    hdr_cb,                 # fn: bool -> None
    debug_cb,               # fn: bool -> None
    debug_vals_fn,          # fn: None -> dict[name,score]
    debug_pass_fn,          # fn: None -> dict[name,score]
    default_spec,           # your `DEFAULT_TEMPLATE_SPEC`
    initial_lux_thread,     # bool
    initial_lux_EXP,        # bool
    initial_mirror_full_auto,   # bool
    lux_thread_cb,          # fn: bool -> None
    lux_EXP_cb,             # fn: bool -> None
    mirror_full_auto_cb     # fn: bool -> None
):
    import copy, threading
    orig = copy.deepcopy(template_spec)
    def _run():
        Tuner(
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
            default_spec,
            initial_lux_thread,
            initial_lux_EXP,
            initial_mirror_full_auto,
            lux_thread_cb,
            lux_EXP_cb,
            mirror_full_auto_cb
        ).mainloop()
    threading.Thread(target=_run, daemon=True).start()