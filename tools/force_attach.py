import usb.core
import usb.util
import sys

VENDOR_ID = 0x25A7
PRODUCT_ID_MOUSE = 0xFA08

def force_attach():
    print(f"Searching for Venus Pro Mouse ({VENDOR_ID:04X}:{PRODUCT_ID_MOUSE:04X})...")
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID_MOUSE)
    
    if dev is None:
        print("Mouse not found via PyUSB. Check USB connection.")
        return

    print("Mouse found.")
    for iface in [0, 1]:
        if dev.is_kernel_driver_active(iface):
            print(f"Interface {iface}: Kernel driver active.")
        else:
            print(f"Interface {iface}: Kernel driver DETACHED. Attempting to attach...")
            try:
                dev.attach_kernel_driver(iface)
                print(f"Interface {iface}: Attached successfully.")
            except Exception as e:
                print(f"Interface {iface}: Attach failed: {e}")

if __name__ == "__main__":
    force_attach()
