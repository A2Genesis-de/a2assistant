import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into fr.ts.
export const frGatewayHost: GatewayHostTranslations = {
  unavailableTitle: 'Paramètres du gateway indisponibles',
  unavailableDesc: "Le pont IPC du desktop n'expose pas les paramètres du gateway.",
  webappHostTitle: 'Hôte A2Assistant',
  webappHostDesc:
    'La Webapp s’exécute toujours sur l’hôte A2Assistant qui la sert. Les connexions enregistrées ci-dessous sont la liste de cette machine, partagée avec l’app A2Assistant Desktop ; les autres passerelles sont atteintes via cet hôte.',
  webappOauthPaste: {
    title: 'Terminer la connexion',
    description: 'Si l’onglet de connexion s’est arrêté sur une adresse qui ne charge pas (ce navigateur n’est pas sur la machine de la passerelle), collez cette adresse ici.',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: 'Terminer',
    failed: 'Impossible de terminer la connexion'
  }
}
