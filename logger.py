import logging

# Create a global logger
logger = logging.getLogger("DMX")
logger.setLevel(logging.DEBUG)

# Configure handler (stdout)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d [%(threadName)s %(thread)d] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Optional: avoid duplicate logs if re-imported
logger.propagate = False

def safe_log(msg, level=logging.INFO):
    """Thread-safe log wrapper."""
    logger.log(level, msg)
