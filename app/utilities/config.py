#!/usr/bin/env python3

# the model type to use, either openai or insight server (ollama)
# model_type = "insight"
model_type = "openai"

# model category to use, either pydantic_ai or dspy
model_category = "pydantic_ai"

# 128K is the max context length for the GPT-4o model
# we use less than this to be safe
max_context_length = 120000 * 4


upload_compliance = """
Upload Compliance:
1. Document Format:
    - Ensure the document is in a supported format (PDF, DOCX, XLSX, TXT).
2. Content Guidelines:
    - The document should not contain FERPA violations.
    The Family Educational Rights and Privacy Act of 1974, as amended, also known as the Buckley Amendment  is a federal law that governs the confidentiality of student records. Generally, the law requires that educational institutions maintain the confidentiality of what are termed "education records," ensures that each student has access to his or her education records, and provides students with a limited opportunity to correct erroneous education records.
    FERPA applies to the education records of persons who are or have been in attendance at the University of Idaho. With certain exceptions, education records are those records maintained by the university which are directly related to a student. This is an extremely broad definition.
    FERPA may be more permissive or restrictive than the privacy and public information laws of some states. Therefore, the Idaho Public Records Law must be taken into account when the University of Idaho considers issues related to student records.
    - The document should not contain Personally Identifiable Information (PII) (for example student ID numbers, social security numbers, etc.).
    Personally identifiable information is information contained in any record which makes a student's identity easily traceable. A student's ID number, for example, is personally identifiable information. Personally identifiable information cannot be released to third parties without the student's written consent, except under very narrow circumstances.
"""
