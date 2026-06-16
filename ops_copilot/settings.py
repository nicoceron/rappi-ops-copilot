from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def default_data_file() -> Path:
    env_value = os.getenv("DATA_FILE")
    if env_value:
        return Path(env_value)

    files = sorted(DEFAULT_DATA_DIR.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(
            "No .xlsx file found in data/. Set DATA_FILE to the workbook path."
        )
    return files[0]


def export_dir() -> Path:
    value = os.getenv("EXPORT_DIR", str(PROJECT_ROOT / "outputs"))
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_api_base_url() -> str:
    return os.getenv(
        "PUBLIC_API_BASE_URL",
        os.getenv("NEXT_PUBLIC_OPS_API_URL", "http://localhost:8000"),
    ).rstrip("/")
