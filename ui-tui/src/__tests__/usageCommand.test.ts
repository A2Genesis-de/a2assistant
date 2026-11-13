import type { SessionUsageResponse } from '@hermes/shared/gateway-types'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sessionCommands } from '../app/slash/commands/session.js'
import { applyLocale, resetLocale, t } from '../i18n/runtime.js'

const usageCommand = sessionCommands.find(cmd => cmd.name === 'usage')!

const guarded =
  <T>(fn: (r: T) => void) =>
  (r: null | T) => {
    if (r) {
      fn(r)
    }
  }

/** Build a ctx whose rpc routes by method name to a supplied map of results. */
const buildCtx = (results: Record<string, unknown>) => {
  const sys = vi.fn()
  const panel = vi.fn()

  const rpc = vi.fn((method: string, _params: unknown) => Promise.resolve(results[method]))

  const ctx = {
    gateway: { rpc },
    guarded,
    guardedErr: vi.fn(),
    sid: 'sid-1',
    stale: () => false,
    transcript: { page: vi.fn(), panel, sys }
  }

  const run = async (arg: string) => {
    usageCommand.run(arg, ctx as any, 'usage')
    await rpc.mock.results[0]?.value
    await Promise.resolve()
    await Promise.resolve()
  }

  return { ctx, panel, run, sys }
}

const baseUsage = (overrides: Partial<SessionUsageResponse> = {}): SessionUsageResponse =>
  ({ calls: 0, input: 0, output: 0, total: 0, ...overrides }) as SessionUsageResponse

const printed = (sys: ReturnType<typeof vi.fn>) => sys.mock.calls.map(c => c[0]).join('\n')

describe('/usage slash command', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('resolves its words at run time, so a locale pack applied after import is observed', async () => {
    applyLocale('xx', {
      lang: 'xx',
      messages: { 'slashCmd.session.usage.noCalls': 'ZZ-NOCALLS' },
      surface: 'tui'
    })

    try {
      const { run, sys } = buildCtx({ 'session.usage': baseUsage() })
      await run('')
      expect(printed(sys)).toContain('ZZ-NOCALLS')
    } finally {
      resetLocale()
    }
  })

  it('says "no API calls yet" and draws no panel before the first call', async () => {
    const { panel, run, sys } = buildCtx({ 'session.usage': baseUsage() })
    await run('')
    expect(printed(sys)).toContain(t('slashCmd.session.usage.noCalls'))
    expect(panel).not.toHaveBeenCalled()
  })

  it('draws the session totals panel once there are calls', async () => {
    const { panel, run } = buildCtx({ 'session.usage': baseUsage({ calls: 3, input: 10, output: 5, total: 15 }) })
    await run('')
    expect(panel).toHaveBeenCalledWith(t('slashCmd.session.usage.usageTitle'), expect.any(Array))
  })
})
