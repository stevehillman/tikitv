import time
import threading
from simple_dmx_client import SimpleDMXClient
from sequence import Sequence
from mqtt_client import MQTTClient
from logger import safe_log
from value_event import ValueEvent

# ---------------------------------------------------------------------------
# DMX Engine
# ---------------------------------------------------------------------------
class DMXEngine:
    def __init__(self, config_loader, client: SimpleDMXClient, fps=30):
        self.config_loader = config_loader
        self.client = client
        self.fps = fps
        self.lock = threading.Lock()

        self.current_frame = bytearray([0]*512) # The most recent frame sent to DMX
        self.active_sequence = None
        self.previous_sequence = None
        self.sequence_thread = None
        self.stop_requested = ValueEvent()

    # --------------------------------------------
    # Internal fade function
    # --------------------------------------------
    def _fade_to_scene(self, target_scene, duration):
        non_fading = self.config_loader.get_non_fading_channels()
        steps = max(1, int(duration * self.fps))
        current = getattr(self, 'current_frame', bytearray([0]*512))
        target = bytearray(current)
        if not target_scene:  # fade to black
            target = bytearray([0]*512)
        else:
            for ch, val in target_scene.items():
                target[ch] = val

        if duration:
            for step in range(steps):
                if self.stop_requested.is_set() and target_scene:
                    return
                progress = (step + 1)/(steps+1)
                frame = bytearray(512)
                for ch in range(512):
                    if ch + 1 in non_fading:  # DMX channels are 1-indexed
                        frame[ch] = current[ch] if progress < 0.5 else target[ch]  # no fade
                    else:
                        frame[ch] = int(current[ch] + (target[ch] - current[ch]) * progress)
                self.current_frame = frame
                self.client.send_dmx(self.current_frame)
                time.sleep(1/self.fps)
        self.current_frame = target
        self.client.send_dmx(self.current_frame)

    # --------------------------------------------
    # Thread runner for a sequence
    # --------------------------------------------
    def _sequence_runner(self):
        safe_log("Sequence runner started")
        fade_time = None
        mqtt = MQTTClient()

        while True:
            with self.lock:
                sequence = self.active_sequence

            if not sequence:
                safe_log("No active sequence, runner exiting")
                break

            safe_log(f"Playing sequence '{sequence.name}' (loop={sequence.loop})")

            mqtt.publish("current_scene",{"scene":sequence.name,"status":"playing"})

            for step in sequence.steps:
                scene_name = step["scene_name"]
                duration = step["duration"]
                transition = step["transition"]

                if sequence != self.active_sequence:
                    # Active sequence has changed, break out so we can start the new sequence
                    break
                if self.stop_requested.is_set():
                    safe_log("Stop requested...")
                    fade_time = self.stop_requested.get_value()
                    if fade_time is not None:
                        safe_log(f"Fading out over {fade_time} seconds...")
                        self._fade_to_scene({}, fade_time)
                    else:
                        safe_log("Stopping immediately.")
                    break

                scene = self.config_loader.get_scene(scene_name)
                if not scene:
                    print(f"[DMXEngine] Scene '{scene_name}' not found.")
                    continue

                safe_log(f"Fading to scene {scene_name} over {transition}s")
                target = scene.values
                self._fade_to_scene(target, transition)

                start_time = time.time()
                while not self.stop_requested.is_set() and (time.time() - start_time < duration):
                    time.sleep(1/self.fps)

            if self.stop_requested.is_set():
                # Clean up after stop
                with self.lock:
                    self.stop_requested.clear()
                    self.active_sequence = None
                    if self.previous_sequence and fade_time is None and self.active_sequence != self.previous_sequence:
                        safe_log(f"Resuming previous sequence '{self.previous_sequence.name}'")
                        self.active_sequence = self.previous_sequence
                        self.previous_sequence = None
                    else:
                        self.active_sequence = None

                continue

            # ✅ Loop or finish
            if not sequence.loop:
                safe_log(f"Sequence '{sequence.name}' finished (no loop)")
                with self.lock:
                    if sequence == self.active_sequence:
                        self.active_sequence = None
                        if self.previous_sequence:
                            safe_log(f"Resuming previous sequence '{self.previous_sequence.name}'")
                            self.active_sequence = self.previous_sequence
                            self.previous_sequence = None
                if not self.active_sequence:
                    break
            else:
                safe_log(f"Looping sequence '{sequence.name}'")

        safe_log("Sequence runner exiting")
        mqtt.publish("current_scene",{"scene":"off","status":"idle"})

        with self.lock:
            self.active_sequence = None
            self.previous_sequence = None


    # --------------------------------------------
    # Play a sequence (interrupts lower-priority sequences)
    # --------------------------------------------
    def play_sequence(self, sequence: Sequence):
        """Start or replace the active sequence based on priority."""
        with self.lock:
            # Clean up old thread if done
            self._cleanup_thread()

            # If something is already playing, decide if we should interrupt
            if self.active_sequence:
                if sequence.priority >= self.active_sequence.priority:
                    safe_log(f"Interrupting '{self.active_sequence.name}' with '{sequence.name}'")
                    self.previous_sequence = self.active_sequence
                    if not sequence.loop:
                        # If the new sequence isn't a looping sequence, request a hard stop of the current sequence
                        # Otherwise, let it fade from the old to new sequence
                        self.stop_requested.set()
                else:
                    safe_log(f"Ignoring '{sequence.name}' because '{self.active_sequence.name}' has higher priority")
                    return

            self.active_sequence = sequence
            self.stop_requested.clear()

            # If no runner exists or it's stopped, start it
            if not self.sequence_thread or not self.sequence_thread.is_alive():
                safe_log("Starting new sequence runner thread")
                self.sequence_thread = threading.Thread(target=self._sequence_runner, daemon=True)
                self.sequence_thread.start()

    # --------------------------------------------
    # Stop current sequence immediately
    # --------------------------------------------
    def stop(self):
        self.stop_requested.set_value(None)

    # --------------------------------------------
    # Stop current sequence with fade to black
    # --------------------------------------------
    def stop_with_fade(self, fade_time):
        safe_log(f"Requesting stop with fade: {fade_time}s")
        self.stop_requested.set_value(fade_time)

    # --------------------------------------------
    # Internal cleanup of finished threads
    # --------------------------------------------
    def _cleanup_thread(self):
        if self.sequence_thread and not self.sequence_thread.is_alive():
            safe_log("Cleaning up finished thread")
            self.sequence_thread.join(timeout=0.1)
            self.sequence_thread = None
