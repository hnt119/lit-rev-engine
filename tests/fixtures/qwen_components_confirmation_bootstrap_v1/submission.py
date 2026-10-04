import os
from pathlib import Path

# Set the exact directory containing the five attached private dataset files.
MOUNT_CANDIDATES = (
    Path('/kaggle/input/datasets/yixuanhuangethan/qwen-components-confirmation-bootstrap-v1'),
    Path('/kaggle/input/qwen-components-confirmation-bootstrap-v1'),
)
matching_bundles = [path for path in MOUNT_CANDIDATES
                    if path.is_dir() and (path / 'job.json').is_file()]
if len(matching_bundles) != 1:
    raise RuntimeError('Expected exactly one confirmation dataset mount containing job.json')
BUNDLE = matching_bundles[0]
print({'dataset_mount': str(BUNDLE)})
JOB_PATH = BUNDLE / 'job.json'
CORE_PATH = BUNDLE / 'component_core.py'
HELPER_PATH = BUNDLE / 'qwen_kaggle_environment.py'
RUNNER_PATH = BUNDLE / 'qwen_components_kaggle_runner.py'
BOOTSTRAP_PATH = BUNDLE / 'qwen_kaggle_bootstrap.py'
JOB_SHA256 = '46cdb4be34507d170d656eeba19478bf493acdfe6315a352ae37bc941d0b19e5'
PROFILE_SHA256 = 'f379e61b007801a9d97540bac7665b4ad0faeaab507a000e03daaf6541bdb632'
BOOTSTRAP_SHA256 = 'b81fcf821708b40ee5cce907858851595cc58df01a9f8a9e24c8d68b457ff41c'
BOOTSTRAP_SIZE_BYTES = 16118
OUTPUT_PATH = Path('/kaggle/working/components-results.json')
CHECKPOINT_PATH = Path('/kaggle/working/components-checkpoint.json')
AUDIT_PATH = Path('/kaggle/working/components-environment-audit.json')
INSTALLER_REPORT_PATH = Path('/kaggle/working/components-installer-report.json')
BOOTSTRAP_AUDIT_PATH = Path('/kaggle/working/components-bootstrap-audit.json')
os.environ['HF_HOME'] = '/kaggle/temp/components-huggingface'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'


import hashlib
import importlib.util
import json

def load_json(path):
    def pairs(items):
        value = {}
        for name, item in items:
            if name in value:
                raise ValueError('Duplicate JSON key')
            value[name] = item
        return value
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Component job exceeds artifact bound')
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

assert BUNDLE.is_absolute() and BUNDLE.is_dir()
assert JOB_PATH.is_file() and not JOB_PATH.is_symlink()
envelope = load_json(JOB_PATH)
assert isinstance(envelope, dict) and set(envelope) == {'payload', 'payload_sha256'}
encoded = json.dumps(envelope['payload'], ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
assert hashlib.sha256(encoded).hexdigest() == envelope['payload_sha256'] == JOB_SHA256
assert envelope['payload']['profile_sha256'] == PROFILE_SHA256
bound_files = {'component_core.py': CORE_PATH, 'qwen_kaggle_environment.py': HELPER_PATH,
               'qwen_components_kaggle_runner.py': RUNNER_PATH}
assert set(envelope['payload']['execution_files']) == set(bound_files)
for name, path in bound_files.items():
    assert path.name == name and path.is_file() and not path.is_symlink()
    assert path.resolve().is_relative_to(BUNDLE.resolve())
    body = path.read_bytes()
    assert {'sha256': hashlib.sha256(body).hexdigest(), 'size_bytes': len(body)} == envelope['payload']['execution_files'][name]

# The additional bootstrap has a separate prospective binding, outside the original job's three-file binding.
assert BOOTSTRAP_PATH.name == 'qwen_kaggle_bootstrap.py'
assert BOOTSTRAP_PATH.is_file() and not BOOTSTRAP_PATH.is_symlink()
assert BOOTSTRAP_PATH.resolve().is_relative_to(BUNDLE.resolve())
bootstrap_bytes = BOOTSTRAP_PATH.read_bytes()
assert len(bootstrap_bytes) == BOOTSTRAP_SIZE_BYTES
assert hashlib.sha256(bootstrap_bytes).hexdigest() == BOOTSTRAP_SHA256

# Verify every executable above before loading either helper.
def load_verified_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

helper = load_verified_module('verified_qwen_environment', HELPER_PATH)
bootstrap = load_verified_module('verified_qwen_bootstrap', BOOTSTRAP_PATH)
print({'job_sha256': JOB_SHA256, 'questions': len(envelope['payload']['questions']),
       'encoded_queries': len(envelope['payload']['query_rows'])})


summary = bootstrap.prepare_environment(helper, JOB_PATH, JOB_SHA256,
    core_path=CORE_PATH, runner_path=RUNNER_PATH, output_path=OUTPUT_PATH,
    checkpoint_path=CHECKPOINT_PATH, audit_path=AUDIT_PATH,
    report_path=INSTALLER_REPORT_PATH, bootstrap_audit_path=BOOTSTRAP_AUDIT_PATH)
print(json.dumps(summary, sort_keys=True))
