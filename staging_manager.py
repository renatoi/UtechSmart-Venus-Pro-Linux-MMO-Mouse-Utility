from copy import deepcopy

class StagingManager:
    """
    Manages the staging of button assignment changes.
    Separates the 'committed' state (on device) from the 'staged' state (in UI).
    Supports undo/redo for staged changes.
    """
    MAX_HISTORY = 50  # Cap history to limit memory
    
    def __init__(self):
        self.base_state = {}
        self.staged_state = {}
        self._history = []  # Stack of previous staged_state snapshots
        self._redo_stack = []  # Stack for redo

    def load_base_state(self, state: dict):
        """
        Load the authoritative state from the device/application.
        Clears any existing staged changes and history.
        """
        self.base_state = deepcopy(state)
        self.staged_state = {}
        self._history = []
        self._redo_stack = []

    def stage_change(self, key: str, action: str, params: dict):
        """
        Stage a change for a specific button key.
        Pushes current state to history for undo.
        """
        # Save current state for undo
        self._history.append(deepcopy(self.staged_state))
        if len(self._history) > self.MAX_HISTORY:
            self._history.pop(0)
        # Clear redo stack (branching invalidates redo)
        self._redo_stack = []
        # Apply the change
        self.staged_state[key] = {"action": action, "params": params}

    def undo(self) -> bool:
        """
        Undo the last staging operation.
        Returns True if an undo was performed.
        """
        if not self._history:
            return False
        # Push current state to redo stack
        self._redo_stack.append(deepcopy(self.staged_state))
        # Restore previous state
        self.staged_state = self._history.pop()
        return True

    def redo(self) -> bool:
        """
        Redo the last undone staging operation.
        Returns True if a redo was performed.
        """
        if not self._redo_stack:
            return False
        # Push current state to history
        self._history.append(deepcopy(self.staged_state))
        # Restore redo state
        self.staged_state = self._redo_stack.pop()
        return True

    def can_undo(self) -> bool:
        """Return True if undo is available."""
        return len(self._history) > 0

    def can_redo(self) -> bool:
        """Return True if redo is available."""
        return len(self._redo_stack) > 0

    def get_effective_state(self, key: str) -> dict | None:
        """
        Get the state of a key, preferring staged over base.
        """
        if key in self.staged_state:
            return self.staged_state[key]
        return self.base_state.get(key)

    def get_all_effective_state(self) -> dict:
        """
        Return the complete state map with staged changes applied.
        """
        state = deepcopy(self.base_state)
        state.update(self.staged_state)
        return state

    def clear_stage(self):
        """Discard all staged changes. Clears history."""
        self._history.append(deepcopy(self.staged_state))
        self._redo_stack = []
        self.staged_state = {}

    def commit(self):
        """
        Apply staged changes to base state.
        Call this after successful device sync.
        Clears undo/redo history.
        """
        self.base_state.update(self.staged_state)
        self.staged_state = {}
        self._history = []
        self._redo_stack = []

    def get_staged_changes(self) -> dict:
        """Return dictionary of only the staged items."""
        return self.staged_state

    def has_changes(self) -> bool:
        """Return True if there are pending changes."""
        return len(self.staged_state) > 0
