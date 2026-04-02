# AJXOS — Smartwatch OS in Python

> A fully functional smartwatch OS simulator built in Python.  
> Not a UI mockup — a real OS architecture with kernel, scheduler, drivers, filesystem, and more.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-Phase%201%20Complete-cyan?style=flat-square)

---

## What Is This?

Most "OS projects" you'll find online are just screen switchers — a few `if/else` statements changing what's displayed. This is different.

AJXOS is a Python simulation of a real OS architecture. Every concept that exists in production smartwatch firmware — bootloader, HAL, kernel scheduler, IRQ handling, syscalls, virtual filesystem, process management, power states, BLE networking, encrypted storage — is implemented here, just with Python instead of C/Assembly underneath.

The goal was to understand *how* an OS works by building one from scratch, before rewriting it in industry-standard languages (Phase 2 of this repo).

---

## Screenshots

| Clock Face | Activity | Heart Rate |
|-----------|----------|------------|
| Analog clock with date complications | Activity rings with 4 metrics | Live ECG waveform + heart zones |

| App Launcher | Notifications | Settings |
|-------------|---------------|----------|
| 9 apps, click to open | Auto-arriving BLE notifications | Toggles + brightness control |

---

## Architecture

```
AJXOS/
├── main.py              # Entry point — the "power button"
├── boot.py              # Bootloader — 7-stage boot sequence  
├── hal.py               # Hardware Abstraction Layer interface
├── drivers.py           # Display + sensor drivers (tkinter + simulated I2C)
├── kernel.py            # Kernel — scheduler, syscalls, IRQ handler
├── fs.py                # Virtual Filesystem — inodes, file descriptors
├── watchos.py           # User space — all 11 watch screens + processes
├── memory_manager.py    # First-fit memory allocator with fragmentation tracking
├── power_manager.py     # Sleep states, wrist-raise detection, battery model
├── network_stack.py     # BLE simulation — auto phone notifications
├── security.py          # Secure boot, encrypted storage, app verification
├── update_manager.py    # OTA firmware update simulation
└── shell.py             # Interactive debug shell (runs in terminal)
```

### How the layers connect

```
[ watchos.py — User Space ]
         ↕ syscalls
[ kernel.py — Kernel ]
         ↕
[ hal.py — Hardware Abstraction ]
         ↕
[ drivers.py — Device Drivers ]
         ↕
[ tkinter window + simulated sensors ]
```

---

## OS Concepts Implemented

| Concept | File | What it does |
|---------|------|-------------|
| Bootloader | `boot.py` | 7-stage boot: POST → HAL init → VFS mount → Kernel init → Process spawn |
| HAL | `hal.py` | Abstracts hardware so kernel works on any platform |
| Device Drivers | `drivers.py` | Simulates SPI display, I2C sensors, GPIO buttons |
| Process Scheduler | `kernel.py` | Priority-based scheduler, PCB per process, 10Hz tick |
| IRQ / IDT | `kernel.py` | Interrupt Descriptor Table, ISRs for buttons and swipes |
| Syscalls | `kernel.py` | `SYS_SENSOR_READ`, `SYS_NAVIGATE`, `SYS_DRAW`, `SYS_FS_*` etc. |
| Virtual Filesystem | `fs.py` | Inode tree, file descriptors (0/1/2 reserved), `open/read/write/close` |
| Memory Manager | `memory_manager.py` | 256KB RAM simulation, first-fit allocator, per-process tracking |
| Power Manager | `power_manager.py` | RUN → SLEEP → DEEP_SLEEP state machine, battery drain model |
| Network Stack | `network_stack.py` | BLE connection state machine, GATT simulation, notification dispatch |
| Security | `security.py` | Secure boot hashing, XOR encrypted storage, HMAC integrity checks |
| OTA Updates | `update_manager.py` | Dual-partition update flow, chunk download simulation, rollback |
| Debug Shell | `shell.py` | `ps`, `kill`, `mem`, `memmap`, `log`, `cat`, `notify`, `power`, `uptime` |

---

## Getting Started

### Requirements

```bash
Python 3.8+
tkinter (included with Python on Windows/Mac, install separately on Linux)
```

On Linux if tkinter is missing:
```bash
sudo apt-get install python3-tk
```

### Run

```bash
git clone https://github.com/ES7/smartwatch-OS
cd smartwatch-OS/python
python main.py
```

---

## Controls

### Navigation
| Key | Action |
|-----|--------|
| `A` | Swipe left |
| `D` | Swipe right |
| `W` | Swipe up |
| `S` / `X` | Swipe down |
| `C` | Crown button (open/close app launcher) |
| `Q` / `Esc` | Back |

### In App Launcher
| Action | Result |
|--------|--------|
| Mouse click on app circle | Open that app |

### App-specific
| Key | Action |
|-----|--------|
| `S` | Stopwatch start/stop |
| `L` | Stopwatch lap |
| `P` | Music play/pause |
| `N` | Music next track |
| `B` | Music previous track |
| `PgUp` / `=` | Brightness up |
| `PgDn` / `-` | Brightness down |

### Debug Shell (in terminal)
```
ps              → list all running processes
kill <pid>      → kill a process
mem             → memory usage per process
memmap          → ASCII memory map of 256KB RAM
log             → tail kernel log
cat <path>      → read a VFS file
ls <path>       → list directory
power           → power manager status + battery
notify <msg>    → push notification to watch
uptime          → system uptime + boot time
```

---

## Boot Sequence

When you run `main.py`, this is what happens:

```
[STAGE 1] Power-On Self Test        → RAM + flash integrity checks
[STAGE 2] Hardware Init (HAL)       → Display driver + sensor bus init
[STAGE 3] Filesystem Mount          → VFS mounted, /sys /data /logs created
[STAGE 4] Kernel Init               → Process table, syscall table, IDT populated
[STAGE 5] Spawning System Processes → 5 processes with PIDs + priorities
[STAGE 6] Wiring Renderer & Input   → UI renderer registered, input handler bound
[STAGE 7] Secondary Systems         → Network, power, security, OTA, shell
```

---

## Screens

| Screen | Navigate to |
|--------|-------------|
| Clock Face | Home (default) |
| Activity | `A` from home |
| Heart Rate | `D` from home |
| Quick Settings | `W` from home |
| Notifications | `S` from home |
| App Launcher | `C` (crown) |
| Music | Apps → Music |
| Stopwatch | Apps → Stopwatch |
| Weather | Apps → Weather |
| Maps | Apps → Maps |

---

## Why Python First?

Industry standard for embedded OS is Assembly (bootloader) and C (kernel). That's what Boat, Noise, and Garmin use in production.

But the *concepts* are identical regardless of language. Building in Python first meant I could focus on understanding what a scheduler does, what a syscall is, why a HAL exists — without fighting memory pointers and compiler errors at the same time.

Phase 2 of this repo (in progress) rewrites AJXOS in C and Assembly — same architecture, same file structure, but running without Python underneath.

---

## Author

**Ebad Sayed**  
[GitHub](https://github.com/ES7) · [Medium Article]([https://github.com/ES7/smartwatch-OS](https://medium.com/@sayedebad.777/i-built-a-smartwatch-os-from-scratch-using-python-heres-what-actually-happened-c93ee0a80185))

---

## License

MIT — see [LICENSE](../LICENSE) for details.
