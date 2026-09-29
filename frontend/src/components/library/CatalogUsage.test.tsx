import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { CatalogUsage } from './CatalogUsage'
import type { VerifiedCatalogItem } from '../../types/library'
it('distinguishes unknown requirements from a configured no-input workflow', () => {
  const view = render(<CatalogUsage item={{} as VerifiedCatalogItem} />)
  expect(screen.getByText(/Input requirements are not described/)).toBeInTheDocument()
  view.rerender(<CatalogUsage item={{ usage: { input: 'No manual run input is required.', output: 'Review findings.', output_names: [], notes: [] } } as unknown as VerifiedCatalogItem} />)
  expect(screen.getByText('No manual run input is required.')).toBeInTheDocument()
  expect(screen.queryByText(/Input requirements are not described/)).not.toBeInTheDocument()
})
it('summarizes output names on a card and exposes the whole list and caveats in detail', () => {
  const item = { usage: { input: 'Choose files', output: 'Workflow results', output_names: ['Findings', 'Citations', 'Summary'], notes: ['Fixed document access is checked at run time.'] } } as unknown as VerifiedCatalogItem
  const view = render(<CatalogUsage item={item} compact />)
  expect(screen.getByText(/Findings · Citations · \+1 more/)).toBeInTheDocument()
  view.rerender(<CatalogUsage item={item} />)
  expect(screen.getByText(/Findings · Citations · Summary/)).toBeInTheDocument()
  expect(screen.getByText('Fixed document access is checked at run time.')).toBeInTheDocument()
})
