#!/usr/bin/env python3

import time

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
    engine = DMXEngine()

    vlc_launcher = VLCLauncher(4212,"tikitv")
    vlc_launcher.ensure_running()
    vlc = VLCClient("127.0.0.1", 4212, "tikitv")

    handler = CommandHandler(engine, vlc)
    mqtt_client = MQTTClient(handler)

    runner = None
    last_whole_offset = None
    fractional_offset = 0.0
    last_poll_time = time.monotonic()

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

            whole_offset = vlc.get_time()  # integer seconds from VLC

            if whole_offset is not None and runner is not None:
                now = time.monotonic()
                elapsed = now - last_poll_time
                last_poll_time = now

                if last_whole_offset is None or whole_offset != last_whole_offset:
                    # VLC time advanced (or first read) — reset fractional part
                    fractional_offset = 0.0
                    last_whole_offset = whole_offset
                else:
                    # Same second — advance fractional offset using real elapsed time
                    fractional_offset += elapsed

                    # Cap it so we never roll into the next second
                    if fractional_offset >= 0.999:
                        fractional_offset = 0.999

                precise_offset = whole_offset + fractional_offset

                runner.check_and_run(precise_offset)
        time.sleep(0.2)
    

if __name__ == "__main__":
    main()
