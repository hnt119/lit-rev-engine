# Single-instance hosted MVP

Baseline: `codex/mvp-v0-3` at `4aa28790c25e419b78be70f57ffebd690a391ba1`.
This prepares an invite-only production package. No hosted service, paid resource,
DNS change, research-data upload or portfolio release has been performed.
Executed checks and limitations are recorded in [deployment evaluation](deployment_evaluation.md).

## Topology and release boundaries

```mermaid
flowchart LR
  P[Existing GitHub Pages portfolio] -. verified link only .-> I[Managed Render HTTPS ingress]
  I --> N[Production Next.js :PORT]
  N --> F[FastAPI on 127.0.0.1:8765]
  F --> S[Existing MVP services and preparation worker]
  S --> D[Private mounted /var/data/litrev]
```

One service, one replica, one provider-owning API process and the existing
in-process preparation worker. The public listener binds `0.0.0.0:$PORT`.
FastAPI has no published container port. The supervisor owns both process groups,
reaps children, stops the sibling after an unexpected exit and holds an exclusive
disk lock through shutdown. It runs an existing Next production build, never
`next dev`, model installation or provider discovery during startup.

The portfolio remains GitHub Pages. The separate Vercel backup is untouched.
The [portfolio handoff](deployment_portfolio_handoff.md) identifies the existing
article and the gate for adding a verified application link; no URL is invented.

## Build and runtime configuration

The Dockerfile builds from the repository root, including the shared Streamlit
theme tokens. Node and Python base images use exact versions and multi-architecture
manifest digests. JavaScript uses the frozen pnpm lock. `requirements-hosted.txt`
pins only the HTTP/runtime dependencies; Streamlit, Torch and embedding weights
are absent. Normal package installation needs network access; no inference or
literature-provider calls are part of the build.

```sh
docker build --tag litrev-hosted:local .
```

`.dockerignore` denies the build context by default. Only application code,
production scripts, locked dependencies, shared theme and the attributed public
30-paper example are allowed. Local `.env`, registries/databases, research data,
exports, `.git`, model caches, virtual environments, host `node_modules` and
`.next` do not enter the image. Do not add secrets as build arguments.

Use [.env.hosted.example](../.env.hosted.example) as a setting inventory, not a
working credential file. Its placeholders deliberately fail validation.

| Setting | Hosted requirement |
| --- | --- |
| `MVP_DEPLOYMENT_MODE` | `hosted`; omitted remains local mode |
| `MVP_HOSTED_INGRESS` | `render`; explicit trust in that managed ingress |
| `MVP_PUBLIC_ORIGIN` | One exact canonical HTTPS origin, without trailing slash |
| `MVP_API_HOST` | `127.0.0.1:8765` |
| `MVP_API_ORIGIN` | `http://127.0.0.1:8765` |
| `MVP_PERSISTENT_ROOT` | Existing actual mounted directory; reference `/var/data` |
| `MVP_WEB_DATA_DIR` | Private descendant; reference `/var/data/litrev` |
| `MVP_HOSTED_INVITE_SHA256` | SHA-256 of an operator-generated random invitation code |
| `PORT` | Public Next listener, default `10000`, distinct from `8765` |
| `MVP_MAP_ENABLED`, `MVP_SEARCH_PLANNER_ENABLED`, `MVP_PROPOSALS_ENABLED` | `0`; enabling them is refused in this hosted release |
| `NCBI_EMAIL`, `NCBI_API_KEY` | Optional private operator configuration; no live discovery without a contact |

Generate the invitation locally with a cryptographic random generator, at least
32 characters (the login accepts 32–256). Store only its lowercase SHA-256 digest
in service environment settings. Share the invitation privately; never put it in
a URL, repository, screenshot, analytics or command log. Keep the configuration
file mode `0600`. No sample invitation in this repository is a production secret.

For a new local production volume, the reference container command is:

```sh
docker volume create litrev-hosted-data
docker run --name litrev-hosted --detach \
  --publish 127.0.0.1:10080:10000 \
  --mount source=litrev-hosted-data,target=/var/data \
  --env-file /absolute/path/to/private-hosted.env litrev-hosted:local
```

This listener needs the intended HTTPS ingress before browser use. A raw HTTP
request to `10080` is not a hosted browser deployment. Runtime runs as UID/GID
`10001`; a new mounted directory must be writable by that identity. Initialize
only the new hosted mount when necessary, never chmod/chown a local research tree.
No local `.mvp-web-state` mount or automatic migration is part of this command.

## Hosted security and recovery limits

Python and the Next bridge independently validate configured origins. The bridge
checks actual `Host`, unchanged browser `Origin`, and HTTPS ingress confirmation.
A forwarded host can confirm the actual host, never replace it. Forwarded client
IP is not used for identity, admission or quotas. FastAPI ignores proxy headers
and stays internal. Only allowlisted methods, paths, query keys and bounded
bodies are forwarded; upstream redirects and request-selected upstream URLs fail.
Body reads have a 15-second total deadline and cancel stalled streams, returning
a redacted 408 before an upstream research operation starts.

Render terminates TLS and redirects public HTTP to HTTPS before forwarding to
the service's inaccessible public-facing internal port. This is an explicit
platform boundary, not a generic authorization scheme for an exposed HTTP port.
Do not place this configuration behind a different proxy or expose the internal
listener without reviewing and testing its header/network policy.
See [Render networking](https://render.com/docs/web-services#host-and-port).

Admission gates session issuance and all research API routes. It is separate
from workspace ownership: two admitted browsers receive different opaque research
sessions and cannot read each other's workspaces, citations or exports.
Hosted cookies use `__Host-` names, Secure, HttpOnly, SameSite=Strict and path `/`,
without Domain. Existing CSRF and exact resource ownership checks remain.
Research/auth responses use `no-store`; errors are redacted and API access logs
are disabled. Static hashed JavaScript/CSS are public application code and can
still be cached by Next; they contain no research state or server secrets.

Initial bounds are fixed epoch windows, not rolling or IP-based limits:

- 40 global login attempts per 15 minutes; at most 256 unexpired admission grants.
- Admission expires after eight hours; 2,000 API requests and 60 expensive
  operations per admission per hour. Upload parsing, discovery, resolution,
  preparation and model-related submission paths consume the expensive budget.
- Manual cell saves use the request budget; a 180-cell board does not authorize
  180 model calls. Existing concurrency, body, storage and proposal bounds remain.

Rotating the configured invitation digest revokes existing admission at the next
request after restart/configuration rollout; it does not cancel already admitted
in-flight work. `POST /api/v1/admission/logout` revokes admission only and retains
the separate research cookie. Logging in again can reopen that browser's work.
The beta banner offers **Renew beta access** without unmounting the research
editor. **End beta admission** first drains draft saves; a failed save keeps the
editor open and offers renewal rather than discarding entered work.
There are no named accounts, cross-device synchronization, MFA or cookie recovery.
Losing/clearing/expiring the research cookie loses access. Export regularly.
Shared-invite/global limits can cause shared denial of service; this beta is for
a small invited group, not unrestricted public registration.

The public `/healthz` returns only generic readiness, with no session or source
data. It checks the internal API's live preparation thread, storage write/fsync
probe and registry/admission database queries. A failed child stops the service.

## Durable state and consistent backups

The entire `MVP_WEB_DATA_DIR` is durable, including:

- `web-credentials.sqlite3`: private sessions, capability registry, UI drafts and
  deletion fences. Protect it as credentials.
- `workspaces.sqlite3`: research snapshots, imports/collections, search plans,
  sources, preparations, assessments, preparation jobs and retained stages.
- `evidence-boards.sqlite3`: definitions, cell drafts/revisions, candidates,
  optional proposal records and immutable references.
- `paper-maps.sqlite3`: retained maps, coordinates and embedding/projection artifacts.
- `hosted-admission.sqlite3`: hashed admission tokens, expiry and bounded counters.
- SQLite journals, per-workspace deletion locks, preparation-worker locks and any
  derived artifacts under the same tree. Backups inventory all files, not just
  this list of known database names.

Only paths under the mounted disk survive Render restart/redeployment. Its disk
requires a paid service, is attached to one instance, and is unavailable during
build/pre-deploy stages. Do not use a free ephemeral service for persistent
research state. [Render persistent disk documentation](https://render.com/docs/disks).

Backup is a stopped-whole-application operation. Stop and reap both servers and
workers first; the backup tool refuses the supervisor's held disk lock. It checks
SQLite integrity on a private stopped-state snapshot copy, archives the entire
private tree with an exact hash/size
manifest, fsyncs and publishes a new `0600` archive without overwriting a copy.
Restore verifies every entry, rejects unsafe paths/links/duplicates/oversized or
tampered files, checks SQLite and publishes a new `0700` directory. It never
overwrites the only data copy. Bounds: 4 GiB total, 1 GiB/file, 100,000 data files.

With the service stopped and the same private environment/volume mounted in an
operator container, the implemented commands are:

```sh
python scripts/hosted_backup.py backup --output /backup/new-backup.tar.gz
python scripts/hosted_backup.py restore \
  --archive /backup/new-backup.tar.gz --destination /var/data/restored-new
```

For Docker, override the normal entrypoint with `--entrypoint python`, mount a
protected operator backup directory at `/backup`, and pass the script/arguments.
The output must be a new file outside `/var/data`; the restore target must be a
new direct child of `/var/data`. Retain the original directory and test the
restored one by explicitly setting `MVP_WEB_DATA_DIR=/var/data/restored-new`.
Off-service backups contain credentials and source material: download privately,
protect/encrypt them and test restoration. The CLI does not upload them anywhere.
The backup destination needs space for both the private snapshot copy and the
compressed archive. Integrity checking cannot create journals in the source tree.
Never independently launch an API against this tree while stopped-app operations
hold the lock. A mounted disk or platform snapshot alone is not this backup gate.

Interrupted preparation resumes only through the existing persisted lease/stage
recovery rules. An interruption may leave a failed job requiring explicit retry;
provider side effects are not promised exactly once. Do not add a second provider
process or a separate disk-dependent worker service.

## Capabilities and release gate

Saved public sources, precomputed maps, imports, lexical passage retrieval,
manual comparison, revision/history and exports remain available. Live PubMed
requires private operator contact configuration and a separately authorized live
smoke. New map fitting, AI planning and cell suggestions stay disabled; a cloud
container cannot call a model on the developer's laptop. Capability reasons say
what is actually unavailable. No model download occurs on a visitor's first page.

After patch review, an operator must separately authorize the service/disk cost
and deployment. Select the reviewed branch containing this implementation, use
the Dockerfile and root build context, one instance, `/var/data` disk, runtime
secrets and public `/healthz`. Keep automatic rollout disabled. Use the assigned
application URL as the exact origin; do not buy a domain for this checkpoint.
Choose an instance/disk size from observed workload plus headroom, not an invented
minimum. Actual platform networking, disk ownership and browser cookies still
require verification on that assigned HTTPS domain.

Before a portfolio link: verify health, invitation denial/login, separate-browser
isolation, direct-page refresh, uploads, exact sources, save/revision, restart,
exports and backup restoration on the deployed commit. Record enabled
capabilities and failures. Only then apply the separate portfolio handoff through
its existing branch/PR/Pages process, with authorization.

Local mode remains the default. `scripts/run_web.py` and Streamlit are retained;
use the existing local data directory and origin, with
`MVP_DEPLOYMENT_MODE=local` if a hosted environment was exported in that shell.
