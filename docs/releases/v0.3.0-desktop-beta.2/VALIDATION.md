# Validation — macOS 0.3.0-desktop-beta.2

Release preparation/qualification date: **2026-10-27**. Publication date is the GitHub release timestamp. This record separates historical tests, scoped clean-guest observations and checks not performed.

## Immutable identity

Application source `f1ac1734c829f673ce342174a069fe868dabc786`; historical evaluation `87a2e01e5b26c28fb49f0c6e71b20288508f88cf`. Native build 3002. DMG `lit-rev-engine-0.3.0-desktop-beta.2-macos-arm64.dmg`, 169622385 bytes, SHA-256 `30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8`. The Mac app manifest has 4302 entries and SHA-256 `6ee72875bf5148dd677cf6434d58fa016499356eb1128fc8233294d7267a987a`. No application rebuild or signing mutation is part of this staging operation.

## Recorded software/build evidence

For this source, the historical evaluation records 131 affected Python tests, 216 web tests and 23 Electron security/session/export tests passing, with existing deprecation warnings. Thirty-nine overlapping packaging/notice tests are not 39 additional unique product behaviors. Both source-bound production assemblies completed; Mac CRC and strict deep ad-hoc signature checks passed. The Mac artifact's 4302 entries, 198 bundled native notice-evidence files and 64 canonical web notice packages were hash checked. These are software/integrity checks, not scientific-quality or independent researcher validation.

Direct installed Core/example/entry/source-return/native-export/reopen checks ran on macOS 26.6.2 arm64 on the existing **developer host** with stripped application PATH. Developer tools still existed on that host. Those observations cannot satisfy the new clean-environment browser/quarantine gate. Previous browser-download checks there were inconclusive.

## Clean guest execution — scoped qualification observations

The release owner observed a fresh UTM guest running **macOS 26.6.2, build 25G83, arm64**, after owner-completed Setup Assistant. Node.js and pnpm were not on the guest PATH; `xcode-select` reported no active developer directory. The system `/usr/bin/python3` stub was not invoked. These checks do not assert that every possible developer executable was exhaustively inventoried.

Safari downloaded the exact DMG over a **private VM bridge HTTP** route. The downloaded file was 169622385 bytes and its SHA-256 matched `30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8`. Read-only inspection found its naturally assigned `com.apple.quarantine` value beginning `0083` with Safari as the agent, and a WhereFroms origin for that private transfer. No quarantine attribute was manufactured or removed. No private address or guest identifier is included here. This is not a public HTTPS/CDN download test.

The image mounted in Finder and displayed **Literature Review Engine.app**, an **Applications** shortcut and **INSTALL.txt**. The owner later operated quit/eject/reopen from Applications. The release owner observed the executable path under `/Applications/Literature Review Engine.app`, no mounted image volume (only Macintosh HD listed), and retained application quarantine beginning `01c3` with Safari. These observations precede the QA-induced mutation described below.

The release owner observed the first-launch warning titled **“未打开 Literature Review Engine”**. Its text says Apple cannot verify whether the app contains malware that might harm the Mac or compromise privacy; the available actions were **Done** and **Move to Trash**. This is the expected Apple cannot-verify warning for this unnotarized candidate, not an observed detected-malware or damaged-app message. The owner subsequently reported using official Privacy & Security → Open Anyway and that the app opened. The release owner observed the production app afterward. The later executable-path and image-ejection checks confirmed that scoped installed-copy path. The subsequent QA incident and restored-copy checks are recorded separately below. [Apple’s official procedure](https://support.apple.com/en-us/102445) remains the permitted per-app route; private authentication was not recorded.

The release owner then observed the saved thirty-paper public fixture, explicit full-text preparation of PMID **42051515**, and a **one-paper × three-field Core board**. The Population cell returned **three lexical candidates**. Its exact **Block 18** context and highlighted excerpt were displayed; **I have read this excerpt — use it** was explicitly activated. A software-QA-only note remained **Unassessed / Not assessed**, then passed through **Review entry before saving** and **Save reviewed entry**. The visible acknowledgment was **Saved to comparison. / Saved without a human support judgment.**, with **1 / 3** cells saved and **0 human-supported**. These are software acceptance observations, not fabricated research judgments.

For exports, the native JSON **Save research export** dialog targeted Downloads and **Research export saved** was observed. Later file checks found a **7710-byte CSV** with `mvp.board-table.v1` and the expected provenance/reference columns, and a **34850-byte JSON** audit with candidate runs, rows, source hashes and null/unassessed fields. CSV's first path encountered an OS Downloads-permission prompt; the owner authorized access, but the exact granting action was not independently observed. The subsequent file observation, rather than that permission authorization, establishes the bounded CSV result. The QA JSON parser successfully parsed the export but also caused the installed-copy mutation described below. The exports themselves remain private QA material, not release assets.

After the owner's quit/eject/reopen operation, the release owner observed the same workspace and board, **1 / 3** saved cells and **0 human-supported**, the persisted Population note with current exact references and Unassessed / Not assessed states, and reopening of the saved excerpt's exact highlighted full-text context. This is one same-machine restart cycle; no machine reboot or fresh-copy replacement is inferred.

| Stage | Current status | Actual observation or remaining fact |
| --- | --- | --- |
| Fresh guest OS and architecture | OBSERVED by release owner | macOS 26.6.2, build 25G83, arm64 |
| Owner Setup Assistant and limited developer-tool baseline | OBSERVED by release owner | Setup completed; no Node.js/pnpm on PATH; no active Xcode developer directory; system Python stub not invoked |
| Ordinary Safari download of exact DMG | PASS, private route only | Private VM bridge HTTP; 169622385 bytes; no public CDN claim |
| Download SHA-256 equals the immutable value above | PASS | Exact `30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8` |
| Natural quarantine and origin on downloaded image | OBSERVED by release owner | `0083` / Safari; WhereFroms identifies the private transfer |
| Finder image mount and contents | OBSERVED by release owner | App, Applications shortcut and INSTALL.txt visible |
| Installed executable path | OBSERVED by release owner | Process executable under /Applications/Literature Review Engine.app |
| Retained application quarantine and image ejection | OBSERVED by release owner | 01c3 / Safari retained; image volume absent after owner-operated ejection |
| First-launch trust warning | OBSERVED by release owner | Apple cannot verify the app; Done / Move to Trash; no detected-malware or damaged-app message observed |
| Official per-app approval and opened UI | OWNER-REPORTED / UI OBSERVED | Owner reported Open Anyway and App opened; release owner observed production UI and later Applications executable path |
| Saved-example Core preparation/retrieval/explicit cell save | OBSERVED, scoped software path | Thirty-paper fixture; PMID 42051515 full text; one × three board; three lexical candidates; Block 18; explicit excerpt use; QA-only note; 1 / 3 saved and 0 human-supported |
| Native JSON save and file verification | OBSERVED, scoped pass | Research export saved; 34850-byte audit parsed, with expected source/audit state; diagnostic mutation separately recorded below |
| Native CSV file verification | OBSERVED, scoped pass | 7710-byte CSV, mvp.board-table.v1 and expected provenance/reference columns; first permission-path interruption retained as QA history |
| One quit/eject/reopen and saved-source preservation | OBSERVED, scoped pass | Same workspace/board; 1 / 3 saved; 0 human-supported; current exact reference and source reopened |
| Fresh-copy replacement and strict deep signature verification | OBSERVED PASS | Restored from the same unchanged verified DMG; signature check passed before the normal UI recheck |
| Restored-copy normal UI and board/source preservation | OBSERVED, read-only scoped pass | Same original workspace; one report × three fields; 1 / 3 saved, 0 human-supported; unchanged Population QA note and CURRENT exact references; saved excerpt reopened |
| Restored-copy quarantine after normal UI recheck | OBSERVED PASS | Owner-operated read-only xattr check showed 01c3 / Safari and provenance; no attribute manufacture/removal or security change |

Do not set quarantine merely to manufacture evidence, remove it, disable protections or convert a missing/failed step into a pass. Public HTTPS/download verification remains separate. A normal Open Anyway exception is not Developer ID signing or notarization. Private screenshots and detailed guest evidence remain outside the public staging set.

## QA-induced installed-copy integrity failure and recovery

After the successful workflow and reopening observations, the release owner invoked bundled Python's `json.tool` for an export diagnostic **without `-B`**. That diagnostic parsed JSON but created additional `__pycache__` files inside the installed application. A subsequent code-seal verification **failed** because the installed copy had been modified. This was a QA-induced application-directory write, not a demonstrated defect in the normal application workflow. The frozen normal launcher already starts its backend with `-B` and `PYTHONDONTWRITEBYTECODE=1`; no source fix or rebuild was needed. The failed check is not silently converted into a pass.

The owner replaced the QA application from the same verified, unchanged DMG while preserving external research state. The restored application's **`codesign --verify --deep --strict --verbose=2` passed before the normal UI recheck**. The owner initially reported that the replacement could not open; later the release owner observed the production Workspaces screen with the existing workspace. No cause or timing explanation is inferred from that sequence.

The final read-only recheck observed the same original workspace and one-report × three-field board, **1 / 3 saved and 0 human-supported**, the unchanged Population software-QA note with **Unassessed / Not assessed** states and **CURRENT exact references**, and reopening of **Inspect selected excerpt 1** to the same highlighted retained full text for PMID **42051515**. No new search, preparation, inference, edit or save was performed for that recheck. This establishes the scoped restored-copy board/source result; it is not scientific or independent human validation.

The first restored-copy xattr command was truncated and supplied no usable result; it was not counted as a pass. After the final normal UI recheck, the owner operated a read-only xattr check on the restored Applications copy, and the release owner observed **`com.apple.quarantine` beginning `01c3`, Safari and provenance**. No attribute was manufactured or removed and no security policy was changed. This later direct observation establishes the scoped restored-copy quarantine result. The source-bound DMG and its staged bytes remain unchanged.

## Not claimed

Live PubMed, cloud generation, real generation, new neural execution, scientific/human usefulness and independent review are **NOT_RUN** for this candidate. Optional Qwen/MedCPT runtime/weights are not bundled; the separately tested Mac capsule remains private. No public optional neural download is being offered. No Windows native release, Windows installed test or other Mac hardware/OS qualification is implied.

## Notice scope and public-download boundary

The bounded exact Mac source/notice asset set accompanies this candidate. `MAC_RELEASE_REDISTRIBUTION.md` explains the resolved source-delivery evidence and remaining scope; raw SBOM historical flags remain visible. This is not a blanket legal or codec-patent certification.

Qualification used a private VM bridge HTTP download. Anonymous verification of the final GitHub-hosted downloads is separate from that guest test and has not yet been performed. Use the accompanying release manifest and SHA256SUMS to check the version-specific assets. Publication timing is determined by the GitHub release timestamp, not the qualification date.
