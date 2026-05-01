import json
import time
import threading
import queue
import paho.mqtt.client as mqtt
from logger import safe_log,logging
from config_loader import ConfigLoader

class MQTTClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config=None, command_handler=None):
        """Singleton pattern: always return the same instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, command_handler=None):
        if self._initialized:
            return
        self._initialized = True

        self._command_handler = command_handler
        self._queue = queue.Queue()  # for queued outbound messages
        self._command_queue = queue.Queue()  # for queued inbound command requests
        self._stop_event = threading.Event()
        ConfigLoader().subscribe(self.on_config_change)

        self._load_config()

    def _load_config(self):
        self._config = ConfigLoader()
        self._mqtt_config = self._config.get_mqtt_config() or {}

        # Determine if MQTT is enabled
        self._enabled = bool(self._mqtt_config and self._mqtt_config.get("host"))
        if not self._enabled:
            safe_log("MQTTClient: MQTT disabled (no valid config found)", logging.INFO)
            return

        self.host = self._mqtt_config.get("host", "localhost")
        self.port = self._mqtt_config.get("port", 1883)
        self.username = self._mqtt_config.get("username")
        self.password = self._mqtt_config.get("password")
        self.client_id = self._mqtt_config.get("client_id", "tikitv")
        self.keepalive = self._mqtt_config.get("keepalive", 60)
        self.base_topic = self._mqtt_config.get("base_topic")
        self.discovery_prefix = self._mqtt_config.get("discovery_prefix", "homeassistant")
        self.subscriptions = self._mqtt_config.get("subscriptions", [])  # optional list of topics for us to listen to
        self.entities = self._mqtt_config.get("entities", {}) # entities to publish to Home Assistant

        # Initialize client
        self.client = mqtt.Client(client_id=self.client_id)

        if self.username:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.client.connect(self.host, self.port, self.keepalive)
        self.client.loop_start()

        self.publish_discovery_entities()

        # Start background publisher thread
        self._thread = threading.Thread(target=self._publisher_loop, daemon=True)
        self._thread.start()

    def _publisher_loop(self):
        """Background thread that sends queued messages to the MQTT broker."""
        while not self._stop_event.is_set():
            try:
                topic, payload, retain = self._queue.get(timeout=0.2)
                try:
                    self.client.publish(topic, payload, retain=retain)
                    safe_log(f"[MQTT] Published to {topic}: {payload}")
                except Exception as e:
                    safe_log(f"[MQTT] Publish failed: {e}")
            except queue.Empty:
                time.sleep(0.1)  # prevent busy-looping


    # -------------------------------
    # MQTT Event Handlers
    # -------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            safe_log(f"[MQTT] Connected to {self.host}:{self.port}")
            # Subscribe to topics if defined in config
            for topic in self.subscriptions:
                client.subscribe(f"{self.base_topic}/{topic}")
                safe_log(f"[MQTT] Subscribed to: {topic}")
        else:
            safe_log(f"[MQTT] Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        print("[MQTT] Disconnected")
        if rc != 0:
            safe_log("[MQTT] Unexpected disconnect, retrying in 5 seconds...")
            time.sleep(5)
            try:
                self.client.reconnect()
            except Exception as e:
                safe_log(f"[MQTT] Reconnect failed: {e}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages (e.g., control commands from Home Assistant)."""
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        safe_log(f"[MQTT] Received on {topic}: {payload}")

        # Example hook — you could route this to your DMXEngine
        if topic.endswith("/command"):
            self._command_queue.put((topic,payload))

    def on_config_change(self, config):
        """ Handle changes to config.json, in case they affect MQTT """
        self.stop()
        self._load_config()

    def process_pending_commands(self):
        """Interpret MQTT commands and route to DMX CommandHandler."""
        while not self._command_queue.empty():
            topic, payload = self._command_queue.get_nowait()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = payload
            # Pass to the command handler if available
            if self._command_handler:
                try:
                    safe_log(f"[MQTT] processing HASS command {data}")
                    self._command_handler(data)
                except Exception as e:
                    safe_log(f"[MQTT] Error forwarding command to CommandHandler: {e}")
            else:
                safe_log("[MQTT] No CommandHandler registered; ignoring command")

    # -------------------------------
    # Public API
    # -------------------------------

    def publish(self, topic, message, retain=False):
        """Queue a message to publish (non-blocking)."""
        if not self._enabled:
            safe_log(f"MQTTClient disabled: publish({topic}) ignored", logging.DEBUG)
            return
        payload = message if isinstance(message, str) else json.dumps(message)
        self._queue.put((f"{self.base_topic}/{topic}", payload, retain))

    def publish_discovery_entities(self, device_info=None):
        """Publish Home Assistant discovery configs for all entities."""
        if not device_info:
            device_info = {
                "identifiers": ["dmx_controller_1"],
                "name": "DMX Controller",
                "manufacturer": "McSkillman Solutions",
                "model": "DMX Engine v1"
            }

        for key, entity in self.entities.items():
            component = entity.get("component", "sensor")
            unique_id = entity.get("unique_id", key)
            topic = f"{self.discovery_prefix}/{component}/{unique_id}/config"

            payload = {
                "name": entity.get("name", key),
                "state_topic": entity.get("state_topic"),
                "unique_id": unique_id,
                "device": device_info
            }

            # Include optional fields if present
            for field in ["command_topic", "icon", "unit_of_measurement", "json_attributes_topic","value_template"]:
                if field in entity:
                    payload[field] = entity[field]

            if component == "select":
                payload["options"] = list(self._config.get_sequence_names()) + ["off"]

            safe_log(f"Publishing discovery config for {key} → {topic}")
            self.publish(topic, json.dumps(payload), retain=True)
            time.sleep(0.1)  # small delay to avoid flooding

        print("MQTT discovery configs published")

    def stop(self):
        """Gracefully stop MQTT client and background thread."""
        if self._enabled:
            self._stop_event.set()
            self.client.loop_stop()
            self.client.disconnect()
            self._thread.join(timeout=2)
            self._stop_event.clear()
        safe_log("[MQTT] Client stopped")
