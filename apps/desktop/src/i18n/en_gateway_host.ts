import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into en.ts.
export const enGatewayHost: GatewayHostTranslations = {
  unavailableTitle: 'Gateway settings unavailable',
  unavailableDesc: 'Connection settings can only be changed from the A2Assistant Desktop app on the computer running it.',
  webappHostTitle: 'A2Assistant host',
  webappHostDesc:
    'The Webapp always runs on the A2Assistant host that serves it. The saved connections below are this machine\'s list, shared with the A2Assistant Desktop app; other gateways are reached through this host.',
  webappOauthPaste: {
    title: 'Finish signing in',
    description: 'If the sign-in tab ended on an address that would not load (this browser is not on the gateway\'s machine), paste that address here.',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: 'Finish',
    failed: 'Could not finish signing in'
  }
}
