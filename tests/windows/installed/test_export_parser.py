"""Independent parser rejects tampered bindings and leaked unsubmitted drafts."""
import copy
import csv
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('installed_trial', Path(__file__).with_name('trial.py'))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def write_case(root, mutate=None):
    # A non-BMP code point ensures range checking uses Python Unicode offsets,
    # rather than accidentally accepting JavaScript UTF-16 slicing.
    quote = '😀 microbiome'
    source = {'source_id': 's', 'version': 'v1', 'source_sha256': 'a' * 64, 'blocks_sha256': 'b' * 64}
    reference = {'paper_id': 'p0', 'source_id': 's', 'source_version': 'v1',
        'source_sha256': 'a' * 64, 'blocks_sha256': 'b' * 64, 'block_id': 'abstract',
        'start': 2, 'end': 2 + len(quote), 'quote': quote}
    expected = {'submitted': 'SUBMITTED', 'draft': 'UNSUBMITTED', 'missing': 'Not assessed',
        'excerpt': 'xx' + quote + 'tail', 'inspectedResponse': {'source': source,
            'block': {'block_id': 'abstract', 'start': 0, 'text': 'xx' + quote + 'tail'}}}
    rows = [{'paper_id': f'p{i}', 'field_id': f'f{j}', 'value': None,
        'missing_information': '', 'references': [], 'scope_result': 'not_assessed'}
        for i in range(3) for j in range(3)]
    rows[0].update(value='SUBMITTED', source_id='s', source_sha256='a' * 64,
        blocks_sha256='b' * 64, semantic_assessment='unassessed',
        reference_integrity='checked', references=[reference])
    rows[1]['missing_information'] = 'Not assessed'
    audit = {'table': rows, 'cell_revisions': [copy.deepcopy(rows[0]), copy.deepcopy(rows[1])]}
    if mutate:
        mutate(audit, expected)
    (root / 'private-expected-excerpt.json').write_text(json.dumps(expected), encoding='utf-8')
    folder = root / 'exports with spaces 亚洲'
    folder.mkdir()
    (folder / 'comparison.json').write_text(json.dumps(audit), encoding='utf-8')
    with (folder / 'comparison.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, ['paper_id', 'field_id', 'value', 'missing_information', 'source_sha256'], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def test_exact_unicode_source_and_draft_separation(tmp_path):
    write_case(tmp_path)
    trial.parse_exports(tmp_path)


@pytest.mark.parametrize('mutate', [
    lambda a, e: e['inspectedResponse']['source'].update(source_sha256='c' * 64),
    lambda a, e: a['table'][0]['references'][0].update(start=3),
    lambda a, e: a['table'][2].update(value='UNSUBMITTED'),
    lambda a, e: a['table'][1].update(value='Invented resolved value'),
    lambda a, e: a['cell_revisions'].pop(),
])
def test_tampered_export_is_rejected(tmp_path, mutate):
    write_case(tmp_path, mutate)
    with pytest.raises(trial.TrialFailure):
        trial.parse_exports(tmp_path)
