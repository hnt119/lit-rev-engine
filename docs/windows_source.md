# Windows x64 source beta — setup required

This is the same Next.js/FastAPI local application, with the reviewed Windows
security and launcher boundary. It is source that you set up, not a native
installer or a bundled desktop runtime. Use a fixed local **NTFS** volume and
an ordinary non-administrator account. Windows ARM, network shares, FAT/exFAT,
junction/reparse data paths and a native Windows desktop package are unsupported.
Linux installation remains unverified.

Exact candidate `c27aea059cde4371bed48026b2bcee284c35e09f` passed
[run 40222652682](https://github.com/hnt119/lit-rev-engine/actions/runs/40222652682):
Core production/browser/restart/export/backup checks and actual bounded Qwen
and MedCPT CPU indexing/query/reranking through the production API. Those cases
used two public abstract-only reports and ranked one selected 1,435-character
abstract/two windows; they do not validate full-paper latency or scientific
quality. Earlier 8cf4379/9ed6bc5/dfb8399 failures remain in VALIDATION.md rather
than being relabeled or erased.

The runner label was `windows-2025`; observed OS release was **`2022Server`**,
version **10.0.26100**, architecture AMD64. Do not infer the product OS from the
runner label. A fresh macOS candidate passed separately. Final merged-archive
gates remain pending; their external RELEASE_ACCEPTANCE.json is generated after
the final build. **Physical Windows 11 testing is NOT_RUN.** No qualification
follows from macOS tests or Windows mocks alone.

## Verify the source download

Install Python **3.12** with `venv`/pip, Node.js **24** and pnpm **10.20.0** from
their normal trusted distributions. The PowerShell commands require the Windows
Python launcher: verify `py -3.12 --version`. If `py` is missing, include the
launcher when installing/repairing Python 3.12; do not change execution policy.
The tools must be available in your terminal; setup can also take explicit
`--node` / `--pnpm` executable paths. The app does
not fetch these runtimes or model weights automatically. Do not disable TLS,
SmartScreen, antivirus or PowerShell execution policy to use it.

If pnpm is absent, trusted Node's `npm.cmd install --global pnpm@10.20.0` can
install the pinned tool in your usual per-user npm prefix without elevation.
Use `npm.cmd` / `pnpm.cmd` from PowerShell if a `.ps1` wrapper is blocked;
verify `pnpm.cmd --version`. Do not weaken script policy, install app Python
packages globally, or use an administrator shell as a workaround. A permission
failure should be fixed by selecting a supported own-user tool installation.

Keep the purpose-built ZIP, matching manifest and SHA256SUMS together in the
download directory. GitHub's automatic source ZIP is a different artifact. In
PowerShell, verify both listed files before extracting:

```powershell
Get-Content .\lit-rev-engine-0.3.0-beta.4.SHA256SUMS | ForEach-Object {
    $expected, $name = $_ -split '  ', 2
    if (-not $name -or (Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw 'Release checksum mismatch; do not run this download.'
    }
}
Expand-Archive -LiteralPath .\lit-rev-engine-0.3.0-beta.4.zip -DestinationPath .\litrev-beta4
Set-Location .\litrev-beta4\lit-rev-engine-0.3.0-beta.4
```

Checksums bind these files to the supplied integrity data; they are not a signed
publisher identity or a scientific validity certificate. Use the exact release
and source identity in RELEASE.json, not a guessed/latest download URL.

## Isolated bootstrap, setup and ordinary use

Inside the extracted application directory:

```powershell
py -3.12 -m venv .venv-bootstrap
.\.venv-bootstrap\Scripts\python.exe -m pip install -r requirements-windows-bootstrap.txt
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py setup
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py launch
```

The bootstrap installs `pywin32==312` only in that environment. The app-owned
`.venv-preview` also receives the pinned Windows security dependency. No shell
activation, global pip/pywin32 post-install or execution-policy change is needed.
Missing prerequisites fail before private state opens; there is no permissive
fallback. Setup installs locked dependencies and builds the production UI. It
does not search, call a model, download weights or migrate research.

Both services bind IPv4 loopback. The browser opens only after readiness and
native listener-ownership checks. Host, Origin, session and CSRF checks remain
in force. Inherited hosted settings, provider keys, Python injection and Node
options are stripped. Start with **Saved example · offline**: its 30 public
papers and saved map work with Core lexical and no model/key.

Keep the launch terminal open. Ctrl-C or authenticated `stop` requests the
existing API/frontend cleanup through narrow Windows console-break adapters:

```powershell
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py status
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py stop
```

The launcher waits up to twelve seconds before its owned Job Object terminates
remaining children. A missing-console launch has only that termination fallback;
graceful terminal shutdown was tested separately. The passed baseline runner
already had a console (four console processes); no test-fixture console was
allocated. The disposable fixture can explicitly allocate one only when absent;
that is not hidden production behavior. A kill-on-close Job Object also cleans
up after launcher crashes. No
recorded PID or occupied port is used as a kill target. Choose another port
explicitly if a foreign process owns one; do not delete locks to bypass it.

## Normal Settings and optional private operator file

Use **Research & AI Settings** for ordinary session PubMed and optional
local/OpenAI/DeepSeek configuration. A saved preference makes no external
request. Keys are session-scoped backend memory, GET returns presence only,
and restart requires re-entry. Every generation action still needs explicit
bounded data/cost consent. Paper-provider settings are independent of LLM
selection; core/manual work needs no LLM. No paid validation is implied.

The advanced launch-file route remains optional. It accepts explicit live
contact, pinned new-map configuration and a literal-loopback generation adapter;
it is not the cloud-key route. Read OPTIONAL_FEATURES.md for its exact schema,
allowed endpoints and budgets, but use the **Windows ACL procedure below**
instead of that historical guide's POSIX `chmod` and Unix executable examples.
The sample disables all optional actions.

From this app directory, create a **new** protected operator directory/file
outside the app through the existing platform facade. This does not print or
fetch credentials and refuses to overwrite an existing file:

```powershell
@'
import os
from pathlib import Path
from src.platform_support import private_directory, open_private
folder = private_directory(Path(os.environ["LOCALAPPDATA"]) / "LiteratureReviewEngine-operator")
target = folder / "settings.json"
fd = open_private(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
with os.fdopen(fd, "wb") as stream:
    stream.write(Path("config/local-beta.example.json").read_bytes())
'@ | .\.venv-bootstrap\Scripts\python.exe -
$operatorConfig = Join-Path $env:LOCALAPPDATA 'LiteratureReviewEngine-operator\settings.json'
```

Edit only that private copy using an editor you trust. Never put keys in the app,
Git, browser storage, a Next.js `.env` or a public issue. After editing, reapply
and verify the supported current-user ACL through the same facade; do not use
POSIX mode bits as a Windows security check:

```powershell
@'
import os
from pathlib import Path
from src.platform_support import restrict_path, owned_path
path = Path(os.environ["LOCALAPPDATA"]) / "LiteratureReviewEngine-operator" / "settings.json"
restrict_path(path)
if not owned_path(path, private=True):
    raise SystemExit("Private settings ACL verification failed.")
'@ | .\.venv-bootstrap\Scripts\python.exe -
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py check-config --config "$operatorConfig"
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py launch --config "$operatorConfig"
```

Only the existing facade changes permissions on this own-user private copy; it
does not take ownership of somebody else's files. `check-config` validates
without provider/model calls and rejects unsafe ACLs, paths or unsupported
settings. Saving a cache preference in the UI alone does not activate new-map
computation: that existing opt-in still requires the private launch config,
optional mapping runtime and separately acquired pinned BGE weights.

## Data, replacement and recovery

The stable data directory defaults to `%LOCALAPPDATA%\LiteratureReviewEngine`,
outside the app. Use the same explicit `--data-dir` for launch/status/stop if
you choose another absolute private path. No browser-beta or desktop database
is automatically moved. Current-user SID ownership, protected ACLs, reparse
checks and actual OS locks protect local state. They do not protect against
malware as the same user or privileged administrators.

Stop first, extract an update into a new app folder, repeat bootstrap/setup,
then launch using the same external data directory, browser hostname/profile
and selected ports. Do not copy a venv between app folders or run two versions
against one data directory. Access depends on the retained local session cookie;
a workspace UUID alone is not recovery. Cookies are host-scoped rather than
port-scoped. Clearing cookies, switching profile/hostname or using another
browser can lose access. Independent data folders need separate browser profiles.
There are no cross-device accounts or authenticated multi-user/reviewer claims.

Use the existing stopped backup path only after the controller **and any raw
API processes** have stopped. It reuses bounded archive, SQLite integrity and
exact-manifest validators. The output must be a new file outside the data
parent; backup contents include private access registry material and must stay
private. For example, with the default data path:

```powershell
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py backup --output "$env:USERPROFILE\Desktop\research-backup.tar.gz"
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py restore --archive "$env:USERPROFILE\Desktop\research-backup.tar.gz" --destination "$env:LOCALAPPDATA\LiteratureReviewEngine-restored"
```

Restore verifies into a new sibling directory and never overwrites the original.
Inspect it with an explicit `--data-dir` before deciding what to keep. Back up
browser access state separately under browser/OS privacy controls; the app does
not promise portable cookie recovery. Windows uses flushed files and native
write-through publication, not a claim of identical POSIX directory-fsync or
power-loss semantics. Preserve the only research copy.

## Optional models and actual evidence boundary

For optional retrieval, stop and run setup with `--with-retrieval` using the
bootstrap Python above; then explicitly install/check the selected pinned pack
in Settings or the existing `scripts/retrieval_pack.py`. Setup adds dependencies,
not weights. Do not paste Unix `.venv-preview/bin/...` paths from older guides
into PowerShell; the Windows app environment is `.venv-preview\Scripts`.
Both packs/cache and research data stay outside replaceable application files.
Core and saved maps keep working without them. No default change downloads,
indexes, searches or infers; no provider fallback exists.

Candidate c27aea0 actually passed both Qwen and MedCPT CPU component checks and
bounded production HTTP index/query/rerank cases, including exact-source/cell
return, wrong-paper rejection, replay/export and no automatic human-review
writes. The earlier failed production attempts remain historical; the verified
username prerequisite and later pass are not causal proof of their unknown
loading error. Model computation, frozen profiles and budgets were unchanged.
The demonstrated abstracts are not a clinical/biomedical relevance or quality
benchmark. Apple MPS is not a Windows option. Fresh Windows BGE map fitting,
real generation and live providers remain **NOT_RUN**. Read VALIDATION.md and
the future final RELEASE_ACCEPTANCE.json for exact candidate/final source gates;
no earlier runner qualifies a new archive automatically.

The public-repository standard `windows-2025` job uses read-only repository
permissions. Its authorized optional checks can download only the existing
approved pinned Qwen/MedCPT packs into disposable private cache. It uploads no
models, cookies, database, browser state or native binary. MIT covers owner code;
dependencies, articles, data and models keep their own terms. No native executable
is included or qualified by this source application work.

Implementation references: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex),
[named-pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights),
[pywin32 312](https://pypi.org/project/pywin32/312/).
