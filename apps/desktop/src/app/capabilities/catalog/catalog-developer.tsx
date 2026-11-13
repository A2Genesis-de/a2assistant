import { README_URL, REPOSITORY_URL } from '@hermes/shared/repository'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { openExternalLink } from '@/lib/external-link'

import type { CatalogKind } from './catalog-data'

const SKILLS_DOCS_URL = README_URL
const SUBMIT_MOD_URL = REPOSITORY_URL

/** One banner for every catalog. The wing, copy and docs links are shared; the page supplies its own management actions. */
export function CatalogDeveloper({ actions }: { kind: CatalogKind; actions?: ReactNode }) {
  const { t } = useI18n()
  const d = t.catalog.developer

  return (
    <section data-catalog-section="developer">
      <header className="catalog-section-heading"><h2>{d.heading}</h2></header>
      <div className="catalog-developer">
        <div aria-hidden className="catalog-developer-art" />
        <div className="catalog-developer-content">
          <span aria-hidden className="catalog-developer-mark" />
          <h3>{d.title}</h3>
          <p className="text-sm text-(--ui-text-secondary)">{d.pitch}<br />{d.pitchFollowUp}</p>
          <div className="catalog-developer-ctas">
            <Button onClick={() => void openExternalLink(SUBMIT_MOD_URL)} size="sm" variant="default">
              {d.submit}<Codicon name="arrow-up-right" />
            </Button>
            <Button onClick={() => void openExternalLink(SKILLS_DOCS_URL)} size="sm" variant="secondary">
              {d.docs}<Codicon name="arrow-up-right" />
            </Button>
          </div>
        </div>
      </div>
      {actions && <div className="catalog-developer-management">{actions}</div>}
    </section>
  )
}
