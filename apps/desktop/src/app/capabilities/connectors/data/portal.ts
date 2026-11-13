import { openExternalLink } from '@/lib/external-link'

import { FALLBACK_PORTAL_URL } from '../../../settings/billing/use-billing-state'

const CONNECTORS_PATH = '/connectors'

const FALLBACK_CONNECTORS_ADMIN_URL = `${FALLBACK_PORTAL_URL}${CONNECTORS_PATH}`

export function openConnectorsAdmin(): void {
  openExternalLink(FALLBACK_CONNECTORS_ADMIN_URL)
}
