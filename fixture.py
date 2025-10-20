class Fixture:
    def __init__(self, name: str, address: int, num_channels: int, assignments: dict):
        self.name = name                    # name of the fixture
        self.address = address              # Starting DMX address
        self.num_channels = num_channels    # total number of channels
        self.assignments = assignments      # Dictionary of channel name to number assignments (e.g. {"red": 1})

        # Map logical channel names to absolute DMX channel numbers
        self.absolute_channels = {
            name: address + offset for name, offset in assignments.items()
        }

    def get_channel_number(self, channel_name: str):
        return self.absolute_channels.get(channel_name)
