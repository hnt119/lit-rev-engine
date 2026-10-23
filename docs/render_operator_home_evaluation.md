# Private operator home — packaging follow-up

Date: 24 October 2026 (Asia/Singapore). Parent release candidate:
`9891ac352d39c66395e21af2e9732a76b076d002`, branch `codex/mvp-v0-3`.
The candidate containing this report is a minimal, local successor for review.
Paid resources, pushing and deployment have not been authorized by this step.

## Included change

The Dockerfile creates the existing `litrev` account with `/home/litrev` and
`/bin/sh`, makes its home mode 0700, and creates an empty `.ssh` owned by
10001:10001 with mode 0700. The runtime still uses `USER 10001:10001`, the
existing supervisor entrypoint and the existing health check. No SSH keys,
credentials, SSH daemon, mount initialization or application changes are added.
This supplies the image-side prerequisites in
[Render's Docker SSH documentation](https://render.com/docs/ssh#docker-specific-configuration).
The persistent disk must remain at `/var/data`, never over the user's home.

Exactly three files belong in this candidate:

- `Dockerfile`
- `tests/deployment/test_hosted_image_identity.py`
- `docs/render_operator_home_evaluation.md`

The new test is an explicit opt-in test of an immutable, already built local
image. It checks real passwd/group/HOME/shell behavior, directory ownership and
mode, empty `.ssh`, and actual 0600 write/fsync/delete operations. It also checks
the unchanged image user, entrypoint, working directory and health check.
Its container has no network, data mounts or application startup, drops all
capabilities and enables no-new-privileges. No Docker access happens when the
image variable is absent.

## Observed local results

The build input was a clean Git archive of the parent candidate with only the
approved Dockerfile substituted. It contained no untracked local changes or
research state. The existing deny-by-default `.dockerignore`, pinned images and
dependency locks were unchanged. BuildKit reused unchanged dependency and
frontend layers; this was not a fresh dependency installation or frontend
recompilation.

| Check | Actual result |
| --- | --- |
| Production Docker build | PASS, `linux/amd64`, locally emulated on Apple Silicon |
| Deployment suite without image opt-in | 51 passed, 1 explicitly skipped, 4.10 s |
| Final deployment suite including actual-image probe | 52 passed, 0 failed, 0 skipped, 4.68 s |
| Runtime home and shell | PASS: HOME and passwd home `/home/litrev`, executable `/bin/sh`, UID/GID/euid/egid 10001 |
| Private home and `.ssh` | PASS: both owned 10001:10001, mode 0700, `.ssh` empty; real write/fsync/delete probes |
| Independent fresh normal startup | PASS: supervisor, API and Next run as 10001; both health listeners return 200; ready in 3.568 s |
| Fresh local mount | PASS: new empty Docker named volume, private data directory, write/fsync/delete probes |
| Existing backup lock | PASS: held by normal supervisor, prevents stopped-state operation |
| Controlled SIGTERM | PASS: exit 0 in 0.398 s; fresh QA container removed |
| Actual Render service, origin, disk ownership, SSH/SCP | NOT_RUN |
| Actual-domain browser, persistence and protected recovery | NOT_RUN |
| Live PubMed, model/provider calls, paid usage | NOT_RUN |

The independently checked image was:
`sha256:a7d5a23a79d76bd8796c73c9d4b9b2a16107db18dcc8d24dd2b88ecc2f2a8afc`.
The normal startup used a new random invitation digest, reserved `.test` origin,
no published ports and no external network. Only newly created QA storage was
attached; existing local applications and research databases were not mounted
or stopped. The QA volume was retained separately.

The first image-enabled suite recorded 51 passes and one failure: its strict
stderr check caught Docker's warning about an implicit amd64 image on an ARM
host. The in-container identity probe itself succeeded. The test now reads the
selected image's OS/architecture and requests that platform explicitly, keeping
strict stderr checking. The final full deployment rerun passed. Two inherited
TestClient/AnyIO deprecation warnings remain.

## Reproduction and evidence boundaries

From an isolated clean source export, build the candidate with the existing
Dockerfile. Do not use a developer research directory as a runtime volume or
pass private environment files as build input.

```sh
docker build --platform linux/amd64 --progress plain \
  --iidfile "$LITREV_IMAGE_ID_FILE" -t litrev-hosted:operator-home "$LITREV_CLEAN_SOURCE"

# Set this to the exact local sha256 image identity returned by Docker.
LITREV_HOSTED_TEST_IMAGE="sha256:<image-id>" \
  "$MVP_TEST_PYTHON" -m pytest tests/deployment -q
```

The results above were obtained before the candidate commit. A clean committed
archive must be checked separately, recording its full commit and image identity
without relying on untracked files. Local logs, fixture details, build/context
hashes, and preservation evidence are kept outside Git under the ignored
`.mvp-web-state/ui-checks/operator-home-2026-10-24/` directory.

The complete MVP/API/frontend suites and browser research workflow were not
repeated for this packaging-only change. Earlier results in
`deployment_evaluation.md` remain historical. No local Docker test proves
Render's actual mount permissions, gateway SSH access, service command override,
actual-domain authorization, backup transfer or restored application behavior.
Those remain gated platform acceptance work. The separately prepared Render
templates still name parent RC `9891ac3`; they must not be used for this successor
without explicitly rebinding and reviewing the new full SHA. No service, payment,
portfolio change, research upload, push or merge is part of this follow-up.
