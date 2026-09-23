import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { ScheduleConfigFields } from './ScheduleConfigFields'
import { previewSchedule } from '../../api/automations'
import type { ScheduleTriggerConfig } from '../../types/automation'

vi.mock('../../api/automations', () => ({
  previewSchedule: vi.fn().mockResolvedValue({
    cron_expression: '0 9 * * *', timezone: 'Asia/Tokyo',
    next_runs: ['2026-09-24T00:00:00+00:00', '2026-09-25T00:00:00+00:00', '2026-09-26T00:00:00+00:00'],
  }),
}))
vi.mock('../shared/DocumentPickerDialog', () => ({
  DocumentPickerDialog: ({ onSelect }: { onSelect: (d: { uuid: string; title: string }[]) => void }) => (
    <button type="button" onClick={() => onSelect([{ uuid: 'd1', title: 'Award.pdf' }])}>pick doc</button>
  ),
}))
vi.mock('../../utils/schedule', async (orig) => ({
  ...(await orig<typeof import('../../utils/schedule')>()),
  browserTimeZone: () => 'America/Boise',
}))

function Harness({ initial }: { initial: ScheduleTriggerConfig }) {
  const [value, setValue] = useState(initial)
  return <ScheduleConfigFields value={value} onChange={setValue} folders={[]} />
}

const cfg: ScheduleTriggerConfig = {
  frequency: 'daily', time: '09:00', timezone: 'Asia/Tokyo', source: 'documents', document_uuids: [],
}

describe('ScheduleConfigFields', () => {
  it('shows the next run in the schedule zone and in the viewer\'s time', async () => {
    render(<Harness initial={cfg} />)
    await waitFor(() => expect(screen.getByText(/Next run:/)).toBeInTheDocument())
    const status = screen.getByRole('status')
    expect(status.textContent).toMatch(/9:00/)        // Tokyo
    expect(status.textContent).toMatch(/your time/)   // Boise differs
    expect(vi.mocked(previewSchedule).mock.calls[0][0]).toMatchObject({ frequency: 'daily', timezone: 'Asia/Tokyo' })
  })

  it('adds and removes specific documents', () => {
    render(<Harness initial={cfg} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose documents' }))
    fireEvent.click(screen.getByRole('button', { name: 'pick doc' }))
    expect(screen.getByText('Award.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Runs on/ }).textContent).toMatch(/1 document/)
    fireEvent.click(screen.getByRole('button', { name: 'Remove Award.pdf' }))
    expect(screen.queryByText('Award.pdf')).not.toBeInTheDocument()
  })
})
