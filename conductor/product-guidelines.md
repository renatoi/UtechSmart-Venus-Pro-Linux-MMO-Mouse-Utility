# Product Guidelines - Venus Pro Config (Linux)

## Visual Design
*   **Native Integration:** Adhere to a clean, native Linux look and feel using standard PyQt6/Qt widgets. The UI should feel like a first-class citizen of the user's desktop environment (KDE/GNOME) rather than a separate "gaming skin."

## Interaction & UX
*   **Staged Batch Configuration:** Implement a non-blocking configuration workflow. Users must be able to stage multiple button rebinds or macro edits within the UI without immediate device writes. An explicit "Apply Changes" action will then push the entire batch to the device at once.
*   **Functional Polish:** Focus on high-density functionality without clutter. Refine the existing interface to minimize the number of clicks required for common remapping tasks.

## Safety & Protocol Integrity
*   **Atomic Transactions:** Configuration groups (such as a full profile update) should be treated as atomic operations. The implementation must ensure the device state is not left in a partial or corrupted state if a write is interrupted.
*   **Comprehensive Transaction Logging:** All outgoing HID packets and their corresponding device responses must be logged to a persistent session file. This is critical for data recovery and debugging protocol edge cases.

## Technical Transparency
*   **Persistent Expert Console:** Maintain and enhance the integrated real-time traffic view. Technical users should have immediate access to decoded protocol communication to verify hardware behavior and assist in further reverse engineering efforts.
