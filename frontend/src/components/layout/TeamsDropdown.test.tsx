import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { TeamsDropdown } from './TeamsDropdown'
let user = { is_admin: false, is_staff: false, is_examiner: false }
let role = 'member'
let count = 1
vi.mock('@tanstack/react-router', () => ({ Link: ({ to, children, search: _search, ...props }: { to: string; children: ReactNode; search?: unknown }) => <a href={to} {...props}>{children}</a> }))
vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ teams: Array.from({ length: count }, (_, i) => ({ uuid: String(i), name: `Team ${i}` })), currentTeam: { uuid: '0', name: 'Team 0', role }, switchTeam: vi.fn(), refreshTeams: vi.fn() }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user, logout: vi.fn() }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanel: () => ({ openPanel: vi.fn() }) }))
vi.mock('../../hooks/useMyReviewCount', () => ({ useMyReviewCount: () => ({ count: 0 }) }))
vi.mock('./VersionMenuFooter', () => ({ VersionMenuFooter: () => null }))
beforeEach(() => { role = 'member'; count = 1; user = { is_admin: false, is_staff: false, is_examiner: false } })
function open() { render(<><TeamsDropdown /><button>After menu</button></>); fireEvent.click(screen.getByRole('button', { name: 'Account menu: Team 0' })) }
describe('account navigation', () => {
  it.each(['owner', 'admin'])('offers Team Admin for team %s', r => { role = r; open(); expect(screen.getByRole('menuitem', { name: 'Team Admin' })).toHaveAttribute('href', '/admin') })
  it('does not offer inaccessible admin navigation to examiners', () => { user.is_examiner = true; open(); expect(screen.queryByRole('menuitem', { name: /Admin|Analytics/ })).not.toBeInTheDocument(); expect(screen.getByRole('menuitem', { name: 'Shared items' })).toBeInTheDocument() })
  it('uses Admin for staff', () => { user.is_staff = true; open(); expect(screen.getByRole('menuitem', { name: 'Admin' })).toBeInTheDocument() })
  it('closes on Tab without preventing normal tab movement', () => { open(); const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }); fireEvent(screen.getAllByRole('menuitem')[0], event); expect(event.defaultPrevented).toBe(false); expect(screen.queryByRole('menu')).not.toBeInTheDocument() })
  it('closes when focus moves outside and restores the trigger on Escape', () => { open(); fireEvent.keyDown(screen.getAllByRole('menuitem')[0], { key: 'Escape' }); expect(screen.getByRole('button', { name: 'Account menu: Team 0' })).toHaveFocus(); fireEvent.click(screen.getByRole('button', { name: 'Account menu: Team 0' })); fireEvent.blur(screen.getAllByRole('menuitem')[0], { relatedTarget: screen.getByRole('button', { name: 'After menu' }) }); expect(screen.queryByRole('menu')).not.toBeInTheDocument() })
  it('filters large memberships while leaving account actions available', () => { count = 12; open(); const search = screen.getByRole('searchbox', { name: 'Find a team' }); expect(search).toHaveFocus(); fireEvent.change(search, { target: { value: 'Team 11' } }); expect(screen.getByRole('menuitem', { name: 'Team 11' })).toBeInTheDocument(); expect(screen.queryByRole('menuitem', { name: 'Team 0 (current)' })).not.toBeInTheDocument(); expect(screen.getByRole('menuitem', { name: 'Logout' })).toBeInTheDocument(); fireEvent.keyDown(search, { key: 'ArrowDown' }); expect(screen.getByRole('menuitem', { name: 'Team 11' })).toHaveFocus() })
})
