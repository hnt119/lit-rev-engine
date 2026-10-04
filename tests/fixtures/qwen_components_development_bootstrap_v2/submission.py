import os
from pathlib import Path
BUNDLE_CANDIDATES = (
    Path('/kaggle/input/datasets/yixuanhuangethan/qwen-components-development-bootstrap-v2'),
    Path('/kaggle/input/qwen-components-development-bootstrap-v2'),
)
PRESENT_BUNDLES = [candidate for candidate in BUNDLE_CANDIDATES
                   if candidate.is_dir() and (candidate / 'job.json').is_file()]
if len(PRESENT_BUNDLES) != 1:
    raise ValueError('Require exactly one configured development dataset mount with job.json; missing or ambiguous mounts stop execution.')
BUNDLE = PRESENT_BUNDLES[0]
print('Selected dataset mount: ' + str(BUNDLE))
JOB_PATH = BUNDLE / 'job.json'
CORE_PATH = BUNDLE / 'component_core.py'
HELPER_PATH = BUNDLE / 'qwen_kaggle_environment.py'
RUNNER_PATH = BUNDLE / 'qwen_components_kaggle_runner.py'
JOB_SHA256 = "4de843130af3727968e1a0f7bfd150c5743fcfb521d820a5c0fe0fd9c3bc3ce2"
OUTPUT_PATH = Path('/kaggle/working/components-results.json')
CHECKPOINT_PATH = Path('/kaggle/working/components-checkpoint.json')
AUDIT_PATH = Path('/kaggle/working/components-environment-audit.json')
INSTALLER_REPORT_PATH = Path('/kaggle/working/components-installer-report.json')
os.environ['HF_HOME'] = '/kaggle/temp/components-huggingface'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import hashlib
import importlib.util
import json
def unique_pairs(items):
    result = {}
    for name, value in items:
        if name in result: raise ValueError('Duplicate JSON key')
        result[name] = value
    return result
def reject_constant(value):
    raise ValueError('Nonfinite JSON')
assert JOB_PATH.stat().st_size <= 100 * 1024 * 1024
envelope = json.loads(JOB_PATH.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
assert set(envelope) == {'payload', 'payload_sha256'}
payload_bytes = json.dumps(envelope['payload'], ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
assert hashlib.sha256(payload_bytes).hexdigest() == envelope['payload_sha256'] == JOB_SHA256
executables = {'component_core.py': CORE_PATH, 'qwen_kaggle_environment.py': HELPER_PATH, 'qwen_components_kaggle_runner.py': RUNNER_PATH}
assert set(envelope['payload']['execution_files']) == set(executables)
for name, path in executables.items():
    assert path.name == name and path.resolve().is_relative_to(BUNDLE.resolve())
    body = path.read_bytes()
    assert {'sha256': hashlib.sha256(body).hexdigest(), 'size_bytes': len(body)} == envelope['payload']['execution_files'][name]
spec = importlib.util.spec_from_file_location('verified_qwen_environment', HELPER_PATH)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
print({'job_sha256': JOB_SHA256, 'questions': len(envelope['payload']['questions']), 'encoded_queries': len(envelope['payload']['query_rows'])})


# This new bootstrap adapter has a separate prospective runtime binding.
BOOTSTRAP_PATH = BUNDLE / 'qwen_kaggle_bootstrap.py'
BOOTSTRAP_SHA256 = 'b81fcf821708b40ee5cce907858851595cc58df01a9f8a9e24c8d68b457ff41c'
BOOTSTRAP_SIZE_BYTES = 16118
assert BOOTSTRAP_PATH.is_file() and BOOTSTRAP_PATH.name == 'qwen_kaggle_bootstrap.py'
assert BOOTSTRAP_PATH.resolve().is_relative_to(BUNDLE.resolve())
bootstrap_bytes = BOOTSTRAP_PATH.read_bytes()
assert len(bootstrap_bytes) == BOOTSTRAP_SIZE_BYTES
assert hashlib.sha256(bootstrap_bytes).hexdigest() == BOOTSTRAP_SHA256
bootstrap_spec = importlib.util.spec_from_file_location('verified_qwen_bootstrap', BOOTSTRAP_PATH)
bootstrap = importlib.util.module_from_spec(bootstrap_spec)
bootstrap_spec.loader.exec_module(bootstrap)
BOOTSTRAP_AUDIT_PATH = Path('/kaggle/working/components-bootstrap-audit.json')
summary = bootstrap.prepare_environment(helper, JOB_PATH, JOB_SHA256,
    core_path=CORE_PATH, runner_path=RUNNER_PATH, output_path=OUTPUT_PATH,
    checkpoint_path=CHECKPOINT_PATH, audit_path=AUDIT_PATH,
    report_path=INSTALLER_REPORT_PATH, bootstrap_audit_path=BOOTSTRAP_AUDIT_PATH)
print(json.dumps(summary, sort_keys=True))
