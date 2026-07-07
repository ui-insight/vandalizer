import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import 'vitest-axe/extend-expect'
import { Toggle } from './components/shared/Toggle'
import { ConfirmDialog } from './components/shared/ConfirmDialog'
import { ErrorBanner } from './components/shared/RunBanners'
import { ModelEffortPicker } from './components/ModelEffortPicker'
import { ProgressRow } from './components/shared/ProgressRow'
import { AttachmentList } from './components/chat/AttachmentList'

// Standing automated accessibility gate (WCAG pass 3). Renders representative
// remediated primitives and asserts zero axe-core violations, so a11y
// regressions on these surface in CI. Expand coverage over time.
describe('a11y — no axe violations', () => {
  it('Toggle (role=switch)', async () => {
    const { container } = render(
      <Toggle label="Enable feature" description="Turns the thing on" checked={false} onChange={() => {}} />,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('ConfirmDialog (dialog + focus trap)', async () => {
    const { container } = render(
      <ConfirmDialog
        open
        title="Delete item?"
        message="This cannot be undone."
        destructive
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('ErrorBanner (role=alert)', async () => {
    const { container } = render(<ErrorBanner message="Something went wrong" />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('ModelEffortPicker (radiogroup)', async () => {
    const models = [
      { name: 'gpt-4o', tag: 'gpt-4o', tier: 'high', speed: 'standard', privacy: 'external' },
      { name: 'haiku', tag: 'haiku', tier: 'standard', speed: 'fast', privacy: 'external' },
    ] as React.ComponentProps<typeof ModelEffortPicker>['models']
    const { container } = render(
      <ModelEffortPicker models={models} selectedModel="gpt-4o" onChange={() => {}} />,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('ProgressRow (role=progressbar)', async () => {
    const { container } = render(
      <ProgressRow label="Uploading" subtitle="42%" pct={42} color="#7c3aed" />,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('AttachmentList (icon-button labels)', async () => {
    const { container } = render(
      <AttachmentList
        fileAttachments={[{ id: 'f1', filename: 'report.pdf' } as never]}
        urlAttachments={[]}
        selectedDocUuids={[]}
        onRemoveFile={() => {}}
      />,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
