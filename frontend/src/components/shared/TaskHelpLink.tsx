import type { ReactNode } from 'react'

export function TaskHelpLink({ topic, children }: {
  topic: 'getting-started' | 'project-scope' | 'library-tools' | 'validation' | 'human-review' | 'source-recovery'
  children: ReactNode
}) {
  return <a href={`/docs#${topic}`} target="_blank" rel="noopener noreferrer"
    style={{ display: 'inline-block', padding: '6px 0', fontSize: 13, color: '#475569', textDecoration: 'underline', textUnderlineOffset: 3 }}>
    {children}<span className="sr-only"> (opens help in a new tab)</span>
  </a>
}
