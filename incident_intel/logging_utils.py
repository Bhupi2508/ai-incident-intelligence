"""Logging helpers. Incident text and API keys are never logged; use redact() on anything external."""
import logging
import re

_KEY_LIKE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{20,}|AKIA[0-9A-Z]{12,}|Bearer\s+\S+)")


def redact(text, secrets=()):
    """Remove known secret values and anything that looks like an API key from text."""
    text = str(text)
    for s in secrets:
        if s:
            text = text.replace(s, "[redacted]")
    return _KEY_LIKE.sub("[redacted]", text)


def get_logger(name="incident_intel"):


    """Return the app logger, configuring basic logging once."""
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logger
