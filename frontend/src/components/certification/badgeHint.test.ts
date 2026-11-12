import { describe, expect, it } from 'vitest'
import { certificationBadgeHint } from './badgeHint'

describe('certificationBadgeHint', () => {
  it('explains the level and the points, and names the next level', () => {
    const hint = certificationBadgeHint({ level: 'expert', xp: 1275, certified: false, title: 'Vandal Workflow Architect' })
    expect(hint).toContain('Certification level: Expert, with 1,275 XP.')
    expect(hint).toContain('XP (experience points) is earned by completing certification modules')
    expect(hint).toContain('Next level: Master at 1,300 XP (25 XP to go).')
  })

  it("uses the course's own levels when it has them", () => {
    const hint = certificationBadgeHint({ level: 'builder', xp: 300, certified: false, title: 'T', levels: [{ name: 'novice', xp: 0 }, { name: 'builder', xp: 200 }, { name: 'architect', xp: 500 }] })
    expect(hint).toContain('Next level: Architect at 500 XP (200 XP to go).')
  })

  it('says so at the highest level, once certified, and before starting', () => {
    expect(certificationBadgeHint({ level: 'architect', xp: 1700, certified: false, title: 'T' })).toContain('This is the highest level.')
    expect(certificationBadgeHint({ level: 'architect', xp: 1850, certified: true, title: 'Vandal Workflow Architect' })).toContain('Vandal Workflow Architect: you have completed the certification course, with 1,850 XP.')
    expect(certificationBadgeHint({ level: 'novice', xp: 0, certified: false, title: 'T' })).toMatch(/^Get Certified: /)
  })
})
