import { describe, it, expect } from 'vitest'
import { nameWithoutEmail } from './displayName'

describe('nameWithoutEmail', () => {
  it('strips a trailing bracketed email that matches', () => {
    expect(
      nameWithoutEmail('Kasireddy, Kiran Kumar Reddy (kkasireddy@uidaho.edu)', 'kkasireddy@uidaho.edu'),
    ).toBe('Kasireddy, Kiran Kumar Reddy')
  })

  it('matches the email case-insensitively', () => {
    expect(nameWithoutEmail('Jane Doe (JDoe@uidaho.edu)', 'jdoe@uidaho.edu')).toBe('Jane Doe')
  })

  it('strips square brackets too', () => {
    expect(nameWithoutEmail('Jane Doe [jdoe@uidaho.edu]', 'jdoe@uidaho.edu')).toBe('Jane Doe')
  })

  it('leaves a name without an embedded email alone', () => {
    expect(nameWithoutEmail('Jane Doe', 'jdoe@uidaho.edu')).toBe('Jane Doe')
  })

  it('does not strip a different email', () => {
    expect(nameWithoutEmail('Jane Doe (jdoe@uidaho.edu)', 'other@uidaho.edu')).toBe('Jane Doe (jdoe@uidaho.edu)')
  })

  it('does not strip an email in the middle of the name', () => {
    expect(nameWithoutEmail('Jane (jdoe@uidaho.edu) Doe', 'jdoe@uidaho.edu')).toBe('Jane (jdoe@uidaho.edu) Doe')
  })

  it('keeps the name when it is only the bracketed email', () => {
    expect(nameWithoutEmail('(jdoe@uidaho.edu)', 'jdoe@uidaho.edu')).toBe('(jdoe@uidaho.edu)')
  })

  it('handles null/undefined name and email', () => {
    expect(nameWithoutEmail(null, 'jdoe@uidaho.edu')).toBeNull()
    expect(nameWithoutEmail(undefined, 'jdoe@uidaho.edu')).toBeNull()
    expect(nameWithoutEmail('Jane Doe', null)).toBe('Jane Doe')
    expect(nameWithoutEmail('Jane Doe', undefined)).toBe('Jane Doe')
  })
})
