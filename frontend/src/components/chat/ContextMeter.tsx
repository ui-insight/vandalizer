import { useState } from 'react'

interface ContextMeterProps {
  tokensUsed: number
  contextWindow: number
  onClick: () => void
}

function formatTokenCount(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(0)}k`
  return String(n)
}

export function ContextMeter({ tokensUsed, contextWindow, onClick }: ContextMeterProps) {
  const [hover, setHover] = useState(false)

  if (tokensUsed <= 0 || contextWindow <= 0) return null

  const ratio = Math.min(tokensUsed / contextWindow, 1)
  const percent = Math.round(ratio * 100)

  // Color transitions: gray <70%, amber 70-90%, red >90%
  let strokeColor = '#9ca3af'
  let textColor = '#6b7280'
  if (ratio >= 0.9) {
    strokeColor = '#ef4444'
    textColor = '#ef4444'
  } else if (ratio >= 0.7) {
    strokeColor = '#f59e0b'
    textColor = '#d97706'
  }

  const size = 30
  const strokeWidth = 3
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference * (1 - ratio)

  return (
    <div style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        onClick={onClick}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: '50%',
          transition: 'background 0.15s',
          ...(hover ? { background: '#f3f4f6' } : {}),
        }}
        title={`${formatTokenCount(tokensUsed)} / ${formatTokenCount(contextWindow)} tokens used`}
        aria-label={`Context usage: ${percent}%`}
      >
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth={strokeWidth}
          />
          {/* Progress arc */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.4s ease, stroke 0.3s ease' }}
          />
        </svg>
        <span
          style={{
            position: 'absolute',
            fontSize: 8,
            fontWeight: 700,
            color: textColor,
            userSelect: 'none',
            transition: 'color 0.3s ease',
          }}
        >
          {percent}%
        </span>
      </button>
    </div>
  )
}
