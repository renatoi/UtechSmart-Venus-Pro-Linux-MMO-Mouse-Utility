import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from staging_manager import StagingManager

class TestStagingManager(unittest.TestCase):
    def setUp(self):
        self.manager = StagingManager()
        self.initial_state = {
            "btn_1": {"action": "Left Click", "params": {}},
            "btn_2": {"action": "Right Click", "params": {}},
        }
        self.manager.load_base_state(self.initial_state)

    def test_load_base_state(self):
        """Test that base state is loaded correctly and clears stage."""
        self.manager.stage_change("btn_1", "Macro", {})
        self.manager.load_base_state(self.initial_state)
        self.assertFalse(self.manager.has_changes())
        self.assertEqual(self.manager.get_effective_state("btn_1")["action"], "Left Click")

    def test_stage_change(self):
        """Test staging a change updates the effective state but not base."""
        self.manager.stage_change("btn_1", "Macro", {"index": 1})
        
        # Effective state should show Macro
        effective = self.manager.get_effective_state("btn_1")
        self.assertEqual(effective["action"], "Macro")
        self.assertEqual(effective["params"]["index"], 1)
        
        # Staged changes should contain the update
        changes = self.manager.get_staged_changes()
        self.assertIn("btn_1", changes)
        
        # Original state should remain untouched (internal check)
        self.assertEqual(self.manager.base_state["btn_1"]["action"], "Left Click")

    def test_clear_stage(self):
        """Test clearing staged changes reverts to base state."""
        self.manager.stage_change("btn_1", "Macro", {})
        self.manager.clear_stage()
        
        self.assertFalse(self.manager.has_changes())
        self.assertEqual(self.manager.get_effective_state("btn_1")["action"], "Left Click")

    def test_commit(self):
        """Test committing promotes staged changes to base state."""
        self.manager.stage_change("btn_1", "Macro", {})
        self.manager.commit()
        
        self.assertFalse(self.manager.has_changes())
        self.assertEqual(self.manager.base_state["btn_1"]["action"], "Macro")

    def test_get_all_effective_state(self):
        """Test retrieving the full merged state."""
        self.manager.stage_change("btn_1", "Macro", {})
        full_state = self.manager.get_all_effective_state()
        
        self.assertEqual(full_state["btn_1"]["action"], "Macro")
        self.assertEqual(full_state["btn_2"]["action"], "Right Click")

if __name__ == '__main__':
    unittest.main()
