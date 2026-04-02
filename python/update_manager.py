# =============================================================================
#  update_manager.py — OTA Update Manager
# =============================================================================
#
#  REAL OS CONCEPT:
#  OTA (Over-The-Air) updates let manufacturers push new firmware to
#  watches without physical access. This is how your Boat/Noise watch
#  gets new features and bug fixes through its companion app.
#
#  Real OTA flow:
#  1. Server notifies phone: "new firmware v2.1 available"
#  2. Phone downloads firmware package (~2-4MB)
#  3. Phone sends firmware to watch over BLE in small chunks (MTU = 23 bytes)
#  4. Watch stores chunks in a secondary flash partition (not the running one)
#  5. Watch verifies complete package signature
#  6. Watch reboots, bootloader detects new firmware, swaps partitions
#  7. New firmware runs. If it fails to boot 3 times → rollback to old version
#
#  This "dual partition" approach means the watch always has a working
#  fallback — it can never be bricked by a bad update.
#
#  Protocols used:
#    DFU (Device Firmware Update) — Nordic's BLE update protocol
#    FOTA (Firmware Over The Air) — generic term
# =============================================================================

import time
import threading
import hashlib
import random


# ── Update States ─────────────────────────────────────────────────────────────

class UpdateState:
    IDLE         = "IDLE"
    CHECKING     = "CHECKING"       # querying server for updates
    AVAILABLE    = "AVAILABLE"      # new version found
    DOWNLOADING  = "DOWNLOADING"    # receiving chunks over BLE
    VERIFYING    = "VERIFYING"      # checking signature + hash
    READY        = "READY"          # verified, waiting for good time to install
    INSTALLING   = "INSTALLING"     # writing to secondary partition
    REBOOTING    = "REBOOTING"      # about to reboot
    FAILED       = "FAILED"         # something went wrong
    UP_TO_DATE   = "UP_TO_DATE"


# ── Firmware Package ──────────────────────────────────────────────────────────

class FirmwarePackage:
    """Represents a firmware update package."""

    def __init__(self, version: str, size_kb: int, changelog: list):
        self.version   = version
        self.size_kb   = size_kb
        self.changelog = changelog
        self.checksum  = hashlib.sha256(version.encode()).hexdigest()
        self.chunks    = size_kb * 1024 // 23   # BLE MTU-sized chunks
        self.released  = time.strftime("%Y-%m-%d")

    def __repr__(self):
        return f"<FirmwarePackage v{self.version} {self.size_kb}KB>"


# ── Simulated Update Server ───────────────────────────────────────────────────

class UpdateServer:
    """
    Simulates the manufacturer's OTA server.
    Real: HTTPS endpoint, CDN-hosted firmware binaries,
    version database per device model.
    """

    CURRENT_VERSION = "1.0.0"

    AVAILABLE_UPDATES = {
        "1.0.0": FirmwarePackage(
            version   = "1.1.0",
            size_kb   = 512,
            changelog = [
                "Fixed navigation bounce bug",
                "Improved heart rate accuracy",
                "Added sleep tracking",
                "Battery life improved by 15%",
                "New watch faces",
            ]
        ),
        "1.1.0": None,   # already latest
    }

    @staticmethod
    def check(current_version: str) -> FirmwarePackage:
        """Query server for available update. Returns None if up to date."""
        time.sleep(0.5)   # simulate network latency
        return UpdateServer.AVAILABLE_UPDATES.get(current_version)


# ── Update Manager ────────────────────────────────────────────────────────────

class UpdateManager:
    """
    Manages the complete OTA update lifecycle.
    Works with NetworkStack (BLE download) and SecurityManager (verification).
    """

    def __init__(self, kernel_ref, network_ref, security_ref, vfs_ref):
        self._kernel   = kernel_ref
        self._network  = network_ref
        self._security = security_ref
        self._vfs      = vfs_ref

        self.state           = UpdateState.IDLE
        self.current_version = UpdateServer.CURRENT_VERSION
        self.pending_pkg     = None
        self.progress        = 0.0    # 0.0 to 1.0 download progress
        self._download_thread= None
        self._history        = []

    def check_for_updates(self) -> dict:
        """
        Check server for available updates.
        Called automatically or when user triggers in settings.
        """
        self.state = UpdateState.CHECKING
        self._log("Checking for updates...")

        pkg = UpdateServer.check(self.current_version)

        if pkg is None:
            self.state = UpdateState.UP_TO_DATE
            self._log("Already up to date")
            return {"status": "up_to_date", "version": self.current_version}
        else:
            self.state       = UpdateState.AVAILABLE
            self.pending_pkg = pkg
            self._log(f"Update available: v{pkg.version} ({pkg.size_kb}KB)")
            self._kernel.push_notification(
                "System Update",
                f"AJX OS v{pkg.version} is available",
                "🔄"
            )
            return {
                "status":    "available",
                "version":   pkg.version,
                "size_kb":   pkg.size_kb,
                "changelog": pkg.changelog,
            }

    def start_download(self):
        """
        Begin downloading firmware over BLE.
        Real: DFU protocol sends 23-byte chunks, watch ACKs each one.
        """
        if not self.pending_pkg:
            return False
        if self._network.ble.state != "CONNECTED":
            self._log("Download failed: BLE not connected")
            self.state = UpdateState.FAILED
            return False

        self.state    = UpdateState.DOWNLOADING
        self.progress = 0.0
        self._download_thread = threading.Thread(
            target=self._download_loop,
            daemon=True
        )
        self._download_thread.start()
        return True

    def _download_loop(self):
        """
        Simulates receiving firmware chunks over BLE.
        Each chunk = 23 bytes (BLE MTU). Real watches show download progress.
        """
        pkg         = self.pending_pkg
        total_chunks= pkg.chunks
        received    = 0

        # Create staging area in VFS (secondary partition simulation)
        try:
            self._vfs.mkdir("/tmp/ota")
        except Exception:
            pass

        while received < total_chunks:
            if self.state == UpdateState.FAILED:
                return

            # Simulate occasional packet loss (real BLE retransmits)
            if random.random() < 0.02:
                time.sleep(0.1)   # retransmit delay
                continue

            received    += 1
            self.progress= received / total_chunks

            # Write chunk to staging area
            chunk_data = f"chunk_{received}_{random.randbytes(4).hex()}"
            self._vfs.append_text(f"/tmp/ota/firmware.bin", chunk_data)

            time.sleep(0.01)   # simulate BLE transfer time

        self._log(f"Download complete: {pkg.size_kb}KB received")
        self._verify()

    def _verify(self):
        """
        Verify downloaded firmware integrity.
        Real: SHA-256 hash check + RSA signature verification.
        """
        self.state = UpdateState.VERIFYING
        self._log("Verifying firmware integrity...")
        time.sleep(0.5)   # crypto takes time on slow embedded CPUs

        pkg = self.pending_pkg
        # Simulate hash verification
        downloaded_hash = hashlib.sha256(
            pkg.version.encode()
        ).hexdigest()

        if downloaded_hash == pkg.checksum:
            self.state = UpdateState.READY
            self._log("Firmware verified — ready to install")
            self._kernel.push_notification(
                "System Update",
                f"v{pkg.version} ready. Will install tonight.",
                "✅"
            )
        else:
            self.state = UpdateState.FAILED
            self._log("Verification FAILED — firmware corrupted")
            self._security.log_threat("CORRUPT_FIRMWARE",
                f"Hash mismatch for v{pkg.version}")

    def install(self):
        """
        Install verified firmware.
        Real: write to secondary flash partition, set boot flag, reboot.
        The bootloader detects the flag, swaps partitions, boots new firmware.
        If new firmware fails to boot 3 times → rollback to old partition.
        """
        if self.state != UpdateState.READY:
            return False

        self.state = UpdateState.INSTALLING
        self._log("Installing firmware...")
        self._kernel.push_notification("System Update",
            "Installing update — do not power off", "⚡")

        # Simulate flash write time (real: ~30 seconds for 512KB)
        time.sleep(2.0)

        # "Swap partitions"
        old_version          = self.current_version
        self.current_version = self.pending_pkg.version
        self.pending_pkg     = None
        self.progress        = 0.0
        self.state           = UpdateState.REBOOTING

        self._history.append({
            "from":    old_version,
            "to":      self.current_version,
            "time":    time.strftime("%H:%M:%S"),
            "status":  "success",
        })

        self._log(f"Updated: v{old_version} → v{self.current_version}")
        self._kernel.push_notification("System Update",
            f"Updated to v{self.current_version} successfully!", "🎉")

        # Simulate reboot (just reset state in our simulation)
        time.sleep(1.0)
        self.state = UpdateState.IDLE
        return True

    def status(self) -> dict:
        return {
            "current_version": self.current_version,
            "state":           self.state,
            "progress":        round(self.progress * 100, 1),
            "pending":         str(self.pending_pkg) if self.pending_pkg else None,
            "history":         self._history,
        }

    def _log(self, msg: str):
        from fs import vfs
        timestamp = time.strftime("%H:%M:%S")
        vfs.append_text("/logs/kernel.log",
                        f"[{timestamp}] [INFO] [OTA] {msg}\n")


# ── Kernel process function ────────────────────────────────────────────────────

def process_update_check(kernel):
    """
    pid: update_daemon — priority 8 (lowest — never urgent)
    Checks for updates once. After first check, kills itself.
    Real watches check on boot + once every 24 hours.
    """
    sys = kernel.get_sys_data()
    um  = sys.get("_update_manager")
    if um and not sys.get("_update_checked"):
        sys["_update_checked"] = True
        threading.Thread(
            target=um.check_for_updates,
            daemon=True
        ).start()
        # Kill self after triggering check
        for p in kernel.ps():
            if p.name == "update_daemon":
                kernel.kill(p.pid)
                break
