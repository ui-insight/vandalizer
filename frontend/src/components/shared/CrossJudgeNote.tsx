import { Scale } from 'lucide-react'
import type { CrossJudge } from '../../api/knowledge'

interface Props {
  crossJudge: CrossJudge
  primaryScore: number
  primaryJudge: string | null
}

/**
 * Surfaces a cross-judge sanity check: "judge A says 84%, judge B says 79%".
 * Large deltas suggest the headline score is judge-specific (self-bias);
 * small deltas tighten the credibility of the comparison.
 */
export function CrossJudgeNote({ crossJudge, primaryScore, primaryJudge }: Props) {
  const deltaPts = crossJudge.delta * 100
  const absDeltaPts = Math.abs(deltaPts)
  // "Large" disagreement = 10pts. Arbitrary but matches the common case where
  // a single judge swing is news-worthy.
  const tone: 'good' | 'warn' = absDeltaPts > 10 ? 'warn' : 'good'
  const fg = tone === 'good' ? '#86efac' : '#fbbf24'
  const bg = tone === 'good' ? 'rgba(34, 197, 94, 0.08)' : 'rgba(245, 158, 11, 0.08)'
  const border = tone === 'good' ? 'rgba(34, 197, 94, 0.25)' : 'rgba(245, 158, 11, 0.3)'

  return (
    <div style={{
      padding: '10px 14px', backgroundColor: bg, border: `1px solid ${border}`,
      borderRadius: 8, display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <Scale size={16} style={{ color: fg }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: fg }}>
          Cross-judge check: {tone === 'good' ? 'judges agree' : 'judges disagree'}
        </div>
        <div style={{ fontSize: 11, color: '#aaa', marginTop: 2, lineHeight: 1.4 }}>
          <strong>{primaryJudge || 'primary'}</strong> scored {(primaryScore * 100).toFixed(0)}% ·{' '}
          <strong>{crossJudge.model}</strong> scored {(crossJudge.score * 100).toFixed(0)}%{' '}
          ({deltaPts >= 0 ? '+' : ''}{deltaPts.toFixed(0)}pts).
          {tone === 'warn' && ' Treat the headline with care.'}
        </div>
      </div>
    </div>
  )
}
