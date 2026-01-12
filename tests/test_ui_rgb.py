import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from PyQt6 import QtWidgets, QtCore, QtGui, QtTest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock venus_protocol
sys.modules['venus_protocol'] = MagicMock()
import venus_protocol as vp
vp.RGB_PRESETS = {"Red": b'\x01'}
vp.RGB_MODE_STEADY = 0x01
vp.BUTTON_PROFILES = {}
vp.HID_KEY_USAGE = {}
vp.MEDIA_KEY_CODES = {}
vp.POLLING_RATE_PAYLOADS = {}
vp.DPI_PRESETS = {}
vp.PYUSB_AVAILABLE = False

from venus_gui import MainWindow

class TestUIRGB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication(sys.argv)

    def setUp(self):
        with patch('venus_gui.MainWindow._refresh_and_connect'):
            self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_rgb_tab_initial_state(self):
        """Verify RGB tab has the expected widgets."""
        # Find RGB tab (index 2 usually, check build_tabs)
        # Tabs: Buttons(0), Macros(1), RGB(2)
        rgb_tab = self.window.findChild(QtWidgets.QTabWidget).widget(2)
        self.assertIsNotNone(rgb_tab)
        
        # Check for Pick Color button
        self.assertIsNotNone(self.window.rgb_color_button)
        
    def test_color_picker_updates_state(self):
        """Verify that picking a color updates rgb_current_color."""
        # We need to mock QColorDialog.getColor to return a specific color
        new_color = QtGui.QColor(0, 255, 0)
        with patch('PyQt6.QtWidgets.QColorDialog.getColor', return_value=new_color):
            QtTest.QTest.mouseClick(self.window.rgb_color_button, QtCore.Qt.MouseButton.LeftButton)
            
        self.assertEqual(self.window.rgb_current_color, new_color)

if __name__ == '__main__':
    unittest.main()
