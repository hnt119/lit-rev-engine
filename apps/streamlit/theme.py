"""Load portable identity tokens and the temporary Streamlit presentation adapter."""
from pathlib import Path


def load_theme() -> str:
    """Return local CSS without importing Streamlit or changing research state."""
    theme_dir = Path(__file__).resolve().with_name("theme")
    return "\n\n".join(
        (theme_dir / name).read_text(encoding="utf-8")
        for name in ("tokens.css", "streamlit.css")
    )
