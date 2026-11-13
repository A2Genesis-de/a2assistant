import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into es.ts.
export const esGatewayHost: GatewayHostTranslations = {
  unavailableTitle: 'Ajustes del gateway no disponibles',
  unavailableDesc:
    'Los ajustes de conexión solo se pueden cambiar desde la app A2Assistant Desktop en el equipo que la ejecuta.',
  webappHostTitle: 'Host de A2Assistant',
  webappHostDesc:
    'La Webapp siempre se ejecuta en el host de A2Assistant que la sirve. Las conexiones guardadas de abajo son la lista de esta máquina, compartida con la app A2Assistant Desktop; los demás gateways se alcanzan a través de este host.',
  webappOauthPaste: {
    title: 'Terminar de iniciar sesión',
    description: 'Si la pestaña de inicio de sesión terminó en una dirección que no carga (este navegador no está en la máquina del gateway), pega esa dirección aquí.',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: 'Terminar',
    failed: 'No se pudo terminar el inicio de sesión'
  }
}
