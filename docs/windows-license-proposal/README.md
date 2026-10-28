# Inactive Microsoft-component agreement proposal

**Historical scope:** this folder preserves the review draft for the earlier `6381a46f…` installer and checkpoint `d428087`. Its statements about the then-current inactive installer are historical. The owner-authorized Windows experimental release uses [the active NSIS page](../../apps/desktop/windows-license-page.nsh) and [final component terms/route record](../../apps/desktop/notices/windows-distribution/README.md). These preserved draft files are not the shipping agreement.

**Owner review only. Not active, not an accepted agreement, and not publication clearance.** The current application, installer source and private Setup remain unchanged. This proposal does not establish the owner's applicable Windows SDK agreement, the applicable CRT redistribution grant, or acceptance of their distribution/indemnity conditions. It does not ask the owner to change the engine's MIT license.

## Exact existing candidate

- Application source: `8566e225a1c4e8d25de76d984f80fcb346deae79`.
- Setup: `Literature Review Engine Setup 0.3.0-desktop-beta.2.exe`; 195,446,034 bytes; SHA-256 `6381a46f766024078093ef0c46ddf0fecd200197859f0688aa732279bd58491d`.
- Original installed-file manifest: 7,447 entries; SHA-256 `dbbada2784954fc1e737e8ce5bd560911336b485b9c2a279defa0a020aba3fff`.

No existing Setup or payload file is replaced or repackaged by these files. Windows installation, checkbox interaction, silent-mode rejection and execution remain **NOT_RUN**. Host-side compilation tests establish NSIS syntax and included instructions, not observed Windows behavior or legal sufficiency.

## Review files and future contract

`MICROSOFT_COMPONENT_TERMS.txt` is the proposed, non-operative wording. `windows-license-page.nsh` supplies the interaction. `integration.patch` is an **unapplied** patch for the current `apps/desktop/installer.nsi` and `scripts/build_desktop_installers.py`. It does not introduce another builder, frontend or runtime.

If separately approved and activated in a future reviewed build, the small host-only copy hook would produce **`resources/MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt`**, outside the existing, exact 15-file `WINDOWS_DEPENDENCY_NOTICES` closure. Its content is, in order:

1. The complete owner-reviewed Microsoft-component protective text.
2. The complete unchanged `resources/WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rendered.txt`.
3. The complete unchanged `resources/python/LICENSE.txt`, including the Additional Conditions for the Windows binary build.

A UTF-8 byte-order mark and section headings are added; each original input remains a complete unchanged byte sequence. Original `LICENSE.rtf` remains alongside the readable SDK conversion; `REDIST.html`, `SDK.nuspec`, every existing license and all component binaries remain unchanged. The proposed hook checks that all four input files exist as ordinary files, records their sizes and SHA-256 values, and binds the exact displayed/retained file in `DESKTOP_RELEASE.json`. The normal future `INSTALLATION.json` inventory would include that file. NSIS embeds that **same complete file** for review before acceptance. External links or post-install-only notices do not substitute for this pre-install display.

## Proposed interaction

The page follows Welcome and precedes installation. It states that only Microsoft components are covered; original engine MIT, Python, FFmpeg and other independent rights remain separate. Agree starts unchecked and is reset on every page visit. Leaving the page requires reading the actual checkbox state before setting a process-local affirmative flag. The first instruction of the Application section checks that flag before application extraction, temporary runtime extraction, registry changes or shortcuts.

The first installer `.onInit` instruction resets the flag and rejects NSIS silent mode with a nonzero exit code before installer-controlled application, registry or payload writes. This does not claim that NSIS or Windows performs no bootstrap work in temporary storage. There is no command-line acceptance option. Cancel/unchecked state does not authorize installation. The proposal adds no acceptance telemetry, accounts, inference or application settings. It does not change uninstall behavior or existing path/ACL/process/security checks.

The checkbox control identifier is verified against [NSIS 3.13's resource header](https://github.com/kichik/nsis/blob/v313/Source/exehead/resource.h); the SDK's bundled Modern UI 2 license-page macro implements `LicenseForceSelection checkbox`. These are technical mechanisms, not a determination that this wording satisfies every upstream condition.

## Activation remains separate

Review the [redistribution analysis](../windows_redistribution_review.md), applicable upstream route and complete terms first. Approval must resolve the owner's applicable SDK and CRT redistribution positions as well as the protective wording/mechanism. The supplied `RuntimeCpp_2015-2022_ENU.1033` and `BuildTools2024Mar` installation/use terms are not treated as publisher redistribution grants or appended as permission. The complete applicable CRT distribution terms still require owner review; a checkbox cannot supply missing authorization. This draft must not be treated as an agreement already accepted by either owner or recipient. Original engine MIT rights must remain intact; Microsoft-only conditions must not restrict Python itself, FFmpeg's modification/replacement/debugging rights or independently licensed code.

The [free-license/downstream checklist](../windows_license_decisions.md) identifies additional conditional developer and downstream mechanisms. A direct Community route would require its complete applicable text and different obligations to be considered; the current SDK/Python-only display is not automatically a final agreement for that route. Availability of a free grant does not record owner eligibility/acquisition or acceptance. The existing inactive patch is preserved, not activated or relabeled as final licensing clearance.

After explicit approval, a future source-bound build would apply the reviewed patch, retain complete texts, regenerate its own metadata/manifest/checksums, and receive independent static checks. Any Windows checks not performed remain NOT_RUN; this proposal does not authorize a VM or native execution. Do not relabel the current payload with a new application source, overwrite its hashes, or activate the patch implicitly. No Windows release, tag, upload or public download is authorized by this proposal.

## Checks performed for this inactive proposal

- The unapplied patch passes `git apply --check` against its recorded current source. Active installer/builder files remain unchanged.
- The pinned NSIS 3.13 compiler successfully compiled an inert host-side fixture containing the proposal page and guards, with the complete draft, SDK text and Python license available before the choice. No application payload or runtime was rebuilt.
- Actual Windows page interaction, decline/cancel, silent-mode behavior, installation and execution are **NOT_RUN**. Compilation is not acceptance of the draft or evidence that the wording meets every legal condition.
