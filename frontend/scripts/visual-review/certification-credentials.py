"""Synthetic PDF fixtures for immutable credential visual inspection."""
import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certificate_pdf import render_certificate_pdf  # noqa: E402

output = ROOT / 'artifacts/visual-review/certification-credentials-2026-10-05'
output.mkdir(parents=True, exist_ok=True)
base = dict(level='architect', certified_at=datetime.datetime(2026, 10, 5, tzinfo=datetime.timezone.utc), credential_id='0123456789ABCDEF0123456789ABCDEF', course_title='Vandal Workflow Architect - current course', course_version='legacy-2026-10-02.1', module_count=11)
fixtures = {
    'new-course': {**base, 'name': 'Alex Morgan'},
    'long-name': {**base, 'name': 'Alexandra Theodora Maximiliana Wilhelmina Featherstonehaugh-Cholmondeley van der Meer de la Cruz', 'course_title': 'Vandal Workflow Architect - Research Administration, Source Verification, Recovery and Reviewed Delivery'},
    'legacy-unknown': {**base, 'name': 'Nguyễn Văn A', 'course_title': 'Legacy certification - historical version unknown', 'course_version': None, 'certified_at': None, 'legacy_unknown': True},
}
for name, args in fixtures.items():
    (output / f'{name}.pdf').write_bytes(render_certificate_pdf(**args))
    print(output / f'{name}.pdf')
