from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
import fitz

from src.settings import settings


def sanitize_filename(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)


def paper_id(paper: Dict) -> str:
    """Preserve both modern and category-prefixed legacy arXiv identifiers."""
    path = urlparse(paper["entry_id"]).path
    identifier = path.split("/abs/", 1)[-1] if "/abs/" in path else path.strip("/")
    identifier = sanitize_filename(identifier)
    if not identifier:
        raise ValueError("Paper entry_id does not contain an identifier.")
    return identifier


def _is_readable_pdf(path: Path) -> bool:
    with path.open("rb") as handle:
        if b"%PDF-" not in handle.read(1024):
            return False
    try:
        with fitz.open(path) as doc:
            return len(doc) > 0
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError):
        return False


def download_pdf(paper: Dict, save_dir: Optional[str] = None) -> str:
    """Download atomically so interrupted or non-PDF responses are not cached."""
    directory = Path(save_dir) if save_dir is not None else settings.data_directory / "pdfs"
    directory.mkdir(parents=True, exist_ok=True)
    filepath = directory / f"{paper_id(paper)}.pdf"
    if filepath.is_file() and _is_readable_pdf(filepath):
        return str(filepath)

    temporary = None
    try:
        with requests.get(paper["pdf_url"], stream=True, timeout=30) as response:
            response.raise_for_status()
            with NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
        if not _is_readable_pdf(temporary):
            raise ValueError("Downloaded response is not a PDF or is unreadable.")
        temporary.replace(filepath)
        return str(filepath)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_many(papers: List[Dict], save_dir: Optional[str] = None) -> List[str]:
    paths = []
    for paper in papers:
        try:
            paths.append(download_pdf(paper, save_dir=save_dir))
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            print(f"Failed to download {paper.get('title', 'unknown')}: {exc}")
    return paths
