import { PanelEmpty } from '@/app/overlays/panel'
import { useI18n } from '@/i18n'
import type { Translations } from '@/i18n/types'

import type { ToolsEditorPhase } from './types'

export function ToolsWash({ label, rows = 8 }: { label?: string; rows?: number }) {
  const { t } = useI18n()

  return (
    <div aria-busy className="grid gap-2 px-3.5 py-3" role="status">
      <span className="sr-only">{label ?? t.connectorsPage.tools.loading}</span>
      {Array.from({ length: rows }, (_, index) => (
        <span
          aria-hidden
          className="h-3 rounded-sm bg-(--ui-bg-quaternary)"
          key={index}
          style={{ width: `${68 - (index % 4) * 9}%` }}
        />
      ))}
    </div>
  )
}

type ToolsCopy = Translations['connectorsPage']['tools']

export type ToolsStatusPhase = 'needsAuth' | 'off'

interface StatusView {
  body: (copy: ToolsCopy) => string
  icon: string
  title: (copy: ToolsCopy, connectorName: string) => string
}

type StatusTable = { readonly [phase in ToolsStatusPhase]: StatusView }

const STATUS: StatusTable = {
  needsAuth: {
    body: copy => copy.needsAuthBody,
    icon: 'key',
    title: (copy, connectorName) => copy.needsAuthTitle(connectorName)
  },
  off: {
    body: copy => copy.offBody,
    icon: 'plug',
    title: (copy, connectorName) => copy.offTitle(connectorName)
  }
}

export function isToolsStatusPhase(phase: ToolsEditorPhase): phase is ToolsStatusPhase {
  return phase in STATUS
}

export function ToolsStatus({ connectorName, phase }: { connectorName: string; phase: ToolsStatusPhase }) {
  const { t } = useI18n()
  const copy = t.connectorsPage.tools
  const view = STATUS[phase]

  return <PanelEmpty description={view.body(copy)} icon={view.icon} title={view.title(copy, connectorName)} />
}
