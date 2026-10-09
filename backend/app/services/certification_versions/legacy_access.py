"""Apply current read permissions without rewriting preserved legacy criteria.

The legacy collectors follow linked extraction IDs and creator references. Bind
their model reads to this learner for one call; never monkeypatch shared rubric
globals, which would mix permissions between concurrent grading requests. The
original field merging, required counts and star thresholds execute unchanged.
"""
from types import FunctionType

from app.models.user import User
from app.services.access_control import get_authorized_search_set


class _ReadableQuery:
    def __init__(self, query, user_id, reference):
        self.query, self.user_id, self.reference = query, user_id, reference

    async def to_list(self, *args, **kwargs):
        records = await self.query.to_list(*args, **kwargs)
        readable = []
        # Recheck after the field query: revocation cannot be hidden by an
        # earlier access check or an authorization cache shared across calls.
        allowed = {}
        for record in records:
            reference = getattr(record, self.reference, None)
            if reference not in allowed:
                allowed[reference] = bool(reference and await get_authorized_search_set(
                    reference, User(user_id=self.user_id)))
            if allowed[reference]:
                readable.append(record)
        return readable


class _ReadableModel:
    def __init__(self, model, user_id, reference):
        self.model, self.user_id, self.reference = model, user_id, reference

    def __getattr__(self, name):
        return getattr(self.model, name)

    def find(self, *args, **kwargs):
        return _ReadableQuery(self.model.find(*args, **kwargs), self.user_id, self.reference)


def with_legacy_field_access(validator, user_id):
    """Bind only the affected collectors; leave their executable rules intact.

    Works with the current legacy validator and the hash-verified frozen runner.
    A private globals dictionary preserves the original functions and models.
    It is not installed on either module and lives only for this invocation.
    """
    if not isinstance(validator, FunctionType):
        return validator
    scope = dict(validator.__globals__)
    scope['SearchSet'] = _ReadableModel(scope['SearchSet'], user_id, 'uuid')
    scope['SearchSetItem'] = _ReadableModel(scope['SearchSetItem'], user_id, 'searchset')

    def bind(function):
        if not isinstance(function, FunctionType):
            return function
        bound = FunctionType(function.__code__, scope, function.__name__,
                             function.__defaults__, function.__closure__)
        bound.__kwdefaults__ = function.__kwdefaults__
        return bound

    for name in ('_resolve_extraction_field_names', '_collect_extraction_fields',
                 '_collect_searchset_fields', '_validate_foundations', '_validate_extraction_engine'):
        scope[name] = bind(scope[name])
    scope['_VALIDATORS'] = {
        module: scope['_validate_' + module] if module in ('foundations', 'extraction_engine') else function
        for module, function in scope['_VALIDATORS'].items()
    }
    return bind(validator)
