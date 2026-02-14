"""Holtek Venus MMO (04D9:FC55) USB HID Protocol Implementation.

Reverse-engineered from Windows driver hid.exe v1.3.4 and live device probing.
Uses Interface 2 (vendor HID, Usage Page 0xFFA0) with feature reports.
Report ID 0x02 (16 bytes) and 0x03 (64 bytes). No checksums.

Communication: send_feature_report -> get_feature_report (NOT interrupt reads).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import hid
import time


# -- Device Constants --
VENDOR_ID = 0x04D9
PRODUCT_ID = 0xFC55
INTERFACE = 2  # Vendor HID config interface

# Report IDs
RID_SHORT = 0x02  # 16 bytes total
RID_LONG = 0x03   # 64 bytes total

# Commands (byte 1 after report ID)
CMD_WRITE_CTRL = 0xF1
CMD_READ = 0xF2
CMD_WRITE_DATA = 0xF3
CMD_POLLING = 0xF5

# Write control sub-commands (sent via RID_SHORT)
CTRL_ENTER_WRITE = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x01])
CTRL_COMMIT = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x02])
CTRL_EXIT_WRITE = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x02, 0x10])
CTRL_POST_COMMIT_1 = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x04])
CTRL_POST_COMMIT_2 = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x01])
CTRL_RESET = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x00])
CTRL_FLASH_ACK = bytes([RID_SHORT, CMD_WRITE_CTRL, 0x00, 0x08])

# Memory addresses
ADDR_DPI = 0x20        # DPI config (0x20-0x2F)
ADDR_LED = 0x30        # LED config (0x30-0x3F) -- actually written at 0x00
ADDR_POLLING = 0x38    # Polling rate area
ADDR_BUTTONS = 0x80    # Button map start (2-byte count + 20x4 bytes)
ADDR_BUTTONS_END = 0xD4  # End of button map region

# Button type constants
BTN_LMB = 0x81
BTN_RMB = 0x82
BTN_MMB = 0x83
BTN_BACK = 0x84
BTN_FORWARD = 0x85
BTN_DPI_UP = 0x8B
BTN_DPI_DOWN = 0x8C
BTN_PROFILE = 0x8D
BTN_KEYBOARD = 0x90
BTN_DISABLED = 0x00

# Human-readable type names
BUTTON_TYPE_NAMES = {
    BTN_LMB: "Left Click",
    BTN_RMB: "Right Click",
    BTN_MMB: "Middle Click",
    BTN_BACK: "Back",
    BTN_FORWARD: "Forward",
    BTN_DPI_UP: "DPI Up",
    BTN_DPI_DOWN: "DPI Down",
    BTN_PROFILE: "Profile Switch",
    BTN_KEYBOARD: "Keyboard Key",
    BTN_DISABLED: "Disabled",
}

# Action name to button type constant (for GUI -> protocol)
ACTION_TO_BTN_TYPE = {
    "Left Click": BTN_LMB,
    "Right Click": BTN_RMB,
    "Middle Click": BTN_MMB,
    "Back": BTN_BACK,
    "Forward": BTN_FORWARD,
    "DPI Up": BTN_DPI_UP,
    "DPI Down": BTN_DPI_DOWN,
    "DPI Control": None,  # handled specially
    "Profile Switch": BTN_PROFILE,
    "Keyboard Key": BTN_KEYBOARD,
    "Disabled": BTN_DISABLED,
}


@dataclass(frozen=True)
class HoltekButtonProfile:
    label: str
    index: int  # 0-based index into the 20-button map


# 20 buttons: Side 1-12, Fire, LMB, MMB, RMB, DPI Up, DPI Down, Profile, Scroll Click
# Order matches Windows driver layout
BUTTON_PROFILES = {
    "Button 1": HoltekButtonProfile("Side Button 1", 0),
    "Button 2": HoltekButtonProfile("Side Button 2", 1),
    "Button 3": HoltekButtonProfile("Side Button 3", 2),
    "Button 4": HoltekButtonProfile("Side Button 4", 3),
    "Button 5": HoltekButtonProfile("Side Button 5", 4),
    "Button 6": HoltekButtonProfile("Side Button 6", 5),
    "Button 7": HoltekButtonProfile("Side Button 7", 6),
    "Button 8": HoltekButtonProfile("Side Button 8", 7),
    "Button 9": HoltekButtonProfile("Side Button 9", 8),
    "Button 10": HoltekButtonProfile("Side Button 10", 9),
    "Button 11": HoltekButtonProfile("Side Button 11", 10),
    "Button 12": HoltekButtonProfile("Side Button 12", 11),
    "Button 13": HoltekButtonProfile("Fire Key", 12),
    "Button 14": HoltekButtonProfile("Left Mouse Button", 13),
    "Button 15": HoltekButtonProfile("Middle Mouse Button", 14),
    "Button 16": HoltekButtonProfile("Right Mouse Button", 15),
    "Button 17": HoltekButtonProfile("DPI Up", 16),
    "Button 18": HoltekButtonProfile("DPI Down", 17),
    "Button 19": HoltekButtonProfile("Profile Switch", 18),
    "Button 20": HoltekButtonProfile("Scroll Click", 19),
}

# Default button assignments (factory defaults)
DEFAULT_BUTTON_MAP = [
    (BTN_LMB, 0x00, 0x00, 0x00),     # 1: LMB
    (BTN_RMB, 0x00, 0x00, 0x00),     # 2: RMB
    (BTN_MMB, 0x00, 0x00, 0x00),     # 3: MMB
    (BTN_BACK, 0x00, 0x00, 0x00),    # 4: Back
    (BTN_FORWARD, 0x00, 0x00, 0x00), # 5: Forward
    (BTN_DPI_UP, 0x00, 0x00, 0x00),  # 6: DPI Up
    (BTN_DPI_DOWN, 0x00, 0x00, 0x00),# 7: DPI Down
    (BTN_PROFILE, 0x00, 0x00, 0x00), # 8: Profile
    (BTN_KEYBOARD, 0x00, 0x04, 0x00),# 9: Key A (placeholder)
    (BTN_KEYBOARD, 0x00, 0x05, 0x00),# 10: Key B (placeholder)
    (BTN_KEYBOARD, 0x00, 0x06, 0x00),# 11: Key C (placeholder)
    (BTN_KEYBOARD, 0x00, 0x07, 0x00),# 12: Key D (placeholder)
    (BTN_LMB, 0x00, 0x00, 0x00),     # 13: Fire = LMB
    (BTN_LMB, 0x00, 0x00, 0x00),     # 14: LMB
    (BTN_MMB, 0x00, 0x00, 0x00),     # 15: MMB
    (BTN_RMB, 0x00, 0x00, 0x00),     # 16: RMB
    (BTN_DPI_UP, 0x00, 0x00, 0x00),  # 17: DPI Up
    (BTN_DPI_DOWN, 0x00, 0x00, 0x00),# 18: DPI Down
    (BTN_PROFILE, 0x00, 0x00, 0x00), # 19: Profile
    (BTN_MMB, 0x00, 0x00, 0x00),     # 20: Scroll Click
]

# HID keyboard scancodes (same as Venus Pro HID_KEY_USAGE for the most part)
# Reuse venus_protocol's HID_KEY_USAGE via import in the GUI
# Here we just need the mapping for building packets


# Polling rates supported by Holtek
POLLING_RATES = {
    125: 0x08,   # Code for 125Hz
    250: 0x04,   # Code for 250Hz
    500: 0x02,   # Code for 500Hz
    1000: 0x01,  # Code for 1000Hz
}

POLLING_CODE_TO_RATE = {v: k for k, v in POLLING_RATES.items()}


class HoltekDevice:
    """Device wrapper for Holtek Venus MMO (04D9:FC55).

    Uses HID feature reports on Interface 2.
    Communication: send_feature_report + get_feature_report (no interrupt reads).
    """

    def __init__(self, path: str):
        self._path = path
        self._dev: Optional[hid.device] = None

    def open(self) -> None:
        if self._dev is not None:
            return
        dev = hid.device()
        dev.open_path(self._path.encode() if isinstance(self._path, str) else self._path)
        dev.set_nonblocking(True)
        self._dev = dev

    def close(self) -> None:
        if self._dev is None:
            return
        self._dev.close()
        self._dev = None

    def send_feature(self, data: bytes) -> None:
        """Send a feature report (raw bytes including report ID)."""
        if self._dev is None:
            raise RuntimeError("device not open")
        self._dev.send_feature_report(data)

    def get_feature(self, report_id: int, size: int) -> bytes:
        """Get a feature report response."""
        if self._dev is None:
            raise RuntimeError("device not open")
        # Prepend report ID for get_feature_report
        buf = bytes([report_id]) + bytes(size - 1)
        result = self._dev.get_feature_report(report_id, size)
        return bytes(result) if result else b""

    def send_reliable(self, report: bytes, timeout_ms: int = 500) -> bool:
        """Send a feature report with a short delay (fire-and-forget).

        Holtek has no ACK mechanism. We just send and wait briefly.
        Always returns True unless an exception occurs.
        """
        self.send_feature(report)
        time.sleep(0.008)  # 8ms inter-packet delay
        return True

    def read_memory(self, addr: int, length: int) -> bytes:
        """Read device memory at the given address.

        Sends F2 read command, then gets feature report for response.
        Response format: [rid, 0x08, addr_lo, status, length, 0x00, 0xFA, 0xFA, data...]
        """
        if self._dev is None:
            raise RuntimeError("device not open")

        addr_lo = addr & 0xFF
        addr_hi = (addr >> 8) & 0xFF

        # Build read request
        req = bytearray(16)
        req[0] = RID_SHORT
        req[1] = CMD_READ
        req[2] = addr_lo
        req[3] = addr_hi
        req[4] = length & 0xFF

        self._dev.send_feature_report(bytes(req))
        time.sleep(0.005)

        # Get response
        resp = self._dev.get_feature_report(RID_SHORT, 16)
        if not resp:
            raise RuntimeError(f"Read failed at 0x{addr:04X}: no response")

        resp = bytes(resp)
        # Verify response header
        if len(resp) < 8 + length:
            raise RuntimeError(f"Read failed at 0x{addr:04X}: short response ({len(resp)} bytes)")

        # Data starts at offset 8 (after header: rid, 0x08, addr_lo, status, length, 0x00, 0xFA, 0xFA)
        return resp[8:8 + length]

    def read_memory_long(self, addr: int, length: int) -> bytes:
        """Read device memory using long (64-byte) feature reports for larger reads."""
        if self._dev is None:
            raise RuntimeError("device not open")

        addr_lo = addr & 0xFF
        addr_hi = (addr >> 8) & 0xFF

        # Build read request using short report
        req = bytearray(16)
        req[0] = RID_SHORT
        req[1] = CMD_READ
        req[2] = addr_lo
        req[3] = addr_hi
        req[4] = length & 0xFF

        self._dev.send_feature_report(bytes(req))
        time.sleep(0.005)

        # For larger reads, get response on long report ID
        if length > 8:
            resp = self._dev.get_feature_report(RID_LONG, 64)
        else:
            resp = self._dev.get_feature_report(RID_SHORT, 16)

        if not resp:
            raise RuntimeError(f"Read failed at 0x{addr:04X}: no response")

        resp = bytes(resp)
        return resp[8:8 + length]

    def write_memory(self, addr: int, data: bytes) -> None:
        """Write data to device memory using F3 command."""
        addr_lo = addr & 0xFF
        addr_hi = (addr >> 8) & 0xFF

        if len(data) <= 12:
            # Short report (16 bytes)
            pkt = bytearray(16)
            pkt[0] = RID_SHORT
            pkt[1] = CMD_WRITE_DATA
            pkt[2] = addr_lo
            pkt[3] = addr_hi
            pkt[4:4 + len(data)] = data
            self.send_feature(bytes(pkt))
        else:
            # Long report (64 bytes)
            pkt = bytearray(64)
            pkt[0] = RID_LONG
            pkt[1] = CMD_WRITE_DATA
            pkt[2] = addr_lo
            pkt[3] = addr_hi
            pkt[4:4 + len(data)] = data
            self.send_feature(bytes(pkt))
        time.sleep(0.008)

    def enter_write_mode(self) -> None:
        """Enter flash write mode."""
        self.send_feature(CTRL_ENTER_WRITE.ljust(16, b'\x00'))
        time.sleep(0.01)

    def commit_writes(self) -> None:
        """Commit flash writes with full sequence from Windows driver."""
        self.send_feature(CTRL_EXIT_WRITE.ljust(16, b'\x00'))
        time.sleep(0.01)
        self.send_feature(CTRL_POST_COMMIT_1.ljust(16, b'\x00'))
        time.sleep(0.01)
        self.send_feature(CTRL_POST_COMMIT_2.ljust(16, b'\x00'))
        time.sleep(0.01)
        self.send_feature(CTRL_RESET.ljust(16, b'\x00'))
        time.sleep(0.01)
        self.send_feature(CTRL_FLASH_ACK.ljust(16, b'\x00'))
        time.sleep(0.05)

    def set_polling_rate(self, rate: int) -> None:
        """Set polling rate directly using F5 command."""
        code = POLLING_RATES.get(rate)
        if code is None:
            raise ValueError(f"Unsupported polling rate: {rate}Hz")
        pkt = bytearray(16)
        pkt[0] = RID_SHORT
        pkt[1] = CMD_POLLING
        pkt[2] = code
        self.send_feature(bytes(pkt))
        time.sleep(0.01)


def read_all_config(device: HoltekDevice) -> dict:
    """Read full device configuration.

    Returns dict with keys: 'dpi', 'led', 'polling', 'buttons', 'raw_button_data'
    """
    config = {}

    # Read DPI/LED/polling region (0x20-0x3F) in 8-byte chunks
    settings_data = bytearray()
    for addr in range(0x20, 0x40, 8):
        chunk = device.read_memory(addr, 8)
        settings_data.extend(chunk)

    # Read button map region (0x80-0xDF) in 8-byte chunks
    button_data = bytearray()
    for addr in range(0x80, 0xE0, 8):
        chunk = device.read_memory(addr, 8)
        button_data.extend(chunk)

    # Parse DPI (at relative offset 0x00 from our 0x20 base = addr 0x20)
    # DPI config is stored in the 0x20-0x2F region
    config['dpi_raw'] = bytes(settings_data[0:16])

    # Parse LED/polling (at relative offset 0x10 from our 0x20 base = addr 0x30)
    config['led_raw'] = bytes(settings_data[16:32])

    # Parse buttons
    config['raw_button_data'] = bytes(button_data)
    config['buttons'] = parse_button_map(button_data)

    return config


def parse_button_map(data: bytes) -> list[dict]:
    """Parse the button map from raw data starting at address 0x80.

    Format: 2-byte LE count, then count x 4-byte entries.
    Each entry: [type_lo, type_hi, code_lo, code_hi]
    """
    if len(data) < 2:
        return []

    count = data[0] | (data[1] << 8)
    buttons = []

    for i in range(min(count, 20)):
        offset = 2 + (i * 4)
        if offset + 4 > len(data):
            break

        type_lo = data[offset]
        type_hi = data[offset + 1]
        code_lo = data[offset + 2]
        code_hi = data[offset + 3]

        btn_type = type_lo  # Primary type byte
        hid_code = code_lo  # HID scancode for keyboard keys

        action = BUTTON_TYPE_NAMES.get(btn_type, f"Unknown (0x{btn_type:02X})")

        buttons.append({
            'index': i,
            'type': btn_type,
            'type_hi': type_hi,
            'code': hid_code,
            'code_hi': code_hi,
            'action': action,
            'raw': bytes(data[offset:offset + 4]),
        })

    return buttons


def build_button_entry(action: str, params: dict) -> bytes:
    """Build a 4-byte button map entry for a given action.

    Args:
        action: Action name (e.g., "Left Click", "Keyboard Key")
        params: Parameters dict (e.g., {"key": 0x04} for keyboard)

    Returns:
        4-byte entry: [type_lo, type_hi, code_lo, code_hi]
    """
    if action == "Keyboard Key":
        hid_key = params.get("key", 0)
        return bytes([BTN_KEYBOARD, 0x00, hid_key, 0x00])

    elif action == "Left Click":
        return bytes([BTN_LMB, 0x00, 0x00, 0x00])
    elif action == "Right Click":
        return bytes([BTN_RMB, 0x00, 0x00, 0x00])
    elif action == "Middle Click":
        return bytes([BTN_MMB, 0x00, 0x00, 0x00])
    elif action == "Back":
        return bytes([BTN_BACK, 0x00, 0x00, 0x00])
    elif action == "Forward":
        return bytes([BTN_FORWARD, 0x00, 0x00, 0x00])

    elif action == "DPI Control":
        func = params.get("func", 1)
        if func == 2:  # DPI Up
            return bytes([BTN_DPI_UP, 0x00, 0x00, 0x00])
        elif func == 3:  # DPI Down
            return bytes([BTN_DPI_DOWN, 0x00, 0x00, 0x00])
        else:  # DPI Loop / default
            return bytes([BTN_DPI_UP, 0x00, 0x00, 0x00])

    elif action == "Profile Switch":
        return bytes([BTN_PROFILE, 0x00, 0x00, 0x00])

    elif action == "Disabled":
        return bytes([BTN_DISABLED, 0x00, 0x00, 0x00])

    # Default: disabled
    return bytes([BTN_DISABLED, 0x00, 0x00, 0x00])


def build_write_packets(button_index: int, action: str, params: dict) -> list[bytes]:
    """Build feature report packets to write a single button entry.

    The button map starts at address 0x82 (after the 2-byte count at 0x80).
    Each button is 4 bytes: addr = 0x82 + button_index * 4.

    Returns list of raw feature report bytes (F3 commands).
    """
    entry = build_button_entry(action, params)
    addr = 0x82 + (button_index * 4)

    # Build F3 write packet
    pkt = bytearray(16)
    pkt[0] = RID_SHORT
    pkt[1] = CMD_WRITE_DATA
    pkt[2] = addr & 0xFF
    pkt[3] = (addr >> 8) & 0xFF
    pkt[4:8] = entry

    return [bytes(pkt)]


def build_button_map_packets(buttons: list[tuple[str, dict]]) -> list[bytes]:
    """Build packets to write the full button map.

    Args:
        buttons: List of (action, params) tuples for all 20 buttons.

    Returns list of F3 write packets.
    """
    packets = []

    # Write count first (2 bytes LE at address 0x80)
    count = len(buttons)
    count_pkt = bytearray(16)
    count_pkt[0] = RID_SHORT
    count_pkt[1] = CMD_WRITE_DATA
    count_pkt[2] = 0x80  # addr_lo
    count_pkt[3] = 0x00  # addr_hi
    count_pkt[4] = count & 0xFF
    count_pkt[5] = (count >> 8) & 0xFF
    packets.append(bytes(count_pkt))

    # Write each button entry
    for i, (action, params) in enumerate(buttons):
        packets.extend(build_write_packets(i, action, params))

    return packets


def build_dpi_packets(dpi_values: list[int]) -> list[bytes]:
    """Build packets to write DPI configuration.

    DPI is written at address 0x20.
    Format depends on reverse-engineering; this is a basic implementation.
    """
    packets = []

    # DPI values are written at 0x20 (and 0x46 per Windows driver)
    # Basic: write the raw DPI bytes
    if dpi_values:
        data = bytearray(len(dpi_values))
        for i, val in enumerate(dpi_values):
            data[i] = val & 0xFF

        pkt = bytearray(16)
        pkt[0] = RID_SHORT
        pkt[1] = CMD_WRITE_DATA
        pkt[2] = 0x20  # addr_lo
        pkt[3] = 0x00  # addr_hi
        pkt[4:4 + len(data)] = data[:12]  # Max 12 bytes in short report payload
        packets.append(bytes(pkt))

    return packets


def build_led_packets(r: int, g: int, b: int, mode: int = 1, brightness: int = 100) -> list[bytes]:
    """Build packets to write LED configuration.

    LED config is written at address 0x00 (per Windows driver F3 writes).
    """
    pkt = bytearray(16)
    pkt[0] = RID_SHORT
    pkt[1] = CMD_WRITE_DATA
    pkt[2] = 0x00  # addr_lo for LED
    pkt[3] = 0x00  # addr_hi
    pkt[4] = r & 0xFF
    pkt[5] = g & 0xFF
    pkt[6] = b & 0xFF
    pkt[7] = mode & 0xFF
    pkt[8] = brightness & 0xFF
    return [bytes(pkt)]


def build_polling_packet(rate: int) -> bytes:
    """Build F5 polling rate packet."""
    code = POLLING_RATES.get(rate)
    if code is None:
        raise ValueError(f"Unsupported polling rate: {rate}Hz")
    pkt = bytearray(16)
    pkt[0] = RID_SHORT
    pkt[1] = CMD_POLLING
    pkt[2] = code
    return bytes(pkt)


def button_action_to_gui(btn_type: int, code: int) -> tuple[str, dict]:
    """Convert Holtek button type/code to GUI action/params format.

    Returns: (action_name, params_dict) matching the GUI's format.
    """
    if btn_type == BTN_LMB:
        return "Left Click", {}
    elif btn_type == BTN_RMB:
        return "Right Click", {}
    elif btn_type == BTN_MMB:
        return "Middle Click", {}
    elif btn_type == BTN_BACK:
        return "Back", {}
    elif btn_type == BTN_FORWARD:
        return "Forward", {}
    elif btn_type == BTN_DPI_UP:
        return "DPI Control", {"func": 2}
    elif btn_type == BTN_DPI_DOWN:
        return "DPI Control", {"func": 3}
    elif btn_type == BTN_PROFILE:
        return "Profile Switch", {}
    elif btn_type == BTN_KEYBOARD:
        return "Keyboard Key", {"key": code, "mod": 0}
    elif btn_type == BTN_DISABLED:
        return "Disabled", {}
    else:
        return f"Unknown (0x{btn_type:02X})", {}
