import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from PyQt6 import QtWidgets, QtCore, QtGui, QtTest

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
        vp.BUTTON_PROFILES = {
            "Side 1": MagicMock(label="Side 1", code_hi=0, code_lo=0, apply_offset=0),
            "Side 2": MagicMock(label="Side 2", code_hi=0, code_lo=0, apply_offset=0)
        }
        
        self.window = MainWindow()

    def tearDown(self):
        self.patcher1.stop()
        self.window.close()

    def test_stage_change_visuals(self):
        """Verify that applying a binding updates the table with a visual cue."""
        self.window.btn_table.selectRow(0)
        self.window.action_select.setCurrentText("Left Click")
        
        # Click Apply Binding (Should stage)
        QtTest.QTest.mouseClick(self.window.apply_button, QtCore.Qt.MouseButton.LeftButton)
        
        # Verify visual cue (orange text or *)
        item = self.window.btn_table.item(0, 1)
        self.assertIn("*", item.text())
        # Check color match
        expected_color = QtGui.QColor("orange")
        self.assertEqual(item.foreground().color(), expected_color)

    def test_sync_not_called_on_stage(self):
        """Verify that _sync_all_buttons is NOT called when staging."""
        self.window.btn_table.selectRow(0)
        self.window.action_select.setCurrentText("Disabled")
        
        # Mock _sync_all_buttons
        with patch.object(self.window, '_sync_all_buttons') as mock_sync:
            QtTest.QTest.mouseClick(self.window.apply_button, QtCore.Qt.MouseButton.LeftButton)
            mock_sync.assert_not_called()

if __name__ == '__main__':
    unittest.main()
