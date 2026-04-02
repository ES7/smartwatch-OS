# =============================================================================
#  shell.py — AJX OS Shell
# =============================================================================
#
#  REAL OS CONCEPT:
#  A shell is a user-facing program that lets you interact with the OS
#  by typing commands. It's just an app — no special privileges.
#  It talks to the kernel through syscalls like any other process.
#
#  Famous shells:
#    bash, zsh    → Linux/Mac default shells
#    cmd.exe      → Windows
#    PowerShell   → Windows (more powerful)
#
#  On real watches there's no shell — no screen for text input.
#  But during development, engineers connect via UART serial port and
#  use a debug shell to inspect the running OS. Exactly what we're doing.
#
#  Our shell runs in the terminal (separate thread) while the watch UI
#  runs in the tkinter window. Same concept — UART shell + display.
#
#  Commands implemented:
#    ps           → list all processes (like Unix ps)
#    kill <pid>   → kill a process
#    mem          → memory usage stats
#    memmap       → ASCII memory map
#    cat <path>   → read a file from VFS
#    ls <path>    → list directory
#    log          → tail kernel log
#    power        → power manager status
#    notify <msg> → push a notification
#    uptime       → system uptime
#    clear        → clear terminal
#    help         → list commands
# =============================================================================

import threading
import time
import sys


class Shell:
    """
    Interactive debug shell.
    Runs on its own thread so it doesn't block the kernel or UI.
    """

    PROMPT  = "\n\033[96mAJX OS\033[0m:\033[93m~\033[0m$ "
    VERSION = "AJX OS Shell v1.0 (debug mode)"

    COMMANDS = {
        "ps":     "List all running processes",
        "kill":   "Kill a process by PID: kill <pid>",
        "mem":    "Show memory usage statistics",
        "memmap": "Show ASCII memory map",
        "cat":    "Read a file: cat <path>",
        "ls":     "List directory: ls <path>",
        "log":    "Show kernel log (last 20 lines)",
        "power":  "Show power manager status",
        "notify": "Push notification: notify <message>",
        "uptime": "Show system uptime",
        "clear":  "Clear terminal",
        "help":   "Show this help",
        "exit":   "Exit shell (OS keeps running)",
    }

    def __init__(self, kernel):
        self._kernel  = kernel
        self._running = False
        self._thread  = None

    def start(self):
        """Start shell on background thread."""
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop,
            name="shell",
            daemon=True
        )
        self._thread.start()

    def _loop(self):
        """Main shell loop — reads commands, dispatches them."""
        time.sleep(1.0)   # wait for boot to finish printing
        print(f"\n{'='*52}")
        print(f"  {self.VERSION}")
        print(f"  Type 'help' for commands")
        print(f"{'='*52}")

        while self._running:
            try:
                sys.stdout.write(self.PROMPT)
                sys.stdout.flush()
                line = input().strip()
                if not line:
                    continue
                self._dispatch(line)
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                print(f"  shell error: {e}")

    def _dispatch(self, line: str):
        parts   = line.split()
        cmd     = parts[0].lower()
        args    = parts[1:]

        handlers = {
            "ps":     self._cmd_ps,
            "kill":   self._cmd_kill,
            "mem":    self._cmd_mem,
            "memmap": self._cmd_memmap,
            "cat":    self._cmd_cat,
            "ls":     self._cmd_ls,
            "log":    self._cmd_log,
            "power":  self._cmd_power,
            "notify": self._cmd_notify,
            "uptime": self._cmd_uptime,
            "clear":  self._cmd_clear,
            "help":   self._cmd_help,
            "exit":   self._cmd_exit,
        }

        handler = handlers.get(cmd)
        if handler:
            handler(args)
        else:
            print(f"  command not found: '{cmd}'. Type 'help'.")

    # ── Commands ──────────────────────────────────────────────────────────────

    def _cmd_ps(self, args):
        """Like Unix `ps aux` — show all processes."""
        procs = self._kernel.ps()
        print(f"\n  {'PID':>4}  {'NAME':<20} {'STATE':<10} {'PRI':>4}  {'INTERVAL':>8}")
        print(f"  {'─'*4}  {'─'*20} {'─'*10} {'─'*4}  {'─'*8}")
        for p in sorted(procs, key=lambda x: x.pid):
            print(f"  {p.pid:>4}  {p.name:<20} {p.state.value:<10} "
                  f"{p.priority:>4}  {p.interval:>7.2f}s")
        print(f"\n  Total: {len(procs)} processes")

    def _cmd_kill(self, args):
        if not args:
            print("  Usage: kill <pid>")
            return
        try:
            pid = int(args[0])
            self._kernel.kill(pid)
            print(f"  Process {pid} killed.")
        except ValueError:
            print("  PID must be an integer.")

    def _cmd_mem(self, args):
        """Like /proc/meminfo"""
        from memory_manager import mm
        s = mm.stats()
        print(f"\n  ┌─ Memory Usage ──────────────────┐")
        print(f"  │ Total RAM:     {s['total_kb']:>6} KB          │")
        print(f"  │ Kernel region: {s['kernel_kb']:>6} KB (reserved)│")
        print(f"  │ Stack region:  {s['stack_kb']:>6} KB (reserved)│")
        print(f"  │ Heap total:    {s['heap_total_kb']:>6} KB          │")
        print(f"  │ Heap used:     {s['heap_used_kb']:>6} KB  {s['used_pct']:>5.1f}%    │")
        print(f"  │ Heap free:     {s['heap_free_kb']:>6} KB          │")
        print(f"  │ Allocations:   {s['alloc_count']:>6}            │")
        print(f"  └─────────────────────────────────┘")

        # Per-process breakdown
        procs = self._kernel.ps()
        print(f"\n  Per-process usage:")
        print(f"  {'PID':>4}  {'NAME':<20} {'BYTES':>8}  {'ALLOCS':>6}")
        print(f"  {'─'*4}  {'─'*20} {'─'*8}  {'─'*6}")
        for p in sorted(procs, key=lambda x: x.pid):
            usage = mm.pid_usage(p.pid)
            print(f"  {p.pid:>4}  {p.name:<20} "
                  f"{usage['total_bytes']:>8}  {usage['alloc_count']:>6}")

        frag = mm.fragmentation()
        print(f"\n  Fragmentation: {frag}%")

    def _cmd_memmap(self, args):
        from memory_manager import mm
        print()
        print(mm.memmap())

    def _cmd_cat(self, args):
        """Like Unix `cat` — print file contents."""
        if not args:
            print("  Usage: cat <path>")
            return
        from fs import vfs
        path = args[0]
        try:
            content = vfs.read_text(path)
            print(f"\n  ── {path} ──")
            for line in content.splitlines():
                print(f"  {line}")
        except FileNotFoundError:
            print(f"  cat: {path}: No such file or directory")

    def _cmd_ls(self, args):
        """Like Unix `ls` — list directory."""
        from fs import vfs
        path = args[0] if args else "/"
        try:
            entries = vfs.listdir(path)
            print(f"\n  {path}:")
            for entry in sorted(entries):
                full = path.rstrip("/") + "/" + entry
                try:
                    s    = vfs.stat(full)
                    kind = "DIR " if s["is_dir"] else "FILE"
                    size = f"{s['size']}B" if not s["is_dir"] else ""
                    print(f"    [{kind}]  {entry:<30} {size}")
                except Exception:
                    print(f"    {entry}")
        except (FileNotFoundError, NotADirectoryError) as e:
            print(f"  ls: {path}: {e}")

    def _cmd_log(self, args):
        """Tail the kernel log."""
        from fs import vfs
        try:
            content = vfs.read_text("/logs/kernel.log")
            lines   = content.strip().splitlines()
            n       = int(args[0]) if args else 20
            print(f"\n  ── /logs/kernel.log (last {n} lines) ──")
            for line in lines[-n:]:
                print(f"  {line}")
        except FileNotFoundError:
            print("  No kernel log found.")

    def _cmd_power(self, args):
        """Show power manager status."""
        from power_manager import pm
        s = pm.status()
        b = s["battery"]
        print(f"\n  ┌─ Power Status ──────────────────┐")
        print(f"  │ State:     {s['state']:<24}│")
        print(f"  │ Battery:   {b['level']:>5.1f}%  ({b['state']:<16})│")
        print(f"  │ Charging:  {'Yes' if b['charging'] else 'No':<24}│")
        print(f"  │ Est. life: {b['est_hours']:>5.1f} hours              │")
        print(f"  └─────────────────────────────────┘")

        if s["history"]:
            print(f"\n  Recent power transitions:")
            for h in s["history"]:
                print(f"    [{h['time']}] {h['from']} → {h['to']}  ({h['reason']})")

    def _cmd_notify(self, args):
        if not args:
            print("  Usage: notify <message>")
            return
        msg = " ".join(args)
        self._kernel.push_notification("Shell", msg, "💻")
        print(f"  Notification pushed: '{msg}'")

    def _cmd_uptime(self, args):
        sys_data = self._kernel.get_sys_data()
        uptime   = sys_data.get("uptime", 0)
        h = int(uptime // 3600)
        m = int((uptime % 3600) // 60)
        s = int(uptime % 60)
        boot_time = time.strftime(
            "%H:%M:%S",
            time.localtime(sys_data.get("boot_time", time.time()))
        )
        print(f"\n  Uptime:     {h:02d}:{m:02d}:{s:02d}")
        print(f"  Boot time:  {boot_time}")
        print(f"  Processes:  {len(self._kernel.ps())}")

    def _cmd_clear(self, args):
        print("\033[2J\033[H", end="")

    def _cmd_help(self, args):
        print(f"\n  {self.VERSION}")
        print(f"\n  {'COMMAND':<12} DESCRIPTION")
        print(f"  {'─'*12} {'─'*35}")
        for cmd, desc in self.COMMANDS.items():
            print(f"  {cmd:<12} {desc}")

    def _cmd_exit(self, args):
        print("  Shell closed. OS still running.")
        self._running = False
