from pathlib import Path

APP_NAME = "reddit-video-automator"
APP_DIR = Path.home() / f".{APP_NAME}"
APP_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{APP_DIR / 'app.db'}"
KEY_FILE = APP_DIR / ".key"