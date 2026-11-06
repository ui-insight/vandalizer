"""Give an uncited claim in a knowledge-base answer the passage that holds it.

A KB answer cites its passages sentence by sentence ("[Source: § 200.421 ·
part 3]"), and the chips and the grader judge each citation against the
passage it names. On the final sweep of the shipped build (2026-11-05,
``runs/2026-11-05_sweep_18e58332``) 37% of claim sentences carried no citation
at all (2,102 of 5,381 under qwen, 36% under kimi), and a claim with no
citation is one the reader cannot check. Most of them are true: the grader
found a passage that states them for the great majority. The passage is in
the pool the model was given; the model simply did not write the marker.

This runs after the answer is final (the repair may have rewritten it) and
before the chips are derived, with the lexical test the chips use
(``citation_grounding``: every figure, date and quoted phrase of the claim on
the passage; a claim without anchors needs most of its content words there),
held to a stricter bar than the attached-document page pass: an anchorless
claim needs :data:`MIN_SHARE` of its content words on the passage, an
anchored one all its anchors and :data:`ANCHORED_MIN_SHARE` of its words, and
the passage must beat every passage of another section by :data:`MARGIN` in
word share. The 2026-11-04 study of the page pass's test on the KB rows
(``runs/2026-11-04_doc-page-citations_206a60e7``) put its precision at 89%
against the grader's own reading at the page pass's bar; the bar here is set
on the same rows (``runs/2026-11-06_kb-citation-attach_fe141a3d``). Headings,
questions, summaries, sentences about what the passages do not say, and
sentences already citing are left alone. Behind
``chat_config.kb_citation_attach_enabled`` (default off).
"""

import re
import time
from typing import Optional

from app.services import citation_grounding as cg
from app.services import doc_page_citations as dpc

VERSION = 1
KIND = "kb_citation_attach"
MAX_ATTACH = 20
# The bar, set on the 11-05 sweep's rows against the grader's own reading of each sentence
# (runs/2026-11-06_kb-citation-attach_fe141a3d): at 0.85 / 0.6 / 0.2, 911 citations on 1,515 answers, the
# grader's passage (or its section) 93.6% of the time under qwen and 98.1% under kimi; at the page pass's
# 0.6 / 0.3 / 0.15, 1,360 citations at 90.5% / 96.0%.
MIN_SHARE = 0.85          # an anchorless claim: share of its content words on the passage
ANCHORED_MIN_SHARE = 0.6  # an anchored claim: every anchor there, and this share of its words
MARGIN = 0.2              # over the best passage of any other section
MIN_STEMS = dpc.MIN_ATTACH_STEMS

# "[Source: § 200.421 · part 3]", "[Source: A; B]", "[S3]", "[S1, S3]".
CITE_RE = re.compile(r"\[(?:Source:\s*[^\[\]]{3,300}|S\d{1,2}(?:\s*[,;]\s*S?\d{1,2})*)\]")
_PART_RE = re.compile(r"\s*·\s*part\s+\d+\s*$", re.IGNORECASE)


def config(sys_config_doc: Optional[dict]) -> Optional[dict]:
    """The settings in ``chat_config``, or None when the step is off."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    if not bool(cfg.get("kb_citation_attach_enabled", False)):
        return None

    def share(key: str, default: float) -> float:
        try:
            return min(1.0, max(0.0, float(cfg.get(key) if cfg.get(key) is not None else default)))
        except (TypeError, ValueError):
            return default

    return {"min_share": share("kb_citation_attach_min_share", MIN_SHARE),
            "anchored_min_share": share("kb_citation_attach_anchored_min_share", ANCHORED_MIN_SHARE),
            "margin": share("kb_citation_attach_margin", MARGIN)}


def section_of(label: str) -> str:
    """A passage's section: its label without the trailing "· part N"."""
    return _PART_RE.sub("", label or "").strip().lower()


def index_sources(sources: list[dict]) -> list[dpc.PageIndex]:
    """One index per passage of the pool, in pool order; ``page`` carries the
    passage's position (1-based) and ``title`` its citation label. The
    lead-in the model was shown counts as part of the passage."""
    out = []
    for i, s in enumerate(sources or [], 1):
        text = " ".join(t for t in ((s.get("lead_in") or ""), (s.get("content") or "")) if t)
        label = s.get("label") or s.get("cite_label") or ""
        if text.strip() and label:
            out.append(dpc.PageIndex(str(s.get("chunk_id") or i), label, i, text))
    return out


def best_passage(claim: dpc.Claim, passages: list[dpc.PageIndex], *, min_share: float = MIN_SHARE,
                 anchored_min_share: float = ANCHORED_MIN_SHARE, margin: float = MARGIN) -> Optional[dpc.PageIndex]:
    """The passage that holds *claim* when one section wins outright: every
    anchor there and the share of words the bar asks; the best passage by
    (anchors, share), and no passage of another section within *margin* of
    its share (one of the same section is the same citation to the reader)."""
    scored = []
    for p in passages:
        s = dpc._score(claim, p, floor=anchored_min_share)
        if s is None:
            continue
        anchors, share = s
        if anchors == 0 and share < min_share:
            continue
        scored.append((s, p))
    if not scored:
        return None
    scored.sort(key=lambda sp: (-sp[0][0], -sp[0][1], sp[1].page))
    (best_anchors, best_share), best = scored[0]
    for (anchors, share), p in scored[1:]:
        if section_of(p.title) == section_of(best.title):
            continue
        if anchors == best_anchors and best_share - share < margin:
            return None
        break
    return best


def attach_citations(answer: str, sources: list[dict], *, min_share: float = MIN_SHARE,
                     anchored_min_share: float = ANCHORED_MIN_SHARE, margin: float = MARGIN) -> tuple[str, dict]:
    """``(answer, record)``: the answer with each uncited checkable claim
    given the one passage that holds it, as "[Source: <label>]" before the
    sentence's closing punctuation; the record says what was considered and
    attached. The answer comes back unchanged when nothing qualifies."""
    started = time.monotonic()
    record: dict = {"version": VERSION, "kind": KIND, "claims": 0, "attached": [], "ambiguous": 0,
                    "no_passage": 0, "changed": False}

    def done(text: str) -> tuple[str, dict]:
        record["changed"] = text != answer
        record["seconds"] = round(time.monotonic() - started, 3)
        return text, record

    passages = index_sources(sources)
    if not answer or not passages:
        return done(answer)
    inserts: list[tuple[int, str]] = []
    in_fence = False
    for start, end in cg._sentences(answer, CITE_RE):
        seg = answer[start:end]
        if seg.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or CITE_RE.search(seg):
            continue
        body = seg.strip()
        if not body or dpc._TABLE_SEP_RE.match(body) or dpc._HEADING_RE.match(body) or "?" in body:
            continue
        plain = dpc._MARKUP_RE.sub(" ", dpc._LEAD_RE.sub("", body))
        plain = cg._without_file_names(plain)
        if dpc._SKIP_START_RE.match(plain) or dpc._NEGATIVE_RE.search(plain):
            continue
        claim = dpc._claim(plain)
        if not claim.anchors and len(claim.stems) < MIN_STEMS:
            continue
        record["claims"] += 1
        best = best_passage(claim, passages, min_share=min_share, anchored_min_share=anchored_min_share,
                            margin=margin)
        if best is None:
            if any(dpc._score(claim, p, floor=anchored_min_share) is not None for p in passages):
                record["ambiguous"] += 1
            else:
                record["no_passage"] += 1
            continue
        inserts.append((dpc._insertion_point(answer, start, end), f" [Source: {best.title}]"))
        record["attached"].append({"ref": best.page, "label": best.title, "sentence": " ".join(plain.split())[:120]})
        if len(inserts) >= MAX_ATTACH:
            break
    text = answer
    for at, marker in sorted(inserts, reverse=True):
        text = text[:at] + marker + text[at:]
    return done(text)
