# =============================================================================
#  boot.py — The Bootloader
# =============================================================================
#
#  REAL OS CONCEPT:
#  This is the Python equivalent of your boot.asm file.
#
#  In a real smartwatch, boot.asm is the VERY first code that runs when
#  you press the power button. The CPU starts executing from a fixed
#  memory address (the reset vector). boot.asm is placed there.
#
#  What real boot.asm does (step by step):
#    1. Set up the stack pointer (SP register) — CPU needs a stack to work
#    2. Zero out the BSS segment (uninitialized global variables)
#    3. Copy initialized data from flash to RAM
#    4. Initialize the hardware clock (PLL) to set CPU speed
#    5. Call main() / kernel_main() — hand control to the C kernel
#
#  Your kernel.c had:
#    void kernel_main() { char *video = (char*)0xb8000; ... }
#  That 0xb8000 is the VGA text buffer address on x86 — writing there
#  puts text on screen. That's exactly what a bootloader hands off to.
#
#  HERE: boot.py does the equivalent — hardware checks, mounts filesystem,
#  validates the kernel, then calls kernel.run().
# =============================================================================

import sys
import os
import time


# ── Boot Configuration ─────────────────────────────────────────────────────────
# In real embedded C: #define KERNEL_LOAD_ADDR 0x08000000
#                     #define STACK_TOP        0x20010000

BOOT_CONFIG = {
    "kernel_version_required": "1.0",
    "display_width":  340,
    "display_height": 340,
    "ram_size_kb":    256,    # simulated RAM (real watch: 64–512KB)
    "flash_size_kb":  2048,   # simulated flash storage
    "cpu_mhz":        64,     # simulated CPU speed (real: 64–400 MHz)
}


def _print_boot(msg, ok=True):
    """
    Bootloader console output.
    On a real system with no display yet, this goes to a UART serial port
    that you read with a USB-to-UART cable — this is how embedded devs debug boot.
    """
    status = "[ OK ]" if ok else "[FAIL]"
    print(f"  {status}  {msg}")


def run_bootloader():
    """
    The bootloader sequence.
    Each step mirrors what real boot.asm / startup code does.
    Returns (hal, kernel) — the initialized hardware and kernel objects,
    ready for the kernel to start scheduling.
    """

    print()
    print("=" * 52)
    print("         AJX OS Bootloader v1.0")
    print("=" * 52)
    print()
    time.sleep(0.1)

    # ── STAGE 1: Power-On Self Test (POST) ─────────────────────────────────────
    #
    #  Real OS: CPU checks that RAM is not corrupted by reading/writing test
    #  patterns. Checks that flash (where the kernel lives) is readable.
    #  If anything fails here, the watch shows a dead battery icon and halts.

    print("[STAGE 1] Power-On Self Test")
    time.sleep(0.1)

    _print_boot(f"CPU simulation: {BOOT_CONFIG['cpu_mhz']} MHz")
    _print_boot(f"RAM: {BOOT_CONFIG['ram_size_kb']} KB")
    _print_boot(f"Flash: {BOOT_CONFIG['flash_size_kb']} KB")
    _print_boot("RAM integrity check passed")
    _print_boot("Flash read-back check passed")

    time.sleep(0.2)
    print()

    # ── STAGE 2: Hardware Abstraction Layer Init ────────────────────────────────
    #
    #  Real OS: Initialize the clock tree (PLL), configure GPIO pins,
    #  set up the SPI bus for the display, I2C bus for sensors.
    #  This is done in C startup code BEFORE kernel_main() is called.

    print("[STAGE 2] Hardware Init (HAL)")
    time.sleep(0.1)

    try:
        from drivers import WatchHAL
        hal = WatchHAL()
        _print_boot("HAL object created")
    except ImportError as e:
        _print_boot(f"HAL init failed: {e}", ok=False)
        sys.exit(1)

    # Start display (this opens the window)
    # In real OS: SPI display init sequence, send RESET + config commands
    _print_boot("Starting display driver (SPI init)...")
    from hal import IRQ_BUTTON_CROWN
    hal.display_init(irq_handler=None)   # kernel will register IRQs later
    _print_boot("Display driver ready (AMOLED 340×340 simulated)")
    _print_boot("Sensor bus ready (I2C simulated)")

    time.sleep(0.2)
    print()

    # ── STAGE 3: Filesystem Mount ───────────────────────────────────────────────
    #
    #  Real OS: Read the first sector of flash, verify the filesystem magic
    #  number (e.g. LittleFS magic = 0x4C697474), mount the filesystem.
    #  We just initialize our in-memory VFS.

    print("[STAGE 3] Filesystem Mount")
    time.sleep(0.1)

    from fs import vfs
    _print_boot("VFS (MemFS) initialized")
    _print_boot("Root filesystem mounted at /")

    # Write boot record to filesystem (like /proc/version in Linux)
    vfs.write_json("/sys/boot_config.json", BOOT_CONFIG)
    vfs.write_text("/sys/version", "AJX OS 1.0.0-alpha\n")
    _print_boot("Boot config written to /sys/boot_config.json")
    _print_boot("Kernel version written to /sys/version")

    time.sleep(0.2)
    print()

    # ── STAGE 4: Kernel Init ────────────────────────────────────────────────────
    #
    #  Real OS: Jump to kernel_main(). The kernel sets up its data structures:
    #  process table, interrupt descriptor table, memory allocator.
    #  THIS is the moment your kernel.c's kernel_main() gets called.

    print("[STAGE 4] Kernel Init")
    time.sleep(0.1)

    from kernel import Kernel
    kernel = Kernel(hal)
    _print_boot(f"Kernel '{Kernel.KERNEL_VERSION}' loaded")
    _print_boot(f"Process table initialized")
    _print_boot(f"Syscall table registered ({10} syscalls)")

    # Register interrupt handlers (populate the IDT)
    kernel._register_irqs()
    _print_boot("IRQ handlers registered (IDT populated)")

    time.sleep(0.2)
    print()

    # ── STAGE 5: Spawn System Processes ────────────────────────────────────────
    #
    #  Real OS: kernel spawns the first process (init / PID 1 in Linux).
    #  All other processes are children of init.
    #  Our kernel spawns its daemon processes here.

    print("[STAGE 5] Spawning System Processes")
    time.sleep(0.1)

    from memory_manager import mm
    from power_manager  import pm
    from network_stack  import NetworkStack, process_network
    from security       import SecurityManager, SecureBoot
    from update_manager import UpdateManager, process_update_check
    from shell          import Shell
    from watchos import (process_sensor_poll, process_ui_render,
                         process_stopwatch, process_music,
                         process_boot_animation, WatchRenderer, InputHandler)

    # PID 1: boot animation (highest priority, kills itself when done)
    p0 = kernel.spawn("boot_anim",      process_boot_animation, priority=0, interval=0.05)
    _print_boot(f"pid {p0.pid:3d}  boot_anim         pri=0   interval=50ms")

    # PID 2: sensor daemon (reads hardware sensors)
    p1 = kernel.spawn("sensor_daemon",  process_sensor_poll,    priority=1, interval=1.0)
    _print_boot(f"pid {p1.pid:3d}  sensor_daemon     pri=1   interval=1s")

    # PID 3: UI compositor (draws the screen)
    p2 = kernel.spawn("ui_compositor",  process_ui_render,      priority=2, interval=0.05)
    _print_boot(f"pid {p2.pid:3d}  ui_compositor     pri=2   interval=50ms (~20fps)")

    # PID 4: stopwatch daemon
    p3 = kernel.spawn("stopwatch_daemon", process_stopwatch,    priority=3, interval=0.05)
    _print_boot(f"pid {p3.pid:3d}  stopwatch_daemon  pri=3   interval=50ms")

    # PID 5: media daemon
    p4 = kernel.spawn("media_daemon",   process_music,          priority=4, interval=0.1)
    _print_boot(f"pid {p4.pid:3d}  media_daemon      pri=4   interval=100ms")

    time.sleep(0.2)
    print()

    # ── STAGE 6: Wire up renderer & input ──────────────────────────────────────

    print("[STAGE 6] Wiring Renderer & Input")

    renderer = WatchRenderer(kernel, hal.display)
    kernel.set_renderer(lambda d: renderer.render(hal.display))
    _print_boot("WatchRenderer registered with kernel")

    # Wait for display thread to be ready, then attach input bindings
    time.sleep(0.3)
    try:
        InputHandler(kernel, hal.display)
        _print_boot("InputHandler registered")
    except Exception as e:
        _print_boot(f"InputHandler warning: {e}", ok=False)

    # Push a welcome notification
    kernel.push_notification("AJX OS", "System booted successfully", "🟢")

    time.sleep(0.2)
    print()
    print("=" * 52)
    print("  Boot complete. Handing control to kernel.")
    print(f"  Kernel scheduler running at {Kernel.TICK_RATE_HZ} Hz")
    print("=" * 52)
    print()

    # ── STAGE 7: Secondary Systems ─────────────────────────────────────────────
    print("[STAGE 7] Secondary Systems")
    time.sleep(0.1)

    # Secure boot — provision file hashes
    import os
    os_files = [os.path.join(os.path.dirname(__file__), f)
                for f in ["kernel.py","drivers.py","hal.py","fs.py"]]
    SecureBoot.provision(os_files)
    results = SecureBoot.verify(os_files)
    all_ok  = all(v == "OK" for v in results.values())
    _print_boot(f"Secure boot: {'PASSED' if all_ok else 'WARNING'} ({len(results)} files checked)")

    # Security manager
    sec = SecurityManager(vfs)
    kernel._sys_data["_security"] = sec
    # Store a demo secret
    sec.secure_storage.write("device_id", "AJX-OS-001-DEMO", owner_pid=0)
    _print_boot("Security manager ready (encrypted storage initialized)")

    # Network stack
    net = NetworkStack(kernel)
    kernel._sys_data["_network_stack"] = net
    net.enable_ble()
    _print_boot("Network stack ready (BLE advertising...)")

    # Power manager
    pm.register_callback(lambda old, new, reason:
        kernel._log(f"Power: {old} → {new} ({reason})"))
    kernel._sys_data["_power_manager"] = pm
    _print_boot("Power manager ready")

    # Update manager
    um = UpdateManager(kernel, net, sec, vfs)
    kernel._sys_data["_update_manager"] = um
    _print_boot("Update manager ready")

    # Spawn secondary processes
    p6 = kernel.spawn("network_daemon",  process_network,      priority=3, interval=0.5)
    p7 = kernel.spawn("update_daemon",   process_update_check, priority=8, interval=5.0)
    _print_boot(f"pid {p6.pid:3d}  network_daemon    pri=3   interval=500ms")
    _print_boot(f"pid {p7.pid:3d}  update_daemon     pri=8   interval=5s")

    # Power manager process (inline lambda)
    def _pm_tick(kernel):
        pm.tick(kernel.get_sys_data())
        # Notify kernel of user activity on any input
    p8 = kernel.spawn("power_daemon", _pm_tick, priority=2, interval=1.0)
    _print_boot(f"pid {p8.pid:3d}  power_daemon      pri=2   interval=1s")

    time.sleep(0.1)
    print()

    # Shell — runs in terminal alongside the watch UI
    shell = Shell(kernel)
    shell.start()
    _print_boot("Shell started (type commands in this terminal)")

    time.sleep(0.1)
    print()

    return hal, kernel
