"""Hybrid exact references into a new packet contract; generation budgets unchanged."""
from ..board_contracts import BoardRevision
from ..contracts import canonical, digest
from ..ports import MvpError
from ..proposal_contracts import (
    MAX_PACKET_BYTES, MAX_PACKET_CHARACTERS, ProposalEvidence, HybridProposalPacket,
    HybridProposalPacketField,
)
from ..hybrid_contracts import QWEN_PROFILE, MEDCPT_PROFILE
from ..hybrid_app_contracts import HybridBoardCandidates
from .cell_generation import _packet_error

SPAN_PACKET_POLICY = 'hybrid-primary-spans-round-robin.v1'


def build_hybrid_packet(definition: BoardRevision, paper_id: str,
                      field_candidates: list[HybridBoardCandidates]) -> HybridProposalPacket:
    """Reserve one available candidate per field, then fill in round-robin order.

    Whole exact anchors are deduplicated and shared across all associated fields.
    If the initial field-coverage set cannot fit, fail before generation instead
    of silently starving later fields. Extra candidates are omitted whole at the
    existing byte/character bounds. No generator or prompt version changes.
    """
    profile = definition.retrieval_profile
    if (profile.get('profile_id') not in {QWEN_PROFILE, MEDCPT_PROFILE}
            or profile.get('packet_policy') != SPAN_PACKET_POLICY
            or digest(profile) != definition.retrieval_profile_sha256):
        raise _packet_error()
    papers = [value for value in definition.papers if value.id == paper_id]
    sources = [value for value in definition.sources if value.paper_id == paper_id]
    if (len(papers) != 1 or len(sources) != 1 or paper_id not in definition.paper_ids
            or not 1 <= len(field_candidates) <= 6
            or len({value.field_id for value in field_candidates}) != len(field_candidates)):
        raise _packet_error()
    paper, source = papers[0], sources[0]
    fields = {value.id: value for value in definition.fields}
    runs, queues, evidence = [], {}, {}
    for raw in field_candidates:
        try:
            run = HybridBoardCandidates.model_validate(raw.model_dump(mode='json'))
        except Exception:
            raise _packet_error() from None
        field = fields.get(run.field_id)
        if (field is None or run.board_id != definition.board_id
                or run.board_revision_id != definition.revision_id or run.paper_id != paper_id
                or run.field_revision_id != field.revision_id
                or run.preparation_id != definition.preparation_id
                or run.source_manifest_sha256 != definition.source_manifest_sha256
                or run.retrieval_profile != profile
                or run.retrieval_profile_sha256 != definition.retrieval_profile_sha256
                or [value.model_dump(mode='json') for value in run.result.requirements]
                   != profile.get('requirements_by_field', {}).get(field.id)):
            raise _packet_error()
        runs.append(run)
        queues[field.id] = []
        for candidate in run.result.candidates:
            ref = candidate.reference
            omitted_characters = candidate.omitted_before + candidate.omitted_after
            if (ref.paper_id != paper_id or ref.source_id != source.source_id
                    or ref.source_version != source.version or ref.source_sha256 != source.source_sha256
                    or ref.blocks_sha256 != source.blocks_sha256 or ref.integrity != 'checked'):
                raise _packet_error()
            anchor = (ref.source_id, ref.source_version, ref.source_sha256,
                      ref.blocks_sha256, ref.block_id, ref.start, ref.end)
            if anchor in queues[field.id]:
                raise _packet_error()
            queues[field.id].append(anchor)
            prior = evidence.get(anchor)
            if prior is not None:
                if (prior.reference != ref or prior.total_block_characters != candidate.total_block_characters
                        or prior.omitted_characters != omitted_characters):
                    raise _packet_error()
                evidence[anchor] = prior.model_copy(update={'field_ids': [*prior.field_ids, field.id]})
            else:
                evidence[anchor] = ProposalEvidence(evidence_id='e:' + digest([paper_id, anchor]),
                    reference=ref, field_ids=[field.id], total_block_characters=candidate.total_block_characters,
                    omitted_characters=omitted_characters)

    def packet(selected):
        retained = set(selected)
        result_fields = []
        for run in runs:
            field = fields[run.field_id]
            own = queues[field.id]
            result_fields.append(HybridProposalPacketField(field_id=field.id, field_revision_id=field.revision_id,
                label=field.label, subquestion=field.subquestion,
                evidence_ids=[evidence[key].evidence_id for key in own if key in retained],
                candidate_run_id=run.id, indexed_windows=run.result.coverage.indexed_windows,
                candidate_count=run.result.returned_count, component_ids=[v.id for v in run.result.requirements],
                omitted_evidence=sum(key not in retained for key in own)))
        return HybridProposalPacket(retrieval_profile_sha256=definition.retrieval_profile_sha256, paper_id=paper_id, title=paper.title, question=definition.question,
            source_type=source.source_type, source_status=source.status, fields=result_fields,
            evidence=[evidence[key] for key in selected],
            evidence_characters=sum(len(evidence[key].reference.quote) for key in selected),
            omitted_evidence=sum(value.omitted_evidence for value in result_fields))

    def fits(value):
        return (value.evidence_characters <= MAX_PACKET_CHARACTERS
                and len(canonical(value.model_dump(mode='json')).encode('utf-8')) <= MAX_PACKET_BYTES)

    selected = list(dict.fromkeys(own[0] for own in queues.values() if own))
    result = packet(selected)
    if not fits(result):
        raise MvpError('proposal_context_limit', 'The per-field evidence coverage set exceeds the existing packet budget. Select fewer fields or shorter explicit field questions; no generation was called.')
    for rank in range(1, 3):
        for own in queues.values():
            if rank >= len(own) or own[rank] in selected:
                continue
            proposed = packet([*selected, own[rank]])
            if fits(proposed):
                selected.append(own[rank])
                result = proposed
    return result
