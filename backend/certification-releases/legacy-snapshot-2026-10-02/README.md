# Preserved course at the October 2 audit baseline

This is a source preservation package, not a published course release or a claim about any learner’s historical course version. Its immutable source revision is `fdce99138d81e99ca1a0d77dd8f4caef4b71383b`. The manifest records every file’s SHA-256 and the archive digest. It contains no learner records or credentials.

The archive includes all 74 lessons, panel diagrams and knowledge checks, reflections, exercises and eight sample PDFs; the backend validators and XP rules; chat tool and API behavior; certificate rendering; and the application source and dependency locks needed to interpret them. Preserved behavior includes known defects, including the prerequisite bypass, weak evidence checks and obsolete progress-tool field. Do not deploy this archive as an upgrade.

Verify or extract into a new directory from the repository root:

```bash
python3 scripts/snapshot_certification.py backend/certification-releases/legacy-snapshot-2026-10-02
python3 scripts/snapshot_certification.py backend/certification-releases/legacy-snapshot-2026-10-02 --extract /tmp/certification-baseline
```

The extractor refuses an existing destination and verifies the archive and every file before writing. Source paths are preserved. Use the archived `backend/uv.lock` and `frontend/package-lock.json` to reproduce dependencies; runtime credentials and databases are intentionally excluded. The recorded source commit supplies repository infrastructure outside this course package.

To exercise the preserved rubric independently of subsequent edits, run Python from an environment with the archived backend dependencies, with the extracted `backend` directory as the working directory:

```bash
python -m pytest tests/test_certification_extraction_fields.py tests/test_certification_governance.py tests/test_certification_output_delivery.py tests/test_certificate_pdf.py tests/test_chat_cert_tools.py -q
```

On October 2, 2026, archive extraction verified 928 file hashes, and the above archived suite passed all 54 tests using the existing backend environment. Those tests establish reproducibility of the existing behavior; they do not establish assessment validity. No live database or model was used. The baseline audit documents the gaps the old tests accept.

Existing enrollments must retain their earned credit and credential dates. Version-aware enrollment routing is a separate unfinished milestone; creating this snapshot does not pin learners or migrate them.
