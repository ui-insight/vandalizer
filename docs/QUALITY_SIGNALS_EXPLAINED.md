# Quality signals

Quality labels describe performance on recorded examples. They are separate from permission to share, examiner review, successful execution, and course certification.

## Reading the label

| Label | Meaning |
|---|---|
| Strong on tested examples | The recorded evaluation falls in the configured good or excellent tier, or the workflow rubric awarded A or B. Inspect the coverage and exceptions for your task. |
| Mixed results | The recorded evaluation falls in the configured fair tier, or the workflow rubric awarded C. |
| Needs improvement | A measured result falls below the configured fair tier, or the workflow rubric awarded D or F. |
| Not evaluated | No measured score or rubric result is available. An author's rating is not a measured evaluation. |
| Evaluation recorded | A score exists but its tier or rubric interpretation was not recorded. |
| Evaluation outdated | A known configuration, model, test-set, plan, or freshness flag means the previous evaluation may not describe current behavior. |
| Needs review | Monitoring detected a regression or a critical alert. Workflow result summaries also use this when a check fails or a structural diagnostic reports an error. |

Knowledge-base comparisons use **Improved on tested questions** or **No measured improvement** when a measured AI-only baseline exists. These describe the comparison, not absolute answer quality. Exact comparison values remain in the evaluation details.

The numeric scoring rules and configured tier thresholds are unchanged. The interface translates the stored tier; it does not apply a new universal percentage cutoff. Workflows, extractions, and knowledge bases measure different aspects of performance, so equal scores do not imply equivalent reliability.

## Evidence alongside quality

The badge shows the number of tested examples when it is recorded. Fewer than five examples, or an explicit sample-size penalty, is labeled **Limited evidence**. This is a prompt to inspect coverage, not a statistical confidence guarantee. Five examples alone do not establish representative coverage.

If sample size is missing, the interface says **Sample size not recorded**. It does not infer it from a score, number of checks, or number of validation runs. Author assertions are identified separately and do not receive a measured quality endorsement.

Open **View evaluation** on a resource badge or **Show details** in chat to inspect the exact score, available sample size and evaluation date. Chat details also retain accuracy, consistency, run count, rubric grade, alerts, and tuning evidence when available. The workflow result's **Scoring details** preserves its letter grade. Validation charts, diagnostic tables, comparisons and exports retain numerical metrics.

## Interpreting results

A score of 95 is not automatically a 95% chance that the next answer is correct. Scores may combine multiple measures and sample-size adjustments. Check what was measured, which examples and version were used, and which checks failed or were skipped.

Extraction accuracy compares values with saved expected answers; consistency measures agreement across repeated runs, including consistently wrong answers. Knowledge-base scores can combine retrieval, coverage, answer grading and other components. Workflow results use their own checks and rubric. The relevant validation views show those breakdowns.

Adding representative examples can uncover failures and reduce a score while improving the usefulness of the evaluation. Aim for coverage and understood limitations rather than a perfect number. Missing evaluation is not a failed evaluation. A completed run is not evidence that every result is correct.

## Catalog discovery

Quality filters group measured good and excellent tiers under **Strong on tested examples**, fair under **Mixed results**, and measured below-tier results under **Needs improvement**. **Not evaluated** includes author-provided assertions. **Needs review** includes pending regressions. Filtering happens before pagination, so totals cover the full matching collection.

The quality spotlight contains measured strong results without pending regressions. A spotlight position does not establish fitness for a new task; inspect each item's evidence before adopting it.
