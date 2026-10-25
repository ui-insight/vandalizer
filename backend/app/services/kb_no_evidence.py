"""A knowledge-base chat turn with no evidence: say so, never recall.

When every attached knowledge base returned nothing for a message, chat used
to fall into rules that allowed "general questions from your own knowledge".
Measured over 505 questions on 14 knowledge bases (2026-10-23): 19% of the
answerable questions retrieved nothing, and the model then answered from
memory 89% of the time, uncited, unchecked and never once correct; 23 of 23
development questions the bases cannot answer got an answer from memory, some
with invented or superseded specifics ("due 30 days after the award year", a
"15%" cap, a "$215,000" salary cap). A wrong answer with no source behind it
reads exactly like a right one with a source.

So a turn without evidence refuses: it says what was searched, that nothing
there matched, and how to ask so a passage can match — and it states no rule,
requirement, figure or procedure from memory. The turn's rules
(``llm_service.PROJECT_KB_EMPTY_RULES``) ask the model for that, but a prompt
cannot make a model comply, so the finished answer is read before anyone sees
it (chat holds it back while the model writes) and :func:`leaked_statements`
lists what it says that no source behind this turn gave it: not the
conversation so far, not a tool result, not the knowledge bases' own source
list. An answer that leaks anything is replaced by :func:`refusal`. A turn in
which the agent's own knowledge-base search did return passages has evidence
after all, and is answered and checked like any other.

Requests that need nothing from a knowledge base — reshaping an earlier
answer, drafting from the conversation, a greeting — are still answered: what
they say is either carried over from the conversation or, for a drafting
request, held only to stating no rule or figure of its own.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from app.services.kb_answer_grounding import _content_words, unsupported_figures

# A clause needs this share of its content words in the turn's sources to
# count as carried over (an earlier answer reshaped into a table or a shorter
# list keeps nearly all of its words; a rule recalled from memory keeps few).
CARRIED_SHARE = 0.6
# A clause with fewer content words than this says nothing to check
# ("Sure.", "Here is the table:").
MIN_CONTENT_WORDS = 4

# A suggestion passes only when it adds at most this many words of its own,
# outside its quoted examples: words that are not about searching and asking
# (_PROCESS_WORDS), not the question's, and not carried over. "Try asking
# about the disclosure timelines" adds one; "try asking OSP, who approves
# rebudgeting under 25 percent" adds more.
MAX_NEW_WORDS = 2

# A clause that reports the search came up empty ("I couldn't find …",
# "no passage matched", "I'm not seeing any passages", "I don't have the
# policy wording"), or that a source does not cover something ("the
# knowledge base does not state …"). The second kind needs a word for the
# source in the clause: "is not included in MTDC" states a rule.
_NOT_FOUND_RE = re.compile(
    r"\b(?:(?:(?:could|did|was|were|is|are|have|has)\s*(?:n['’]t|\s+not)|ca(?:n['’]t|nnot|n\s+not)|am\s+not)"
    r"(?:\s+(?:been\s+)?able\s+to)?\s+"
    r"(?:find|locate|retrieve|match|see|pull|confirm|verify|identify|surface|return|turn\s+up|be\s+found|tell|"
    r"say|determine|answer|point\s+to|quote|cite)|i\s+do(?:n['’]t|\s+not)\s+have|"
    r"(?:not|n['’]t)\s+(?:seeing|finding|getting)|cannot\s+(?:find|locate|confirm|verify)|(?:unable|not\s+able)\s+to|"
    r"nothing\s+(?:was\s+|came\s+up|in\b|there\b|matched|that\b|about\b|found|retrieved|relevant)|"
    r"no\s+(?:specific\s+|relevant\s+|matching\s+)?(?:policy\s+)?(?:passages?|snippets?|results?|match(?:es)?|"
    r"text|information|content|guidance|excerpts?|sources?)\b|none\s+of\s+(?:the|those|these|its|them)\b|"
    r"not\s+(?:found|retrieved|returned)|(?:returned|found|yielded|surfaced)\s+(?:nothing|no\b)|"
    r"did\s*(?:n['’]t|\s+not)\s+(?:return|yield|surface|bring\s+up|turn\s+up))",
    re.IGNORECASE,
)
# The clause is about the search or the next step, not the subject.
_META_RE = re.compile(
    r"\b(?:let\s+me|i\s+can\s+then|we\s+can|will\s+let\s+me|so\s+(?:i|we)\s+can|i['’]ll\s+be\s+able|"
    r"to\s+give\s+you|to\s+answer\s+(?:this|your|that)|i\s+can\s+(?:retrieve|search|look|pull|answer|help))\b",
    re.IGNORECASE,
)
_NOT_COVERED_RE = re.compile(
    r"\b(?:(?:does|do|did)\s*(?:n['’]t|\s+not)\s+(?:state|say|contain|cover|address|mention|include|list|"
    r"specify|discuss|hold|have|define|describe|provide|appear)|(?:is|are)\s*(?:n['’]t|\s+not)\s+(?:in|part\s+of|"
    r"among|covered|included|listed|mentioned|stated|addressed)|not\s+(?:covered|stated|mentioned|listed|"
    r"included|addressed|present))\b",
    re.IGNORECASE,
)
_SOURCE_WORD_RE = re.compile(
    r"\b(?:knowledge[\s-]bases?|kbs?|sources?|passages?|snippets?|documents?|retriev\w*|search\w*|results?|"
    r"stored|connected|attached|selected|the\s+text|this\s+chat)\b",
    re.IGNORECASE,
)
# "… generally, NSF requires …" in a clause about the search is content
# again. ("But …" opens a clause of its own, see _CLAUSE_RE.)
_CONTRAST_RE = re.compile(
    r"\b(?:generally|typically|usually|commonly|normally|in\s+general|often|standard|common\s+practice|"
    r"most\s+(?:agencies|sponsors|institutions|universities))\b",
    re.IGNORECASE,
)
# The clause tells the user how to ask or where to look ("Try naming …",
# "Using an exact phrase in quotes …", "If you're after X, mention …").
_SUGGESTION_RE = re.compile(
    r"(?:^|[—–]\s*)\W*(?:(?:please|but|you\s+(?:can|could|may|might)(?:\s+also)?(?:\s+(?:want|need)\s+to)?|i\s+(?:can|could|suggest|"
    r"recommend)|or|and|by|then|also|first|next)\s+|(?:if|to|for|when|once)\b.*?,\s*)*(?:try(?:ing)?|ask(?:ing)?|"
    r"re-?ask|rephras(?:e|ing)|re-?word(?:ing)?|nam(?:e|ing)|search(?:ing)?|check(?:ing)?|consult(?:ing)?|"
    r"contact(?:ing)?|open(?:ing)?|upload(?:ing)?|add(?:ing)?|includ(?:e|ing)|specify(?:ing)?|us(?:e|ing)|"
    r"look(?:ing)?|refer(?:ring)?|referenc(?:e|ing)|provid(?:e|ing)|attach(?:ing)?|select(?:ing)?|quot(?:e|ing)|"
    r"mention(?:ing)?|giv(?:e|ing)|confirm(?:ing)?|verify(?:ing)?|retry(?:ing)?|wait(?:ing)?|shar(?:e|ing)|"
    r"ensur(?:e|ing)|(?:make|be)\s+sure|double-?check(?:ing)?|consider(?:ing)?|phras(?:e|ing)|pinpoint(?:ing)?|"
    r"plac(?:e|ing)|re-?upload(?:ing)?|cit(?:e|ing)|point\s+me|let\s+me\s+know)\b",
    re.IGNORECASE,
)
# Words about searching, sources and asking, which a refusal is made of.
_PROCESS_WORDS = _content_words(
    "knowledge base bases kb kbs passage passages snippet snippets excerpt excerpts source sources document "
    "documents file files text content search searched searching query queries retrieve retrieved retrieval "
    "find found finding locate located pull pulled return returned returning match matched matching index "
    "indexed indexing section sections part parts subpart subparts chapter appendix paragraph policy policies "
    "title titles phrase phrases quote quotes quoted exact exactly wording word words language name names named "
    "naming mention mentioned specific relevant question questions answer answers ask asking rephrase try retry "
    "confirm verify upload uploaded add added connected attached selected see seeing check look open give "
    "provide help need needs want know let able unable show address addresses addressed cover covers covered "
    "contain contains include includes included state states stated say says said discuss describe list detail "
    "details information guidance precise particular related refer referring reference referencing using use "
    "focus identify identified finish finished recent recently earlier again current wait moment project chat "
    "here there now then once still also just might likely possibly perhaps please sure sorry unfortunately "
    "appear appears seem seems available access back get got make way thing something anything nothing "
    "yielded yield surface surfaced lookup look-up exact-text double connected official website force "
    "term terms sentence sentences clause clauses used heading headings page pages system like "
    # What a refusal names as the thing it could not find.
    "rule rules requirement requirements approval approvals restriction restrictions limit limits deadline "
    "deadlines threshold thresholds condition conditions procedure procedures process step steps regulation "
    "regulations guideline guidelines general office officer contact"
)
# Periods a stale memory gets wrong ("30 days", "six years"). Money and
# percentages are compared by value (kb_answer_grounding.unsupported_figures).
_PERIOD_RE = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|thirty|sixty|ninety)\s*"
    r"(?:-\s*)?(?:calendar\s+|business\s+|working\s+)?(?:days?|weeks?|months?|years?|hours?)\b",
    re.IGNORECASE,
)
# Words that make a clause a rule.
_RULE_RE = re.compile(
    r"\b(?:must|shall|required?|requires|mandatory|obligat\w*|prohibit\w*|forbid\w*|"
    r"(?:un)?allowable|allowed|permitted|permissible|(?:in)?eligib\w*|exempt\w*|needs?\s+to|ha(?:s|ve)\s+to|"
    r"may\s+not|deadline|no\s+later\s+than|prior\s+(?:written\s+)?approval|threshold|not\s+exceed|"
    r"at\s+least|at\s+most|up\s+to)\b",
    re.IGNORECASE,
)
# A request to work on what the conversation already holds, or to write
# something new from it, rather than a question for the knowledge base.
_TASK_RE = re.compile(
    r"^\W*(?:(?:please|ok(?:ay)?|now|thanks?|great)[,!.\s]+)*(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
    r"(?:draft|write|compose|rewrite|re-?word|proofread|edit|translate|format|re-?format|shorten|condense|"
    r"simplify|expand|tidy|clean\s+up|turn|convert|put|make|summari[sz]e\s+(?:this|that|it|the\s+above|your|"
    r"what)|list\s+(?:them|those|these)|bullet)\b",
    re.IGNORECASE,
)
_MARKUP_RE = re.compile(r"[*_`#>|]+")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[\"“(\[]?[A-Z0-9§])")
# Clauses are read one by one, so "it doesn't say; you must …" or "nothing
# was found, and the limit is …" cannot hide a rule behind a report.
_CLAUSE_RE = re.compile(
    r"\s*[;:]\s+|,\s*(?=(?:and|but|so|while|whereas|which|because|however|although|though)\b)|"
    r"\s+(?=(?:but|however|although|whereas)\b)",
    re.IGNORECASE,
)
# Quoted titles and parenthesised examples in a suggestion ("e.g., “Subpart
# D—Post Federal Award Requirements”") name things; they state no rule.
_QUOTED_RE = re.compile(r"\([^()]*\)|“[^”]*”|\"[^\"]*\"|‘[^’]*’")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")


def is_task_request(message: str) -> bool:
    """Whether *message* asks to reshape or draft rather than to be told something."""
    return bool(_TASK_RE.search((message or "").strip()))


def asks_for_web(message: str) -> bool:
    """Whether the user asked for a web search themselves."""
    return bool(re.search(r"\b(?:web|internet|online|google|search\s+engine)\b", message or "", re.IGNORECASE))


def _clauses(answer: str) -> list[str]:
    out: list[str] = []
    for line in (answer or "").splitlines():
        line = _BULLET_RE.sub("", _MARKUP_RE.sub(" ", line)).strip()
        if not line or set(line) <= set("-:| "):
            continue
        for sentence in _SENTENCE_END_RE.split(line):
            out.extend(c.strip() for c in _CLAUSE_RE.split(sentence) if c and c.strip())
    return out


def _reports_absence(clause: str) -> bool:
    """Whether *clause* says what the search did not find, or that a source
    does not cover something. What it names as not found is the question's
    subject in other words, so any words may follow."""
    return bool(_NOT_FOUND_RE.search(clause)) or bool(
        _NOT_COVERED_RE.search(clause) and _SOURCE_WORD_RE.search(clause)
    )


def _suggests(clause: str, own: set[str]) -> bool:
    """Whether *clause* says how to ask or what comes next, states no rule
    after its verb ("you may need to consult …" is how it opens; "check with
    OSP, since approval is required" is a rule), and adds no more than
    :data:`MAX_NEW_WORDS` of *own* words outside its quoted examples."""
    m = _SUGGESTION_RE.search(clause) or _META_RE.search(clause)
    if not m:
        return False
    rest = _QUOTED_RE.sub(" ", clause[m.end():])
    return not _RULE_RE.search(rest) and len(_content_words(_QUOTED_RE.sub(" ", clause)) & own) <= MAX_NEW_WORDS


def _new_figures(clause: str, sources: str, lowered: str) -> bool:
    if unsupported_figures(clause, sources):
        return True
    return any(" ".join(m.group(0).lower().split()) not in lowered for m in _PERIOD_RE.finditer(clause))


def leaked_statements(answer: str, *, message: str, carried: Iterable[str] = ()) -> list[str]:
    """The clauses of a no-evidence *answer* that no source of this turn gave it.

    *carried* is everything the answer may draw on without retrieval: earlier
    messages of the conversation (both sides), what tools returned this turn,
    and the knowledge bases' status and source list. A clause that adds a
    figure leaks. Otherwise it passes when it is too short to say anything; is
    carried over (most of its words are in there); reports what the search
    did not find; suggests how to ask or what comes next (see
    :func:`_suggests`); or is made only of words about searching and of
    carried words ("that will help surface the passage you need"). For a
    drafting or reshaping request (:func:`is_task_request`) new wording is
    the point, so only a clause that adds a rule leaks.

    The question itself is not a source: "allegations have no time limit"
    shares nearly every word with "is there a time limit on allegations?" and
    answers it from memory. Its words may be repeated in a clause about the
    search ("nothing addresses time limits on allegations"), and it excuses a
    figure it states ("is it $5,000 or $10,000?"). "… but generally …" makes
    any clause content again.
    """
    history = "\n".join(carried)
    with_question = f"{message or ''}\n{history}"
    lowered = " ".join(with_question.lower().split())
    vocab = _content_words(history)
    asked = _content_words(message or "")
    task = is_task_request(message)
    leaks: list[str] = []
    for clause in _clauses(answer):
        if _new_figures(clause, with_question, lowered):
            leaks.append(clause)
            continue
        words = _content_words(clause)
        if len(words) < MIN_CONTENT_WORDS:
            continue
        if len(words & vocab) / len(words) >= CARRIED_SHARE:
            continue
        if not _CONTRAST_RE.search(clause):
            if _reports_absence(clause) or _suggests(clause, words - _PROCESS_WORDS - asked - vocab):
                continue
            plain = _QUOTED_RE.sub(" ", clause)
            if not _RULE_RE.search(plain) and not (_content_words(plain) - _PROCESS_WORDS - vocab):
                continue
        if task and not _RULE_RE.search(clause):
            continue
        leaks.append(clause)
    return leaks


def _names(kb_titles: list[str]) -> str:
    titles = [f"“{t}”" for t in dict.fromkeys(t.strip() for t in kb_titles if t and t.strip())]
    if not titles:
        return "the attached knowledge base"
    if len(titles) == 1:
        return f"the knowledge base {titles[0]}"
    return "the knowledge bases " + ", ".join(titles[:-1]) + f" and {titles[-1]}"


def refusal(kb_titles: list[str]) -> str:
    """What a no-evidence turn says when the model's own answer leaked."""
    several = len({t for t in kb_titles if t and t.strip()}) > 1
    return (
        f"I couldn't find this in {_names(kb_titles)}. Nothing there matched the question, so I won't "
        "answer it from general knowledge: a rule or figure recalled from memory can be out of date or wrong.\n\n"
        "- Ask again naming the section, part or policy number, or using the wording the source itself uses.\n"
        f"- If the regulation or policy you need is not among {'their' if several else 'its'} sources, this chat "
        f"can't answer it from {'them' if several else 'it'}."
    )


def kb_evidence(citations: Iterable[dict]) -> bool:
    """Whether any citation this turn is a knowledge-base passage (web pages
    and fetched URLs carry no chunk id)."""
    return any(c.get("chunk_id") for c in citations or [] if isinstance(c, dict))


def enforce(
    answer: str, *, message: str, carried: Iterable[str], kb_titles: list[str],
) -> tuple[str, list[str]]:
    """``(answer to show, leaked clauses)``: the model's answer when it
    leaked nothing, else :func:`refusal`."""
    leaks = leaked_statements(answer, message=message, carried=carried)
    return (refusal(kb_titles) if leaks or not (answer or "").strip() else answer), leaks


def kb_titles_of(entries: Optional[list[dict]], active_kbs: list[tuple[str, str]]) -> list[str]:
    """Titles of the attached knowledge bases, from the status entries when
    loaded (they carry the stored title), else from what the turn was given."""
    titles = [e.get("title") or "" for e in entries or []]
    return titles if any(titles) else [t for _, t in active_kbs]
