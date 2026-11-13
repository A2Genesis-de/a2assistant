import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into de.ts.
export const deGatewayHost: GatewayHostTranslations = {
  unavailableTitle: 'Gateway-Einstellungen nicht verfügbar',
  unavailableDesc: 'Die Desktop-IPC-Brücke stellt keine Gateway-Einstellungen bereit.',
  webappHostTitle: 'A2Assistant-Host',
  webappHostDesc:
    'Die Webapp läuft immer auf dem A2Assistant-Host, der sie bereitstellt. Die gespeicherten Verbindungen unten sind die Liste dieses Rechners, geteilt mit der A2Assistant-Desktop-App; andere Gateways werden über diesen Host erreicht.',
  webappOauthPaste: {
    title: 'Anmeldung abschließen',
    description: 'Wenn der Anmelde-Tab auf einer Adresse endete, die nicht lädt (dieser Browser läuft nicht auf dem Rechner des Gateways), füge diese Adresse hier ein.',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: 'Abschließen',
    failed: 'Anmeldung konnte nicht abgeschlossen werden'
  }
}
