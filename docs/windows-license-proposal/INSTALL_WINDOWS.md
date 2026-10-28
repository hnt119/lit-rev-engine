# Windows beta.2 — private candidate installation guide

**Windows 11 x64 — experimental, unsigned, not tested on Windows. Publication is blocked pending redistribution decisions and separate owner approval.** No public Windows download is available. This is an intended installation sequence, not an observed Windows acceptance result.

## Exact current candidate

- Product: **0.3.0-desktop-beta.2**, build **3002**.
- File: `Literature Review Engine Setup 0.3.0-desktop-beta.2.exe`.
- Size: **195446034 bytes**.
- SHA-256: `6381a46f766024078093ef0c46ddf0fecd200197859f0688aa732279bd58491d`.
- Application source: `8566e225a1c4e8d25de76d984f80fcb346deae79`.
- Existing application/package evaluation: `343467d9e16fe595854d1e312caad6051f5b02dc`.

The license-review work does not rebuild or modify this executable. The [proposed agreement page](README.md) is inactive and is **absent from this candidate**. It must not be described as a completed agreement mechanism.

## Intended installation, after authorization

1. Obtain the exact owner-authorized installer, manifest, notices and checksums. Compare actual bytes with the matching SHA-256 before opening it. A future changed installer requires a new checksum; the hash above cannot identify it.
2. Run Setup on Windows 11 x64 as the ordinary user. No end-user Python, Node, pnpm, Docker or model installation is intended for Core. The installer configuration rejects unsupported operating systems/architectures and does not request elevation.
3. If Windows blocks the unsigned executable, reports damage/malware, or gives an integrity error, stop and report it. Actual Defender, SmartScreen and downloaded-file behavior is **NOT_RUN**. Do not disable protections, remove Mark-of-the-Web or use a security bypass.
4. After installation, open **Literature Review Engine** from Start and choose **Try the saved example**. Optional research/AI setup can be deferred. Core is intended to work without keys or models. Actual installed-app launch, comparison, save and export on Windows are **NOT_RUN**.

If a later approved installer includes the agreement proposal, it would show the Microsoft-component text and full retained SDK/Python texts before an unchecked affirmative choice. Declining cancels; silent setup is rejected. That behavior needs a newly bound installer and its own evidence. Compiling the proposal does not establish upstream rights, user acceptance or legal adequacy.

## License material and data

Current application files are intended at `%LOCALAPPDATA%\Programs\Literature Review Engine\app-0.3.0-desktop-beta.2`. Existing vendor texts are under `resources\WINDOWS_DEPENDENCY_NOTICES\microsoft-sdk-10.0.28000.2270` and `resources\python\LICENSE.txt`. The proposed future displayed/retained file would be `resources\MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt`; it is **not present in the current candidate**.

Original engine code remains [MIT](../../LICENSE). Microsoft components, Python, FFmpeg and other dependencies retain their own grants. See the [two-row owner decision packet](../windows_redistribution_review.md); a notice or checkbox cannot supply missing redistribution permission.

Research/profile state is intended outside program files at `%LOCALAPPDATA%\LiteratureReviewEngineDesktop`, separate from browser-beta and Track B state. No automatic migration is authorized. Uninstall is configured to preserve research by default, but Windows execution/replacement/uninstall/data-preservation checks are **NOT_RUN**. Keep independent private backups. Cookie/profile loss can prevent reopening protected workspaces; CSV/JSON exports are not complete authorization backups.

Optional neural libraries and model weights are separate and not qualified for this Windows candidate. Real models, provider calls and scientific usefulness are **NOT_RUN**. Preserve the published Mac and source-beta releases throughout this private review.
