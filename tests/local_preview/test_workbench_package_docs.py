"""Purpose-built documentation closure; synthetic Git state, no research/private inputs."""
import csv
import io
from pathlib import Path
import shutil
import zipfile

import pytest
from scripts import build_local_preview as package
from tests.local_distribution.test_release_packager import source, commit, ROOT, archive_audit


def payload_for_docs():
    payload={name:b'# Public documentation fixture\n' for name in package.WORKBENCH_DOCUMENTS}
    payload['USER_MANUAL.md']=b'# Manual\n'
    for name,header in package.BLANK_TEMPLATE_HEADERS.items():
        payload['question_evidence_evaluation/templates/'+name]=(header+'\n').encode()
    return payload


def test_explicit_public_workbench_docs_have_closed_links_and_exact_blank_templates(source,tmp_path):
    assert len(package.WORKBENCH_DOCUMENTS)==24
    assert len(package.BLANK_TEMPLATE_HEADERS)==9
    for destination,original in package.WORKBENCH_DOCUMENTS.items():
        target=source/original;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/original).read_bytes())
    (source/'docs/user_manual.md').write_bytes((ROOT/'docs/user_manual.md').read_bytes())
    # Deliberately committed synthetic future observation is outside the fixed
    # document list; no recursive directory inclusion is permitted.
    extra=source/'docs/question_evidence_evaluation/templates/future-private-observations.csv'
    extra.write_text('synthetic_canary\nnot-a-participant\n',encoding='utf-8')
    fixture='examples/mvp/offline_microbiome_30_v1'
    shutil.copytree(ROOT/fixture,source/fixture)
    head=commit(source);result=package.build(source,tmp_path/'public-docs',expected_source_commit=head)
    with zipfile.ZipFile(result['archive']) as bundle:
        payload={name.removeprefix(package.NAME+'/'):bundle.read(name) for name in bundle.namelist()}
    assert set(package.WORKBENCH_DOCUMENTS)<=payload.keys()
    assert not any('future-private-observations' in name for name in payload)
    guide=payload['question_evidence_user_guide.md']
    original=(ROOT/'docs/question_evidence_user_guide.md').read_bytes()
    assert guide==original.replace(b'](user_manual.md',b'](USER_MANUAL.md')
    assert b'](USER_MANUAL.md)' in guide and b'](USER_MANUAL.md#' in guide
    package.validate_workbench_documents(payload)
    archive_audit.audit_markdown_links(payload)
    assert archive_audit.audit(result['archive'],head,source)['all_payload_files_match_commit']
    for name,header in package.BLANK_TEMPLATE_HEADERS.items():
        assert list(csv.reader(io.StringIO(payload['question_evidence_evaluation/templates/'+name].decode('utf-8'))))==[header.split(',')]


@pytest.mark.parametrize('name',sorted(package.BLANK_TEMPLATE_HEADERS))
def test_populated_template_is_refused_before_creating_archive(source,tmp_path,name):
    target=source/'docs/question_evidence_evaluation/templates'/name
    target.write_text(package.BLANK_TEMPLATE_HEADERS[name]+'\nSYNTHETIC_PRIVATE_OBSERVATION_CANARY\n',encoding='utf-8')
    commit(source)
    with pytest.raises(ValueError,match='header only'):
        package.build(source,tmp_path/'must-not-exist')
    assert not (tmp_path/'must-not-exist').exists()


def test_changed_header_is_refused_even_when_it_has_only_one_row():
    payload=payload_for_docs()
    payload['question_evidence_evaluation/templates/issues.csv']=b'actual_private_text_cannot_masquerade_as_a_header\n'
    with pytest.raises(ValueError,match='header only'):package.validate_workbench_documents(payload)


def test_local_link_closure_checks_files_not_external_urls_anchors_or_code():
    payload=payload_for_docs()
    payload['question_evidence_user_guide.md']=b'[manual](USER_MANUAL.md#section) [external](https://invalid.example/never-contact) [anchor](#local)\n`[literal](missing-inline.md)`\n```sh\n[not-a-link](missing-code.md)\n```\n'
    package.validate_workbench_documents(payload);archive_audit.audit_markdown_links(payload)
    payload['question_evidence_user_guide.md']+=b'[broken](missing-file.md)\n'
    with pytest.raises(ValueError,match='no retained local target'):package.validate_workbench_documents(payload)
    with pytest.raises(AssertionError,match='no retained target'):archive_audit.audit_markdown_links(payload)
