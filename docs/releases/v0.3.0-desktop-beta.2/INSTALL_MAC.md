# Install on Apple Silicon Mac — 0.3.0-desktop-beta.2

Release preparation/qualification date: **2026-10-27**. Publication date is the GitHub release timestamp. Use this release’s Assets panel for downloads. Scoped observations and limits are recorded in `VALIDATION.md`.

## Download and check

Use the GitHub release page’s **Assets** section. GitHub’s automatic source archives do not contain the installed desktop application. Download `lit-rev-engine-0.3.0-desktop-beta.2-macos-arm64.dmg` plus the final matching manifest/checksums. Expected DMG size: **169622385 bytes**. Expected SHA-256:

```text
30c08636b310f88848bf49d40eed9b6eed8b5bcb84e90fa09ef6a1e84978c0d8
```

Check the hash with a trusted checksum utility. For optional operator verification, macOS's built-in `shasum -a 256` can check the file; the application itself needs no Terminal window or developer runtime for normal use. Stop if size/hash differ, the image is damaged, a signature/integrity check unexpectedly changes, or macOS reports malware. Do not force an altered or malware-blocked copy to run.

## Install and open

1. Open the downloaded DMG and drag **Literature Review Engine.app** to **Applications**.
2. Eject the DMG. Open the installed copy from Applications; running from the image/build folder is not the supported path.
3. This beta is **unnotarized and ad-hoc signed**, not Apple Developer ID signed. If macOS gives its unknown-developer/unnotarized warning, first verify the exact download and decide whether you trust the app. If you choose to proceed, follow [Apple's official per-app procedure](https://support.apple.com/en-us/102445): open **System Settings → Privacy & Security → Open Anyway**, then confirm **Open** when prompted. Enter any required login password privately. If the expected per-app option is unavailable, stop and report the actual result.
4. Preserve quarantine. Do not remove download attributes, disable Gatekeeper/SmartScreen, change global app-trust policy or run a bypass script. A normal per-app approval is not a malware or integrity clearance.
5. No Python/Node/pnpm/Docker setup is needed for Core.

## Current clean-guest evidence

On a fresh macOS 26.6.2 (25G83) arm64 UTM guest, the owner used official Open Anyway and the release owner observed the production Core workflow, an explicit source-linked cell save, native CSV/JSON files and reopening of the same saved entry/source. The executable was observed under `/Applications/Literature Review Engine.app`; the DMG was ejected and Safari quarantine remained. The cell stayed Unassessed / Not assessed, with zero human-supported entries.

A subsequent QA diagnostic ran bundled Python directly without `-B`, creating bytecode cache files inside the installed app; the later code-seal check failed. The normal launcher already supplies `-B` and `PYTHONDONTWRITEBYTECODE=1`. This was a QA-induced mutation, not a demonstrated application defect; the verified original DMG is unchanged.

After replacement from that same image while preserving external state, strict deep signature verification **passed before the normal UI recheck**. The release owner then observed the existing workspace, unchanged saved Population note/judgments and reopening of the same exact source excerpt, without a new search, preparation, inference, edit or save. A subsequent read-only check of the restored app observed retained `01c3` / Safari quarantine and provenance. No download attribute or security policy was changed. These are scoped software qualification observations, not scientific validation. Normal use does not require running bundled Python or modifying application contents. See `VALIDATION.md` for the incident and recovery sequence.

## First useful comparison

Choose **Try the saved example** in the optional welcome flow, or choose setup later and open a workspace. Public saved papers need no API key or model download. Preparation and passage retrieval remain explicit. Open a cell, inspect its exact source, explicitly select evidence, write your interpretation, then review and save the entry. Opening a passage alone does not declare inspection or support. Draft saving and reviewed-entry submission remain separate.

Optional setup is not required for manual research. Qwen/MedCPT libraries and weights are not bundled; the private optional runtime capsule is not supplied here, so this release does not promise a public neural-install path or model readiness. Do not install packages into the application. Local/OpenAI/DeepSeek generation requires separate user configuration and per-action consent; a key or saved model name does not establish compatibility.

## Data, exports and replacement

Research/profile state is external at `~/Library/Application Support/LiteratureReviewEngineDesktop`. Browser-beta, Track B and earlier prototype data are not silently migrated. Export through the native save dialogs and quit normally before replacing app files. Do not delete the data directory as a repair step.

Keep a stopped backup of the complete state, including authorization/browser state as documented by the application. Retaining SQLite files alone is not guaranteed access recovery. Keys entered in Settings are backend-session memory only and must be re-entered after restart. Cookie loss/expiry can lose workspace access; this is not an account-recovery service.

A replacement/update test and an actual browser download are separate observations. Consult `VALIDATION.md`; do not infer a clean-OS pass from tests on the developer's existing Mac.
