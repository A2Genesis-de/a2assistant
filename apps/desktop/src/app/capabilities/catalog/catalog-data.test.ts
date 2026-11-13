import { afterEach, describe, expect, it, vi } from 'vitest'

import { parseCatalog } from './catalog-data'

afterEach(() => vi.unstubAllGlobals())

describe('public catalog data', () => {
  it('preserves every source and distinct install identifier, including same-named skills', () => {
    const rows = ['official', 'github', 'community', 'future-source'].map(source => ({
      name: 'research',
      identifier: `${source}/research`,
      source,
      author: `${source} maintainer`,
      description: `Research from ${source}`,
      category: 'research',
      categoryLabel: 'Research',
      tags: [`${source}-tag`],
      envVars: [`${source.toUpperCase()}_KEY`]
    }))

    // Same source, different identifier is also a distinct install target.
    rows.push({ ...rows[0], identifier: 'official/alternate/research' })

    const entries = parseCatalog('skills', rows)

    expect(entries).toHaveLength(rows.length)
    expect(new Set(entries.map(entry => entry.id)).size).toBe(rows.length)
    rows.forEach(row => {
      const entry = entries.find(candidate => candidate.identifier === row.identifier)
      expect(entry).toMatchObject({
        name: row.name,
        identifier: row.identifier,
        source: row.source,
        author: row.author,
        description: row.description,
        categoryLabel: row.categoryLabel,
        tags: row.tags,
        requirements: row.envVars
      })
      expect(entry?.search).toContain(row.source)
      expect(entry?.search).toContain(row.tags[0])
    })
  })

  it('keeps each plugin tier, pinned install target, and published detail metadata together', () => {
    const rows = ['official', 'community', 'future-tier'].map(tier => ({
      name: `${tier}-plugin`,
      tier,
      repo: `https://github.com/example/${tier}-plugins`,
      subdir: 'packages/weather',
      sha: 'a'.repeat(40),
      maintainer: `${tier} maintainer`,
      overview: `Overview for ${tier}`,
      version: '1.2.3',
      requiresHermes: '>=0.17',
      platforms: ['macos', 'linux'],
      docsUrl: `https://example.com/${tier}/docs`,
      capabilities: {
        providesTools: [`${tier}_forecast`],
        providesHooks: ['on_session_start'],
        requiresEnv: ['WEATHER_KEY']
      }
    }))

    const entries = parseCatalog('plugins', rows)

    expect(entries).toHaveLength(rows.length)
    rows.forEach(row => {
      const entry = entries.find(candidate => candidate.name === row.name)
      expect(entry).toMatchObject({
        name: row.name,
        source: row.tier,
        repo: row.repo,
        sha: row.sha,
        subdir: row.subdir,
        author: row.maintainer,
        overview: row.overview,
        version: row.version,
        requiresHermes: row.requiresHermes,
        platforms: row.platforms,
        docsUrl: row.docsUrl,
        sourceUrl: row.repo,
        tools: row.capabilities.providesTools,
        hooks: row.capabilities.providesHooks,
        requirements: row.capabilities.requiresEnv
      })
      expect(entry?.search).toContain(row.capabilities.providesTools[0])
    })
  })

  it('only renders plugin images hosted on GitHub so the browser never fans out to third-party hosts', () => {
    const base = { name: 'x', tier: 'community', repo: 'https://github.com/o/r', sha: 'a'.repeat(40), version: '1.4.0' }

    const [github, offhost, http] = parseCatalog('plugins', [
      { ...base, name: 'github', image: 'https://raw.githubusercontent.com/o/r/abc/banner.png' },
      { ...base, name: 'offhost', image: 'https://cdn.example.com/banner.png' },
      { ...base, name: 'http', image: 'http://github.com/o/r/banner.png' }
    ])

    expect(github.imageUrl).toBe('https://raw.githubusercontent.com/o/r/abc/banner.png')
    expect(github.version).toBe('1.4.0')
    expect(offhost.imageUrl).toBeNull()
    expect(http.imageUrl).toBeNull()
  })

  it('rejects a non-catalog response instead of treating an error payload as an empty catalog', () => {
    expect(() => parseCatalog('skills', { error: 'Service unavailable' })).toThrow('Invalid catalog response')
  })
})
