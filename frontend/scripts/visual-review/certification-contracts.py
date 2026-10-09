"""Read-only certification audit probes; no DB, credentials or model calls.
Run using backend/.venv/bin/python. These are observations, not release acceptance tests.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'backend'))
from app.services import certification_service as cs
from app.services.chat_tools import get_certification_progress

async def main():
    findings = {}
    progress = SimpleNamespace(id='audit', user_id='audit', modules={}, total_xp=0,
        level='novice', certified=False, certified_at=None, last_activity_date=None, unlocked=False)
    with patch.object(cs, 'get_progress', AsyncMock(return_value=progress)):
        findings['actual_progress_keys'] = sorted((await cs.get_progress_dict('audit')).keys())
        try:
            await get_certification_progress(SimpleNamespace(deps=SimpleNamespace(user_id='audit')))
            findings['progress_tool'] = {'error': None}
        except Exception as exc:
            findings['progress_tool'] = {'error': type(exc).__name__, 'detail': str(exc)}
    model = MagicMock()
    model.find.return_value.to_list = AsyncMock(return_value=[])
    with patch.object(cs, 'Workflow', model), patch.object(cs, '_collect_searchset_fields', AsyncMock(return_value=[f'Unrelated field {n}' for n in range(15)])):
        findings['unrelated_unexecuted_15_fields'] = await cs._validate_extraction_engine('audit')
    validator = AsyncMock(return_value={'passed':True,'stars':1,'checks':[]})
    with patch.object(cs, 'get_progress', AsyncMock(return_value=progress)), patch.dict(cs._VALIDATORS, {'governance':validator}):
        findings['prerequisite_enforced_before_validator'] = not (await cs.validate_module('audit','governance'))['passed']
        findings['later_validator_called_with_empty_progress'] = validator.await_count == 1
    findings['base_xp'] = sum(cs.MODULE_XP.values())
    findings['max_xp_including_stars'] = sum(cs.MODULE_XP.values()) + 75 * len(cs.MODULE_ORDER)
    print(json.dumps(findings, indent=2))
asyncio.run(main())
