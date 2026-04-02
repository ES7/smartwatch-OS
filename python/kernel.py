# =============================================================================
#  kernel.py — The AJX OS Kernel
# =============================================================================
#
#  REAL OS CONCEPT:
#  The kernel is the core of an OS. It sits between hardware and apps.
#  Everything runs through the kernel. It has 4 main jobs:
#
#  1. PROCESS MANAGEMENT — create, schedule, kill processes
#  2. MEMORY MANAGEMENT — give each process its own memory space
#  3. INTERRUPT HANDLING — respond to hardware events (button press, sensor tick)
#  4. SYSTEM CALLS (SYSCALLS) — controlled gateway for apps to use hardware
#
#  Apps NEVER touch hardware directly. They ask the kernel via syscalls.
#  Example: an app can't just read the heart rate sensor. It calls:
#    syscall(SYS_SENSOR_READ, SENSOR_HEART_RATE)
#  The kernel checks permissions, reads the sensor, returns the data.
#
#  This file is the equivalent of your kernel.c — but in Python.
# =============================================================================

import time
import threading
import traceback
from enum import Enum
from hal import (HAL, SENSOR_HEART_RATE, SENSOR_ACCELERO,
                 SENSOR_BATTERY, BTN_CROWN, BTN_BACK,
                 BTN_SWIPE_LEFT, BTN_SWIPE_RIGHT,
                 BTN_SWIPE_UP, BTN_SWIPE_DOWN)
from fs import vfs
from memory_manager import mm


# =============================================================================
#  PROCESS / TASK MANAGEMENT
#  REAL OS CONCEPT:
#  A process is a running program. The kernel tracks every process in a
#  Process Control Block (PCB) — a struct holding its state, priority, etc.
#  On real RTOS (like FreeRTOS used in watches), these are called "tasks".
# =============================================================================

class ProcessState(Enum):
    READY    = "READY"      # waiting for CPU time
    RUNNING  = "RUNNING"    # currently executing
    SLEEPING = "SLEEPING"   # waiting for a timer
    WAITING  = "WAITING"    # waiting for an event/resource
    DEAD     = "DEAD"       # finished, can be reaped


class Process:
    """
    Process Control Block (PCB).
    In C: struct task_struct { pid_t pid; int state; int priority; ... }
    """
    _next_pid = 1

    def __init__(self, name, target_fn, priority=5, interval=1.0):
        self.pid       = Process._next_pid
        Process._next_pid += 1
        self.name      = name
        self.state     = ProcessState.READY
        self.priority  = priority      # 1 (highest) to 10 (lowest)
        self.interval  = interval      # how often to run (seconds)
        self._target   = target_fn    # the function this process runs
        self._last_run = 0.0
        self._thread   = None

        # Memory space simulation
        # Real OS: each process gets a virtual address space (MMU maps it)
        # We simulate it as a private dict — processes can't touch each other's
        self.memory    = {}

        # File descriptor table — each process has its own
        self.fd_table  = {}

        # Exit code (set when process dies)
        self.exit_code = 0

    def __repr__(self):
        return f"<Process pid={self.pid} name='{self.name}' state={self.state.value} pri={self.priority}>"


# =============================================================================
#  SYSCALL TABLE
#  REAL OS CONCEPT:
#  A syscall is a controlled way for user-space apps to ask the kernel
#  for privileged operations. On x86, it's the `int 0x80` or `syscall`
#  instruction. On ARM (watches), it's the `SVC` instruction.
#
#  Linux has ~400 syscalls. We implement the ones a watch OS needs.
# =============================================================================

class SyscallNum:
    SYS_SENSOR_READ   = 0x10
    SYS_GET_TIME      = 0x11
    SYS_FS_OPEN       = 0x20
    SYS_FS_READ       = 0x21
    SYS_FS_WRITE      = 0x22
    SYS_FS_CLOSE      = 0x23
    SYS_LOG           = 0x30
    SYS_SPAWN         = 0x40
    SYS_KILL          = 0x41
    SYS_SLEEP         = 0x42
    SYS_GET_POWER     = 0x50
    SYS_MEMORY_STATS  = 0x50
    SYS_NAVIGATE      = 0x60    # watch-specific: switch UI screen
    SYS_DRAW          = 0x61    # watch-specific: request screen redraw


# =============================================================================
#  INTERRUPT DESCRIPTOR TABLE (IDT)
#  REAL OS CONCEPT:
#  When hardware fires an interrupt (button press, sensor ready, timer tick),
#  the CPU stops what it's doing, saves its state, and jumps to the
#  Interrupt Service Routine (ISR) registered for that interrupt number.
#  On x86: the IDT maps IRQ numbers to ISR function pointers.
# =============================================================================

class IRQHandler:
    def __init__(self):
        self._table = {}   # irq_number → handler_function

    def register(self, irq, handler):
        """Register an ISR for an IRQ line. Like request_irq() in Linux."""
        self._table[irq] = handler

    def dispatch(self, irq, data=None):
        """Fire an interrupt. CPU calls this when hardware raises IRQ line."""
        if irq in self._table:
            try:
                self._table[irq](data)
            except Exception as e:
                print(f"[KERNEL] IRQ {irq:#04x} handler crashed: {e}")


# =============================================================================
#  THE KERNEL
# =============================================================================

class Kernel:
    """
    AJX OS Kernel.
    Manages processes, handles interrupts, exposes syscall interface.
    """

    KERNEL_VERSION = "AJXOS 1.0.0-alpha"
    TICK_RATE_HZ   = 10    # how many times per second the scheduler runs

    def __init__(self, hal: HAL):
        self._hal      = hal          # our hardware abstraction layer
        self._process_table = {}      # pid → Process  (like /proc in Linux)
        self._irq      = IRQHandler() # interrupt descriptor table
        self._running  = False
        self._lock     = threading.Lock()

        # Kernel-space data (only kernel can write here)
        self._sys_data = {
            "boot_time":   time.time(),
            "uptime":      0,
            "sensor_cache": {},       # last known sensor values
            "screen":      "boot",    # current UI screen
            "screen_history": [],
            "settings":    {
                "bluetooth": True,
                "wifi":      True,
                "dnd":       False,
                "brightness": 70,
            },
            "notifications": [],
        }

        # The UI renderer (set by watchos.py after kernel boots)
        self._renderer = None

        self._log("Kernel object created")

    # ── Kernel Log (writes to VFS /logs/kernel.log) ────────────────────────────

    def _log(self, msg, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}\n"
        vfs.append_text("/logs/kernel.log", line)

    # ── Syscall Dispatcher ────────────────────────────────────────────────────
    #
    #  REAL OS CONCEPT:
    #  When an app issues a syscall instruction, the CPU switches from
    #  user mode to kernel mode and jumps here.
    #  We check permissions, do the work, return result to app.

    def syscall(self, number, *args, caller_pid=None):
        """
        Main syscall gate. Apps call this instead of touching hardware.
        Returns (result, errno) — like real syscalls return value + errno.
        """
        try:
            if number == SyscallNum.SYS_SENSOR_READ:
                sensor_id = args[0]
                data = self._hal.sensor_read(sensor_id)
                self._sys_data["sensor_cache"][sensor_id] = data
                return data, 0

            elif number == SyscallNum.SYS_GET_TIME:
                return self._hal.wall_time(), 0

            elif number == SyscallNum.SYS_GET_POWER:
                return self._hal.power_state(), 0

            elif number == SyscallNum.SYS_LOG:
                msg = args[0]
                proc_name = self._process_table.get(caller_pid, type('', (), {'name': '?'})()).name
                self._log(f"[{proc_name}] {msg}")
                return None, 0

            elif number == SyscallNum.SYS_FS_OPEN:
                path, mode = args[0], args[1]
                fd = vfs.open(path, mode)
                return fd, 0

            elif number == SyscallNum.SYS_FS_READ:
                fd = args[0]
                return vfs.read(fd), 0

            elif number == SyscallNum.SYS_FS_WRITE:
                fd, data = args[0], args[1]
                vfs.write(fd, data)
                return None, 0

            elif number == SyscallNum.SYS_FS_CLOSE:
                vfs.close(args[0])
                return None, 0

            elif number == SyscallNum.SYS_MEMORY_STATS:
                return mm.stats(), 0

            elif number == SyscallNum.SYS_NAVIGATE:
                screen, direction = args[0], args[1] if len(args) > 1 else "right"
                self._navigate(screen, direction)
                return None, 0

            elif number == SyscallNum.SYS_DRAW:
                if self._renderer:
                    self._hal.display_flip(self._renderer)
                return None, 0

            elif number == SyscallNum.SYS_SPAWN:
                name, fn, pri, interval = args
                proc = self.spawn(name, fn, pri, interval)
                return proc.pid, 0

            elif number == SyscallNum.SYS_KILL:
                pid = args[0]
                self.kill(pid)
                return None, 0

            elif number == SyscallNum.SYS_SLEEP:
                duration = args[0]
                time.sleep(duration)
                return None, 0

        except Exception as e:
            self._log(f"syscall {number:#04x} failed: {e}", level="ERROR")
            return None, -1

        return None, -22   # EINVAL — unknown syscall

    # ── Process Management ────────────────────────────────────────────────────

    def spawn(self, name, target_fn, priority=5, interval=1.0) -> Process:
        """
        Create a new process. Like fork()+exec() in Unix, or
        xTaskCreate() in FreeRTOS.
        """
        proc = Process(name, target_fn, priority, interval)
        with self._lock:
            self._process_table[proc.pid] = proc
        # Allocate base memory for this process (like mmap at process creation)
        mm.malloc(proc.pid, 4096, tag="stack")    # 4KB stack
        mm.malloc(proc.pid, 2048, tag="heap")     # 2KB initial heap
        self._log(f"Spawned process '{name}' pid={proc.pid} pri={priority}")
        return proc

    def kill(self, pid: int):
        """Terminate a process. Like kill(pid, SIGKILL)."""
        with self._lock:
            if pid in self._process_table:
                proc = self._process_table[pid]
                proc.state = ProcessState.DEAD
                reclaimed = mm.reclaim(pid)
                self._log(f"Killed process '{proc.name}' pid={pid}, reclaimed {reclaimed}B")

    def ps(self) -> list:
        """List all processes. Like the `ps` command."""
        return list(self._process_table.values())

    # ── Scheduler ─────────────────────────────────────────────────────────────
    #
    #  REAL OS CONCEPT:
    #  The scheduler decides which process runs next and for how long.
    #  Real RTOS schedulers use priority queues + time slicing.
    #  Our scheduler: run each READY process if its interval has elapsed.
    #  This is called a "cooperative scheduler" — processes yield voluntarily.

    def _schedule(self):
        now = time.monotonic()
        with self._lock:
            procs = sorted(self._process_table.values(), key=lambda p: p.priority)
        for proc in procs:
            if proc.state == ProcessState.DEAD:
                continue
            if proc.state == ProcessState.SLEEPING:
                continue
            if (now - proc._last_run) >= proc.interval:
                proc.state    = ProcessState.RUNNING
                proc._last_run = now
                try:
                    proc._target(self)   # give this process a CPU slice
                except Exception as e:
                    self._log(f"Process '{proc.name}' crashed: {e}", "ERROR")
                    traceback.print_exc()
                    proc.state = ProcessState.DEAD
                else:
                    # Only mark READY if not already killed during its own run
                    if proc.state != ProcessState.DEAD:
                        proc.state = ProcessState.READY

    # ── IRQ Registration & Navigation ─────────────────────────────────────────

    def _register_irqs(self):
        """
        Register Interrupt Service Routines.
        Real OS: called during boot to populate the IDT.
        """
        from hal import IRQ_BUTTON_CROWN, IRQ_BUTTON_BACK, IRQ_BUTTON_SWIPE, IRQ_TIMER_TICK

        self._irq.register(IRQ_BUTTON_CROWN, self._isr_crown)
        self._irq.register(IRQ_BUTTON_BACK,  self._isr_back)
        self._irq.register(IRQ_BUTTON_SWIPE, self._isr_swipe)
        self._irq.register(IRQ_TIMER_TICK,   self._isr_timer)

    def _isr_crown(self, data=None):
        """ISR for crown button. Toggles app launcher."""
        if self._sys_data["screen"] == "apps":
            self._navigate("home", "right")
        else:
            self._navigate("apps", "left")

    def _isr_back(self, data=None):
        hist = self._sys_data["screen_history"]
        if hist:
            prev = hist.pop()
            self._navigate(prev, "right", push_history=False)
        else:
            self._navigate("home", "right", push_history=False)

    def _isr_swipe(self, direction):
        nav_map = {
            "home":     {BTN_SWIPE_LEFT: "fitness", BTN_SWIPE_RIGHT: "heart",
                         BTN_SWIPE_UP: "settings", BTN_SWIPE_DOWN: "notifs"},
            "fitness":  {BTN_SWIPE_RIGHT: "home"},
            "heart":    {BTN_SWIPE_LEFT: "home"},
            "settings": {BTN_SWIPE_DOWN: "home"},
            "notifs":   {BTN_SWIPE_UP: "home"},
        }
        current = self._sys_data["screen"]
        target  = nav_map.get(current, {}).get(direction)
        if target:
            dir_map = {
                BTN_SWIPE_LEFT: "left", BTN_SWIPE_RIGHT: "right",
                BTN_SWIPE_UP: "up",     BTN_SWIPE_DOWN: "down"
            }
            self._navigate(target, dir_map.get(direction, "right"))

    def _isr_timer(self, data=None):
        self._sys_data["uptime"] = time.time() - self._sys_data["boot_time"]

    def _navigate(self, screen, direction="right", push_history=True):
        """Kernel-managed screen navigation. Apps never touch this directly."""
        current = self._sys_data["screen"]
        if current == screen:
            return
        if push_history and current != "boot":
            self._sys_data["screen_history"].append(current)
            if len(self._sys_data["screen_history"]) > 10:
                self._sys_data["screen_history"].pop(0)
        self._sys_data["screen"]     = screen
        self._sys_data["nav_dir"]    = direction
        self._sys_data["screen_dirty"] = True
        self._log(f"Navigate: {current} → {screen} ({direction})")

    # ── Input Polling Loop ────────────────────────────────────────────────────

    def _poll_input(self):
        """
        Poll hardware for button events and dispatch as IRQs.
        Real OS: hardware fires actual electrical interrupts.
        We simulate by polling a queue the display driver fills.
        """
        buttons = self._hal.button_poll()
        for btn in buttons:
            if btn == BTN_CROWN:
                self._irq.dispatch(0x01)
            elif btn == BTN_BACK:
                self._irq.dispatch(0x02)
            elif isinstance(btn, str) and btn.startswith("CLICK:"):
                # Touch/click event — parse coordinates
                _, x, y = btn.split(":")
                self._isr_click(int(x), int(y))
            else:
                self._irq.dispatch(0x03, btn)

    def _isr_click(self, x, y):
        """Handle screen tap. Route to app if on apps screen."""
        print(f"[CLICK] x={x} y={y} screen={self._sys_data['screen']}")
        if self._sys_data["screen"] != "apps":
            return

        # App grid positions (must match watchos.py _screen_apps exactly)
        icon_r     = 32
        pad_y      = 52
        cell_h     = 84
        col_centers= [57, 170, 283]
        app_screens= ["home","fitness","heart","music","stopwatch",
                      "notifs","settings","weather","maps"]

        for i, screen in enumerate(app_screens):
            col = i % 3
            row = i // 3
            cx  = col_centers[col]
            cy  = pad_y + icon_r + row * cell_h
            if abs(x - cx) <= icon_r and abs(y - cy) <= icon_r:
                self._navigate(screen, "left")
                return

    # ── Kernel Main Loop ──────────────────────────────────────────────────────

    def set_renderer(self, renderer_fn):
        """Called by watchos to register the UI draw function."""
        self._renderer = renderer_fn

    def get_sys_data(self) -> dict:
        """Read-only window into kernel state for UI processes."""
        return self._sys_data

    def push_notification(self, app, text, icon="🔔"):
        self._sys_data["notifications"].append({
            "app": app, "text": text, "icon": icon,
            "time": time.strftime("%H:%M")
        })
        self._log(f"Notification from {app}: {text}")

    def run(self):
        """
        Kernel main loop. Equivalent to the scheduler loop in kernel.c.
        Real RTOS: this runs forever after boot, never returns.
        """
        self._running = True
        tick_interval = 1.0 / self.TICK_RATE_HZ

        while self._running:
            loop_start = time.monotonic()

            # 1. Poll hardware interrupts
            self._poll_input()

            # 2. Run scheduler — give each process its CPU slice
            self._schedule()

            # 3. Update uptime
            self._sys_data["uptime"] = time.time() - self._sys_data["boot_time"]

            # 4. Sleep for remainder of tick (to hit target Hz)
            elapsed = time.monotonic() - loop_start
            sleep_time = max(0, tick_interval - elapsed)
            time.sleep(sleep_time)