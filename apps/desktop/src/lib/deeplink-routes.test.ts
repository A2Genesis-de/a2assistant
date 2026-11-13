import { describe, expect, it } from 'vitest'

import { resolveDeepLinkAction } from './deeplink-routes'

describe('resolveDeepLinkAction', () => {
  it('routes unified plugin install deeplinks', () => {
    expect(
      resolveDeepLinkAction({
        kind: 'plugin',
        name: 'install',
        params: { repo: 'owner/repo', enable: '0', force: '1' }
      })
    ).toEqual({
      type: 'plugin-install',
      repo: 'owner/repo',
      enable: false,
      force: true,
      legacyHint: null
    })
  })

  it('ignores catalog=, never falling through to a git-path install', () => {
    const cases: Record<string, string>[] = [{ catalog: 'web-search-plus' }, { catalog: 'nope', repo: 'evil/repo' }, { catalog: '' }]

    for (const params of cases) {
      expect(resolveDeepLinkAction({ kind: 'plugin', name: 'install', params })).toEqual({ type: 'ignore' })
    }
  })

  it('does not trust URL catalog metadata on a repository install', () => {
    const params = {
      repo: 'https://github.com/owner/repo#plugins/example',
      catalog_name: 'example',
      sha: '0123456789abcdef0123456789abcdef01234567',
      enable: '1'
    }

    const url = new URL(`hermes://plugin/install?${new URLSearchParams(params)}`)

    expect(
      resolveDeepLinkAction({
        kind: url.hostname,
        name: url.pathname.slice(1),
        params: Object.fromEntries(url.searchParams)
      })
    ).toEqual({
      type: 'plugin-install',
      repo: params.repo,
      enable: true,
      force: false,
      legacyHint: null
    })
  })

  it('routes legacy plugin-agent alias', () => {
    expect(
      resolveDeepLinkAction({
        kind: 'plugin-agent',
        name: '',
        params: { repo: 'owner/repo' }
      })
    ).toMatchObject({ type: 'plugin-install', legacyHint: 'agent' })
  })

  it('only routes skill installs with an explicit, unchanged identifier', () => {
    const identifier = 'skills-sh/owner/repo/a skill?mode=one&two#readme'
    const url = new URL(`hermes://skill/install?${new URLSearchParams({ identifier })}`)

    expect(
      resolveDeepLinkAction({
        kind: url.hostname,
        name: url.pathname.slice(1),
        params: Object.fromEntries(url.searchParams)
      })
    ).toEqual({ type: 'skill-install', identifier })

    const invalidParams: Record<string, string>[] = [
      {},
      { identifier: '' },
      { identifier: '   ' },
      { identifier: ' official/skill ' }
    ]

    for (const params of invalidParams) {
      expect(resolveDeepLinkAction({ kind: 'skill', name: 'install', params })).toEqual({ type: 'ignore' })
    }

    expect(resolveDeepLinkAction({ kind: 'skill', name: 'remove', params: { identifier } })).toEqual({ type: 'ignore' })
    expect(resolveDeepLinkAction({ kind: 'plugin', name: 'install', params: {} })).toEqual({ type: 'ignore' })
  })

  it('preserves connector completion routing without treating browser status as authority', () => {
    expect(
      resolveDeepLinkAction({
        kind: 'connections',
        name: 'done',
        params: { op: ' operation-1 ', status: ' connected ' }
      })
    ).toEqual({ type: 'connection-done', op: 'operation-1', status: 'connected' })
    expect(
      resolveDeepLinkAction({
        kind: 'connections',
        name: 'done',
        params: { status: 'connected' }
      })
    ).toEqual({ type: 'ignore' })
  })

  it('routes blueprint composer inserts', () => {
    expect(
      resolveDeepLinkAction({
        kind: 'blueprint',
        name: 'morning-brief',
        params: { time: '08:00' }
      })
    ).toEqual({
      type: 'composer-blueprint',
      name: 'morning-brief',
      params: { time: '08:00' }
    })
  })
})
