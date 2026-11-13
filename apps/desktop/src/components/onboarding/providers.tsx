import { RowButton } from '@/components/ui/row-button'
import { useI18n } from '@/i18n'
import { Check, ChevronRight, Terminal } from '@/lib/icons'
import { PROVIDER_DISPLAY_NAMES } from '@/lib/model-status-label'
import type { OAuthProvider } from '@/types/hermes'

// Titles live in PROVIDER_DISPLAY_NAMES (shared with the model pill); this is
// only the curated order. Both Anthropic entries sit at the bottom: the API-key
// path first, then the subscription OAuth path (only works with extra usage credits).
const PROVIDER_ORDER: Record<string, number> = {
  'openai-codex': 1,
  'minimax-oauth': 2,
  'qwen-oauth': 3,
  'xai-oauth': 4,
  anthropic: 5,
  'claude-code': 6
}

export const providerTitle = (p: OAuthProvider) => PROVIDER_DISPLAY_NAMES[p.id] ?? p.name
const orderOf = (p: OAuthProvider) => PROVIDER_ORDER[p.id] ?? 99

export const sortProviders = (providers: OAuthProvider[]) =>
  [...providers].sort((a, b) => orderOf(a) - orderOf(b) || a.name.localeCompare(b.name))

function ConnectedTag() {
  const { t } = useI18n()

  return (
    <span className="inline-flex items-center gap-1 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
      <Check className="size-3" />
      {t.onboarding.connected}
    </span>
  )
}

const PROVIDER_ROW_CLASS =
  'group flex w-full items-center justify-between gap-3 rounded-[6px] px-3 py-2.5 text-left transition-colors hover:bg-(--ui-control-hover-background)'

/** Quick-key row for API-key providers (Fireworks leads the list, OpenRouter further down). */
export function KeyProviderRow({ onClick, pitch, title }: { onClick: () => void; pitch: string; title: string }) {
  return (
    <RowButton className={PROVIDER_ROW_CLASS} onClick={onClick}>
      <div className="min-w-0">
        <span className="text-[length:var(--conversation-text-font-size)] font-semibold">{title}</span>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{pitch}</p>
      </div>
      <ChevronRight className="size-4 text-muted-foreground transition group-hover:text-foreground" />
    </RowButton>
  )
}

export function FireworksProviderRow({ onClick }: { onClick: () => void }) {
  const { t } = useI18n()

  return <KeyProviderRow onClick={onClick} pitch={t.onboarding.fireworksPitch} title="Fireworks AI" />
}

/** Onboarding row for the managed local runtime: no account, no key — the
 *  destination is the Local Models pane where install/download live. */
export function LocalModelsProviderRow({ onClick }: { onClick: () => void }) {
  const { t } = useI18n()

  return (
    <KeyProviderRow onClick={onClick} pitch={t.onboarding.localModelsPitch} title={t.onboarding.localModelsTitle} />
  )
}

export function OpenRouterProviderRow({ onClick }: { onClick: () => void }) {
  const { t } = useI18n()

  return <KeyProviderRow onClick={onClick} pitch={t.onboarding.openRouterPitch} title="OpenRouter" />
}

export function ProviderRow({
  onSelect,
  provider
}: {
  onSelect: (provider: OAuthProvider) => void
  provider: OAuthProvider
}) {
  const { t } = useI18n()
  const loggedIn = provider.status?.logged_in
  const Trail = provider.flow === 'external' ? Terminal : ChevronRight

  return (
    <RowButton className={PROVIDER_ROW_CLASS} onClick={() => onSelect(provider)}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[length:var(--conversation-text-font-size)] font-semibold">
            {providerTitle(provider)}
          </span>
          {loggedIn ? <ConnectedTag /> : null}
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{t.onboarding.flowSubtitles[provider.flow]}</p>
      </div>
      <Trail className="size-4 text-muted-foreground transition group-hover:text-foreground" />
    </RowButton>
  )
}
