# Optional capabilities in Local beta 0.3.0-beta.2

The existing Track A Next.js/FastAPI research capabilities are included. For runtime session settings and optional own-key OpenAI/DeepSeek access, read SETTINGS.md. The private launch-file path below stays supported and intentionally permits literal-loopback generation only. Normal
setup/launch is offline/manual and does not download weights, call a model or
contact a literature provider. Historical CLI, Streamlit, arXiv and Kaggle tools
are separate entry points; this beta does not package them as additional apps.
Track B protocol-pilot work is not part of this download.

## Private explicit configuration

Copy `config/local-beta.example.json` to an **absolute path outside the app**.
Keep the copy owned by your OS user and set mode `0600` (`chmod 600` on that
private copy). Do not put credentials in the app, website, browser, a Next.js
`.env` file or a Git repository. The example contains no active settings.

```sh
python3.12 scripts/local_preview.py check-config --config /private/path/settings.json
python3.12 scripts/local_preview.py launch --config /private/path/settings.json
```

Use your actual private path, not the example path. The file must be ordinary,
not symlinked, at most 16 KiB and match `litrev.local-beta.settings.v1`. Unknown
keys, duplicate keys, unsupported endpoints and resource-budget overrides fail.
The launcher starts with its existing clean local environment, then adds only
these validated settings. Inherited provider keys, proxy variables, model flags
and hosted configuration are still removed. `check-config` reports availability
without starting a research session, loading weights or probing an endpoint.

The four sections are `live`, `maps`, `search_planner` and `cell_proposals`, each
with an explicit boolean `enabled`. Disabled sections do not forward their values.
Use the private config route when combining features. Do not combine `--config`
with the legacy `--allow-live` shell-contact route.

## Live PubMed and query diagnostics

Set `live.enabled` to true and supply `live.email`, your actual operational NCBI
contact. `live.api_key` is optional. Enabling the capability is not a search;
only an explicit live discovery/diagnostic action sends a query/contact to the
existing fixed providers. Saved examples do not become live searches.

The existing alternative remains available: without `--config`, use
`launch --allow-live` to forward only validated `NCBI_EMAIL` and optional
`NCBI_API_KEY` from that shell. No other inherited credentials are accepted.
Connectivity and search quality are not established by `check-config`.

## Compute a new local semantic map

Stop this installation before changing its Python environment. Explicitly add
the existing pinned mapping dependencies, in the isolated application environment:

```sh
python3.12 scripts/local_preview.py setup --with-maps
```

This installs the base requirements plus `requirements-map.txt` under its
existing `requirements-map-lock.txt` constraints. It does not obtain model
weights. Ordinary `setup` omits the optional mapping stack. Re-running ordinary
setup replaces this installation's owned runtime with the base environment.
Research data and external model caches are not migrated or deleted.

Acquire the existing BGE snapshot separately only if you choose to. The adapter
requires `BAAI/bge-small-en-v1.5` revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. The exact model/tokenizer files are
listed in `src/mvp/adapters/paper_embeddings.py`. A deliberate separate Hugging
Face CLI download, after optional dependency installation, can populate the cache:

```sh
.venv-preview/bin/hf download BAAI/bge-small-en-v1.5 \
  --revision 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a \
  config.json model.safetensors tokenizer.json tokenizer_config.json modules.json \
  1_Pooling/config.json sentence_bert_config.json config_sentence_transformers.json \
  special_tokens_map.json vocab.txt
```

That is an optional user-run model download, not part of setup, app startup or
normal navigation. The beta preparation does not imply it was executed.
Keep the model's own license and notices. Weights are not covered by the engine's
MIT license and are not bundled. Use the normal Hugging Face cache, or an
absolute external directory in `maps.cache_dir`; the directory must not be inside
the replaceable app. Set `maps.enabled` true, run `check-config`, then launch with
that config. The API's existing in-process worker handles explicit map requests;
no second worker is required. `scripts/run_map_worker.py` is also retained as an
advanced diagnostic tool, not an automatic launcher step.

The launcher forces offline model access and disables HF telemetry. The adapter
requires the exact pinned local snapshot and uses `local_files_only=True`, CPU
execution and the existing dimension/token/window profile. Missing dependencies
or weights leave new-map computation unavailable with an actionable setup
message; the offline/manual workflow and saved precomputed map still work.
No passage ranking, map fit/profile or historical artifact is silently changed.

## LLM query planning and AI cell proposals

Both existing adapters support one explicitly operated **literal HTTP loopback**
OpenAI-compatible server. They do not support remote credentials or paid provider
calls. You must install/operate your own compatible server and acquire its
weights separately. These settings do not install or start a model server.

For either `search_planner` or `cell_proposals`, set `enabled` true and supply:

- `url`: `http://127.0.0.1:8000/v1/chat/completions` (use your actual local port),
  or the existing literal IPv6 loopback equivalent;
- `model`: the name served by that endpoint;
- `model_revision`: the explicit revision you configured for that server.

`localhost`, remote hosts, HTTPS, embedded credentials, redirects, query strings,
fragments and other endpoint paths are unsupported. The app fixes both spend
caps at zero, preserves all existing call/context/token/runtime/concurrency
budgets, and never adds provider fallback or retries. It cannot attest what an
independently operated local endpoint does behind that interface. Do not point
it at a forwarding proxy to a remote/paid provider. Recorded revisions identify
configuration, not verified loaded weights.

`check-config` validates adapter construction but does not contact the server or
prove real-model quality. Planning proposals remain editable, unapproved search
intent. Cell proposals remain **AI suggestion — needs review**, stored separately
from drafts/submitted cells; exact references, manual judgment and explicit
adoption/submission remain required. No model receives tools or action authority.

## Evidence boundaries

Capability packaging, mocked workflow checks, real local embeddings and live
provider/model runs are different evidence. Inspect the final release validation
record for what actually ran. `NOT_RUN` means untested, not passed or zero usage.
No software test establishes scientific support, methodological completeness,
clinical reliability or usefulness to a researcher.
