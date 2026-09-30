import type { KBTestQuery } from '../../api/knowledge'

/** The same untruncated expectations in a quick check and the tuning wizard. */
export function QuestionExpectations({ question }: { question: KBTestQuery }) {
  return <div style={{ fontSize: 12, lineHeight: 1.6, overflowWrap: 'anywhere' }}>
    <strong style={{ color: 'var(--workspace-text)' }}>{question.query}</strong>
    <div style={{ color: 'var(--workspace-muted)', marginTop: 4 }}>Expected answer: {question.expected_answer || 'Not set — answer grading will be skipped for this question.'}</div>
    <div style={{ color: 'var(--workspace-muted)' }}>Expected sources: {question.expected_source_labels.length ? question.expected_source_labels.join(' · ') : 'Not specified'}</div>
    {question.expected_answer_contains && <div style={{ color: 'var(--workspace-muted)' }}>Required retrieved text: {question.expected_answer_contains}</div>}
    {question.category && <div style={{ color: 'var(--workspace-muted)' }}>Category: {question.category}</div>}
  </div>
}
