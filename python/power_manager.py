# =============================================================================
#  power_manager.py — Power Manager
# =============================================================================
#
#  REAL OS CONCEPT:
#  A watch runs on a tiny battery — maybe 300mAh. Without power management,
#  it would die in hours. Real watches achieve 7-14 day battery life through
#  aggressive power management.
#
#  The CPU has multiple power states (defined by ARM):
#    Run       → CPU fully active, 100% power
#    Sleep     → CPU paused, RAM kept, wakes on interrupt ~5% power
#    Deep Sleep → CPU + most peripherals off, only RTC runs ~0.1% power
#    Hibernate → Everything off, state saved to flash, ~0% power
#
#  The power manager decides which state to enter based on:
#    - Is the user interacting? (wrist raise, touch)
#    - Is there a pending alarm or notification?
#    - What is the battery level?
#    - Is the watch charging?
#
#  Real implementation: configures ARM's SCB->SCR register bits,
#  then executes WFI (Wait For Interrupt) assembly instruction.
# =============================================================================

import time
import threading
import random
import math


# ── Power States ──────────────────────────────────────────────────────────────

class PowerState:
    RUN        = "RUN"         # screen on, full CPU
    SLEEP      = "SLEEP"       # screen dim, CPU throttled
    DEEP_SLEEP = "DEEP_SLEEP"  # screen off, CPU ~stopped
    CHARGING   = "CHARGING"    # plugged in


# ── Power Events (what can wake the watch) ────────────────────────────────────

class WakeEvent:
    WRIST_RAISE   = "WRIST_RAISE"    # accelerometer detects wrist raise
    BUTTON_PRESS  = "BUTTON_PRESS"   # crown or back button
    NOTIFICATION  = "NOTIFICATION"   # incoming message/call
    ALARM         = "ALARM"          # scheduled alarm
    CHARGER_IN    = "CHARGER_IN"     # USB/wireless charger connected


# ── Battery Model ─────────────────────────────────────────────────────────────

class BatteryModel:
    """
    Simulates battery drain based on power state.
    Real watches measure battery via ADC reading of cell voltage,
    then estimate capacity using a fuel gauge IC (e.g. MAX17048).

    Discharge rates (simulated, based on real watch datasheets):
        RUN        → ~50mA  (screen on, GPS, BT active)
        SLEEP      → ~5mA   (screen dim, sensors polling)
        DEEP_SLEEP → ~0.1mA (only RTC + wakeup logic)
        CHARGING   → +100mA
    """

    DRAIN_RATE = {
        PowerState.RUN:        0.008,   # % per second
        PowerState.SLEEP:      0.001,
        PowerState.DEEP_SLEEP: 0.00002,
        PowerState.CHARGING:  -0.015,   # negative = charging
    }

    def __init__(self, initial_pct=87.0):
        self.level    = initial_pct
        self.charging = False
        self._last    = time.monotonic()

    def tick(self, state: str):
        now  = time.monotonic()
        dt   = now - self._last
        self._last = now

        rate = self.DRAIN_RATE.get(state, self.DRAIN_RATE[PowerState.RUN])
        self.level = max(0.0, min(100.0, self.level - rate * dt))
        self.charging = (state == PowerState.CHARGING)

    def status(self) -> dict:
        return {
            "level":    round(self.level, 2),
            "charging": self.charging,
            "state":    "critical" if self.level < 10 else
                        "low"      if self.level < 20 else
                        "normal"   if self.level < 80 else "full",
            "est_hours": round(self.level / 0.008 / 3600, 1)  # rough estimate
        }


# ── Wake Gesture Detector ─────────────────────────────────────────────────────

class WristGestureDetector:
    """
    Simulates accelerometer-based wrist raise detection.
    Real implementation: BMA421 accelerometer fires interrupt when
    it detects the specific angular velocity pattern of raising wrist.

    Algorithm (simplified):
    1. Monitor Z-axis acceleration
    2. If Z changes from negative (face down) to positive (face up)
       within 300ms window → wrist raise detected
    3. Debounce: ignore repeated raises within 2 seconds
    """

    def __init__(self):
        self._last_raise = 0.0
        self._debounce   = 2.0   # seconds

    def check(self) -> bool:
        """Returns True if wrist raise detected."""
        now = time.monotonic()
        if now - self._last_raise < self._debounce:
            return False
        # Simulate ~10% chance of wrist raise per check when moving
        if random.random() < 0.002:
            self._last_raise = now
            return True
        return False


# ── Power Manager ─────────────────────────────────────────────────────────────

class PowerManager:
    """
    Central power state machine.
    Runs as a kernel process — monitors activity, transitions between states.
    """

    SCREEN_TIMEOUT   = 15.0   # seconds of inactivity before sleep
    DEEP_SLEEP_AFTER = 60.0   # seconds in sleep before deep sleep

    def __init__(self):
        self.state        = PowerState.RUN
        self.battery      = BatteryModel()
        self.gesture      = WristGestureDetector()
        self._last_active = time.monotonic()
        self._sleep_since = None
        self._lock        = threading.Lock()
        self._callbacks   = []   # wake/sleep event listeners
        self._history     = []   # power state history log

    def register_callback(self, fn):
        """Register a function to call on power state change."""
        self._callbacks.append(fn)

    def _transition(self, new_state: str, reason: str):
        """Move to a new power state and notify listeners."""
        if new_state == self.state:
            return
        old = self.state
        self.state = new_state
        entry = {
            "from":   old,
            "to":     new_state,
            "reason": reason,
            "time":   time.strftime("%H:%M:%S"),
        }
        self._history.append(entry)
        for cb in self._callbacks:
            try:
                cb(old, new_state, reason)
            except Exception:
                pass

    def activity(self, event: str = "user_input"):
        """
        Called whenever user does something — button press, touch etc.
        Resets inactivity timer and wakes screen if sleeping.
        """
        with self._lock:
            self._last_active = time.monotonic()
            if self.state in (PowerState.SLEEP, PowerState.DEEP_SLEEP):
                self._transition(PowerState.RUN, f"wake:{event}")
                self._sleep_since = None

    def tick(self, sys_data: dict):
        """
        Called every kernel tick. Manages power state transitions.
        This is the equivalent of the Linux PM (power management) subsystem.
        """
        now      = time.monotonic()
        inactive = now - self._last_active

        # Update battery drain based on current state
        self.battery.tick(self.state)

        # Check for wrist raise (only relevant in sleep mode)
        if self.state == PowerState.DEEP_SLEEP:
            if self.gesture.check():
                self._transition(PowerState.RUN, WakeEvent.WRIST_RAISE)
                self._last_active = now
                return

        # State transitions based on inactivity
        if self.state == PowerState.RUN:
            if inactive > self.SCREEN_TIMEOUT:
                self._transition(PowerState.SLEEP, "inactivity_timeout")
                self._sleep_since = now

        elif self.state == PowerState.SLEEP:
            sleep_dur = now - (self._sleep_since or now)
            if sleep_dur > self.DEEP_SLEEP_AFTER:
                self._transition(PowerState.DEEP_SLEEP, "extended_inactivity")

        # Critical battery warning
        if self.battery.level < 5.0 and self.state == PowerState.RUN:
            self._transition(PowerState.SLEEP, "critical_battery")

        # Update sys_data so kernel and UI can read power info
        sys_data["power"] = {
            "state":   self.state,
            "battery": self.battery.status(),
            "inactive_sec": round(inactive, 1),
        }

    def plug_charger(self):
        """Simulate plugging in charger."""
        self._transition(PowerState.CHARGING, WakeEvent.CHARGER_IN)
        self.battery.charging = True

    def unplug_charger(self):
        """Simulate unplugging charger."""
        self._transition(PowerState.RUN, "charger_removed")
        self.battery.charging = False

    def status(self) -> dict:
        return {
            "state":    self.state,
            "battery":  self.battery.status(),
            "history":  self._history[-5:],   # last 5 transitions
            "screen_timeout": self.SCREEN_TIMEOUT,
            "deep_sleep_after": self.DEEP_SLEEP_AFTER,
        }

    def history(self) -> list:
        return self._history


# ── Global instance ───────────────────────────────────────────────────────────
pm = PowerManager()
