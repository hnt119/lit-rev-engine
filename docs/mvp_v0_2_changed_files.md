# MVP v0.2 publication inventory

Branch: `codex/mvp-v0-2`. Implementation baseline: `8df5993c86893d47620a101a2319c564cff2d494`.

Publication is scoped to this branch; `main` and hosted deployment remain unchanged. The implementation evaluation retains its original execution dates and evidence boundaries.

The publication contains **69 files listed below**, plus this inventory itself (**70 files total**). `M` means modified from the MVP baseline; `A` means added. SHA-256 values describe the committed file contents, including partial staging of README and `.gitignore`.

The original tested implementation had 67 inventoried files plus its inventory. Publication adds the two linked scope documents, `ARCHITECTURE_V0_2.md` and `ACCEPTANCE_V0_2.md`, without modifying their supplied contents, and updates branch/publication wording in the guide, README and evaluation report. Implementation code and tests retain the previously tested bytes.

Excluded and preserved locally: the preexisting README Retrieval quality experiments section; the `.gitignore` `.cache/` rule; `CODEX_PROMPT_V0_2.md`; unrelated benchmarks/data/evaluations/reports/retrieval code/tests and workflow archives; actual `.env`/credentials; private SQLite/session/source/export state; model weights; environments, dependency directories and generated build caches. The committed `.env.example` contains only loopback-origin placeholders.

| File | Status | SHA-256 |
|---|---|---|
| [.gitignore](../.gitignore) | M | `d14bcdc072c3ace9f51ab3e424ce363d43b6262296b574f06ed4831a873f7e5b` |
| [ACCEPTANCE_V0_2.md](../ACCEPTANCE_V0_2.md) | A | `81f7e4d4e90e10ccc5a92a2949dc03a935727081a56562b62042ecaa3abeb0e7` |
| [ARCHITECTURE_V0_2.md](../ARCHITECTURE_V0_2.md) | A | `e959dfd06eb9c0ab740ade8eae59f106e200b2ca0bf4aa8fb40aebde1ad33519` |
| [README.md](../README.md) | M | `e8778b0df9c8649c465769c7c289a8b5f5e73d5986ade7ce8aabf08e7203c5cc` |
| [apps/streamlit/app.py](../apps/streamlit/app.py) | M | `6a7925a6f05df3e55fa12fc81eb5d5500f398585e506c98ebada9cbf159a765f` |
| [apps/web/.env.example](../apps/web/.env.example) | A | `b6003620cc882930eb6691453f90bd816d60a8179f492c53a08cdc1242292d51` |
| [apps/web/.gitignore](../apps/web/.gitignore) | A | `6f5d9561bf6ca0b4aae0552a0f9023dda3dcf79c2f41f024792eac8ee278e1df` |
| [apps/web/README.md](../apps/web/README.md) | A | `1c6bab6a1a84621f5599cbf6a31f4bbeeb2f44c9524e7ca930f5808387cdcb1b` |
| [apps/web/app/api/v1/\[...path\]/route.ts](../apps/web/app/api/v1/[...path]/route.ts) | A | `874c59076838610197813f4a0ce9554531943e645a612953916d615ca8549a8b` |
| [apps/web/app/globals.css](../apps/web/app/globals.css) | A | `9a2d16aa33ae8c7cc3e1890faaf70172e2ec649b4665f7fc36bf4b1e1a5062fc` |
| [apps/web/app/layout.tsx](../apps/web/app/layout.tsx) | A | `1b6629dfb6c17a032a35048c5effb891812ec5eca302c3c1ba15c5b366dacbd7` |
| [apps/web/app/page.tsx](../apps/web/app/page.tsx) | A | `5ae4cbcebc2e01d01657e233379d75e2014db10e2b9ccd39a9467a22e90bd163` |
| [apps/web/components/discover.tsx](../apps/web/components/discover.tsx) | A | `614199571aaa393bac2b3b714bf3d3ac65fb2e918ab197f475f730e81b550e56` |
| [apps/web/components/evidence.tsx](../apps/web/components/evidence.tsx) | A | `b367a82fcec9c102665b89e0895a95743d2ea09669f629d9c8bc28d8bfbd3a39` |
| [apps/web/components/exploration-panels.tsx](../apps/web/components/exploration-panels.tsx) | A | `57e2f885fbab9b48eb286f789ee21059eb4bea7acc91115d825735efe6e5fda7` |
| [apps/web/components/history.tsx](../apps/web/components/history.tsx) | A | `0b73ff7d69ba17ba415aa3010e94ea335ae28f32e246f3b1ffa0ef6bd226fa6f` |
| [apps/web/components/map-explorer.tsx](../apps/web/components/map-explorer.tsx) | A | `9d704f5506b2118b050b54aa4c4ee95d3ac9f20b20f769e4a5eab99de4a32a78` |
| [apps/web/components/semantic-map.tsx](../apps/web/components/semantic-map.tsx) | A | `a05aed1667196babc4a683cb9c6053a2cc04d7edac9d1eb4beef924fb25e1bca` |
| [apps/web/components/ui.tsx](../apps/web/components/ui.tsx) | A | `42b9690347b5d02e349e00ef3d1620f7bb26e03c0e4cb1649490222695aff60d` |
| [apps/web/components/workspace-app.tsx](../apps/web/components/workspace-app.tsx) | A | `f077eeb857a6a43836a31ff97c2c2c978174b992981b5a57b3000bd46f84531e` |
| [apps/web/lib/api.ts](../apps/web/lib/api.ts) | A | `9147a7a7f6869e80a1c5d4d6696eba742848365ed2e805e1e44657b2f611c894` |
| [apps/web/lib/bridge.ts](../apps/web/lib/bridge.ts) | A | `c9ad83666fd5f337d3e23827ef48d125c1e3cb8174b9a331bbfd024cb6d57f19` |
| [apps/web/lib/drafts.tsx](../apps/web/lib/drafts.tsx) | A | `608674de5b73fa1aeae5ecb5f55e2967dd601d7facad0b9edb5bd71595a76fba` |
| [apps/web/lib/generated-api.ts](../apps/web/lib/generated-api.ts) | A | `38a32f5d6d7931e7d483dc5e8d7607b67bb4d914d25fc67ced9c4e43bd1bba2c` |
| [apps/web/lib/helpers.ts](../apps/web/lib/helpers.ts) | A | `6c9eb40a8754334814288367c2d365a67147215e65e073039c6d8781a1b14dab` |
| [apps/web/lib/map-view.ts](../apps/web/lib/map-view.ts) | A | `23c47686ee08b22f1c8cf996988b146cce2ea95071ed34ed731d54ffac6681d6` |
| [apps/web/lib/openapi.json](../apps/web/lib/openapi.json) | A | `2bc6e6e033c228ba0d7a04b90288aaa5550a0a69e9aa8ea83ce85667f6878dfb` |
| [apps/web/next-env.d.ts](../apps/web/next-env.d.ts) | A | `1862ac4bbbc5192d4bf562161df66ea547ed3e67173100656ab606ae9797db2b` |
| [apps/web/next.config.ts](../apps/web/next.config.ts) | A | `3843f10aaa492bc8b7daeb170c002f032cea2e7136a0f7627eace047307878c8` |
| [apps/web/package.json](../apps/web/package.json) | A | `9e183caf3b467010964be0dd44d6db3c99fec4075a0b989f2c6c0a423e9b81b2` |
| [apps/web/pnpm-lock.yaml](../apps/web/pnpm-lock.yaml) | A | `e13ff519022b7bef9e3016dcba5bf82335196b55d270967f76c058588817d440` |
| [apps/web/tests/boundaries.test.ts](../apps/web/tests/boundaries.test.ts) | A | `019f789d53138be4a1ce6185ef705bda230331c0b0ac8d71d80194b6e693d743` |
| [apps/web/tests/drafts.test.tsx](../apps/web/tests/drafts.test.tsx) | A | `8756ac33474ad250c982f7e08727e8ee2f3875e2ff017942731f10b5a3ec7cae` |
| [apps/web/tests/map-component.test.tsx](../apps/web/tests/map-component.test.tsx) | A | `d6de9c4bc7da95fb7a9df7e34ec270bef308f1bce2dbd283054bbee931104b3f` |
| [apps/web/tests/map-view.test.ts](../apps/web/tests/map-view.test.ts) | A | `a5fc3e1df6ec1f71fa29fb691b710e1a070787cc0708ffe4dcf1c09f626bf659` |
| [apps/web/tsconfig.json](../apps/web/tsconfig.json) | A | `85e5e6d205aae400a27949123db408cc5140a14103bb09682bbd6752f4b71452` |
| [docs/mvp_v0_2.md](../docs/mvp_v0_2.md) | A | `fee1fa91e2295d75052507e7493fbe4342da6138b443fbb43405143e0201f1ed` |
| [docs/mvp_v0_2_evaluation.md](../docs/mvp_v0_2_evaluation.md) | A | `07e5e6e754cab144958fcfb0183f5f9a4a0dcdbf8f938d8cdb32dbfb15100897` |
| [requirements-map-dev.txt](../requirements-map-dev.txt) | A | `59a745cbff42da5dc0423f1e00bde69c870bd52e9590090d590c475033366659` |
| [requirements-map-lock.txt](../requirements-map-lock.txt) | A | `909731bdfee8057e61d2b993ffe2c19d27e0c06a6cbbf760ad0f291047c5d48b` |
| [requirements-map.txt](../requirements-map.txt) | A | `7d80d0425b44c829126c6de00ea945d125eee57efb7379d875ae282c7ed5e530` |
| [requirements-web-dev.txt](../requirements-web-dev.txt) | A | `46093585ce0b86743263211ef986fa3b15043752c5cb4c84dddf3016e0afd4cb` |
| [requirements-web-lock.txt](../requirements-web-lock.txt) | A | `67cfcae34bd941de361fce49952ae87beb159db35a7e2ab9e1e8af2f2c9322b7` |
| [requirements-web.txt](../requirements-web.txt) | A | `7e5155af456117c3fc575084b67464527e53b2faa673f86a018a097e1c108a96` |
| [scripts/export_web_openapi.py](../scripts/export_web_openapi.py) | A | `e62edda04cd42448cae68a4459e80f16336ba8bb4479104201a17c8ecb764554` |
| [scripts/mvp_map_smoke.py](../scripts/mvp_map_smoke.py) | A | `25666a96ffc6da2d8e32c6f826630c2750b3fdc354036b9924b3e12a64f4afd4` |
| [scripts/run_map_worker.py](../scripts/run_map_worker.py) | A | `9702f9ab8bb5617fb3071f089dedb77c893109fdf70fffed6e919c17b4059267` |
| [scripts/run_web.py](../scripts/run_web.py) | A | `ed9e5cc125385ffc0145373898b628717fd630287be06edf2daa6a50dc36a44f` |
| [src/mvp/adapters/map_storage.py](../src/mvp/adapters/map_storage.py) | A | `85c813633a76995aaba11d5dc4bc10e2bfd04594a837b1db7dfd3911675d7997` |
| [src/mvp/adapters/paper_embeddings.py](../src/mvp/adapters/paper_embeddings.py) | A | `411c1b8488a8a1f61c74a2960174c3c93a01d34243f91aa0b5ea90cc5ca17b4a` |
| [src/mvp/adapters/storage.py](../src/mvp/adapters/storage.py) | M | `930cbd1f3d4b88b70beceb017192b55a9379dfd8480f068a61117e49e316e51d` |
| [src/mvp/contracts.py](../src/mvp/contracts.py) | M | `76be39aef65df1bf9106cc6cb11236763b0a52c71d64e9222cc2e4c00703e52e` |
| [src/mvp/map_jobs.py](../src/mvp/map_jobs.py) | A | `533742174b5448158d6a10a62196962d5bbc255870dc885b3b5f6e9654b56f92` |
| [src/mvp/mapping.py](../src/mvp/mapping.py) | A | `7b295184c8670f4354a4b45b2cc5d13d08457572029e37b674f909b4efddca5b` |
| [src/mvp/ports.py](../src/mvp/ports.py) | M | `3869298a6b50dd8f4c9b61e3a12d46d0ffc0865174671c65cee87b666ed23d99` |
| [src/mvp/service.py](../src/mvp/service.py) | M | `fb643458034c5f47195e88ddc110fb71ad93fdbd24ba6ff079db21cb8100c8a4` |
| [src/mvp/workspace_ui.py](../src/mvp/workspace_ui.py) | A | `e5166c6bc447be0b03e88b8b23a3d0087179afd418846bf6cb760bea6bdfb6f9` |
| [src/web_api/__init__.py](../src/web_api/__init__.py) | A | `e82a0d177b7209f5d70fdddc6ba633eb1062fca08f0f4397e1c5a3e2a42c8032` |
| [src/web_api/app.py](../src/web_api/app.py) | A | `da0dd41d74855b14968a9b187fcbc8f843e6abdc15690f0fb5eac7329f136bda` |
| [src/web_api/contracts.py](../src/web_api/contracts.py) | A | `124af4417b9b2161281bcfa32607f6042bff5836a0ce39f8345862c6386c6af1` |
| [src/web_api/map_routes.py](../src/web_api/map_routes.py) | A | `241a2e3a673d1be9562559754704cfe3f584be9f4d206cb5181bfd8c9fd00434` |
| [src/web_api/projections.py](../src/web_api/projections.py) | A | `79338db1d43801d910025d95e524be3fe3a627677d5e58a2a9f77d00b9c4a873` |
| [tests/mapping/test_embedding_windows.py](../tests/mapping/test_embedding_windows.py) | A | `d7a3007ec04563335286e3b83bd6557f377f73bfdc45f1072dc6f2701e4bf8b5` |
| [tests/mapping/test_independent.py](../tests/mapping/test_independent.py) | A | `5055440f9370762160f6c5d39d90b5e1c59c4a3624734a7b132a62bb53e91163` |
| [tests/mapping/test_independent_jobs.py](../tests/mapping/test_independent_jobs.py) | A | `bc6a9a9f8a7771177052e0da4fcfecd685afac6d7b7764f0dbf17b4ffa36d81b` |
| [tests/mapping/test_jobs.py](../tests/mapping/test_jobs.py) | A | `3aebc4a624621f5fb5fc37f22035de7b7395b22f2fa96473b220db47fe4e6b75` |
| [tests/mvp/test_bound_history.py](../tests/mvp/test_bound_history.py) | A | `de9dc8c5740c679a835a37da5dc344572b7538ee4bca412ddb0b6f0d0a8705f6` |
| [tests/mvp/test_drafts.py](../tests/mvp/test_drafts.py) | A | `9208f420641ac2bc98db3101c3892bb68f229810013603d194cb45a010656b2d` |
| [tests/web_api/test_api.py](../tests/web_api/test_api.py) | A | `9c7b7e83cd09ff1838b0885c7e65435b79fcbdc4520a7967a31487a7daaea4d4` |

This inventory has no self-hash. See the evaluation report for commands, observed results, skips, browser checks and remaining limitations.
