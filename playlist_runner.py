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
        self._last_offset = 0.0
        for trigger in self.playlist["triggers"]:
            trigger["executed"] = False

    def check_and_run(self, current_offset):
        if not self.playlist:
            return

        now = float(current_offset)

        # If playback jumped backwards, reset trigger state
        if now < self._last_offset:
            for trigger in self.playlist["triggers"]:
                trigger["executed"] = False
        self._last_offset = now

        # All triggers not yet executed whose time has passed
        eligible = [
            t for t in self.playlist.get("triggers",[])
            if not t.get("executed") and t["offset"] <= now
        ]

        if not eligible:
            return

        # Prefer triggers within the last 5 seconds
        recent = [t for t in eligible if now - t["offset"] <= 5]

        if recent:
            # Pick the most recent of the recent ones
            trigger_to_run = max(recent, key=lambda t: t["offset"])
        else:
            # Otherwise pick the most recent past trigger
            trigger_to_run = max(eligible, key=lambda t: t["offset"])

        # Execute all commands in that trigger
        for cmd in trigger_to_run["commands"]:
            safe_log(f"Firing trigger at offset {now}: {cmd}")
            self.command_handler(cmd)

        # Mark ALL triggers up to and including this one as executed
        for t in self.playlist.get("triggers",[]):
            if t["offset"] <= trigger_to_run["offset"]:
                t["executed"] = True

