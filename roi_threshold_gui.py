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
        debug_vals_fn, debug_pass_fn, default_spec 
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

        # ─── state vars ─────────────────────────────────────
        self.spec        = live_spec
        self.orig        = orig_spec
        self.update_cb   = update_cb
        self.var_delay   = tk.IntVar(value=initial_delay_ms)
        self.var_hdr     = tk.BooleanVar(value=initial_is_HDR)
        self.var_debug   = tk.BooleanVar(value=initial_debug)
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
        ttk.Checkbutton(controls, text="HDR mode",
                        variable=self.var_hdr, command=self._toggle_hdr).pack(anchor="w")
        ttk.Checkbutton(controls, text="Debug mode",
                        variable=self.var_debug, command=self._toggle_debug).pack(anchor="w", pady=(0,4))


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
        self.var_thr_label = tk.StringVar(value=f"{initial_thr:.3f}")
        ttk.Label(sf, textvariable=self.var_thr_label, width=6).pack(side="left", padx=4)
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
        self.hdr_cb(self.var_hdr.get())
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

    def _load_data(self, *_):
        base, thr, roi = self.spec[self.var_name.get()]
        self.var_thr.set(thr)
        self.var_thr_label.set(f"{thr:.3f}")
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
        name = self.var_name.get()
        base, _, roi = self.spec[name]
        val = round(self.var_thr.get(), 3)
        self.spec[name] = (base, val, roi)
        self.var_thr_label.set(f"{val:.3f}")
        self.update_cb()

    def _reset_thr(self):
        name = self.var_name.get()
        base, orig_thr, _ = self.default_spec[name]
        # keep whatever ROI the user currently has
        _, _, roi = self.spec[name]
        self.spec[name] = (base, orig_thr, roi)
        self.var_thr.set(orig_thr)
        self.var_thr_label.set(f"{orig_thr:.3f}")
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
    delay_cb,               # fn: int -> None
    hdr_cb,                 # fn: bool -> None
    initial_debug,          # bool
    debug_cb,               # fn: bool -> None
    debug_vals_fn,          # fn: None -> dict[name,score]
    debug_pass_fn,          # fn: None -> dict[name,score]
    default_spec
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
            default_spec
        ).mainloop()
    threading.Thread(target=_run, daemon=True).start()