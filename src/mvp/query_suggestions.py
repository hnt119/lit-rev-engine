"""Local, deterministic keyword starting points; never a search or a protocol.

This deliberately small parser preserves explicit strategies. For natural language
it retains phrases from the question, removes question framing, and groups nearby
listed alternatives. It does not invent MeSH terms, synonyms, or populations.
"""

from dataclasses import dataclass
import re
import unicodedata

from .contracts import QuerySuggestion


# Recognizing syntax is not validating PubMed's field names or Boolean grammar.
_FIELD_TAG = re.compile(r"\[[^\[\]\r\n]+\]")
_BOOLEAN = re.compile(r"\S\s+\b(?:AND|OR|NOT)\b\s+\S")
_WORD = re.compile(r"[^\W_]+(?:[.'’][^\W_]+)*", re.UNICODE)

# These phrases protect boundaries and identify nearby alternatives, rather than
# expanding the question into a specialist search strategy. Unknown terms still
# pass through the residual-phrase path below. Longer matches always win.
_PHRASES = {
    "topic": (
        r"(?:gut|intestinal|gastrointestinal|oral|vaginal)\s+(?:microbiome|microbiota|flora)",
        r"(?:gut\s+)?microbial\s+metabolites?", r"short\s+chain\s+fatty\s+acids?",
        r"microbiome", r"microbiota", r"estrobolome", r"equol",
    ),
    "population": (
        r"(?:pregnant|postmenopausal|perimenopausal|premenopausal|older|elderly|adult|adolescent|young)\s+(?:women|females?)",
        r"reproductive\s+age\s+women", r"women", r"woman", r"females?",
        r"men", r"males?", r"children", r"adolescents?", r"adults?",
    ),
    "geography": (
        r"(?:south\s*east|east|south|central|west|western|eastern|southeastern)\s+asians?",
        r"(?:south\s*east|east|south|central|west)\s+asia", r"asians?", r"asia",
        r"sri\s+lankan?", r"hong\s+kong", r"south\s+korea", r"north\s+korea",
        r"chinese", r"japanese", r"korean", r"indian", r"malaysian", r"malay",
        r"pakistani", r"bangladeshi", r"thai", r"vietnamese", r"indonesian",
        r"filipino", r"singaporean?", r"iranian", r"kazakh", r"uzbek", r"nepali",
        r"china", r"japan", r"korea", r"india", r"malaysia", r"pakistan",
        r"bangladesh", r"thailand", r"vietnam", r"indonesia", r"philippines",
        r"singapore", r"iran", r"kazakhstan", r"uzbekistan", r"nepal",
    ),
    "exposure": (
        r"(?:high\s+)?(?:fibre|fiber)\s+(?:intake|diet)", r"(?:mediterranean|western)\s+diet",
        r"dietary\s+(?:patterns?|intake|habits?|interventions?)", r"environmental\s+exposures?",
        r"air\s+pollution", r"endocrine\s+disruptors?", r"physical\s+activity",
        r"diet", r"dietary", r"exposome", r"probiotics?", r"prebiotics?",
        r"antibiotics?", r"exercise", r"smoking", r"alcohol",
    ),
    "outcome": (
        r"reproductive\s+(?:longevity|lifespan|aging|ageing|health)",
        r"ovarian\s+(?:aging|ageing|reserve)", r"(?:healthy|successful)\s+(?:aging|ageing)",
        r"gyn(?:a?ecological|a?ecologic)\s+diseases?", r"gynecological\s+diseases?",
        r"gestational\s+diabetes", r"type\s+[12]\s+diabetes", r"diabetes\s+mellitus",
        r"polycystic\s+ovary\s+syndrome", r"primary\s+ovarian\s+insufficiency",
        r"premature\s+ovarian\s+(?:failure|insufficiency)", r"premature\s+menopause",
        r"age\s+at\s+menopause", r"menopause\s+timing", r"menopausal\s+symptoms?",
        r"anti\s+mullerian\s+hormone", r"antral\s+follicle\s+count",
        r"bone\s+mineral\s+density", r"blood\s+pressure", r"skeletal\s+muscle",
        r"physical\s+function", r"side\s+effects?", r"sleep\s+quality",
        r"endometriosis", r"pcos", r"infertility", r"fertility", r"menopause",
        r"perimenopause", r"postmenopause", r"healthspan", r"inflammage?ing",
        r"frailty", r"sarcopenia", r"osteoporosis", r"fractures?", r"obesity", r"diabetes",
    ),
}
_PATTERNS = tuple(
    (kind, re.compile(r"(?<!\w)(?:" + phrase + r")(?!\w)", re.IGNORECASE))
    for kind, phrases in _PHRASES.items() for phrase in phrases
)

# Framing words also split unknown noun phrases, avoiding an arbitrary word cap.
# No terms are dropped because the question is long or a topic is unfamiliar.
_FRAMING = frozenset("""
a an the what which who whose when where why how whether can could should would
will may might do does did is are was were be been being have has had it its this
that these those their they them there our your my we you i me us about of in on at to
for from by with within without among amongst across through into during after
before between versus vs than and or but nor as such any some all both each either
also only particularly especially mainly specifically preferably preferred prefer
please tell show explain find identify describe explore investigate examine evaluate
assess study studies studied studying source sources report reports reported reporting
paper papers research question questions review reviews systematic scoping literature
relationship relationships relation relations relate relates related relating association
associations associated associate affect affects affected affecting effect effects impact
impacts influence influences influencing improve improves improving improved change changes
changing contribute contributes contribution linked link links correlation correlations
correlated result results evidence role roles suggest suggests understand understanding
happen happens happening compare compares compared comparing comparison differences difference
originating originate originated recruited recruitment living lives live based concerning
regarding including include includes included involve involves involving possible potentially
other factors factor if best better worse good promote promotes promoted promoting
patients patient participants participant subjects subject cohorts cohort
women's woman's
""".split())
_NEGATION = re.compile(r"\b(?:not|no|never|without|excluding|exclude|except|non(?=[-\s]))\b", re.IGNORECASE)
_COMPARISON = re.compile(r"\b(?:versus|vs|compared|compare|comparison|better|worse|difference|differences|than)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Concept:
    text: str
    kind: str
    start: int
    end: int


def _normalize(question: str) -> str:
    return re.sub(r"[\-‐‑‒–—]", " ", unicodedata.normalize("NFKC", question)).replace("’", "'")


def _separate_preferences(text: str) -> tuple[str, list[str]]:
    """Do not turn a trailing preference note into a mandatory search group.

    Only separate later sentences or an explicitly introduced trailing clause;
    the main question is always retained. The removed text remains in the
    explanation, so regional preferences can guide human screening.
    """
    spans: list[tuple[int, int]] = []
    preference = re.compile(r"\b(?:prefer|preferred|prefers|preferably|preference)\b", re.IGNORECASE)
    for sentence in re.finditer(r"[^.!?;]+(?:[.!?;]|$)", text):
        if sentence.start() > 0 and preference.search(sentence.group()):
            spans.append(sentence.span())
    for clause in re.finditer(
        r"[,;]\s*(?:preferably|with\s+(?:a\s+)?preference\s+for|would\s+prefer|prefer)\b[^.!?;]*",
        text, re.IGNORECASE,
    ):
        spans.append(clause.span())
    for clause in re.finditer(
        r"\bwith\s+(?:a\s+)?preference\s+for\b[^.!?;]*|"
        r"\([^()]*\b(?:prefer|preferred|preferably|preference)\b[^()]*\)|"
        r",[^,.!?;]*\b(?:preferred|preferable)\b[^,.!?;]*",
        text, re.IGNORECASE,
    ):
        spans.append(clause.span())
    if not spans:
        return text, []
    notes: list[str] = []
    chars = list(text)
    for start, end in sorted(spans):
        note = text[start:end].strip(" ,;.!?\t\n")
        if note and note not in notes:
            notes.append(note)
        chars[start:end] = " " * (end - start)
    return "".join(chars), notes


def _extract(text: str) -> list[_Concept]:
    candidates = [
        _Concept(" ".join(match.group().split()), kind, match.start(), match.end())
        for kind, pattern in _PATTERNS for match in pattern.finditer(text)
    ]
    selected: list[_Concept] = []
    for candidate in sorted(candidates, key=lambda item: (-(item.end - item.start), item.start)):
        if not any(candidate.start < item.end and item.start < candidate.end for item in selected):
            selected.append(candidate)
    selected.sort(key=lambda item: item.start)

    # Split residual text on known concepts, framing, and punctuation. Preserve
    # contiguous unknown terms as a phrase, rather than AND-ing every word.
    residual: list[_Concept] = []
    boundaries = [(-1, 0), *((item.start, item.end) for item in selected), (len(text), len(text))]
    for (_, start), (end, _) in zip(boundaries, boundaries[1:]):
        words: list[re.Match[str]] = []
        def flush() -> None:
            if words:
                residual.append(_Concept(" ".join(item.group() for item in words), "keyword", words[0].start(), words[-1].end()))
                words.clear()
        for match in _WORD.finditer(text, start, end):
            token = match.group()
            if token.casefold() == "s" and match.start() > 0 and text[match.start() - 1] == "'":
                flush()
                continue
            if token.casefold() in _FRAMING or token.casefold() in {"not", "no", "never", "exclude", "excluding", "except", "non"}:
                flush()
                continue
            if words and text[words[-1].end():match.start()].strip():
                flush()
            words.append(match)
        flush()
    return sorted([*selected, *residual], key=lambda item: item.start)


def _listed(left: _Concept, right: _Concept, text: str) -> bool:
    between = text[left.end:right.start]
    words = [match.group().casefold() for match in _WORD.finditer(between)]
    # A bare 'or' expresses alternatives even for unfamiliar concepts. For other
    # lists require the same recognized role and only list separators between.
    return bool(between.strip()) and (
        words == ["or"] or
        (left.kind == right.kind and left.kind != "keyword" and
         all(word in {"and", "or", "other"} for word in words) and
         bool(re.search(r"[,;/]|\b(?:and|or)\b", between, re.IGNORECASE)))
    )


def _render(concepts: list[_Concept], text: str) -> tuple[str, list[list[_Concept]]]:
    groups: list[list[_Concept]] = []
    for concept in concepts:
        if groups and _listed(groups[-1][-1], concept, text):
            groups[-1].append(concept)
        else:
            groups.append([concept])
    seen: set[str] = set()
    distinct_groups: list[list[_Concept]] = []
    for group in groups:
        unique: list[_Concept] = []
        for concept in group:
            key = concept.text.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(concept)
        if unique:
            distinct_groups.append(unique)
    def render_phrase(concept: _Concept) -> str:
        return f"({concept.text})" if " " in concept.text else concept.text
    return " AND ".join(
        "(" + " OR ".join(render_phrase(concept) for concept in group) + ")"
        if len(group) > 1 else render_phrase(group[0])
        for group in distinct_groups
    ), distinct_groups


def suggest_pubmed_query(question: str) -> QuerySuggestion:
    """Extract a minimal editable keyword query; preserve explicit strategies."""
    if _FIELD_TAG.search(question) or _BOOLEAN.search(question):
        return QuerySuggestion(
            query=question,
            explanation=(
                "Your structured query was preserved exactly. It has not been validated; "
                "no live PubMed call was made. Review PubMed's translation and warnings "
                "after an explicit search."
            ),
        )
    normalized, preferences = _separate_preferences(_normalize(question))
    query, groups = _render(_extract(normalized), normalized)
    if not query:
        return QuerySuggestion(
            query="",
            explanation=(
                "No substantive keywords were found after removing question framing. "
                "Add a topic, population, exposure, or outcome before applying a proposal. "
                "No live PubMed call was made."
            ),
        )
    # Never offer an Apply action that cannot satisfy SearchRequest's limit.
    # Refuse the whole proposal rather than silently discarding named concepts.
    if len(query) > 20000:
        return QuerySuggestion(
            query="",
            explanation=(
                f"The extracted query would contain {len(query)} characters, exceeding "
                "the 20,000-character search limit. Reduce or split the research question "
                "before proposing again; no concepts were silently truncated and no live "
                "PubMed call was made."
            ),
        )
    description = "; ".join(" OR ".join(concept.text for concept in group) for group in groups)
    caveat = ""
    if preferences:
        caveat += (
            " Preference notes retained for manual screening, not mandatory search restrictions: "
            + "; ".join(preferences) + "."
        )
    negation_text = re.sub(r"\bwhether\s+or\s+not\b", "", question, flags=re.IGNORECASE)
    if _NEGATION.search(negation_text):
        caveat += " Negation was not translated into NOT; check exclusions manually."
    if _COMPARISON.search(question):
        caveat += " Comparison direction was not encoded; check the groups manually."
    return QuerySuggestion(
        query=query,
        explanation=(
            f"Keywords retained from your question: {description}. "
            "AND joins distinct concepts; OR joins nearby listed alternatives. "
            "Question framing was removed; multiword concepts are parenthesized without "
            "quotes or field tags so PubMed can apply automatic term mapping. "
            "No synonyms, countries, or MeSH terms were added. This deterministic starting "
            "point may misread unfamiliar phrasing; review every group and PubMed's "
            "translation and warnings. It is not a complete systematic-review strategy "
            "and has not been validated; no live PubMed call was made." + caveat
        ),
    )
