import { describe, expect, it } from 'vitest'

import { TRANSLATIONS } from '@/i18n'
import { en } from '@/i18n/en'

import {
  ERROR_CODE_KEYS,
  errorCardActions,
  errorCardOffers,
  errorCardSeverity,
  type ErrorSurface,
  formatErrorDiagnostics,
  formatResetClock,
  parseErrorSurface,
  scheduledRetryDelayMs
} from './error-surface'
import { errorCardText } from './error-surface-copy'

describe('parseErrorSurface', () => {
  it('accepts a valid descriptor', () => {
    expect(parseErrorSurface({ layer: 'streaming', code: 'stream_drop', retryable: true })).toEqual({
      layer: 'streaming',
      code: 'stream_drop',
      retryable: true
    })
  })

  it('accepts every documented layer', () => {
    for (const layer of ['provider', 'endpoint', 'streaming', 'auth', 'billing', 'gateway', 'runtime', 'disk']) {
      expect(parseErrorSurface({ layer, code: 'x', retryable: false })?.layer).toBe(layer)
    }
  })

  it('rejects unknown layers and non-objects', () => {
    expect(parseErrorSurface({ layer: 'blockchain', code: 'x', retryable: true })).toBeNull()
    expect(parseErrorSurface('provider')).toBeNull()
    expect(parseErrorSurface(null)).toBeNull()
    expect(parseErrorSurface(undefined)).toBeNull()
    expect(parseErrorSurface(7)).toBeNull()
  })

  it('defaults code and retryable when missing', () => {
    expect(parseErrorSurface({ layer: 'gateway' })).toEqual({ layer: 'gateway', code: 'unknown', retryable: true })
  })

  it('honors retryable=false', () => {
    expect(parseErrorSurface({ layer: 'auth', code: 'auth_permanent', retryable: false })?.retryable).toBe(false)
  })

  it('carries the failing session identity when present', () => {
    const surface = parseErrorSurface({
      layer: 'provider',
      code: 'rate_limit',
      retryable: true,
      provider: 'openrouter',
      model: 'test/m1'
    })

    expect(surface?.provider).toBe('openrouter')
    expect(surface?.model).toBe('test/m1')
    // Absent identity yields no keys, not empty strings.
    expect(parseErrorSurface({ layer: 'provider', code: 'x', retryable: true })?.provider).toBeUndefined()
  })
})

describe('formatErrorDiagnostics', () => {
  it('prefers the descriptor identity over the caller fallback', () => {
    const text = formatErrorDiagnostics({
      errorText: 'boom',
      // Foreground composer atom — potentially stale by click time.
      model: 'some/other-model',
      surface: { layer: 'provider', code: 'rate_limit', retryable: true, provider: 'openrouter', model: 'failed/model' }
    })

    expect(text).toContain('provider: openrouter')
    expect(text).toContain('model: failed/model')
    expect(text).not.toContain('some/other-model')
  })

  it('stamps the recorded failure time, never the copy time (#141348)', () => {
    expect(formatErrorDiagnostics({ errorText: 'boom', failedAt: 1_792_000_000 })).toContain(
      'time: 2026-10-14T17:46:40.000Z'
    )
  })

  it('omits absent fields without leaving blank lines', () => {
    const text = formatErrorDiagnostics({ errorText: 'boom' })

    expect(text).not.toContain('time:')
    expect(text).not.toContain('layer:')
    expect(text).not.toContain('model:')
    expect(text.split('\n').every(line => line.trim().length > 0)).toBe(true)
  })
})

// The card body and the buttons under it must agree: a body that says "retry"
// while the plan hides the Retry button leaves the user with an instruction
// they cannot follow. Walks every code the backend can send (plus the layer
// fallbacks) with the non-retryable verdict the classifier stamps for it.
describe('error copy never names a hidden Retry', () => {
  const thread = en.assistant.thread
  const RETRY_WORDS = /\bretry\b|\btry again\b/i

  // Verdicts the classifier stamps as deterministic (agent/error_surface.py
  // `_NON_RETRYABLE_REASONS`); everything else arrives retryable.
  const NON_RETRYABLE = new Set([
    'auth',
    'auth_permanent',
    'billing',
    'content_policy_blocked',
    'provider_policy_blocked',
    'model_not_found',
    'format_error',
    'ssl_cert_verification',
    'context_overflow',
    'interpreter_shutdown',
    'upstream_blocked'
  ])

  const surfaces: ErrorSurface[] = [
    ...ERROR_CODE_KEYS.map(code => ({ code, layer: 'provider' as const, retryable: !NON_RETRYABLE.has(code) })),
    { code: 'auth', layer: 'auth', retryable: false },
    { code: 'auth_permanent', layer: 'auth', retryable: false },
    { code: 'ssl_cert_verification', layer: 'endpoint', retryable: false },
    { code: 'interpreter_shutdown', layer: 'gateway', retryable: false },
    { code: 'interpreter_shutdown', layer: 'runtime', retryable: false },
    { code: 'unknown', layer: 'endpoint', retryable: false }
  ]

  it.each(surfaces.map(surface => [surface.code, surface.layer, surface] as const))(
    '%s on %s',
    (_code, _layer, surface) => {
      const { primary, secondary } = errorCardActions(surface)
      const { body } = errorCardText(thread, surface)
      const offersRetry = [primary, secondary].some(action => action === 'retry' || action === 'retry_at_reset')

      if (!offersRetry) {
        expect(body).not.toMatch(RETRY_WORDS)
      }
    }
  )

  it('a credential rejection keeps Retry, so its body may still say retry', () => {
    const surface: ErrorSurface = {
      authKind: 'api_key',
      code: 'auth',
      layer: 'auth',
      provider: 'openai',
      retryable: false
    }

    expect(errorCardOffers(surface, 'retry')).toBe(true)
  })

  it('a WAF block names the firewall and the User-Agent fix, not the key and not a retry', () => {
    const surface = parseErrorSurface({
      code: 'upstream_blocked',
      layer: 'provider',
      provider: 'custom',
      retryable: false
    })!

    const { body, title } = errorCardText(thread, surface)
    expect(title).toBe('custom blocked this request')
    expect(body).toMatch(/firewall/i)
    expect(body).toMatch(/User-Agent/)
    expect(body).not.toMatch(/\bkey\b/i)
    expect(errorCardActions(surface).primary).toBe('switch_provider')
  })
})

describe('cron session read-only (#141348)', () => {
  it('renders its own copy and offers a new chat instead of Retry', () => {
    const surface = parseErrorSurface({ layer: 'gateway', code: 'cron_session_read_only', retryable: false })

    expect(errorCardText(en.assistant.thread, surface)).toEqual(en.assistant.thread.errorCodes.cron_session_read_only)
    expect(errorCardActions(surface)).toEqual({ primary: 'start_new_session' })
  })
})

describe('managed local model server down', () => {
  it('names the local model server, not a custom one, and offers another model, never a key update', () => {
    const surface = parseErrorSurface({ layer: 'endpoint', code: 'local_runtime_unavailable', retryable: false })
    const { body, title } = errorCardText(en.assistant.thread, surface)

    expect(`${title} ${body}`).toContain('local model server')
    // The card is the same in Desktop and the Webapp, which has no Local models pane.
    expect(body).not.toMatch(/custom|Settings|Local models/)
    expect(errorCardActions(surface)).toEqual({ primary: 'switch_provider' })
  })

  it('offers Retry first while the server is still starting', () => {
    const surface = parseErrorSurface({ layer: 'endpoint', code: 'local_runtime_unavailable', retryable: true })

    expect(errorCardActions(surface)).toEqual({ primary: 'retry', secondary: 'switch_provider' })
  })

  it('says Retry only while the server is starting, in every locale', () => {
    const card = (retryable: boolean, thread = en.assistant.thread) =>
      errorCardText(thread, parseErrorSurface({ layer: 'endpoint', code: 'local_runtime_unavailable', retryable }))

    expect(card(true).body).toMatch(/retry/i)
    expect(card(false).body).not.toMatch(/retry/i)
    expect(card(false).body).toContain('hermes model')

    for (const copy of Object.values(TRANSLATIONS)) {
      expect(card(false, copy.assistant.thread).body).not.toBe(card(true, copy.assistant.thread).body)
      expect(card(false, copy.assistant.thread).body).toContain('hermes model')
    }
  })
})

describe('limit reset (#98852)', () => {
  it('parses resets_at and renders its local "HH:mm"', () => {
    const now = Date.UTC(2026, 0, 1, 12, 0, 0)
    const resetsAt = now / 1000 + 3600 + 5 * 60

    const surface = parseErrorSurface({ layer: 'provider', code: 'rate_limit', retryable: true, resets_at: resetsAt })

    expect(surface?.resetsAt).toBe(resetsAt)

    const at = new Date(resetsAt * 1000)
    const clock = `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`

    expect(formatResetClock(surface!.resetsAt!)).toBe(clock)
    expect(formatErrorDiagnostics({ errorText: 'x', surface })).toContain('resets_at: ')
  })

  it('schedules nothing once the reset has passed or when the backend sent none', () => {
    const now = Date.now()

    expect(scheduledRetryDelayMs(now / 1000 - 60, now)).toBeNull()
    expect(scheduledRetryDelayMs(undefined, now)).toBeNull()
    expect(parseErrorSurface({ layer: 'provider', code: 'rate_limit', retryable: true })?.resetsAt).toBeUndefined()
    expect(
      parseErrorSurface({ layer: 'provider', code: 'rate_limit', retryable: true, resets_at: 'soon' })?.resetsAt
    ).toBeUndefined()
  })
})

describe('out of credits', () => {
  it('offers Billing, then another provider', () => {
    const surface = parseErrorSurface({ code: 'billing', layer: 'billing', provider: 'example', retryable: false })

    expect(errorCardActions(surface)).toEqual({ primary: 'open_billing', secondary: 'switch_provider' })
  })
})

describe('error card actions: one main action, at most one second option', () => {
  const at = (surface: Record<string, unknown>) => errorCardActions(parseErrorSurface(surface))
  const later = Math.floor(Date.now() / 1000) + 600

  it('offers another provider only when the provider side failed', () => {
    expect(at({ code: 'mystery', layer: 'provider', retryable: false }).primary).toBe('switch_provider')
    expect(at({ code: 'mystery', layer: 'gateway', retryable: false }).primary).toBeNull()
    expect(at({ code: 'mystery', layer: 'disk', retryable: false }).primary).toBeNull()
    expect(at({ code: 'mystery', layer: 'gateway', retryable: true }).primary).toBe('retry')
  })

  it('keeps an immediate Retry beside the scheduled one for a rate limit with a known reset', () => {
    expect(at({ code: 'rate_limit', layer: 'provider', resets_at: later, retryable: true })).toEqual({
      primary: 'retry_at_reset',
      secondary: 'retry'
    })
  })

  it('a stuck tool loop retries or starts over', () => {
    expect(at({ code: 'loop_error', layer: 'runtime', retryable: true })).toEqual({
      primary: 'retry',
      secondary: 'start_new_session'
    })
  })

  it('points a privacy block at the provider page only when one is known', () => {
    expect(
      at({ code: 'provider_policy_blocked', layer: 'provider', provider: 'openrouter', retryable: false })
    ).toEqual({ primary: 'open_provider_settings', secondary: 'choose_model' })
    expect(
      at({ code: 'provider_policy_blocked', layer: 'provider', provider: 'OpenRouter', retryable: false })
    ).toEqual({ primary: 'open_provider_settings', secondary: 'choose_model' })
    expect(at({ code: 'provider_policy_blocked', layer: 'provider', provider: 'acme', retryable: false })).toEqual({
      primary: 'choose_model'
    })
  })

  it('names the severity from what the user can still do', () => {
    const severity = (surface: Record<string, unknown>) => errorCardSeverity(parseErrorSurface(surface))

    expect(severity({ code: 'rate_limit', layer: 'provider', retryable: true })).toBe('degraded')
    expect(severity({ code: 'truncated', layer: 'provider', retryable: true })).toBe('degraded')
    expect(severity({ auth_kind: 'api_key', code: 'auth', layer: 'auth', retryable: false })).toBe('blocking')
    expect(severity({ code: 'agent_init_failed', layer: 'runtime', retryable: true })).toBe('blocking')
    expect(severity({ code: 'SESSION_OWNER_UNCONFIRMED', layer: 'gateway', retryable: false })).toBe('blocking')
  })
})
