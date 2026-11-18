"""Seed the local database with the bundled sample incidents (analysed in DEMO mode).

    python -m incident_intel.seed
"""
import json

from dotenv import load_dotenv

from .analysis import AnalysisService
from .api import SAMPLES_PATH
from .config import Settings
from .storage import Storage


def main():


    """Insert the bundled samples as demo-mode analyses."""
    load_dotenv()
    settings = Settings.from_env(history_enabled=True)
    service = AnalysisService(settings, Storage(settings.database_path))
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        samples = json.load(f)
    for s in samples:
        service.analyze({**{k: s[k] for k in ("title", "service", "description")}, "provider": "demo"})
    print(f"Seeded {len(samples)} demo-analysed sample incidents into {settings.database_path}")


if __name__ == "__main__":
    main()
