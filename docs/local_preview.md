# Literature Review Engine — Local beta, setup required

Version: **0.3.0-beta.2** (successor candidate, not yet published). This is a source distribution of the existing
Next.js/FastAPI application. It is not a standalone installer and contains no
Python, Node.js, Docker, model weights, credentials or research workspaces.
The public website demonstration is read-only; the research application runs
on your own computer. Hosted deployment is deferred.

## Requirements and supported platforms

- Python **3.12**, including `venv` and pip.
- Node.js **24**, available on PATH or supplied with `--node`.
- pnpm **10.20.0**, available on PATH or supplied with `--pnpm` during setup.
- A writable application folder, a private per-user data folder and two unused
  loopback ports. Internet access is needed for locked dependency installation.

macOS **26.6.2 arm64 is tested**, with Python 3.12.7 and Node 24.19.0. Fresh
release checks are recorded separately from historical working-tree results;
these checks do not imply testing on all macOS versions. Linux installation is
unverified; Windows is unsupported in this beta because process/control
locking uses POSIX facilities. No Docker or native desktop framework is needed.
Models are optional advanced components, installed and configured separately;
they are not required for saved-example exploration, lexical retrieval, manual
comparison, source inspection or exports.

## Verify and install

Keep the ZIP, matching manifest and `SHA256SUMS` together. Before extraction:

```sh
shasum -a 256 -c lit-rev-engine-0.3.0-beta.2.SHA256SUMS
unzip lit-rev-engine-0.3.0-beta.2.zip
cd lit-rev-engine-0.3.0-beta.2
python3.12 scripts/local_preview.py setup
```

`setup` checks prerequisites, creates `.venv-preview` inside this application
folder, installs the pinned core Python requirements and locked web
dependencies, and builds the production frontend. It does not start a research
session, download models, search papers or migrate data. Missing tools, wrong
versions, failed installations and failed builds produce an actionable error;
resolve that error and rerun setup. Do not disable TLS verification to install.

For tools outside PATH, supply their actual executable paths:

```sh
python3.12 scripts/local_preview.py setup --node /path/to/node --pnpm /path/to/pnpm
```

## Launch and stop

```sh
python3.12 scripts/local_preview.py launch
```

The launcher explicitly selects local mode, starts the API and **production**
Next.js frontend on loopback only, and opens the browser after both readiness
checks succeed. It does not expose an application on your local network.
Keep the terminal open. Press **Ctrl-C** for a controlled stop, or use another
terminal in the application folder:

```sh
python3.12 scripts/local_preview.py status
python3.12 scripts/local_preview.py stop
```

An occupied port or an already running controller is an error. Choose unused
ports explicitly rather than silently attaching to or terminating another app:

```sh
python3.12 scripts/local_preview.py launch --web-port 3088 --api-port 8798 --no-browser
```

Use the exact URL printed by the launcher. Keep the hostname stable when
reopening. The distributed launcher defaults to `localhost` for the browser;
network listeners still bind `127.0.0.1`. `--browser-host 127.0.0.1` is an
explicit alternative, not an account-transfer feature.

Use normal stop or Ctrl-C. Force-killing the controller can leave its server
processes running. Those children retain the data and installation locks, so a
second launch or setup cannot reuse them. The stop command does not kill an
unverified recorded PID when its controller is gone. Close only the confirmed
leftover application processes using your OS process manager, or restart the
computer before relaunching. Do not delete lock files or change ports to bypass
an active instance.

Inherited hosted settings and model/provider credentials are removed from the
child environment. Generation, new map fitting and AI planning are off by
default. All current Track A UI capabilities can be explicitly enabled through
the validated private configuration path described in `OPTIONAL_FEATURES.md`;
use `check-config --config /private/path/settings.json` to inspect availability
without calls, and `launch --config /private/path/settings.json` to apply it.
Optional map dependencies use an explicit `setup --with-maps`; weights and local
LLM serving remain separate. Resource budgets, zero-spend restrictions and
manual review do not change. The public saved example includes previously computed map results;
opening those results does not run a model. To deliberately configure live
PubMed discovery, set your own `NCBI_EMAIL` privately and launch with
`--allow-live`; an optional `NCBI_API_KEY` is forwarded only with that opt-in.
That permits the application's live actions to send queries and your contact
to providers. Do not combine `--allow-live` with `--config`; use the private file
for a combined live/model configuration. Do not put credentials inside the
distribution or website demo.
No live retrieval or inference is needed for the setup/read-only demonstration.

## Data location, reopening and upgrades

Distributed data defaults to a stable private directory outside the app:

- macOS: `~/Library/Application Support/LiteratureReviewEngine`
- Linux, unverified: `$XDG_DATA_HOME/lit-rev-engine`, or
  `~/.local/share/lit-rev-engine` when that variable is absent.

`--data-dir /absolute/private/path` selects another directory. Use the same
selection for launch, status and stop. No existing checkout `.mvp-web-state`,
Streamlit `.mvp-state` or research database is automatically imported or moved.
The developer launcher `scripts/run_web.py` keeps its existing checkout data
default; the distribution wrapper supplies its external default explicitly.

Wait for draft indicators to say **saved** before stopping or closing the tab.
Reloading, reopening the same browser profile and restarting the app preserve
acknowledged drafts, source bindings and submitted revisions. The browser's
session cookie is part of access: it is host-scoped, not port-scoped, and lasts
30 days. Clearing or expiring it, switching browser profiles, alternating
`localhost`/`127.0.0.1`, or running different data folders on the same hostname
can lose access to an older workspace. A workspace ID is not a recovery key.
Changing ports alone does not isolate cookies. Use a separate browser profile
for independent data folders. There are no cross-device accounts or automatic
access recovery in this preview. Keep the whole private data directory and
browser access state protected; never publish credential databases or cookies.

To replace application files, stop the old application, keep its external data
directory intact, extract the new version into a separate folder and run setup
there. Launch it with the same data directory, hostname and browser profile.
Do not delete the data folder or run two application versions against it at the
same time. This checkpoint adds no schema migration; compatibility with future
versions must be reviewed separately. Back up the complete data directory only
while the application is stopped, and keep that copy private.

## Evidence and limitations

The bundled thirty-paper example is a fixed, attributed public capture, not a
new PubMed search, complete systematic-review search or eligibility decision.
Its own README, manifest, source identities and licenses are included. Retrieved
passages, exact quotation locations and human support judgments remain separate.
Manual cell values and judgments require explicit researcher submission.

From an open comparison, choose **Search passages for this comparison** to
prefill its question, or open a cell and choose **Open passage search for this
field** to prefill that field's subquestion. Neither action runs retrieval.
The passage-search page identifies the exact comparison revision and paper
scope; choose a question and 5–30 results, then explicitly retrieve passages.
Its query, result limit and selected run have a separate saved draft from
workspace-wide passage search. Use **Back to comparison** or **Back to cell**
to return. A cell search can reopen an exact result in that cell's existing
source inspector; attaching evidence, editing a value and submitting remain
separate explicit actions. Changed or unsupported bindings are reported rather
than silently replaced with current sources.

The release manifest enumerates the actual packaged files and SHA-256 values.
It excludes developer databases, environment files, caches, browser state,
runtime environments, `node_modules`, frontend build output, tests, private
exports and model weights. Setup recreates build/runtime artifacts locally.
See `CAPABILITIES.md` for the full Track A UI matrix. Historical CLI, Streamlit,
arXiv and Kaggle research tools are separate entry points, and Track B is not
part of this download. A checksum detects changes relative to the supplied manifest; it is not a
cryptographic publisher signature or a scientific validity claim.

See `LICENSE` for the standard MIT grant covering the owner's original engine
code, and `THIRD_PARTY_NOTICES.md` / `DISTRIBUTION_TERMS.md` for preserved article,
model, dependency and research-data boundaries. Beta status does not restrict
MIT rights; private research material is not relicensed by the engine.

Actual results, failed attempts, skips and remaining limitations belong in the
separate local-preview evaluation report. Software checks do not establish
human usefulness, scientific support or clinical validity. No hosted service,
paid inference or release publication is part of this beta preparation.

## Research & AI Settings

Use Research & AI Settings for session-owned PubMed and optional local/OpenAI/DeepSeek generation configuration. Per-search scientific specifications remain beside each query. Saving settings makes no external request. Read SETTINGS.md for fixed endpoints, key lifetime, explicit one-run cost/data consent and limits. Existing private --config launch settings remain supported and are not silently imported or rewritten. Core saved/manual research works without an LLM.
