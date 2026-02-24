import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface SparklinePoint {
  score: number
  created_at: string
}

export function QualitySparkline({
  scores,
  width = 48,
  height = 16,
}: {
  scores: SparklinePoint[]
  width?: number
  height?: number
}) {
  if (scores.length < 2) return null

  const latestScore = scores[scores.length - 1].score
  const color = latestScore >= 90 ? '#16a34a' : latestScore >= 70 ? '#d97706' : '#dc2626'

  return (
    <div style={{ width, height, display: 'inline-flex', alignItems: 'center' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={scores}>
          <Line
            type="monotone"
            dataKey="score"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
