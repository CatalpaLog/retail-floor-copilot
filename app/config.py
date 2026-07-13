from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DATA_DIR = ROOT_DIR / "data"
SOURCE_ARTIFACT_DIR = ROOT_DIR / "artifacts"


def _streamlit_secret(name: str, default: Any = "") -> Any:
    """Read a Streamlit secret without making non-Streamlit processes depend on it."""
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


def get_setting(name: str, default: Any = "") -> Any:
    """Environment variables take precedence; Streamlit secrets are the fallback."""
    value = os.getenv(name)
    if value is not None:
        return value
    return _streamlit_secret(name, default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _copy_demo_data(source: Path, target: Path) -> None:
    """Copy repository demo fixtures into an isolated writable runtime directory."""
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if not path.is_file():
            continue
        if path.name.endswith(".db") or path.name.startswith("."):
            continue
        shutil.copy2(path, target / path.name)


def _prepare_demo_runtime(runtime_root: Path, reset_minutes: int) -> None:
    runtime_data = runtime_root / "data"
    marker = runtime_root / ".prepared_at"
    should_reset = not runtime_data.exists() or not marker.exists()
    if not should_reset and reset_minutes > 0:
        try:
            age_seconds = time.time() - float(marker.read_text(encoding="utf-8"))
            should_reset = age_seconds >= reset_minutes * 60
        except (OSError, ValueError):
            should_reset = True

    if should_reset:
        if runtime_root.exists():
            shutil.rmtree(runtime_root, ignore_errors=True)
        runtime_data.mkdir(parents=True, exist_ok=True)
        _copy_demo_data(SOURCE_DATA_DIR, runtime_data)
        marker.write_text(str(time.time()), encoding="utf-8")


APP_MODE = str(get_setting("APP_MODE", "demo")).strip().lower()
AUTH_MODE = str(get_setting("AUTH_MODE", "demo")).strip().lower()
DEMO_RESET_MINUTES = int(get_setting("DEMO_RESET_MINUTES", "60"))

if APP_MODE == "demo":
    runtime_base = Path(
        str(
            get_setting(
                "RFC_RUNTIME_DIR",
                Path(tempfile.gettempdir()) / "retail-floor-copilot-demo",
            )
        )
    )
    _prepare_demo_runtime(runtime_base, DEMO_RESET_MINUTES)
    DATA_DIR = runtime_base / "data"
    ARTIFACT_DIR = runtime_base / "artifacts"
else:
    DATA_DIR = Path(str(get_setting("RFC_DATA_DIR", SOURCE_DATA_DIR)))
    ARTIFACT_DIR = Path(str(get_setting("RFC_ARTIFACT_DIR", SOURCE_ARTIFACT_DIR)))

DATA_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(str(get_setting("RFC_DB_PATH", DATA_DIR / "retail_copilot.db")))


def reset_demo_runtime() -> None:
    """Reset writable demo fixtures without deleting active log handlers."""
    if APP_MODE != "demo":
        raise RuntimeError("Only demo mode supports runtime reset")
    runtime_root = DATA_DIR.parent
    if DATA_DIR.exists():
        for path in DATA_DIR.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _copy_demo_data(SOURCE_DATA_DIR, DATA_DIR)
    (runtime_root / ".prepared_at").write_text(str(time.time()), encoding="utf-8")


def ensure_demo_runtime_fresh() -> bool:
    """Reset stale demo data on Streamlit reruns; return whether a reset happened."""
    if APP_MODE != "demo" or DEMO_RESET_MINUTES <= 0:
        return False
    marker = DATA_DIR.parent / ".prepared_at"
    try:
        age_seconds = time.time() - float(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        age_seconds = DEMO_RESET_MINUTES * 60
    if age_seconds < DEMO_RESET_MINUTES * 60:
        return False
    reset_demo_runtime()
    return True


@dataclass(frozen=True)
class Settings:
    app_name: str = "门店智伴 Retail Floor Copilot"
    app_version: str = "2.1.0-demo"
    app_mode: str = APP_MODE
    auth_mode: str = AUTH_MODE
    top_k: int = int(get_setting("RFC_TOP_K", "5"))
    min_score: float = float(get_setting("RFC_MIN_SCORE", "0.055"))
    business_date: str = str(get_setting("RFC_BUSINESS_DATE", "2026-07-15"))
    llm_base_url: str = str(get_setting("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_api_key: str = str(get_setting("LLM_API_KEY", ""))
    llm_model: str = str(get_setting("LLM_MODEL", "gpt-4.1-mini"))
    llm_timeout_seconds: float = float(get_setting("LLM_TIMEOUT_SECONDS", "30"))
    demo_access_code: str = str(get_setting("DEMO_ACCESS_CODE", ""))
    api_demo_token: str = str(get_setting("API_DEMO_TOKEN", ""))
    demo_reset_minutes: int = DEMO_RESET_MINUTES
    simulated_inventory: bool = _as_bool(get_setting("SIMULATED_INVENTORY", "true"), True)
    demo_show_role_switcher: bool = _as_bool(get_setting("DEMO_SHOW_ROLE_SWITCHER", "true"), True)
    demo_allow_catalog_writes: bool = _as_bool(get_setting("DEMO_ALLOW_CATALOG_WRITES", "true"), True)

    def active_date(self) -> date:
        try:
            return date.fromisoformat(self.business_date)
        except ValueError:
            return date.today()

    @property
    def is_demo(self) -> bool:
        return self.app_mode == "demo"


settings = Settings()
