"""form_fill: checking a Form Filler's values against its inputs, attributing
them to a document and page, and reading/writing real PDF form fields.

Pure helpers plus PyMuPDF; no DB, no LLM.
"""

import fitz
import pytest

from app.services.form_fill import (
    describe_fill_report,
    fill_pdf_form,
    filled_pdf_filename,
    find_value_offset,
    load_form_filler_assets,
    pdf_form_fields,
    resolve_fill,
    value_is_missing,
)

AWARD = (
    "NOTICE OF AWARD\nIndirect cost rate: 47.5% of MTDC.\nTotal award: $1,250,000.\n"
    "\fProject period: 09/01/2026 – 08/31/2029.\nPI: Dr. Ada Lovelace\nAgency: NIH"
)
# Page 2 starts at the form feed.
MARKERS = [
    {"char_offset": 0, "kind": "page", "value": 1},
    {"char_offset": AWARD.index("\f"), "kind": "page", "value": 2},
]
SOURCES = [
    {"kind": "step_input", "title": "Previous Step Output", "text": "Cover note: submit by Friday."},
    {"kind": "workflow_documents", "title": "Award.pdf", "uuid": "D1", "text": AWARD, "text_markers": MARKERS},
]


class TestFindValueOffset:
    def test_verbatim_and_case_and_whitespace(self):
        assert find_value_offset(AWARD, "47.5%")[1] == "verbatim"
        assert find_value_offset(AWARD, "dr. ada lovelace")[1] == "verbatim"  # case is folded
        assert find_value_offset(AWARD, "Dr.  Ada\nLovelace")[1] == "verbatim"  # whitespace too

    def test_same_number_and_same_date(self):
        assert find_value_offset(AWARD, "1250000")[1] == "same_number"
        assert find_value_offset(AWARD, "September 1, 2026")[1] == "same_date"

    def test_percent_matters_for_number_matching(self):
        # "47.5" is literally present in "47.5%", so it is found verbatim; but a
        # number-level match must not equate 47.5 with 47.5%.
        assert find_value_offset("rate 47.5% here", "47.5")[1] == "verbatim"
        assert find_value_offset("rate 47.5% here", "47.50") == (None, None)
        assert find_value_offset("rate 47.5 here", "47.5%") == (None, None)

    def test_short_value_must_not_match_inside_a_longer_token(self):
        assert find_value_offset("total 2012 units and 12 more", "12") == (21, "verbatim")
        assert find_value_offset("Adam only", "Ada") == (None, None)

    def test_missing(self):
        assert find_value_offset(AWARD, "EUR 4,000") == (None, None)
        assert find_value_offset("", "x") == (None, None)


class TestResolveFill:
    def test_status_source_and_page_per_field(self):
        values = {
            "rate": "47.5%", "pi": "Dr. Ada Lovelace", "start": "September 1, 2026",
            "note": "submit by Friday", "eur": "EUR 4,000", "cap": None, "basis": "N/A",
            "human_subjects": True,
        }
        report = resolve_fill(values, SOURCES)
        by = {e["name"]: e for e in report}

        assert [e["name"] for e in report] == list(values)
        assert by["rate"]["status"] == "supported"
        assert by["rate"]["document_title"] == "Award.pdf"
        assert by["rate"]["document_uuid"] == "D1"
        assert by["rate"]["page"] == 1
        assert "47.5%" in by["rate"]["quote"]
        assert by["pi"]["page"] == 2
        assert by["start"]["method"] == "same_date"
        assert by["start"]["page"] == 2
        # Previous-step output is a source with a title but no document or page.
        assert by["note"]["document_title"] == "Previous Step Output"
        assert by["note"]["document_uuid"] is None
        assert by["note"]["page"] is None
        assert by["eur"]["status"] == "unsupported"
        assert by["cap"]["status"] == "missing"
        assert by["basis"]["status"] == "missing"  # sentinel counts as unfilled
        assert by["human_subjects"] == {"name": "human_subjects", "value": True, "status": "supported", "method": "boolean"}

    def test_field_order_is_honoured_and_unknown_fields_are_missing(self):
        report = resolve_fill({"b": "x"}, [], field_order=["a", "b"])
        assert [(e["name"], e["status"]) for e in report] == [("a", "missing"), ("b", "unsupported")]

    def test_approximate_page_is_flagged(self):
        src = [{"title": "OCR.pdf", "uuid": "O", "text": "rate 3%",
                "text_markers": [{"char_offset": 0, "kind": "page", "value": 4, "approximate": True}]}]
        [entry] = resolve_fill({"r": "3%"}, src)
        assert entry["page"] == 4 and entry["page_approximate"] is True


class TestDescribeFillReport:
    def test_unfilled_then_unsupported(self):
        report = resolve_fill({"a": None, "b": "nope", "c": "47.5%"}, SOURCES)
        warnings = describe_fill_report(report, missing_token="[Not provided]")
        assert warnings[0] == "1 field not found in the input and marked [Not provided] in the form — fill in or remove before using it: a"
        assert warnings[1].startswith("1 value does not appear anywhere in the input data")
        assert "b ('nope')" in warnings[1]

    def test_blank_wording_for_pdf_mode_and_plural(self):
        report = resolve_fill({"a": None, "b": None}, SOURCES)
        [w] = describe_fill_report(report, missing_token=None)
        assert w == "2 fields not found in the input and left blank in the form — fill in before using it: a, b"

    def test_clean_fill_has_no_warnings(self):
        assert describe_fill_report(resolve_fill({"c": "47.5%"}, SOURCES), missing_token="x") == []


def test_value_is_missing():
    assert value_is_missing(None) and value_is_missing("  ") and value_is_missing("Not provided")
    assert not value_is_missing(False) and not value_is_missing(0) and not value_is_missing("0")


# ---------------------------------------------------------------------------
# PDF forms
# ---------------------------------------------------------------------------

def _form_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((20, 25), "Principal Investigator")
    w = fitz.Widget(); w.field_name = "pi_name"; w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(150, 10, 400, 30); page.add_widget(w)
    page.insert_text((20, 55), "Human subjects?")
    w = fitz.Widget(); w.field_name = "human_subjects"; w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(150, 40, 170, 60); page.add_widget(w)
    w = fitz.Widget(); w.field_name = "agency"; w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    w.rect = fitz.Rect(150, 70, 300, 90); w.choice_values = ["NSF", "NIH", "DOE"]; page.add_widget(w)
    w = fitz.Widget(); w.field_name = "sig"; w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    w.rect = fitz.Rect(150, 100, 300, 120); page.add_widget(w)
    page2 = doc.new_page()
    w = fitz.Widget(); w.field_name = "notes"; w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(20, 20, 400, 60); page2.add_widget(w)
    return doc.tobytes()


def _widget_values(pdf: bytes) -> dict:
    doc = fitz.open(stream=pdf, filetype="pdf")
    return {w.field_name: w.field_value for page in doc for w in page.widgets()}


class TestPdfFormFields:
    def test_lists_fields_with_type_page_label_and_choices(self):
        fields = pdf_form_fields(_form_pdf())
        by = {f["name"]: f for f in fields}
        assert [f["name"] for f in fields] == ["pi_name", "human_subjects", "agency", "sig", "notes"]
        assert by["pi_name"] == {"name": "pi_name", "type": "text", "page": 1, "label": "Principal Investigator"}
        assert by["human_subjects"]["type"] == "checkbox"
        assert by["human_subjects"]["label"] == "Human subjects?"
        assert by["agency"]["choices"] == ["NSF", "NIH", "DOE"]
        assert by["sig"]["type"] == "signature"
        assert by["notes"]["page"] == 2

    def test_pdf_without_fields(self):
        doc = fitz.open(); doc.new_page().insert_text((20, 20), "plain page")
        assert pdf_form_fields(doc.tobytes()) == []


class TestFillPdfForm:
    def test_writes_each_type_and_reports_skips(self):
        out, applied, skipped = fill_pdf_form(_form_pdf(), {
            "pi_name": "Dr. Ada Lovelace", "human_subjects": "yes", "agency": "nih",
            "sig": "x", "notes": None,
        })
        assert applied == ["pi_name", "human_subjects", "agency"]
        assert skipped == [("sig", "signature fields cannot hold a value")]
        values = _widget_values(out)
        assert values["pi_name"] == "Dr. Ada Lovelace"
        assert values["human_subjects"] == "Yes"
        assert values["agency"] == "NIH"
        assert values["notes"] == ""  # missing value leaves the field untouched

    def test_bad_choice_and_bad_checkbox_are_skipped_not_written(self):
        out, applied, skipped = fill_pdf_form(_form_pdf(), {"agency": "NASA", "human_subjects": "maybe"})
        assert applied == []
        assert dict(skipped) == {
            "agency": "'NASA' is not one of the field's options",
            "human_subjects": "checkbox needs true/false, got 'maybe'",
        }
        assert _widget_values(out)["agency"] == ""

    def test_boolean_false_unticks(self):
        out, applied, _ = fill_pdf_form(_form_pdf(), {"human_subjects": False})
        assert applied == ["human_subjects"]
        assert _widget_values(out)["human_subjects"] == "Off"


def test_filled_pdf_filename():
    assert filled_pdf_filename("NSF Budget Form.pdf") == "NSF Budget Form-filled.pdf"
    assert filled_pdf_filename("a/b:c?.pdf") == "a_b_c-filled.pdf"
    assert filled_pdf_filename(None) == "form-filled.pdf"


# ---------------------------------------------------------------------------
# Task-data preload
# ---------------------------------------------------------------------------

class _Db:
    def __init__(self, doc):
        self._doc = doc
        self.smart_document = self

    def find_one(self, query):
        return self._doc if self._doc and self._doc.get("uuid") == query.get("uuid") else None


class TestLoadFormFillerAssets:
    def test_text_mode_is_untouched(self):
        data = {"template_source": "text", "template_document_uuid": "T"}
        load_form_filler_assets(_Db(None), data, upload_dir="/nowhere")
        assert "template_pdf_b64" not in data and "template_load_error" not in data

    def test_loads_pdf_bytes_and_title(self, tmp_path):
        (tmp_path / "u1").mkdir()
        (tmp_path / "u1" / "T.pdf").write_bytes(_form_pdf())
        db = _Db({"uuid": "T", "title": "Budget form.pdf", "extension": "pdf", "path": "u1/T.pdf"})
        data = {"template_source": "pdf", "template_document_uuid": "T"}
        load_form_filler_assets(db, data, upload_dir=str(tmp_path))
        assert data["template_document_title"] == "Budget form.pdf"
        assert pdf_form_fields(__import__("base64").b64decode(data["template_pdf_b64"]))[0]["name"] == "pi_name"

    @pytest.mark.parametrize("doc, needle", [
        (None, "no longer exists"),
        ({"uuid": "T", "title": "x.docx", "extension": "docx", "path": "u1/T.docx"}, "not a PDF"),
        ({"uuid": "T", "title": "gone.pdf", "extension": "pdf", "path": "u1/gone.pdf"}, "missing on the server"),
    ])
    def test_load_errors_are_recorded_not_raised(self, tmp_path, doc, needle):
        data = {"template_source": "pdf", "template_document_uuid": "T"}
        load_form_filler_assets(_Db(doc), data, upload_dir=str(tmp_path))
        assert needle in data["template_load_error"]
        assert "template_pdf_b64" not in data

    def test_no_document_selected(self):
        data = {"template_source": "pdf"}
        load_form_filler_assets(_Db(None), data, upload_dir="/nowhere")
        assert "no template document is selected" in data["template_load_error"]
