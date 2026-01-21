# TikiTV DMX Controller

This project provides a Python-based DMX lighting controller for Raspberry Pi, designed to synchronize DMX lighting to a video file, with optional integration with Home Assistant via MQTT. It supports sequences, scenes, fixtures, crossfades, and can respond to triggers from a VLC video timeline.

---

## Prerequisites

Before using this project, you need:

1. **Raspberry Pi running a desktop OS** (Raspberry Pi OS recommended).
2. **USB DMX controller compatible with [OLA (Open Lighting Architecture)](https://www.openlighting.org/ola/)**.
   - Example compatible device: [USB DMX512 Adapter on Amazon](https://www.amazon.com/DSD-TECH-Lighting-Equipment-Controller/dp/B07WV6P5W6/ref=sr_1_5)
3. **OLA and ola-python libraries installed**:

```bash
sudo apt install ola ola-python
```

4. **OLA Universe configuration**:

   - If using an FTDI serial-based USB DMX controller, disable all other serial USB plugins in OLA to avoid conflicts by editing their config files in /etc/ola
   - Configure a universe using your USB DMX controller by browsing to http://<your pi's IP address>:9090

5. **Home Assistant integration (optional)**:
   - Install the MQTT plugin in Home Assistant.
   - Create a dedicated credential for this project.
   - Ensure the Raspberry Pi can connect to the MQTT broker.

---

## Configuration

All settings are stored in `config.json`. A fully configured system is included in the project's `config.json` file. You need to configure:

### Fixtures

Define your DMX lighting fixtures in the `fixtures` array. You should be able to get the assignments from the user manual for your fixtures. The names for the assignments are arbitrary, but must match the names given in the `values` map specified in the Scenes below.

```json
"fixtures": [
  {
    "name": "front_left",
    "address": 1,
    "channels": 8,
    "assignments": {"dimmer": 0, "red": 1, "green": 2, "blue": 3}
  }
]
```

- `address`: DMX start address of the fixture.
- `channels`: Total number of channels this fixture has. Not currently used, but good to track
- `assignments`: Mapping of channel names to offsets from the start address.

### Scenes

Scenes are sets of static lighting values that are applied to a predefined set of fixtures. A scene consists of a set of fixtures for the scene, and a set of values to apply to all of those fixtures, with optional override values for individual fixtures. The DMX engine automatically handles transitioning between sequential scenes by fading values linearly

```json
"scenes": [
  {
    "name": "bright yellow",
    "values": {"dimmer": 255, "red": 255, "green": 255, "blue": 0},
    "fixtures": [{"name": "front_left"},
                 {"name": "front_right",
                    "overrides": {
                      "dimmer": 128
                      }
                  }
                ]
  }
]
```

- `values`: Default channel values for the scene.
- `fixtures`: Array of fixture references with optional overrides.

### Sequences

Sequences are built up from an array of one or more scenes, along with timing for how to transition between each scene. Specify an array of one or more sequences

```json
"sequences": [
  {
    "name": "Daylight",
    "loop": true,
    "priority": 0,
    "scenes": [
      {"scene": "bright yellow", "duration": 5.0, "transition": 0}
    ]
  }
]
```

- `name`: Unique name for this sequence. This name is used to reference this sequence in commands
- `loop`: Whether the sequence should repeat indefinitely
- `priority`: Priority ranking of this sequence. A lower numbered sequence will not be played if a higher-numbered sequence is playing
- `scenes`: Array of scenes that compose this sequence. Scenes are referred to by name. `transition` is the fade-in time and `duration` is the length of time the sequence plays for. The total time the scene takes is equal to transition + duration

### Playlists

Playlists are associated with VLC video file names. You must specify an array of at least one or more playlists (specify a dummy name if you don't intend to use VLC)

```json
"playlists": [
  {
    "name": "volcano_loop.mov",
    "triggers": [
      {
        "offset": 2,
        "command": "mqtt current_scene {\"scene\": \"show_start\"}"
      },
      { "offset": 5, "command": "play Daylight" },
      { "offset": 2643, "command": "play Lightning" },
       { "offset": 3605, "command": "vlc seek 0" }
    ]
  }
]
```

- `name`: The name of the playlist, which must match the full name of the video file
- `triggers`: An array of time offsets. Each offset consists of an `offset` value in seconds, and a `command` to be executed (see below)

### MQTT (for Home Assistant integration)

MQTT is a service that allows IoT devices to communicate with each other in a semi-standard way. The DMX controller includes an MQTT client. It is intended for use with Home Assistant, but could be used in any environment that supports MQTT for message passing.

```json
"mqtt": {
  "host": "192.168.1.1",
  "port": 1883,
  "username": "tikitv",
  "password": "TikiTV",
  "base_topic": "lighting/tikitv",
  "discovery_prefix": "homeassistant",
  "subscriptions": ["command", "set_scene"],
  "entities": {
    "scene_trigger": {
      "component": "select",
      "name": "TikiTV Scene Trigger",
      "state_topic": "lighting/tikitv/current_scene",
      "command_topic": "lighting/tikitv/set_scene",
      "icon": "mdi:play",
      "unique_id": "dmx_scene_switch"
    }
  }
}
```

- `host`: The host IP of your MQTT server - most likely your Home Assistant server
- `port`: Port for MQTT. The default is 1883
- `username`/`password`: Credentials for the MQTT server
- `subscriptions`: An array of topics to listen for commands on
- `base_topic`: The topic prefix to prepend to `subscriptions`
- `entities`: An array of entity objects to publish to Home Assistant's autodiscovery topic

### VLC integration (optional)

- Ensure VLC is installed (`sudo apt install vlc`).
- VLC videos can be started in a paused state via the DMX controller.
- TODO: Configure `vlc_telnet_port` and `password` and the default video file in `config.json`. Currently they are hard-coded

The DMX controller will launch VLC at startup, in a paused state, hidden behind the desktop. When a command is received via MQTT to start playback, VLC starts playing and moves to the foreground. Edit vlc_launcher.py to change the name of the video file it plays by default. To have VLC start playing immediately upon start up, comment out the "--start-paused" line in vlc_launcher.py

---

## Commands

The DMX controller is essentially a command processing engine. Commands can come from either a `playlist`, triggered at VLC time offsets, or via an MQTT topic, e.g. from Home Assistant. The following commands are currently supported:

- `play <sequence_name>`: takes a sequence name as an argument, and immediately starts the new DMX sequence playing. If the new sequence is non-looping, the previous sequence will resume when the new sequence ends
- `stop`: Immediatley stop the currently playing sequence. If a previously looping sequence was playing before this sequence, it will resume
- `stop_with_fade <value>`: Takes a floating point value. Fade to black over the specified number of seconds. No previous sequence will resume. Use a small value (e.g. `0.1`) to stop without allowing a previous sequence to resume
- `mqtt <topic> <json>`: Takes two arguments - the topic name and an escaped JSON string to send. This will send the specified JSON message to the specified topic. The `base_topic` value is prepended to the specified `topic`
- `vlc <command>`: Pass `command` through to VLC via the telnet interface - all telnet commands are supported. For example, `vlc seek 0` will tell VLC to seek to the start of the current video
- `startup`: Intended to be received from Home Assistant, this will seek to the beginning of the current video and start playback in full screen
- `shutdown`: Intended to be received from Home Assistant, this will pause playback and fade all DMX lights to black

---

## Home Assistant Integration

Integration with Home Assistant is done using MQTT. MQTT is a message passing service, allowing for asynchronous communication between IoT devices and services. Home Assistant supports the automatic discovery of entities through a message publishing mechanism - the entity (in this case, this DMX controller)
publishes JSON messages to specific topics corresponding with the entities it wishes to publish. Once published, these entities will be available to Home Assistant to view in the dashboard, and to use in automations.

The included `config.json` file includes several defined entities, including a `current_scene` entity, where the currently playing scene is published. An automation can then be created in Home Assistant to trigger actions based on specific scenes playing. For example, if the room that will house the DMX controller has lighting in it that is controlled by Home Assistant (such as Wifi RGB lights), this mechanism can be used to synchronize the WiFi lights with the DMX lights. Here's an example automation:

```yaml
alias: DMX → Home Assistant Scene Mapper
description: Activate Tiki Patio scenes based on DMX light sequences
triggers:
  - entity_id: sensor.dmx_controller_tikitv_current_scene
    trigger: state
conditions: []
actions:
  - choose:
      - conditions:
          - condition: state
            entity_id: sensor.dmx_controller_tikitv_current_scene
            state: Daylight
        sequence:
          - target:
              entity_id: scene.tiki_daylight
            data:
              transition: 5
            action: scene.turn_on
      - conditions:
          - condition: or
            conditions:
              - condition: state
                entity_id: sensor.dmx_controller_tikitv_current_scene
                state: Sunset
              - condition: state
                entity_id: sensor.dmx_controller_tikitv_current_scene
                state: Sunrise
        sequence:
          - target:
              entity_id: scene.tiki_sunset
            data:
              transition: 5
            action: scene.turn_on
```

This automation turns on the "tiki_daylight" scene in Home Assistant when the "Daylight" sequence plays on the DMX controller, and the "tiki_sunset" scene when either Sunset or Sunrise play.

## Starting at Boot

Create a `systemd` service file `/etc/systemd/system/tikitv.service`:

```ini
[Unit]
Description=TikiTV DMX Controller
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/tikitv
ExecStart=/usr/bin/python3 /home/pi/tikitv/main.py
StandardOutput=append:/run/shm/tikitv.log
StandardError=append:/run/shm/tikitv.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Reload `systemd` and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tikitv
sudo systemctl start tikitv
```

> Logs are stored in `/run/shm/tikitv.log` (RAM disk) to reduce SD card writes.

---

## Usage

- Place video files in `/home/pi/Documents`.
- Configure fixtures, scenes, and sequences in `config.json`.
- Start the DMX controller:

```bash
sudo systemctl start tikitv
```

- If Home Assistant integration is enabled, the scene select entity will appear, allowing you to trigger sequences.

---

## Notes

- Only **one sequence** can play at a time. Higher-priority sequences can interrupt lower-priority ones.
- DMX **control channels** can be configured to **not fade**, avoiding unwanted fixture behavior.
- MQTT publishing is non-blocking and thread-safe.

---

## References

- [OLA (Open Lighting Architecture)](https://www.openlighting.org/ola/)
- [Home Assistant MQTT Integration](https://www.home-assistant.io/integrations/mqtt/)
- [VLC Command-Line Options](https://wiki.videolan.org/VLC_command-line_help/)
