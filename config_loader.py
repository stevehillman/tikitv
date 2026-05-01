"""
config_loader.py

Loads lighting sequences and playlists from a JSON configuration file.
Each sequence is built into a Sequence object and stored by name.
"""

import json
import os
import threading
import time
import re
from typing import Any
from sequence import Sequence
from scene import Scene
from fixture import Fixture
from logger import safe_log,logging

class ConfigLoader:
    """
    Singleton class to load config for fixtures, scenes, sequences, and playlists
    from a JSON file. MQTT and VLC config are also loaded

    Automatically reloads if the file changes on disk.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, filepath: str | None = None):
        with cls._lock:
            if cls._instance is None:
                if filepath is None:
                    raise ValueError(
                        "ConfigLoader must be initialized with a file path the first time."
                    )
                cls._instance = super(ConfigLoader, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, filepath: str | None = None):
        if self._initialized:
            return  # already initialized

        if filepath is None:
            raise ValueError(
                "ConfigLoader must be initialized with a file path the first time."
            )

        self.filepath = filepath
        self._last_modified = None
        self._reload_interval = 2.0  # seconds between modification checks

        self.fixtures = {}
        self.scenes = {}
        self.sequences = {}
        self.playlists = {}
        self.mqtt_config = {}
        self._subscribers = []  # list of callback functions
        self.current_playlist = None
        self._load_config()

        # Start background watcher thread
        self._watcher_thread = threading.Thread(
            target=self._watch_config_changes, daemon=True
        )
        self._watcher_thread.start()

        self._initialized = True

    def _load_config(self):
        try:
            with open(self.filepath, 'r') as f:
                config = json.load(f)

            # Load non-fading channels
            self.non_fading_channels = set(config.get("non_fading_channels", []))

            # MQTT setup
            self.mqtt_config = config.get("mqtt", {})

            # Load Fixtures
            for fix in config.get("fixtures", []):
                fixture = Fixture(
                    name=fix["name"],
                    address=fix["address"],
                    num_channels=fix["channels"],
                    assignments=fix["assignments"]
                )
                self.fixtures[fixture.name] = fixture

            # --- Load Scenes ---
            for sc in config.get("scenes", []):
                scene = Scene(
                    name=sc["name"],
                    values=sc.get("values", {}),
                    fixture_defs=sc.get("fixtures", []),
                    fixtures=self.fixtures
                )
                self.scenes[scene.name] = scene

            # Load Sequences
            for seq_data in config.get("sequences", []):
                name = seq_data["name"]
                loop = seq_data.get("loop", False)
                sequence = Sequence(name, loop=loop)
                for step in seq_data.get("scenes", []):
                    sequence.add_step(step["scene"], step["duration"], step["transition"])
                self.sequences[name] = sequence

            # Load Playlists
            for pl_data in config.get("playlists", []):
                name = pl_data["name"]
                raw_triggers = pl_data.get("triggers", [])

                processed_triggers = []

                for t in raw_triggers:
                    offset = float(t["offset"])

                    # Normalize commands → always a list
                    cmd = t.get("command")
                    if isinstance(cmd, list):
                        commands = cmd
                    else:
                        commands = [cmd]

                    processed_triggers.append({
                        "offset": offset,
                        "commands": commands,
                        "executed": False
                    })

                # Sort once at load time (important!)
                processed_triggers.sort(key=lambda x: x["offset"])

                # Load and normalize playlist tags (named offsets)
                tags = self._normalize_tags(pl_data.get("tags", {}), name)

                self.playlists[name] = {
                    "name": name,
                    "triggers": processed_triggers,
                    "tags": tags
                }

            self._last_modified = os.path.getmtime(self.filepath)
            safe_log(f"[ConfigLoader] Configuration loaded from {self.filepath}")

        except Exception as e:
            safe_log(f"[ConfigLoader] Error loading configuration: {e}")

    def _normalize_tags(self, raw_tags: dict, playlist_name: str):
        """
        Normalize playlist tags.

        - Lowercase keys
        - Validate numeric offsets
        - Ensure offset >= 0
        """

        if not isinstance(raw_tags, dict):
            raise ValueError(f"Playlist '{playlist_name}' tags must be a dictionary")

        normalized = {}

        for tag_name, offset in raw_tags.items():

            if not isinstance(tag_name, str):
                raise ValueError(f"Playlist '{playlist_name}' tag names must be strings")

            key = tag_name.strip().lower()

            try:
                offset_val = int(offset)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Playlist '{playlist_name}' tag '{tag_name}' offset must be numeric"
                )

            if offset_val < 0:
                raise ValueError(
                    f"Playlist '{playlist_name}' tag '{tag_name}' offset must be >= 0"
                )

            normalized[key] = offset_val

        return normalized

    def _watch_config_changes(self):
        """Monitor file modification time and reload if it changes."""
        while True:
            try:
                current_mtime = os.path.getmtime(self.filepath)
                if self._last_modified and current_mtime > self._last_modified:
                    safe_log("[ConfigLoader] Detected configuration change, reloading...")
                    self._load_config()
                    for callback in self._subscribers:
                        try:
                            callback(self)
                        except Exception as e:
                            safe_log(f"ConfigLoader subscriber error: {e}", logging.ERROR)
            except FileNotFoundError:
                safe_log(f"[ConfigLoader] Warning: Config file {self.filepath} not found.")
            except Exception as e:
                safe_log(f"[ConfigLoader] Error watching config: {e}")
            time.sleep(self._reload_interval)

    def subscribe(self, callback):
        """Register a function to be called when config reloads."""
        if callable(callback):
            self._subscribers.append(callback)

    def get_scene(self, name):
        return self.scenes.get(name)

    def get_sequence(self, name):
        """Return a Sequence object by name."""
        return self.sequences.get(name)
    
    def get_sequence_names(self):
        return self.sequences.keys()

    def get_playlist(self, name):
        """Return a playlist dict by name."""
        return self.playlists.get(name)
    
    def get_non_fading_channels(self):
        return self.non_fading_channels
    
    def get_mqtt_config(self):
        return self.mqtt_config
    
    def set_current_playlist(self,name):
        self.current_playlist = name

    def resolve_tag(self, tag_or_offset) -> int:
        """
        Resolve:
        - float
        - tag
        - tag+offset
        - tag-offset
        """

        # Direct numeric?
        try:
            return int(tag_or_offset)
        except (TypeError, ValueError):
            if self.current_playlist is None:
                raise ValueError("Current playlist is not set. Can not use named tags")
            pass

        if not isinstance(tag_or_offset, str):
            raise ValueError("Seek target must be a number or tag string")

        expr = tag_or_offset.strip().lower()

        # Match: tag(+|-)number
        match = re.match(r'^([a-z0-9_\-]+)([+-]\d+(\.\d+)?)?$', expr)
        if not match:
            raise ValueError(f"Invalid seek expression '{tag_or_offset}'")

        tag_key = match.group(1)
        delta_str = match.group(2)

        playlist = self.playlists.get(self.current_playlist)
        if not playlist:
            raise ValueError(f"Unknown playlist '{self.current_playlist}'")

        tags = playlist.get("tags", {})
        if tag_key not in tags:
            raise ValueError(
                f"Tag '{tag_or_offset}' not found in playlist '{self.current_playlist}'"
            )

        base = tags[tag_key]

        delta = int(delta_str) if delta_str else 0

        final = base + delta

        if final < 0:
            final = 0

        return final
