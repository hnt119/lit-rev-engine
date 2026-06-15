import fitz  # PyMuPDF
import re
from typing import Dict


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract raw text from PDF using PyMuPDF.
    """
    doc = fitz.open(pdf_path)

    text = []
    for page in doc:
        text.append(page.get_text())

    return "\n".join(text)


def clean_text(text: str) -> str:
    """
    Basic cleanup for academic PDFs.
    """

    # fix hyphenated line breaks
    text = re.sub(r"-\n", "", text)

    # merge broken lines
    text = re.sub(r"\n+", "\n", text)

    # remove excessive spaces
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def split_sections(text: str) -> Dict[str, str]:
    """
    Very simple heuristic section splitter.
    Works surprisingly well for arXiv papers.
    """

    sections = {
        "introduction": "",
        "methods": "",
        "results": "",
        "conclusion": ""
    }

    # normalize
    lower_text = text.lower()

    # find section boundaries
    intro_match = re.search(r"introduction", lower_text)
    method_match = re.search(r"(methodology|methods)", lower_text)
    result_match = re.search(r"(results|experiments)", lower_text)
    concl_match = re.search(r"(conclusion|concluding)", lower_text)

    indices = {
        "intro": intro_match.start() if intro_match else -1,
        "methods": method_match.start() if method_match else -1,
        "results": result_match.start() if result_match else -1,
        "conclusion": concl_match.start() if concl_match else -1,
    }

    # sort valid indices
    sorted_sections = sorted(
        [(k, v) for k, v in indices.items() if v != -1],
        key=lambda x: x[1]
    )

    # split text by positions
    for i, (name, start_idx) in enumerate(sorted_sections):
        end_idx = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else len(text)
        content = text[start_idx:end_idx]

        if name == "intro":
            sections["introduction"] = content
        elif name == "methods":
            sections["methods"] = content
        elif name == "results":
            sections["results"] = content
        elif name == "conclusion":
            sections["conclusion"] = content

    return sections


def parse_pdf(pdf_path: str) -> Dict:
    """
    Full pipeline: PDF → structured representation.
    """

    raw_text = extract_text_from_pdf(pdf_path)
    cleaned = clean_text(raw_text)
    sections = split_sections(cleaned)

    return {
        "pdf_path": pdf_path,
        "text": cleaned,
        "sections": sections
    }