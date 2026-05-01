import subprocess
import psutil
import time
from logger import safe_log,logging

class VLCLauncher:
    def __init__(self, telnet_port=4212, password="password"):
        self.telnet_port = telnet_port
        self.password = password

    def is_running(self):
        """Return True if any VLC process is active."""
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if 'vlc' in proc.info['name'].lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def start_vlc(self):
        """Start VLC with telnet interface enabled if not already running."""
        if self.is_running():
            safe_log("VLC is already running.")
            return

        safe_log("Starting VLC...")

        # Adjust the command as needed for your environment
        cmd = [
            "cvlc",  # console (headless) VLC
            "-I", "telnet",
            "--telnet-password", self.password,
            "--telnet-port", str(self.telnet_port),
            "--fullscreen",
            "--vout", "xvideo",
            "--no-video-title-show",
            "--quiet",
            "--start-paused",
            "/home/pi/Documents/volcano_loop.mov",
            "/home/pi/Documents/kikori_loop.mp4"
        ]

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            safe_log("VLC launched successfully. Waiting for it to start...")
            time.sleep(2)  # give VLC a moment to initialize
        except Exception as e:
            safe_log(f"Failed to start VLC: {e}",logging.WARNING)
            raise

    def ensure_running(self):
        """Ensure VLC is running, start if needed."""
        if not self.is_running():
            self.start_vlc()
