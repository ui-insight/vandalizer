#!/usr/bin/env python3
"""Plan or run synthetic certification grading checks without application writes.

Planning is the default. Live requests require --live, an explicit configured
model and a private JSON model-config file. Each invocation defaults to one new
case. Resume preserves prior results and rejects changed suites/model settings.
"""
import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.certification_versions.attempts import encode  # noqa: E402
from app.services.certification_versions.automatic_review import evaluate_draft_structured_review, reviewer_identity  # noqa: E402
from app.services.certification_versions.outcomes import OutcomeContract  # noqa: E402
from app.services.certification_versions.review_calibration import ReviewCalibrationSuite, measure_calibration_case  # noqa: E402
from app.services import metering  # noqa: E402

DRAFT = ROOT / 'backend/certification-data/drafts/v5.0'


def load_suites(module_ids=()):
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    suites = [ReviewCalibrationSuite.model_validate_json(p.read_bytes())
              for p in sorted(DRAFT.glob('*-review-calibration.json'))]
    required = {m.module_id for m in contract.modules if any(o.method == 'structured_review' for o in m.outcomes)}
    if len(suites) != len(required) or {s.module_id for s in suites} != required:
        raise ValueError('Every reviewed module requires exactly one suite')
    if not set(module_ids) <= required:
        raise ValueError('Unknown calibration module')
    for suite in suites:
        suite.verify_contract(contract)
    return contract, [s for s in suites if not module_ids or s.module_id in module_ids]


def plan(contract, suites):
    return {'schema_version': 1, 'synthetic': True,
            'contract_sha256': encode(contract.model_dump(mode='json'))[1],
            'suites': [{'module_id': s.module_id, 'suite_sha256': encode(s.model_dump(mode='json'))[1],
                        'case_ids': [c.id for c in s.cases]} for s in suites],
            'case_count': sum(len(s.cases) for s in suites), 'release_ready': False, 'credit_awarded': False}


def save_report(path, report):
    # Interrupted writes leave the last complete report available for resumption.
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def report_only_metering():
    # The ordinary metered() context flushes into application MongoDB. These
    # synthetic QA calls deliberately retain usage in the local report instead.
    scope = metering.MeterScope(feature='certification_calibration_qa')
    token = metering._current_scope.set(scope)
    try:
        yield scope
    finally:
        metering._current_scope.reset(token)


def summarize(report):
    latest = {(row['module_id'], row['case_id']): row for row in report['attempts']}
    rows = list(latest.values())
    return {'recorded_cases': len(rows), 'pending_cases': report['plan']['case_count'] - len(rows),
            'unavailable_cases': sum(r['grading_unavailable'] for r in rows),
            'false_support_count': sum(len(r['false_supported_outcomes']) for r in rows),
            'false_rejection_count': sum(len(r['false_rejected_outcomes']) for r in rows),
            'all_cases_matched': len(rows) == report['plan']['case_count'] and all(r['matches'] for r in rows),
            'total_attempts': len(report['attempts']), 'release_ready': False, 'credit_awarded': False}


def _usage_record(scope: metering.MeterScope) -> dict:
    """The scope's totals plus its per-model rows. ``asdict`` can't copy the
    scope's lock, and its ``usage`` map is keyed by tuples JSON can't hold."""
    record = {f.name: getattr(scope, f.name) for f in fields(scope)
              if f.name not in ('usage', '_lock')}
    record['models'] = metering.model_usage_rows(scope)
    return record

async def run_batch(contract, suites, *, model_name, config, output, max_cases=1,
                    resume=False, retry_unavailable=False, call_model=None):
    if max_cases < 1:
        raise ValueError('The new-case budget must be positive')
    models = config.get('available_models', [])
    if sum(m.get('name') == model_name for m in models) != 1:
        raise ValueError('Select exactly one explicitly configured model')
    identity = {'plan': plan(contract, suites), 'reviewer': reviewer_identity(model_name, config),
                'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'measurement_sha256': hashlib.sha256((ROOT / 'backend/app/services/certification_versions/review_calibration.py').read_bytes()).hexdigest(),
                'execution_kind': 'injected_test_control' if call_model is not None else 'live_provider'}
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name(output.name + '.lock')
    # Prevent two operators from replaying the same pending case concurrently.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if output.exists():
            if not resume:
                raise ValueError('Existing evidence requires explicit resume or a new output path')
            report = json.loads(output.read_text())
            if any(report.get(k) != v for k, v in identity.items()):
                raise ValueError('Resume inputs changed; preserve this report and start a new output path')
            expected_keys = {(s.module_id, c.id) for s in suites for c in s.cases}
            for row in report['attempts']:
                content = {k: v for k, v in row.items() if k != 'row_sha256'}
                if row.get('row_sha256') != encode(content)[1] or (row['module_id'], row['case_id']) not in expected_keys:
                    raise ValueError('Saved evidence integrity check failed')
        elif resume:
            raise ValueError('There is no report to resume')
        else:
            report = {**identity, 'attempts': [], 'release_ready': False, 'credit_awarded': False}
        latest = {(r['module_id'], r['case_id']): r for r in report['attempts']}
        pending = [(s, c) for s in suites for c in s.cases
                   if (s.module_id, c.id) not in latest or
                   (retry_unavailable and latest[(s.module_id, c.id)]['grading_unavailable'])]
        report['stop_reason'] = 'running' if pending else 'no_pending_cases'
        report['summary'] = summarize(report)
        save_report(output, report)
        for suite, case in pending[:max_cases]:
            with report_only_metering() as usage:
                result = await evaluate_draft_structured_review(contract, suite.module_id, case.evidence,
                    model_name=model_name, system_config=config, call_model=call_model)
            row = {'module_id': suite.module_id, **measure_calibration_case(case, result),
                   'recorded_at': datetime.now(timezone.utc).isoformat(), 'usage': _usage_record(usage)}
            row['row_sha256'] = encode(row)[1]
            report['attempts'].append(row)
            report['summary'] = summarize(report)
            report['stop_reason'] = 'provider_unavailable' if row['grading_unavailable'] else 'case_budget_reached'
            save_report(output, report)
            print(json.dumps({'module_id': suite.module_id, 'case_id': case.id,
                              'matches': row['matches'], 'grading_unavailable': row['grading_unavailable']}), flush=True)
            if row['grading_unavailable']:
                break
        if report['summary']['pending_cases'] == 0 and report['summary']['unavailable_cases'] == 0:
            report['stop_reason'] = 'completed'
            save_report(output, report)
        return report
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', action='append', default=[])
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--config', type=Path, help='Private JSON model configuration; never copied to results')
    parser.add_argument('--model')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-cases', type=int, default=1)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--retry-unavailable', action='store_true')
    args = parser.parse_args(argv)
    try:
        contract, suites = load_suites(args.module)
        if not args.live:
            print(json.dumps(plan(contract, suites), indent=2))
            return 0
        if not args.config or not args.model or not args.output:
            parser.error('--live requires --config, --model and --output')
        if args.config.resolve() in {args.output.resolve(), args.output.with_name(args.output.name + '.lock').resolve()}:
            parser.error('Configuration and result paths must be different')
        config = json.loads(args.config.read_text())
        # Provider errors are summarized by the evaluator; never echo raw SDK
        # errors, request headers or private config through command-line logs.
        logging.disable(logging.CRITICAL)
        async def run():
            try:
                return await run_batch(contract, suites, model_name=args.model, config=config, output=args.output,
                    max_cases=args.max_cases, resume=args.resume, retry_unavailable=args.retry_unavailable)
            finally:
                from app.services.llm_service import aclose_loop_http_client
                await aclose_loop_http_client()
        report = asyncio.run(run())
        print(json.dumps(report['summary'], indent=2))
        return 0 if report['summary']['all_cases_matched'] else 1
    except (OSError, ValueError, TypeError, KeyError):
        print('Calibration did not complete. Check inputs, model availability and output lock; prior evidence is preserved.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
