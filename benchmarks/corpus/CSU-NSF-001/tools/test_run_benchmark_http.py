"""Tests for the harness's pure functions — the parts that decide a row.

The harness cannot be tested end to end here: it needs a live deployment and
real GPU time, which is why nothing under `.github/workflows/` invokes it. But
everything that shapes a row *before* the network is reached is a pure
function, and two review findings lived in exactly those functions — a silently
narrowed abstention vocabulary, and a routing diagnostic that reported "no"
where it meant "unknown". Both are pinned below.

No network is touched, no credentials are read from the ambient environment,
and nothing here uploads anything.

Run: cd backend && uv run --with pytest pytest \\
       ../benchmarks/corpus/CSU-NSF-001/tools/test_run_benchmark_http.py -q
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pytest.importorskip("requests", reason="the harness imports requests at module scope")

import run_benchmark_http as harness  # noqa: E402
from score import REFUSAL, normalise  # noqa: E402

KEY = json.loads((Path(__file__).parent.parent / "ground_truth.json").read_text())


# --------------------------------------------------------------------------
# Argument parsing — the defaults the README documents
# --------------------------------------------------------------------------


class TestArgumentParsing:
    """Every flag the corpus README names has to exist with the documented
    default, because the README's reproduction block is pasted verbatim."""

    def test_documented_defaults(self):
        args = harness.build_parser().parse_args([])
        assert args.mode == "attach"
        assert args.out_dir == Path("benchmark-runs")
        assert args.keys == harness.KEYS_DEFAULT
        assert args.label == "csu-nsf-001-bench"
        assert args.repeat == 1
        assert args.pace == 2.5
        assert args.timeout == 900
        assert args.questions == "all"
        assert args.warmup is False
        assert args.preflight_only is False
        assert args.admin_config is False
        assert args.model is None
        assert args.run_id is None
        assert args.state is None

    def test_the_published_invocation_parses(self):
        args = harness.build_parser().parse_args([
            "--assets-dir", "/tmp/corpus-assets", "--mode", "kb",
            "--model", "some-tag", "--repeat", "3", "--pace", "2.5",
            "--timeout", "900", "--warmup", "--run-id", "20260101T000000Z",
        ])
        assert (args.mode, args.model, args.repeat, args.warmup) == \
            ("kb", "some-tag", 3, True)
        assert args.assets_dir == Path("/tmp/corpus-assets")

    def test_an_unknown_mode_is_rejected(self):
        with pytest.raises(SystemExit):
            harness.build_parser().parse_args(["--mode", "everything"])

    def test_every_offered_mode_maps_to_a_docset(self):
        """`--mode` and `DOCSET_FOR_MODE` are read from each other at run
        time; a mode offered with no docset would KeyError on line one."""
        parser = harness.build_parser()
        modes = next(action for action in parser._actions
                     if action.dest == "mode").choices
        assert set(modes) == set(harness.DOCSET_FOR_MODE)


class TestCredentials:
    def test_missing_credentials_exit_cleanly(self, monkeypatch):
        for key in ("VANDALIZER_URL", "VANDALIZER_USER", "VANDALIZER_PASS"):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(SystemExit) as excinfo:
            harness.load_credentials(None, None)
        assert "missing credential(s)" in str(excinfo.value)

    def test_an_env_file_seeds_and_the_environment_wins(self, tmp_path,
                                                        monkeypatch):
        env_file = tmp_path / "bench.env"
        env_file.write_text(
            "# a comment\n"
            "VANDALIZER_URL=http://from-file.invalid\n"
            "VANDALIZER_USER=file-user\n"
            "VANDALIZER_PASS=file-pass\n")
        monkeypatch.delenv("VANDALIZER_URL", raising=False)
        monkeypatch.setenv("VANDALIZER_USER", "env-user")
        monkeypatch.delenv("VANDALIZER_PASS", raising=False)
        values = harness.load_credentials(env_file, None)
        assert values["VANDALIZER_URL"] == "http://from-file.invalid"
        assert values["VANDALIZER_USER"] == "env-user"      # environment wins
        assert values["VANDALIZER_PASS"] == "file-pass"

    def test_url_override_beats_both(self, tmp_path, monkeypatch):
        env_file = tmp_path / "bench.env"
        env_file.write_text("VANDALIZER_URL=http://from-file.invalid\n"
                            "VANDALIZER_USER=u\nVANDALIZER_PASS=p\n")
        monkeypatch.setenv("VANDALIZER_URL", "http://from-env.invalid")
        values = harness.load_credentials(env_file, "http://from-flag.invalid")
        assert values["VANDALIZER_URL"] == "http://from-flag.invalid"

    def test_a_missing_env_file_exits_cleanly(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            harness.load_credentials(tmp_path / "nope.env", None)
        assert "does not exist" in str(excinfo.value)


class TestQuestionSelection:
    def test_all_returns_the_whole_key(self):
        assert harness.questions_for(KEY, "all") == KEY["questions"]

    def test_a_subset_keeps_key_order(self):
        chosen = harness.questions_for(KEY, "Q003,Q001")
        assert [q["id"] for q in chosen] == ["Q001", "Q003"]

    def test_an_unknown_id_exits_cleanly(self):
        with pytest.raises(SystemExit) as excinfo:
            harness.questions_for(KEY, "Q001,Q099")
        assert "Q099" in str(excinfo.value)


class TestKeyCrossCheck:
    def test_a_version_mismatch_refuses(self, tmp_path):
        (tmp_path / "manifest.json").write_text(json.dumps({"version": "0.5.0"}))
        (tmp_path / "ground_truth.json").write_text(
            json.dumps({"version": "0.4.0"}))
        with pytest.raises(SystemExit) as excinfo:
            harness.load_key(tmp_path)
        assert "refusing to run" in str(excinfo.value)

    def test_the_shipped_key_and_manifest_agree(self):
        manifest, truth = harness.load_key(harness.KEYS_DEFAULT)
        assert manifest["version"] == truth["version"]

    def test_the_digital_asset_is_the_one_holding_the_pdfs(self):
        manifest, _ = harness.load_key(harness.KEYS_DEFAULT)
        asset = harness.digital_asset(manifest)
        assert "pdf/" in asset["contents"]
        assert len(asset["sha256"]) == 64


# --------------------------------------------------------------------------
# The abstention vocabulary — the review finding that must not recur
# --------------------------------------------------------------------------


class TestAbstainVocabulary:
    """`_ABSTAIN` feeds the `abstained` diagnostic column.

    A port of this harness narrowed it by six alternation branches, which
    silently unflagged 17 abstentions across the 900 published rows and dropped
    its agreement with `score.py`'s `REFUSAL` from 830/900 to 819/900. Every
    branch that went missing has a fixture here, phrased as the audited rows
    phrased it, so the narrowing cannot happen again without a red test.
    """

    #: One phrasing per dropped branch, taken from the shapes the audit read.
    DROPPED_BRANCHES = [
        # `^\s*[-*\s]*not (applied|...)` — a bare list item
        "- Not applicable\n",
        # `:\s*not (applied|...)` — a label/value line
        "Voluntary committed cost sharing: not applicable to this proposal",
        # `no \w+(\s+\w+)? (is|are|was|were) (included|listed|...)`
        "No subaward budget is included in the packet.",
        # `no (mention|reference|information|...)`
        "There is no mention of an off-campus rate anywhere in the packet.",
        "The budget carries no line items for participant support.",
        # `(could|can|do|did)( ?n[o']?t| not) (find|locate|determine|see|identify)`
        "I could not find that figure in the attached documents.",
        "I did not see an ORCID identifier for either investigator.",
        # `does not exist|do not exist|no such|nothing in the (document|text)`
        "No such document exists in this packet.",
        "There is nothing in the document that states a subaward amount.",
        # `not (...|included) in` — the port also dropped `included` here
        "That cost is not included in the amount requested.",
    ]

    @pytest.mark.parametrize("phrase", DROPPED_BRANCHES)
    def test_a_dropped_branch_still_matches(self, phrase):
        assert harness._ABSTAIN.search(phrase), phrase

    def test_the_kept_branches_still_match(self):
        for phrase in (
            "The documents do not specify a manufacturer.",
            "The value is not stated in the packet.",
            "There is no personal identifier of that kind anywhere in the "
            "packet.",
            "That cannot be determined from the attached documents.",
            "I am unable to locate a figure for that.",
            "The rate isn't listed anywhere.",
        ):
            assert harness._ABSTAIN.search(phrase), phrase

    def test_an_answer_that_declines_nothing_does_not_match(self):
        assert not harness._ABSTAIN.search(
            "The proposal requests $1,184,398.51 from NSF over three years.")

    def test_it_agrees_with_the_scorer_on_the_published_shapes(self):
        """Both vocabularies fire on the same audited abstentions.

        Full agreement is neither expected nor wanted — `REFUSAL` decides
        verdicts and widens when the audit finds a phrasing it missed, while
        this one is a diagnostic pinned to the harness that produced the
        published evidence. What has to hold is that the diagnostic does not
        quietly fall behind on the phrasings both were built from.
        """
        for phrase in (
            "The documents do not provide the name of the postdoctoral "
            "researcher.",
            "A specific make and model is not mentioned in any of the "
            "attached documents.",
            "There is no personal identifier of that kind anywhere in the "
            "packet.",
        ):
            assert harness._ABSTAIN.search(phrase), phrase
            assert REFUSAL.search(normalise(phrase)), phrase


# --------------------------------------------------------------------------
# Routing — the diagnostic that used to report "no" where it meant "unknown"
# --------------------------------------------------------------------------


class TestRoutedDerivation:
    def test_a_different_served_model_is_routed(self):
        assert harness.derive_routed("long-doc-model", "asked-for-model", []) \
            is True

    def test_the_same_model_is_not_routed(self):
        assert harness.derive_routed("same-model", "same-model", []) is False

    def test_the_notice_settles_it_upward(self):
        """`model_routed` is proof of routing even with nothing to compare."""
        assert harness.derive_routed(None, None, ["model_routed"]) is True

    def test_nothing_to_compare_against_is_unknown_not_false(self):
        """The finding: without --model and --admin-config there is no
        `requested`, and reporting `False` there asserts something unmeasured.
        """
        assert harness.derive_routed("long-doc-model", None, []) is None
        assert harness.derive_routed(None, None, []) is None
        assert harness.derive_routed(None, None, ["model_not_routed"]) is None

    def test_an_unrelated_notice_does_not_decide_it(self):
        assert harness.derive_routed("a", "a", ["context_trimmed"]) is False


# --------------------------------------------------------------------------
# Row diagnostics
# --------------------------------------------------------------------------


class TestKeyFigures:
    def test_the_identifier_guard_drops_a_policy_number(self):
        """`CSU-RSP-204` is a name, not a figure — `score.py`'s rule."""
        assert "204" not in harness.key_figures(
            "No. Participant support costs are not participants under policy "
            "CSU-RSP-204.")

    def test_money_survives(self):
        assert "$1,184,398.51" in harness.key_figures(
            "The total requested is $1,184,398.51.")

    def test_short_tokens_are_dropped(self):
        assert harness.key_figures("Exactly 1 instrument, in year 2.") == []

    def test_typographic_punctuation_is_folded(self):
        assert harness.key_figures("The award ran 07/01/2025–06/30/2026.")

    def test_it_matches_the_scorers_token_rule_on_the_shipped_key(self):
        """Same tokens as `score.py.figures()` over every key answer.

        The two implementations are separate on purpose — the harness must not
        import a scorer — so this is what keeps them from drifting.
        """
        import score
        for question in KEY["questions"]:
            expected = question.get("answer") or ""
            assert harness.key_figures(expected) == score.figures(expected), \
                question["id"]


class TestPagesIn:
    def test_a_range_expands(self):
        assert harness.pages_in("see pp. 1-3") == [1, 2, 3]

    def test_a_list_is_two_citations(self):
        assert harness.pages_in("pages 20 and 21") == [20, 21]

    def test_a_single_page(self):
        assert harness.pages_in("(Document 05, p. 2)") == [2]

    def test_an_approximate_marker_is_still_a_citation(self):
        assert harness.pages_in("around p. ~4") == [4]

    def test_absurd_numbers_are_ignored(self):
        assert harness.pages_in("page 999") == []

    def test_no_citation_is_an_empty_list(self):
        assert harness.pages_in("The total is $1,184,398.51.") == []


class TestDiagnostics:
    def test_the_shape_is_stable(self):
        """These keys are the contract the adjudication pass sorts on."""
        diag = harness.diagnostics("some answer", "the key answer")
        assert set(diag) == {
            "key_figures", "figures_found", "figures_all_present",
            "pages_named", "abstained", "thinking_leak", "answer_chars",
        }

    def test_a_present_figure_is_found_through_markdown(self):
        diag = harness.diagnostics(
            "The total requested is $**1,184,398.51** (p. 1).",
            "$1,184,398.51 is requested from NSF.")
        assert diag["figures_all_present"] is True
        assert diag["pages_named"] == [1]

    def test_an_absent_figure_is_not_found(self):
        diag = harness.diagnostics("The total is $999,999.00.",
                                   "$1,184,398.51 is requested from NSF.")
        assert diag["figures_found"] == []
        assert diag["figures_all_present"] is False

    def test_all_present_is_false_when_the_key_has_no_figures(self):
        assert harness.diagnostics("anything", "no figures here")[
            "figures_all_present"] is False

    def test_abstention_is_flagged(self):
        assert harness.diagnostics(
            "The documents do not specify a model.", "")["abstained"] is True

    def test_a_thinking_leak_is_flagged_and_the_answer_is_not_stripped(self):
        answer = "Thinking:\nI should check the budget justification first."
        diag = harness.diagnostics(answer, "")
        assert diag["thinking_leak"] is True
        assert diag["answer_chars"] == len(answer)

    def test_an_empty_answer_does_not_raise(self):
        diag = harness.diagnostics("", "")
        assert diag["answer_chars"] == 0
        assert diag["abstained"] is False


class TestRowShape:
    """The row contract `score.py` and `citation_accuracy.py` read.

    Built from the same key the harness builds it from, so a key edit that
    dropped one of these fields would fail here rather than mid-run.
    """

    SCORER_KEYS = {"id", "type", "answerable", "question", "expected", "got"}

    def test_the_key_carries_every_field_a_row_needs(self):
        for question in KEY["questions"]:
            assert {"id", "type", "question", "answer"} <= set(question)
            assert isinstance(question.get("answerable", True), bool)

    def test_a_row_built_from_the_key_scores(self):
        import score
        question = KEY["questions"][0]
        row = {
            "id": question["id"],
            "type": question["type"],
            "answerable": question.get("answerable", True),
            "question": question["question"],
            "expected": question.get("answer"),
            "got": question.get("answer"),
        }
        assert self.SCORER_KEYS <= set(row)
        verdict, _ = score.score_row(row)
        assert verdict in (score.PASS, score.REVIEW)

    def test_the_transport_error_prefix_is_the_one_the_scorer_reads(self):
        import score
        assert score.score_row({"answerable": True, "expected": "x",
                                "got": "<<ERROR: ConnectionError>>"}) == \
            (score.FAIL, "request error")
