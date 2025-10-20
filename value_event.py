import threading

"""
Extend the standard Threading Event to add a value to be passed between threads
"""

class ValueEvent(threading.Event):
    """An Event that carries a value."""
    def __init__(self):
        super().__init__()
        self._value = None
        self._lock = threading.Lock()

    def set_value(self, value):
        with self._lock:
            self._value = value
            self.set()

    def get_value(self):
        self.wait()
        with self._lock:
            return self._value

    def clear(self):
        with self._lock:
            self._value = None
        super().clear()
