# =============================================================================
#  hal.py — Hardware Abstraction Layer (HAL)
# =============================================================================
#
#  REAL OS CONCEPT:
#  In a real OS, the HAL is a thin layer that hides the differences between
#  hardware platforms. The kernel never talks to hardware directly — it always
#  goes through the HAL. This means the same kernel can run on different chips.
#  Example: Linux's HAL lets the same kernel run on ARM (phones), x86 (PCs),
#  RISC-V, etc. without changing the kernel code.
#
#  HERE: We define what "hardware" our fake watch has. The drivers (drivers.py)
#  will implement these. The kernel only knows about HAL — never about tkinter.
# =============================================================================

import time

# ── Hardware Constants (like #define in C) ────────────────────────────────────

DISPLAY_WIDTH  = 340   # pixels
DISPLAY_HEIGHT = 340
DISPLAY_FPS    = 30

# Simulated hardware interrupt numbers (IRQ lines)
# On real hardware these map to physical interrupt controller pins
IRQ_BUTTON_CROWN  = 0x01
IRQ_BUTTON_BACK   = 0x02
IRQ_BUTTON_SWIPE  = 0x03
IRQ_SENSOR_TICK   = 0x10   # sensor data ready
IRQ_TIMER_TICK    = 0x20   # 1-second system clock
IRQ_DISPLAY_VSYNC = 0x30   # display ready for next frame

# Sensor IDs (like device addresses on an I2C bus)
SENSOR_HEART_RATE  = 0xA0
SENSOR_ACCELERO    = 0xA1   # for step counting
SENSOR_BATTERY     = 0xA2
SENSOR_TEMPERATURE = 0xA3

# Button codes
BTN_CROWN = "CROWN"
BTN_BACK  = "BACK"
BTN_SWIPE_LEFT  = "SWIPE_LEFT"
BTN_SWIPE_RIGHT = "SWIPE_RIGHT"
BTN_SWIPE_UP    = "SWIPE_UP"
BTN_SWIPE_DOWN  = "SWIPE_DOWN"


# ── HAL Interface (Abstract Base — like a C header file) ──────────────────────
#
#  In C this would be a struct of function pointers:
#    struct hal_ops {
#        void (*display_init)(void);
#        void (*display_draw)(frame_t*);
#        int  (*sensor_read)(uint8_t sensor_id);
#        ...
#    };

class HAL:
    """
    Abstract Hardware Abstraction Layer.
    The kernel holds a reference to ONE hal instance.
    Swap this out → same kernel runs on different hardware.
    """

    def display_init(self):
        raise NotImplementedError

    def display_flip(self, frame):
        """Push rendered frame to the physical display."""
        raise NotImplementedError

    def display_shutdown(self):
        raise NotImplementedError

    def sensor_read(self, sensor_id) -> dict:
        """Read raw data from a sensor. Returns dict of values."""
        raise NotImplementedError

    def button_poll(self) -> list:
        """Return list of button events since last poll."""
        raise NotImplementedError

    def system_time(self) -> float:
        """Monotonic clock in seconds. Like clock_gettime(CLOCK_MONOTONIC)."""
        return time.monotonic()

    def wall_time(self) -> time.struct_time:
        """Real-world time. Like gettimeofday()."""
        return time.localtime()

    def power_state(self) -> dict:
        """Returns battery level, charging status etc."""
        raise NotImplementedError
