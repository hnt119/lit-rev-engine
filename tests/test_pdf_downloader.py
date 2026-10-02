from pathlib import Path

import pytest
import requests
import fitz

from src.download.pdf_downloader import download_pdf, paper_id


PAPER = {
    "entry_id": "https://arxiv.org/abs/2501.12345v1",
    "pdf_url": "https://arxiv.org/pdf/2501.12345v1",
}


def pdf_bytes():
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "Example evidence")
        return doc.tobytes()


class Response:
    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


def test_interrupted_download_does_not_cache_partial_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(
        requests, "get", lambda *a, **kw: Response([
            b"%PDF-1.7\npartial", requests.ConnectionError("disconnected"),
        ]),
    )
    with pytest.raises(requests.ConnectionError):
        download_pdf(PAPER, str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_invalid_cached_file_is_replaced_and_pdf_is_reused(monkeypatch, tmp_path):
    path = tmp_path / "2501.12345v1.pdf"
    path.write_bytes(b"<html>server error</html>")
    content = pdf_bytes()
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response([content]))
    assert Path(download_pdf(PAPER, str(tmp_path))) == path
    assert path.read_bytes() == content
    monkeypatch.setattr(requests, "get", lambda *a, **kw: pytest.fail("cached PDF downloaded"))
    assert Path(download_pdf(PAPER, str(tmp_path))) == path


def test_non_pdf_response_is_not_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response([b"<html>not a PDF</html>"]))
    with pytest.raises(ValueError, match="not a PDF"):
        download_pdf(PAPER, str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_corrupt_pdf_with_valid_header_is_downloaded_again(monkeypatch, tmp_path):
    path = tmp_path / "2501.12345v1.pdf"
    path.write_bytes(b"%PDF-1.7\ntruncated")
    content = pdf_bytes()
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response([content]))
    download_pdf(PAPER, str(tmp_path))
    assert path.read_bytes() == content


def test_legacy_identifier_preserves_category():
    assert paper_id({"entry_id": "https://arxiv.org/abs/math.GT/0309136v1"}) == "math.GT_0309136v1"
    assert paper_id(PAPER) == "2501.12345v1"
