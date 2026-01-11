# UtechSmart Venus Pro Protocol Findings & Theories

## Executive Summary
We have successfully reverse-engineered the Communication, Unlock, and Write mechanisms. The current roadblock is the **Macro Event Execution Format**—the device accepts our data (writes persist), but does not execute the events (types nothing). This suggests a mismatch in the *Event Structure* or *Event Count* logic.

## 1. The "Magic Unlock" Mechanism
**Theory:** The device requires a specific handshake sequence on **Interface 1** (Config Interface) to enable flash write operations. This state is volatile and tied to the USB session.

**Evidence:**
*   **Capture Source:** `wired - open utility - all communication automatic.pcapng`
*   **Packet Analysis:**
    *   **Reset:** `Cmd 09` sent to Interface 1.
    *   **Magic 1:** `Cmd 4D` sent immediately after reset. Payload: `08 4D 05 50 00 55...`
    *   **Magic 2:** `Cmd 01` sent after 4D. Payload: `08 01 00 00 00 04...`
*   **Validation:**
    *   Sending write commands *without* this sequence (on Interface 0) results in no response.
    *   Sending this sequence *and keeping the connection open* (via `VenusDevice.unlock()`) allows subsequent Write commands (`Cmd 07`) to be accepted by the firmware.

## 2. The Write Protocol (Interface 1)
**Theory:** Configuration writes MUST be directed to **Interface 1** (HID Interface 1), not Interface 0 (Generic Mouse). The format involves a specific Report ID and Command Byte.

**Evidence:**
*   **Capture Source:** `create new macro...pcapng` (Frames 2930-2940).
*   **Packet Analysis:**
    *   **Setup Packet:** `21 09 08 03 01 00...`
        *   `21 09`: Set Report (Class Interface).
        *   `08 03`: `wValue` = Report Type Feature (03) + Report ID (08).
        *   `01 00`: `wIndex` = **Interface 1**.
    *   **Payload:** `08 07 00 03 ...`
        *   Byte 0: `08` (Report ID).
        *   Byte 1: `07` (Command ID - Write Flash).
*   **Validation:**
    *   Initial tests targeting Interface 0 failed (writes didn't stick).
    *   Tests targeting Interface 1 (confirmed by `test_macro_verify.py` logs) resulted in persistent data changes in flash.

## 3. Macro Memory Layout
**Theory:** Macros are stored in 256-byte slots starting at Page 0x03. The header structure is strictly defined.

**Evidence:**
*   **Dump Source:** `dumps/Good_Config_Windows.bin` (Offsets 0x300, 0x400...)
*   **Capture Source:** `create new macro...pcapng` (Frame 2931 Payload).
*   **Structure Pattern:**
    *   Capture Payload start: `00 0a 0e 74 ...`
    *   Dump Slot 9 (`testing`): `08 74 00 65 ...` (Wait, Dump slot 9 starts with 08?)
    *   Dump Slot 0 (`123`): `06 31 00 32 ...`
    *   **Resolved Structure:**
        *   `Byte 0`: **Unknown Const** (Capture `00`, Dump `06`/`08`). Likely Flags or Type.
        *   `Byte 1`: **Unknown Const** (Capture `0a`).
        *   `Byte 2`: **Name Length** (in bytes). Capture `0e` (14 bytes for "testing"), Dump `06` (6 bytes for "123").
        *   `Byte 3..`: **Name (UTF-16LE)**.
        *   `Offset 0x1F` (31): **Event Count** (Logical or Byte Count).

## 4. The Checksum Logic
**Theory:** The macro data end is marked by a Terminator `03 [Checksum] 00`. This checksum MUST be correct for the firmware to accept the macro.

**Evidence:**
*   **Failed Writes:** Initial writes with `0x55 - Sum` persisted but were likely marked "invalid" by firmware (execution failed).
*   **Algorithm Reversal:**
    *   The `Good_Config_Windows.bin` file was vital.
    *   Formula: `Checksum = (~Sum_of_Data - Count_Byte + Correction) & 0xFF`.
    *   `Correction`: Seems to be `(Index + 1)^2` or simply `1` for Slot 1.
*   **Validation:**
    *   `verify_dump_checksum.py` confirmed this formula matches valid dumps.
    *   Writes using this formula are consistently accepted.

## 5. The Current Puzzle: Event Structure (3-byte vs 5-byte)
**Problem:** We wrote the macro, but "types nothing". This means the firmware parses `0` events or invalid events.

**Theory A: 3-Byte Logical, 5-Byte Physical**
*   **Evidence:**
    *   Dump Slot 0 ("123") has 6 actions (Press 1, Rel 1, Press 2...).
    *   Offset `0x1F` (Count) is `0x12` (18).
    *   **Math:** 18 / 6 = **3 bytes per event**.
*   **Contradiction:**
    *   The raw dump data shows pattern `81 1E 00 00 7D` (5 bytes!).
    *   If logical is 3, why is physical 5?
    *   Maybe the Count `18` refers to *Logical Bytes* (3 * 6), but firmware *reads* 5-byte chunks?

**Theory B: Checksum per Event**
*   **Evidence:** The 5th byte in the dump `7D` looks random/calculated.
*   `81 1E 00 00` -> `81+1E = 9F`. `100 - 9F = 61`. `55 - 9F = B6`. `(~9F) = 60`.
*   Checksum `7D`.
*   If we don't get this per-event checksum right, the event is invalid -> "Types nothing".

**Test Plan (In Progress):**
1.  We just updated `test_macro_verify.py` to use **exact 5-byte events copied from the dump**.
2.  If this works (types "1"), it proves the Physical 5-Byte structure requirement.
