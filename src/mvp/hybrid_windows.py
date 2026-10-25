"""Query-independent, source-bound windows with complete bounded coverage.

The optional fit predicate validates the *whole* document representation using
pinned tokenizers, including full title and reserved cross-encoder query space.
No title or evidence prefix is discarded to make a template fit.
"""
from __future__ import annotations
import re
from hashlib import sha256
from collections import defaultdict
from .contracts import PreparedSource, digest
from .board_contracts import BoardReference
from .hybrid_contracts import HybridCoverage, HybridInventory, HybridSourceBinding, HybridWindow
from .ports import MvpError
from .span_budget import budget_token_count

WINDOWIZER = 'sentence-codepoint-overlap.complete-model-template.v1'
MAX_WINDOW_CHARACTERS = 1000
OVERLAP_CHARACTERS = 160
MAX_SOURCE_BLOCKS = 2048
MAX_SOURCE_CHARACTERS = 4_000_000
MAX_WINDOWS = 8192
MAX_SOURCES = 30
_SENTENCE_END = re.compile(r'[.!?。！？]["\'”’\)\]]*\s+|\r\n|[\r\n]')


def check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise MvpError('hybrid_cancelled', 'Hybrid work was cancelled. No completed result or partial index was published.', True)


def source_binding(source):
    return HybridSourceBinding(source_id=source.id, **{k: getattr(source, k) for k in
        ('paper_id', 'version', 'source_sha256', 'blocks_sha256', 'parser_id', 'source_type')})


def scoped_sources(sources, authorized_sources):
    if not isinstance(sources, (list, tuple)) or any(not isinstance(v, PreparedSource) for v in sources):
        raise MvpError('hybrid_scope', 'Use retained canonical sources and an exact authorized source manifest.')
    if not isinstance(authorized_sources, (list, tuple)) or len(authorized_sources) > MAX_SOURCES:
        raise MvpError('hybrid_scope', 'Use a bounded explicit authorized source manifest.')
    bindings = []
    for item in authorized_sources:
        value = item.model_dump(mode='json') if hasattr(item, 'model_dump') else item
        if not isinstance(value, dict):
            raise MvpError('hybrid_scope', 'Use exact authorized source bindings.')
        try:
            bindings.append(HybridSourceBinding.model_validate({k: value[k] for k in HybridSourceBinding.model_fields}))
        except (ValueError, KeyError, TypeError):
            raise MvpError('hybrid_scope', 'Use exact authorized source bindings.') from None
    if len({v.source_id for v in bindings}) != len(bindings):
        raise MvpError('hybrid_scope', 'Each authorized source must be unambiguous.')
    allowed = {v.source_id: v for v in bindings}
    # Filter before looking at text, tokenizing, indexing or scoring. A caller
    # may provide a larger owned preparation; only the authorized subset enters.
    selected = [v for v in sources if v.id in allowed]
    if len(selected) != len(allowed) or len({v.id for v in selected}) != len(selected):
        raise MvpError('hybrid_source_missing', 'The exact bound source snapshot is unavailable; current preparation cannot substitute for it.')
    for source in selected:
        if source_binding(source) != allowed[source.id]:
            raise MvpError('hybrid_source_stale', 'A retained source differs from the authorized version or hashes. No ranking was performed.')
        if source.retained_content_utf8 is not None and sha256(source.retained_content_utf8.encode('utf-8')).hexdigest() != source.source_sha256:
            raise MvpError('hybrid_source_integrity', 'Retained raw source bytes do not match their exact source hash.')
        if source.blocks_sha256 != digest([b.model_dump(mode='json') for b in source.blocks]):
            raise MvpError('hybrid_source_integrity', 'Canonical block bytes do not match the exact retained source hash.')
        if source.source_type == 'none' and source.blocks:
            raise MvpError('hybrid_source_invalid', 'An unavailable source cannot supply canonical text.')
        if len({b.id for b in source.blocks}) != len(source.blocks):
            raise MvpError('hybrid_source_invalid', 'Canonical block identifiers must be unique within a source.')
    return sorted(selected, key=lambda value: (value.paper_id, value.id))


def _union_size(ranges):
    total, edge = 0, 0
    for start, end in sorted(ranges):
        total += max(0, end - max(edge, start))
        edge = max(edge, end)
    return total


def _ranges(text, limit, title, fits_document):
    def fits(title, passage):
        return budget_token_count(passage) <= 400 and (fits_document is None or fits_document(title, passage))
    start = 0
    while start < limit:
        hard_end = min(limit, start + MAX_WINDOW_CHARACTERS)
        endings = [m.end() for m in _SENTENCE_END.finditer(text, start, hard_end)]
        eligible = [v for v in endings if v-start >= MAX_WINDOW_CHARACTERS//3]
        end = hard_end if hard_end == len(text) or not eligible else eligible[-1]
        if text[start:end].strip() and not fits(title, text[start:end]):
            # A full title that cannot fit even beside a single evidence code
            # point is unsupported. Never silently shorten contextual metadata.
            # Tokenizers correctly reject whitespace-only evidence. Include the
            # first nonblank code point when probing the complete title budget,
            # retaining all preceding source whitespace and exact offsets.
            probe_end = next(i+1 for i in range(start, end) if not text[i].isspace())
            if not fits(title, text[start:probe_end]):
                if probe_end > start+1:
                    # A long blank prefix can exhaust tokens itself. Account
                    # for it as an exact blank range before scoring evidence.
                    yield start, probe_end-1, False
                    start = probe_end-1
                    continue
                raise MvpError('hybrid_document_budget', 'The complete title/document template cannot fit this profile. No title or evidence was silently truncated.')
            low, high = probe_end, end
            while low < high:
                middle = (low + high + 1)//2
                if fits(title, text[start:middle]):
                    low = middle
                else:
                    high = middle-1
            end = low
            # Prefer a complete word/sentence while retaining exact full cover.
            previous = [m.end() for m in re.finditer(r'\s+', text[start:end])]
            if previous and previous[-1] >= max(1, (end-start)//2):
                candidate = start+previous[-1]
                if fits(title, text[start:candidate]):
                    end = candidate
            if text[start:end].strip() and not fits(title, text[start:end]):
                raise MvpError('hybrid_document_budget', 'The complete document template failed its final token budget check.')
        split = (start > 0 and not text[start-1].isspace()) or (end < len(text) and end not in endings)
        yield start, end, split
        if end >= limit:
            break
        overlap = min(OVERLAP_CHARACTERS, (end-start)//4)
        start = max(start+1, end-overlap)


def build_inventory(sources, *, authorized_sources, titles=None, fits_document=None, cancelled=None):
    selected = scoped_sources(sources, authorized_sources)
    titles = titles or {}
    if any(not isinstance(titles.get(v.paper_id, ''), str) for v in selected):
        raise MvpError('hybrid_title', 'Pass complete paper titles as text metadata.')
    check_cancelled(cancelled)
    windows, ranges, omissions, limitations = [], defaultdict(list), [], []
    blocks = [(source, block) for source in selected for block in source.blocks]
    total_characters = sum(len(block.text) for _, block in blocks)
    scanned = 0
    for order, (source, block) in enumerate(blocks):
        check_cancelled(cancelled)
        if order >= MAX_SOURCE_BLOCKS:
            omissions.append('source_block_quota'); break
        remaining = MAX_SOURCE_CHARACTERS-scanned
        if remaining <= 0:
            omissions.append('source_character_quota'); break
        limit = min(len(block.text), remaining)
        if not block.text[:limit].strip():
            ranges[(source.id, block.id)].append((0, limit)); scanned += limit
            continue
        if any('table' in str(value).lower() for value in block.locator.values()):
            limitations.append('Parsed table text is indexed as retained; missing heading/unit/footnote relationships are not reconstructed or claimed understood.')
        for start, end, clipped in _ranges(block.text, limit, titles.get(source.paper_id, ''), fits_document):
            check_cancelled(cancelled)
            if len(windows) >= MAX_WINDOWS:
                omissions.append('window_quota'); break
            quote = block.text[start:end]
            if not quote.strip():
                # Blank ranges have no searchable evidence, but their exact
                # source coverage remains accounted for without model calls.
                ranges[(source.id, block.id)].append((start, end))
                continue
            identity = digest([source_binding(source).model_dump(mode='json'), block.id, start, end, quote])
            reference = BoardReference(id='hybrid-reference:'+identity, paper_id=source.paper_id,
                source_id=source.id, source_version=source.version, source_sha256=source.source_sha256,
                blocks_sha256=source.blocks_sha256, block_id=block.id, start=start, end=end,
                quote=quote, locator=block.locator)
            windows.append(HybridWindow(id='window:'+identity, reference=reference,
                title=titles.get(source.paper_id, ''), source_type=source.source_type,
                total_block_characters=len(block.text), split_sentence=clipped))
            ranges[(source.id, block.id)].append((start, end))
        scanned += limit
        if 'window_quota' in omissions:
            break
        if limit < len(block.text):
            omissions.append('source_character_quota'); break
    covered = sum(_union_size(v) for v in ranges.values())
    manifest = [source_binding(v) for v in selected]
    coverage = HybridCoverage(total_source_blocks=len(blocks), indexed_blocks=len(ranges),
        total_source_characters=total_characters, indexed_source_characters=covered,
        indexed_windows=len(windows), unindexed_characters=total_characters-covered,
        complete=covered==total_characters, omissions=list(dict.fromkeys(omissions)),
        limitations=list(dict.fromkeys(limitations)))
    data = dict(schema_version='mvp.hybrid-inventory.v1', windowizer=WINDOWIZER,
        source_manifest=[v.model_dump(mode='json') for v in manifest],
        source_snapshot_sha256=digest([v.model_dump(mode='json') for v in selected]),
        windows=[v.model_dump(mode='json') for v in windows], coverage=coverage.model_dump(mode='json'))
    return HybridInventory(**data, manifest_sha256=digest(data))
