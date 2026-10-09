"""Describe preserved legacy check roles without changing its frozen rubric.

The extraction field suggestion has always been advisory: completion depends
on the field count. New competency rubrics author their required roles directly.
"""


def legacy_check_roles(module_id, result):
    return {**result, 'checks': [
        {**check, 'role': ('advisory' if module_id == 'extraction_engine'
                          and check['name'] == 'Missing expected fields' else 'required')}
        for check in result['checks']
    ]}
