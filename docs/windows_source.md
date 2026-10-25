# Windows source preview: validation gate

This is the existing local research application, with a Windows security and
launcher boundary. It is setup-required source, not a native installer. Native
Windows execution is **NOT_RUN** until the reviewed Windows CI job passes.
No Windows support claim follows from macOS tests or mocks. Windows ARM,
network shares, FAT/exFAT, junction/reparse data paths and native Windows desktop
packaging are unsupported. Linux installation remains unverified.

The intended validation target is Windows x64, a fixed local NTFS volume, Python
3.12, Node.js 24 and pnpm 10.20.0. Install those prerequisites yourself. The
application does not download runtimes or weights automatically. Use an ordinary
non-administrator account; do not weaken Windows security or script policy.

## Explicit bootstrap and setup

In PowerShell, inside the extracted application directory:

```powershell
py -3.12 -m venv .venv-bootstrap
.\.venv-bootstrap\Scripts\python.exe -m pip install -r requirements-windows-bootstrap.txt
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py setup
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py launch
```

No activation or execution-policy change is needed. The dedicated bootstrap
installs `pywin32==312` only in that environment. The application environment
also receives that Windows-only pin through its requirements. Never run a global
pywin32 post-install operation. Missing native security dependencies produce an
actionable failure before private state is opened; there is no permissive fallback.

Ordinary use runs the production Next.js build and binds both services to IPv4
loopback. The browser opens only after health checks and native listener ownership
checks pass. Host, Origin, session and CSRF checks remain in force. Inherited
hosted settings, provider keys, Python injection and Node options are stripped.
The existing private `--config` route and session-scoped Research & AI Settings
are still explicit opt-ins; saving preferences is not a provider test.

```powershell
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py status
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py stop
```

The launcher stays in its terminal; Ctrl-C or authenticated `stop` requests the
existing API/frontend cleanup through narrow Windows console-break adapters.
The launcher waits up to twelve seconds before the owned Job Object terminates
remaining children. Missing-console launches have only that termination fallback;
graceful shutdown is qualified separately on the terminal path. The disposable
Windows CI fixture explicitly allocates a console when its worker has none and
records that fact. A kill-on-close Job Object also cleans up after launcher
crashes. No recorded PID or occupied port is used as a kill target.
If a foreign process owns a requested port, choose a different port explicitly.

## Data, replacement and recovery

The default stable data directory is `%LOCALAPPDATA%\LiteratureReviewEngine`,
outside the app. `--data-dir` selects a separate absolute private directory;
there is no automatic migration of existing browser-beta or desktop data.
Current-user SID ownership, protected ACLs, reparse checks and real OS file
locks protect local state. These are per-user boundaries, not protection against
malware running as the same user or privileged administrators.

After stopping, extract an update into a new application folder, repeat bootstrap
and setup there, and launch with the same external `--data-dir`, hostname and
ports. Do not copy a virtual environment between app folders. Browser access
depends on its retained local session cookie; a workspace ID alone cannot recover
access. Clearing cookies, changing browser profile/hostname or using another
browser can lose that access. Backups contain private registry credentials and
must be protected as private research material. The app does not offer account
recovery, authenticated multi-user review or access recovery by workspace ID.

The stopped backup path reuses the existing bounded archive, SQLite integrity
and exact-manifest validators. Run it only after all independently started API
processes are stopped; the launcher cannot coordinate arbitrary raw API commands.
The output must be a new file outside the parent of the data directory.

```powershell
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py backup --output "$env:USERPROFILE\Desktop\research-backup.tar.gz"
.\.venv-bootstrap\Scripts\python.exe scripts\local_preview.py restore --archive "$env:USERPROFILE\Desktop\research-backup.tar.gz" --destination "$env:LOCALAPPDATA\LiteratureReviewEngine-restored"
```

Restore publishes a new sibling directory and never overwrites the original.
Inspect that restored copy with an explicit `--data-dir` before deciding what to
keep. Windows publishes flushed files with native write-through moves; no claim
of identical POSIX directory-fsync/power-loss semantics is made.

## Optional models and evidence status

Core research, saved examples and lexical passage retrieval need no model.
`setup --with-retrieval` explicitly installs optional pinned dependencies but
does not install weights. Use the existing `scripts/retrieval_pack.py` install
and check actions explicitly for the two existing pinned packs. Windows validation
targets CPU only; Apple MPS remains an Apple-specific option. Model weights,
credentials and caches are never included in source assets. Cloud generation
remains optional, session-scoped, consented and bounded; no paid validation is
authorized by this portability work.

The reviewed CI job uses the free standard `windows-2025` public-repository x64
runner with read-only repository permissions. It may explicitly download only
the already approved pinned Qwen/MedCPT artifacts into disposable private cache
and run both encoders and rerankers on synthetic text. It uploads no models,
cookies, databases or binaries. Test execution, live providers, real model
execution and research usefulness are separate evidence categories.

Implementation references: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex),
[named-pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights),
[pywin32 312](https://pypi.org/project/pywin32/312/).
Separately installed dependencies retain their upstream terms; engine MIT does
not relicense dependencies, model weights or article data.
