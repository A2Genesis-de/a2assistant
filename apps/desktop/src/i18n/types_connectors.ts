export interface ConnectorCardTranslations {
  title: string
  connect: string
  skip: string
  cancel: string
  retry: string
  grant: string
  connected: string
  checking: string
  notConnected: string
  skipped: string
  disabled: string
  failed: string
  needsAuth: string
  opening: string
  waiting: string
  timeout: string
  refresh: string
  connectError: string
  connectErrorFor: (app: string) => string
  unavailable: string
  ownerMissing: string
  search: string
  empty: string
  disclaimer: string
  execution: string
  setup: (server: string) => string
  openInBrowser: string
  setupCancel: string
  authorizedToolsUnavailable: string
  required: string
}
