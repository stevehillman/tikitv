class Scene:
    def __init__(self, name: str, values: dict, fixture_defs: list, fixtures: dict):
        """
        name: scene name
        values: base values shared by all fixtures (e.g. {"dimmer":255,"red":128})
        fixture_defs: list of {"name":<fixture_name>, "overrides":{...}} dictionaries
        fixtures: dictionary of Fixture objects by name
        """
        self.name = name
        self.scene_values = values
        self.fixture_defs = fixture_defs
        self.fixtures_by_name = fixtures

        # Final flattened DMX channel map: {channel_number: value}
        self.values = self._calculate_final_channels()

    def _calculate_final_channels(self):
        dmx_map = {}

        for fixture_entry in self.fixture_defs:
            fixture_name = fixture_entry["name"]
            fixture = self.fixtures_by_name.get(fixture_name)
            if not fixture:
                raise ValueError(f"Scene '{self.name}' references unknown fixture '{fixture_name}'")

            overrides = fixture_entry.get("overrides", {})

            # Merge base values + overrides
            merged_values = self.scene_values.copy()
            merged_values.update(overrides)

            # Convert channel names to DMX channel numbers
            for ch_name, value in merged_values.items():
                ch_num = fixture.get_channel_number(ch_name)
                if ch_num is not None:
                    dmx_map[ch_num-1] = value
                else:
                    # It's ok if a fixture doesn't have that channel
                    pass

        return dmx_map
