# Independent synthetic source, locator, and quote truth

These invented source files support the source-document gate before structured extraction. They describe software fixtures, not real publications, patients, clinical findings, or medical gold labels. `manifest.json` was authored independently of the operational source parser and lists exact expected blocks, typed locators, hashes, and quotations.

| File | Format | Expected blocks | Source/version purpose |
| --- | --- | --- | --- |
| `source-v1.txt` | UTF-8 text with BOM | 1 | CRLF retained; composed café, decomposed café, Greek characters, emoji, scoped negation. |
| `source-v2.txt` | UTF-8 text with BOM | 1 | Only invented follow-up changes from 6 to 8 weeks. |
| `article-v1.xml` | Synthetic JATS XML | 7 | Title, abstract, nested body text, table/cells/foot, section paths, negation, excluded references. |
| `article-v2.xml` | Synthetic JATS XML | 7 | Same structural paths; only follow-up paragraph changes from 6 to 8 weeks. |
| `three-pages.pdf` | Generated synthetic PDF | 3 | Actual pages 1 and 3 contain text; actual page 2 is blank. Printed labels are 10 and 12. |

The manifest's `fixtures` array contains `alias`, `file`, `format`, source hash/size, expected parser ID, complete `expected_blocks`, canonical block hash, and `quotes`. IDs and locators belong to a source version, not a runtime document UUID. Evaluation should map returned document IDs after attachment. A replacement retains earlier bytes/blocks, receives a new document/version ID, and must not certify an old quotation as support for revised text solely because its block path is unchanged.

TXT has one block, `text:1`, locator `{"type":"text_block","ordinal":1}`. Decode UTF-8/BOM and remove only the BOM: CRLF and composed/decomposed characters remain exact. The Unicode code-point count differs from UTF-8 byte length. Canonical text is not a normalized scientific assertion.

JATS expected document order is:

1. `/article[1]/front[1]/article-meta[1]/title-group[1]/article-title[1]`
2. `/article[1]/front[1]/article-meta[1]/abstract[1]/sec[1]/p[1]`
3. `/article[1]/body[1]/sec[1]/p[1]`
4. `/article[1]/body[1]/sec[1]/table-wrap[1]`
5. `/article[1]/body[1]/sec[1]/p[2]`
6. `/article[1]/body[1]/sec[2]/p[1]`
7. `/article[1]/body[1]/sec[2]/sec[1]/p[1]`

Each block ID prefixes its path with `xml:`. Locator fields use `type="xml_element"`, `path`, `tag`, original `element_id`, and nearest enclosing `section_title` where present; the table also has `table_label="Table S1"`. There are no PDF page numbers in XML locators. Reference-list title/value are retained in source bytes but never expected finding blocks.

Join inline text before collapsing whitespace: `X<sub>2</sub>` becomes `X2`, not `X 2`. Extra abstract spaces/newline collapse to ordinary spaces. Preserve Unicode/punctuation. The table is exactly one block; caption/footer paragraphs do not become additional blocks. Its canonical text is:

```text
Table S1
Invented software counts.
Group\tCount
α\t12
β\t12
Total: 24 fixture rows
Software counts only; no participant data.
```

Above, `\t` denotes an actual tab in the manifest block. Label, caption, each row, and table foot are separate lines. The spanning `colspan="2"` cell stays one textual cell; no invented second value or semantic span expansion is permitted. External DTD points to `invalid.example/never-fetch.dtd` specifically to prove parsing needs no network. No entity is declared in the valid files.

`quotes` use **Unicode code-point offsets** into the exact canonical block string, half-open `[start,end)`. The exact nonempty slice must equal `quote`. Offsets are not raw XML/PDF/UTF-8 byte positions or printed page numbers. They include table tabs, TXT CRLF, and Unicode as appropriate. The manifest supplies 16 quote anchors across the five files, including X2 concatenation, table row/foot, quantitative text, negation, and revised follow-up. These are source-location assertions, not entailment/clinical correctness judgments.

The block hash is SHA-256 of `json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`. Source hash uses exact file bytes. Every expected block includes unique `id`, one-based `ordinal`, exact `text`, and typed `locator`. Both source and block hashes differ between the original and revised TXT/JATS versions, while relevant block IDs remain stable.

Parser provenance is part of the acceptance contract: metadata must record the effective Python version and decoding/normalization/extraction options. PDF metadata additionally records the effective PyMuPDF version and sorted page-text option. These runtime facts must not be replaced by the fixture generator's version fields or inferred publisher versions.

The PDF fixture was generated with the existing PyMuPDF version recorded in `pdf_generation`; no images, OCR, external fonts, or medical paper downloads are involved. Its standard-font ASCII page text has no trailing newline under that runtime's sorted extraction. The empty second page still contributes `pdf:page:2`, ordinal 2, empty text, locator `{"type":"pdf_page","page":2}`. Page 3's locator is 3, even though its text prints label 12. All-text-empty/encrypted/corrupt inputs belong to independent rejection tests.

Reproduce PDF bytes with the same runtime into a new output path:

```sh
python tests/fixtures/evidence/generate_pdf.py /tmp/new-synthetic-source.pdf
```

The recipe refuses to overwrite an existing file, uses fixed metadata with no dates/random document ID, and lazily imports only existing PyMuPDF. Two same-runtime generations were byte-identical; different library versions may serialize/extract differently. The committed PDF/hash pin this source, and the recipe provides layout provenance rather than permission to silently replace it.

Fixture verification requires no operational source parser. Verify file size/SHA-256 and canonical block hashes from the manifest, every quote slice, every manually supplied XML path/element ID/section/table label, and actual PDF positions/text. Existing source files are immutable test inputs; rejection cases can be temporary transforms. Useful adversarial transforms include ENTITY declarations, malformed/error XML, replacing an own quotation with reference-only text, out-of-range offsets, quote/locator mismatch, corrupt PDF, or an all-blank PDF. Evaluation independently owns those cases and the stored-version/transaction/snapshot tests.
