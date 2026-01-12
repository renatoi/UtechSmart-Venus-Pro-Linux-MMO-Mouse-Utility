# Technology Stack - Venus Pro Config (Linux)

## Core Technologies
*   **Python (3.8+):** The primary programming language, chosen for its rapid development capabilities and extensive library support.
*   **PyQt6:** The graphical user interface framework, selected for its ability to create robust, native-feeling desktop applications on Linux.
*   **hidapi:** The cross-platform library used for low-level USB HID (Human Interface Device) communication with the mouse hardware.

## Tooling & Infrastructure
*   **Cython:** Utilized to provide efficient Python bindings for the `hidapi` C library, ensuring high-performance hardware interaction.
*   **PKGBUILD:** Integration with the Arch Linux Build System (makepkg) for streamlined packaging and distribution to Linux users.
*   **Git:** Version control system for managing the project's source code and collaborative development history.
