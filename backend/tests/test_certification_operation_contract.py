"""Invalid principals fail before a course operation can touch learner data."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services.certification_versions import runtime
from app.services.certification_versions.enrollments import EnrollmentConflict


@pytest.mark.asyncio
@pytest.mark.parametrize('principal', [None, '', 7, SimpleNamespace(), SimpleNamespace(user_id=None), SimpleNamespace(deps=SimpleNamespace(user_id=7))])
@pytest.mark.parametrize('boundary', ['internal', 'http', 'tool'])
async def test_invalid_principal_cannot_enter_course_operation(monkeypatch, principal, boundary):
    repository = Mock(side_effect=AssertionError('Invalid principal reached learner storage'))
    monkeypatch.setattr(runtime, 'EnrollmentRepository', repository)
    called = False

    @runtime.course_operation(http=boundary == 'http', tool=boundary == 'tool')
    async def operation(user):
        nonlocal called
        called = True
        return {'ok': True}

    if boundary == 'tool':
        result = await operation(principal)
        assert 'authenticated learner' in result['error']
        assert result['hint']
    elif boundary == 'http':
        with pytest.raises(HTTPException) as caught:
            await operation(principal)
        assert caught.value.status_code == 409
    else:
        with pytest.raises(EnrollmentConflict, match='authenticated learner'):
            await operation(principal)
    assert not called
    repository.assert_not_called()
