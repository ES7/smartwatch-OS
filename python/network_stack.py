# =============================================================================
#  network_stack.py — Network Stack
# =============================================================================
#
#  REAL OS CONCEPT:
#  A network stack is the set of software layers that handle communication.
#  It follows the OSI model (7 layers) — each layer does one job and
#  hands data to the next.
#
#  For a smartwatch, two protocols matter:
#
#  BLUETOOTH LE (BLE):
#    Used for phone connection — notifications, sync, calls.
#    Range: ~10 meters. Power: very low (~1mA).
#    Protocol: GATT (Generic Attribute Profile) — client/server model.
#    The watch is a GATT server, phone is a GATT client.
#
#  Wi-Fi:
#    Used for direct internet (firmware updates, music streaming).
#    Power hungry (~50mA) — only used in bursts.
#    Most watches turn Wi-Fi off unless explicitly needed.
#
#  Our simulation:
#    - BLE "connection" to a fake phone
#    - Incoming notifications arrive on a schedule (like real push notifications)
#    - Packet simulation with signal strength (RSSI)
#    - Connection state machine (disconnected → connecting → connected)
# =============================================================================

import threading
import time
import random
import queue


# ── Protocol Constants ────────────────────────────────────────────────────────

BLE_MTU          = 23      # bytes per BLE packet (real default)
BLE_CONN_INTERVAL= 0.05   # 50ms connection interval (real: 7.5ms-4s)
WIFI_CHANNEL     = 6       # 2.4GHz channel


# ── Packet ────────────────────────────────────────────────────────────────────

class Packet:
    """
    Simulates a network packet.
    Real BLE packet: preamble + access address + PDU + CRC = max 258 bytes.
    """
    _seq = 0

    def __init__(self, src, dst, protocol, payload, rssi=None):
        self.seq      = Packet._seq
        Packet._seq  += 1
        self.src      = src
        self.dst      = dst
        self.protocol = protocol     # "BLE" or "WIFI"
        self.payload  = payload      # dict — the actual data
        self.rssi     = rssi or random.randint(-80, -40)  # signal strength dBm
        self.timestamp= time.time()
        self.size     = len(str(payload))   # simulated byte count

    def __repr__(self):
        return (f"<Packet #{self.seq} {self.protocol} "
                f"{self.src}→{self.dst} rssi={self.rssi}dBm>")


# ── Connection State Machine ───────────────────────────────────────────────────

class BLEState:
    DISCONNECTED = "DISCONNECTED"
    ADVERTISING  = "ADVERTISING"    # watch broadcasting, waiting for phone
    CONNECTING   = "CONNECTING"     # handshake in progress
    CONNECTED    = "CONNECTED"
    PAIRING      = "PAIRING"        # security key exchange


# ── BLE Radio ─────────────────────────────────────────────────────────────────

class BLERadio:
    """
    Simulates the Bluetooth LE radio controller.
    Real implementation: talks to a BLE chip (e.g. Nordic nRF52840)
    via HCI (Host Controller Interface) commands.

    State machine:
    DISCONNECTED → ADVERTISING → CONNECTING → CONNECTED
                                              ↓
                                         DISCONNECTED (if out of range)
    """

    PHONE_ADDR = "AA:BB:CC:DD:EE:FF"   # simulated phone MAC address
    WATCH_ADDR = "11:22:33:44:55:66"   # simulated watch MAC address

    def __init__(self, kernel_ref):
        self._kernel    = kernel_ref
        self.state      = BLEState.DISCONNECTED
        self.rssi       = -999     # no signal when disconnected
        self._rx_queue  = queue.Queue()
        self._tx_queue  = queue.Queue()
        self._lock      = threading.Lock()
        self._enabled   = False
        self._conn_time = None
        self._packets_rx= 0
        self._packets_tx= 0

    def enable(self):
        """Turn on BLE radio. Like HCI_Reset + LE_Set_Advertising_Enable."""
        self._enabled = True
        self.state    = BLEState.ADVERTISING
        # Simulate auto-connect to phone after short delay
        threading.Timer(2.0, self._simulate_connect).start()

    def disable(self):
        """Turn off BLE. Like sending HCI command to power down controller."""
        self._enabled = False
        self.state    = BLEState.DISCONNECTED
        self.rssi     = -999

    def _simulate_connect(self):
        if not self._enabled:
            return
        self.state = BLEState.CONNECTING
        time.sleep(0.5)   # handshake delay
        self.state     = BLEState.CONNECTED
        self.rssi      = random.randint(-65, -40)
        self._conn_time= time.monotonic()

    def send(self, payload: dict) -> bool:
        """
        Send a BLE packet to connected device.
        Real: fragments payload into MTU-sized chunks, sends each.
        """
        if self.state != BLEState.CONNECTED:
            return False
        pkt = Packet(self.WATCH_ADDR, self.PHONE_ADDR, "BLE", payload)
        self._tx_queue.put(pkt)
        self._packets_tx += 1
        return True

    def receive(self) -> list:
        """Drain incoming packet queue."""
        packets = []
        while not self._rx_queue.empty():
            try:
                packets.append(self._rx_queue.get_nowait())
            except queue.Empty:
                break
        return packets

    def inject_packet(self, payload: dict):
        """Simulates incoming packet from phone."""
        if self.state == BLEState.CONNECTED:
            pkt = Packet(self.PHONE_ADDR, self.WATCH_ADDR, "BLE", payload,
                        rssi=self.rssi)
            self._rx_queue.put(pkt)
            self._packets_rx += 1

    def status(self) -> dict:
        conn_duration = (time.monotonic() - self._conn_time
                        if self._conn_time else 0)
        return {
            "state":      self.state,
            "enabled":    self._enabled,
            "rssi":       self.rssi,
            "peer":       self.PHONE_ADDR if self.state == BLEState.CONNECTED else None,
            "packets_rx": self._packets_rx,
            "packets_tx": self._packets_tx,
            "connected_for": round(conn_duration, 1),
        }


# ── Wi-Fi Radio ───────────────────────────────────────────────────────────────

class WiFiRadio:
    """
    Simulates Wi-Fi. On real watches, Wi-Fi is off 99% of the time
    — only enabled for OTA updates or music streaming.
    Power cost: ~50mA vs BLE's ~1mA.
    """

    def __init__(self):
        self.enabled  = False
        self.ssid     = None
        self.rssi     = -999
        self.ip       = None

    def enable(self, ssid="HomeNetwork"):
        self.enabled  = True
        self.ssid     = ssid
        time.sleep(0.3)   # association delay
        self.rssi     = random.randint(-70, -30)
        self.ip       = f"192.168.1.{random.randint(100, 200)}"

    def disable(self):
        self.enabled  = False
        self.ssid     = None
        self.rssi     = -999
        self.ip       = None

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "ssid":    self.ssid,
            "rssi":    self.rssi,
            "ip":      self.ip,
        }


# ── Notification Dispatcher ───────────────────────────────────────────────────

class NotificationDispatcher:
    """
    Handles incoming notifications from phone over BLE.
    Real protocol: ANCS (Apple Notification Center Service) for iOS,
    or MAP (Message Access Profile) for Android.

    Receives packets, parses them, pushes to kernel notification system.
    """

    FAKE_NOTIFICATIONS = [
        {"app": "WhatsApp",   "text": "Bhai kahan hai tu?",        "icon": "💬"},
        {"app": "Instagram",  "text": "Someone liked your post",   "icon": "❤️"},
        {"app": "Gmail",      "text": "Meeting at 3 PM today",     "icon": "📧"},
        {"app": "YouTube",    "text": "New video from your channel","icon": "▶️"},
        {"app": "Zomato",     "text": "Your order is on the way",  "icon": "🍕"},
        {"app": "Paytm",      "text": "Payment of ₹299 received",  "icon": "💰"},
        {"app": "LinkedIn",   "text": "You have a new connection",  "icon": "👔"},
        {"app": "Phone",      "text": "Missed call from Maa",      "icon": "📞"},
    ]

    def __init__(self, ble: BLERadio, kernel_ref):
        self._ble    = ble
        self._kernel = kernel_ref
        self._last_notif = 0.0

    def tick(self):
        """
        Called every kernel tick. Checks for incoming BLE packets.
        Occasionally injects a fake notification from "phone".
        """
        # Inject a fake notification every 30-90 seconds randomly
        now = time.monotonic()
        if (self._ble.state == BLEState.CONNECTED and
                now - self._last_notif > random.randint(180, 300)):
            notif = random.choice(self.FAKE_NOTIFICATIONS)
            # Simulate phone sending this over BLE
            self._ble.inject_packet({
                "type": "notification",
                **notif
            })
            self._last_notif = now

        # Process incoming packets
        for pkt in self._ble.receive():
            payload = pkt.payload
            if payload.get("type") == "notification":
                self._kernel.push_notification(
                    payload.get("app", "Phone"),
                    payload.get("text", ""),
                    payload.get("icon", "🔔")
                )


# ── Network Stack ─────────────────────────────────────────────────────────────

class NetworkStack:
    """
    Top-level network manager. Kernel holds one instance.
    Manages BLE + WiFi radios and notification dispatching.
    """

    def __init__(self, kernel_ref):
        self.ble          = BLERadio(kernel_ref)
        self.wifi         = WiFiRadio()
        self.notif        = NotificationDispatcher(self.ble, kernel_ref)
        self._kernel      = kernel_ref

    def enable_ble(self):
        self.ble.enable()

    def disable_ble(self):
        self.ble.disable()

    def tick(self):
        """Called every kernel tick — process incoming packets."""
        self.notif.tick()

        # Simulate RSSI drift (signal strength varies naturally)
        if self.ble.state == BLEState.CONNECTED:
            self.ble.rssi = max(-90, min(-30,
                self.ble.rssi + random.randint(-2, 2)))

        # Random disconnection (simulate walking out of range)
        if (self.ble.state == BLEState.CONNECTED and
                random.random() < 0.0002):
            self.ble.state = BLEState.DISCONNECTED
            self.ble.rssi  = -999
            self._kernel.push_notification(
                "Bluetooth", "Phone disconnected", "🔵")

    def status(self) -> dict:
        return {
            "ble":  self.ble.status(),
            "wifi": self.wifi.status(),
        }


# ── Kernel process function ────────────────────────────────────────────────────

def process_network(kernel):
    """
    pid: network_daemon — priority 3
    Runs every 500ms. Processes incoming packets, manages connections.
    """
    sys = kernel.get_sys_data()
    net = sys.get("_network_stack")
    if net:
        net.tick()
        sys["network"] = net.status()