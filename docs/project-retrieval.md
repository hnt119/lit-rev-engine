# Finding passages in a review project's sources

Status: **synthetic walkthrough verified; optional whole-block method passes its bounded v3 medical pilot; BM25 remains the software default; v1 and v2 failures preserved**. The API, CLI, candidate methods, and prospective evaluation rules are frozen in the [v1 milestone](project-retrieval-milestone.md), [v2 contract](project-retrieval-v2-milestone.md) and [v3 contract](project-retrieval-v3-milestone.md). All six original executable synthetic shell blocks passed in a temporary ledger with network/settings/model imports blocked; the additional guarded context block also passed. Each medical candidate was selected prospectively before its fresh held-out ranking. Exact anchors and a small pilot do not establish clinical validity or automatic answerability.

Project retrieval searches the source blocks retained in a review ledger and returns exact passage candidates with source provenance. It uses the project's active document versions in one SQLite read snapshot. The existing arXiv/Chroma/Agnes pipeline has its own index and runtime; these commands use the ledger's retained source representations and initialize no model, network request, or live vector collection.

## Select scope and preserve the trace

Command template, with your database path and project UUID:

```text
.venv/bin/python review.py --db /path/to/review.sqlite3 retrieve-sources PROJECT_UUID \
  --query "Enter the population, outcome, and timepoint you want to inspect" \
  --top-k 5 --method bm25 --scope included > retrieval-trace.json
```

Choose the scope explicitly when inspecting sources before eligibility decisions:

| Scope | Selected sources |
| --- | --- |
| `included` | Active documents of currently full-text-included reports; the default scope. |
| `all_attached` | Active documents of every report with an attachment, including pending/excluded reports. |

Older document versions remain auditable but do not supply retrieval candidates. Source attachment itself does not include a report or establish a study association. `all_attached` supports source inspection during screening; it does not make its results eligible for an evidence proposal. Resolved study IDs and screening/linkage state are returned as snapshot provenance.

`retrieve-sources` writes JSON to stdout. Save the entire result through shell redirection: the exact query, method/version/parameters, scope, source manifest, manifest SHA-256, and ranked anchors belong together. There is no `--output` flag, and the command creates no ledger search/evidence events. Keep saved traces alongside a project export when you need a portable review bundle. The trace describes its original retrieval snapshot; later screening, source, or linkage changes do not rewrite it.

The result identifies `status="candidate_passages"`, `source_manifest`, `source_snapshot_sha256`, `indexed_passages`, `matched_passages`, and `passages`. Each source manifest entry identifies the source document/report/version, source/block hashes, parser identity/options, explicit source identifiers, descriptive source URL/version label, and current screening/linkage state. Each candidate retains rank, score, report/document IDs, source/block hashes, parser ID, typed locator, and an exact `anchor` containing `block_id`, `start`, `end`, and `quote`. Offsets are half-open Unicode code-point bounds in its canonical source block.

Candidate methods are `token_overlap`, `bm25`, `bm25_context` and `bm25_context_blocks`, using the same frozen Unicode casefolded word tokens and stop words. The first three methods use windows of at most 200 whitespace-delimited words with 40 words of overlap. The whole-block method returns complete canonical blocks. Every anchor preserves its original substring and stays within one block/document; XML locators remain element paths and PDF locators remain actual page positions. BM25 is the API/CLI default selected on the frozen development criteria. Use `--method` explicitly to preserve your intended comparison. Parameters, method IDs, and full source manifests are included in each trace.

Only positive-score candidates are returned, up to the positive integer `top_k`. A query reduced to no effective tokens can return an empty candidate list while retaining its source manifest and indexed count. Selected source integrity/identity is still checked. Corrupt selected sources, an explicit source/report DOI/PMID contradiction, unknown projects, blank queries, and invalid options fail without ledger mutations.

Rank and score order lexical matches. They do not certify support, answerability, effect direction, clinical significance, or extraction verification. A high-ranking negation or limitation can be useful context while leaving the requested estimate unreported. An empty result also does not prove absence from the literature.

## Optional XML scoring context

The [prospective v2 contract](project-retrieval-v2-milestone.md) adds `bm25_context` as an explicit optional experimental interface; the default remains `bm25`. It scores an XML paragraph/table window using its own tokens plus the last at most 80 words of the nearest preceding accepted paragraph with the same immediate XML parent. Context cannot come from another parent, document, report, project or source version. Titles, TXT/PDF blocks and targets without an eligible preceding paragraph have no context. Context token frequencies also enter the BM25 document lengths and corpus statistics; this is a different recorded scoring representation, not an assertion that a nearby paragraph supports a finding.

```text
.venv/bin/python review.py --db /path/to/review.sqlite3 retrieve-sources PROJECT_UUID \
  --query "population outcome timepoint" --top-k 5 --method bm25_context --scope included \
  > context-retrieval-trace.json
```

```python
context_trace = store.search_sources(
    project_id, "population outcome timepoint",
    top_k=5, method="bm25_context", scope="included",
)
```

Its method ID is `lit-rev-engine.project-retrieval.v2.bm25_context`, with `context_rule="preceding-paragraph-same-xml-parent-v1"` and `context_max_words=80` recorded alongside the BM25 parameters. Each returned passage retains its exact own-block `anchor` and adds `scoring_context`: an empty list or one separately anchored context object with its own exact `locator`. Both refer to blocks of the same retained source representation. A match can be driven solely by context tokens even when the returned own quote does not contain the query term.

Reuse `candidate["anchor"]` as the quote location of a manually entered evidence proposal. Inspect `candidate["scoring_context"]` separately to understand the rank; do not replace the finding anchor with that context or join the two strings into a quotation. If a finding requires both passages, they must be inspected and anchored separately. Scoring context contributes neither an answerability claim nor positive support coverage, and ranking never creates or verifies an extraction. The [independent v2 evaluation](medical-retrieval-v2-evaluation.md) failed the fresh held-out quality gate. This method remains experimental; its synthetic proof below establishes software behavior, not medical retrieval quality.

## Complete canonical blocks

The [prospective v3 contract](project-retrieval-v3-milestone.md) adds optional `bm25_context_blocks`. It uses the same BM25 constants and preceding-XML-paragraph scoring context, but supplies one candidate per nonblank canonical block. A long paragraph or table keeps its entire text, including every canonical row and table foot. TXT blocks and physical PDF page blocks also retain their complete text. Whitespace-only blocks are skipped; nonblank punctuation-only and stopword-only blocks remain indexed even if they cannot score positively.

```text
.venv/bin/python review.py --db /path/to/review.sqlite3 retrieve-sources PROJECT_UUID \
  --query "population outcome timepoint" --top-k 5 --method bm25_context_blocks \
  --scope included > block-retrieval-trace.json
```

The method ID is `lit-rev-engine.project-retrieval.v3.bm25_context_blocks`. Its parameters record `passage_unit="block"` and omit window/overlap sizes. Each own anchor has `start=0`, `end=len(canonical_block_text)` and the full canonical text as `quote`, preserving padding and Unicode. Context is separately anchored and enters each scoring representation once. It supplies no own-quotation support. Whole blocks can be long; inspect the relevant exact quotations before manually proposing evidence. Retrieval creates no finding, verification or automatic model input. The [independent v3 evaluation](medical-retrieval-v3-evaluation.md) accepts the bounded source-disjoint quality gate; this method remains an explicitly selected reviewer-facing candidate interface.

## Synthetic offline walkthrough

Run the blocks below in order from the repository root in one bash or zsh shell. They write only to a new temporary directory and create their own invented text; they do not use or change the medical pilot. This demonstration checks scope, active-version selection, trace preservation, and direct candidate-anchor reuse. It supplies no medical findings or retrieval-performance claim.

Set up two invented reports. The first will be included and linked; the second will remain pending. Its text explicitly says diagnostic sensitivity was not measured.

```sh
set -e
PROJECT_RETRIEVAL_PYTHON=".venv/bin/python"
PROJECT_RETRIEVAL_DEMO="$(mktemp -d "${TMPDIR:-/tmp}/lit-source-retrieval.XXXXXX")"
PROJECT_RETRIEVAL_DB="$PROJECT_RETRIEVAL_DEMO/review.sqlite3"
source_demo_cli() { "$PROJECT_RETRIEVAL_PYTHON" review.py --db "$PROJECT_RETRIEVAL_DB" "$@"; }
source_demo_id() {
  "$PROJECT_RETRIEVAL_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' \
    "$1" "${2:-id}"
}
cat > "$PROJECT_RETRIEVAL_DEMO/records.json" <<'JSON'
[
  {"title":"Invented included software report","source_id":"SYNTHETIC-INCLUDED"},
  {"title":"Invented pending software report","source_id":"SYNTHETIC-PENDING"}
]
JSON
printf '%s\n' 'Software fixture only. Fixture follow-up: 6 weeks, not 12 months.' > "$PROJECT_RETRIEVAL_DEMO/included-v1.txt"
printf '%s\n' 'Software fixture only. Fixture follow-up: 8 weeks, not 12 months.' > "$PROJECT_RETRIEVAL_DEMO/included-v2.txt"
printf '%s\n' 'Software fixture only. No diagnostic sensitivity was measured.' > "$PROJECT_RETRIEVAL_DEMO/pending.txt"
source_demo_cli create --title "Synthetic project retrieval" --type scoping \
  --question "Can exact candidates retain scope and source-version provenance?" \
  > "$PROJECT_RETRIEVAL_DEMO/project.json"
PROJECT_RETRIEVAL_PROJECT="$(source_demo_id "$PROJECT_RETRIEVAL_DEMO/project.json")"
source_demo_cli import "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_DEMO/records.json" \
  --source "Invented retrieval demonstration" --import-key synthetic-source-demo \
  > "$PROJECT_RETRIEVAL_DEMO/import.json"
source_demo_cli records "$PROJECT_RETRIEVAL_PROJECT" > "$PROJECT_RETRIEVAL_DEMO/records-listed.json"
PROJECT_RETRIEVAL_INCLUDED="$("$PROJECT_RETRIEVAL_PYTHON" -c 'import json,sys; print(next(r["id"] for r in json.load(open(sys.argv[1])) if r["title"]=="Invented included software report"))' "$PROJECT_RETRIEVAL_DEMO/records-listed.json")"
PROJECT_RETRIEVAL_PENDING="$("$PROJECT_RETRIEVAL_PYTHON" -c 'import json,sys; print(next(r["id"] for r in json.load(open(sys.argv[1])) if r["title"]=="Invented pending software report"))' "$PROJECT_RETRIEVAL_DEMO/records-listed.json")"
```

Include and link the first report, then attach its six-week and eight-week sources as separate immutable versions. Attach the other report's source while leaving its screening/linkage pending.

```sh
source_demo_cli screen "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  --stage title_abstract --decision include --reviewer FixtureScreener --reason "Invented setup."
source_demo_cli fulltext "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  --status retrieved --reviewer FixtureScreener --reason "Local invented source available."
source_demo_cli screen "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  --stage full_text --decision include --reviewer FixtureScreener --reason "Invented setup."
source_demo_cli study-create "$PROJECT_RETRIEVAL_PROJECT" --label "Invented software study" \
  --reviewer FixtureCurator --reason "Manual demonstration association." \
  > "$PROJECT_RETRIEVAL_DEMO/study.json"
PROJECT_RETRIEVAL_STUDY="$(source_demo_id "$PROJECT_RETRIEVAL_DEMO/study.json")"
source_demo_cli link-studies "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  --study-id "$PROJECT_RETRIEVAL_STUDY" --reviewer FixtureLinker --reason "Complete manual association."
source_demo_cli attach-source "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  "$PROJECT_RETRIEVAL_DEMO/included-v1.txt" --format txt --reviewer Ari \
  --reason "Invented six-week source." > "$PROJECT_RETRIEVAL_DEMO/document-v1.json"
source_demo_cli attach-source "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  "$PROJECT_RETRIEVAL_DEMO/included-v2.txt" --format txt --reviewer Ari \
  --reason "Invented active eight-week replacement." > "$PROJECT_RETRIEVAL_DEMO/document-v2.json"
source_demo_cli attach-source "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_PENDING" \
  "$PROJECT_RETRIEVAL_DEMO/pending.txt" --format txt --reviewer Ari \
  --reason "Retain invented source before screening." > "$PROJECT_RETRIEVAL_DEMO/document-pending.json"
PROJECT_RETRIEVAL_DOC_V2="$(source_demo_id "$PROJECT_RETRIEVAL_DEMO/document-v2.json")"
PROJECT_RETRIEVAL_DOC_PENDING="$(source_demo_id "$PROJECT_RETRIEVAL_DEMO/document-pending.json")"
```

Save three explicit traces. The included scope selects one active document. The all-attached scope selects both active documents, so it can retrieve the pending report's unmeasured-sensitivity declaration. Its lexical match supplies no measured sensitivity estimate.

```sh
source_demo_cli retrieve-sources "$PROJECT_RETRIEVAL_PROJECT" \
  --query "fixture follow-up weeks" --top-k 5 --method bm25 --scope included \
  > "$PROJECT_RETRIEVAL_DEMO/included-trace.json"
source_demo_cli retrieve-sources "$PROJECT_RETRIEVAL_PROJECT" \
  --query "diagnostic sensitivity" --top-k 5 --method token_overlap --scope included \
  > "$PROJECT_RETRIEVAL_DEMO/included-diagnostic-trace.json"
source_demo_cli retrieve-sources "$PROJECT_RETRIEVAL_PROJECT" \
  --query "diagnostic sensitivity" --top-k 5 --method token_overlap --scope all_attached \
  > "$PROJECT_RETRIEVAL_DEMO/all-attached-trace.json"
source_demo_cli source-blocks "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_DOC_V2" \
  > "$PROJECT_RETRIEVAL_DEMO/blocks-v2.json"
source_demo_cli source-blocks "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_DOC_PENDING" \
  > "$PROJECT_RETRIEVAL_DEMO/blocks-pending.json"
```

Inspect the included candidate, then manually enter the invented eight-week value/context while reusing its complete exact anchor. The anchor alone supplies no interpretation. A candidate from a pending report still needs eligibility and a resolved study association before a proposal is allowed.

```sh
"$PROJECT_RETRIEVAL_PYTHON" - "$PROJECT_RETRIEVAL_DEMO" "$PROJECT_RETRIEVAL_STUDY" <<'PY'
import hashlib, json, sys
from pathlib import Path
folder = Path(sys.argv[1])
read = lambda name: json.loads((folder / name).read_text())
included = read("included-trace.json")
all_attached = read("all-attached-trace.json")
snapshots = [read("blocks-v2.json"), read("blocks-pending.json")]
sources = {s["document"]["id"]: s for s in snapshots}
for trace in (included, read("included-diagnostic-trace.json"), all_attached):
    assert trace["status"] == "candidate_passages"
    canonical = json.dumps(trace["source_manifest"], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == trace["source_snapshot_sha256"]
    for candidate in trace["passages"]:
        snapshot = sources[candidate["document_id"]]
        block = next(b for b in snapshot["blocks"] if b["id"] == candidate["anchor"]["block_id"])
        anchor = candidate["anchor"]
        assert block["text"][anchor["start"]:anchor["end"]] == anchor["quote"]
        assert candidate["locator"] == block["locator"]
        assert candidate["source_sha256"] == snapshot["document"]["source_sha256"]
        assert candidate["blocks_sha256"] == snapshot["document"]["blocks_sha256"]
assert len(included["source_manifest"]) == 1 and len(included["passages"]) == 1
assert read("included-diagnostic-trace.json")["passages"] == []
assert len(all_attached["source_manifest"]) == 2 and len(all_attached["passages"]) == 1
assert included["scope"] == "included" and all_attached["scope"] == "all_attached"
assert {source["document_id"] for source in included["source_manifest"]} == {read("document-v2.json")["id"]}
assert {source["document_id"] for source in all_attached["source_manifest"]} == {
    read("document-v2.json")["id"], read("document-pending.json")["id"],
}
candidate = included["passages"][0]
assert candidate["document_id"] == read("document-v2.json")["id"]
assert candidate["document_version"] == 2
assert "8 weeks, not 12 months." in candidate["anchor"]["quote"]
assert all_attached["passages"][0]["document_id"] == read("document-pending.json")["id"]
assert "No diagnostic sensitivity was measured." in all_attached["passages"][0]["anchor"]["quote"]
payload = {
    "study_id": sys.argv[2], "document_id": candidate["document_id"],
    "field": "fixture.follow_up", "value": {"duration": 8, "unit": "weeks"},
    "context": {"population": "Invented entries; not patients", "timepoint": "8 weeks",
                "units": "weeks", "notes": "Manually entered software value; explicitly not twelve months."},
    "anchor": candidate["anchor"],
}
(folder / "manual-proposal.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
print("Exact candidate anchors/source hashes checked; manual proposal payload prepared.")
PY
source_demo_cli propose-evidence "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_INCLUDED" \
  --payload "$PROJECT_RETRIEVAL_DEMO/manual-proposal.json" --reviewer Ari \
  --reason "Manually inspected the source and entered the invented eight-week value." \
  > "$PROJECT_RETRIEVAL_DEMO/proposal.json"
source_demo_cli evidence "$PROJECT_RETRIEVAL_PROJECT" --verified-only \
  > "$PROJECT_RETRIEVAL_DEMO/verified.json"
```

Expected: the exact anchor is reusable, but the new extraction remains `proposed` and verified-only output is empty. Follow the [independent verification guide](verified-evidence.md) to confirm/reject it with a distinct reviewer, preserve disagreement, or revise it after a source change.

Retain the original retrieval traces beside a project export, then check that the proposal remains unverified. These copied traces are caller-managed files, not extra ledger events or automatic export-manifest entries.

```sh
mkdir "$PROJECT_RETRIEVAL_DEMO/bundle"
source_demo_cli export "$PROJECT_RETRIEVAL_PROJECT" "$PROJECT_RETRIEVAL_DEMO/bundle/project" \
  > "$PROJECT_RETRIEVAL_DEMO/export-result.json"
cp "$PROJECT_RETRIEVAL_DEMO/included-trace.json" \
  "$PROJECT_RETRIEVAL_DEMO/included-diagnostic-trace.json" \
  "$PROJECT_RETRIEVAL_DEMO/all-attached-trace.json" "$PROJECT_RETRIEVAL_DEMO/bundle/"
```

Check the exported proposal, retained documents, and byte-preserved trace files:

```sh
"$PROJECT_RETRIEVAL_PYTHON" - "$PROJECT_RETRIEVAL_DEMO" <<'PY'
import hashlib, json, sys
from pathlib import Path
folder = Path(sys.argv[1])
project = json.loads((folder / "bundle/project/project.json").read_text())
assert json.loads((folder / "verified.json").read_text()) == project["verified_evidence"] == []
assert len(project["evidence"]) == 1 and project["evidence"][0]["state"] == "proposed"
assert len(project["documents"]) == 3
assert len(project["search_runs"]) == 1 and len(project["evidence_reviews"]) == 0
candidate = json.loads((folder / "included-trace.json").read_text())["passages"][0]
stored_anchor = project["evidence"][0]["current_revision"]["anchor"]
assert {key: stored_anchor[key] for key in candidate["anchor"]} == candidate["anchor"]
for name in ("included-trace.json", "included-diagnostic-trace.json", "all-attached-trace.json"):
    assert (folder / name).read_bytes() == (folder / "bundle" / name).read_bytes()
for artifact in project["document_artifacts"]:
    content = (folder / "bundle/project" / artifact["export_file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
print("PASS: scopes/active versions/exact anchors checked; three trace JSON files preserved; one manual proposal remains unverified.")
print("Inspect temporary demonstration:", folder)
PY
```

The verified synthetic run selected only the included report's active second version in `included` scope and both active documents in `all_attached`. It retained three source versions, preserved all three trace files byte-for-byte, and reused the exact candidate anchor in one manual proposal. Verified output remained empty, and the ranking calls created no extra import/search runs or evidence reviews.

## Guarded synthetic context check

This additional block is standalone and uses the existing Python environment. Setup creates one isolated temporary ledger with an invented included report, manual study association and XML attachment. All subsequent CLI calls are reads; an exact database-byte comparison proves that retrieval and source inspection leave the seeded ledger unchanged. Guards reject network sockets, model/index dependencies and application settings imports. The block invokes the same CLI parser/handler in-process so the guards cover every command. It creates a manual proposal JSON file for inspection, without submitting or verifying it.

```sh
.venv/bin/python - <<'PY'
import builtins, contextlib, hashlib, io, json, socket, sys, tempfile
from pathlib import Path

def denied(*args, **kwargs):
    raise AssertionError("This demonstration permits no network, models, live index, or settings.")

class GuardedSocket(socket.socket):
    def __new__(cls, *args, **kwargs):
        denied()

socket.socket = GuardedSocket
socket.create_connection = denied
original_import = builtins.__import__
forbidden = {"requests", "httpx", "openai", "chromadb", "langchain", "langchain_core",
             "langchain_community", "sentence_transformers", "transformers", "dotenv"}

def guarded_import(name, *args, **kwargs):
    if name.split(".")[0] in forbidden or name in {"src.settings", "src.config", "src.config.settings"}:
        denied()
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
try:
    builtins.__import__("src.settings")
except AssertionError:
    pass
else:
    raise AssertionError("The repository settings import was not rejected.")
assert "src.settings" not in sys.modules
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.review.cli import main

folder = Path(tempfile.mkdtemp(prefix="lit-synthetic-context-"))
database = folder / "review.sqlite3"
xml = b'''<article><front><article-meta><title-group>
<article-title>Invented software context report</article-title>
</title-group></article-meta></front><body><sec id="fixture"><title>Software fixture</title>
<p id="older">Distant software widget description used six weeks.</p>
<p id="nearest">Synthetic software widget measurements used eight weeks.</p>
<p id="result">Invented value: 7 units; no medical meaning.</p>
<sec id="other"><title>Other fixture</title><p id="isolated">Separate placeholder.</p></sec>
</sec></body></article>'''
with ReviewStore(database) as store:
    project = store.create_project("Synthetic context check", "scoping", "Inspect invented passages.")["id"]
    store.import_records(project, SearchRunSpec("Invented context fixture"),
                         [BibliographicRecord(title="Invented context report")])
    report = store.list_records(project)[0]["id"]
    store.record_decision(project, report, "title_abstract", "include", "FixtureScreener")
    store.set_full_text_status(project, report, "retrieved", "FixtureCustodian")
    store.record_decision(project, report, "full_text", "include", "FixtureScreener")
    study = store.create_study(project, "Invented widget study", "FixtureCurator", "Software association.")["id"]
    store.record_study_links(project, report, [study], "FixtureLinker", "Complete manual association.")
    document = store.attach_document(project, report, xml, "jats_xml", "FixtureCustodian", "Invented source.")["id"]

def cli(*arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert main(["--db", str(database), *arguments]) == 0
    return json.loads(output.getvalue())

before = database.read_bytes()
context_trace = cli("retrieve-sources", project, "--query", "widget", "--top-k", "5",
                    "--method", "bm25_context", "--scope", "included")
default_trace = cli("retrieve-sources", project, "--query", "widget", "--top-k", "5")
snapshot = cli("source-blocks", project, document)
assert database.read_bytes() == before
assert default_trace["method"] == "bm25"
assert all("scoring_context" not in row for row in default_trace["passages"])
assert context_trace["method_version"] == "lit-rev-engine.project-retrieval.v2.bm25_context"
assert context_trace["parameters"]["context_rule"] == "preceding-paragraph-same-xml-parent-v1"
assert context_trace["parameters"]["context_max_words"] == 80
assert len(context_trace["source_manifest"]) == 1 and len(context_trace["passages"]) == 3
canonical_manifest = json.dumps(context_trace["source_manifest"], ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
assert hashlib.sha256(canonical_manifest).hexdigest() == context_trace["source_snapshot_sha256"]
blocks = {block["id"]: block for block in snapshot["blocks"]}
for candidate in context_trace["passages"]:
    for item in [candidate, *candidate["scoring_context"]]:
        anchor = item["anchor"]
        block = blocks[anchor["block_id"]]
        assert block["text"][anchor["start"]:anchor["end"]] == anchor["quote"]
        assert item["locator"] == block["locator"]
    assert candidate["source_sha256"] == snapshot["document"]["source_sha256"]
    assert candidate["blocks_sha256"] == snapshot["document"]["blocks_sha256"]

candidate = next(row for row in context_trace["passages"] if row["locator"].get("element_id") == "result")
context = candidate["scoring_context"][0]
assert len(candidate["scoring_context"]) == 1 and context["locator"]["element_id"] == "nearest"
assert context["anchor"]["quote"] == "Synthetic software widget measurements used eight weeks."
assert candidate["anchor"]["quote"] == "Invented value: 7 units; no medical meaning."
assert "widget" not in candidate["anchor"]["quote"]
assert candidate["locator"]["path"].rsplit("/", 1)[0] == context["locator"]["path"].rsplit("/", 1)[0]
manual = {"study_id": study, "document_id": document, "field": "fixture.value",
          "value": {"amount": 7, "unit": "fixture units"},
          "context": {"population": "Invented software entries", "timepoint": "Synthetic demonstration",
                      "units": "fixture units", "notes": "Entered manually; scoring context is separate."},
          "anchor": candidate["anchor"]}
assert manual["anchor"] == candidate["anchor"] and manual["anchor"] != context["anchor"]
for name, value in (("context-trace.json", context_trace), ("default-trace.json", default_trace),
                    ("source-blocks.json", snapshot), ("manual-proposal.json", manual)):
    (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
print("Own finding quote:", manual["anchor"]["quote"])
print("Separate scoring context:", context["anchor"]["quote"])
print("PASS: settings import rejected; three context candidates; nearest paragraph selected; exact own/context anchors; BM25 default; three read-only CLI calls; no proposal submitted.")
print("Inspect temporary synthetic traces:", folder)
PY
```

The verified guarded run rejected an attempted import of the repository's actual `src.settings` module, returned three context candidates and selected the nearest eligible paragraph for the invented value. The value paragraph is a candidate because its separate context contains `widget`; its finding anchor contains only the invented value. All returned own/context anchors matched the source blocks, the default BM25 trace had no `scoring_context` fields, and the three CLI reads left database bytes unchanged. The manual proposal remained a caller-managed JSON file. This check establishes trace/anchor behavior, not medical retrieval performance; all six earlier shell blocks remain byte-identical.

## Python API and evaluation status

```python
from src.review.store import ReviewStore

with ReviewStore("/path/to/review.sqlite3") as store:
    trace = store.search_sources(
        project_id, "population outcome timepoint",
        top_k=5, method="bm25", scope="included",
    )
    # Inspect a candidate and enter value/context manually before proposing it.
```

The frozen medical pilot has nine development and nine held-out questions, each split containing seven answerable and two no-answer items. Support sets use OR alternatives and AND necessary passages, and quote coverage must preserve the correct source/block. No-answer candidates and retrieved limitation/context spans are reported separately from answerable denominators.

The [development selection receipt](medical-retrieval-selection-v1.json) records BM25 selection before held-out ranking. Both methods met the predeclared development gate and tied on mean support coverage and complete questions at five; BM25 had the higher reciprocal rank under the frozen tie ordering.

| Development method | Mean support coverage at five | Complete answerable questions at five | Mean reciprocal rank at five |
| --- | --- | --- | --- |
| Token overlap | 0.8571 | 6/7 | 0.6476 |
| BM25, selected | 0.8571 | 6/7 | 0.7857 |

Both methods missed the required measured SARS-CoV-2 accuracy support for `dev-raptor-02` while retrieving manufacturer claims. Both returned candidates for both no-answer questions; only one of two declared no-answer context quotes was covered at five. These failures remain recorded and reinforce that rank/score does not establish source support or answerability.

The [independent v1 evaluation report](medical-retrieval-evaluation.md) records a **failed medical-quality gate**: held-out mean support coverage was 4.5/7 (0.642857, 64.29%), below 0.75. Complete support for 4/7 answerable questions and 45/45 valid exact anchors passed their respective thresholds. BM25 remains the selected software default; the failed support gate remains visible alongside the operational and synthetic proof.

Parameters, questions, gold, thresholds, selection receipt, and all reported failures remain retained. No tuning against v1 held-out failures is authorized. A future development change requires a prospectively frozen candidate and fresh source-anchored held-out evidence. The three-paper manual pilot does not establish general medical retrieval or clinical quality.

## Experimental v2 evaluation

The [v2 selection receipt](medical-retrieval-selection-v2.json) fixed `bm25_context` for evaluation before the coordinator inspected fresh question content or authorized fresh ranking. The [development results](medical-retrieval-development-v2.json) compare that single frozen candidate with the unchanged BM25 reference on the original development set:

| Development method | Mean support coverage at five | Complete answerable questions at five | Mean reciprocal rank at five |
| --- | --- | --- | --- |
| BM25 reference | 0.857143 | 6/7 | 0.785714 |
| Experimental bm25_context | 1.0 | 7/7 | 0.738095 |

The candidate met the prospective complete-support development gate, while two first-support ranks regressed and mean reciprocal rank decreased. Those regressions remain in the [independent report](medical-retrieval-v2-evaluation.md); complete development support is not evidence of generalization.

The [selected-method-only fresh results](medical-retrieval-held-out-v2.json) retain a **failed v2 medical-quality gate** on twelve questions from three document-disjoint sources:

| Fresh held-out metric | Experimental bm25_context | Frozen requirement |
| --- | --- | --- |
| Mean support coverage at five | 4.5/9 = 0.50 | At least 0.75: failed |
| Complete answerable questions at five | 3/9 | At least 6/9: failed |
| Any-required-quote Hit at five | 8/9 | Descriptive |
| Mean reciprocal rank at five | 0.75 | Descriptive |
| Exact own / scoring-context anchors | 60/60 / 32/32 | All exact: passed |
| No-answer context quotes recovered | 0/6 | Reported separately |
| No-answer queries with nonempty candidates | 3/3 | No answerability or abstention claim |

The answerable denominator is nine; three no-answer requests are reported separately. Finding one required quote can yield a Hit without recovering every required quote or passage. High Hit/MRR and valid source locations therefore coexist with incomplete support. Scoring-context quotations receive no support credit. Project/current-source/scope isolation and unchanged-ledger checks passed, while the quality conditions failed.

BM25 remains the API/CLI default. No tuning, reranking, code/default/source/gold changes or alternate-method fresh comparison followed this failure. The original v1 failure and artifacts remain unchanged. These small agent-authored pilots expose software limits; different source sets and denominators do not support a direct comparative medical-quality claim. Neither the experimental interface nor exact anchors validate clinical entailment, appraisal, answerability, evidence synthesis or cross-report study retrieval.

## Whole-block source-disjoint pilot

The [v3 prospective contract](project-retrieval-v3-milestone.md) froze one granularity change, exact algorithm/provenance behavior, original development data and newly authored medical truth before ranking. Original development retained 7/7 complete answers and identical required-quote ranks for the reference and candidate. The coordinator [selection receipt](medical-retrieval-selection-v3.json) fixed `bm25_context_blocks` before inspecting fresh QA or fresh ranking.

The first held-out setup attempt failed before any query because the gold stores publisher URLs inside acquisition records while the original harness expects a top-level field. A separately [authorized schema repair](medical-retrieval-v3-schema-repair.json) pins a new held-only wrapper and both synthetic test suites. It adds only the three missing URL fields to an in-memory copy of the exact selected manifest. Original source/gold/freeze/code/metric/development/selection bytes remain unchanged; all original evaluation guards execute. The failure has no quality score.

The [first actual fresh result](medical-retrieval-held-out-v3.json), independently reviewed in the [v3 report](medical-retrieval-v3-evaluation.md), passes all six predeclared conditions:

| Measure at five candidates | Observed | Frozen requirement |
| --- | ---: | ---: |
| Answerable questions | 9 | 9 |
| Mean support coverage | 0.8518518518518519 | >=0.75 |
| Complete answers | 6/9 | >=6/9 |
| Valid own anchors | 60/60 | 100% |
| Valid scoring-context anchors | 36/36 | 100% |
| Project / active-source / scope isolation | 100% | 100% |

The trial, cohort and routine imaging sources contain 156 canonical blocks and nine tables. Eight of the nine answerable requests require distinct blocks in every identified sufficient alternative. All nine queries recover at least one required quotation, but three remain incomplete: one has 2/3 required passages and two have 1/2. Mean reciprocal rank is 0.8888888888888888. Every no-answer query returns five candidates, only 1/4 declared context quotations is recovered, and two queries return declared misleading alternatives. This is evidence for a bounded reviewer-facing retrieval gate, with explicit remaining failures; it provides no automatic abstention, clinical validation or cross-pilot superiority claim.

The recorded evaluation used:

```text
python tools/evaluate_medical_retrieval_v3_schema.py --split held-out --selection docs/medical-retrieval-selection-v3.json --output docs/medical-retrieval-held-out-v3.json
```

The checked-in output is immutable and that command refuses to overwrite it. A deliberately separate reproduction needs a new output path; it creates an independent temporary ledger whose UUIDs differ. Compare normalized source/anchor/score/parameter content while retaining each run's actual UUID-bearing hashes. No further ranking or tuning followed the accepted first grade. For project use, select `--method bm25_context_blocks` explicitly and preserve the entire trace. BM25 remains the existing default.
