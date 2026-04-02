# =============================================================================
#  drivers.py — Hardware Drivers
# =============================================================================
#
#  REAL OS CONCEPT:
#  A driver is code that knows HOW to talk to a specific piece of hardware.
#  It implements the HAL interface for one particular chip/platform.
#
#  Real watch drivers talk to:
#    - Display: SPI bus → OLED/AMOLED controller chip (e.g. RM67162)
#    - Heart rate: I2C bus → optical sensor chip (e.g. MAX30102)
#    - Accelerometer: I2C → motion chip (e.g. BMA421) for step counting
#    - Battery: ADC pin → fuel gauge IC
#    - Touch: I2C → capacitive touch controller
#
#  HERE: We implement these using Python's tkinter for display and
#  random/math for simulated sensor data. Same interface, fake hardware.
# =============================================================================

import tkinter as tk
import math, random, time, threading, queue
from hal import (HAL, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                 SENSOR_HEART_RATE, SENSOR_ACCELERO,
                 SENSOR_BATTERY, SENSOR_TEMPERATURE,
                 BTN_CROWN, BTN_BACK,
                 BTN_SWIPE_LEFT, BTN_SWIPE_RIGHT,
                 BTN_SWIPE_UP, BTN_SWIPE_DOWN,
                 IRQ_BUTTON_CROWN, IRQ_BUTTON_BACK, IRQ_BUTTON_SWIPE)


# =============================================================================
#  DISPLAY DRIVER
#  Simulates an AMOLED display controller over SPI.
#  Real driver would write pixel data into a framebuffer and trigger DMA.
#  We use a tkinter Canvas as our "framebuffer".
# =============================================================================

class DisplayDriver:
    """
    Manages the watch window and canvas.
    The kernel/apps NEVER import tkinter — they only call methods here.
    This is driver isolation: hardware details stay in the driver.
    """

    COLORS = {
        "bg":       "#080c10",
        "surface":  "#0e1420",
        "surface2": "#151d2e",
        "border":   "#1e2a3a",
        "cyan":     "#00e5ff",
        "amber":    "#ffb300",
        "red":      "#ff4b6e",
        "green":    "#00e676",
        "text":     "#e8f0fe",
        "dim":      "#6b7a99",
        "white":    "#ffffff",
    }

    def __init__(self):
        self.root    = None
        self.canvas  = None
        self._ready  = threading.Event()
        self._button_queue = queue.Queue()   # thread-safe button events
        self._thread = None

    def init(self, irq_handler):
        """
        Boot the display in its own thread (tkinter must own its thread).
        irq_handler: kernel function to call when hardware interrupt fires.
        """
        self._irq = irq_handler
        self._thread = threading.Thread(target=self._tk_main, daemon=True)
        self._thread.start()
        self._ready.wait()   # block until window is up (like waiting for hardware init)

    def _tk_main(self):
        """Runs in display thread. Equivalent to the display controller's main loop."""
        self.root = tk.Tk()
        self.root.title("AJXOS")
        self.root.resizable(False, False)
        self.root.configure(bg="#020408")

        # Watch bezel frame
        outer = tk.Frame(self.root, bg="#0d1520", padx=14, pady=14)
        outer.pack(padx=20, pady=20)

        # The canvas IS our display framebuffer
        self.canvas = tk.Canvas(
            outer,
            width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT,
            bg=self.COLORS["bg"],
            highlightthickness=1,
            highlightbackground="#1e2d3e"
        )
        self.canvas.pack()

        # Hint bar
        hint = tk.Label(self.root,
            text="A D W X = navigate  |  C = Apps  |  Q/Esc = Back",
            bg="#020408", fg="#1e2d48",
            font=("Courier", 9))
        hint.pack(pady=(0, 10))

        # Focus
        self.root.focus_force()

        # Direct callbacks — bypass the queue entirely.
        # Keys call _direct_cb which is checked by poll_buttons().
        self._direct_events = []

        def _fire(btn):
            print(f"[INPUT] {btn}")   # visible in terminal immediately
            self._direct_events.append(btn)

        for w in (self.root, self.canvas):
            w.bind("<Left>",      lambda e: _fire(BTN_SWIPE_LEFT))
            w.bind("<Right>",     lambda e: _fire(BTN_SWIPE_RIGHT))
            w.bind("<Up>",        lambda e: _fire(BTN_SWIPE_UP))
            w.bind("<Down>",      lambda e: _fire(BTN_SWIPE_DOWN))
            w.bind("<a>",         lambda e: _fire(BTN_SWIPE_LEFT))
            w.bind("<d>",         lambda e: _fire(BTN_SWIPE_RIGHT))
            w.bind("<w>",         lambda e: _fire(BTN_SWIPE_UP))
            w.bind("<s>",         lambda e: _fire(BTN_SWIPE_DOWN))
            w.bind("<c>",         lambda e: _fire(BTN_CROWN))
            w.bind("<q>",         lambda e: _fire(BTN_BACK))
            w.bind("<Escape>",    lambda e: _fire(BTN_BACK))

        self.root.bind("<Button-1>", lambda e: self.root.focus_force())
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._ready.set()   # signal: display hardware is up
        self.root.mainloop()

    def _on_canvas_click(self, event):
        """Handle canvas clicks — used for app launcher."""
        self._direct_events.append(f"CLICK:{event.x}:{event.y}")
        self.root.focus_force()

    def _on_close(self):
        import sys
        self.root.destroy()
        sys.exit(0)

    def poll_buttons(self) -> list:
        """Drain direct event list. Thread-safe swap."""
        if not hasattr(self, "_direct_events") or not self._direct_events:
            return []
        events, self._direct_events = self._direct_events, []
        return events

    def clear(self, color=None):
        """Clear framebuffer — like memset(framebuffer, 0, size)."""
        self.canvas.delete("all")
        if color:
            self.canvas.configure(bg=color)

    def schedule(self, fn):
        """
        Thread-safe way to draw on canvas.
        tkinter is not thread-safe so all draw calls must be scheduled
        on the display thread — like DMA completion callbacks in real drivers.
        """
        if self.root:
            self.root.after(0, fn)

    # ── Drawing Primitives (like framebuffer write functions) ─────────────────

    def draw_rect(self, x, y, w, h, fill=None, outline=None, radius=0, tag=""):
        fill    = fill    or self.COLORS["surface"]
        outline = outline or self.COLORS["border"]
        if radius:
            self._rounded_rect(x, y, w, h, radius, fill, outline, tag)
        else:
            self.canvas.create_rectangle(x, y, x+w, y+h,
                fill=fill, outline=outline, tags=tag)

    def draw_text(self, x, y, text, size=12, color=None, font="Courier",
                  bold=False, anchor="center", tag=""):
        color  = color or self.COLORS["text"]
        weight = "bold" if bold else "normal"
        self.canvas.create_text(x, y, text=text,
            fill=color, font=(font, size, weight),
            anchor=anchor, tags=tag)

    def draw_line(self, x1, y1, x2, y2, color=None, width=1, tag=""):
        color = color or self.COLORS["dim"]
        self.canvas.create_line(x1, y1, x2, y2,
            fill=color, width=width, tags=tag)

    def draw_circle(self, cx, cy, r, fill=None, outline=None, tag=""):
        fill    = fill    or self.COLORS["surface"]
        outline = outline or self.COLORS["border"]
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
            fill=fill, outline=outline, tags=tag)

    def draw_arc(self, cx, cy, r, start, extent, color, width=6, tag=""):
        self.canvas.create_arc(
            cx-r, cy-r, cx+r, cy+r,
            start=start, extent=extent,
            style="arc", outline=color, width=width, tags=tag)

    def draw_polygon(self, points, fill=None, outline=None, tag=""):
        fill    = fill    or self.COLORS["text"]
        outline = outline or ""
        self.canvas.create_polygon(points, fill=fill, outline=outline, tags=tag)

    def _rounded_rect(self, x, y, w, h, r, fill, outline, tag):
        self.canvas.create_polygon(
            x+r,y,  x+w-r,y,
            x+w,y+r, x+w,y+h-r,
            x+w-r,y+h, x+r,y+h,
            x,y+h-r, x,y+r,
            smooth=True, fill=fill, outline=outline, tags=tag)

    def update(self):
        """Force display refresh. Like triggering a vsync."""
        if self.root:
            self.root.update_idletasks()


# =============================================================================
#  SENSOR DRIVER
#  Simulates I2C sensor bus. Real driver would do:
#    i2c_write(SENSOR_ADDR, REG_CMD, START_MEASUREMENT)
#    i2c_read(SENSOR_ADDR, REG_DATA, buffer, len)
# =============================================================================

class SensorDriver:
    """
    Simulates all watch sensors. Each read() call returns fresh data
    as if we just polled the hardware register.
    """

    def __init__(self):
        # Simulated "hardware state" — drifts over time like real sensors
        self._hr_base    = 72.0
        self._step_count = 4200
        self._battery    = 87.0
        self._temp       = 36.5
        self._last_tick  = time.monotonic()

    def read(self, sensor_id) -> dict:
        """
        Read sensor register. In real C:
          uint8_t buf[2];
          i2c_read(sensor_id, REG_DATA, buf, 2);
          return (buf[0] << 8) | buf[1];
        """
        now = time.monotonic()
        dt  = now - self._last_tick
        self._last_tick = now

        if sensor_id == SENSOR_HEART_RATE:
            # Simulate natural HR variation using a sine wave + noise
            self._hr_base = 72 + math.sin(now / 5.0) * 10
            hr = int(self._hr_base + random.gauss(0, 1.5))
            return {"bpm": max(50, min(160, hr))}

        elif sensor_id == SENSOR_ACCELERO:
            # Simulate steps — random chance of a step every poll
            if random.random() < 0.15:
                self._step_count += random.randint(1, 3)
            return {
                "steps":    self._step_count,
                "calories": int(self._step_count * 0.075),
                "distance": round(self._step_count * 0.00075, 2),
                "active_min": int(self._step_count / 150),
            }

        elif sensor_id == SENSOR_BATTERY:
            # Battery drains slowly
            self._battery = max(0, self._battery - dt * 0.001)
            return {
                "level":    round(self._battery, 1),
                "charging": False,
            }

        elif sensor_id == SENSOR_TEMPERATURE:
            self._temp = 36.5 + random.gauss(0, 0.1)
            return {"celsius": round(self._temp, 1)}

        return {}


# =============================================================================
#  CONCRETE HAL IMPLEMENTATION
#  This is the class that gets passed to the kernel.
#  It wires up DisplayDriver + SensorDriver behind the HAL interface.
# =============================================================================

class WatchHAL(HAL):
    """
    Concrete HAL for our simulated watch platform.
    In a real project you'd have:  HAL_STM32.c, HAL_NRF52.c etc.
    The kernel only ever sees the HAL base class.
    """

    def __init__(self):
        self.display = DisplayDriver()
        self.sensors = SensorDriver()
        self._irq_handler = None

    def display_init(self, irq_handler):
        self._irq_handler = irq_handler
        self.display.init(irq_handler)

    def display_flip(self, render_fn):
        """
        Schedule a full frame render on the display thread.
        render_fn receives the DisplayDriver and draws into it.
        """
        d = self.display
        self.display.schedule(lambda: render_fn(d))

    def display_shutdown(self):
        if self.display.root:
            self.display.root.quit()

    def sensor_read(self, sensor_id) -> dict:
        return self.sensors.read(sensor_id)

    def button_poll(self) -> list:
        return self.display.poll_buttons()

    def power_state(self) -> dict:
        bat = self.sensors.read(SENSOR_BATTERY)
        return bat