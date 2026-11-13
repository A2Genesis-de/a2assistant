import { afterEach, describe, expect, it } from 'vitest'

import { claimRouteLink, resetRouteLinksForTests } from './deep-link'

afterEach(() => resetRouteLinksForTests())

describe('a link is acted on once, by the page on its scope', () => {
  it('leaves a link for another profile alone and lets only the first mounted page take it', () => {
    const params = new URLSearchParams({ profile: 'b', server: 'files' })

    expect(claimRouteLink('k1', params, 'a')).toBe(false)
    expect(claimRouteLink('k1', params, 'b')).toBe(true)
    expect(claimRouteLink('k1', params, 'b')).toBe(false)
    expect(claimRouteLink('k2', params, 'b')).toBe(true)
  })
})
