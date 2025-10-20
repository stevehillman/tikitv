from typing import Dict
from logger import safe_log

class PlaylistRunner:
    def __init__(self, playlist: Dict, command_handler):
        """
        playlist: a dict from ConfigLoader, with keys:
          - "name": str
          - "triggers": list of { "offset": int, "command": str }
        command_handler: callable that executes commands (e.g. function or object)
        """
        self.playlist = playlist
        self.command_handler = command_handler
        self.fired_triggers = set()  # keep track of offsets we've already handled
        self.last_offset_seen = 0

    def check_and_run(self, current_offset: int):
        """
        Check if any triggers should fire at this offset.
        Run them if not yet fired.
        """
        if current_offset < self.last_offset_seen:
            # Clear the list of fired triggers if we've gone back in time
            self.fired_triggers = set()
        self.last_offset_seen = current_offset
        for trigger in self.playlist.get("triggers", []):
            offset = trigger["offset"]
            command = trigger["command"]

            # Fire if current time >= offset, and not already fired
            if current_offset >= offset and current_offset < offset+5 and offset not in self.fired_triggers:
                safe_log(f"Firing trigger at offset {offset}: {command}")
                try:
                    self.command_handler(command)
                except Exception as e:
                    safe_log(f"Error executing command '{command}': {e}")
                self.fired_triggers.add(offset)
