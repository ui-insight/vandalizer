"""Chat tools tell a damaged file apart from a failure a retry may fix.

#1021 records ``error_retryable`` on a document: False when the file itself
is the problem (a damaged workbook, another format renamed), unset or True
for a crash or outage. The agent's tools called every failure "permanent —
retrying will not help", so the user was told not to retry a document a
retry would have read.
"""

from types import SimpleNamespace

from app.services.chat_tools import _doc_text_unavailable_err


def _doc(**over):
    base = dict(title="budget.xlsx", uuid="d1", task_status="error",
                error_message="Reader crashed", error_retryable=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_a_retryable_failure_points_at_retry_extraction():
    out = _doc_text_unavailable_err(_doc())
    assert "FAILED" in out["error"]
    assert "retrying will not help" not in out["error"]
    assert "Retry extraction" in out["hint"]


def test_a_damaged_file_is_told_to_re_export_not_retry():
    out = _doc_text_unavailable_err(_doc(error_retryable=False, error_message="This workbook is damaged"))
    assert "retrying will not help" in out["error"]
    assert "This workbook is damaged" in out["error"]
    assert "Do not suggest Retry extraction" in out["hint"]
    assert "Save As" in out["hint"]


def test_a_document_still_processing_says_so():
    out = _doc_text_unavailable_err(_doc(task_status="processing"))
    assert "still processing" in out["error"]
