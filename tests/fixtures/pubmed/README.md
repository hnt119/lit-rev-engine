# Synthetic PubMed response fixtures

These are independently constructed software fixtures, not saved live searches. PMIDs, DOI, authors, titles, warning, translation, and history token are invented. They contain no clinical findings and must not be resolved or cited as real bibliography records. The files test adapter behavior, not PubMed search sensitivity or real database result ordering.

`manifest.json` is the hand-computed test oracle. The original submitted query intentionally has two leading/trailing spaces; request and receipt must retain them. `search-five.xml` returns **five unique IDs** in this exact order:

```text
999999803, 999999801, 999999805, 999999802, 999999804
```

Use `batch_size=2`. Expected requests and deliberately different response order:

| Batch | Requested IDs in order | Returned record order | Record count |
| --- | --- | --- | --- |
| `fetch-0001.xml` | 999999803, 999999801 | 999999801, 999999803 | 2 |
| `fetch-0002.xml` | 999999805, 999999802 | 999999802, 999999805 | 2 |
| `fetch-0003.xml` | 999999804 | 999999804 | 1 |

There are four journal-article records and one `PubmedBookArticle` (999999805). Combined `records.xml` must restore the ESearch order **803, 801, 805, 802, 804**, not response order, numeric order, or article-only order. Five captured IDs = five validated fetched records = five unique own PMIDs. A valid capture makes **four successful requests**: one search and three fetches. Neither the book accession nor reference-only PMID **999999899** is an additional result.

- Record 801 contains nested title/abstract text and a collective author. Expected title: `Synthetic capture record A: nested-text exercise`. Authors: `Example, Ada`, `Synthetic Fixture Consortium`. Abstract: `PURPOSE: Preserve synthetic bibliography metadata.\nNOTE: No clinical results or actual research participants are described.`
- Record 803 includes matching DOI fields and a cited-reference PMID 999999899. The reference PMID is not the record's own identity.
- Record 805 is a book record with a collective author and year 2024.
- Record 802 uses `MedlineDate` for year 2023 and initials for `Example, BB`; its abstract is absent.
- Record 804 makes a one-record final batch. Publication years in search order are **2025, 2024, 2024, 2023, 2022**, consistent with the declared descending publication-date sort. Ties do not define an independent ordering rule.

The fixture ESearch **response** has `RetMax=5` and `RetStart=0`; the adapter's **request** must use `retmax=10000` and `retstart=0`. RetMax describes IDs shown, not proof that all matching records were retrieved. The requested filter object is `{"datetype":"pdat","mindate":"2020/01/01","maxdate":"2025/12/31"}`; exact text must survive. The translation includes date terms and differs from the input; warnings and history tokens must be preserved. The external search DTD is intentionally declared but must never be fetched.

`search-zero.xml` is a successful zero-result search: `Count=RetMax=RetStart=0`, empty IdList, a translation and warning, no history tokens. Expected capture has one search request, no fetch requests, an empty combined PubmedArticleSet, `reported_count=fetched_count=0`, `complete=true`, and null history values.

`error-search.xml` and `error-fetch.xml` are HTTP-200 response bodies that must still fail. The manifest describes adversarial transformations for a 10,001-result search, short/duplicate/wrong-membership responses, missing/conflicting own IDs, malformed XML, and entities. Evaluation may implement independent transformations; production code must not use this manifest or weaken membership checks to accept it.

Official references:

- [NCBI ESearch/EFetch parameters](https://www.ncbi.nlm.nih.gov/sites/books/NBK25499/): zero-based start, returned RetMax, history tokens, explicit PMID fetches, publication-date sort, and PubMed's 10,000 ESearch limit.
- [NCBI E-utilities quick start](https://www.ncbi.nlm.nih.gov/sites/books/NBK25500/): query translations in the search response.
- [NLM PubMed XML elements](https://www.nlm.nih.gov/bsd/licensee/data_elements_doc.html) and [book-record schema](https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/190101/el-PubmedBookArticle.html): citation, nested text, authors, and book records.

The synthetic warning code demonstrates preservation of warning metadata; no claim is made that a live query would return these IDs or this exact wording.
