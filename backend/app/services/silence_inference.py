"""Find answers that turn "the sources don't say" into "it's allowed" (#1012).

The first measured RA run (#1005, docs/reviews/2026-10-08-ra-expected-checks.md)
passed every factual question. The only partial answers were about something
the sources do not address, and each read the silence as a rule:

* "The sponsor notice explicitly says it does not specify a page limit for the
  budget justification. → Therefore, the budget justification may be any
  length (no defined maximum)."
* "The notice does not require the PI to be a U.S. citizen; citizenship
  eligibility is not specified."

An RA who acts on "may be any length" can have a proposal returned when the
sponsor's general guide sets a limit. The chat rules now tell the model to
report the gap and send the reader to the sponsor; this check is the
backstop, like ``unsupported_figures``.

It flags a sentence only when **both** are present, in that sentence or the
one right after it:

* a statement that the sources are silent ("not specified", "does not
  state", "is silent on", "no … is stated"), and
* a conclusion drawn from that silence: unlimited, allowed, not required, or
  prohibited ("may be any length", "there is no limit", "does not require",
  "is permitted", "is not allowed").

A source that itself says "there is no page limit" yields an answer with the
conclusion but no silence marker, and is not flagged. Deliberately narrow:
missing an inference is better than nagging on every "not specified".
"""

import re

_MAX_FLAGS = 3
_MAX_CHARS = 220

_SILENCE = re.compile(
    r"\b(?:not|never)\s+(?:specif\w*|stated?|mention\w*|list(?:ed)?|address\w*|set|given|provided|included|defined|identif\w*)\b"
    r"|\b(?:does|do|did)\s*(?:not|n't)\s+(?:specif\w*|state|say|mention|list|address|set|give|provide|include|define|identify|establish)\b"
    r"|\b(?:is|are)\s+silent\b"
    r"|\bno\s+(?:\w+\s+){0,3}(?:is|are)\s+(?:specified|stated|mentioned|given|listed)\b"
    r"|\bnothing\s+(?:in|on)\s+the\b",
    re.IGNORECASE,
)

_CONCLUSION = re.compile(
    r"\bmay\s+be\s+(?:of\s+)?any\b"
    r"|\bany\s+length\b"
    r"|\b(?:no|without\s+(?:a|any))\s+(?:defined\s+|set\s+|maximum\s+|minimum\s+)?(?:limit|maximum|cap|restriction)s?\b(?!\s+(?:is|are)\s+(?:specified|stated|given|listed|mentioned))"
    r"|\bunlimited\b"
    r"|\b(?:is|are)\s+(?:therefore\s+)?(?:allowed|permitted|acceptable|unrestricted)\b"
    r"|\b(?:is|are)\s+not\s+(?:allowed|permitted|required|necessary|mandatory)\b"
    r"|\b(?:does|do)\s*(?:not|n't)\s+(?:require|need|restrict|limit|prohibit|bar|exclude)\b"
    r"|\bnot\s+(?:a\s+)?require(?:d|ment)\s+(?:to|for)\b"
    r"|\bfree\s+to\b"
    r"|\bcan\s+(?:use|include|submit|exceed)\s+(?:as\s+many|any)\b",
    re.IGNORECASE,
)

# A sentence ends at . ! ? followed by space and something that starts a new
# sentence, or at a line break. "U.S. citizen" and "e.g. a cap" stay whole.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[*_A-Z0-9→-])|\n+")
_LEADS_ON = re.compile(r"^\W*(?:→|therefore|so\b|thus|hence|this\s+means|that\s+means|meaning)", re.IGNORECASE)


_CITATION_MARKUP = re.compile(r"【[^】]*】|\[(?:p\.|pp\.|Source:)[^\]]*\]|\((?:see\s+)?[^()]*\bp\.\s*\d[^()]*\)")


def _clean(text: str) -> str:
    text = re.sub(r"[*_`#>]", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" -–—•")


def inferences_from_silence(answer: str) -> list[str]:
    """Sentences in *answer* that conclude a rule from the sources' silence.

    Returned as the answer's own text, trimmed, in order, at most three.
    """
    if not answer or not answer.strip():
        return []
    # Citation markup first: its "p." would otherwise end a sentence.
    text = _CITATION_MARKUP.sub(" ", answer)
    sentences = [_clean(s) for s in _SENTENCE_END.split(text)]
    sentences = [s for s in sentences if s]
    flagged: list[str] = []
    for i, sentence in enumerate(sentences):
        if not _SILENCE.search(sentence):
            continue
        conclusion = None
        if _CONCLUSION.search(_SILENCE.sub(" ", sentence)):
            conclusion = sentence
        elif i + 1 < len(sentences) and _LEADS_ON.search(sentences[i + 1]) and _CONCLUSION.search(sentences[i + 1]):
            conclusion = f"{sentence} {sentences[i + 1]}"
        if conclusion and conclusion not in flagged:
            flagged.append(conclusion[:_MAX_CHARS])
        if len(flagged) >= _MAX_FLAGS:
            break
    return flagged
