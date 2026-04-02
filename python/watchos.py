# =============================================================================
#  watchos.py — Watch UI Layer (runs as kernel processes)
# =============================================================================
#
#  REAL OS CONCEPT:
#  This is "user space" — the apps and UI that run ON TOP of the kernel.
#  They never access hardware directly. Everything goes through syscalls.
#
#  Think of this like:
#    Android / WearOS   = user space apps running on Linux kernel
#    Our watchos.py     = user space UI running on our AJX OS kernel
#
#  Each "screen" (watch face, fitness, heart rate etc.) is actually a
#  kernel process with a specific priority and update interval.
#  The kernel scheduler decides when each one gets CPU time.
# =============================================================================

import time
import math
from kernel import Kernel, SyscallNum
from hal import (SENSOR_HEART_RATE, SENSOR_ACCELERO, SENSOR_BATTERY,
                 BTN_SWIPE_LEFT, BTN_SWIPE_RIGHT)
from drivers import DisplayDriver

# Color palette — shared across all UI processes
C = DisplayDriver.COLORS


# =============================================================================
#  RENDERER
#  This is THE draw function. The kernel calls it every frame.
#  It reads kernel state and draws the correct screen.
#  Like a compositor / window manager.
# =============================================================================

class WatchRenderer:
    """
    Composites all screens onto the display.
    The kernel holds a reference and calls render() each frame.
    """

    SCREEN_ORDER_H = ["fitness", "home", "heart"]   # horizontal axis

    def __init__(self, kernel: Kernel, display: DisplayDriver):
        self._k   = kernel
        self._d   = display
        self._anim = {}      # animation state per screen transition
        self._last_screen = None
        self._transition  = None   # ("from", "to", "dir", start_time)

    def render(self, display: DisplayDriver):
        """
        Main render call — runs on the display thread.
        Reads kernel sys_data and paints the correct screen.
        """
        d   = display
        sys = self._k.get_sys_data()
        scr = sys.get("screen", "home")
        nav = sys.get("nav_dir", "right")

        # Clear framebuffer
        d.clear()

        # Draw current screen
        self._draw_screen(d, scr, sys)

        # Status bar overlaid on top of everything
        self._draw_status_bar(d, sys)

        d.update()
        sys["screen_dirty"] = False

    def _draw_screen(self, d, screen, sys):
        draw_fn = {
            "boot":      self._screen_boot,
            "home":      self._screen_home,
            "fitness":   self._screen_fitness,
            "heart":     self._screen_heart,
            "notifs":    self._screen_notifs,
            "settings":  self._screen_settings,
            "apps":      self._screen_apps,
            "stopwatch": self._screen_stopwatch,
            "music":     self._screen_music,
            "weather":   self._screen_weather,
            "maps":      self._screen_maps,
        }.get(screen, self._screen_home)
        draw_fn(d, sys)

    # ── STATUS BAR ─────────────────────────────────────────────────────────────

    def _draw_status_bar(self, d, sys):
        W = 340
        # Background
        d.draw_rect(0, 0, W, 30, fill=C["bg"], outline="")

        # Time
        t = time.strftime("%H:%M")
        d.draw_text(20, 15, t, size=9, color=C["dim"], font="Courier", anchor="w")

        # Bluetooth dot
        bt_color = C["green"] if sys["settings"]["bluetooth"] else C["dim"]
        d.draw_circle(W//2, 15, 3, fill=bt_color, outline="")

        # Battery
        bat = sys["sensor_cache"].get(SENSOR_BATTERY, {})
        pct = bat.get("level", 87)
        d.draw_text(W - 20, 15, f"{int(pct)}%", size=9, color=C["dim"], font="Courier", anchor="e")
        # Battery bar
        bx = W - 58
        d.draw_rect(bx, 10, 32, 10, fill=C["surface"], outline=C["dim"], radius=2)
        fill_w = int((pct / 100) * 28)
        bar_color = C["green"] if pct > 30 else C["amber"] if pct > 15 else C["red"]
        if fill_w > 0:
            d.draw_rect(bx + 2, 12, fill_w, 6, fill=bar_color, outline="")

    # ── BOOT SCREEN ────────────────────────────────────────────────────────────

    def _screen_boot(self, d, sys):
        W = H = 340
        uptime = sys.get("boot_progress", 0)

        d.draw_text(W//2, 120, "AJX", size=32, color=C["cyan"],
                    font="Courier", bold=True)
        d.draw_text(W//2, 158, "OS", size=32, color=C["cyan"],
                    font="Courier", bold=True)
        d.draw_text(W//2, 200, "v1.0.0-alpha", size=10,
                    color=C["dim"], font="Courier")
        d.draw_text(W//2, 220, "kernel init...", size=9,
                    color=C["dim"], font="Courier")

        # Boot progress bar
        bar_w = 180
        bx = (W - bar_w) // 2
        d.draw_rect(bx, 250, bar_w, 4, fill=C["surface2"], outline="")
        fill = int(bar_w * min(uptime, 1.0))
        if fill > 0:
            d.draw_rect(bx, 250, fill, 4, fill=C["cyan"], outline="")

    # ── WATCH FACE ─────────────────────────────────────────────────────────────

    def _screen_home(self, d, sys):
        W = H = 340
        CX, CY = W // 2, 148   # slightly higher center
        R  = 98

        now = time.localtime()
        h, m, s = now.tm_hour, now.tm_min, now.tm_sec

        # Outer ring
        d.draw_circle(CX, CY, R + 4, fill=C["bg"], outline=C["surface2"])

        # Tick marks
        for i in range(60):
            angle    = math.radians(i * 6 - 90)
            is_major = (i % 5 == 0)
            r_outer  = R
            r_inner  = R - (9 if is_major else 4)
            x1 = CX + r_outer * math.cos(angle)
            y1 = CY + r_outer * math.sin(angle)
            x2 = CX + r_inner * math.cos(angle)
            y2 = CY + r_inner * math.sin(angle)
            color = C["cyan"] if is_major else C["surface2"]
            d.draw_line(x1, y1, x2, y2, color=color, width=2 if is_major else 1)

        # Hour hand — from center outward only
        h_angle = math.radians((h % 12) * 30 + m * 0.5 - 90)
        d.draw_line(CX, CY,
                    CX + 50 * math.cos(h_angle),
                    CY + 50 * math.sin(h_angle),
                    color=C["text"], width=5)

        # Minute hand — from center outward only
        m_angle = math.radians(m * 6 + s * 0.1 - 90)
        d.draw_line(CX, CY,
                    CX + 72 * math.cos(m_angle),
                    CY + 72 * math.sin(m_angle),
                    color=C["cyan"], width=3)

        # Second hand — small tail + long tip, all from center
        s_angle = math.radians(s * 6 - 90)
        # tail (opposite direction)
        d.draw_line(CX, CY,
                    CX - 18 * math.cos(s_angle),
                    CY - 18 * math.sin(s_angle),
                    color=C["amber"], width=1)
        # tip
        d.draw_line(CX, CY,
                    CX + 82 * math.cos(s_angle),
                    CY + 82 * math.sin(s_angle),
                    color=C["amber"], width=1)

        # Center dot — drawn last so it covers hand bases
        d.draw_circle(CX, CY, 6, fill=C["bg"], outline=C["cyan"])
        d.draw_circle(CX, CY, 2, fill=C["cyan"], outline="")

        # Date — positioned inside clock at 3 o'clock area
        days   = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
        months = ["JAN","FEB","MAR","APR","MAY","JUN",
                  "JUL","AUG","SEP","OCT","NOV","DEC"]
        date_str = f"{days[now.tm_wday]} {now.tm_mday:02d} {months[now.tm_mon-1]}"
        # Small date box at 3 o'clock position
        d.draw_rect(CX + 52, CY - 10, 50, 20, fill=C["surface2"], outline=C["border"], radius=4)
        d.draw_text(CX + 77, CY, date_str, size=7, color=C["dim"], font="Courier")

        # Complications — moved down with more space
        sen = sys["sensor_cache"]
        steps = sen.get(SENSOR_ACCELERO, {}).get("steps", 0)
        hr    = sen.get(SENSOR_HEART_RATE, {}).get("bpm", "--")
        cals  = sen.get(SENSOR_ACCELERO, {}).get("calories", 0)

        self._complication(d, 58,  285, "👣", str(steps), "STEPS")
        self._complication(d, 170, 285, "❤️", str(hr),    "BPM")
        self._complication(d, 282, 285, "🔥", str(cals),  "KCAL")

        # Swipe nav dots
        dot_y = 325
        dots  = [("fitness", 148), ("home", 170), ("heart", 192)]
        for name, x in dots:
            color = C["cyan"] if name == sys["screen"] else C["surface2"]
            r     = 5 if name == "home" else 3
            d.draw_circle(x, dot_y, r, fill=color, outline="")

    def _complication(self, d, cx, cy, icon, val, label):
        # Background pill
        d.draw_rect(cx - 40, cy - 26, 80, 50, fill=C["surface"],
                    outline=C["border"], radius=12)
        # Icon left of center, value right of center — balanced
        d.draw_text(cx - 14, cy - 8, icon, size=11, anchor="center")
        d.draw_text(cx + 12, cy - 8, val,  size=11, color=C["text"],
                    font="Courier", bold=True, anchor="center")
        # Label centered at bottom
        d.draw_text(cx, cy + 14, label, size=7, color=C["dim"],
                    font="Courier", anchor="center")

    # ── FITNESS ────────────────────────────────────────────────────────────────

    def _screen_fitness(self, d, sys):
        W = H = 340
        CX, CY = W // 2, 155
        sen    = sys["sensor_cache"]
        acc    = sen.get(SENSOR_ACCELERO, {})
        steps  = acc.get("steps", 0)
        cals   = acc.get("calories", 0)
        active = acc.get("active_min", 0)
        dist   = acc.get("distance", 0.0)

        d.draw_text(W // 2, 42, "ACTIVITY", size=10, color=C["dim"], font="Courier")

        # Activity rings (3 concentric arcs)
        rings = [
            (steps,  10000, 80, C["green"], "STEPS"),
            (cals,   600,   60, C["red"],   "CAL"),
            (active, 60,    40, C["cyan"],  "MOVE"),
        ]
        for val, goal, r, color, label in rings:
            pct    = min(val / goal, 1.0)
            extent = pct * 359.9   # degrees (0 = no fill, 359.9 = full)
            # Track (background arc)
            d.draw_arc(CX, CY, r, 90, -359.9, color=C["surface2"], width=8)
            # Fill arc
            if extent > 1:
                d.draw_arc(CX, CY, r, 90, -extent, color=color, width=8)

        # Center text
        d.draw_text(CX, CY - 8, str(steps), size=16, color=C["text"],
                    font="Courier", bold=True)
        d.draw_text(CX, CY + 10, "steps", size=9, color=C["dim"], font="Courier")

        # Stats grid — 2 columns, perfectly centered
        col1 = W // 2 - 82   # left col center
        col2 = W // 2 + 82   # right col center
        row1 = 268
        row2 = 310
        stats = [
            (f"{cals}",      "kcal",   col1, row1),
            (f"{active}m",   "active", col2, row1),
            (f"{dist:.1f}",  "km",     col1, row2),
            (f"{int(steps/100)}%", "goal", col2, row2),
        ]
        for val, label, x, y in stats:
            d.draw_rect(x - 68, y - 24, 136, 46, fill=C["surface"],
                        outline=C["border"], radius=10)
            d.draw_text(x, y - 6,  val,   size=14, color=C["text"],
                        font="Courier", bold=True)
            d.draw_text(x, y + 12, label, size=8,  color=C["dim"],
                        font="Courier")

    # ── HEART RATE ─────────────────────────────────────────────────────────────

    def _screen_heart(self, d, sys):
        W = 340
        bpm = sys["sensor_cache"].get(SENSOR_HEART_RATE, {}).get("bpm", 72)

        d.draw_text(W // 2, 42, "HEART RATE", size=10, color=C["dim"], font="Courier")

        # Big BPM number
        d.draw_text(W // 2, 120, str(bpm), size=52, color=C["red"],
                    font="Courier", bold=True)
        d.draw_text(W // 2, 158, "BPM", size=12, color=C["dim"], font="Courier")

        # Animated ECG line (using sine wave approximation)
        ecg_y = 210
        points = []
        t      = time.monotonic()
        for i in range(0, W - 40):
            x   = 20 + i
            pos = (i / 30 + t * 2) % 1.0
            # Approximate ECG shape
            if 0.3 < pos < 0.35:
                y = ecg_y - 40 * math.sin((pos - 0.3) / 0.05 * math.pi)
            elif 0.35 < pos < 0.4:
                y = ecg_y + 15 * math.sin((pos - 0.35) / 0.05 * math.pi)
            else:
                y = ecg_y + math.sin(pos * math.pi * 2) * 3
            points.extend([x, y])

        # Draw ECG as connected line segments
        for i in range(0, len(points) - 4, 2):
            d.draw_line(points[i], points[i+1], points[i+2], points[i+3],
                        color=C["red"], width=2)

        # Heart rate zones
        zones = [
            (0,  60,  "REST",    "REST"),
            (60, 80,  "FAT BURN","FAT\nBURN"),
            (80, 90,  "CARDIO",  "CARDIO"),
            (90, 200, "PEAK",    "PEAK"),
        ]
        zone_x = 18
        for lo, hi, _, label in zones:
            active = lo <= bpm < hi
            bg     = C["red"] if active else C["surface"]
            tc     = C["white"] if active else C["dim"]
            d.draw_rect(zone_x, 262, 72, 34, fill=bg, outline=C["border"], radius=10)
            parts  = label.split("\n")
            if len(parts) == 2:
                d.draw_text(zone_x + 36, 272, parts[0], size=7, color=tc, font="Courier")
                d.draw_text(zone_x + 36, 284, parts[1], size=7, color=tc, font="Courier")
            else:
                d.draw_text(zone_x + 36, 279, parts[0], size=7, color=tc, font="Courier")
            zone_x += 76

    # ── NOTIFICATIONS ──────────────────────────────────────────────────────────

    def _screen_notifs(self, d, sys):
        W = 340
        d.draw_text(W // 2, 42, "NOTIFICATIONS", size=10, color=C["dim"], font="Courier")

        notifs = sys.get("notifications", [])
        if not notifs:
            d.draw_text(W // 2, 170, "No notifications", size=11,
                        color=C["dim"], font="Courier")
            return

        y = 70
        for n in reversed(notifs[-4:]):
            d.draw_rect(20, y, W - 40, 54, fill=C["surface"],
                        outline=C["border"], radius=12)
            d.draw_text(30, y + 14, n["icon"], size=14, anchor="w")
            d.draw_text(55, y + 12, n["app"],  size=8,
                        color=C["dim"], font="Courier", anchor="w")
            d.draw_text(55, y + 30, n["text"][:28], size=10,
                        color=C["text"], font="Courier", anchor="w")
            d.draw_text(W - 28, y + 12, n["time"], size=8,
                        color=C["dim"], font="Courier", anchor="e")
            y += 62

    # ── QUICK SETTINGS ─────────────────────────────────────────────────────────

    def _screen_settings(self, d, sys):
        W = 340
        d.draw_text(W // 2, 42, "SETTINGS", size=10, color=C["dim"], font="Courier")

        s     = sys["settings"]
        tiles = [
            ("🔵", "BLUETOOTH", "bluetooth", 22,  72),
            ("📶", "WI-FI",     "wifi",      178, 72),
            ("🌙", "DND",       "dnd",        22, 172),
            ("💡", "ALWAYS ON", "aod",       178, 172),
        ]

        for icon, label, key, x, y in tiles:
            on     = s.get(key, False)
            bg     = C["surface"]
            border = C["cyan"] if on else C["border"]
            tc     = C["cyan"] if on else C["dim"]
            # Tile is 136px wide
            d.draw_rect(x, y, 136, 72, fill=bg, outline=border, radius=14)
            d.draw_text(x + 22, y + 36, icon, size=20, anchor="center")
            d.draw_text(x + 78, y + 26, "ON" if on else "OFF",
                        size=11, color=tc, font="Courier", bold=on, anchor="center")
            d.draw_text(x + 78, y + 48, label, size=8,
                        color=C["dim"], font="Courier", anchor="center")

        # Brightness slider
        bright = s.get("brightness", 70)
        bx, by = 22, 262
        d.draw_text(W // 2, by, f"BRIGHTNESS  {bright}%", size=9,
                    color=C["dim"], font="Courier")
        d.draw_rect(bx, by + 18, 296, 10, fill=C["surface2"], outline="", radius=5)
        fill_w = int(296 * bright / 100)
        d.draw_rect(bx, by + 18, max(fill_w, 1), 10, fill=C["amber"], outline="", radius=5)

        d.draw_text(W // 2, 308, "PgUp / PgDn = adjust brightness",
                    size=7, color=C["dim"], font="Courier")

    # ── APP LAUNCHER ───────────────────────────────────────────────────────────

    _APP_REGISTRY = [
        ("⏰", "CLOCK",    "home"),
        ("🏃", "FITNESS",  "fitness"),
        ("❤️", "HEART",    "heart"),
        ("🎵", "MUSIC",    "music"),
        ("⏱️", "STOPWATCH","stopwatch"),
        ("🔔", "NOTIFS",   "notifs"),
        ("⚙️", "SETTINGS", "settings"),
        ("⛅", "WEATHER",  "weather"),
        ("🌍", "MAPS",     "maps"),
    ]

    def _screen_apps(self, d, sys):
        W = 340
        d.draw_text(W // 2, 35, "APPS", size=10, color=C["dim"], font="Courier")

        cols   = 3
        icon_r = 32       # circle radius — slightly smaller for cleaner fit
        pad_y  = 52       # top margin (below title)
        cell_h = 84       # vertical spacing per row
        # Explicit column centers: divide 340 into 3 equal zones
        col_centers = [57, 170, 283]

        for i, (icon, name, screen) in enumerate(self._APP_REGISTRY):
            col = i % cols
            row = i // cols
            cx  = col_centers[col]
            cy  = pad_y + icon_r + row * cell_h

            # All circles same size and style
            bg     = C["surface2"]
            border = C["cyan"]   # all same cyan border
            d.draw_circle(cx, cy, icon_r, fill=bg, outline=border)
            # Draw icon centered in circle — anchor center means (cx,cy) is middle
            d.draw_text(cx, cy, icon, size=17, anchor="center")
            d.draw_text(cx, cy + icon_r + 12, name,
                        size=7, color=C["text"], font="Courier", anchor="center")

        d.draw_text(W // 2, 324, "select app  |  Q / C = back",
                    size=7, color=C["dim"], font="Courier")

    # ── STOPWATCH ──────────────────────────────────────────────────────────────



    # -- WEATHER --

    def _screen_weather(self, d, sys):
        import random, math
        W = 340
        d.draw_text(W // 2, 38, "WEATHER", size=10, color=C["dim"], font="Courier")

        # Fake weather data (would come from network in real OS)
        weather = sys.get("weather", {
            "city":     "New Delhi",
            "temp":     32,
            "feels":    35,
            "humidity": 48,
            "condition":"Partly Cloudy",
            "wind":     14,
            "high":     36,
            "low":      24,
        })

        # Big temperature
        d.draw_text(W // 2, 90, "🌤️", size=36)
        d.draw_text(W // 2, 145, f"{weather['temp']}°C", size=38,
                    color=C["amber"], font="Courier", bold=True)
        d.draw_text(W // 2, 183, weather["condition"], size=10,
                    color=C["dim"], font="Courier")
        d.draw_text(W // 2, 200, weather["city"], size=9,
                    color=C["text"], font="Courier")

        # Stats row — 3 equal columns across 340px
        stat_y = 220
        stats = [
            ("💧", f"{weather['humidity']}%", "HUMIDITY",  57),
            ("🌡️", f"{weather['feels']}°",    "FEELS",    170),
            ("💨", f"{weather['wind']}km/h",  "WIND",     283),
        ]
        for icon, val, label, x in stats:
            d.draw_rect(x - 50, stat_y, 100, 62, fill=C["surface"],
                        outline=C["border"], radius=12)
            d.draw_text(x, stat_y + 18, icon,  size=13)
            d.draw_text(x, stat_y + 36, val,   size=11, color=C["text"],
                        font="Courier", bold=True)
            d.draw_text(x, stat_y + 51, label, size=7,  color=C["dim"],
                        font="Courier")

        # Hi/Lo
        d.draw_text(W // 2, 298, f"H: {weather['high']}°C    L: {weather['low']}°C",
                    size=10, color=C["dim"], font="Courier")
        d.draw_text(W // 2, 318, "Q = back", size=7, color=C["dim"], font="Courier")

    # -- MAPS --

    def _screen_maps(self, d, sys):
        import math
        W = H = 340
        d.draw_text(W // 2, 38, "MAPS", size=10, color=C["dim"], font="Courier")

        # Fake GPS location
        loc = sys.get("location", {
            "lat":  28.6139,
            "lon":  77.2090,
            "city": "New Delhi",
            "area": "Connaught Place",
        })

        # Draw a fake map grid
        map_x, map_y = 20, 52
        map_w, map_h = 300, 210

        # Map background
        d.draw_rect(map_x, map_y, map_w, map_h, fill=C["surface"],
                    outline=C["border"], radius=8)

        # Grid lines (streets)
        for i in range(1, 5):
            gx = map_x + i * (map_w // 5)
            gy = map_y + i * (map_h // 5)
            d.draw_line(gx, map_y, gx, map_y + map_h, color=C["surface2"], width=1)
            d.draw_line(map_x, gy, map_x + map_w, gy, color=C["surface2"], width=1)

        # Fake roads (diagonals)
        d.draw_line(map_x, map_y + 60,  map_x + map_w, map_y + 100,
                    color=C["surface2"], width=2)
        d.draw_line(map_x + 60, map_y,  map_x + 100, map_y + map_h,
                    color=C["surface2"], width=2)
        d.draw_line(map_x, map_y + map_h - 40, map_x + map_w, map_y + 40,
                    color=C["surface2"], width=2)

        # You are here — center dot with pulse rings
        cx = map_x + map_w // 2
        cy = map_y + map_h // 2
        d.draw_circle(cx, cy, 18, fill="", outline=C["cyan"])
        d.draw_circle(cx, cy, 10, fill="", outline=C["cyan"])
        d.draw_circle(cx, cy, 5,  fill=C["cyan"], outline="")

        # Location info
        d.draw_text(W // 2, 278, f"📍 {loc['area']}", size=11,
                    color=C["text"], font="Courier")
        d.draw_text(W // 2, 296, loc["city"], size=9,
                    color=C["dim"], font="Courier")
        d.draw_text(W // 2, 313, f"{loc['lat']:.4f}°N  {loc['lon']:.4f}°E",
                    size=8, color=C["dim"], font="Courier")
        d.draw_text(W // 2, 328, "Q = back", size=7, color=C["dim"], font="Courier")



    def _screen_stopwatch(self, d, sys):
        W  = 340
        sw = sys.get("stopwatch", {"elapsed": 0, "running": False, "laps": []})
        elapsed = sw["elapsed"]

        d.draw_text(W // 2, 42, "STOPWATCH", size=10, color=C["dim"], font="Courier")

        mm  = int(elapsed // 60)
        ss  = int(elapsed % 60)
        ms  = int((elapsed % 1) * 100)
        d.draw_text(W // 2, 130, f"{mm:02d}:{ss:02d}", size=40,
                    color=C["text"], font="Courier", bold=True)
        d.draw_text(W // 2, 162, f".{ms:02d}", size=18, color=C["cyan"], font="Courier")

        # Buttons
        run = sw["running"]
        d.draw_circle(170 + 40, 210, 26,
                      fill=C["surface"], outline=C["green"] if not run else C["red"])
        d.draw_text(170 + 40, 210, "▶" if not run else "⏸", size=16,
                    color=C["green"] if not run else C["red"])

        d.draw_circle(170 - 40, 210, 26,
                      fill=C["surface"], outline=C["border"])
        d.draw_text(170 - 40, 210, "LAP", size=10, color=C["dim"], font="Courier")

        # Laps
        y = 250
        for lap in reversed(sw["laps"][-3:]):
            d.draw_text(W // 2, y, lap, size=10, color=C["dim"], font="Courier")
            y += 22

        d.draw_text(W // 2, 320, "S = start/stop  |  L = lap",
                    size=7, color=C["dim"], font="Courier")

    # ── MUSIC ──────────────────────────────────────────────────────────────────

    _TRACKS = [
        {"title": "Midnight Drive",   "artist": "Synthwave Radio",    "emoji": "🌃", "dur": 214},
        {"title": "Lo-fi Study Beat", "artist": "Chillhop",           "emoji": "☕", "dur": 187},
        {"title": "Neon Pulse",       "artist": "Oscillator",         "emoji": "⚡", "dur": 198},
        {"title": "Deep Space",       "artist": "Ambient Collective",  "emoji": "🌌", "dur": 256},
    ]

    def _screen_music(self, d, sys):
        W     = 340
        music = sys.get("music", {"idx": 0, "playing": False, "pos": 0})
        track = self._TRACKS[music.get("idx", 0) % len(self._TRACKS)]
        pos   = music.get("pos", 0)
        dur   = track["dur"]
        pct   = pos / dur if dur else 0

        d.draw_rect(120, 55, 100, 100, fill=C["surface2"], outline=C["border"], radius=20)
        d.draw_text(170, 105, track["emoji"], size=36)

        d.draw_text(W // 2, 170, track["title"][:20], size=13,
                    color=C["text"], font="Courier", bold=True)
        d.draw_text(W // 2, 190, track["artist"][:22], size=9,
                    color=C["dim"], font="Courier")

        # Progress
        bx = 40
        d.draw_rect(bx, 215, W - 80, 4, fill=C["surface2"], outline="", radius=2)
        fw = int((W - 80) * pct)
        if fw > 0:
            d.draw_rect(bx, 215, fw, 4, fill=C["amber"], outline="", radius=2)

        cur_s = int(pos)
        tot_s = dur
        d.draw_text(bx,     228, f"{cur_s//60}:{cur_s%60:02d}", size=8,
                    color=C["dim"], font="Courier", anchor="w")
        d.draw_text(W - bx, 228, f"{tot_s//60}:{tot_s%60:02d}", size=8,
                    color=C["dim"], font="Courier", anchor="e")

        # Controls
        d.draw_text(W // 2 - 60, 268, "⏮", size=20, color=C["dim"])
        play_color = C["amber"] if music.get("playing") else C["text"]
        d.draw_circle(W // 2, 268, 26, fill=C["surface"], outline=C["amber"])
        d.draw_text(W // 2, 268, "⏸" if music.get("playing") else "▶",
                    size=18, color=play_color)
        d.draw_text(W // 2 + 60, 268, "⏭", size=20, color=C["dim"])

        d.draw_text(W // 2, 316, "P=play/pause  N=next  B=prev",
                    size=7, color=C["dim"], font="Courier")


# =============================================================================
#  KERNEL PROCESSES
#  Each function below is a process that runs on a schedule.
#  The kernel calls it: process._target(kernel)
# =============================================================================

def process_sensor_poll(kernel: Kernel):
    """
    pid: sensor_daemon — priority 1 (highest)
    Polls all sensors and caches results in kernel space.
    Real OS: this would be an interrupt-driven driver, not a polling loop.
    """
    sys = kernel.get_sys_data()
    sys["sensor_cache"][SENSOR_HEART_RATE], _ = kernel.syscall(
        SyscallNum.SYS_SENSOR_READ, SENSOR_HEART_RATE)
    sys["sensor_cache"][SENSOR_ACCELERO], _ = kernel.syscall(
        SyscallNum.SYS_SENSOR_READ, SENSOR_ACCELERO)
    sys["sensor_cache"][SENSOR_BATTERY], _ = kernel.syscall(
        SyscallNum.SYS_SENSOR_READ, SENSOR_BATTERY)


def process_ui_render(kernel: Kernel):
    """
    pid: ui_compositor — priority 2
    Requests a screen redraw every frame.
    """
    kernel.syscall(SyscallNum.SYS_DRAW)


def process_stopwatch(kernel: Kernel):
    """
    pid: stopwatch_daemon — priority 3
    Updates stopwatch elapsed time in kernel data store.
    """
    sys = kernel.get_sys_data()
    if "stopwatch" not in sys:
        sys["stopwatch"] = {
            "running":    False,
            "elapsed":    0.0,
            "start_mono": 0.0,
            "laps":       [],
        }
    sw = sys["stopwatch"]
    if sw["running"]:
        sw["elapsed"] = (time.monotonic() - sw["start_mono"])


def process_music(kernel: Kernel):
    """
    pid: media_daemon — priority 4
    Advances music playback position.
    """
    sys = kernel.get_sys_data()
    if "music" not in sys:
        sys["music"] = {"idx": 0, "playing": False, "pos": 0.0, "_last": 0.0}
    mu = sys["music"]
    if mu["playing"]:
        now = time.monotonic()
        if mu["_last"]:
            mu["pos"] += now - mu["_last"]
        mu["_last"] = now
        dur = WatchRenderer._TRACKS[mu["idx"] % len(WatchRenderer._TRACKS)]["dur"]
        if mu["pos"] >= dur:
            mu["pos"]  = 0
            mu["idx"]  = (mu["idx"] + 1) % len(WatchRenderer._TRACKS)
            mu["_last"] = 0.0
    else:
        mu["_last"] = 0.0


def process_boot_animation(kernel: Kernel):
    """
    pid: boot_anim — priority 0 (runs first, kills itself when done)
    Advances the boot progress bar then hands off to home screen.
    """
    sys = kernel.get_sys_data()
    prog = sys.get("boot_progress", 0.0)
    prog = min(prog + 0.08, 1.0)
    sys["boot_progress"] = prog
    if prog >= 1.0:
        # Kill self FIRST so it never runs again, then navigate
        for p in kernel.ps():
            if p.name == "boot_anim":
                kernel.kill(p.pid)
                break
        sys["boot_done"] = True
        if sys.get("screen") == "boot":
            kernel.syscall(SyscallNum.SYS_NAVIGATE, "home", "right")

# =============================================================================
#  INPUT HANDLER
#  Extended input handling for app-specific keys (stopwatch, music, settings).
#  The kernel's IRQ handler handles navigation. This handles app logic.
# =============================================================================

class InputHandler:
    def __init__(self, kernel: Kernel, display: DisplayDriver):
        self._k = kernel
        self._d = display
        # Bind extra keys on the display thread
        display.root.bind("<s>", lambda e: self._sw_toggle())
        display.root.bind("<l>", lambda e: self._sw_lap())
        display.root.bind("<p>", lambda e: self._music_play())
        display.root.bind("<n>", lambda e: self._music_next())
        display.root.bind("<b>", lambda e: self._music_prev())
        # Settings navigation
        display.root.bind("<Prior>",  lambda e: self._bright_up())   # PgUp
        display.root.bind("<Next>",   lambda e: self._bright_dn())   # PgDn
        display.root.bind("<equal>",  lambda e: self._bright_up())   # = / +
        display.root.bind("<minus>",  lambda e: self._bright_dn())   # -
        display.root.bind("<plus>",   lambda e: self._bright_up())
        display.canvas.bind("<Prior>", lambda e: self._bright_up())
        display.canvas.bind("<Next>",  lambda e: self._bright_dn())
        display.canvas.bind("<equal>", lambda e: self._bright_up())
        display.canvas.bind("<minus>", lambda e: self._bright_dn())

    def _sw_toggle(self):
        sys = self._k.get_sys_data()
        if "stopwatch" not in sys:
            return
        sw = sys["stopwatch"]
        sw["running"] = not sw["running"]
        if sw["running"]:
            sw["start_mono"] = time.monotonic() - sw["elapsed"]

    def _sw_lap(self):
        sys = self._k.get_sys_data()
        sw  = sys.get("stopwatch", {})
        if sw.get("running"):
            e   = sw["elapsed"]
            mm  = int(e // 60)
            ss  = int(e % 60)
            ms  = int((e % 1) * 100)
            sw["laps"].append(f"Lap {len(sw['laps'])+1}  {mm:02d}:{ss:02d}.{ms:02d}")

    def _music_play(self):
        mu = self._k.get_sys_data().get("music", {})
        mu["playing"] = not mu.get("playing", False)

    def _music_next(self):
        mu = self._k.get_sys_data().get("music", {})
        mu["idx"] = (mu.get("idx", 0) + 1) % len(WatchRenderer._TRACKS)
        mu["pos"] = 0; mu["_last"] = 0.0

    def _music_prev(self):
        mu = self._k.get_sys_data().get("music", {})
        mu["idx"] = (mu.get("idx", 0) - 1) % len(WatchRenderer._TRACKS)
        mu["pos"] = 0; mu["_last"] = 0.0

    def _bright_up(self):
        s = self._k.get_sys_data()["settings"]
        s["brightness"] = min(100, s.get("brightness", 70) + 5)

    def _bright_dn(self):
        s = self._k.get_sys_data()["settings"]
        s["brightness"] = max(0, s.get("brightness", 70) - 5)