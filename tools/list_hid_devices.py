import hid
import sys

VENDOR_ID = 0x25A7

def list_all():
    print("Enumerating all HID devices...")
    for d in hid.enumerate():
        if d['vendor_id'] == VENDOR_ID:
            print(f"FOUND 25A7: {d['product_string']} (PID {d['product_id']:04X})")
            print(f"  Path: {d['path']}")
            print(f"  Interface: {d['interface_number']}")
            print("-" * 20)

if __name__ == "__main__":
    list_all()
