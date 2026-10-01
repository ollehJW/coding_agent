"""Load the project .env without replacing deployment environment variables."""
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_environment(path=None):
    return load_dotenv(path or PROJECT_ROOT / '.env', override=False)


def database_path():
    import os
    value = os.environ.get('DB_PATH', '').strip()
    path = Path(value).expanduser() if value else PROJECT_ROOT / 'backend/app.db'
    return path if path.is_absolute() else PROJECT_ROOT / path


load_environment()
