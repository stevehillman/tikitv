#!/usr/bin/env python3

import time

from simple_dmx_client import SimpleDMXClient
from dmx_engine import DMXEngine
from config_loader import ConfigLoader
from command_handler import CommandHandler
from playlist_runner import PlaylistRunner
from vlc_client import VLCClient
from logger import safe_log
from mqtt_client import MQTTClient
from vlc_launcher import VLCLauncher

def main():
    current_title = None
    mqtt_client = None

    # Load all config (sequences, playlists) from JSON
    config = ConfigLoader("config.json")

    # Initialize DMX client and engine
    client = SimpleDMXClient()
    engine = DMXEngine(config, client)

    vlc_launcher = VLCLauncher(4212,"tikitv")
    vlc_launcher.ensure_running()
    vlc = VLCClient("10.0.8.111", 4212, "tikitv")

    handler = CommandHandler(engine, config, vlc)
    mqtt_client = MQTTClient(config, handler)

    runner = None

    while True:
        mqtt_client.process_pending_commands()
        if vlc.is_playing():
            if current_title != vlc.get_title():
                current_title = vlc.get_title()
                safe_log(f"VLC is currently playing {current_title}")
                playlist = config.get_playlist(current_title)
                if playlist is None:
                    raise ValueError(f"ERROR: No playlist for {current_title}")
                runner = PlaylistRunner(playlist, handler)
            offset = vlc.get_time()
            if offset is not None and runner is not None:
                runner.check_and_run(offset)
        time.sleep(0.2)
    

if __name__ == "__main__":
    main()
