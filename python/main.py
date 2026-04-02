# =============================================================================
#  main.py — The Power Button
# =============================================================================
#
#  REAL OS CONCEPT:
#  On a real smartwatch, this is the reset vector — the very first
#  instruction the CPU executes when power is applied or the button is held.
#  In embedded C:
#
#    // Placed at 0x00000000 (reset vector in ARM Cortex-M)
#    void Reset_Handler(void) {
#        SystemInit();       // clock setup
#        __libc_init_array();// C runtime init
#        main();             // your main()
#    }
#
#  main() in C would call your bootloader, which calls kernel_main().
#  HERE: main.py does the same — it's the single entry point.
#  Run this file to "press the power button" on AJX OS.
#
#  Usage:
#    python main.py
#
#  Controls (keyboard):
#    ← → ↑ ↓    Navigate between screens
#    C           Crown button (open app launcher)
#    Escape      Back button
#    S           Stopwatch start/stop
#    L           Stopwatch lap
#    P           Music play/pause
#    N           Music next track
#    B           Music previous track
#    PgUp/PgDn   Brightness up/down (on settings screen)
# =============================================================================

import sys
import os
import threading

# Make sure imports work from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """
    Entry point. Equivalent to main() in a C embedded OS.
    Never returns (kernel runs forever, like a real OS).
    """

    print()
    print("  █████╗      ██╗██╗  ██╗ ██████╗ ███████╗")
    print(" ██╔══██╗     ██║╚██╗██╔╝██╔═══██╗██╔════╝")
    print(" ███████║     ██║ ╚███╔╝ ██║   ██║███████╗")
    print(" ██╔══██║██   ██║ ██╔██╗ ██║   ██║╚════██║")
    print(" ██║  ██║╚█████╔╝██╔╝ ██╗╚██████╔╝███████║")
    print(" ╚═╝  ╚═╝ ╚════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝")
    print()
    print("           SmartWatch OS v1.0")
    print("    Built for learning. Built to run.")
    print()

    # ── Run bootloader (returns initialized hal + kernel) ─────────────────────
    from boot import run_bootloader
    hal, kernel = run_bootloader()

    # ── Start kernel on a background thread ───────────────────────────────────
    #
    #  REAL OS CONCEPT:
    #  The kernel's scheduler loop must run continuously.
    #  We run it in a thread so the display (tkinter) can own the main thread.
    #  On real hardware, there's only ONE thread — the CPU itself.
    #  The "multitasking" illusion is created by the scheduler rapidly
    #  switching between processes (context switching).

    kernel_thread = threading.Thread(
        target=kernel.run,
        name="kernel_main",
        daemon=True
    )
    kernel_thread.start()

    # ── Main thread: keep alive (display owns this thread) ────────────────────
    #
    #  tkinter's mainloop() is already running inside the display driver thread.
    #  We just keep main alive until the window closes.

    try:
        kernel_thread.join()
    except KeyboardInterrupt:
        print("\n[KERNEL] SIGINT received — shutting down AJX OS")
        hal.display_shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
