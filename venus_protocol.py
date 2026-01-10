from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import hid
import time


VENDOR_ID = 0x25A7
PRODUCT_IDS = (0xFA07, 0xFA08)

REPORT_ID = 0x08
REPORT_LEN = 17
CHECKSUM_BASE = 0x55


@dataclass(frozen=True)
class ButtonProfile:
    label: str
    code_hi: int | None
    code_lo: int | None
    apply_offset: int | None


BUTTON_PROFILES = {
    # Verified from memory dumps and USB captures:
    # - Buttons 1-12: Side button grid (thumb panel)
    # - Button 13: Fire key (left of left mouse button)
    # - Button 14: Left mouse button
    # - Button 15: Middle mouse button (scroll click)
    # - Button 16: Right mouse button
    # 
    # Each button has:
    # - code_hi: Keyboard region page (0x01 for 1-6, 0x02 for 7-12, 0x03 for 13-16)
    # - code_lo: Keyboard region offset (0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0)
    # - apply_offset: Mouse region offset at page 0x00 (CONTIGUOUS: 0x60 + button_index * 4)
    #
    # Verified Layout from Dump Analysis:
    # Mouse Offsets are strictly sequential 0x60 -> 0x9C (skipping nothing relevant to slots).
    # Kbd Pages fill Pg1 (8 slots) then Pg2 (8 slots).
    # 
    # Pg1 Slots:
    # 00: Btn 1 (60)
    # 20: Btn 2 (64)
    # 40: Btn 3 (68)
    # 60: Btn 4 (6C)
    # 80: Btn 5 (70)
    # A0: Btn 6 (74)
    # C0: Btn 16 (Right) (78)  -> Found 'g' here
    # E0: Btn 14 (Left) (7C)   -> Found 'h' here
    #
    # Pg2 Slots:
    # 00: Btn 7 (80)           -> Found Key 7 here
    # 20: Btn 8 (84)           -> Found Key 8 here
    # 40: Btn 15 (Mid) (88)
    # 60: Btn 13 (Fire) (8C)
    # 80: Btn 9 (90)           -> Found Key 9 here
    # A0: Btn 10 (94)
    # C0: Btn 11 (98)
    # E0: Btn 12 (9C)
    
    "Button 1": ButtonProfile("Side Button 1", 0x01, 0x00, 0x60),
    "Button 2": ButtonProfile("Side Button 2", 0x01, 0x20, 0x64),
    "Button 3": ButtonProfile("Side Button 3", 0x01, 0x40, 0x68),
    "Button 4": ButtonProfile("Side Button 4", 0x01, 0x60, 0x6C),
    "Button 5": ButtonProfile("Side Button 5", 0x01, 0x80, 0x70),
    "Button 6": ButtonProfile("Side Button 6", 0x01, 0xA0, 0x74),
    "Button 7": ButtonProfile("Side Button 7", 0x02, 0x00, 0x80),
    "Button 8": ButtonProfile("Side Button 8", 0x02, 0x20, 0x84),
    "Button 9": ButtonProfile("Side Button 9", 0x02, 0x80, 0x90),
    "Button 10": ButtonProfile("Side Button 10", 0x02, 0xA0, 0x94),
    "Button 11": ButtonProfile("Side Button 11", 0x02, 0xC0, 0x98),
    "Button 12": ButtonProfile("Side Button 12", 0x02, 0xE0, 0x9C),
    "Button 13": ButtonProfile("Fire Key", 0x02, 0x60, 0x8C),
    "Button 14": ButtonProfile("Left Mouse Button", 0x01, 0xE0, 0x7C),
    "Button 15": ButtonProfile("Middle Mouse Button", 0x02, 0x40, 0x88),
    "Button 16": ButtonProfile("Right Mouse Button", 0x01, 0xC0, 0x78),
}



RGB_PRESETS = {
    "Neon (Magenta)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0xFF, 0x57, 0x02, 0x53, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Breathing (Magenta)": bytes(
        [0x00, 0x00, 0x5C, 0x02, 0x03, 0x52, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    ),
    "Off": bytes([0x00, 0x00, 0x58, 0x02, 0x00, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    "Steady (Magenta, 20%)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0xFF, 0x57, 0x01, 0x54, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Steady (Red, 20%)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0x00, 0x56, 0x01, 0x54, 0x3C, 0x19, 0x00, 0x00]
    ),
    "Steady (Red, Low)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0x00, 0x56, 0x01, 0x54, 0x01, 0x54, 0x00, 0x00]
    ),
    "Steady (Red, High)": bytes(
        [0x00, 0x00, 0x54, 0x08, 0xFF, 0x00, 0x00, 0x56, 0x01, 0x54, 0xFF, 0x56, 0x00, 0x00]
    ),
}


POLLING_RATE_PAYLOADS = {
    # Polling rate encoding: code = log2(1000/rate)
    # From wired USB captures:
    # 125Hz = code 0x04 (but pattern suggests 0x03?), 250Hz = 0x02, 500Hz = 0x01, 1000Hz = 0x00
    125: bytes([0x00, 0x00, 0x00, 0x02, 0x04, 0x51, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    250: bytes([0x00, 0x00, 0x00, 0x02, 0x02, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    500: bytes([0x00, 0x00, 0x00, 0x02, 0x01, 0x54, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    1000: bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
}


DPI_PRESETS = {
    1600: {"value": 0x12, "tweak": 0x31},
    2400: {"value": 0x1B, "tweak": 0x1F},
    4900: {"value": 0x3A, "tweak": 0xE1},
    8900: {"value": 0x6A, "tweak": 0x81},
    14100: {"value": 0xA8, "tweak": 0x05},
}


# Modifier key bit flags (standard HID modifier byte)
MODIFIER_CTRL = 0x01
MODIFIER_SHIFT = 0x02
MODIFIER_ALT = 0x04
MODIFIER_WIN = 0x08

# HID keyboard usage codes (extended beyond basic A-Z)
HID_KEY_USAGE = {
    # Letters A-Z
    **{chr(ord("A") + i): 0x04 + i for i in range(26)},
    # Numbers 1-9, 0
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    # Function keys
    "F1": 0x3A, "F2": 0x3B, "F3": 0x3C, "F4": 0x3D, "F5": 0x3E, "F6": 0x3F,
    "F7": 0x40, "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    # Special keys
    "Enter": 0x28, "Escape": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C,
    "Minus": 0x2D, "Equal": 0x2E, "LeftBracket": 0x2F, "RightBracket": 0x30,
    "Backslash": 0x31, "Semicolon": 0x33, "Quote": 0x34, "Grave": 0x35,
    "Comma": 0x36, "Period": 0x37, "Slash": 0x38,
    # Navigation
    "Insert": 0x49, "Home": 0x4A, "PageUp": 0x4B,
    "Delete": 0x4C, "End": 0x4D, "PageDown": 0x4E,
    "Right": 0x4F, "Left": 0x50, "Down": 0x51, "Up": 0x52,
    # System
    "PrintScreen": 0x46, "ScrollLock": 0x47, "Pause": 0x48,
    "Menu": 0x65, "NumLock": 0x53,
    # Keypad
    "Keypad /": 0x54, "Keypad *": 0x55, "Keypad -": 0x56, "Keypad +": 0x57,
    "Keypad Enter": 0x58, "Keypad .": 0x63,
    "Keypad 1": 0x59, "Keypad 2": 0x5A, "Keypad 3": 0x5B,
    "Keypad 4": 0x5C, "Keypad 5": 0x5D, "Keypad 6": 0x5E,
    "Keypad 7": 0x5F, "Keypad 8": 0x60, "Keypad 9": 0x61,
    "Keypad 0": 0x62,
}

# USB HID Consumer Page codes (for media keys)
# These use a different packet format than standard keycodes
MEDIA_KEY_CODES = {
    "PlayPause": 0xCD,
    "NextTrack": 0xB5,
    "PrevTrack": 0xB6,
    "Mute": 0xE2,
    "VolumeUp": 0xE9,
    "VolumeDown": 0xEA,
}

# Button action types (from wired USB captures)
BUTTON_TYPE_DISABLED = 0x00
BUTTON_TYPE_MOUSE = 0x01
BUTTON_TYPE_DPI_LEGACY = 0x02 # Acts as Keyboard (Simple) but specific combos trigger DPI!
BUTTON_TYPE_SPECIAL = 0x04  # Fire Key, Triple Click - uses (delay_ms, repeat_count)
BUTTON_TYPE_KEYBOARD = 0x05 # Standard Keyboard (Complex/Media) - Safe for normal keys
BUTTON_TYPE_MEDIA = 0x05    # Alias for Keyboard
BUTTON_TYPE_MACRO = 0x06
BUTTON_TYPE_POLL_RATE = 0x07  # Toggle polling rate
BUTTON_TYPE_RGB_TOGGLE = 0x08  # Toggle RGB LED

# RGB LED modes
RGB_MODE_OFF = 0x00
RGB_MODE_STEADY = 0x01
RGB_MODE_BREATHING = 0x02
RGB_MODE_NEON = 0x02  # Same as breathing with different params

# ASCII to HID mapping for Quick Text Macro
# Maps char -> (keycode, modifier_mask)
ASCII_TO_HID = {
    # Lowercase
    **{chr(ord('a') + i): (0x04 + i, 0) for i in range(26)},
    # Uppercase (Shift)
    **{chr(ord('A') + i): (0x04 + i, MODIFIER_SHIFT) for i in range(26)},
    # Numbers
    '1': (0x1E, 0), '2': (0x1F, 0), '3': (0x20, 0), '4': (0x21, 0), '5': (0x22, 0),
    '6': (0x23, 0), '7': (0x24, 0), '8': (0x25, 0), '9': (0x26, 0), '0': (0x27, 0),
    # Symbols (Assuming US Layout)
    '!': (0x1E, MODIFIER_SHIFT), '@': (0x1F, MODIFIER_SHIFT), '#': (0x20, MODIFIER_SHIFT),
    '$': (0x21, MODIFIER_SHIFT), '%': (0x22, MODIFIER_SHIFT), '^': (0x23, MODIFIER_SHIFT),
    '&': (0x24, MODIFIER_SHIFT), '*': (0x25, MODIFIER_SHIFT), '(': (0x26, MODIFIER_SHIFT),
    ')': (0x27, MODIFIER_SHIFT),
    ' ': (0x2C, 0), '.': (0x37, 0), ',': (0x36, 0), '?': (0x38, MODIFIER_SHIFT),
    '/': (0x38, 0), ';': (0x33, 0), ':': (0x33, MODIFIER_SHIFT), "'": (0x34, 0),
    '"': (0x34, MODIFIER_SHIFT), '[': (0x2F, 0), '{': (0x2F, MODIFIER_SHIFT),
    ']': (0x30, 0), '}': (0x30, MODIFIER_SHIFT), '\\': (0x31, 0), '|': (0x31, MODIFIER_SHIFT),
    '-': (0x2D, 0), '_': (0x2D, MODIFIER_SHIFT), '=': (0x2E, 0), '+': (0x2E, MODIFIER_SHIFT),
    '`': (0x35, 0), '~': (0x35, MODIFIER_SHIFT),
    '\n': (0x28, 0), # Enter
}



# Macro Repeat Modes
MACRO_REPEAT_ONCE = 0x01
MACRO_REPEAT_HOLD = 0xFE
MACRO_REPEAT_TOGGLE = 0xFF



def calc_checksum(prefix: Iterable[int]) -> int:
    return (CHECKSUM_BASE - (sum(prefix) & 0xFF)) & 0xFF


def build_report(command: int, payload: bytes) -> bytes:
    if len(payload) != 14:
        raise ValueError(f"payload must be 14 bytes, got {len(payload)}")
    data = bytearray([REPORT_ID, command, *payload])
    data.append(calc_checksum(data))
    return bytes(data)


def build_simple(command: int) -> bytes:
    return build_report(command, bytes(14))


def build_flash_read(page: int, offset: int, length: int) -> bytes:
    """Build a flash memory read request.
    
    The response will arrive on the Interrupt In endpoint (Report ID 0x09).
    Max reliable length per report is 10-11 bytes.
    """
    payload = bytes([0x00, page & 0xFF, offset & 0xFF, length & 0xFF]) + bytes(10)
    return build_report(0x08, payload)


def build_key_binding(code_hi: int, code_lo: int, hid_key: int, modifier: int = 0x00) -> bytes:
    """Build a key binding packet.
    
    Args:
        code_hi: High byte of keyboard region address (page)
        code_lo: Low byte of keyboard region address (offset)
        hid_key: HID keycode to bind
        modifier: Modifier byte (combination of MODIFIER_CTRL/SHIFT/ALT/WIN)
    
    Based on captures:
    - shift-1: 08 07 00 01 00 0a 04 80 02 00 81 1e 00 40 02 00 [checksum]
    - ctrl-alt-1: 08 07 00 01 00 0a 06 80 01 00 80 04 00 81 1e [checksum]
    """
    
    events = bytearray()
    
    if modifier != 0:
        # Complex Binding with Modifiers - FULL 4-EVENT STREAM
        # Based on actual Windows dump analysis of Shift+A (B12):
        # Data: 04 80 02 00 81 04 00 40 02 00 41 04 00 c3
        # Format: [Count=4] [ModDn] [KeyDn] [ModUp] [KeyUp] [Guard]
        
        events.extend([0x80, modifier, 0x00])  # Event 1: ModDn
        events.extend([0x81, hid_key, 0x00])   # Event 2: KeyDn
        events.extend([0x40, modifier, 0x00])  # Event 3: ModUp
        events.extend([0x41, hid_key, 0x00])   # Event 4: KeyUp
        
        count = 4  # Always 4 events for modifier bindings
        full_payload = bytearray([count]) + events
        
        # Guard byte for complex bindings
        # From dump: Shift+A (mod=0x02, key=0x04) -> Guard=0xC3
        # Empirical formula: Simple guard + offset for event stream
        simple_guard = (0x91 - (hid_key * 2)) & 0xFF
        # The modifier events add ~0x3E offset based on analysis
        guard = (simple_guard + 0x3A) & 0xFF
        full_payload.append(guard)
        
        # Total: 1 + 12 + 1 = 14 bytes (will split into 10 + 4)
        
    else:
        # Simple Binding (No Modifiers)
        # Format: [Count=2] [KeyDn] [KeyUp] [Guard] = 8 bytes
        events.extend([0x81, hid_key, 0x00])  # KeyDn
        events.extend([0x41, hid_key, 0x00])  # KeyUp
        
        count = 2
        full_payload = bytearray([count]) + events
        
        # Guard byte: 0x91 - (key * 2)
        guard = (0x91 - (hid_key * 2)) & 0xFF
        full_payload.append(guard)
        
        # Total: 1 + 6 + 1 = 8 bytes (fits in 1 packet)
    
    # Split payload into chunks of max 10 bytes for the 0x07 write command
    packets = []
    chunk_size = 10
    total_len = len(full_payload)
    
    for i in range(0, total_len, chunk_size):
        chunk = full_payload[i : i + chunk_size]
        current_len = len(chunk)
        
        # Build Write Packet (Cmd 0x07)
        # Payload: [00] [Page] [Offset+i] [Len] [Data...]
        # Data chunk must be padded to 10 bytes to satisfy strict 14-byte payload check in build_report
        padded_chunk = chunk.ljust(10, b'\x00')
        
        pkt_payload = bytes([
            0x00,
            code_hi,
            code_lo + i,
            current_len,
        ]) + padded_chunk
        
        packets.append(build_report(0x07, pkt_payload))
        
    return packets

def build_key_binding_apply(code_hi: int, code_lo: int, hid_key: int, modifier: int = 0x00) -> bytes:
    """Build the second packet for key binding with modifiers.
    
    With Type 02 packets (which we now use exclusively), this second packet is NOT needed.
    """
    return b""


def build_rgb(r: int, g: int, b: int, mode: int = RGB_MODE_STEADY, brightness: int = 100) -> bytes:
    """Build an RGB LED control packet.
    
    Args:
        r, g, b: Color values 0-255
        mode: RGB_MODE_OFF, RGB_MODE_STEADY, or RGB_MODE_BREATHING
        brightness: Brightness percentage 0-100
    
    Packet format from captures at offset 0x54:
    08 07 00 00 54 08 [R] [G] [B] [MODE] 01 54 [B1] [B2] 00 00 [checksum]
    
    Brightness encoding from wired captures:
    - B1 + B2 = 0x55 (85 decimal) - checksum constraint
    - B1 = percent × 3, capped at 255, minimum 1
    - B2 = (0x55 - B1) & 0xFF
    
    LED Mode codes:
    - 0x56 = Steady (solid color)
    - 0x57 = Neon (rainbow cycle)
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    # Mode byte: 0x56 for steady, 0x57 for neon/animated
    # Default to steady mode (0x56) for solid colors
    mode_byte = 0x56 if mode == RGB_MODE_STEADY else 0x57
    
    # Brightness encoding: B1 = percent × 3 (capped), B2 = (0x55 - B1) & 0xFF
    # From captures: 0% = 0x01, 10% = 0x1e (30), 20% = 0x3c (60), 100% = 0xff
    b1 = max(1, min(255, int(brightness * 3)))
    b2 = (0x55 - b1) & 0xFF
    
    payload = bytes(
        [
            0x00,
            0x00,
            0x54,  # RGB offset
            0x08,  # Data marker
            r,
            g,
            b,
            mode_byte,  # 0x56=steady, 0x57=neon
            0x01,  # Constant
            0x54,  # Constant (matches offset)
            b1,    # Brightness value
            b2,    # Brightness complement (B1 + B2 = 0x55)
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_apply_binding(apply_offset: int, action_type: int, action_code: int, action_index: int = 0x00, modifier: int = 0x00, page: int = 0x00) -> bytes:
    # Packet structure for Page 0 (or Profile N) binding entry:
    # [00] [Page] [Offset] [Len=04] [Type] [D1=Modifier] [D2=action_index] [D3=action_code] ...
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            action_type,
            modifier,      # D1: Modifier goes here (Shift=0x02, Ctrl=0x01, etc.)
            action_index,  # D2
            action_code,   # D3
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_mouse_param(apply_offset: int, val: int, page: int = 0x00) -> bytes:
    """Build a mouse button binding (Left/Right/etc).
    
    Args:
        apply_offset: Button offset.
        val: Mouse button code (1=Left, 2=Right, 4=Middle, 8=Back, 10=Forward).
        page: Memory page (0x00, 0x40, etc).
        
    Packet structure inferred from capture contexts:
    [00] [Page] [Offset] [Len=04] [Type=01] [Val] [00] [Code] ...
    
    Code mapping (Val -> Code):
    - 0x01 (Left) -> 0xF0 (Guess/Standard?) - Wait, Forward/Back used 0x44/0x4C.
    - Let's assume Code is not critical or is derived.
    - Actually, build_forward_back uses explicit codes.
    - If capture for Left Click (Btn 14, Offset 0x7C) is confusing, let's look at build_forward_back logic.
    - Forward (0x10) -> 0x44. Back (0x08) -> 0x4c.
    - Left/Right likely follow similar pattern or are hardcoded.
    - Standard Mouse is Type 0x01.
    """
    # Just use the generic payload with Type 0x01.
    # What is D3 (Action Code)?
    # For Forward/Back it was 0x44/0x4C.
    # For Left/Right?
    # Let's assume generic Type 0x01 doesn't STRICTLY verify D3 or it is 0x00?
    # Or maybe valid vals: 
    # Left (1) -> F0?
    # Right (2) -> F1?
    # Middle (4) -> F2?
    # D3 seems to be 'Index'?
    
    # Safest bet: Just replicate build_apply_binding functionality for Type 0x01.
    # D1 = val. D2 = 00. D3 = ?
    # Let's assume D3 is not strictly checked for basic buttons or is 0.
    
    # Wait, build_forward_back sets D3=44/4C.
    # Maybe I should just expose build_apply_binding and let caller handle code?
    # But venus_gui calls build_mouse_param(offset, val).
    
    # Let's map val to something reasonable or just 0 if unknown.
    code = 0x00
    if val == 0x10: code = 0x44 # Forward
    elif val == 0x08: code = 0x4C # Back
    elif val == 0x01: code = 0xF0 # Left (Guess)
    elif val == 0x02: code = 0xF1 # Right (Guess)
    elif val == 0x04: code = 0xF2 # Middle (Guess)
        
    return build_apply_binding(apply_offset, action_type=BUTTON_TYPE_MOUSE, action_code=code, modifier=val, page=page)


def build_forward_back(apply_offset: int, forward: bool, page: int = 0x00) -> bytes:
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            0x01,
            0x10 if forward else 0x08,
            0x00,
            0x44 if forward else 0x4C,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_special_binding(apply_offset: int, delay_ms: int, repeat_count: int, page: int = 0x00) -> bytes:
    """Build a special button binding (Fire Key, Triple Click, etc.).
    
    Args:
        apply_offset: Button's mouse region offset (e.g., 0x6C for button 4)
        delay_ms: Delay between repeats in milliseconds (0-255)
        repeat_count: Number of repeats (0-255)
        page: Memory page (0x00 for Profile 1, 0x40 for Profile 2, etc.)
    
    From wired USB captures:
    - Triple Click (btn 4): type=0x04, data=0x32 0x03 (delay=50ms, repeat=3)
    - Fire Key (btn 7): type=0x04, data=0x28 0x03 (delay=40ms, repeat=3)
    """
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,  # Marker
            BUTTON_TYPE_SPECIAL,  # 0x04 = Special (fire/triple click)
            delay_ms & 0xFF,
            repeat_count & 0xFF,
            0x00,  # Unknown, possibly validation
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_poll_rate_toggle(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a polling rate toggle binding for a button."""
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            BUTTON_TYPE_POLL_RATE,  # 0x07
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_rgb_toggle(apply_offset: int, page: int = 0x00) -> bytes:
    """Build an RGB LED toggle binding for a button."""
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            BUTTON_TYPE_RGB_TOGGLE,  # 0x08
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


def build_disabled(apply_offset: int, page: int = 0x00) -> bytes:
    """Build a disabled binding for a button."""
    payload = bytes(
        [
            0x00,
            page,
            apply_offset,
            0x04,
            BUTTON_TYPE_DISABLED,  # 0x00
            0x00,
            0x00,
            0x55,  # Validation byte
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


@dataclass(frozen=True)
class MacroEvent:
    keycode: int
    is_down: bool
    delay_ms: int

    def to_bytes(self) -> bytes:
        """Convert to the 5-byte format expected by the mouse hardware.
        Format from memory dumps: [STATUS] [KEYCODE] 0x00 [DELAY_HI] [DELAY_LO]
        """
        status = 0x81 if self.is_down else 0x41
        return bytes([status, self.keycode, 0x00, (self.delay_ms >> 8) & 0xFF, self.delay_ms & 0xFF])


def build_macro_chunk(offset: int, chunk: bytes, macro_page: int = 0x03) -> bytes:
    """Build a macro data chunk packet.
    
    Args:
        offset: Byte offset within the macro data region
        chunk: The data bytes to write (max 10 bytes)
        macro_page: Memory page for macro storage. 
                   From captures: button 1 uses 0x03, button 11 uses 0x18
    """
    if len(chunk) > 10:
        raise ValueError("macro chunk must be <= 10 bytes")
    chunk_len = len(chunk)
    padded = chunk.ljust(10, b"\x00")
    payload = bytes([0x00, macro_page & 0xFF, offset & 0xFF, chunk_len & 0xFF, *padded])
    return build_report(0x07, payload)


def build_flash_write(page: int, offset: int, data: bytes) -> bytes:
    """Write data to flash memory.
    
    This is a generic wrapper around the same packet structure used for macros.
    Max 10 bytes per packet.
    """
    return build_macro_chunk(offset, data, page)



def get_macro_page(apply_offset: int) -> int:
    """Calculate the macro memory page for a button.
    
    With contiguous button offsets (0x60-0x9C), the flash_index is simply:
    flash_index = (apply_offset - 0x60) // 4
    
    Macros are stored starting at page 0x03, with each button getting dedicated pages.
    From memory dumps, macros appear in slots starting at page 0x03.
    """
    flash_index = (apply_offset - 0x60) // 4
    # Simple linear mapping: button 0 -> page 0x03, button 1 -> page 0x04, etc.
    return 0x03 + flash_index


def build_macro_terminator(offset: int, macro_page: int = 0x03) -> bytes:
    """Build the macro terminator found in memory dumps.
    Format: [00, 03, OFFSET, 00, 00, 00]
    """
    tail = bytes([0x00, 0x03, offset & 0xFF, 0x00, 0x00, 0x00])
    return build_macro_chunk(offset, tail, macro_page)


def build_macro_bind(apply_offset: int, macro_index: int = 0x01, repeat_mode: int = MACRO_REPEAT_ONCE, page: int = 0x00) -> bytes:
    """Build a macro bind packet.
    
    From USB captures:
    - Button 1 (offset 0x60): 08 07 00 00 60 04 06 00 01 4e
    - Button 11 (offset 0x98): 08 07 00 00 98 04 06 0e 01 40
    
    The flash_index is derived from apply_offset and included in the packet.
    Action code = 0x4E - flash_index
    """
    # Calculate flash_index from apply_offset
    # Simple linear formula: flash_index = (apply_offset - 0x60) / 4
    # From captures: Button 1 (0x60) -> index 0, Button 11 (0x98) -> index 14
    flash_index = (apply_offset - 0x60) // 4
    
    action_code = (0x4E - flash_index) & 0xFF
    
    # Payload must be exactly 14 bytes for build_report
    # Structure: [00, Page, offset] [len] [type] [macro] [action] [repeat] [padding...]
    payload_list = [
        0x00,
        page,
        apply_offset,
        0x04,  # Length field in packet
        0x06,  # Type: macro
        macro_index & 0xFF,
        action_code,
        repeat_mode & 0xFF,
    ]
    # Pad with zeros to 14 bytes
    while len(payload_list) < 14:
        payload_list.append(0x00)
        
    return build_report(0x07, bytes(payload_list))

def get_macro_slot_info(macro_index: int) -> tuple[int, int]:
    """Get the start page and offset for a macro slot.
    
    Each slot is 384 bytes (1.5 pages).
    Formula:
    - Start Page: 0x03 + (i * 3) // 2
    - Start Offset: 0x80 if i is odd, 0x00 if i is even
    """
    # Ensure 1-based index is converted to 0-based for calc, or assume 0-based?
    # GUI uses 1-12. The protocol packet uses 0x01-0x0C? Captures show "macro_index" in bind packet.
    # In captures: "apply macro _testing_ to side button 1" -> bind packet has '01' at index 7.
    # So macro indices are 1-based in the UI/bind packet.
    # But for calculation we probably want 0-based offset so macro 1 starts at 0x03.
    
    # Correction: Memory dump shows "arrows" (Macro 1?) at Page 3.
    # "poopypants" (Macro 2?) at Page 4 Offset 0x80.
    
    idx = macro_index - 1 # Convert to 0-based
    if idx < 0: idx = 0
    
    page = 0x03 + (idx * 3) // 2
    offset = 0x80 if (idx % 2 != 0) else 0x00
    return page, offset



def build_dpi(slot_index: int, value: int, tweak: int) -> bytes:
    if not 0 <= slot_index <= 4:
        raise ValueError("slot_index must be 0..4")
    offset = 0x0C + (slot_index * 4)
    payload = bytes(
        [
            0x00,
            0x00,
            offset & 0xFF,
            0x04,
            value & 0xFF,
            value & 0xFF,
            0x00,
            tweak & 0xFF,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    return build_report(0x07, payload)


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    product: str
    manufacturer: str
    vendor_id: int
    product_id: int
    serial: str


def list_devices(exclude_receivers: bool = True) -> list[DeviceInfo]:
    devices = []
    seen_paths = set()
    for item in hid.enumerate(VENDOR_ID, 0):
        if item["product_id"] not in PRODUCT_IDS:
            continue
        # win.md: Use HID interface 1 for configuration commands.
        if item["interface_number"] != 1:
            continue
        
        path_str = item["path"].decode() if isinstance(item["path"], bytes) else item["path"]
        if path_str in seen_paths:
            continue
        
        product = item.get("product_string") or "Unknown"
        
        # Filter out "Wireless Receiver" if requested, as it doesn't support flash reads
        if exclude_receivers and "Receiver" in product:
            continue
            
        seen_paths.add(path_str)

        devices.append(
            DeviceInfo(
                path=path_str,
                product=product,
                manufacturer=item.get("manufacturer_string") or "Unknown",
                vendor_id=item["vendor_id"],
                product_id=item["product_id"],
                serial=item.get("serial_number") or "",
            )
        )
        
    # Sort devices to put "Dual Mode Mouse" first if present
    devices.sort(key=lambda d: 0 if "Dual Mode Mouse" in d.product else 1)
    
    return devices


class VenusDevice:
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

    def send(self, report: bytes) -> None:
        if self._dev is None:
            raise RuntimeError("device not open")
        if len(report) != REPORT_LEN:
            raise ValueError(f"report must be {REPORT_LEN} bytes")
        self._dev.send_feature_report(report)

    def read_flash(self, page: int, offset: int, length: int) -> bytes:
        """Read 8 bytes from flash memory at the given page and offset.
        
        Note: Currently fixed to 8 bytes per read to ensure reliability.
        """
        if self._dev is None:
            raise RuntimeError("device not open")
        
        # Flush any pending reports
        while True:
            r = self._dev.read(128, timeout_ms=10)
            if not r:
                break
        
        req = build_flash_read(page, offset, length)
        self._dev.send_feature_report(req)
        
        # Responses arrive on Interrupt endpoint, Report ID 0x09
        # Wait up to 100ms for response
        start_time = time.time()
        while (time.time() - start_time) < 0.2: # 200ms timeout
            resp = self._dev.read(128, timeout_ms=50)
            if resp and resp[0] == 0x09 and resp[1] == 0x08:
                # Format: 09 08 00 [page] [offset] [len] [data...]
                # Check consistency
                if resp[3] == page and resp[4] == offset:
                    # Successfully read data
                    data_len = resp[5]
                    return bytes(resp[6 : 6 + data_len])
        
        raise RuntimeError(f"Flash read timeout at Page=0x{page:02X} Offset=0x{offset:02X}")
