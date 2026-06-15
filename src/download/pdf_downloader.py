import os
import requests
from typing import Dict, List


def sanitize_filename(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)


def download_pdf(paper: Dict, save_dir: str = "data/pdfs") -> str:
    """
    Download a single paper PDF from arXiv.
    Returns file path.
    """

    os.makedirs(save_dir, exist_ok=True)

    arxiv_id = paper["entry_id"].split("/")[-1]
    filename = sanitize_filename(arxiv_id) + ".pdf"
    filepath = os.path.join(save_dir, filename)

    # Skip if already exists
    if os.path.exists(filepath):
        return filepath

    response = requests.get(paper["pdf_url"], stream=True, timeout=30)
    response.raise_for_status()

    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return filepath


def download_many(papers: List[Dict]) -> List[str]:
    """
    Batch download multiple PDFs.
    """
    paths = []

    for paper in papers:
        try:
            path = download_pdf(paper)
            paths.append(path)
        except Exception as e:
            print(f"Failed: {paper.get('title', 'unknown')}")
            print(e)

    return paths