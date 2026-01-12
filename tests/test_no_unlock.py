import sys
import os
import time
import hid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import venus_protocol as vp

def main():
    print("--- Test No Unlock Script ---")
    
    # 1. SKIP Unlock
    print("1. Skipping unlock.")

    # 2. List devices
    print("2. Listing devices (hidapi)...")
    devices = vp.list_devices()
    
    if not devices:
        print("   No devices found.")
        return
        
    target_info = devices[0]
    print(f"3. Opening device: {target_info.path}...")
    
    device = None
    try:
        device = vp.VenusDevice(target_info.path)
        device.open()
        print("   Device opened.")
        
        # 4. Read Settings
        print("4. Attempting Read Settings Sequence...")
        
        # Handshake
        print("   Sending Prepare (0x04)...")
        device.send(vp.build_simple(0x04))
        time.sleep(0.05)
        print("   Sending Handshake (0x03)...")
        device.send(vp.build_simple(0x03))
        
        # Read Loop manually to debug
        print("   Reading loop...")
        start = time.time()
        while time.time() - start < 2.0:
            resp = device._dev.read(128, timeout_ms=50)
            if resp:
                print(f"   Read: {bytes(resp).hex()}")
            else:
                pass
                # print("   Read: None")
        
        # Read Page 0 (This will probably fail if above consumed it)
        # chunk = device.read_flash(0, 0, 8)
        # print(f"   Success! Data: {chunk.hex()}")
            
    except Exception as e:
        print(f"   Open/Comm Error: {e}")
    finally:
        if device:
            device.close()
            print("   Device closed.")

if __name__ == "__main__":
    main()
