import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import type * as ReactRouterDom from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ToolsetConfig } from '@/types/hermes'

// Collect the component graph before the behavioral test deadline starts.
import { ToolsetConfigPanel } from './toolset-config-panel'

// EnvVarField navigates to Settings → Keys via useNavigate, so every render
// needs a router context. The navigate spy asserts the deep-link target.
const navigateSpy = vi.fn()

vi.mock('react-router', async importOriginal => ({
  ...(await importOriginal<typeof ReactRouterDom>()),
  useNavigate: () => navigateSpy
}))

// The inline VoiceProviderFields reads the shared config record through React
// Query, so the panel needs a QueryClientProvider (fresh per render — cached
// config from one test must not leak into the next).
const render = (ui: ReactElement) =>
  rtlRender(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        {ui}
      </QueryClientProvider>
    </MemoryRouter>
  )

const getToolsetConfig = vi.fn()
const getToolsetModels = vi.fn()
const selectToolsetModel = vi.fn()
const selectToolsetProvider = vi.fn()
const setEnvVar = vi.fn()
const deleteEnvVar = vi.fn()
const revealEnvVar = vi.fn()
const runToolsetPostSetup = vi.fn()
const getActionStatus = vi.fn()
const startOAuthLogin = vi.fn()
const pollOAuthSession = vi.fn()
const getHermesConfigRecord = vi.fn()
const getHermesConfigSchema = vi.fn()
const saveHermesConfig = vi.fn()
const saveHermesConfigRecord = vi.fn()

vi.mock('@/hermes', () => ({
  // useHermesConfigRecord (via VoiceProviderFields) reads these from the barrel.
  peekConfigReadOrigin: () => undefined,
  retainConfigReadOrigin: (next: unknown) => next,
  getToolsetConfig: (name: string) => getToolsetConfig(name),
  getToolsetModels: (name: string, provider?: string) => getToolsetModels(name, provider),
  selectToolsetModel: (name: string, model: string, provider?: string) => selectToolsetModel(name, model, provider),
  selectToolsetProvider: (name: string, provider: string, capability?: string) =>
    capability === undefined
      ? selectToolsetProvider(name, provider)
      : selectToolsetProvider(name, provider, capability),
  setEnvVar: (key: string, value: string) => setEnvVar(key, value),
  deleteEnvVar: (key: string) => deleteEnvVar(key),
  revealEnvVar: (key: string) => revealEnvVar(key),
  runToolsetPostSetup: (name: string, key: string) => runToolsetPostSetup(name, key),
  getActionStatus: (name: string, lines?: number) => getActionStatus(name, lines),
  startOAuthLogin: (providerId: string) => startOAuthLogin(providerId),
  pollOAuthSession: (providerId: string, sessionId: string) => pollOAuthSession(providerId, sessionId),
  getHermesConfigRecord: () => getHermesConfigRecord(),
  getHermesConfigSchema: () => getHermesConfigSchema(),
  saveHermesConfig: (config: unknown) => saveHermesConfig(config),
  saveHermesConfigRecord: (config: unknown, profile?: unknown) => saveHermesConfigRecord(config, profile),
  // use-config-record keys its query cache by scope via profileScopeKey; a
  // scoped panel reaches it, so the full-replacement mock must provide it.
  profileScopeKey: (scope?: { profile?: string; connectionId?: string } | string) =>
    typeof scope === 'object' && scope
      ? `${scope.connectionId ?? ''}::${scope.profile ?? 'default'}`
      : (scope ?? 'default'),
  // @/store/profile (pulled in transitively via use-config-record's
  // normalizeProfileKey import) calls this at module-init; the full-replacement
  // mock must provide it or the module graph throws on load.
  setApiRequestProfile: () => undefined,
  getApiRequestProfile: () => null
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

vi.mock('@/store/activity', () => ({
  upsertDesktopActionTask: vi.fn()
}))

function config(overrides: Partial<ToolsetConfig> = {}): ToolsetConfig {
  return {
    name: 'tts',
    has_category: true,
    active_provider: null,
    providers: [
      {
        name: 'Piper',
        badge: 'free',
        tag: 'No API key needed',
        env_vars: [],
        post_setup: null,
        requires_nous_auth: false,
        is_active: false
      },
      {
        name: 'OpenAI TTS',
        badge: 'paid',
        tag: 'High quality voices',
        env_vars: [
          { key: 'VOICE_TOOLS_OPENAI_KEY', prompt: 'OpenAI API key', url: 'https://x', default: null, is_set: false }
        ],
        post_setup: null,
        requires_nous_auth: false,
        is_active: false
      }
    ],
    ...overrides
  }
}

beforeEach(() => {
  // Radix menus/selects call these on open; jsdom implements neither, so the
  // dropdown never opens without the stubs (mirrors model-settings.test.tsx).
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
  // cmdk (used by the free-input voice/model combobox) needs ResizeObserver,
  // which jsdom doesn't ship (mirrors searchable-select.test.tsx).
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  )

  getToolsetConfig.mockResolvedValue(config())
  getToolsetModels.mockResolvedValue({
    name: 'tts',
    has_models: false,
    models: [],
    current: null,
    default: null
  })
  selectToolsetModel.mockResolvedValue({ ok: true, name: 'image_gen', model: 'gpt-image-2-low' })
  selectToolsetProvider.mockResolvedValue({ ok: true, name: 'tts', provider: 'OpenAI TTS' })
  setEnvVar.mockResolvedValue({ ok: true })
  deleteEnvVar.mockResolvedValue({ ok: true })
  getHermesConfigRecord.mockResolvedValue({
    tts: {
      provider: 'piper',
      piper: { voice: 'en_US-lessac-medium' },
      openai: { model: 'gpt-4o-mini-tts', voice: 'alloy' }
    }
  })
  getHermesConfigSchema.mockResolvedValue({ fields: {}, category_order: [] })
  saveHermesConfig.mockResolvedValue({ ok: true })
  saveHermesConfigRecord.mockResolvedValue({ ok: true })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ToolsetConfigPanel', () => {
  it('renders inline voice/model fields for a TTS provider row carrying tts_provider', async () => {
    // The Capabilities gap: provider rows only showed API keys — voice/model
    // settings lived exclusively in Settings → Voice. Rows now carry the
    // backend's tts_provider key and the panel renders the same config
    // fields inline (here: OpenAI TTS Model + OpenAI Voice).
    getToolsetConfig.mockResolvedValue(
      config({
        active_provider: 'OpenAI TTS',
        providers: [
          {
            name: 'OpenAI TTS',
            badge: 'paid',
            tag: 'High quality voices',
            env_vars: [
              { key: 'VOICE_TOOLS_OPENAI_KEY', prompt: 'OpenAI API key', url: 'https://x', default: null, is_set: true }
            ],
            post_setup: null,
            requires_nous_auth: false,
            is_active: true,
            tts_provider: 'openai'
          }
        ]
      })
    )

    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

    expect(await screen.findByText('OpenAI TTS Model')).toBeTruthy()
    expect(screen.getByText('OpenAI Voice')).toBeTruthy()
    // Voice/model names are free-input comboboxes seeded with the current
    // config value — a custom voice ID must be typeable, not gated by a
    // closed Select.
    const voiceInput = screen.getByDisplayValue('alloy')
    fireEvent.change(voiceInput, { target: { value: 'marin' } })
    await waitFor(() => expect(saveHermesConfigRecord).toHaveBeenCalled(), { timeout: 3000 })

    const saved = saveHermesConfigRecord.mock.calls.at(-1)?.[0] as Record<
      string,
      Record<string, Record<string, string>>
    >

    expect(saved.tts.openai.voice).toBe('marin')
    // Unscoped panel (no Capabilities override) → profile rides as undefined,
    // preserving the active-profile default. A scoped panel forwards its scope.
    expect(saveHermesConfigRecord.mock.calls.at(-1)?.[1]).toBeUndefined()
  })

  it('autosaves the inline voice fields into the profile the panel is scoped to', async () => {
    // The bug: a scoped Capabilities panel (scope selector → profile B) rendered
    // these fields unscoped, so editing B's voice PUT the ACTIVE profile's config.
    getToolsetConfig.mockResolvedValue(
      config({
        active_provider: 'OpenAI TTS',
        providers: [
          {
            name: 'OpenAI TTS',
            badge: 'paid',
            tag: 'High quality voices',
            env_vars: [],
            post_setup: null,
            requires_nous_auth: false,
            is_active: true,
            tts_provider: 'openai'
          }
        ]
      })
    )

    const scope = { profile: 'scout', connectionId: 'gw-2' }
    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} profile={scope} toolset="tts" />)

    fireEvent.change(await screen.findByDisplayValue('alloy'), { target: { value: 'marin' } })
    await waitFor(() => expect(saveHermesConfigRecord).toHaveBeenCalled(), { timeout: 3000 })

    const [saved, forwarded] = saveHermesConfigRecord.mock.calls.at(-1) as [
      Record<string, Record<string, Record<string, string>>>,
      unknown
    ]

    expect(saved.tts.openai.voice).toBe('marin')
    expect(forwarded).toEqual(scope)
  })

  it('expands a provider on row click and activates it via the explicit button', async () => {
    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

    // Row click only expands — browsing details must not rewrite config.
    const openaiTts = await screen.findByRole('button', { name: /OpenAI TTS/ })
    fireEvent.click(openaiTts)
    expect(selectToolsetProvider).not.toHaveBeenCalled()

    // The explicit activation button is what persists the backend choice.
    fireEvent.click(await screen.findByRole('button', { name: /Use this backend/ }))

    await waitFor(() => expect(selectToolsetProvider).toHaveBeenCalledWith('tts', 'OpenAI TTS'))
  })

  it('serializes provider selection while a previous choice is pending', async () => {
    let resolveSelection: (value: { name: string; ok: boolean; provider: string }) => void = () => undefined
    selectToolsetProvider.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveSelection = resolve
        })
    )

    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

    // Piper auto-expands (first configured provider); activate it explicitly.
    await screen.findByRole('button', { name: /Piper/ })
    const useBackend = await screen.findByRole('button', { name: /Use this backend/ })
    fireEvent.click(useBackend)

    await waitFor(() => expect(selectToolsetProvider).toHaveBeenCalledWith('tts', 'Piper'))
    // While the first selection is pending, the activation CTA is disabled —
    // a second click must not fire another PUT.
    expect(useBackend.hasAttribute('disabled')).toBe(true)
    fireEvent.click(useBackend)
    expect(selectToolsetProvider).toHaveBeenCalledTimes(1)

    resolveSelection({ name: 'tts', ok: true, provider: 'Piper' })
    // Piper is now the active backend — its expanded panel shows the active
    // hint instead of the activation button.
    await waitFor(() => expect(screen.getByText('This is your active backend')).toBeTruthy())
  })

  it('shows a backend model catalog for image_gen and persists a pick', async () => {
    getToolsetConfig.mockResolvedValue(
      config({
        name: 'image_gen',
        active_provider: 'OpenAI',
        providers: [
          {
            name: 'OpenAI',
            badge: 'paid',
            tag: 'GPT Image text-to-image & editing',
            env_vars: [],
            post_setup: null,
            requires_nous_auth: false,
            is_active: true
          }
        ]
      })
    )
    getToolsetModels.mockResolvedValue({
      name: 'image_gen',
      has_models: true,
      provider: 'OpenAI',
      plugin: 'openai',
      models: [
        { id: 'gpt-image-2-low', display: 'GPT Image 2 (Low)', speed: 'fast', strengths: 'cheap drafts', price: '$0.005' },
        { id: 'gpt-image-2-high', display: 'GPT Image 2 (High)', speed: 'slow', strengths: 'quality', price: '$0.05' }
      ],
      current: 'gpt-image-2-low',
      default: 'gpt-image-2-low'
    })

    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="image_gen" />)

    // Both catalog rows render with their picker metadata.
    expect(await screen.findByText('GPT Image 2 (Low)')).toBeTruthy()
    expect(screen.getByText('GPT Image 2 (High)')).toBeTruthy()
    expect(getToolsetModels).toHaveBeenCalledWith('image_gen', 'OpenAI')

    // Picking a different model persists via the model endpoint.
    fireEvent.click(screen.getByRole('button', { name: /GPT Image 2 \(High\)/ }))
    await waitFor(() => expect(selectToolsetModel).toHaveBeenCalledWith('image_gen', 'gpt-image-2-high', 'OpenAI'))
  })

  it('saves an API key for a provider env var', async () => {
    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

    // Select the keyed provider so its env vars render.
    const openaiTts = await screen.findByRole('button', { name: /OpenAI TTS/ })
    fireEvent.click(openaiTts)

    // Open the credential actions menu (Radix opens on pointerdown), then "Set".
    const trigger = await screen.findByRole('button', { name: /^Actions$/ })
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Set' }))

    const input = await screen.findByPlaceholderText('OpenAI API key')
    fireEvent.change(input, { target: { value: 'sk-test-123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(setEnvVar).toHaveBeenCalledWith('VOICE_TOOLS_OPENAI_KEY', 'sk-test-123'))
  })

  it('expands the active provider on load, not just the first configured one', async () => {
    // OpenAI TTS is the active provider per config, even though the keyless
    // Piper provider sorts first and is also "configured". The panel must
    // honor is_active and expand OpenAI TTS (so its API-key field renders)
    // rather than defaulting to the first keyless provider. Regression test
    // for the GUI showing the wrong provider selected after relaunch.
    getToolsetConfig.mockResolvedValue(
      config({
        active_provider: 'OpenAI TTS',
        providers: [
          {
            name: 'Piper',
            badge: 'free',
            tag: 'No API key needed',
            env_vars: [],
            post_setup: null,
            requires_nous_auth: false,
            is_active: false
          },
          {
            name: 'OpenAI TTS',
            badge: 'paid',
            tag: 'High quality voices',
            env_vars: [
              {
                key: 'VOICE_TOOLS_OPENAI_KEY',
                prompt: 'OpenAI API key',
                url: 'https://x',
                default: null,
                is_set: true
              }
            ],
            post_setup: null,
            requires_nous_auth: false,
            is_active: true
          }
        ]
      })
    )

    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

    // The active provider's env-var field only renders when it's the expanded
    // one — so finding it proves OpenAI TTS (not Piper) was auto-expanded.
    expect(await screen.findByText('VOICE_TOOLS_OPENAI_KEY')).toBeTruthy()
    // No provider selection was triggered — this is purely reflecting state.
    expect(selectToolsetProvider).not.toHaveBeenCalled()
  })

  it('runs a provider post-setup install hook and tails its log', async () => {
    // A browser-style toolset whose active provider declares a post_setup hook.
    getToolsetConfig.mockResolvedValue(
      config({
        name: 'browser',
        active_provider: 'Lightpanda',
        providers: [
          {
            name: 'Lightpanda',
            badge: 'local',
            tag: 'Zig headless browser spawned by A2Assistant, text-only (no screenshots)',
            env_vars: [],
            post_setup: 'lightpanda',
            requires_nous_auth: false,
            is_active: true
          }
        ]
      })
    )
    runToolsetPostSetup.mockResolvedValue({ ok: true, pid: 4321, name: 'tools-post-setup', key: 'lightpanda' })
    // First poll: still running; second poll: finished cleanly.
    getActionStatus
      .mockResolvedValueOnce({
        exit_code: null,
        lines: ['Installing Lightpanda...'],
        name: 'tools-post-setup',
        pid: 4321,
        running: true
      })
      .mockResolvedValue({
        exit_code: 0,
        lines: ['Installing Lightpanda...', "Post-setup 'lightpanda' complete"],
        name: 'tools-post-setup',
        pid: 4321,
        running: false
      })

    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

    fireEvent.click(await screen.findByRole('button', { name: /Run setup/ }))

    await waitFor(() => expect(runToolsetPostSetup).toHaveBeenCalledWith('browser', 'lightpanda'))
    // The install log is tailed inline. The first poll fires after a 1200ms
    // delay (mirrors command-center's poll cadence), so allow >1200ms here.
    await waitFor(() => expect(getActionStatus).toHaveBeenCalledWith('tools-post-setup', 300), {
      timeout: 4000
    })
  })

  it('surfaces a non-zero exit code from the setup process', async () => {
    getToolsetConfig.mockResolvedValue(
      config({
        name: 'browser',
        active_provider: 'Lightpanda',
        providers: [
          {
            name: 'Lightpanda',
            badge: 'local',
            tag: 'Zig headless browser spawned by A2Assistant, text-only (no screenshots)',
            env_vars: [],
            post_setup: 'lightpanda',
            requires_nous_auth: false,
            is_active: true
          }
        ]
      })
    )
    runToolsetPostSetup.mockResolvedValue({ ok: true, pid: 4321, name: 'tools-post-setup', key: 'lightpanda' })
    // Action finished but failed (non-zero exit).
    getActionStatus.mockResolvedValue({
      exit_code: 1,
      lines: ['Installing...', 'npm ERR! install failed'],
      name: 'tools-post-setup',
      pid: 4321,
      running: false
    })

    render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

    fireEvent.click(await screen.findByRole('button', { name: /Run setup/ }))

    // The failing install log is still tailed and shown; exit_code:1 routes to
    // the error notify branch (asserted via the poll completing on a non-zero
    // status without throwing).
    await waitFor(() => expect(getActionStatus).toHaveBeenCalledWith('tools-post-setup', 300), {
      timeout: 4000
    })
    await waitFor(() => expect(screen.getByText(/npm ERR! install failed/)).toBeTruthy(), {
      timeout: 4000
    })
  })

  describe('readiness pills', () => {
    it('renders the server status instead of assuming keyless rows are Ready', async () => {
      // The false-Ready bug: a logged-out Nous Subscription row and a
      // never-installed local TTS both have zero env vars — the old client
      // heuristic pilled every such row "Ready". The server now sends an
      // honest per-provider status; the pill must follow it.
      getToolsetConfig.mockResolvedValue(
        config({
          providers: [
            {
              name: 'Piper',
              badge: 'free',
              tag: 'No API key needed',
              env_vars: [],
              post_setup: null,
              requires_nous_auth: false,
              is_active: true,
              status: 'ready'
            },
            {
              name: 'Nous Subscription',
              badge: 'subscription',
              tag: 'Managed OpenAI TTS',
              env_vars: [],
              post_setup: null,
              requires_nous_auth: true,
              is_active: false,
              status: 'needs_auth'
            },
            {
              name: 'KittenTTS',
              badge: 'local · free',
              tag: 'Lightweight local ONNX TTS',
              env_vars: [],
              post_setup: 'kittentts',
              requires_nous_auth: false,
              is_active: false,
              status: 'needs_setup'
            }
          ]
        })
      )

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

      await screen.findByText('Piper')
      // Piper is the active backend — its row pill reads Active (which
      // subsumes Ready); the other rows keep their warn pills.
      expect(screen.getAllByText('Active')).toHaveLength(1)
      expect(screen.queryByText('Ready')).toBeNull()
      expect(screen.getByText('Needs sign-in')).toBeTruthy()
      expect(screen.getByText('Setup required')).toBeTruthy()
    })

    it('falls back to the env-var heuristic when the backend sends no status', async () => {
      // Older backend (no `status` field): keyless rows keep the legacy
      // Ready pill, keyed-and-unset rows keep no pill. Narrow compat path —
      // desktop and backend update on separate clocks.
      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

      await screen.findByText('Piper')
      // Default config(): keyless Piper (ready) + unset OpenAI TTS (not).
      expect(screen.getAllByText('Ready')).toHaveLength(1)
      expect(screen.queryByText('Needs sign-in')).toBeNull()
      expect(screen.queryByText('Setup required')).toBeNull()
    })

    it('flips a needs_keys provider to Ready locally after its key is saved', async () => {
      getToolsetConfig.mockResolvedValue(
        config({
          active_provider: null,
          providers: [
            {
              name: 'OpenAI TTS',
              badge: 'paid',
              tag: 'High quality voices',
              env_vars: [
                {
                  key: 'VOICE_TOOLS_OPENAI_KEY',
                  prompt: 'OpenAI API key',
                  url: 'https://x',
                  default: null,
                  is_set: false
                }
              ],
              post_setup: null,
              requires_nous_auth: false,
              is_active: false,
              status: 'needs_keys'
            }
          ]
        })
      )

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

      expect(await screen.findByText('VOICE_TOOLS_OPENAI_KEY')).toBeTruthy()
      expect(screen.queryByText('Ready')).toBeNull()

      // Save a key: the pill must go Ready from the local envState patch even
      // though the (now stale) server status still says needs_keys.
      const trigger = await screen.findByRole('button', { name: /^Actions$/ })
      fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' })
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Set' }))
      fireEvent.change(await screen.findByPlaceholderText('OpenAI API key'), { target: { value: 'sk-live' } })
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(screen.getByText('Ready')).toBeTruthy())
    })
  })

  describe('post-setup installed state', () => {
    it('renders Installed + Re-run setup instead of the primary CTA when the server says ready', async () => {
      // Regression (Windows 11 Capabilities journey): "Run setup" rendered
      // unconditionally, so an already-installed backend still showed the
      // primary install CTA and clicking it re-ran the whole install.
      // status === 'ready' must flip to a resting Installed state.
      getToolsetConfig.mockResolvedValue(
        config({
          name: 'browser',
          active_provider: 'Lightpanda',
          providers: [
            {
              name: 'Lightpanda',
              badge: 'free',
              tag: 'Zig headless browser spawned by A2Assistant, text-only (no screenshots)',
              env_vars: [],
              post_setup: 'lightpanda',
              requires_nous_auth: false,
              is_active: true,
              status: 'ready'
            }
          ]
        })
      )

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

      await screen.findByText('Lightpanda')
      expect(await screen.findByText('Installed')).toBeTruthy()
      expect(await screen.findByRole('button', { name: /Re-run setup/ })).toBeTruthy()
      expect(screen.queryByRole('button', { name: /^Run setup$/ })).toBeNull()
    })

    it('still runs the hook from the Re-run setup affordance', async () => {
      getToolsetConfig.mockResolvedValue(
        config({
          name: 'browser',
          active_provider: 'Lightpanda',
          providers: [
            {
              name: 'Lightpanda',
              badge: 'free',
              tag: 'Zig headless browser spawned by A2Assistant, text-only (no screenshots)',
              env_vars: [],
              post_setup: 'lightpanda',
              requires_nous_auth: false,
              is_active: true,
              status: 'ready'
            }
          ]
        })
      )
      runToolsetPostSetup.mockResolvedValue({ ok: true, pid: 4321, name: 'tools-post-setup', key: 'lightpanda' })
      getActionStatus.mockResolvedValue({
        exit_code: 0,
        lines: ['lightpanda already installed, nothing to do'],
        name: 'tools-post-setup',
        pid: 4321,
        running: false
      })

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

      fireEvent.click(await screen.findByRole('button', { name: /Re-run setup/ }))

      await waitFor(() => expect(runToolsetPostSetup).toHaveBeenCalledWith('browser', 'lightpanda'))
    })
  })

  describe('managed Nous provider activation', () => {
    const nousBrowserConfig = () =>
      config({
        name: 'browser',
        active_provider: null,
        providers: [
          {
            name: 'Nous Subscription (Browser Use cloud)',
            badge: 'subscription',
            tag: 'Managed Browser Use billed to your subscription',
            env_vars: [],
            post_setup: null,
            requires_nous_auth: true,
            is_active: false,
            status: 'needs_auth'
          }
        ]
      })

    it('surfaces a sign-in notice when the PUT reports needs_nous_auth', async () => {
      // Regression (Windows 11 Capabilities journey): the GUI wrote
      // browser.cloud_provider but skipped the Portal entitlement handshake,
      // so the managed row silently never activated. The endpoint now
      // reports needs_nous_auth and the panel must surface a sign-in action
      // instead of the misleading "provider selected" success toast.
      const { notify } = await import('@/store/notifications')

      getToolsetConfig.mockResolvedValue(nousBrowserConfig())
      selectToolsetProvider.mockResolvedValue({
        ok: true,
        name: 'browser',
        provider: 'Nous Subscription (Browser Use cloud)',
        needs_nous_auth: true,
        feature: 'browser'
      })

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

      // The single Nous row auto-expands; activate via the explicit button.
      await screen.findByRole('button', { name: /Nous Subscription/ })
      fireEvent.click(await screen.findByRole('button', { name: /Use this backend/ }))

      await waitFor(() =>
        expect(selectToolsetProvider).toHaveBeenCalledWith('browser', 'Nous Subscription (Browser Use cloud)')
      )
      await waitFor(() =>
        expect(notify).toHaveBeenCalledWith(
          expect.objectContaining({
            kind: 'warning',
            action: expect.objectContaining({ label: expect.any(String) })
          })
        )
      )
      // No success toast — the row is not active yet.
      expect(notify).not.toHaveBeenCalledWith(expect.objectContaining({ kind: 'success' }))
    })

    it('drives the existing Nous OAuth device-code flow from the sign-in action and refetches', async () => {
      const { notify } = await import('@/store/notifications')

      getToolsetConfig.mockResolvedValue(nousBrowserConfig())
      selectToolsetProvider.mockResolvedValue({
        ok: true,
        name: 'browser',
        provider: 'Nous Subscription (Browser Use cloud)',
        needs_nous_auth: true,
        feature: 'browser'
      })
      startOAuthLogin.mockResolvedValue({
        flow: 'device_code',
        session_id: 'sess-1',
        user_code: 'NOUS-1234',
        verification_url: 'https://portal.nousresearch.com/device?user_code=NOUS-1234',
        poll_interval: 5,
        expires_in: 600
      })
      pollOAuthSession.mockResolvedValue({ session_id: 'sess-1', status: 'approved' })
      const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)

      try {
        render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

        await screen.findByRole('button', { name: /Nous Subscription/ })
        fireEvent.click(await screen.findByRole('button', { name: /Use this backend/ }))

        // Grab the sign-in action off the warning notification and invoke it —
        // this is the affordance the toast renders as a button.
        await waitFor(() => expect(notify).toHaveBeenCalledWith(expect.objectContaining({ kind: 'warning' })))

        const warning = vi
          .mocked(notify)
          .mock.calls.map(call => call[0])
          .find(input => input.kind === 'warning')

        expect(warning?.action).toBeTruthy()
        getToolsetConfig.mockClear()
        warning!.action!.onClick()

        await waitFor(() => expect(startOAuthLogin).toHaveBeenCalledWith('nous'))
        expect(openSpy).toHaveBeenCalledWith(
          'https://portal.nousresearch.com/device?user_code=NOUS-1234',
          '_blank',
          'noopener,noreferrer'
        )
        // Approved poll → the panel refetches the config so status flips.
        await waitFor(() => expect(pollOAuthSession).toHaveBeenCalledWith('nous', 'sess-1'), { timeout: 8000 })
        await waitFor(() => expect(getToolsetConfig).toHaveBeenCalled(), { timeout: 8000 })
      } finally {
        openSpy.mockRestore()
      }
    }, 20000)

    it('shows the plain success toast when the managed row is already entitled', async () => {
      const { notify } = await import('@/store/notifications')

      getToolsetConfig.mockResolvedValue(nousBrowserConfig())
      selectToolsetProvider.mockResolvedValue({
        ok: true,
        name: 'browser',
        provider: 'Nous Subscription (Browser Use cloud)'
      })

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="browser" />)

      await screen.findByRole('button', { name: /Nous Subscription/ })
      fireEvent.click(await screen.findByRole('button', { name: /Use this backend/ }))

      await waitFor(() => expect(notify).toHaveBeenCalledWith(expect.objectContaining({ kind: 'success' })))
      expect(startOAuthLogin).not.toHaveBeenCalled()
    })
  })

  describe('API key deep link', () => {
    it('offers "Manage in API Keys" on a set key and navigates to Settings → Keys', async () => {
      getToolsetConfig.mockResolvedValue(
        config({
          active_provider: 'OpenAI TTS',
          providers: [
            {
              name: 'OpenAI TTS',
              badge: 'paid',
              tag: 'High quality voices',
              env_vars: [
                {
                  key: 'VOICE_TOOLS_OPENAI_KEY',
                  prompt: 'OpenAI API key',
                  url: 'https://x',
                  default: null,
                  is_set: true
                }
              ],
              post_setup: null,
              requires_nous_auth: false,
              is_active: true,
              status: 'ready'
            }
          ]
        })
      )

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

      const trigger = await screen.findByRole('button', { name: /^Actions$/ })
      fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' })
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Manage in API Keys' }))

      await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/settings?tab=keys&key=VOICE_TOOLS_OPENAI_KEY'))
    })

    it('hides "Manage in API Keys" while the key is unset', async () => {
      // Default config(): OpenAI TTS key is not set. An unset key is managed
      // right here via Set — no point bouncing the user to another page.
      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="tts" />)

      // Expand the keyed provider so its env row renders. Wait for the
      // selection to commit: on a freshly loaded panel this races the default
      // provider initializer, and user intent must win that race.
      const openaiTts = await screen.findByRole('button', { name: /OpenAI TTS/ })
      fireEvent.click(openaiTts)
      await waitFor(() => expect(openaiTts.getAttribute('aria-expanded')).toBe('true'))

      const trigger = await screen.findByRole('button', { name: /^Actions$/ })
      fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' })

      await screen.findByRole('menuitem', { name: 'Set' })
      expect(screen.queryByRole('menuitem', { name: 'Manage in API Keys' })).toBeNull()
    })
  })

  describe('web capability split', () => {
    function webConfig(overrides: Partial<ToolsetConfig> = {}): ToolsetConfig {
      return {
        name: 'web',
        has_category: true,
        active_provider: 'DuckDuckGo (ddgs)',
        active_search_backend: 'ddgs',
        active_extract_backend: 'example',
        providers: [
          {
            name: 'DuckDuckGo (ddgs)',
            badge: 'free · no key · search only',
            tag: 'Search via the ddgs Python package',
            env_vars: [],
            post_setup: null,
            requires_nous_auth: false,
            is_active: true,
            status: 'ready',
            web_backend: 'ddgs',
            capabilities: ['search']
          },
          {
            name: 'Example',
            badge: 'plugin',
            tag: 'Full search + extract',
            env_vars: [],
            post_setup: null,
            requires_nous_auth: false,
            is_active: true,
            status: 'ready',
            web_backend: 'example',
            capabilities: ['search', 'extract']
          }
        ],
        ...overrides
      }
    }

    it('hides "Use for Extract" on a search-only provider and wires capability selection', async () => {
      // The panel refetches after a capability pick: second load is the server's truth.
      getToolsetConfig
        .mockResolvedValueOnce(webConfig())
        .mockResolvedValue(webConfig({ active_search_backend: 'example' }))
      selectToolsetProvider.mockResolvedValue({ ok: true, name: 'web', provider: 'Example', capability: 'search' })

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="web" />)

      await screen.findByText('Search: ddgs')
      expect(await screen.findByRole('button', { name: 'Use for Search' })).toBeTruthy()
      expect(screen.queryByRole('button', { name: 'Use for Extract' })).toBeNull()

      fireEvent.click(screen.getByRole('button', { name: /^Example/ }))
      const useForSearch = await screen.findByRole('button', { name: 'Use for Search' })
      fireEvent.click(useForSearch)

      await waitFor(() => expect(selectToolsetProvider).toHaveBeenCalledWith('web', 'Example', 'search'))
      await waitFor(() => expect(screen.getByText('Search: example')).toBeTruthy())
    })

    it('marks only the configured row of two sharing one backend name', async () => {
      // The server's is_active says which row's credential is set, and only that row carries the pills.
      const selfHosted = {
        ...webConfig().providers[1],
        name: 'Example Self-Hosted',
        badge: 'free · self-hosted',
        is_active: false,
        status: 'needs_keys' as const
      }

      getToolsetConfig.mockResolvedValue(
        webConfig({ active_search_backend: 'example', providers: [selfHosted, webConfig().providers[1]] })
      )

      render(<ToolsetConfigPanel onConfiguredChange={vi.fn()} toolset="web" />)

      const cloudRow = await screen.findByRole('button', { name: /^Example(?! Self)/ })
      const selfRow = screen.getByRole('button', { name: /^Example Self-Hosted/ })
      expect(within(cloudRow).getByText('Search backend')).toBeTruthy()
      expect(within(cloudRow).getByText('Extract backend')).toBeTruthy()
      expect(within(selfRow).queryByText('Search backend')).toBeNull()
      expect(within(selfRow).queryByText('Extract backend')).toBeNull()
    })
  })
})
