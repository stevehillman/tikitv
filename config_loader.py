"""
config_loader.py

Loads lighting sequences and playlists from a JSON configuration file.
Each sequence is built into a Sequence object and stored by name.
"""

import json
from sequence import Sequence  # assumes Sequence class is defined in sequence.py
from scene import Scene
from fixture import Fixture

class ConfigLoader:
    """
    Loads Sequences and Playlists from a JSON configuration file.
    Stores:
      - self.sequences: dict[name -> Sequence]
      - self.playlists: dict[name -> playlist dict]
    """

    def __init__(self, filepath):
        self.filepath = filepath
        self.fixtures = {}
        self.scenes = {}
        self.sequences = {}
        self.playlists = {}
        self.mqtt_config = {}
        self._load_config()

    def _load_config(self):
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
            triggers = pl_data.get("triggers", [])
            self.playlists[name] = {
                "name": name,
                "triggers": triggers
            }

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
