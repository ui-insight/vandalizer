import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { QualityComparisonCard, type BaselinePoint } from './QualityComparisonCard'

// Ticket: chat called 94% vs 92% "a real, if modest, gain" while this card,
// deciding on its own band (about twice the optimizer's), said "No
// significant change" beside an enabled Apply button. The run's verdict wins.
const baselines: BaselinePoint[] = [
  { id: 'default', label: 'Your current settings', score: 0.92, color: '#888' },
  { id: 'optimized', label: 'Best config', score: 0.94, color: '#22c55e', emphasised: true },
]
// SE of 0.011: the optimizer's band is ±2.2 pts; the card's own was ±4.3.
const variance = 0.011

describe("QualityComparisonCard follows the run's verdict", () => {
  it('shows the lift when the run says it cleared the noise', () => {
    render(<QualityComparisonCard baselines={baselines} variance={variance} tiedWithBaseline={false} />)

    expect(screen.queryByText(/No significant change/)).not.toBeInTheDocument()
    expect(screen.getByText('+2pts')).toBeInTheDocument()
  })

  it('says no significant change when the run calls it a tie', () => {
    render(<QualityComparisonCard
      baselines={[baselines[0], { ...baselines[1], score: 0.97 }]}
      variance={variance}
      tiedWithBaseline
    />)

    expect(screen.getByText(/No significant change/)).toBeInTheDocument()
    expect(screen.getByText(/\+5pts difference is inside the judge's measurement noise/)).toBeInTheDocument()
  })

  it('without a run verdict, keeps its own estimate', () => {
    render(<QualityComparisonCard baselines={baselines} variance={variance} />)

    expect(screen.getByText(/No significant change/)).toBeInTheDocument()
  })

  it("doesn't claim the CI spans zero when the tie came from the score band", () => {
    render(<QualityComparisonCard
      baselines={baselines}
      variance={variance}
      tiedWithBaseline
      liftCI={{ lift: 0.02, lower: 0.004, upper: 0.04, p_value: 0.08, n_queries: 12, n_iterations: 1000, confidence_level: 0.95 }}
    />)

    expect(screen.getByText(/No significant change/)).toBeInTheDocument()
    expect(screen.queryByText(/spans zero/)).not.toBeInTheDocument()
  })
})

// Ticket: the editor showed Optimized 95% against Current 93% and called it a
// "+1pts difference". The stated difference must be between the shown numbers.
describe('QualityComparisonCard states the difference between the numbers it shows', () => {
  const rounded: BaselinePoint[] = [
    { id: 'default', label: 'Current settings', score: 0.934, color: '#888' },
    { id: 'optimized', label: 'Optimized settings', score: 0.946, color: '#22c55e', emphasised: true },
  ]

  it('95% against 93% is a 2-point difference', () => {
    render(<QualityComparisonCard baselines={rounded} variance={variance} tiedWithBaseline />)

    expect(screen.getByText('95%')).toBeInTheDocument()
    expect(screen.getByText('93%')).toBeInTheDocument()
    expect(screen.getByText(/\+2pts difference is inside the judge's measurement noise/)).toBeInTheDocument()
  })

  it('a drop is shown with a minus sign, never a plus', () => {
    render(<QualityComparisonCard
      baselines={[{ ...rounded[0], score: 0.91 }, { ...rounded[1], score: 0.88 }]}
      variance={variance}
      tiedWithBaseline={false}
    />)

    expect(screen.getByText('-3pts')).toBeInTheDocument()
  })
})
