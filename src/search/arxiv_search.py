import arxiv
from typing import List, Dict

from src.settings import settings


def search_arxiv(query: str, max_results: int = settings.max_search_results) -> List[Dict]:
    """
    Keyword-based search for academic papers on arXiv.
    """

    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    if not isinstance(max_results, int) or isinstance(max_results, bool) or max_results <= 0:
        raise ValueError("max_results must be a positive integer.")
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
