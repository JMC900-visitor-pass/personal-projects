"""Native, continuously animated aquarium. All lifecycle timers use real time."""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

from .live import LiveTank

BG = "#101c22"
PANEL = "#182930"
INK = "#edf3ed"
MUTED = "#94aaa9"
GREEN = "#a8dab7"
CORAL = "#f08c78"


def duration(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    clock = f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{days}d {clock}" if days else clock


def blend(a, b, fraction):
    fraction = min(1, max(0, fraction))
    channels = [round(int(a[i:i + 2], 16) * (1 - fraction) + int(b[i:i + 2], 16) * fraction)
                for i in (1, 3, 5)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


class AquariumWindow:
    """The window owns presentation; LiveTank owns biology and persistence."""

    def __init__(self, root, tank, save_path):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = root
        self.tank = tank
        self.save_path = Path(save_path)
        self.selected_id = tank.shrimps[0].id if tank.shrimps else None
        self.last_save = time.monotonic()
        self.last_panel = 0.0
        self.saved_text = "Your tank is saved locally"
        self.after_id = None
        self.background_key = None
        self.geometry = (0.0, 0.0, 1.0)
        root.title("Shrimp Brain · Cherry shrimp aquarium")
        root.geometry("1280x840")
        root.minsize(1000, 710)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Tank.TButton", background="#263f45", foreground=INK,
                        borderwidth=0, padding=(14, 12), font=("Helvetica Neue", 12, "bold"))
        style.map("Tank.TButton", background=[("active", "#35535a"), ("pressed", "#1e353b")])
        style.configure("Feed.TButton", background=CORAL, foreground=BG,
                        borderwidth=0, padding=(14, 12), font=("Helvetica Neue", 12, "bold"))
        style.map("Feed.TButton", background=[("active", "#f4ac9e"), ("pressed", "#dd7c69")])

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 18))
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        self.label(titles, "SHRIMP BRAIN", size=10, color=GREEN, bold=True).pack(anchor="w")
        self.label(titles, "Cherry shrimp aquarium", size=25, bold=True).pack(anchor="w", pady=(5, 3))
        self.label(titles, "A living tank. One second here is one second outside.", size=12).pack(anchor="w")
        live = tk.Frame(header, bg="#243c34", padx=15, pady=10)
        live.pack(side="right", anchor="n", pady=8)
        self.label(live, "●  LIVE  1×", size=12, color=GREEN, bold=True).pack()

        content = tk.Frame(root, bg=BG)
        content.pack(fill="both", expand=True, padx=28)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        view = tk.Frame(content, bg=BG)
        view.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        tank_header = tk.Frame(view, bg=BG)
        tank_header.pack(fill="x", pady=(0, 10))
        self.population_label = self.label(tank_header, "", color=INK, size=12, bold=True)
        self.population_label.pack(side="left")
        self.age_label = self.label(tank_header, "", size=11)
        self.age_label.pack(side="right")
        self.canvas = tk.Canvas(view, bg="#0e1a1f", highlightthickness=1,
                                highlightbackground="#30464b", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.click_tank)
        self.canvas.bind("<Configure>", lambda event: self.invalidate_background())
        self.label(view, "Click a shrimp to inspect it · Click open water to drop food", size=11).pack(anchor="w", pady=(10, 4))
        self.label(view, "SPACE  Feed     L  Light     B  Breed pair     S  Save state", color="#6f898b", size=10).pack(anchor="w")

        sidebar = tk.Frame(content, bg=BG, width=290)
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.pack_propagate(False)
        controls = self.card(sidebar, "TANK CONTROLS")
        ttk.Button(controls, text="Drop food     ·     Space", style="Feed.TButton",
                   command=self.feed).pack(fill="x", pady=(12, 8))
        self.light_button = ttk.Button(controls, text="", style="Tank.TButton", command=self.toggle_light)
        self.light_button.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Breed a pair     ·     B", style="Tank.TButton",
                   command=self.breed).pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Save state     ·     S", style="Tank.TButton",
                   command=self.save_state).pack(fill="x")
        self.label(controls, "Feed to attract hungry shrimp. Switch off the light to let the tank settle.\n"
                   "Save state locks a timestamped checkpoint with this tank's seed and population.",
                   size=11, wrap=252).pack(anchor="w", pady=(12, 0))

        breeding = self.card(sidebar, "BREEDING")
        self.breeding_label = self.label(breeding, "", size=12, color=INK, wrap=252)
        self.breeding_label.pack(anchor="w", pady=(9, 7))
        self.label(breeding, f"Egg incubation: {tank.incubation_days:g} real days.\nEgg timers continue while the app is closed.",
                   size=10, wrap=252).pack(anchor="w")

        inspect = self.card(sidebar, "UNDER THE LENS")
        self.name_label = self.label(inspect, "", size=19, color=CORAL, bold=True)
        self.name_label.pack(anchor="w", pady=(8, 5))
        self.detail_label = self.label(inspect, "", size=11, color=INK, wrap=252)
        self.detail_label.pack(anchor="w")
        self.hunger_canvas = tk.Canvas(inspect, width=250, height=6, bg="#294047", highlightthickness=0)
        self.hunger_canvas.pack(fill="x", pady=(12, 5))
        self.hunger_label = self.label(inspect, "", size=10)
        self.hunger_label.pack(anchor="w")

        observations = self.card(sidebar, "TANK NOTES")
        self.events_label = self.label(observations, "", size=10, wrap=252)
        self.events_label.pack(anchor="w", pady=(8, 0))

        footer = tk.Frame(root, bg=BG)
        footer.pack(fill="x", padx=28, pady=(16, 15))
        self.status_label = self.label(footer, "", size=10)
        self.status_label.pack(side="left")
        self.label(footer, "Neocaridina davidi  /  behaviour model", size=10, color="#678184").pack(side="right")
        root.bind("<space>", lambda event: self.feed())
        root.bind("<KeyPress-l>", lambda event: self.toggle_light())
        root.bind("<KeyPress-b>", lambda event: self.breed())
        root.bind("<KeyPress-s>", lambda event: self.save_state())
        self.refresh_panel(time.time())
        self.frame()

    def label(self, parent, text, size=12, color=MUTED, bold=False, wrap=None):
        options = dict(text=text, bg=parent.cget("bg"), fg=color, anchor="w", justify="left",
                       font=("Helvetica Neue", size, "bold" if bold else "normal"))
        if wrap:
            options["wraplength"] = wrap
        return self.tk.Label(parent, **options)

    def card(self, parent, title):
        card = self.tk.Frame(parent, bg=PANEL, padx=16, pady=13)
        card.pack(fill="x", pady=(0, 12))
        self.label(card, title, size=9, color=GREEN, bold=True).pack(anchor="w")
        return card

    def invalidate_background(self):
        self.background_key = None

    def point(self, x, y):
        left, top, scale = self.geometry
        return left + x * scale, top + y * scale

    def draw_background(self):
        canvas = self.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        scale = max(0.01, min((width - 28) / 100, (height - 28) / 65))
        left, top = (width - 100 * scale) / 2, (height - 65 * scale) / 2
        self.geometry = left, top, scale
        canvas.delete("all")
        lit = self.tank.light_on
        water_top, water_bottom = ("#365956", "#172e31") if lit else ("#172a36", "#101c28")
        for row in range(65):
            canvas.create_rectangle(*self.point(0, row), *self.point(100, row + 1),
                                    fill=blend(water_top, water_bottom, row / 64), outline="", tags="background")
        rng = random.Random(208)
        # Uneven mineral grains make the top-down substrate legible without an image asset.
        for _ in range(700):
            x, y = rng.uniform(1, 99), rng.uniform(1, 64)
            px, py = self.point(x, y)
            r = rng.uniform(0.3, 1.6) * scale / 7
            shade = rng.choice(("#637366", "#465d54", "#83907b")) if lit else "#2d4145"
            canvas.create_oval(px-r, py-r, px+r, py+r, fill=shade, outline="", tags="background")

        # A piece of driftwood, viewed from above.
        for offset, stroke, color in ((1.0, 11, "#142627"), (0, 9, "#51463b"), (-.7, 5, "#695746")):
            coords = [self.point(x, y + offset) for x, y in ((7, 54), (20, 47), (30, 43), (40, 41))]
            canvas.create_line(*[v for pair in coords for v in pair], smooth=True, width=stroke*scale/7,
                               fill=color if lit else blend(color, "#172532", .55), capstyle="round", tags="background")
        for anchor, height, spread in ((9, 23, 7), (17, 13, 5), (92, 29, 8), (82, 16, 6), (64, 11, 4)):
            base_y = 58 if anchor < 30 else 61
            for branch in range(5):
                bx = anchor + (branch - 2) * spread / 5
                stem_top = base_y - height * rng.uniform(.65, 1.2)
                canvas.create_line(*self.point(anchor, base_y), *self.point(bx, stem_top),
                                   fill="#548163" if lit else "#294b45", width=1.4, tags="background")
                for leaf in range(7):
                    y = base_y - (base_y - stem_top) * leaf / 7
                    center = anchor + (bx - anchor) * leaf / 7
                    for side in (-1, 1):
                        coords = (self.point(center, y), self.point(center + side*3, y-2.5),
                                  self.point(center + side*4, y-1), self.point(center, y+1))
                        canvas.create_polygon(*[v for pair in coords for v in pair], smooth=True,
                                              fill=rng.choice(("#416f50", "#638563", "#365d48")) if lit else "#27493f",
                                              outline="", tags="background")
        # Shelter geometry matches the live model's (85,20), radius 9 region.
        canvas.create_oval(*self.point(75, 12), *self.point(96, 30), fill="#132629", outline="", tags="background")
        canvas.create_oval(*self.point(75, 10), *self.point(94, 27), fill="#69706a" if lit else "#34464c",
                           outline="#7b8175" if lit else "#40525a", width=2, tags="background")
        canvas.create_oval(*self.point(77, 15), *self.point(91, 27), fill="#0f2023", outline="", tags="background")
        canvas.create_text(*self.point(85, 31), text="SHELTER", font=("Helvetica Neue", 8), fill="#93aaa1" if lit else "#587984", tags="background")
        canvas.create_rectangle(*self.point(0, 0), *self.point(100, 65), outline="#779087" if lit else "#35565d", width=2, tags="background")
        canvas.create_text(*self.point(3, 3), text="LIGHT ON" if lit else "MOONLIGHT", anchor="nw",
                           fill="#b3cabb" if lit else "#7199ae", font=("Helvetica Neue", 9), tags="background")
        self.background_key = (width, height, lit)

    def draw_shrimp(self, shrimp, now):
        canvas = self.canvas
        px, py = self.point(shrimp.x, shrimp.y)
        scale = self.geometry[2]
        length = max(6, min(28, (shrimp.size_mm or 17) * 1.4)) * max(.7, scale / 7)
        c, s = math.cos(shrimp.heading), math.sin(shrimp.heading)

        def p(x, y):
            return px + (x*c-y*s)*length, py + (x*s+y*c)*length

        def line(points, color, width=1):
            canvas.create_line(*[v for pair in points for v in p(*pair)], fill=color, width=width, smooth=True, tags="living")

        color = shrimp.color
        if not self.tank.light_on:
            color = blend(color, "#4a6178", .35)
        if shrimp.state == "HIDE":
            color = blend(color, "#233b3b", .55)
        highlight = blend(color, "#ffe7b1", .38)
        if shrimp.id == self.selected_id:
            r = length * 1.15
            canvas.create_oval(px-r, py-r, px+r, py+r, outline="#b1d8c1", width=1, dash=(2, 4), tags="living")
        # Curved abdomen segments, a tail fan, antennae and moving swimmerets.
        sway = math.sin(now * 7 + len(shrimp.id)) * .09 if shrimp.state not in ("REST", "HIDE") else 0
        for side in (-1, 1):
            line([(.35, side*.08), (.8, side*.22), (1.16, side*(.37+sway))], highlight)
            for leg in range(3):
                x = .15 - leg*.2
                line([(x, side*.14), (x-.05+sway, side*.32), (x+.16+sway, side*.4)], highlight)
            fan = [p(-.65, .02), p(-.96, side*.25), p(-1.04, side*.06), p(-.74, -.04)]
            canvas.create_polygon(*[v for pair in fan for v in pair], fill=color, outline=highlight, tags="living")
        for index in range(6, -1, -1):
            x = .31 - index * .145
            y = .06 * math.sin(index / 2)
            center_x, center_y = p(x, y)
            r = length * (.2 - index*.016)
            canvas.create_oval(center_x-r*1.15, center_y-r, center_x+r*1.15, center_y+r,
                               fill=color, outline=highlight, width=1, tags="living")
        line([(.5, -.045), (.72, 0), (.5, .045)], highlight)
        for side in (-1, 1):
            ex, ey = p(.45, side*.115)
            canvas.create_oval(ex-1.4, ey-1.4, ex+1.4, ey+1.4, fill="#11191c", outline="", tags="living")
        if shrimp.eggs:
            for egg in range(7):
                ex, ey = p(.07 - (egg % 4)*.12, .03 + (egg // 4)*.11)
                canvas.create_oval(ex-1.6, ey-1.6, ex+1.6, ey+1.6, fill="#d7bc67", outline="", tags="living")
        if shrimp.id == self.selected_id:
            canvas.create_text(px, py+length*1.4, text=shrimp.id, fill=INK, font=("Helvetica Neue", 10, "bold"), tags="living")

    def draw_living(self, now):
        self.canvas.delete("living")
        for pellet in self.tank.pellets:
            x, y = self.point(pellet.x, pellet.y)
            r = max(2, min(6, pellet.remaining * 3))
            self.canvas.create_oval(x-10, y-10, x+10, y+10, outline="#738c62", dash=(2, 5), tags="living")
            self.canvas.create_oval(x-r, y-r, x+r, y+r, fill="#c8a769", outline="#e6d297", tags="living")
        for shrimp in self.tank.shrimps:
            self.draw_shrimp(shrimp, now)

    def refresh_panel(self, now):
        adults = sum(s.born_at is None or now-s.born_at >= 30*86400 for s in self.tank.shrimps)
        young = len(self.tank.shrimps) - adults
        population = f"{len(self.tank.shrimps)} shrimp"
        if young:
            population += f" · {young} juveniles"
        self.population_label.configure(text=population)
        self.age_label.configure(text=f"Tank age  {duration(now-self.tank.created_at)}")
        self.light_button.configure(text=f"Light: {'on' if self.tank.light_on else 'off'}     ·     L")
        self.breeding_label.configure(text=self.tank.breeding_status)
        shrimp = next((s for s in self.tank.shrimps if s.id == self.selected_id), None)
        if shrimp:
            sex = {"M": "Male", "F": "Female", "?": "Sex unrecorded"}.get(shrimp.sex, "Sex unrecorded")
            age = "Adult founder" if shrimp.born_at is None else f"Age {duration(now-shrimp.born_at)}"
            body = f"{shrimp.size_mm:.1f} mm" if shrimp.size_mm is not None else "Size unrecorded"
            details = f"{sex} · {age}\n{body} · Generation {shrimp.generation}\n{shrimp.state.replace('_', ' ').title()}"
            if shrimp.eggs:
                details += f"\n{shrimp.eggs} eggs · hatch in {duration((shrimp.hatch_at or now)-now)}"
            self.name_label.configure(text=shrimp.id)
            self.detail_label.configure(text=details)
            fullness = 1 - shrimp.hunger
            self.hunger_canvas.delete("all")
            self.hunger_canvas.create_rectangle(0, 0, max(0, 250*fullness), 6,
                                                 fill=GREEN if fullness > .4 else CORAL, outline="")
            self.hunger_label.configure(text=f"Fullness  {fullness:.0%}")
        self.events_label.configure(text="\n\n".join(reversed(self.tank.events[-3:])))
        self.status_label.configure(text=self.saved_text)

    def feed(self, x=50, y=43):
        self.tank.advance()
        self.saved_text = self.tank.feed(x, y)
        self.persist()
        self.refresh_panel(time.time())
        return "break"

    def toggle_light(self):
        self.tank.advance()
        self.tank.toggle_light()
        self.invalidate_background()
        self.persist()
        self.refresh_panel(time.time())
        return "break"

    def breed(self):
        self.tank.advance()
        self.saved_text = self.tank.request_breeding()
        self.persist()
        self.refresh_panel(time.time())
        return "break"

    def save_state(self):
        self.tank.advance()
        try:
            path = self.tank.save_state(self.save_path.parent / "states")
            self.saved_text = f"State saved: {path.name} (seed {self.tank.seed}, {len(self.tank.shrimps)} shrimp)"
        except (OSError, ValueError) as exc:
            self.saved_text = f"Could not save state: {exc}"
        self.persist()
        self.refresh_panel(time.time())
        return "break"

    def click_tank(self, event):
        left, top, scale = self.geometry
        x, y = (event.x-left)/scale, (event.y-top)/scale
        if not (0 <= x <= 100 and 0 <= y <= 65):
            return
        shrimp = min(self.tank.shrimps, key=lambda s: math.hypot(s.x-x, s.y-y), default=None)
        if shrimp and math.hypot(shrimp.x-x, shrimp.y-y) <= 3:
            self.selected_id = shrimp.id
            self.refresh_panel(time.time())
        else:
            self.feed(x, y)

    def persist(self):
        try:
            self.tank.save(self.save_path)
            self.last_save = time.monotonic()
        except OSError as exc:
            self.saved_text = f"Could not save tank: {exc}"
            return False
        return True

    def frame(self):
        now = time.time()
        self.tank.advance(now)
        key = (self.canvas.winfo_width(), self.canvas.winfo_height(), self.tank.light_on)
        if key != self.background_key:
            self.draw_background()
        self.draw_living(now)
        if time.monotonic() - self.last_save >= 5:
            self.persist()
        if now - self.last_panel >= .5:
            self.refresh_panel(now)
            self.last_panel = now
        self.after_id = self.root.after(33, self.frame)

    def close(self):
        from tkinter import messagebox
        self.tank.advance()
        if not self.persist():
            if not messagebox.askyesno("Tank could not be saved", "Close without saving the latest progress?", parent=self.root):
                return
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        self.root.destroy()


def launch(sheet, seed=None, count=8, save_path="shrimp_tank.json"):
    """Open a saved tank or create founders from the source sheet."""
    try:
        import tkinter as tk
    except ImportError as exc:
        raise ValueError("Live view requires Python with Tkinter support") from exc
    save_path = Path(save_path)
    tank = LiveTank.load(save_path) if save_path.exists() else LiveTank.from_sheet(sheet, seed=seed, count=count)
    tank.save(save_path)
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise ValueError(f"Could not open the aquarium window: {exc}") from exc
    AquariumWindow(root, tank, save_path)
    root.mainloop()
