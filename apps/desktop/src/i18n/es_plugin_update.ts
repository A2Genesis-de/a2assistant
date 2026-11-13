import type { PluginUpdateTranslations } from './types_plugin_update'

/** Copy for an installed plugin (Plugins tab): its folder access. */
export const esPluginUpdate: PluginUpdateTranslations = {
  folderAccess: {
    title: 'Acceso a carpetas',
    hint: (name: string) => `${name} puede leer y modificar archivos en estas carpetas. Revocar el acceso surte efecto al instante.`,
    revoke: 'Revocar',
    revokeLabel: (path: string) => `Revocar el acceso a ${path}`,
    revoked: (name: string, path: string) => `${name} ya no puede usar ${path}.`,
    revokeFailed: (name: string) => `No se pudo revocar el acceso a carpetas de ${name}`,
    pickerTitle: (name: string) => `Elige una carpeta para ${name}`,
    pickerButton: 'Permitir acceso',
    refusedProtected: (name: string) =>
      `${name} no puede usar esa carpeta: contiene ajustes, claves o datos de plugins de A2Assistant. Elige una carpeta que no los contenga.`,
    loadFailed: (name: string) => `No se pudieron cargar las carpetas compartidas con ${name}.`
  }
}
