// Settings → Gateways copy for a renderer that cannot change its connection: a Desktop whose
// bridge exposes no gateway settings, and the Webapp, bound to the host that serves it.
// `Translations['settings']['gateway']` spreads this in.
export interface GatewayHostTranslations {
  unavailableTitle: string
  unavailableDesc: string
  webappHostTitle: string
  webappHostDesc: string
  /** Finishing a saved gateway's sign-in from the address a browser on another machine landed on. */
  webappOauthPaste: { title: string; description: string; placeholder: string; finish: string; failed: string }
}
