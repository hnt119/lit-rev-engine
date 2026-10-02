"""Generate an invented three-page PDF fixture, including a blank second page."""

from pathlib import Path
import sys


PAGE_TEXTS = (
    "Software fixture PDF; no medical findings.\nPDF physical page 1, printed label 10.\nFollow-up: 6 weeks.",
    "",
    "PDF physical page 3, printed label 12.\nNo diagnostic estimate was reported.",
)


def pdf_bytes():
    # This fixture recipe uses the existing dependency; no source parser/model.
    import fitz

    document = fitz.open()
    try:
        for text in PAGE_TEXTS:
            page = document.new_page(width=595, height=842)
            if text:
                page.insert_text((72, 72), text, fontname="helv", fontsize=12)
        document.set_metadata({
            "title": "Synthetic source locator fixture",
            "author": "Software Fixture Collaboration",
            "creator": "lit-rev-engine fixture recipe",
            "producer": "Synthetic software fixture",
        })
        return document.tobytes(garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python generate_pdf.py NEW_OUTPUT_PATH")
    with Path(sys.argv[1]).open("xb") as output:
        output.write(pdf_bytes())
