import sys
import os
import time
import hid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import venus_protocol as vp

def main():
    print("--- Test Fix Init Script ---")
    
    # 1. Unlock (Aggressive)
    if vp.PYUSB_AVAILABLE:
        print("1. Unlocking device (PyUSB)...")
        try:
            vp.unlock_device()
            print("   Unlock command sent.")
        except Exception as e:
            print(f"   Unlock failed: {e}")
    else:
        print("1. PyUSB not available, skipping unlock.")

    # PROPOSED FIX: Wait for device to settle after driver detach/reattach
    print("   Waiting 2 seconds for device settle...")
    time.sleep(2.0)

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
        
        # 4. Read Settings with Retries
        print("4. Attempting Read Settings Sequence with Retries...")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"   Attempt {attempt+1}/{max_retries}...")
                
                # Re-open logic matches GUI
                if device:
                    try:
                        device.close()
                    except:
                        pass
                
                time.sleep(0.1)
                device = vp.VenusDevice(target_info.path)
                device.open()
                
                # Handshake Sequence: 04 then 03
                device.send(vp.build_simple(0x04))
                time.sleep(0.05)
                device.send(vp.build_simple(0x03))
                
                # Small delay after handshake before read?
                time.sleep(0.1)
                
                # Read Page 0
                chunk = device.read_flash(0, 0, 8)
                print(f"   Success! Data: {chunk.hex()}")
                break
            except Exception as e:
                print(f"   Attempt {attempt+1} failed: {e}")
                time.sleep(0.5)
            
    except Exception as e:
        print(f"   Open/Comm Error: {e}")
    finally:
        if device:
            device.close()
            print("   Device closed.")

if __name__ == "__main__":
    main()
