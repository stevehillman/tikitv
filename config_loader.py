"""
config_loader.py

Loads lighting sequences and playlists from a JSON configuration file.
Each sequence is built into a Sequence object and stored by name.
"""

import json
import os
import threading
import time
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

                self.playlists[name] = {
                    "name": name,
                    "triggers": processed_triggers
                }

            self._last_modified = os.path.getmtime(self.filepath)
            safe_log(f"[ConfigLoader] Configuration loaded from {self.filepath}")

        except Exception as e:
            safe_log(f"[ConfigLoader] Error loading configuration: {e}")

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
