import sys
import os
import time
import hid
import usb.core
import usb.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import venus_protocol as vp

def modified_unlock_device():
    """
    Modified unlock that skips the 0x09 Reset command.
    """
    if not vp.PYUSB_AVAILABLE:
        print("PyUSB not available.")
        return False

    print("Attempting MODIFIED unlock (No Reset)...")
    dev = usb.core.find(idVendor=vp.VENDOR_ID, idProduct=vp.PRODUCT_IDS[1]) # FA08 Wireless
    if dev is None:
        dev = usb.core.find(idVendor=vp.VENDOR_ID, idProduct=vp.PRODUCT_IDS[0]) # FA07 Wired
    
    if dev is None:
        print("Unlock: No device found.")
        return False

    # Detach Kernel Driver
    reattach = []
    for iface in [0, 1]:
        if dev.is_kernel_driver_active(iface):
            try:
                dev.detach_kernel_driver(iface)
                reattach.append(iface)
                print(f"Detached kernel driver from iface {iface}")
            except Exception as e:
                print(f"Failed to detach iface {iface}: {e}")
                return False

    try:
        usb.util.claim_interface(dev, 1)
        
        # Helper to send feature report to Interface 1
        def send_magic(data):
            padded = data.ljust(17, b'\x00')
            dev.ctrl_transfer(0x21, 0x09, 0x0308, 1, padded)

        # 1. SKIP Reset (Cmd 09)
        # send_magic(bytes([0x08, 0x09]))
        # time.sleep(0.5)
        
        # 2. Magic packet 1 (CMD 4D)
        # 08 4D 05 50 00 55 00 55 00 55 91
        print("Sending Magic Packet 1 (0x4D)...")
        send_magic(bytes([0x08, 0x4D, 0x05, 0x50, 0x00, 0x55, 0x00, 0x55, 0x00, 0x55, 0x91]))
        time.sleep(0.05)
        
        # 3. Magic packet 2 (CMD 01)
        # 08 01 00 00 00 04 56 57 3d 1b 00 00
        print("Sending Magic Packet 2 (0x01)...")
        send_magic(bytes([0x08, 0x01, 0x00, 0x00, 0x00, 0x04, 0x56, 0x57, 0x3d, 0x1b, 0x00, 0x00]))
        time.sleep(0.05)
        
        print("Unlock sequence sent.")
        
    except Exception as e:
        print(f"Unlock error: {e}")
        return False
    finally:
        # Re-attach Check
        for iface in reattach:
            try:
                dev.attach_kernel_driver(iface)
                print(f"Re-attached kernel driver to iface {iface}")
            except:
                pass
        # Wait for device to re-enumerate after driver re-attach
        time.sleep(1.0)
    return True

def main():
    print("--- Test Fix No Reset Script ---")
    
    # 1. Run Modified Unlock
    if not modified_unlock_device():
        print("Modified unlock failed.")
        return

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
        device.send(vp.build_simple(0x03))
        
        # Read Page 0
        chunk = device.read_flash(0, 0, 8)
        print(f"   Success! Data: {chunk.hex()}")
            
    except Exception as e:
        print(f"   Open/Comm Error: {e}")
    finally:
        if device:
            device.close()
            print("   Device closed.")

if __name__ == "__main__":
    main()
