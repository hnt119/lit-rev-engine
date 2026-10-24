# Local protocol-review pilot

This is the next research checkpoint, separate from the frozen
`0.3.0-local-preview.2` distribution at `cb98e3e`. No release archive was rebuilt,
license selected, provider enabled or hosted deployment changed. Pilot source is maintained separately on `codex/protocol-review-pilot`; it is
not included in the frozen release archive.

For source-checkout use, select the existing Python environment containing the
locked FastAPI/web requirements and Node/pnpm from the local setup guide. Build
with `pnpm --dir apps/web build`, then run `python scripts/run_web.py
--production --node /your/installed/node --data-dir /your/new/private/pilot-data
--api-port 8811 --web-port 3101 --browser-host localhost`. Use a **new** private
data directory, keep it outside replaceable application files, and stop with
Ctrl-C. These are unreleased source-checkout instructions, not a new preview
installer or permission to replace the frozen ZIP. Live/model features were
disabled in evaluation; no live capture or model is needed for this workflow.

## Start with an isolated project

In the existing local application, enter a question and choose **Start an
isolated review pilot**. On the Review pilot page, supply a title, a consistent
self-declared reviewer label, and a reason for the protocol record. Keep purpose
**Research pilot** for actual work. Use **Software usability sample** only for
explicitly scripted tests that are not human eligibility judgments.

Record the protocol reference/version, eligibility, search coverage, outcomes,
appraisal procedure and unresolved choices. **Create isolated review project**
stores the first version in the existing `ReviewStore`. Every subsequent save
appends a protocol revision. Unresolved choices are not silently filled; real
research screening is blocked until the protocol is explicitly declared ready.
The software does not assess whether a declared protocol is methodologically
suitable. Version changes do not erase previous decisions. Old decisions need
explicit re-review under the new protocol before another comparison handoff.

Known topic preferences are Asian-origin women, Southeast Asia preferred, and
gut microbiome in relation to reproductive longevity, healthy aging,
gynecological disease and diet/exposome. Exact age, mixed-population, design,
outcome, language/date/database/search and appraisal choices still need the
team's decision. The proposed sole reviewer is not a second independent reviewer.

## Intake the library, not just a preview

The page offers three distinct intake paths:

1. **Approved 30-record usability sample:** every source in the existing fixed
   public manifest, in manifest order. This is a rights/identity-filtered Europe
   PMC subset: reported 194, returned metadata 100, retained 30. All supplied
   records are imported, but it is **not a complete query capture**. Original
   public manifest/candidate/metadata assets and the derived input are retained.
2. **Supplied bibliography file:** UTF-8 JSON, RIS or PubMed XML. All parsed
   occurrences and exact supplied bytes are retained. A bare XML export is not
   promoted to a complete capture. Browser input limit is 8 MiB. Unsupported or
   malformed input fails atomically; no partial library is silently accepted.
3. **Existing complete PubMed capture:** select the original capture folder
   containing `receipt.json`, `search.xml`, `records.xml` and `batches/`.
   Membership, source bytes and receipt must pass the existing verifier before
   import. No live query executes on this page. The current browser form supports
   10 MiB before base64 encoding / 100 artifacts; its request cap is 16 MiB.

The complete PubMed capture implementation retains its 10,000-match ceiling and
has no automatic segmentation/resume. See [pubmed-search.md](pubmed-search.md)
for deliberate live capture with the existing CLI and an explicitly supplied
contact. Larger saved inputs require a separately supported CLI/intake workflow;
the standalone CLI does not automatically attach a capture to this owned browser
project or create pilot-specific bindings. Never split a complete capture and
call its pieces complete. These byte/transport
limits do not impose a 30-record review limit. The library is paged independently
of the 30-source comparison working subset.

Repeated imports retain duplicate occurrences under the existing conservative
DOI/PMID identity rules. Counts distinguish occurrences, canonical records,
reports and studies. A report match is not evidence of shared study identity.

## Screen and inspect explicitly

Select a report in **Human screening**, read its retained abstract, choose a
stage/decision and enter the reason above. **Record my screening decision** is
the only decision action. All original events remain in history; a later action
under the same reviewer label becomes that label's current decision. Other
labels may produce unresolved conflicts; labels are not authenticated people.

Attaching a source, declaring retrieval status, recording a full-text decision
and adding comparison evidence are separate actions. Use **Attach matching
approved public full text** only for a record with a matching approved source,
or supply permitted JATS XML with attribution and permission. The first bridge
supports JATS with its own PMCID and embedded CC BY/CC0 permission recognized by
the existing parser. Arbitrary TXT/PDF full-text handoff is unsupported and fails
explicitly. Permissions are recorded, not legally certified by this software.

**Retain abstract-only coverage** deliberately keeps the exact retained abstract.
It does not mean full text is absent. Abstract-only coverage cannot establish
retrieved full text. Full-text decisions require title/abstract inclusion,
retrieved status and an attached current full-text source. Opening source blocks
does not record inspection, eligibility or verification. The actual reading and
judgment remain the researcher's responsibility.

The existing ledger intentionally cannot reopen title/abstract inclusion after
retrieval activity, or downgrade a retrieved full-text status. The interface
reports these restrictions; it does not rewrite history to bypass them.

## Hand off an exact working subset

Choose one exact current source version per selected report. The server checks
project/report ownership, protocol decisions, source version, bytes and canonical
block hashes. Excluded/conflicting full-text reports and stale bindings fail.
Pending/uncertain full-text reports and abstract-only sources require an explicit
provisional-working-material acknowledgment. Selection never sets eligibility.

**Create comparison from selected exact sources** publishes an immutable
collection/preparation through existing MVP services, records the cross-ledger
mapping and opens the existing comparison board. Per-cell passage retrieval,
exact inspection, manual values, support judgments, submission, revisions and
exports use the existing workflow unchanged. No model or narrative generation
is needed. The handoff receipt retains the exact protocol, decisions and source
bindings. Later protocol/source changes do not rewrite historical comparisons.

Completed exact retries return the retained receipt, including after source
replacement. Caught publication failures retain phases and partial object IDs.
The page shows incomplete handoffs instead of presenting them as completed.
Cross-store publication has no distributed atomic rollback. Hard-process-crash
reconciliation is not demonstrated by this pilot: preserve the original request
and retained service receipts, and do not retry blindly with changed inputs.

## Reconcile, export and reopen

The displayed counts are authoritative `ReviewStore` ledger arithmetic, including
pending, uncertain and conflict partitions. A separate protocol-alignment notice
identifies records requiring re-review after protocol changes. Reconciled totals
are not proof of completed screening, comprehensive search or clinical validity.
`included_studies` remains null until explicit report/study associations are
complete. This page does not invent one study per report; existing CLI study
linkage remains available, without a new web linkage editor.

**Download retained review audit ZIP** includes the original ledger export plus
versioned protocol/event bindings, exact intake assets, source metadata, handoff
receipts and unchanged comparison CSV/JSON exports. Original project protocol
fields remain the initial snapshot for legacy compatibility; the current
version is in `pilot/pilot.json`. This is an audit export, not a database restore
command. Keep it private when it contains real research sources or notes.

Drafts use the existing server CAS and navigation barriers. Wait for **saved**.
A conflict keeps edits and requires explicitly reloading/reviewing current
heads; it does not overwrite another tab. Selected local file objects and
permission-form inputs are transient; unfinished files block navigation and
cannot be restored after browser refresh. Import them or explicitly discard them.
Use the same browser profile and hostname on reopening. Existing session-cookie
expiry/loss and access-recovery limitations still apply.

Data uses a new private `ReviewStore` project file under the application's
selected external data root, in `review-pilots/`. No original ledger is imported,
migrated or replaced. There is one review authority per isolated project; the
comparison copy is working material, not another screening database.

## Evidence status

See [integration scope](protocol_pilot_integration.md) and
[evaluation report](protocol_pilot_evaluation.md). Software-QA actions on the
disclosed 30-record set are not a real human usability study, completed systematic
review, independent retrieval-accuracy benchmark, dual review or medical result.
An actual sole-reviewer session and methodological protocol approval remain
separate human work.
