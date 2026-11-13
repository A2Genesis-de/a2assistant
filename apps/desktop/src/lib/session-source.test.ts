import { describe, expect, it } from 'vitest'

import { isMessagingSource, sessionSourceSearchTerms } from './session-source'

describe('telegram messaging source registration', () => {
  it('treats telegram as a messaging source (own sidebar section)', () => {
    expect(isMessagingSource('telegram')).toBe(true)
  })

  it('is case/space insensitive on the source id', () => {
    expect(isMessagingSource('TELEGRAM')).toBe(true)
    expect(isMessagingSource('  telegram ')).toBe(true)
  })

  it('exposes the tg search alias so Telegram sessions are findable', () => {
    expect(sessionSourceSearchTerms('telegram')).toContain('tg')
  })

  it('does not flag local/CLI-ish sources as messaging (guard sanity)', () => {
    expect(isMessagingSource('cli')).toBe(false)
    expect(isMessagingSource(null)).toBe(false)
    expect(isMessagingSource(undefined)).toBe(false)
  })
})
