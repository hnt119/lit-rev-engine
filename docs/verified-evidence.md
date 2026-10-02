# Source-anchored findings and verified evidence

The review ledger stores manual findings and appraisal judgments with exact source quotations, immutable revisions, and independent review events. A valid quotation establishes its location in retained source text. A reviewer still decides whether the value, population, outcome, units, analysis, and timepoint follow from that quotation.

An evidence proposal requires a currently full-text-included report, a resolved study association containing the selected study, and that report's active source document. Each proposal has a stable `evidence_id`; its initial and later revisions have separate `id` values. Verification commands take the **revision ID**. Revision commands take the **stable evidence ID** and a complete replacement payload. A revision never inherits verification from an earlier revision.

## Run a synthetic offline demonstration

Run the following blocks in order from the repository root, in one bash or zsh shell using the existing `.venv`. Everything written by this walkthrough stays in a new temporary directory. It imports one invented report and uses the [independent software XML fixtures](../tests/fixtures/evidence/README.md). The six/eight-week declarations and appraisal instrument are invented software data, with no clinical findings or validated clinical appraisal tool.

The small shell helpers invoke the CLI and copy returned UUIDs from saved JSON; they do not infer report or study identity. `--db` stays before each command. The demo directory is retained for inspection.

```sh
set -e
EVIDENCE_PYTHON=".venv/bin/python"
EVIDENCE_DEMO="$(mktemp -d "${TMPDIR:-/tmp}/lit-evidence-demo.XXXXXX")"
EVIDENCE_DB="$EVIDENCE_DEMO/review.sqlite3"
evidence_cli() { "$EVIDENCE_PYTHON" review.py --db "$EVIDENCE_DB" "$@"; }
evidence_id() {
  "$EVIDENCE_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' \
    "$1" "${2:-id}"
}
cp tests/fixtures/evidence/article-v1.xml "$EVIDENCE_DEMO/source-v1.xml"
cp tests/fixtures/evidence/article-v2.xml "$EVIDENCE_DEMO/source-v2.xml"
cat > "$EVIDENCE_DEMO/records.json" <<'JSON'
[{"title":"Invented XML software report","authors":["Software Fixture Author"],"source_id":"EVIDENCE-DEMO-ONLY","raw":{"synthetic":true,"note":"No real publication or clinical findings."}}]
JSON
evidence_cli create --title "Synthetic evidence demonstration" --type scoping \
  --question "Can invented findings retain exact sources and independent verification?" \
  > "$EVIDENCE_DEMO/project-created.json"
EVIDENCE_PROJECT="$(evidence_id "$EVIDENCE_DEMO/project-created.json")"
evidence_cli import "$EVIDENCE_PROJECT" "$EVIDENCE_DEMO/records.json" \
  --source "Invented software fixture" --import-key evidence-demo-v1 \
  > "$EVIDENCE_DEMO/import.json"
evidence_cli records "$EVIDENCE_PROJECT" > "$EVIDENCE_DEMO/records-listed.json"
EVIDENCE_RECORD="$("$EVIDENCE_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))[0]["id"])' "$EVIDENCE_DEMO/records-listed.json")"
```

Screen the report, explicitly record source retrieval, and create its manual study association. Attaching a source alone does not change screening or retrieval status.

```sh
evidence_cli screen "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  --stage title_abstract --decision include --reviewer FixtureScreener \
  --reason "Invented demonstration inclusion."
evidence_cli fulltext "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  --status retrieved --reviewer FixtureScreener --reason "Local synthetic fixture available."
evidence_cli screen "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  --stage full_text --decision include --reviewer FixtureScreener \
  --reason "Invented demonstration full-text inclusion."
evidence_cli study-create "$EVIDENCE_PROJECT" --label "Invented software study alpha" \
  --reviewer FixtureCurator --reason "Manual association for this software fixture only." \
  > "$EVIDENCE_DEMO/study.json"
EVIDENCE_STUDY="$(evidence_id "$EVIDENCE_DEMO/study.json")"
evidence_cli link-studies "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  --study-id "$EVIDENCE_STUDY" --reviewer FixtureLinker \
  --reason "Complete manually declared association set."
evidence_cli attach-source "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  "$EVIDENCE_DEMO/source-v1.xml" --format jats_xml --reviewer Ari \
  --reason "Attach the invented six-week source." --version-label software-fixture-v1 \
  > "$EVIDENCE_DEMO/document-v1.json"
EVIDENCE_DOCUMENT_V1="$(evidence_id "$EVIDENCE_DEMO/document-v1.json")"
evidence_cli source-blocks "$EVIDENCE_PROJECT" "$EVIDENCE_DOCUMENT_V1" \
  > "$EVIDENCE_DEMO/blocks-v1.json"
```

`source-blocks` returns `{"document": metadata, "blocks": [...]}` in one snapshot. Inspect the canonical block text before quoting it. XML locators are structural element paths with available section/table labels; PDF locators use actual page positions; TXT locators use text-block ordinals. The [source guide](source-documents.md) explains each representation.

Prepare two complete proposal payloads. This code enters literal fixture values and validates the hand-selected quotes against the saved canonical blocks. It performs no extraction inference. Offsets are half-open Unicode code-point positions; the input anchor contains exactly `block_id`, `start`, `end`, and `quote`. The ledger adds the original locator and source/block hashes itself.

```sh
"$EVIDENCE_PYTHON" - "$EVIDENCE_DEMO" "$EVIDENCE_STUDY" <<'PY'
import json, sys
from pathlib import Path
folder = Path(sys.argv[1])
snapshot = json.loads((folder / "blocks-v1.json").read_text())
blocks = {block["id"]: block for block in snapshot["blocks"]}
follow_anchor = {
    "block_id": "xml:/article[1]/body[1]/sec[1]/p[2]",
    "start": 21, "end": 44, "quote": "6 weeks, not 12 months.",
}
appraisal_anchor = {
    "block_id": "xml:/article[1]/body[1]/sec[2]/p[1]",
    "start": 58, "end": 98, "quote": "No adverse-event analysis was performed.",
}
for anchor in (follow_anchor, appraisal_anchor):
    assert blocks[anchor["block_id"]]["text"][anchor["start"]:anchor["end"]] == anchor["quote"]
common = {"study_id": sys.argv[2], "document_id": snapshot["document"]["id"]}
finding = {
    **common, "field": "fixture.follow_up", "value": {"duration": 6, "unit": "weeks"},
    "context": {"population": "Invented entries; not patients", "timepoint": "6 weeks",
                "units": "weeks", "notes": "Software fixture only; explicitly not twelve months."},
    "anchor": follow_anchor,
}
appraisal = {
    **common, "kind": "appraisal", "field": "appraisal.fixture.analysis_coverage",
    "value": "Not performed in this fixture",
    "context": {"analysis": "Declared adverse-event analysis coverage",
                "notes": "Arbitrary software-only instrument, not a clinical appraisal tool."},
    "anchor": appraisal_anchor,
    "appraisal": {"instrument": "Software Fixture Appraisal", "instrument_version": "0.1-synthetic",
                  "domain": "Declared analysis coverage"},
}
for filename, payload in (("finding-v1.json", finding), ("appraisal-v1.json", appraisal)):
    (folder / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
PY
evidence_cli propose-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  --payload "$EVIDENCE_DEMO/finding-v1.json" --reviewer Ari \
  --reason "Enter the literal invented six-week declaration." > "$EVIDENCE_DEMO/finding-created.json"
evidence_cli propose-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  --payload "$EVIDENCE_DEMO/appraisal-v1.json" --reviewer Ari \
  --reason "Enter an arbitrary named software appraisal and its supporting declaration." \
  > "$EVIDENCE_DEMO/appraisal-created.json"
EVIDENCE_FINDING="$(evidence_id "$EVIDENCE_DEMO/finding-created.json" evidence_id)"
EVIDENCE_FINDING_REV1="$(evidence_id "$EVIDENCE_DEMO/finding-created.json")"
EVIDENCE_APPRAISAL="$(evidence_id "$EVIDENCE_DEMO/appraisal-created.json" evidence_id)"
EVIDENCE_APPRAISAL_REV1="$(evidence_id "$EVIDENCE_DEMO/appraisal-created.json")"
evidence_cli evidence "$EVIDENCE_PROJECT" > "$EVIDENCE_DEMO/proposed.json"
evidence_cli evidence "$EVIDENCE_PROJECT" --verified-only > "$EVIDENCE_DEMO/verified-proposals.json"
```

Expected: two `proposed` rows and an empty verified-only list. Reviewer/reason come from CLI flags. Payloads cannot override them. The required payload keys are `study_id`, `document_id`, `field`, `value`, `context`, and `anchor`; proposal-only `kind` defaults to `finding`. Appraisals require a nonempty judgment string and the exact named instrument/version/domain object. Context permits only `population`, `comparison`, `outcome`, `timepoint`, `analysis`, `units`, and `notes`. Strict JSON rejects unknown/duplicate keys and nonfinite values.

Have a distinct reviewer check each current revision. The current author cannot confirm, reject, or adjudicate their own revision. Reviewer names are declared strings, not authenticated user accounts.

```sh
evidence_cli review-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_FINDING_REV1" \
  --decision confirm --reviewer Bo --reason "Checked six weeks and the explicitly negated twelve-month context."
evidence_cli review-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_APPRAISAL_REV1" \
  --decision confirm --reviewer Bo --reason "Checked the quotation and preserved the arbitrary instrument inputs."
evidence_cli evidence "$EVIDENCE_PROJECT" --verified-only > "$EVIDENCE_DEMO/verified-v1.json"
```

Expected: two current confirmed rows. To exercise disagreement, add a scripted rejection of the finding, then explicitly adjudicate it. The appraisal stays confirmed. No majority vote or overall appraisal score is computed.

```sh
evidence_cli review-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_FINDING_REV1" \
  --decision reject --reviewer Cy --reason "Scripted synthetic disagreement to exercise conflict handling."
evidence_cli evidence "$EVIDENCE_PROJECT" > "$EVIDENCE_DEMO/conflict.json"
evidence_cli evidence "$EVIDENCE_PROJECT" --verified-only > "$EVIDENCE_DEMO/verified-conflict.json"
evidence_cli adjudicate-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_FINDING_REV1" \
  --decision confirm --reviewer Dee --reason "Resolve this fixture disagreement using the literal six-week source."
evidence_cli evidence "$EVIDENCE_PROJECT" --verified-only > "$EVIDENCE_DEMO/verified-adjudicated.json"
```

Expected: the conflicting finding temporarily leaves verified-only output, then returns after adjudication. Adjudication requires an existing review. Any later review of that revision invalidates its adjudication and uses the latest vote per reviewer again; old events remain retained.

Attach the second immutable source, whose follow-up changes to eight weeks. Both old proposals become `stale_source`, including the appraisal whose quoted sentence happens to remain identical. Repeating an attachment also creates a new version when its bytes are unchanged.

```sh
evidence_cli attach-source "$EVIDENCE_PROJECT" "$EVIDENCE_RECORD" \
  "$EVIDENCE_DEMO/source-v2.xml" --format jats_xml --reviewer Ari \
  --reason "Explicit invented source replacement changes six to eight weeks." \
  --version-label software-fixture-v2 > "$EVIDENCE_DEMO/document-v2.json"
EVIDENCE_DOCUMENT_V2="$(evidence_id "$EVIDENCE_DEMO/document-v2.json")"
evidence_cli source-blocks "$EVIDENCE_PROJECT" "$EVIDENCE_DOCUMENT_V2" > "$EVIDENCE_DEMO/blocks-v2.json"
evidence_cli evidence "$EVIDENCE_PROJECT" > "$EVIDENCE_DEMO/stale.json"
evidence_cli evidence "$EVIDENCE_PROJECT" --verified-only > "$EVIDENCE_DEMO/verified-stale.json"
```

Expected: two stale-source rows, with their previous verification states/history visible, and no verified-only rows. Supply complete replacements anchored to the new document. Revision payloads omit `kind`; report, evidence identity, reviewer, and reason cannot be overridden through JSON.

```sh
"$EVIDENCE_PYTHON" - "$EVIDENCE_DEMO" <<'PY'
import json, sys
from pathlib import Path
folder = Path(sys.argv[1])
snapshot = json.loads((folder / "blocks-v2.json").read_text())
blocks = {block["id"]: block for block in snapshot["blocks"]}
for name in ("finding", "appraisal"):
    payload = json.loads((folder / f"{name}-v1.json").read_text())
    payload.pop("kind", None)
    payload["document_id"] = snapshot["document"]["id"]
    if name == "finding":
        payload["value"] = {"duration": 8, "unit": "weeks"}
        payload["context"]["timepoint"] = "8 weeks"
        payload["context"]["notes"] = "Complete replacement checked against the invented eight-week source."
        payload["anchor"]["quote"] = "8 weeks, not 12 months."
    anchor = payload["anchor"]
    assert blocks[anchor["block_id"]]["text"][anchor["start"]:anchor["end"]] == anchor["quote"]
    (folder / f"{name}-v2.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
PY
evidence_cli revise-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_FINDING" \
  --payload "$EVIDENCE_DEMO/finding-v2.json" --reviewer Ari \
  --reason "Replace the entire finding payload for the active eight-week source." \
  > "$EVIDENCE_DEMO/finding-revised.json"
evidence_cli revise-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_APPRAISAL" \
  --payload "$EVIDENCE_DEMO/appraisal-v2.json" --reviewer Ari \
  --reason "Re-anchor the complete appraisal to the new source identity." \
  > "$EVIDENCE_DEMO/appraisal-revised.json"
EVIDENCE_FINDING_REV2="$(evidence_id "$EVIDENCE_DEMO/finding-revised.json")"
EVIDENCE_APPRAISAL_REV2="$(evidence_id "$EVIDENCE_DEMO/appraisal-revised.json")"
evidence_cli evidence "$EVIDENCE_PROJECT" --verified-only > "$EVIDENCE_DEMO/verified-new-proposals.json"
evidence_cli review-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_FINDING_REV2" \
  --decision confirm --reviewer Bo --reason "Independently checked eight weeks against the active source and complete context."
evidence_cli review-evidence "$EVIDENCE_PROJECT" "$EVIDENCE_APPRAISAL_REV2" \
  --decision confirm --reviewer Bo --reason "Independently checked the new document and retained instrument/version/domain/judgment."
```

Expected: revised proposals initially produce no verified-only rows; their new confirmations restore two. The stable evidence IDs are unchanged, the current revision numbers are both 2, and earlier revisions/reviews remain auditable.

Delete only the copied temporary input sources, then reopen the ledger through further CLI calls. Inspect both document versions and export a snapshot containing retained sources and verified evidence.

```sh
rm "$EVIDENCE_DEMO/source-v1.xml" "$EVIDENCE_DEMO/source-v2.xml"
evidence_cli documents "$EVIDENCE_PROJECT" --record-id "$EVIDENCE_RECORD" > "$EVIDENCE_DEMO/documents.json"
evidence_cli source-blocks "$EVIDENCE_PROJECT" "$EVIDENCE_DOCUMENT_V1" > "$EVIDENCE_DEMO/retained-v1.json"
evidence_cli evidence-history "$EVIDENCE_PROJECT" > "$EVIDENCE_DEMO/evidence-history.json"
evidence_cli evidence-history "$EVIDENCE_PROJECT" --evidence-id "$EVIDENCE_FINDING" \
  > "$EVIDENCE_DEMO/finding-history.json"
evidence_cli counts "$EVIDENCE_PROJECT" > "$EVIDENCE_DEMO/counts.json"
evidence_cli export "$EVIDENCE_PROJECT" "$EVIDENCE_DEMO/export" > "$EVIDENCE_DEMO/export-result.json"
"$EVIDENCE_PYTHON" - "$EVIDENCE_DEMO" <<'PY'
import hashlib, json, sys
from pathlib import Path
folder = Path(sys.argv[1])
read = lambda name: json.loads((folder / name).read_text())
assert len(read("proposed.json")) == 2 and read("verified-proposals.json") == []
assert len(read("verified-v1.json")) == 2
assert {row["state"] for row in read("conflict.json")} == {"conflict", "confirmed"}
assert len(read("verified-conflict.json")) == 1 and len(read("verified-adjudicated.json")) == 2
assert {row["state"] for row in read("stale.json")} == {"stale_source"}
assert read("verified-stale.json") == read("verified-new-proposals.json") == []
history = read("evidence-history.json")
assert set(history) == {"revisions", "reviews"}
assert len(history["revisions"]) == 4 and len(history["reviews"]) == 6
assert len(read("finding-history.json")["revisions"]) == 2
documents = read("documents.json")
assert len(documents) == 2 and [doc["active"] for doc in documents] == [False, True]
assert set(read("retained-v1.json")) == {"document", "blocks"}
project = read("export/project.json")
verified = read("export/verified_evidence.json")
assert verified == project["verified_evidence"] and len(verified) == 2
current = {row["current_revision"]["kind"]: row for row in verified}
assert all(row["verified"] and row["state"] == "confirmed" for row in verified)
assert all(row["current_revision"]["revision"] == 2 for row in verified)
assert current["finding"]["current_revision"]["value"] == {"duration": 8, "unit": "weeks"}
assert current["appraisal"]["current_revision"]["appraisal"] == {
    "instrument": "Software Fixture Appraisal", "instrument_version": "0.1-synthetic",
    "domain": "Declared analysis coverage",
}
assert len(project["evidence_revisions"]) == 4 and len(project["evidence_reviews"]) == 6
assert project["counts"]["reports_included"] == project["counts"]["included_studies"] == 1
for artifact in project["document_artifacts"]:
    content = (folder / "export" / artifact["export_file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    assert len(content) == artifact["size_bytes"]
print("PASS: 1 included report / 1 study; 2 retained source versions; 4 revisions / 6 reviews; 2 current verified rows; exact source artifacts survive input deletion.")
print("Inspect temporary demonstration:", folder)
PY
```

## Current state, audit history, and exports

`evidence` returns current rows with `current_revision`, `verification_state`, `dependency_issues`, `state`, `verified`, and the active verification event IDs. `evidence-history` returns `{"revisions": [...], "reviews": [...]}` in one snapshot, optionally filtered by stable evidence ID. All votes, superseded revisions, declared identities, reasons, timestamps, exact quotations, locators, and hashes remain available.

Dependency issues are ordered `stale_source`, `source_identity_conflict`, `ineligible_report`, `unresolved_linkage`, and `study_not_linked`. The first issue is the current state; otherwise the state is `proposed`, `confirmed`, `rejected`, or `conflict`. A report's later canonical DOI/PMID enrichment can expose a contradiction with retained own-source identifiers. Such a source cannot supply verified evidence. Restoring the same screening eligibility and requested study association can restore an unchanged current confirmation; replacing the document requires a new anchored revision and independent check.

The usual project export adds current `evidence`, append-only `evidence_revisions`/`evidence_reviews`, and current `verified_evidence` to `project.json`. It adds corresponding CSV files plus `verified_evidence.json`. JSON preserves nested payloads exactly; CSV flattens current revisions and uses formula-safe text. All evidence, counts, linkage, source metadata/blocks, and exact source artifacts come from the same SQLite snapshot. Unchanged exports are deterministic. Reconciled report/study counts do not imply that every included study has verified findings.

Only current confirmed revisions with valid source/identity/eligibility/linkage dependencies enter verified output. Unsupported values can pass quote-location validation and should receive a reasoned reviewer rejection. The arbitrary appraisal tool in this demo is preserved as entered; the engine neither selects a clinical instrument nor computes an overall quality score. See the [frozen milestone contract](evidence-milestone.md) for accepted validation and provenance boundaries.

## Python API

Use `ReviewStore` with actual project/report/study/document UUIDs. The same source and evidence APIs work offline and retain source bytes in SQLite; their reads do not require the original files.

| Method | Purpose |
| --- | --- |
| `attach_document(project_id, record_id, content, format, reviewer, reason, *, filename=None, source_url="", version_label="")` | Create a new immutable active source version from one byte snapshot. |
| `get_source_blocks(project_id, document_id)` / `get_document_bytes(project_id, document_id)` | Return integrity-checked canonical blocks / exact retained bytes. |
| `propose_evidence(project_id, record_id, study_id, document_id, field, value, context, anchor, reviewer, reason, *, kind="finding", appraisal=None)` | Create stable evidence plus its initial immutable revision. |
| `revise_evidence(project_id, evidence_id, study_id, document_id, field, value, context, anchor, reviewer, reason, *, appraisal=None)` | Append a complete replacement revision, preserving report/kind and resetting verification. |
| `review_evidence(project_id, revision_id, decision, reviewer, reason)` | Independently confirm or reject the exact current revision. |
| `adjudicate_evidence(project_id, revision_id, decision, reviewer, reason)` | Resolve existing reviews explicitly; a later review invalidates adjudication. |
| `list_evidence(project_id, record_id=None, *, verified_only=False)` | Read current rows and dependency/verification state. |
| `list_evidence_revisions(project_id, evidence_id=None)` / `list_evidence_reviews(project_id, evidence_id=None)` | Read immutable proposal / verification history. |

An API caller needing several related reads in one snapshot should use the existing CLI snapshot commands or a project export. Hashes detect accidental changes to stored representations; the local unsigned ledger does not authenticate declared reviewer names or an external actor consistently rewriting data and hashes.
