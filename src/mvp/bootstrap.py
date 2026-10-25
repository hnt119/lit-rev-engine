"""Construct CPU-only services/configuration without any UI dependency.

Only provider/rate-gate objects and storage adapters are shared. No current
workspace, capability, notes, source selection or private result is cached here.
"""
from functools import lru_cache
import os
import re
from pathlib import Path

from .ports import MvpError

ROOT = Path(__file__).resolve().parents[2]


def public_runtime_info() -> dict:
    from .adapters.saved_examples import saved_example_info
    return {"live_available": bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", os.environ.get("NCBI_EMAIL", "").strip())),
            "saved_example": saved_example_info(), "default_mode": "saved_example"}


def build_service(mode: str = "saved_example", data_dir: str | Path | None = None):
    """Build the same application service for Streamlit, scripts or a future API."""
    if mode not in {"saved_example", "live"}:
        raise MvpError("invalid_mode", "Choose saved example or live discovery.")
    directory = Path(data_dir or os.environ.get("MVP_DATA_DIR") or ROOT / ".mvp-state").expanduser().absolute()
    email = os.environ.get("NCBI_EMAIL", "").strip()
    api_key = os.environ.get("NCBI_API_KEY") or None
    try:
        timeout = float(os.environ.get("MVP_HTTP_TIMEOUT_SECONDS", "12"))
    except ValueError:
        raise MvpError("invalid_configuration", "The server request timeout must be a positive number up to 15 seconds.") from None
    return _build(mode, str(directory), email, api_key, timeout)


@lru_cache(maxsize=8)
def _build(mode, directory, email, api_key, timeout):
    from .adapters.storage import SQLiteWorkspaceStorage
    from .adapters.saved_examples import SavedExampleProvider
    from .adapters.transport import BoundedTransport
    from .service import MVPService
    if mode == "live" and not email:
        raise MvpError("live_not_configured", "Live PubMed discovery is not configured. Use the saved example or configure the server contact email.")
    if mode == "saved_example":
        discovery = source_provider = SavedExampleProvider()
    else:
        from .adapters.pubmed import PubMedPreviewProvider
        from .adapters.europe_pmc import EuropePmcSourceProvider
        try:
            transport = BoundedTransport(timeout=timeout)
        except ValueError:
            raise MvpError("invalid_configuration", "The server request timeout must be a positive number up to 15 seconds.") from None
        try:
            discovery = PubMedPreviewProvider(email=email, api_key=api_key, transport=transport)
        except ValueError:
            raise MvpError("invalid_configuration", "Configure a valid server contact email for live PubMed discovery.") from None
        source_provider = EuropePmcSourceProvider(transport=transport)
    return MVPService(SQLiteWorkspaceStorage(Path(directory) / "workspaces.sqlite3"), discovery, source_provider)
