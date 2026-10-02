# Independent PubMed adapter evaluation

Coordinator commit gate: exported the reviewed Git index into a fresh temporary checkout and ran the full suite with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. Final result: **486 passed**, five existing SWIG warnings, 17.14 seconds. This execution includes the final 28-case independent CLI gate and excludes the five unrelated concurrent retrieval tests/files; it is an actual clean staged-checkout run rather than subtraction from shared-workspace totals. Coordinator reviewed fixture truth, acceptance cases, API/CLI code, and documentation proofs before accepting the milestone.

Evaluator: Evaluation agent. Gates: E3 standalone discovery/capture adapter, E4 verification/ledger integration (I4a), and E4b user-facing CLI (I4b). Source oracle: Retrieval agent's invented responses and hand-computed `tests/fixtures/pubmed/manifest.json`. No medical search was executed, no response was obtained over the network, no existing ledger was changed, and no real sleep or model initialization was permitted.

## Commands and results

| Command | Observed result |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_pubmed_acceptance.py -q` on initial client-only cases | 23 passed, 0.06 s |
| `.venv/bin/python -m pytest tests/test_pubmed_acceptance.py -q` final independent adapter gate | **76 passed**, 0.33 s |
| `.venv/bin/python -m pytest -q` final regression gate | **336 passed**, 5 existing SWIG warnings, 14.09 s |
| `.venv/bin/python -m pytest tests/test_pubmed_integration_acceptance.py -q` E4 independent gate | **69 passed**, 0.76 s |
| `.venv/bin/python -m pytest -q` I4a final regression gate | **450 passed**, 5 existing SWIG warnings, 14.36 s |
| `.venv/bin/python -m pytest tests/test_pubmed_cli_acceptance.py -q` E4b independent CLI gate | **28 passed**, 1.08 s |
| `.venv/bin/python -m pytest -q` I4b initial regression gate | **490 passed**, 5 existing SWIG warnings, 16.77 s; before added secret-bearing recovery exception case |
| `.venv/bin/python -m pytest -q` I4b final regression gate | **491 passed**, 5 existing SWIG warnings, 16.78 s; includes all 28 independent CLI cases |

Full-suite partition: the previously accepted ledger/legacy/concurrent suite had 240 cases; this gate adds 20 implementation unit cases and 76 independent cases. Five concurrent external retrieval cases remain included in the full-suite count and are outside this adapter's ownership. Excluding those gives 331 cases; Evaluation has not rerun a clean staged checkout for this gate.

No evaluation failures occurred and no expectations were relaxed to match operational output. The coordinator's clarified supported date types (`pdat`/`edat`) and month-date format (`YYYY/MM`) were used before the capture tests ran.

I4a adds 29 importer byte-parser cases, 16 implementation integration cases, and 69 independent E4 cases to the earlier 336-case suite, giving 450. Five external retrieval cases remain separate; excluding them gives 445. Evaluation did not execute a clean staged checkout. E4's first run had one evaluator setup failure: record 801 has no DOI, contrary to the initial conflict-fixture assumption. The corrected test constructs a temporary, fully consistent source/combined-byte variant with an invented DOI at record 801, validates its updated hashes, and then tests a conflicting pre-existing DOI. This preserves the requirement to roll back a late conflict after record 803 has been inserted; original R4 files are unchanged. No operational fix or acceptance relaxation was required.

## Independent truth and observed evidence

The fixture oracle's complete search membership is **999999803, 999999801, 999999805, 999999802, 999999804** in that order. Three fetches request partitions of two, two, and one IDs. The first two responses deliberately return records in reversed order. There are four article records and one book record. A cited-reference PMID 999999899 is outside membership. Expected counts are five identified IDs, five fetched records, five unique own PMIDs, and four successful requests total.

| Acceptance condition | Expected | Observed |
| --- | --- | --- |
| Original query/date/sort parameters | Preserve leading/trailing spaces, exact date text, user filters, requested sort; one ESearch with `retstart=0`, `retmax=10000`, `usehistory=y` | Exact match. |
| Search-to-fetch membership | Fetch explicit captured IDs in batches; never page through a second changing search | Exactly one ESearch plus three explicit-ID EFetch calls. |
| Search and response ordering | Restore ID suffixes 803, 801, 805, 802, 804; retain article/book metadata; exclude reference-only 899 | Exact match, including years 2025, 2024, 2024, 2023, 2022, nested article text and collective author. |
| Receipt schema and execution metadata | Frozen fields/version/adapter; UTC start/search/completion values; translated query, warnings, history, exact user filter object | Exact match. Search timestamps were tested using a fixed UTC clock. |
| Durable source bytes | Preserve the exact ESearch bytes and each EFetch batch; hash every response and combined records | Every original byte payload and independently computed SHA-256 matches. |
| Offline replay | Existing importer reads saved combined XML in search order | Five records in exact captured order; book and nested metadata survive. |
| Zero search | One ESearch, no EFetch, empty membership/records, warning/translation preserved, null history | Exact match; `complete=true` describes a valid zero-result capture. |
| Count above 10,000 | Clear failure before fetching, no truncated/partial capture | Rejects 10001 with explicit limit message; one request only. |
| Invalid search count/start/max/history/translation | Reject missing/invalid fields, short/duplicate/bad ID membership, wrong root | All 19 search rejection cases leave no destination/staging. |
| Equal-count wrong fetched set | Two records with one unexpected PMID must fail despite matching count | Rejects missing 801/unexpected 899 before later batches. |
| Fetched membership/data errors | Reject short, repeated, missing/conflicting/invalid own PMID, final-batch substitution, wrong root, malformed/error/entity XML | All tested cases reject with no complete capture. |
| HTTP-200 error bodies | XML ErrorList/ERROR does not become a successful empty search or record set | Rejected; no fetch after search error; no parser retry. |
| Entity declarations and external DTDs | Reject declared entities; never fetch external DTD references | Entity variants reject; valid fixture DTD loads offline with network calls forbidden. |
| Existing destination | Preserve existing file/directory and do not request data | No requests; bytes unchanged. |
| Destination created during capture | Never overwrite another newly created capture | Competing receipt unchanged; staging cleaned. |
| Interrupted fetch | Propagate interruption, remove staging/destination, retain unrelated ledger bytes; retry starts a new capture | KeyboardInterrupt at third call leaves no output; rerun makes all four requests afresh. |
| Standalone dependencies | No settings/dotenv, embedding/vector/model imports or ledger writes | Fresh offline subprocess completes and proves modules absent; ledger sentinel remains unchanged. |

## Client transport evidence

The client tests inject a monotonic fake clock, fake sleep, and scripted transport. Twelve requests per rate variant show adjacent attempts separated by at least 1/3 second without a key or 0.1 second with a key. POST bodies preserve exact query text and add configured tool/email/API key only at transport time; endpoints are restricted to the fixed HTTPS NCBI E-utilities base. Unsupported endpoint/configuration fails before transport.

429, 500, 503, URLError, and TimeoutError retry up to the configured bound. Retry attempts remain throttled and use increasing fallback delays. Permanent 400/401/403/404 failures make one attempt. Retry-After 7 seconds and a fixed HTTP date 9 seconds ahead both delay the next attempt appropriately without real sleeps. Nonempty email/tool, finite positive timeout, and positive integer attempt configuration are validated.

HTTP/transport exceptions deliberately contain the fake secret and contact email; final errors expose neither. A malformed/error XML response containing credentials is not retried and its text is not reflected in the failure. Successful capture through a real `PubMedClient` with injected transport includes credentials in POST bodies while omitting API key/email/tool from the saved receipt and result dictionaries.

## Gate recommendation and limits

E3, E4/I4a, and E4b/I4b are independently green. Complete PubMed captures now have independent API and CLI evidence for membership, durable provenance, offline replay and reconciled identification counts. The coordinator will decide the next roadmap gate; these captured reports still require reviewer screening and study linkage before synthesis.

These tests establish specified software behavior against synthetic responses. They do not measure PubMed search sensitivity, full biomedical coverage, clinical validity, live service compatibility, or authenticated NCBI provenance. Checksums establish internal artifact consistency and are not server signatures. Throttling is per client; shared IP/process coordination is outside this version. Client serialization is visible in the operational lock implementation; concurrent-thread scheduling was not separately load-tested. Deliberate interruptions were exercised during fetch, not every filesystem write. No explicit resume or query segmentation path is evaluated because neither exists in this milestone. Study linkage, full-text acquisition, screening automation, and clinical findings remain outside this gate.

## E4 durable-byte-chain evidence

`tests/test_pubmed_integration_acceptance.py` exercises the public verifier, byte validator, import helper, store, and exporter with 69 independent cases. All tests use temporary files/databases and network/sleep denial.

| Acceptance condition | Expected | Observed |
| --- | --- | --- |
| Complete verified import | Five captured records, exact receipt and six artifact byte payloads, immutable run/occurrences; same keyed replay adds nothing | Exact match; counts 5 identified / 0 duplicate / 5 unique. |
| Durable provenance | Reopen database after deleting the original capture; all source bytes, receipt, hashes, occurrences and counts survive | Complete snapshot unchanged. |
| Exported capture assets | Six manifest entries with run ID, relative name, SHA-256, byte length and export path; all bytes exact; nine baseline plus six capture files | Exact match; 15 named outputs and deterministic repeated export bytes. |
| Portable keyed replay | Same project/key from exported capture after source deletion returns original run/result; original path and history retained | Exact match; no new counts/assets. |
| Project isolation/replay | Same capture/key in another project creates independent five-record run; unknown/cross-project artifact access fails | Exact match. |
| Zero-result durability | Preserve zero search receipt plus search/records/receipt artifacts without invented occurrences | Three assets, 12 named export outputs, zero counts, valid offline verification. |
| Pure byte validation | Parse/hash the supplied byte mapping without file or network reads | File-read methods forbidden; five records validated successfully. |
| Single file snapshot | Read combined XML once, then mutate it; parse/store original read bytes consistently; next verification must fail | One read observed; original bytes and records persisted; later verification rejects mutated file. |
| Hash tampering | Changed search/batch/combined bytes without matching receipt hash fail before ledger mutation | All three cases reject; full ledger snapshots unchanged. |
| Recomputed-hash content tampering | Changing combined title or source-batch title and updating that file's hash cannot hide disagreement with the other source representation | Both variants reject while membership remains five IDs. |
| Strict receipt metadata/JSON | Enforce schema/source/adapter, complete boolean, integer counts, UTC chronology, required fields, query/filter/sort/translation/history/warning agreement; reject duplicates/nonfinite values | All cases reject. |
| Ordered request partition | Exact captured batch partitions and typed search parameters; no reversed/duplicate batch, reordered receipt membership, or boolean retstart | All four variants reject. |
| Artifact/path constraints | Mapping contains exactly required bytes; reject absent/extra/traversal/absolute/backslash paths, declared traversal and unsupported request fields | All variants reject. |
| Directory constraints | Declared files/ancestor directories cannot be symlinks; unrelated notes remain untouched and are omitted from stored assets | Both symlink cases reject; notes case preserves/imports only six required assets. |
| Source/spec/record agreement | Complete execution requires complete bytes and vice versa; spec fields and parsed record payload must match validated sources | Invalid direct imports reject transactionally. |
| Late canonical conflict | DOI disagreement at second captured record rolls back preceding new record, run, occurrences and assets | Complete prior snapshot retained. |
| Artifact/receipt immutability | Changed but valid receipt under used key fails; unkeyed new execution adds a duplicate-only run while retaining old asset bytes | Original run/assets unchanged; new run has 5 identified / 5 duplicate / 0 new. |
| Legacy keyed imports | Reconstructed historical spec/record fingerprint without new fields retries with None/empty execution/artifacts | Four variants return original run; generic artifact mapping empty, history execution null, nine-file export retained with blank execution CSV. |
| Asset read snapshot | Commit a second captured run from another WAL writer after records are read during export | Export retains original one-run/six-asset/count snapshot; next read sees second run and all its assets. |
| Persisted corruption | Corrupt SQLite BLOB or stored digest must block export before output replacement | Both corruptions raise hash error, preserve pre-existing project output and unrelated notes. |
| Credentials | Actual keyed client sends secret only in operational POST; no key in history, SQLite bytes/BLOBs or any exported file | All checks pass. Injected credential fields fail without echoing secret. |

Two narrow SQLite fixtures simulate historical serialized fingerprints and external asset corruption because public ledger methods intentionally cannot modify immutable history/assets. These do not mutate an existing user ledger. The concurrent writer test uses WAL and a wrapped public `list_records` method, with no sleeps or scheduling races. Source-directory mutation is tested through a wrapped `Path.read_bytes` method, not by weakening XML/hash expectations.

Durable verification establishes agreement among saved receipt, source responses, combined records, stored bytes and exported assets. It cannot authenticate an altered set in which an external actor consistently rewrites every original source, receipt and hash; this is the stated unsigned-capture limitation.

## E4b CLI evidence

`tests/test_pubmed_cli_acceptance.py` contributes 28 independent cases. In-process search commands inject actual `PubMedClient` configuration validation with fake transport, clock and sleep. Offline commands run as subprocesses from a different directory with no NCBI credentials. No real medical query is executed.

| Acceptance condition | Observed evidence |
| --- | --- |
| Explicit email/environment precedence and API-key source | Three cases prove option overrides `NCBI_EMAIL`, environment fallback works, and `NCBI_API_KEY` reaches only transport configuration/bodies. |
| Search flags and provenance | Exact query whitespace, date-filter text, sort, requested batch size, captured membership and receipt survive CLI capture, ledger run/occurrences, asset storage and export. Results contain capture/import only after both succeed, with 5 identified / 0 duplicates / 5 unique and 15 export files. |
| Zero result | One ESearch, no fetch, zero records/occurrences, durable complete receipt and three source assets. |
| Ledger-free verification | Default/no DB option, absent DB path and invalid DB parent all verify without constructing ReviewStore. A subprocess with an invalid DB path also succeeds offline. |
| Source deletion and portable replay | Subprocess import/export, delete original capture, verify exported bytes, same-key replay returns original result with no run/count/asset inflation and unchanged original history/path. |
| Pre-request validation | Unknown project, missing/blank email, empty query, partial/invalid/inverted dates, batch 0/201, existing output, and empty/blank import key all fail before transport. Unknown project and invalid key fail before client construction. Ledger snapshots and existing output are preserved. |
| Failed capture | HTTP-200 ESearch error causes no import call, no completed destination, and no ledger change. |
| Capture succeeds but ledger fails | Canonical DOI conflict retains the complete verified capture, rolls back ledger, returns nonzero/clean stdout, and reports capture directory plus a usable `import-pubmed` recovery command. Offline recovery into an independent project adds five records without another search. |
| Secret-bearing recovery exception | An injected import error containing the configured API key is redacted while capture and prior ledger are preserved. This was added after initial green tests because the natural DOI failure does not contain a secret. |
| Project validation before capture read | Unknown project cannot reach the import helper/reader. |
| Generic import snapshot | In inferred/explicit JSON modes, source file changes immediately after its first read; original bytes are parsed, hashed and persisted once, with original raw provenance and no execution/assets. Unsupported extension remains contextual and explicit format still works. |
| Runtime dependency isolation | Fresh CLI import and offline verification load no models, vector store, dotenv or RAG settings; requested DB is not created. |

E4b had no failing expectations or operational defects. The final independent PubMed coverage is 173 cases: E3 76 + E4 69 + E4b 28. Final shared regression is 491 = previous I4a 450 + 13 implementation CLI cases + 28 independent CLI cases. Five external retrieval cases remain included separately; excluding those gives 486, which is arithmetic rather than an Evaluation clean-checkout run. CLI live-service compatibility and shared-IP throttling remain untested; fault handling uses synthetic responses and deterministic injections. All search CLI calls in evaluation used fake transport and synthetic fixtures.
