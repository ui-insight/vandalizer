import type { KBTestQuery } from '../../api/knowledge'

/** The same untruncated expectations in a quick check and the tuning wizard. */
export function QuestionExpectations({ question }: { question: KBTestQuery }) {
  return <div style={{ fontSize: 12, lineHeight: 1.6, overflowWrap: 'anywhere' }}>
    <strong style={{ color: '#ededed' }}>{question.query}</strong>
    <div style={{ color: '#c5c9d0', marginTop: 4 }}>Expected answer: {question.expected_answer || 'Not set — answer grading will be skipped for this question.'}</div>
    <div style={{ color: '#c5c9d0' }}>Expected sources: {question.expected_source_labels.length ? question.expected_source_labels.join(' · ') : 'Not specified'}</div>
    {question.expected_answer_contains && <div style={{ color: '#c5c9d0' }}>Required retrieved text: {question.expected_answer_contains}</div>}
    {question.category && <div style={{ color: '#b8bec7' }}>Category: {question.category}</div>}
  </div>
}
