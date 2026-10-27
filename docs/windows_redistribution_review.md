# Windows Microsoft-code redistribution review

**Scope:** read-only terms/binary review of the existing private candidate, source `1d1bd96e98673015e4cc294cc3b5b6c922764ebb`. Setup is **197,099,124 bytes**, SHA-256 `42858d5ea8d1a907c913c2b8538f278ecc15b529784aa6ba87c80819b26a0188`. This document does not accept an agreement, add operative terms, qualify publication or claim Windows execution. Successor artifacts require their own bindings.

## Exact Microsoft binaries

| Payload path | PE version; bytes | SHA-256; pinned origin |
| --- | --- | --- |
| `d3dcompiler_47.dll` | 10.0.28000.2270; 4,753,864 | `f5c95e919b4ffa1ac71049cd45b9f986d2965e6888395ca2806337985334fa56`; exact Electron45 bytes and Microsoft SDK10.0.28000.2270 `c/Redist/D3D/x64/d3dcompiler_47.dll` |
| `resources/python/vcruntime140.dll` | 14.44.35211.0; 124,544 | `d5e4d9a3e835fa679450145d6a7d94e36573a509317111904d9b3712c30d9066`; exact pinned Python3.12.15+20261021 archive |
| `resources/python/vcruntime140_1.dll` | 14.44.35211.0; 49,792 | `1f2d41c4aa5db0bc33ebf7b66d72943a817d7ce6cbe880502a9403823633093f`; same exact Python archive |

No `api-ms-*.dll`, `ucrtbase*.dll`, `msvcp*.dll`, `msvcr*.dll` or `concrt*.dll` was distributed in that payload. Their names in PE imports do not make them bundled assets. DXC is a separate Chromium-built dependency with its own retained LLVM/NCSA/third-party notices, not this SDK DLL's licensing route.

## Conditional grants and remaining conditions

| Route and exact clause anchors | Permission/requirements established | Current status and proposed resolution |
| --- | --- | --- |
| **SDK D3DCompiler.** The exact [versioned NuGet metadata](https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.cpp/10.0.28000.2270/microsoft.windows.sdk.cpp.nuspec) links the retained [SDK license](https://aka.ms/WinSDKLicenseURL). Its Distributable Code → REDIST and Third Party Distribution clauses, plus [official REDIST](https://learn.microsoft.com/en-us/legal/windows-sdk/redist), name unmodified D3D/x64 code for Classic Windows applications, subject to a validly licensed SDK and its terms. | A conditional upstream grant exists. Relevant distribution conditions include added primary functionality, unmodified code/notices, protective distributor/end-user terms, the program's copyright notice, indemnity, Microsoft-platform limits, no false endorsement or unlawful use, and no relicensing of Microsoft code under an Excluded License. The full retained terms govern; this row is not a substitute. | Exact binary and accompanying terms/REDIST are retained. Archive correspondence and Electron's MIT license do **not** establish the owner's applicable SDK agreement or downstream permission route. Owner must establish that position and satisfy its conditions; the agent does not accept the SDK agreement or indemnity. No Visual Studio purchase requirement is inferred. |
| **Windows Python CRT.** Bundled Python `LICENSE.txt`, Additional Conditions, lines283–320; independently matched to exact [CPython v3.12.15 PC/crtlicense.txt](https://raw.githubusercontent.com/python/cpython/v3.12.15/PC/crtlicense.txt). | The notice expressly describes compliant downstream Windows-interpreter redistribution subject to Microsoft conditions. It requires distributors/external users to agree to protective terms, preserving notices and avoiding endorsement, non-Microsoft-platform distribution and malicious/unlawful use. It expressly confines these restrictions to Microsoft Distributable Code, excluding Python itself and programs running on it. | Both unchanged CRT DLLs and complete notice are retained. A downstream protective-terms mechanism is not demonstrated by the existing installer. Owner review is needed for the mechanism and applicable conditions. [Microsoft's direct Visual C++ redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files) separately names licensed Visual Studio users; that direct route must not automatically be substituted for the downstream Python route. |

The SDK versioned metadata has `requireLicenseAcceptance=true`. The linked authoritative RTF retains its original Windows10SDK title/EULAID; it has not been rewritten as a new Windows11 agreement.

## Is retaining the full grants plus an explicit notice enough?

**It establishes notice retention, not the required agreement mechanism.** Both retained routes expressly require downstream agreement. The existing installer has welcome/install/finish pages, with no terms acknowledgment; no alternative demonstrated distributor/end-user agreement was supplied. Therefore a notice-only packaging pass cannot resolve this condition. A checkbox is one technical option, not a claim that clickwrap is the only valid mechanism or legally sufficient by itself.

A narrow improvement, **for owner review before implementation**, is a Microsoft-component-only terms/notice step before installation. It would identify these three files and full vendor texts; require an affirmative action or stop; preserve the selected terms after installation; and avoid silently equating a background/silent command with consent. The owner must first approve the applicable route and protective text/mechanism. Installing such a page would not itself prove the owner's SDK agreement.

Any proposed protective text must clearly confine its restrictions to Microsoft code. It must not restrict original engine MIT rights, Python's own grant, FFmpeg modification/replacement/debugging rights, or other components' terms. Do not use a whole-application proprietary EULA or ask the owner to choose the engine license again. No operative agreement text is introduced here.

## Retained files and decision boundary

Keep Python's full license (SHA-256 `886a0ead2d89030ee62dbff52b04e47ab91998341295bb9c56fb952b4e081c7a`) and `WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/{LICENSE.rtf,LICENSE.rendered.txt,REDIST.html,SDK.nuspec}`. Authoritative RTF SHA-256: `dd07eb178e00c6bba4148457fc00ff77cd4887eb521d504186fe59c9ec8bbe62`; readable conversion only aids inspection. All existing MIT, Python, Electron/Chromium, FFmpeg/source, DXC and other dependency notices remain required. No source-delivery requirement was identified for these unmodified proprietary DLLs.

The two outstanding items are **owner applicability of the SDK grant/conditions** and **the downstream Microsoft protective-terms mechanism**. These are concrete conditional-permission questions, not proof that no grant exists or a generic legal-certification demand. If unresolved, keep the Windows executable private. No agreement acceptance, Windows execution, payment, DLL/source mutation or publication occurred in this lane.
