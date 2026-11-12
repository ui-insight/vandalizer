import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ContextMenu } from './ContextMenu'

// Menu items and dividers in the order they are drawn.
function layout() {
  return Array.from(screen.getByRole('menu').querySelectorAll('[role="menuitem"], [role="separator"]')).map((el) =>
    el.getAttribute('role') === 'separator' ? '—' : el.textContent,
  )
}

describe('ContextMenu', () => {
  it('groups a folder menu and keeps Delete apart behind a divider', () => {
    const fn = vi.fn()
    render(
      <ContextMenu
        x={0} y={0} onClose={fn}
        onAskFolder={fn} onRunWorkflow={fn} onAddToKB={fn}
        onRename={fn} onMove={fn} onConvertToTeam={fn}
        onExport={fn} onDelete={fn}
      />,
    )
    expect(layout()).toEqual([
      'Ask about folder', 'Run workflow on folder', 'Add to knowledge base',
      '—',
      'Rename', 'Move to…', 'Convert to team folder',
      '—',
      'Export contents',
      '—',
      'Delete',
    ])
  })

  it('leaves out Copy UUID unless the caller offers it', () => {
    const fn = vi.fn()
    const { rerender } = render(<ContextMenu x={0} y={0} onClose={fn} onRename={fn} onDelete={fn} />)
    expect(screen.queryByRole('menuitem', { name: 'Copy UUID' })).toBeNull()
    expect(layout()).toEqual(['Rename', '—', 'Delete'])

    rerender(<ContextMenu x={0} y={0} onClose={fn} onRename={fn} onCopyUuid={fn} onDelete={fn} />)
    expect(layout()).toEqual(['Rename', '—', 'Copy UUID', '—', 'Delete'])
  })

  it('draws no divider when there is a single group', () => {
    render(<ContextMenu x={0} y={0} onClose={vi.fn()} onRename={vi.fn()} onMove={vi.fn()} />)
    expect(layout()).toEqual(['Rename', 'Move to…'])
  })
})
