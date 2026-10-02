import re
from typing import Dict, List

import fitz  # PyMuPDF


HEADING_PATTERN = re.compile(
    r"^[ \t]*(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?[ \t]+)?"
    r"(?P<heading>abstract|introduction|materials and methods|patients and methods|"
    r"methods|methodology|results(?: and discussion)?|experiments|discussion|"
    r"conclusions?|concluding remarks|references|bibliography)[ \t]*[:.]?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def extract_pages_from_pdf(pdf_path: str) -> List[Dict]:
    """Extract text with one-based PDF page numbers and close the document."""
    with fitz.open(pdf_path) as doc:
        return [
            {"page_number": index + 1, "text": page.get_text(sort=True)}
            for index, page in enumerate(doc)
        ]


def extract_text_from_pdf(pdf_path: str) -> str:
    return "\n".join(page["text"] for page in extract_pages_from_pdf(pdf_path))


def clean_text(text: str) -> str:
    """Normalize whitespace while retaining headings and meaningful hyphens."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Keep the hyphen: deleting it can turn IL-6 or double-blind into other terms.
    text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "-", text)
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_sections(text: str) -> Dict[str, str]:
    """Recognize standalone headings, rather than words in ordinary sentences."""
    sections = {
        name: ""
        for name in (
            "abstract", "introduction", "methods", "results",
            "discussion", "conclusion", "references",
        )
    }
    matches = list(HEADING_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        heading = match.group("heading").lower()
        if heading in {"materials and methods", "patients and methods", "methodology"}:
            heading = "methods"
        elif heading in {"experiments", "results and discussion"}:
            heading = "results"
        elif heading in {"conclusions", "concluding remarks"}:
            heading = "conclusion"
        elif heading == "bibliography":
            heading = "references"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.start():end].strip()
        sections[heading] = "\n\n".join(filter(None, [sections[heading], content]))
    return sections


def parse_pdf(pdf_path: str) -> Dict:
    pages = extract_pages_from_pdf(pdf_path)
    for page in pages:
        page["text"] = clean_text(page["text"])
    text = "\n".join(page["text"] for page in pages).strip()
    return {
        "pdf_path": str(pdf_path),
        "text": text,
        "pages": pages,
        "sections": split_sections(text),
    }
