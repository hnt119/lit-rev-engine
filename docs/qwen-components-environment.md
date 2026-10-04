# Component retrieval: cloud environment and prospective source archives

Research checked **4 October 2026, Asia/Singapore**. This note records the selected repair for the supplied Kaggle log and the original sources acquired for the next component experiment. The implementation uses a new helper, runner and notebook; historical frozen runtime, source, truth and failed results stay unchanged. No inference or model download was performed for this research or truth construction. A clean GPU run must still validate the new environment and retrieval quality.

## What the supplied log shows

The 5,412-byte `qwen-kaggle.log` has SHA-256 `51c04983cf550747ece5125daadd4a2451aed3e297e37c15a050798031590aa8`. Its dependency warnings say that Gradio 6.26.0 requires a newer Hugging Face Hub, while Diffusers 0.40.0 requires a newer Hub and safetensors. The notebook installed the frozen older Qwen packages into the shared Kaggle Python environment, making those unrelated preinstalled applications' requirements inconsistent.

The log nevertheless records a completed Qwen batch, with the previously evaluated result checksum `0f5aa688f5382ddbfae3260bc1d832ba6d81aa2222a716feae07395887ea42be`. It has no Python traceback or failed model stage. The shared-environment warnings and failed retrieval quality gate are different issues. Preserve the first run as recorded; changing dependencies cannot retroactively make its retrieval result pass. [First live evaluation](qwen-kaggle-live-evaluation.md).

## Selected environment design

Use a **disposable isolated installer plus a fresh GPU worker with task-scoped Hugging Face packages**. Keep the notebook's own environment and CUDA Torch installation intact. This is isolation of the Qwen package selection and worker process, not a claim that the entire worker has an independent copy of every system library.

1. Create a default Python `venv` in a newly generated temporary directory, such as `/kaggle/temp/qwen-components-<random>/installer`. Do not give this installer access to system site-packages. Its pip then sees its own small environment rather than Kaggle's Gradio/Diffusers distributions. Python documents this default isolation and permits invoking the environment's interpreter without activation. [Python venv](https://docs.python.org/3/library/venv.html).
2. Invoke that interpreter's pip to install **only the four pinned packages**, with `--no-deps`, into a **new, empty** target directory such as `/kaggle/temp/qwen-components-<random>/overlay`. Use `--target` and save the installation report. Reuse compatible transitive dependencies from Kaggle rather than upgrading NumPy or other compiled libraries. Do not install `transformers[torch]`, reinstall Torch, change global packages, or overwrite an earlier target. Plain Transformers treats Torch as a separate backend. [Transformers 4.51.3 installation](https://huggingface.co/docs/transformers/v4.51.3/installation), [release dependency definitions](https://github.com/huggingface/transformers/blob/v4.51.3/setup.py).
3. Start a fresh child process using Kaggle's **base Python interpreter** with `-I`. A reviewed bootstrap explicitly prepends the private target directory to `sys.path` before importing Qwen libraries, then loads the verified runner by its absolute path. `-I` ignores `PYTHONPATH` and user-site injection, so relying on that environment variable would fail. Use structured subprocess arguments, not a shell command assembled from job content. [Python interpreter options](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I), [subprocess execution](https://docs.python.org/3/library/subprocess.html).
4. In the worker, verify the exact versions and module paths of Transformers, Tokenizers, safetensors and Hub all resolve to the private target. Read each of those four distributions' declared requirements; evaluate active environment markers with no extras and reject a missing or out-of-range dependency. Record the resolved transitive versions/paths. Verify Torch resolves to the recorded Kaggle base installation, keeps its original CUDA build, and can perform a small CUDA preflight without downloading models. Then check the job/runtime hashes and only afterward load weights. If a genuine dependency conflict remains, stop and choose a separately reviewed overlay extension; do not silently upgrade the global environment.

The pinned direct requirements remain `transformers==4.51.3`, `tokenizers==0.21.1`, `safetensors==0.5.3` and `huggingface-hub==0.30.2`. Retain those wheel hashes and all reused transitive versions: four direct version pins alone are not a complete environment lock. Record the Kaggle base environment and the import/constraint-check report, preserve pip's install report, and freeze the next profile before grading. This minimal overlay is conditional on actual worker preflight passing. [pip installation reports and hash requirements](https://pip.pypa.io/en/stable/cli/pip_install/).


The exact active non-extra requirements were checked against the four public release metadata records, evaluating Linux CPython 3.13 with `extra=""`. Transformers requires `filelock`, `huggingface-hub<1.0,>=0.30.0`, `numpy>=1.17`, `packaging>=20.0`, `pyyaml>=5.1`, `regex!=2019.12.17`, `requests`, `tokenizers<0.22,>=0.21`, `safetensors>=0.4.3` and `tqdm>=4.27`. Tokenizers requires `huggingface-hub>=0.16.4,<1.0` in its actual wheel metadata; PyPI JSON expresses the equivalent constraints in the reverse order. Hub requires `filelock`, `fsspec>=2023.5.0`, `packaging>=20.9`, `pyyaml>=5.1`, `requests`, `tqdm>=4.42.1` and `typing-extensions>=3.7.4.3`. Safetensors has **no active non-extra requirements**; its declared requirement rows are all extras, so an empty active audit is correct for that package. The helper must still validate actual installed metadata and versions, and the importer must require each package's exact active audit rather than accepting an omitted audit or a boolean alone. [Transformers metadata](https://pypi.org/pypi/transformers/4.51.3/json), [Tokenizers metadata](https://pypi.org/pypi/tokenizers/0.21.1/json), [safetensors metadata](https://pypi.org/pypi/safetensors/0.5.3/json), [Hub metadata](https://pypi.org/pypi/huggingface-hub/0.30.2/json).


The implementation audit was additionally checked against **actual wheel `METADATA`**, fetched as tiny public PEP 658 metadata sidecars without downloading the wheels. This caught the Tokenizers specifier-order difference before freeze. Compare normalized requirement semantics or the exact selected wheel spelling, not raw PyPI JSON string order. The two native wheels inspected use ABI3 manylinux x86_64 tags; the worker still has to prove actual imports and its CUDA operation. All other active requirements above match the inspected wheel metadata.

| Pinned distribution | Inspected public wheel metadata | Requires-Python | Metadata SHA-256 |
| --- | --- | --- | --- |
| transformers 4.51.3 | [transformers-4.51.3-py3-none-any.whl](https://files.pythonhosted.org/packages/a9/b6/5257d04ae327b44db31f15cce39e6020cc986333c715660b1315a9724d82/transformers-4.51.3-py3-none-any.whl.metadata) | >=3.9.0 | `a7fc5edbab63ce77b74b91957a376d101a5159c1b20036aaa33b9349034141ac` |
| tokenizers 0.21.1 | [tokenizers-0.21.1-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl](https://files.pythonhosted.org/packages/8a/63/38be071b0c8e06840bc6046991636bcb30c27f6bb1e670f4f4bc87cf49cc/tokenizers-0.21.1-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata) | >=3.9 | `18befc4e990a387f0a05b07505b6b4d705e0a7d22660260f02d9909772787599` |
| safetensors 0.5.3 | [safetensors-0.5.3-cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl](https://files.pythonhosted.org/packages/a6/f8/dae3421624fcc87a89d42e1898a798bc7ff72c61f38973a65d60df8f124c/safetensors-0.5.3-cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata) | >=3.7 | `fe7d581363ed20b204701623da8f90dd8a3b9995e9a9290b616788d80356adbf` |
| huggingface-hub 0.30.2 | [huggingface_hub-0.30.2-py3-none-any.whl](https://files.pythonhosted.org/packages/93/27/1fb384a841e9661faad1c31cbfa62864f59632e876df5d795234da51c395/huggingface_hub-0.30.2-py3-none-any.whl.metadata) | >=3.8.0 | `108629785c047a774d9859ec1342d5668145bf4b7547306105a523c5ce0e2aea` |

The pip installation report binds the actual installed wheels and their distribution archive hashes; these metadata-only research hashes do not replace that run evidence. Full worker audit, compiled imports and GPU validation remain required on Kaggle.

The implemented [environment helper](../tools/qwen_kaggle_environment.py) verifies explicit upload-bundle bytes before setup, creates a fresh temporary installer/overlay, saves the pip report and starts an isolated base-Python child. Its runner validates active requirements and import locations, followed by a CUDA operation before weights. The following schematic shows the selected process; use the generated notebook and reviewed helper rather than assembling it manually:

```text
KAGGLE_BASE_PYTHON -m venv /kaggle/temp/qwen-components-NEW/installer
/kaggle/temp/qwen-components-NEW/installer/bin/python -m pip install
  --no-deps --target /kaggle/temp/qwen-components-NEW/overlay
  --report /kaggle/working/qwen-install-report.json
  transformers==4.51.3 tokenizers==0.21.1
  safetensors==0.5.3 huggingface-hub==0.30.2
KAGGLE_BASE_PYTHON -I REVIEWED_WORKER_BOOTSTRAP [validated arguments]
```

These are schematic argument lists, not a shell script to paste. The bootstrap must install/import nothing from untrusted job instructions. The notebook controls paths and execution; the job contains data and declared retrieval parameters.

`--target` alone is insufficient assurance: pip's current official implementation still runs its installed-distribution conflict checker. `--no-warn-conflicts` would merely conceal warnings. Use the default-isolated installer to remove the unrelated global distributions from its dependency view. A `venv --system-site-packages` would expose them again. [pip install implementation](https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/commands/install.py).

A fully isolated worker venv is another design, but it would need an explicit, tested mechanism to reuse Torch and its CUDA/runtime dependencies. Adding the whole Kaggle site-packages directory defeats package isolation; hand-selected symlinks must cover the actual distribution dependency closure and native-library paths. That complexity is unnecessary for this first fix. Prefer the scoped worker, verify its imports, and state its boundary precisely.

Keep private packages and model caches in temporary storage outside `/kaggle/working`. Save only reports, provenance, checkpoints and result artifacts there. Kaggle documents saved notebook output and temporary session storage separately; a clean `Save & Run All` must recreate the installer/target without relying on prior interactive imports. [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).

## Environment ticket acceptance

The next notebook must prove:

- A simulated base environment with conflicting Gradio/Diffusers requirements remains unchanged after setup; no global package uninstall, downgrade or warning suppression occurs.
- Installer and worker are fresh processes, the expected HF packages resolve from the private target, and base Torch's path/version/CUDA build remain intact.
- All active, non-extra declared dependency constraints of the four pinned distributions pass. Import-only preflight and a small CUDA operation pass before any weight download; dependency/import/path mismatches stop execution without paid or smaller-model fallback.
- Setup retains its install report, lock hash, module locations, Python/Torch/CUDA versions and actual GPU metadata. A malformed or preexisting partial target fails explicitly or is replaced with a fresh distinct directory.
- A clean cloud run, rather than local mocks alone, validates this environment change. The old successful compute run and failed quality result remain reproducible artifacts.

## Selected prospective medical source split

The coordinator selected the following split and question design **before acquisition/gold construction or another model ranking**. These sources were checked against every earlier fixture with a literal DOI search; none occurred. Their acquired original XML confirms CC BY 4.0 licensing, attribution and publisher provenance. The labels below are abbreviated descriptions, not expected answers.

| Selected split | Original source | DOI / primary page | Structural purpose |
| --- | --- | --- | --- |
| Development | Routine-clinical CT lung-nodule CAD validation, 2022 | [10.1371/journal.pone.0266799](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0266799) | Diagnostic cohort; selection/reference protocol and detection/segmentation results. |
| Development | Rural-India hypertension education/monitoring cluster trial, 2020 | [10.1371/journal.pmed.1002997](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002997) | Trial; enrollment/follow-up, cluster design and adjusted outcome estimates. |
| Blind confirmation | Thyroid TI-RADS comparison between sonographers and radiologists, 2024 | [10.1371/journal.pone.0312121](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0312121) | Different diagnostic cohort; sampling period/reference and reader-specific results. |
| Blind confirmation | COPCOV prevention randomized trial, 2024 | [10.1371/journal.pmed.1004428](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004428) | Different trial; eligibility/endpoint procedures and own trial estimates must be distinguished from discussion or pooled meta-analysis. |

This balanced diagnostic-cohort/trial split tests a generic retrieval mechanism beyond the previously graded mammography/breast-ultrasound pair. DOI separation does not itself prove participant/study independence: the source-first reading additionally inspected study identity, sites, dates, design, trial registrations and related-report context, finding separate primary cohorts. Evaluation independently accepts that assessment before freezing the split. No candidate's raw patient-level data is required.

## Prospective source/gold procedure

The [development originals](../tests/fixtures/qwen_components_development_sources/README.md) and [confirmation originals](../tests/fixtures/qwen_components_confirmation_sources/README.md) retain the publisher's untouched main-article XML, recording DOI, version, acquisition URL, bytes/hash, date, attribution and exact license. Independent reconstruction precedes existing-parser reconciliation. Retrieval read the complete original main XML before constructing questions, inspecting Methods, Results, tables, captions, limitations and published discrepancies. Supplements require their own acquired source/version and cannot be inferred from a caption.

Development and confirmation truth are stored in separate sibling gold directories, each with **six quantitative positive compound questions and two source-scoped nulls**, with two or three requested components per question. Each split has 19 components. Development has four positives requiring separate body Methods and Results blocks in every sufficient alternative; confirmation has five, meeting the predeclared floor of four. Independent review added genuine summary/body OR alternatives before ranking and retained the counts honestly. Genuine sufficient OR alternatives preserve full qualifiers where repeated; no alternative was chosen from retrieval results. Exact own-quote spans and no-answer context are separate. The archives remain pending independent original-source semantic acceptance and prospective runtime freeze.

Components describe requested information using the population, intervention/comparator, outcome and timing named in the original question. They must not reveal answer dates, sample counts, effect values, confidence bounds, block IDs, result-containing quotes or a preferred section path. A component can ask for an enrollment window and an outcome estimate; it cannot supply that window or estimate. Component formulations must be reviewed independently and frozen before ranking.

For nulls, verify the absence of the requested combination in the retained source, not just the absence of a keyword. Preserve nearby misleading but inapplicable evidence and the exact population/timepoint/reference distinctions. Nulls test candidate limitations and human-facing uncertainty; they do not receive positive support credit and the retrieval engine still does not decide answerability.

Freeze the same **20-block global candidate pool and five unique returned own-block budget** for component-aware Qwen, whole-question Qwen and component-aware lexical comparisons. Scoring context does not count as own support. Report pool recall, selection losses, complete support, literal numerical/qualifier accuracy, null behavior and actual reviewer burden separately.

Use development for debugging and the predeclared small comparison budget only. After selecting one fixed candidate, freeze its runtime/profile/allocation rules and thresholds before running confirmation. Confirmation questions and gold must remain unavailable to implementation tuning; evaluation owns the truth and reviews original sources independently. A failed confirmation stays failed and becomes development evidence for a future source-disjoint cycle, never a target for repeated acceptance tuning.

Question, component and quote-anchor construction is now complete in the new archives, before any model or lexical ranking. The coordinator receives only confirmation counts, hashes, licensing and readiness before selection; confirmation QA is withheld from implementation tuning. These structural checks and fresh truth are preparation, not evidence that the new method passes the cloud or quality gates.
