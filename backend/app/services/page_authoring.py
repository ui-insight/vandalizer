"""Source-fidelity guidance shared by Page generation and tool feedback."""

PAGE_SOURCE_FIDELITY_RULES = (
    "For a Page built from documents or spreadsheets, read the original source before authoring or revising; "
    "an earlier generated page or chat summary is not source evidence. Read all relevant rows and columns, "
    "following get_document_text continuation offsets when needed. Preserve every category and every year's "
    "exact value in separate table cells, including repeated values and the final year. Keep units, year "
    "labels and category labels aligned with the source. Never replace individual yearly cells with a range, "
    "'each year', an average or a rounded abbreviation. Chart labels and number cards must agree with those cells. "
    "A summary may accompany the full table, but label it 'Calculated summary' and compute it from all relevant "
    "source values; a range uses the true minimum and maximum, not the first and last values or an assumed trend. "
    "Do not invent statements about how the source is organized: exact source cells are not 'ranges in the source'. "
    "Distinguish source notes actually present in the document from your own calculations and presentation choices. "
    "Check every displayed value and source claim against the original before proposing a preview or saving. "
    "If source values are missing, truncated or ambiguous, retrieve them or clearly mark them unavailable; never guess. "
    "HTML sanitization, saving and publication do not verify factual accuracy. Never claim source verification "
    "unless you actually compared the content with the source."
)
