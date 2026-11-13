import { type SyntheticEvent, useRef } from 'react'

import { CopyButton } from '@/components/ui/copy-button'
import { useI18n } from '@/i18n'

export function UpdateErrorReport({ log }: { log: readonly string[] }) {
  const { t } = useI18n()
  const logText = log.join('\n')
  const logRef = useRef<HTMLPreElement>(null)

  const revealTail = (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (event.currentTarget.open && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }

  if (!logText) {
    return null
  }

  return (
    <div className="grid min-w-0 gap-3 text-left">
      <details className="text-xs text-muted-foreground" onToggle={revealTail}>
        <summary className="cursor-pointer select-none text-center">{t.updates.technicalDetails}</summary>
        <div className="mt-2 grid gap-1">
          <CopyButton appearance="inline" className="justify-self-end" text={logText} />
          <pre
            className="max-h-48 overflow-auto whitespace-pre-wrap wrap-break-word rounded-md border border-border/70 bg-muted/35 px-3 py-2 font-mono text-[0.6875rem] leading-4"
            data-selectable-text="true"
            ref={logRef}
          >
            {logText}
          </pre>
        </div>
      </details>
    </div>
  )
}
