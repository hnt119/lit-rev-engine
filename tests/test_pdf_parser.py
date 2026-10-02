import fitz

from src.parser.pdf_parser import clean_text, parse_pdf, split_sections


def test_sections_do_not_match_words_in_sentences():
    text = (
        "Our methods and results lead to conclusions.\n"
        "1. Introduction\nBackground mentions results.\n"
        "2 Materials and Methods\nActual methods.\n"
        "3 Results\nActual results.\n"
        "4 Conclusions\nActual conclusion.\n"
        "References\nA cited study."
    )
    sections = split_sections(text)
    assert sections["methods"] == "2 Materials and Methods\nActual methods."
    assert sections["results"] == "3 Results\nActual results."
    assert sections["conclusion"] == "4 Conclusions\nActual conclusion."
    assert "A cited study" not in sections["conclusion"]


def test_cleaning_preserves_medical_hyphens():
    assert clean_text("IL-\n6 in a double-\nblind study") == "IL-6 in a double-blind study"


def test_parser_retains_one_based_pages(tmp_path):
    path = tmp_path / "paper.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "Introduction\nFirst page evidence.")
        doc.new_page().insert_text((72, 72), "Results\nSecond page evidence.")
        doc.save(path)
    parsed = parse_pdf(str(path))
    assert [page["page_number"] for page in parsed["pages"]] == [1, 2]
    assert "First page evidence" in parsed["pages"][0]["text"]
    assert "Second page evidence" in parsed["pages"][1]["text"]
    assert "Results" in parsed["sections"]["results"]
    # Opening for update succeeds because the parser closed its document.
    with fitz.open(path) as doc:
        assert len(doc) == 2
