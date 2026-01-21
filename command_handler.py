# command_handler.py
import json
from mqtt_client import MQTTClient
from logger import safe_log,logging
from config_loader import ConfigLoader


class CommandHandler:
    def __init__(self, dmx_engine, vlc_client):
        """
        dmx_engine: instance of DMXEngine
        sequence_loader: instance of ConfigLoader (for accessing loaded sequences)
        """
        self.dmx_engine = dmx_engine
        self.sequence_loader = ConfigLoader()
        self.vlc_client = vlc_client

    def __call__(self, command_str: str):
        """
        Parse and execute a command string from the playlist.
        Supported commands:
          - play <sequence>
          - stop
          - stop_with_fade <seconds>
        """
        safe_log(f"Received command: '{command_str}'")
        parts = command_str.strip().split(maxsplit=1)
        if not parts:
            safe_log("Empty command string",logging.WARNING)
            return

        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else None

        try:
            if cmd == "play":
                if args is None:
                    raise ValueError("play command requires 1 argument: sequence name")
                sequence_name = args
                sequence = self.sequence_loader.get_sequence(sequence_name)
                if sequence is None:
                    safe_log(f"Sequence '{sequence_name}' not found",logging.ERROR)
                    return
                safe_log(f"Playing sequence '{sequence_name}'")
                self.dmx_engine.play_sequence(sequence)

            elif cmd == "stop":
                safe_log("Stopping DMX output immediately")
                self.dmx_engine.stop()

            elif cmd == "stop_with_fade":
                if args is None:
                    raise ValueError("stop_with_fade command requires 1 argument: fade time (seconds)")
                fade_time = float(args)
                safe_log(f"Stopping DMX output with fade over {fade_time} seconds")
                self.dmx_engine.stop_with_fade(fade_time)

            elif cmd == "mqtt":
                mqtt = MQTTClient()
                if mqtt is None:
                    safe_log(f"Can not execute command {cmd}. MQTT not configured",logging.WARNING)
                if args:
                    try:
                        parts = args.split(maxsplit=1)
                        if len(parts) == 1:
                            raise ValueError("mqtt command requires two arguments: topic and JSON string")
                        data = json.loads(parts[1])
                        mqtt.publish(parts[0],data)
                    except json.JSONDecodeError:
                        print("Invalid JSON in MQTT command")

            elif cmd =="vlc":
                # Send a command to VLC
                if args:
                    self.vlc_client.send_command(args)

            elif cmd == "startup":
                # Go through startup process for VLC
                self.vlc_client.send_command("volume 256")
                self.vlc_client.send_command("play")
                self.vlc_client.send_command("seek 0")
                self.vlc_client.send_command("fullscreen on")
            elif cmd == "shutdown":
                self.vlc_client.send_command("pause")
                self.vlc_client.send_command("fullscreen off")
                self.dmx_engine.stop_with_fade(5)
            else:
                safe_log(f"Unknown command: {cmd}",logging.ERROR)

        except Exception as e:
            safe_log(f"Error executing command '{command_str}': {e}",logging.ERROR)
