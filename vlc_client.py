import socket
from logger import safe_log

class VLCClient:
    def __init__(self, host='localhost', port=4212, password='password', timeout=5):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.sock = None

    def connect(self):
        """Establish a Telnet connection and authenticate with password."""
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            # Wait for "Password: " prompt
            self._read_until_prompt(prompt="Password: ")
            # Send password and wait for main prompt
            self._send_raw(self.password)
            self._read_until_prompt(prompt="> ")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to VLC at {self.host}:{self.port}: {e}") from e

    def _send_raw(self, text):
        """Send raw text to VLC, followed by newline."""
        cmd = (text.strip() + "\n").encode()
        if self.sock is not None:
            self.sock.sendall(cmd)

    def _read_until_prompt(self, prompt="> "):
        """Read socket until the given prompt is seen."""
        data = b""
        if self.sock is not None:
            self.sock.settimeout(self.timeout)
            while True:
                chunk = self.sock.recv(1024)
                if not chunk:
                    break
                data += chunk
                if prompt.encode() in data:
                    break
            decoded = data.decode(errors="ignore")
            # Remove trailing prompt text
            cleaned = decoded.split(prompt)[0]
            return cleaned.strip()

    def _send_command(self, command, prompt="> "):
        """
        Send a command and return parsed response lines (without prompt).
        """
        if not self.sock:
            self.connect()
        self._send_raw(command)
        response = self._read_until_prompt(prompt=prompt)
        # Split into non-empty stripped lines
        if response is not None:
            lines = [line.strip() for line in response.splitlines() if line.strip()]
            return lines

    def get_time(self):
        """Fetch current playback time in seconds."""
        lines = self._send_command("get_time")
        if lines is not None:
            for line in lines:
                if line.isdigit():
                    return int(line)
        return None

    def get_title(self):
        """Fetch current title name (string)."""
        lines = self._send_command("get_title")
        # Typically, the response is a single line with the title
        return lines[0] if lines else None

    def close(self):
        """Close the Telnet connection."""
        if self.sock:
            try:
                self._send_raw("logout")
            except Exception:
                pass
            self.sock.close()
            self.sock = None

    def is_playing(self) -> bool:
        """
        Query VLC to see if it is currently playing.
        Returns True if playing, False if not.
        """
        try:
            response = self._send_command("is_playing")
            if response is None:
                return False
            # VLC returns "1" if playing, "0" if not
            for line in response:
                if line.isdigit():
                    return line.strip() == "1"
        except Exception as e:
            safe_log(f"Error checking is_playing: {e}")
        return False

    def send_command(self,cmd):
        return self._send_command(cmd)   