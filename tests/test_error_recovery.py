import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transaction_controller import TransactionController
from staging_manager import StagingManager

class TestErrorRecovery(unittest.TestCase):
    def setUp(self):
        self.mock_device = MagicMock()
        self.mock_protocol = MagicMock()
        self.staging = StagingManager()
        
        # Setup initial state
        self.staging.load_base_state({
            "btn_1": {"action": "Left Click", "params": {}},
            "btn_2": {"action": "Right Click", "params": {}},
        })
        
        self.controller = TransactionController(self.mock_device, self.mock_protocol)

    def test_interrupted_transaction_preserves_staging(self):
        """Verify that if a transaction fails mid-way, staging is preserved."""
        # Stage two changes
        self.staging.stage_change("btn_1", "Macro", {"index": 1})
        self.staging.stage_change("btn_2", "Middle Click", {})
        
        # Mock protocol to return packets
        self.mock_protocol.build_packets.return_value = [b'\x01']
        
        # Mock device to succeed on first packet, fail on second
        # We need to simulate failure based on inputs or sequence
        # TransactionController sends packets sequentially.
        # Let's say btn_1 generates 1 packet, btn_2 generates 1 packet.
        # Total 2 packets.
        
        # Side effect for send_reliable: True, then False
        self.mock_device.send_reliable.side_effect = [True, False]
        
        success = self.controller.execute_transaction(self.staging)
        
        # Transaction should fail
        self.assertFalse(success)
        
        # Staging should still have changes (not committed)
        self.assertTrue(self.staging.has_changes())
        
        # Verify specific changes still exist
        staged = self.staging.get_staged_changes()
        self.assertIn("btn_1", staged)
        self.assertIn("btn_2", staged)

    def test_build_error_aborts_transaction(self):
        """Verify that if packet building fails, no packets are sent and staging is preserved."""
        self.staging.stage_change("btn_1", "Invalid", {})
        
        # Mock protocol to raise exception
        self.mock_protocol.build_packets.side_effect = ValueError("Invalid action")
        
        success = self.controller.execute_transaction(self.staging)
        
        self.assertFalse(success)
        self.mock_device.send_reliable.assert_not_called()
        self.assertTrue(self.staging.has_changes())

if __name__ == '__main__':
    unittest.main()
