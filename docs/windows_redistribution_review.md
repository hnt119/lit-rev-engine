# Windows Microsoft-code redistribution review

**Current candidate:** source `8566e225a1c4e8d25de76d984f80fcb346deae79`; existing Setup **195,446,034 bytes**, SHA-256 `6381a46f766024078093ef0c46ddf0fecd200197859f0688aa732279bd58491d`. The EXE remains unchanged. This is a terms/provenance review and an **inactive owner-review proposal**, not agreement acceptance, Windows execution, legal certification or permission to publish. The earlier `1d1bd96` review is historical; its candidate was not rewritten.

## Exact files and license identity

| Actual payload path | PE version; bytes | SHA-256 |
| --- | --- | --- |
| `d3dcompiler_47.dll` | 10.0.28000.2270; 4,753,864 | `f5c95e919b4ffa1ac71049cd45b9f986d2965e6888395ca2806337985334fa56` |
| `resources/python/vcruntime140.dll` | 14.44.35211.0; 124,544 | `d5e4d9a3e835fa679450145d6a7d94e36573a509317111904d9b3712c30d9066` |
| `resources/python/vcruntime140_1.dll` | 14.44.35211.0; 49,792 | `1f2d41c4aa5db0bc33ebf7b66d72943a817d7ce6cbe880502a9403823633093f` |

The specific SDK package is `Microsoft.Windows.SDK.CPP` **10.0.28000.2270**. Its [versioned NuGet metadata](https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.cpp/10.0.28000.2270/microsoft.windows.sdk.cpp.nuspec) has `requireLicenseAcceptance=true` and points to [WinSDKLicenseURL](https://aka.ms/WinSDKLicenseURL). That retained RTF and the official [SDK license page](https://learn.microsoft.com/en-us/legal/windows-sdk/license) identify the **same** `WIN10SDK.RTM.AUG_2018_en-US` license. The third-party-distribution, protective-terms, copyright and indemnity clauses were compared directly. HTML link labels differ from the RTF's displayed URLs; no byte-identical HTML/RTF claim is made. The legacy Windows10SDK title is preserved, not replaced with a guessed newer license.

The SDK license's §2(a)(i) incorporates its [REDIST list](https://learn.microsoft.com/en-us/legal/windows-sdk/redist), which names the D3D/x64 DLL for Classic Windows apps, subject to validly licensed software and applicable terms. This identifies a **conditional grant**; it does not prove the owner's SDK installation, agreement or authorized downstream route. No mandatory new SDK installation or paid Visual Studio purchase is inferred.

## Two-row owner decision table

| Exact binary / provenance | Applicable license grant | Required downstream terms | Already satisfied | Owner review or acceptance | Publication status |
| --- | --- | --- | --- | --- | --- |
| **D3DCompiler** `d3dcompiler_47.dll` 10.0.28000.2270: Electron45 bytes equal SDK10.0.28000.2270's x64 Redist member; full hashes above. | SDK `WIN10SDK.RTM.AUG_2018_en-US` §2(a)(i) permits listed object code / third-party distribution conditionally. REDIST membership alone is insufficient. | §2(a)(ii–iii): protective distributor/end-user agreement; preserve notices and Microsoft-platform, endorsement, lawful-use and Microsoft-code licensing restrictions. Distributor copyright/functionality/indemnity duties are separate from consumer terms. | Exact archive/member comparison; complete unchanged SDK RTF, readable conversion, NuGet metadata and REDIST retained. | Establish the applicable licensed-SDK or authorized downstream route; personally review applicable SDK obligations, including indemnity; approve adequate component-only wording/mechanism. No agent acceptance. | **BLOCKED** while authorization/conditions remain unresolved. Inactive page supplies no agreement. |
| **Python CRT** `resources/python/{vcruntime140.dll,vcruntime140_1.dll}` 14.44.35211.0: exact pinned Python3.12.15+20261021 archive; full hashes above. | Version-matched [CPython CRT notice](https://raw.githubusercontent.com/python/cpython/v3.12.15/PC/crtlicense.txt) describes conditional downstream redistribution. Runtime/Build Tools install-use EULAs are not publisher redistribution grants. | Agree to adequate protections for Microsoft Distributable Code; preserve notices, lawful/platform use and no false endorsement. Restrictions do not relicense Python, its programs, original MIT code or independent FFmpeg rights. | Both exact DLLs, complete Python LICENSE/CRT conditions and runtime attribution retained. | Establish applicable publisher/downstream Microsoft authorization and review complete applicable terms/protections. PE14.44 does not establish a Visual Studio edition/license. Approve the component-only mechanism; no purchase is presumed. | **BLOCKED** while authorization/protective terms remain unresolved. No unconditional sublicense or compliance claim. |

## CRT route: grants not established by install/use licenses

Two exact official documents from Microsoft's license directory were also reviewed:

- [Visual C++2015–2022 Runtime license](https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx), EULAID `Cpp_2015-2022_ENU.1033`, DOCX SHA-256 `f1e3d56ceb2ad68aae0711b910375009e651ac5530fa0760f0dea6e81e54fae1`. Installation/use is permitted, but its Scope of License restricts sharing/publishing, standalone or combined offerings to others, and transfer. **This is not a publisher redistribution grant.**
- [Visual Studio2022 Diagnostic/Build Tools license](https://visualstudio.microsoft.com/wp-content/uploads/2024/03/Visual-Studio-2022-Diagnostic-Build-Tools-Agent-License_Update-March-2024_EN.docx), EULAID `VS_2022_Tools_2024Mar_ENU.1033`, DOCX SHA-256 `2f66b86a00e8d9833789897ce23d05a4a2dbea370cf39c8c1098dbc17d0e7bdc`. Its specified build/use permissions, including the open-source-dependency exception, do not supply a redistribution grant; Scope of License similarly restricts sharing/publishing, combined offerings and transfer.

Neither document is appended as purported publisher permission. Accepting one is not a proposed solution. Python's exact conditional downstream statement remains relevant, but the applicable Microsoft authorization must be established through the publisher/downstream route or an applicable edition-specific Visual Studio Distributable Code grant. No edition, agreement or owner eligibility follows merely from DLL14.44 or a successful download. No paid purchase is presumed necessary, and none is authorized here.

## Fresh acquisition and byte-comparison evidence

The cached public archives were rehashed and their exact members compared without extraction/execution or installing an SDK:

| Public source archive | Archive SHA-256 | Compared member(s) |
| --- | --- | --- |
| [Electron45.0.0 Windows x64](https://github.com/electron/electron/releases/download/v45.0.0/electron-v45.0.0-win32-x64.zip) | `ae53887a23bb640369c93dbd38c408a2af5c0deb86f2fa76c6c244cb444b7f47` | `d3dcompiler_47.dll` |
| [SDK10.0.28000.2270 NuGet](https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.cpp/10.0.28000.2270/microsoft.windows.sdk.cpp.10.0.28000.2270.nupkg) | `0a4887a64d1b17128f9ffd80032f20debabf943f34eea927aac00cc46cb32879` | `c/Redist/D3D/x64/d3dcompiler_47.dll` |
| [Python3.12.15+20261021 Windows x64](https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.12.15%2B20261021-x86_64-pc-windows-msvc-install_only_stripped.tar.gz) | `aac5d331fc3307343f95928fdbea4583f0d53973d08c7e1d081884fbd229a0e1` | `python/vcruntime140.dll`, `python/vcruntime140_1.dll` |

The package-linked SDK RTF was freshly retrieved and still matches bundled SHA-256 `dd07eb178e00c6bba4148457fc00ff77cd4887eb521d504186fe59c9ec8bbe62`; bundled Python LICENSE.txt remains `886a0ead2d89030ee62dbff52b04e47ab91998341295bb9c56fb952b4e081c7a`. Public acquisition and hash comparison are distinct from installed software, owner agreement and Windows runtime validation. No applicable permission was manufactured by these checks.

## Inactive downstream proposal

Full grants plus a notice prove **retention**, not the agreement expressly required by both routes. The current installer has no acknowledgment page or supplied alternative agreement mechanism. A checkbox is one possible implementation; neither its existence nor a host compile establishes legal adequacy or actual Windows behavior.

[MICROSOFT_COMPONENT_TERMS.txt](windows-license-proposal/MICROSOFT_COMPONENT_TERMS.txt) is a non-operative text for owner review only. The separate [NSIS proposal](windows-license-proposal/README.md) is inactive. A future owner-approved page must provide the **complete SDK license and Python license before the choice**, retain authoritative raw SDK RTF and other notices, require an affirmative decision or abort, and not equate silent execution with consent. A future rebuild/manifest and authorization would be required; the existing EXE is preserved.

Any added restrictions must cover only Microsoft code. They must preserve original MIT code rights, Python's own license, independent open-source portions, and FFmpeg modification/replacement/debugging rights. SDK obligations belonging to the distributor, including its indemnity, are not silently accepted by the agent or transferred wholesale to an application user. No whole-application proprietary EULA or engine-license reselection is proposed.

All existing MIT/Python/Electron/Chromium, FFmpeg source delivery, DXC and other dependency notices remain required. No separate source-delivery condition was identified for these unmodified proprietary DLLs. **Applicable Microsoft redistribution authorization (including the CRT route) and adequate downstream protective terms remain unresolved until actually established; public binary upload stays blocked.**
