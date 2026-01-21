import time
from array import array
from logger import safe_log

from ola.ClientWrapper import ClientWrapper


class SimpleDMXClient:
    def __init__(self, universe=1):
        self.wrapper = ClientWrapper()
        self.client = self.wrapper.Client()
        self.universe = universe
        self._last_frame = None

    def _to_array(self, values):
        """
        Convert many possible input types into array('B', ...),
        which supports .tobytes() required by OLA.
        Accepts: array('B'), list of ints, bytes, bytearray, memoryview.
        """
        if isinstance(values, array):
            return values
        if isinstance(values, (bytes, bytearray)):
            return array('B', values)
        if isinstance(values, memoryview):
            return array('B', values.tobytes())
        # assume iterable of ints
        return array('B', values)

    def send_dmx(self, values):
        data = self._to_array(values)

        # Skip duplicate frames 
        if self._last_frame == data:
            return

        start = time.monotonic()
        # optional callback can be provided as 3rd arg if desired
        # safe_log(f"sending {data} to DMX")
        self.client.SendDmx(self.universe, data)
        elapsed = time.monotonic() - start
        if elapsed > 1.0:
            safe_log(
                f"WARNING: SendDmx blocked for {elapsed:.2f}s"
            )

        # Only update last-frame *after* successful send
        self._last_frame = data
