"""
Archery Duel - Simulator Panahan Fisika (Tkinter)
=================================================
Mata kuliah : Event-Driven Programming

Konsep event-driven yang dipakai:
  - <Motion>          : membidik (busur mengikuti mouse)
  - <ButtonPress-1>   : tarik busur / lanjut dari layar level
  - <ButtonRelease-1> : lepas anak panah
  - <KeyPress>        : 1-4 ganti panah, Space lompat, G garis bantu,
                        A pencapaian, R ulang, Esc keluar
  - root.after(16)    : game loop (~60 FPS)
  - root.after(3500)  : timer independen pengubah angin

Fisika (piksel & detik):
  vy += G * dt                 -> gravitasi
  vx += WIND_ACC * angin * dt  -> percepatan akibat angin
  sudut panah = atan2(vy, vx)  -> panah selalu menghadap arah geraknya
  Musuh menghitung sudut tembak dari persamaan lintasan parabola,
  lalu ditambah galat acak (makin kecil di level tinggi).
"""

import json
import math
import os
import random
import time
import tkinter as tk

# ------------------------------------------------------------------ KONFIGURASI UMUM
W, H = 1100, 620
TOWER_X0, TOWER_X1, TOWER_TOP = 40, 270, 410     # menara pemain
PX = 150                                         # posisi x pemain

G = 500.0
WIND_ACC = 7.0
MIN_SPEED, MAX_SPEED = 300.0, 950.0
CHARGE_TIME = 1.2

ARROW_LEN = 50
BOW_OFF = 24                    # jarak bahu -> pusat busur
PULL_MAX = 22                   # jarak tarik maksimum tali busur
HEAD_R = 11
BLOCK = 44
PLAT_HALF = 66                  # setengah lebar platform musuh (3 blok)

PLAYER_HP = 100
STAMINA_MAX, STAMINA_REGEN, JUMP_COST = 100.0, 22.0, 30.0
JUMP_V, JUMP_G = -560.0, 1900.0

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archery_progress.json")

# ------------------------------------------------------------------ JENIS PANAH
ARROWS = {
    "normal":    dict(name="Panah Biasa", dmg=25, color="#e5e7eb", ammo=None),
    "fire":      dict(name="Panah Api",   dmg=30, color="#fb923c", ammo=10),
    "explosive": dict(name="Panah Ledak", dmg=30, color="#ef4444", ammo=5),
    "triple":    dict(name="Panah Tiga",  dmg=20, color="#a3e635", ammo=6),
}
ORDER = ["normal", "fire", "explosive", "triple"]
UNLOCK_AFTER = {2: "fire", 4: "explosive", 6: "triple"}   # level (mulai 1) yang diselesaikan -> hadiah panah

# ------------------------------------------------------------------ LEVEL
# hp      : HP tiap musuh
# interval: jeda antar tembakan musuh (detik)
# aim     : lama musuh menarik busur sebelum melepas (detik) -> waktu reaksi pemain
# err     : galat bidik musuh (derajat, simpangan baku) -> makin kecil makin akurat
# dmg     : damage panah musuh (headshot 2x)
# wind    : angin maksimum
# guide   : jumlah titik garis bantu (0 = tidak ada)
# spots   : posisi kaki musuh (x, y)
LEVELS = [
    dict(name="Rekrut",     hp=40, interval=5.0, aim=1.00, err=7.0, dmg=10, wind=0.0, guide=24,
         spots=[(900, 430)]),
    dict(name="Pemburu",    hp=45, interval=4.6, aim=0.95, err=6.0, dmg=11, wind=1.5, guide=20,
         spots=[(930, 400), (760, 300)]),
    dict(name="Penjaga",    hp=50, interval=4.2, aim=0.90, err=5.0, dmg=12, wind=2.5, guide=16,
         spots=[(960, 450), (800, 320), (660, 430)]),
    dict(name="Prajurit",   hp=60, interval=3.8, aim=0.80, err=4.0, dmg=13, wind=3.5, guide=12,
         spots=[(970, 300), (880, 450), (720, 350)]),
    dict(name="Kapten",     hp=60, interval=3.4, aim=0.75, err=3.0, dmg=14, wind=4.5, guide=8,
         spots=[(980, 440), (880, 300), (740, 430), (620, 320)]),
    dict(name="Jenderal",   hp=70, interval=3.0, aim=0.70, err=2.4, dmg=15, wind=5.5, guide=4,
         spots=[(990, 330), (900, 470), (780, 340), (650, 450)]),
    dict(name="Raja Panah", hp=80, interval=2.6, aim=0.60, err=1.8, dmg=16, wind=6.5, guide=0,
         spots=[(990, 450), (930, 300), (820, 420), (700, 310), (600, 440)]),
]
BG_COLORS = ["#404040", "#3d4350", "#453d4b", "#4a3d3d", "#3d4a44", "#4a463a", "#2e2e38"]

# ------------------------------------------------------------------ PENCAPAIAN
ACHIEVEMENTS = {
    "first_blood": ("Darah Pertama",   "Kalahkan musuh pertamamu"),
    "headshot":    ("Tepat di Kepala", "Lakukan satu headshot"),
    "sniper":      ("Sniper",          "Headshot dari jarak lebih dari 650 px"),
    "double":      ("Double Kill",     "Kalahkan 2 musuh dalam 3 detik"),
    "pyro":        ("Pembakar",        "Kalahkan musuh dengan panah api"),
    "boom":        ("Ledakan!",        "Kalahkan 2 musuh dengan satu ledakan"),
    "agile":       ("Lincah",          "Hindari 3 panah musuh dengan melompat"),
    "untouched":   ("Tak Tersentuh",   "Selesaikan level 3+ tanpa terkena panah"),
    "legend":      ("Legenda Pemanah", "Selesaikan Level 7"),
}


# ------------------------------------------------------------------ FUNGSI BANTU
def shade(col, d):
    """Terangkan / gelapkan warna hex."""
    r, g, b = (int(col[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, v + d)) for v in (r, g, b))


def hit_part(fx, fy, x, y):
    """Uji titik (x, y) terhadap figur pemanah dengan kaki di (fx, fy)."""
    if (x - fx) ** 2 + (y - (fy - 58)) ** 2 <= (HEAD_R + 2) ** 2:
        return "head"
    if abs(x - fx) <= 11 and fy - 48 <= y <= fy + 2:
        return "body"
    return None


def solve_shot(sx, sy, tx, ty, v):
    """Sudut elevasi (rad, positif = ke atas) agar panah dari (sx, sy) mengenai (tx, ty)
    dengan kecepatan v. Kecepatan dinaikkan bila target di luar jangkauan."""
    x = abs(sx - tx)
    h = sy - ty
    for _ in range(40):
        k = G * x * x / (2 * v * v)
        disc = x * x - 4 * k * (h + k)
        if disc >= 0:
            return math.atan((x - math.sqrt(disc)) / (2 * k)), v
        v += 30
    return 0.7, MAX_SPEED


class Enemy:
    def __init__(self, x, y, hp):
        self.x, self.y = x, y            # posisi kaki
        self.hp = self.maxhp = hp
        self.alive = True
        self.state = "idle"              # idle | aim
        self.timer = 0.0
        self.pull = 0.0
        self.theta = 0.25                # sudut elevasi bidikan (rad)
        self.speed = 650.0
        self.burn_until = 0.0
        self.burn_tick = 0.0
        self.flash = 0.0

    def vec(self):
        return (-math.cos(self.theta), -math.sin(self.theta))


class ArcheryGame:
    def __init__(self, root):
        self.root = root
        root.title("Archery Duel")
        root.resizable(False, False)
        self.c = tk.Canvas(root, width=W, height=H, highlightthickness=0, bg=BG_COLORS[0])
        self.c.pack()

        self.load_progress()
        self.show_guide = True
        self.show_ach = False
        self.mouse = (PX + 300, 300)
        self.aim_angle = -0.2
        self.toasts = []                 # [judul, waktu_habis]
        self.wind = 0.0
        self.wind_target = 0.0
        self.streaks = [[random.uniform(0, W), random.uniform(60, 480)] for _ in range(14)]

        # --- binding event ---
        self.c.bind("<Motion>", self.on_motion)
        self.c.bind("<ButtonPress-1>", self.on_press)
        self.c.bind("<ButtonRelease-1>", self.on_release)
        root.bind("<KeyPress>", self.on_key)

        self.reset_run()
        self.update_aim()
        self.change_wind()               # mulai timer angin
        self.last = time.perf_counter()
        self.loop()                      # mulai game loop

    # ------------------------------------------------------------------ PROGRES TERSIMPAN
    def load_progress(self):
        self.best = 0
        self.done = set()
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.best = int(d.get("best", 0))
            self.done = {a for a in d.get("achievements", []) if a in ACHIEVEMENTS}
        except Exception:
            pass

    def save_progress(self):
        try:
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump({"best": self.best, "achievements": sorted(self.done)}, f)
        except Exception:
            pass

    def unlock_ach(self, key):
        if key in self.done:
            return
        self.done.add(key)
        self.save_progress()
        self.toasts.append([ACHIEVEMENTS[key][0], time.perf_counter() + 3.5])

    # ------------------------------------------------------------------ STATE
    def reset_run(self):
        """Mulai permainan baru dari Level 1 (panah hadiah hilang, achievement tetap)."""
        self.level = 0
        self.score = 0
        self.kills = 0
        self.hp = float(PLAYER_HP)
        self.unlocked = ["normal"]
        self.dodges = 0
        self.kill_times = []
        self.blast_kills = 0
        self.start_level()

    def start_level(self):
        cfg = self.cfg = LEVELS[self.level]
        self.enemies = [Enemy(x, y, cfg["hp"]) for x, y in cfg["spots"]]
        self.solids = [(TOWER_X0, TOWER_TOP, TOWER_X1, H + 60)]
        self.solids += [(e.x - PLAT_HALF, e.y, e.x + PLAT_HALF, e.y + BLOCK) for e in self.enemies]
        self.arrows, self.stuck, self.ragdolls = [], [], []
        self.particles, self.effects, self.floaters = [], [], []
        self.ammo = {k: v["ammo"] for k, v in ARROWS.items()}
        self.sel = "normal"
        self.stamina = STAMINA_MAX
        self.jump_off = 0.0
        self.jump_vy = 0.0
        self.charging = False
        self.power = 0.0
        self.hurt = 0.0
        self.damage_taken = False
        self.player_dead = False
        self.reward = None
        self.state = "intro"             # intro | play | wait | levelup | dead | victory
        self.next_state = None
        self.wait_until = 0.0
        for e in self.enemies:
            e.timer = random.uniform(1.2, cfg["interval"])
        self.draw_bg()

    # ------------------------------------------------------------------ EVENT
    def on_motion(self, e):
        self.mouse = (e.x, e.y)
        self.update_aim()

    def update_aim(self):
        mx, my = self.mouse
        dx = max(20, mx - PX)
        dy = my - (self.feet_y() - 42)
        ang = math.atan2(dy, dx)
        self.aim_angle = max(math.radians(-80), min(math.radians(20), ang))

    def on_press(self, e):
        if self.show_ach:
            return
        if self.state == "intro":
            self.state = "play"
        elif self.state == "play" and not self.player_dead:
            self.charging = True
            self.power = 0.0
        elif self.state == "levelup":
            self.hp = min(float(PLAYER_HP), self.hp + 50)
            self.level += 1
            self.start_level()
        elif self.state in ("dead", "victory"):
            self.reset_run()

    def on_release(self, e):
        if self.charging and self.state == "play":
            self.fire()

    def on_key(self, e):
        k = e.keysym.lower()
        if k == "r":
            self.reset_run()
        elif k == "g":
            self.show_guide = not self.show_guide
        elif k == "a":
            self.show_ach = not self.show_ach
        elif k == "escape":
            self.root.destroy()
        elif k in ("space", "w", "up"):
            self.jump()
        elif k in ("1", "2", "3", "4"):
            kind = ORDER[int(k) - 1]
            if kind in self.unlocked and (self.ammo[kind] is None or self.ammo[kind] > 0):
                self.sel = kind

    def change_wind(self):
        """Timer independen: ganti target angin sesuai level."""
        wmax = self.cfg["wind"]
        self.wind_target = round(random.uniform(-wmax, wmax), 1)
        self.root.after(3500, self.change_wind)

    # ------------------------------------------------------------------ PEMAIN
    def feet_y(self):
        return TOWER_TOP + self.jump_off

    def jump(self):
        if self.state == "play" and not self.player_dead and self.jump_off == 0 and self.stamina >= JUMP_COST:
            self.jump_vy = JUMP_V
            self.stamina -= JUMP_COST

    def new_arrow(self, x, y, vx, vy, owner, kind, dmg):
        return dict(x=x, y=y, vx=vx, vy=vy, owner=owner, kind=kind, dmg=dmg,
                    alive=True, passed=False, trail=[])

    def fire(self):
        kind = self.sel
        spec = ARROWS[kind]
        power = max(self.power, 0.08)
        speed = MIN_SPEED + power * (MAX_SPEED - MIN_SPEED)
        sx, sy = PX, self.feet_y() - 42
        for da in ([-0.09, 0.0, 0.09] if kind == "triple" else [0.0]):
            a = self.aim_angle + da
            dx, dy = math.cos(a), math.sin(a)
            reach = BOW_OFF + ARROW_LEN - PULL_MAX * power
            self.arrows.append(self.new_arrow(sx + dx * reach, sy + dy * reach,
                                              dx * speed, dy * speed, "p", kind, spec["dmg"]))
        if self.ammo[kind] is not None:
            self.ammo[kind] -= 1
            if self.ammo[kind] <= 0:
                self.sel = "normal"
        self.charging = False
        self.power = 0.0

    def hit_player(self, dmg, headshot, x, y):
        if headshot:
            dmg *= 2
        self.hp -= dmg
        self.damage_taken = True
        self.hurt = 0.35
        self.burst(x, y, ["#ffffff", "#ef4444"], 10, 200)
        self.floater(f"-{int(dmg)}", PX, self.feet_y() - 92, "#f87171")

    # ------------------------------------------------------------------ MUSUH
    def update_enemies(self, dt, now):
        cfg = self.cfg
        for e in self.enemies:
            if not e.alive:
                continue
            e.flash = max(0.0, e.flash - dt)
            if now < e.burn_until:
                e.burn_tick -= dt
                if random.random() < 0.5:
                    self.burst(e.x + random.uniform(-6, 6), e.y - random.uniform(10, 60),
                               ["#f97316", "#fbbf24"], 1, 60)
                if e.burn_tick <= 0:
                    e.burn_tick = 0.5
                    self.damage_enemy(e, 4, False, "burn", abs(e.x - PX), e.x, e.y - 40)
                    if not e.alive:
                        continue
            if e.state == "idle":
                e.timer -= dt
                if e.timer <= 0:
                    self.start_aim(e)
            else:
                e.timer -= dt
                e.pull = 1 - max(0.0, e.timer) / cfg["aim"]
                if e.timer <= 0:
                    self.enemy_shoot(e)

    def start_aim(self, e):
        cfg = self.cfg
        theta, v = solve_shot(e.x, e.y - 42, PX, TOWER_TOP - 32, random.uniform(620, 760))
        e.theta = theta + random.gauss(0, math.radians(cfg["err"]))
        e.speed = v * (1 + random.gauss(0, 0.015))
        e.state = "aim"
        e.timer = cfg["aim"]
        e.pull = 0.0

    def enemy_shoot(self, e):
        dx, dy = e.vec()
        reach = BOW_OFF + ARROW_LEN - PULL_MAX
        self.arrows.append(self.new_arrow(e.x + dx * reach, e.y - 42 + dy * reach,
                                          dx * e.speed, dy * e.speed, "e", "normal", self.cfg["dmg"]))
        e.state = "idle"
        e.pull = 0.0
        e.timer = self.cfg["interval"] * random.uniform(0.8, 1.3)

    def damage_enemy(self, e, dmg, headshot, kind, dist, x, y, push=0.0):
        if not e.alive:
            return
        e.hp -= dmg
        e.flash = 0.12
        self.burst(x, y, ["#ffffff", "#ef4444"], 8, 180)
        if headshot:
            self.floater("HEADSHOT!", x, y - 20, "#facc15")
        if e.hp <= 0:
            self.kill_enemy(e, headshot, kind, dist, push)

    def kill_enemy(self, e, headshot, kind, dist, push):
        now = time.perf_counter()
        e.alive = False
        self.kills += 1
        self.blast_kills += 1
        self.score += 100 + (50 if headshot else 0)
        self.spawn_ragdoll(e.x, e.y, push, "#f5f5f5", "#9ca3af" if self.level >= 2 else None)
        self.unlock_ach("first_blood")
        if headshot:
            self.unlock_ach("headshot")
            if dist > 650:
                self.unlock_ach("sniper")
        if kind in ("fire", "burn"):
            self.unlock_ach("pyro")
        self.kill_times.append(now)
        if len([t for t in self.kill_times if now - t <= 3.0]) >= 2:
            self.unlock_ach("double")

    def explode(self, x, y, direct=None):
        radius = 80
        self.effects.append([x, y, 0.0, 0.45, radius])
        self.burst(x, y, ["#f97316", "#fbbf24", "#ef4444"], 26, 320)
        for e in self.enemies:
            if not e.alive or e is direct:
                continue
            d = math.hypot(e.x - x, (e.y - 30) - y)
            if d <= radius:
                self.damage_enemy(e, 40 * (1 - d / radius) + 10, False, "explosive",
                                  abs(e.x - PX), e.x, e.y - 30, push=(e.x - x) * 3)

    # ------------------------------------------------------------------ TUMBUKAN PANAH
    def arrow_collide(self, a, x, y):
        if a["owner"] == "p":
            for e in self.enemies:
                if not e.alive:
                    continue
                part = hit_part(e.x, e.y, x, y)
                if part:
                    a["x"], a["y"], a["alive"] = x, y, False
                    headshot = part == "head"
                    if a["kind"] == "fire":
                        e.burn_until = time.perf_counter() + 3.0
                    if a["kind"] == "explosive":
                        self.blast_kills = 0
                    self.damage_enemy(e, a["dmg"] * (2 if headshot else 1), headshot, a["kind"],
                                      abs(e.x - PX), x, y, push=a["vx"] * 0.3)
                    if a["kind"] == "explosive":
                        self.explode(x, y, e)
                        if self.blast_kills >= 2:
                            self.unlock_ach("boom")
                    return True
        elif not self.player_dead and self.hp > 0:
            part = hit_part(PX, self.feet_y(), x, y)
            if part:
                a["x"], a["y"], a["alive"] = x, y, False
                self.hit_player(a["dmg"], part == "head", x, y)
                return True

        for (x0, y0, x1, y1) in self.solids:
            if x0 <= x <= x1 and y0 <= y <= y1:
                a["x"], a["y"], a["alive"] = x, y, False
                if a["kind"] == "explosive":
                    self.blast_kills = 0
                    self.explode(x, y)
                    if self.blast_kills >= 2:
                        self.unlock_ach("boom")
                else:
                    self.stuck.append((x, y, math.atan2(a["vy"], a["vx"])))
                    self.stuck = self.stuck[-50:]
                return True
        return False

    def update_arrows(self, dt):
        for a in self.arrows:
            if not a["alive"]:
                continue
            a["vx"] += WIND_ACC * self.wind * dt
            a["vy"] += G * dt
            x0, y0 = a["x"], a["y"]
            x1, y1 = x0 + a["vx"] * dt, y0 + a["vy"] * dt
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 4))
            consumed = False
            for i in range(1, n + 1):
                t = i / n
                if self.arrow_collide(a, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t):
                    consumed = True
                    break
            if consumed:
                continue

            # deteksi menghindar: panah musuh melewati pemain yang sedang melompat
            if a["owner"] == "e" and not a["passed"] and x1 <= PX < x0:
                a["passed"] = True
                if self.jump_off < -18 and TOWER_TOP - 70 <= (y0 + y1) / 2 <= TOWER_TOP:
                    self.dodges += 1
                    self.floater("Menghindar!", PX, self.feet_y() - 100, "#7dd3fc")
                    if self.dodges >= 3:
                        self.unlock_ach("agile")

            a["x"], a["y"] = x1, y1
            if a["kind"] in ("fire", "explosive"):
                a["trail"].append((x1, y1))
                a["trail"] = a["trail"][-8:]
            if y1 > H + 80 or x1 < -100 or x1 > W + 100:
                a["alive"] = False
        self.arrows = [a for a in self.arrows if a["alive"]]

    # ------------------------------------------------------------------ EFEK
    def burst(self, x, y, colors, n, speed):
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(0.2, 1.0) * speed
            life = random.uniform(0.3, 0.7)
            self.particles.append([x, y, math.cos(ang) * sp, math.sin(ang) * sp - 40,
                                   life, life, random.choice(colors), random.uniform(1.5, 3.5)])

    def floater(self, text, x, y, color):
        self.floaters.append([text, x, y, 1.1, color])

    def spawn_ragdoll(self, x, y, push, body, helmet):
        def part(kind, px_, py_, ln, w, col):
            return dict(kind=kind, x=px_, y=py_, vx=push + random.uniform(-140, 140),
                        vy=random.uniform(-330, -60), ang=random.uniform(0, math.pi),
                        vang=random.uniform(-9, 9), len=ln, w=w, col=col)
        self.ragdolls += [
            part("head", x, y - 58, HEAD_R, 0, body),
            part("line", x, y - 36, 24, 9, body),
            part("line", x - 4, y - 13, 26, 7, body),
            part("line", x + 4, y - 13, 26, 7, body),
            part("line", x, y - 42, 22, 5, body),
            part("line", x, y - 42, 22, 5, body),
            part("line", x, y - 42, 44, 4, "#f59e0b"),      # busur
        ]

    def update_effects(self, dt, now):
        for p in self.ragdolls:
            p["vy"] += 900 * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["ang"] += p["vang"] * dt
        self.ragdolls = [p for p in self.ragdolls if p["y"] < H + 120]

        for p in self.particles:
            p[3] += 600 * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

        for f in self.effects:
            f[2] += dt
        self.effects = [f for f in self.effects if f[2] < f[3]]

        for f in self.floaters:
            f[2] -= 30 * dt
            f[3] -= dt
        self.floaters = [f for f in self.floaters if f[3] > 0]
        self.toasts = [t for t in self.toasts if t[1] > now]

    # ------------------------------------------------------------------ UPDATE
    def update(self, dt):
        now = time.perf_counter()

        # angin berubah halus
        self.wind += (self.wind_target - self.wind) * min(1.0, dt * 1.5)
        for s in self.streaks:
            s[0] += (self.wind * 22 + (30 if self.wind >= 0 else -30)) * dt
            if s[0] > W + 40:
                s[0] = -40
            elif s[0] < -40:
                s[0] = W + 40

        self.hurt = max(0.0, self.hurt - dt)
        self.update_effects(dt, now)

        # stamina & lompat
        self.stamina = min(STAMINA_MAX, self.stamina + STAMINA_REGEN * dt)
        if self.jump_vy != 0 or self.jump_off < 0:
            self.jump_vy += JUMP_G * dt
            self.jump_off += self.jump_vy * dt
            if self.jump_off >= 0:
                self.jump_off, self.jump_vy = 0.0, 0.0
            self.update_aim()

        if self.state == "play":
            if self.charging:
                self.power = min(1.0, self.power + dt / CHARGE_TIME)
            self.update_enemies(dt, now)
            self.update_arrows(dt)

            if self.hp <= 0 and not self.player_dead:
                self.player_dead = True
                self.charging = False
                self.spawn_ragdoll(PX, self.feet_y(), 0.0, "#d9d9d9", "#8a8a8a")
                self.best = max(self.best, self.score)
                self.save_progress()
                self.state, self.next_state, self.wait_until = "wait", "dead", now + 1.6
            elif all(not e.alive for e in self.enemies):
                self.clear_level(now)
        elif self.state == "wait":
            self.update_arrows(dt)
            if now >= self.wait_until:
                self.state = self.next_state

    def clear_level(self, now):
        self.score += 200 * (self.level + 1)
        if not self.damage_taken and self.level >= 2:
            self.unlock_ach("untouched")
        new = UNLOCK_AFTER.get(self.level + 1)
        self.reward = None
        if new and new not in self.unlocked:
            self.unlocked.append(new)
            self.reward = new
        last = self.level == len(LEVELS) - 1
        if last:
            self.unlock_ach("legend")
        self.best = max(self.best, self.score)
        self.save_progress()
        self.charging = False
        self.state = "wait"
        self.next_state = "victory" if last else "levelup"
        self.wait_until = now + 1.6

    # ------------------------------------------------------------------ PRIMITIF GAMBAR
    def _l(self, *a, **k):
        return self.c.create_line(*a, tags="dyn", **k)

    def _o(self, *a, **k):
        return self.c.create_oval(*a, tags="dyn", **k)

    def _p(self, *a, **k):
        return self.c.create_polygon(*a, tags="dyn", **k)

    def _r(self, *a, **k):
        return self.c.create_rectangle(*a, tags="dyn", **k)

    def _a(self, *a, **k):
        return self.c.create_arc(*a, tags="dyn", **k)

    def _t(self, x, y, text, fill="white", size=11, bold=False, anchor="center", font="Segoe UI"):
        return self.c.create_text(x, y, text=text, fill=fill, anchor=anchor,
                                  font=(font, size, "bold" if bold else "normal"), tags="dyn")

    # ------------------------------------------------------------------ GAMBAR LATAR
    def draw_bg(self):
        c = self.c
        c.delete("bg")
        bg = BG_COLORS[self.level]
        c.configure(bg=bg)
        rng = random.Random(self.level * 13 + 5)
        for _ in range(70):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            r = rng.choice([1, 1, 1.5, 2])
            c.create_oval(x - r, y - r, x + r, y + r, fill=shade(bg, rng.choice([18, 28, 38])),
                          outline="", tags="bg")
        c.create_polygon(150, 210, 250, 310, 150, 410, 50, 310, fill=shade(bg, 8), outline="", tags="bg")
        c.create_line(180, 170, 350, 160, 520, 168, smooth=True, fill=shade(bg, 12), width=2, tags="bg")
        c.create_line(640, 110, 800, 96, 930, 104, smooth=True, fill=shade(bg, 10), width=2, tags="bg")

        # menara pemain
        c.create_rectangle(TOWER_X0, TOWER_TOP, TOWER_X1, H, fill="#5f5f5f", outline="", tags="bg")
        for yy in range(TOWER_TOP, H, 70):
            c.create_line(TOWER_X0, yy, TOWER_X1, yy, fill="#545454", width=2, tags="bg")
        for i, yy in enumerate(range(TOWER_TOP, H, 70)):
            off = 0 if i % 2 == 0 else 38
            for xx in range(TOWER_X0 + 76 - off, TOWER_X1, 76):
                c.create_line(xx, yy, xx, yy + 70, fill="#545454", width=2, tags="bg")
        for bx in (TOWER_X0, TOWER_X1 - 24):
            c.create_rectangle(bx, TOWER_TOP - 16, bx + 24, TOWER_TOP, fill="#5f5f5f", outline="", tags="bg")

        # platform musuh
        for (x0, y0, x1, y1) in self.solids[1:]:
            for bx in range(int(x0), int(x1), BLOCK):
                c.create_rectangle(bx, y0, bx + BLOCK, y1, fill="#6b6b6b", outline="#575757",
                                   width=2, tags="bg")

    # ------------------------------------------------------------------ GAMBAR OBJEK
    def draw_arrow(self, x, y, ang, head_col="#e5e7eb", trail=None):
        """(x, y) = ujung anak panah."""
        dx, dy = math.cos(ang), math.sin(ang)
        px_, py_ = -dy, dx
        tx, ty = x - dx * ARROW_LEN, y - dy * ARROW_LEN
        if trail:
            cols = ["#7c2d12", "#9a3412", "#c2410c", "#ea580c", "#f97316", "#fb923c", "#fdba74", "#fed7aa"]
            for i, (tx_, ty_) in enumerate(trail):
                r = 2 + i * 0.4
                self._o(tx_ - r, ty_ - r, tx_ + r, ty_ + r, fill=cols[min(i, 7)], outline="")
        self._l(tx, ty, x, y, width=3, fill="#e5e7eb")
        self._p(x, y, x - dx * 12 + px_ * 4, y - dy * 12 + py_ * 4,
                x - dx * 12 - px_ * 4, y - dy * 12 - py_ * 4, fill=head_col)
        for s in (1, -1):
            self._l(tx, ty, tx + dx * 13 + px_ * 5 * s, ty + dy * 13 + py_ * 5 * s, width=2, fill="#e5e7eb")

    def draw_archer(self, x, y, d, pull, col, helmet, nock_col, flash):
        if flash:
            col = "#ff8a8a"
        self._l(x, y - 26, x - 9, y, width=7, fill=col, capstyle="round")
        self._l(x, y - 26, x + 9, y, width=7, fill=col, capstyle="round")
        self._l(x, y - 26, x, y - 47, width=9, fill=col, capstyle="round")
        self._o(x - 11, y - 69, x + 11, y - 47, fill=col, outline="")
        if helmet:
            self._a(x - 12, y - 70, x + 12, y - 46, start=0, extent=180, fill=helmet, outline="")

        dx, dy = d
        sx, sy = x, y - 42
        bx, by = sx + dx * BOW_OFF, sy + dy * BOW_OFF
        nx, ny = bx - dx * PULL_MAX * pull, by - dy * PULL_MAX * pull
        self._l(sx, sy, nx, ny, width=5, fill=col, capstyle="round")      # tangan belakang
        self._l(sx, sy, bx, by, width=6, fill=col, capstyle="round")      # tangan depan
        px_, py_ = -dy, dx
        pts = []
        for i in range(-8, 9):
            t = i / 8
            pts += [bx + px_ * t * 30 + dx * 9 * (1 - t * t), by + py_ * t * 30 + dy * 9 * (1 - t * t)]
        self._l(*pts, smooth=True, width=4, fill="#f59e0b", capstyle="round")
        self._l(bx + px_ * 30, by + py_ * 30, nx, ny, bx - px_ * 30, by - py_ * 30, width=1, fill="#fde68a")
        if nock_col:
            self.draw_arrow(nx + dx * ARROW_LEN, ny + dy * ARROW_LEN, math.atan2(dy, dx), nock_col)

    def draw_guide(self):
        dots = self.cfg["guide"]
        if dots <= 0:
            return
        speed = MIN_SPEED + max(self.power, 0.08) * (MAX_SPEED - MIN_SPEED)
        dx, dy = math.cos(self.aim_angle), math.sin(self.aim_angle)
        reach = BOW_OFF + ARROW_LEN - PULL_MAX * self.power
        x, y = PX + dx * reach, self.feet_y() - 42 + dy * reach
        vx, vy = dx * speed, dy * speed
        for i in range(dots):
            vy += G * 0.06
            x += vx * 0.06
            y += vy * 0.06
            if y > H or x > W:
                break
            if i % 2 == 0:
                self._o(x - 2, y - 2, x + 2, y + 2, fill="#ffffff", outline="")

    def icon_arrow(self, x, y, kind, unlocked):
        col = ARROWS[kind]["color"] if unlocked else "#7a7a7a"
        shaft = "#e5e7eb" if unlocked else "#7a7a7a"
        offsets = [-5, 0, 5] if kind == "triple" else [0]
        ln = 26 if kind == "triple" else 34
        for oy in offsets:
            self._l(x, y + oy, x + ln, y + oy, width=2, fill=shaft)
            self._p(x + ln, y + oy, x + ln - 8, y + oy - 4, x + ln - 8, y + oy + 4, fill=col)
        if kind == "explosive":
            for i in range(3):
                self._r(x + 8 + i * 5, y - 7, x + 11 + i * 5, y + 7, fill=col, outline="")

    # ------------------------------------------------------------------ HUD
    def draw_hud(self):
        # kiri atas: tengkorak + jumlah kill
        self._o(18, 14, 34, 30, fill="#f3f4f6", outline="")
        self._r(22, 26, 30, 34, fill="#f3f4f6", outline="")
        self._o(21, 19, 25, 24, fill="#404040", outline="")
        self._o(27, 19, 31, 24, fill="#404040", outline="")
        self._t(44, 24, str(self.kills), size=14, bold=True, anchor="w", font="Courier New")

        # kanan atas: skor
        self._t(W - 20, 22, f"SCORE {self.score}", size=14, bold=True, anchor="e", font="Courier New")
        self._t(W - 20, 44, f"BEST {self.best}", fill="#cbd5e1", size=10, anchor="e", font="Courier New")

        # tengah atas: level + angin
        alive = sum(1 for e in self.enemies if e.alive)
        self._t(W // 2, 20, f"LEVEL {self.level + 1}/{len(LEVELS)} - {self.cfg['name']}   |   Musuh: {alive}",
                size=13, bold=True)
        length = self.wind * 9
        self._t(W // 2 - 70, 48, "ANGIN", fill="#cbd5e1", size=9, bold=True)
        self._l(W // 2, 48, W // 2 + length, 48, width=4, fill="#f59e0b",
                arrow=tk.LAST if abs(length) > 4 else None, arrowshape=(10, 12, 5))
        self._t(W // 2 + 70, 48, f"{abs(self.wind):.1f} m/s", fill="#cbd5e1", size=10)

        # panel di menara
        for i, k in enumerate(ORDER):
            y = 452 + i * 34
            ok = k in self.unlocked
            spec = ARROWS[k]
            self.icon_arrow(52, y, k, ok)
            self._o(92, y - 8, 108, y + 8, outline="#e5e7eb" if ok else "#7a7a7a", width=2)
            if self.sel == k:
                self._o(96, y - 4, 104, y + 4, fill="#e5e7eb", outline="")
            self._t(120, y, str(i + 1), fill="#f59e0b" if ok else "#7a7a7a", size=12, bold=True)
            if ok and spec["ammo"] is not None:
                self._t(134, y, f"x{self.ammo[k]}", size=9, anchor="w")
            elif not ok:
                self._t(134, y, "kunci", fill="#8a8a8a", size=8, anchor="w")

        hp = max(0.0, self.hp)
        self._r(176, 440, 262, 458, fill="#7f1d1d", outline="")
        self._r(176, 440, 176 + 86 * hp / PLAYER_HP, 458, fill="#ef4444", outline="")
        self._t(219, 449, str(int(hp)), size=10, bold=True)
        self._r(176, 464, 262, 480, fill="#1e3a8a", outline="")
        self._r(176, 464, 176 + 86 * self.stamina / STAMINA_MAX, 480, fill="#3b82f6", outline="")
        ready = self.stamina >= JUMP_COST
        self._r(176, 490, 262, 528, fill="#d1d5db" if ready else "#8a8a8a", outline="")
        self._t(219, 503, "JUMP", fill="#374151", size=11, bold=True)
        self._t(219, 519, f"SPACE  -{int(JUMP_COST)}", fill="#2563eb", size=8, bold=True)
        self._t(56, 585, "A = pencapaian", fill="#a3a3a3", size=9, anchor="w")

        self._t(W // 2 + 150, H - 14,
                "Mouse: bidik  |  Tahan klik: tarik  |  Lepas: tembak  |  1-4: panah  |  G: garis bantu  |  R: ulang",
                fill="#a3a3a3", size=9)

        # notifikasi pencapaian
        for i, (title, _) in enumerate(self.toasts[:3]):
            y = 66 + i * 44
            self._r(W - 300, y, W - 16, y + 38, fill="#1f2937", outline="#facc15", width=2)
            self._t(W - 158, y + 19, f"★ Pencapaian: {title}", fill="#facc15", size=11, bold=True)

    def draw_panel(self, title, lines, footer, color="#facc15"):
        height = 130 + 30 * len(lines)
        top = max(60, (H - height) // 2 - 20)
        self._r(W / 2 - 290, top, W / 2 + 290, top + height, fill="#1f2937", outline=color, width=3)
        self._t(W / 2, top + 38, title, fill=color, size=22, bold=True)
        for i, ln in enumerate(lines):
            text, col = ln if isinstance(ln, tuple) else (ln, "white")
            self._t(W / 2, top + 82 + 30 * i, text, fill=col, size=13)
        self._t(W / 2, top + height - 24, footer, fill="#94a3b8", size=11)

    def draw_overlay(self):
        cfg = self.cfg
        if self.state == "intro":
            wind = "Tanpa angin" if cfg["wind"] == 0 else f"Angin hingga {cfg['wind']:.1f} m/s"
            self.draw_panel(f"LEVEL {self.level + 1}: {cfg['name'].upper()}",
                            [f"Kalahkan {len(self.enemies)} musuh pemanah",
                             wind,
                             "Bidik kepala = damage 2x  |  Lompat untuk menghindar"],
                            "Klik untuk mulai")
        elif self.state == "levelup":
            lines = [f"Bonus level: +{200 * (self.level + 1)}", f"Skor: {self.score}",
                     "Nyawa dipulihkan +50 saat lanjut"]
            if self.reward:
                idx = ORDER.index(self.reward) + 1
                lines.append((f"HADIAH: {ARROWS[self.reward]['name']} terbuka! (tekan {idx})", "#facc15"))
            self.draw_panel(f"LEVEL {self.level + 1} SELESAI!", lines,
                            f"Klik untuk lanjut ke Level {self.level + 2}", "#4ade80")
        elif self.state == "dead":
            self.draw_panel("KAMU GUGUR",
                            [f"Mencapai Level {self.level + 1}", f"Skor: {self.score}   |   Kill: {self.kills}",
                             f"Skor terbaik: {self.best}"],
                            "Klik untuk mulai lagi dari Level 1", "#f87171")
        elif self.state == "victory":
            self.draw_panel("SELAMAT! SEMUA LEVEL TUNTAS",
                            [f"Total skor: {self.score}", f"Total kill: {self.kills}",
                             f"Skor terbaik: {self.best}"],
                            "Klik untuk main dari awal")
        if self.show_ach:
            self.draw_ach_panel()

    def draw_ach_panel(self):
        n = len(ACHIEVEMENTS)
        height = 120 + 32 * n
        top = max(20, (H - height) // 2)
        self._r(W / 2 - 320, top, W / 2 + 320, top + height, fill="#111827", outline="#facc15", width=3)
        self._t(W / 2, top + 34, f"PENCAPAIAN  ({len(self.done)}/{n})", fill="#facc15", size=20, bold=True)
        for i, (key, (title, desc)) in enumerate(ACHIEVEMENTS.items()):
            y = top + 78 + i * 32
            ok = key in self.done
            self._r(W / 2 - 290, y - 9, W / 2 - 272, y + 9, outline="#facc15" if ok else "#6b7280", width=2)
            if ok:
                self._l(W / 2 - 286, y, W / 2 - 281, y + 5, W / 2 - 274, y - 6, width=2, fill="#4ade80")
            self._t(W / 2 - 255, y, title, fill="white" if ok else "#6b7280", size=12, bold=True, anchor="w")
            self._t(W / 2 - 60, y, desc, fill="#cbd5e1" if ok else "#6b7280", size=11, anchor="w")
        self._t(W / 2, top + height - 22, "Tekan A untuk menutup", fill="#94a3b8", size=10)

    # ------------------------------------------------------------------ GAMBAR UTAMA
    def draw(self):
        c = self.c
        c.delete("dyn")

        for x, y in self.streaks:
            ln = 14 + abs(self.wind) * 3
            d = 1 if self.wind >= 0 else -1
            self._l(x, y, x + d * ln, y, fill=shade(BG_COLORS[self.level], 40), width=1)

        for x, y, ang in self.stuck:
            self.draw_arrow(x, y, ang)

        # musuh
        for e in self.enemies:
            if not e.alive:
                continue
            self.draw_archer(e.x, e.y, e.vec(), e.pull, "#f5f5f5", "#9ca3af" if self.level >= 2 else None,
                             "#e5e7eb" if e.state == "aim" else None, e.flash > 0)
            self._r(e.x - 15, e.y - 88, e.x + 15, e.y - 82, fill="#1f1f1f", outline="")
            self._r(e.x - 15, e.y - 88, e.x - 15 + 30 * max(0, e.hp) / e.maxhp, e.y - 82,
                    fill="#ef4444", outline="")

        # ragdoll
        for p in self.ragdolls:
            if p["kind"] == "head":
                self._o(p["x"] - p["len"], p["y"] - p["len"], p["x"] + p["len"], p["y"] + p["len"],
                        fill=p["col"], outline="")
            else:
                ca, sa = math.cos(p["ang"]) * p["len"] / 2, math.sin(p["ang"]) * p["len"] / 2
                self._l(p["x"] - ca, p["y"] - sa, p["x"] + ca, p["y"] + sa, width=p["w"],
                        fill=p["col"], capstyle="round")

        # pemain
        if not self.player_dead:
            d = (math.cos(self.aim_angle), math.sin(self.aim_angle))
            nock = ARROWS[self.sel]["color"] if self.state in ("play", "intro") else None
            self.draw_archer(PX, self.feet_y(), d, self.power if self.charging else 0.0,
                             "#d9d9d9", "#7a7a7a", nock, self.hurt > 0)
            if self.charging:
                self._r(PX - 22, self.feet_y() - 96, PX + 22, self.feet_y() - 90, outline="#e5e7eb")
                col = "#4caf50" if self.power < 0.5 else "#ffc107" if self.power < 0.8 else "#f44336"
                self._r(PX - 21, self.feet_y() - 95, PX - 21 + 42 * self.power, self.feet_y() - 91,
                        fill=col, outline="")
                if self.show_guide:
                    self.draw_guide()

        # panah terbang
        for a in self.arrows:
            hc = ARROWS[a["kind"]]["color"] if a["owner"] == "p" else "#e5e7eb"
            self.draw_arrow(a["x"], a["y"], math.atan2(a["vy"], a["vx"]), hc, a["trail"] or None)

        # partikel & efek
        for p in self.particles:
            r = p[7] * (p[4] / p[5])
            self._o(p[0] - r, p[1] - r, p[0] + r, p[1] + r, fill=p[6], outline="")
        for x, y, t, mt, R in self.effects:
            r = R * (t / mt)
            self._o(x - r, y - r, x + r, y + r, outline="#fbbf24", width=3)
            self._o(x - r * 0.6, y - r * 0.6, x + r * 0.6, y + r * 0.6, outline="#ef4444", width=2)
        for text, x, y, life, col in self.floaters:
            self._t(x, y, text, fill=col, size=14, bold=True)

        self.draw_hud()
        if self.hurt > 0:
            self._r(3, 3, W - 3, H - 3, outline="#ef4444", width=8)
        self.draw_overlay()

    # ------------------------------------------------------------------ LOOP
    def loop(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.033)
        self.last = now
        if not self.show_ach:
            self.update(dt)
        self.draw()
        self.root.after(16, self.loop)


if __name__ == "__main__":
    root = tk.Tk()
    ArcheryGame(root)
    root.mainloop()