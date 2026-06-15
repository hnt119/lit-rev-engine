import arxiv
from typing import List, Dict


def search_arxiv(query: str, max_results: int = 10) -> List[Dict]:
    """
    Keyword-based search for academic papers on arXiv.
    """

    client = arxiv.Client()

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )

    results = []

    for paper in client.results(search):
        results.append({
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": paper.summary,
            "published": str(paper.published),
            "pdf_url": paper.pdf_url,
            "entry_id": paper.entry_id
        })

    return results