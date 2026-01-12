import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from PyQt6 import QtWidgets, QtCore, QtTest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock venus_protocol before importing venus_gui
sys.modules['venus_protocol'] = MagicMock()
import venus_protocol as vp
vp.BUTTON_PROFILES = {} # Needs to be a dict
vp.HID_KEY_USAGE = {}
vp.MEDIA_KEY_CODES = {}
vp.RGB_PRESETS = {}
vp.POLLING_RATE_PAYLOADS = {}
vp.DPI_PRESETS = {}
vp.PYUSB_AVAILABLE = False # Prevent unlock attempt

from venus_gui import MainWindow

class TestUIStaged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create the QApplication instance once for the class
        # Use offscreen platform for headless testing
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication(sys.argv)

    def setUp(self):
        # Patch the methods that interact with hardware
        self.patcher1 = patch('venus_gui.MainWindow._refresh_and_connect')
        self.mock_refresh = self.patcher1.start()
        
        # We need to populate some mock data for BUTTON_PROFILES to verify the table
        # Format seems to be "Side 1", "Button 4", etc. based on split()[1] usage
        vp.BUTTON_PROFILES = {
            "Side 1": MagicMock(label="Side 1", code_hi=0, code_lo=0, apply_offset=0),
            "Side 2": MagicMock(label="Side 2", code_hi=0, code_lo=0, apply_offset=0)
        }
        
        self.window = MainWindow()

    def tearDown(self):
        self.patcher1.stop()
        self.window.close()

    def test_apply_button_initially_enabled(self):
        """
        Verify the apply button starts as enabled in the current legacy logic.
        (Note: The goal of this track is to change this, but first we verify baseline)
        """
        # Select a row to enable the right panel
        self.window.btn_table.selectRow(0)
        self.assertTrue(self.window.apply_button.isEnabled())

    def test_apply_button_behavior(self):
        """Verify we can click the button."""
        self.window.btn_table.selectRow(0)
        self.window.action_select.setCurrentText("Disabled")
        
        # Mock _sync_all_buttons to avoid real sync
        with patch.object(self.window, '_sync_all_buttons') as mock_sync:
            QtTest.QTest.mouseClick(self.window.apply_button, QtCore.Qt.MouseButton.LeftButton)
            mock_sync.assert_called_once()

if __name__ == '__main__':
    unittest.main()
