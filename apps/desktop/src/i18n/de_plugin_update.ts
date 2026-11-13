import type { PluginUpdateTranslations } from './types_plugin_update'

/** Copy for an installed plugin (Plugins tab): its folder access. */
export const dePluginUpdate: PluginUpdateTranslations = {
  folderAccess: {
    title: 'Ordnerzugriff',
    hint: (name: string) => `${name} darf Dateien in diesen Ordnern lesen und ändern. Ein Widerruf gilt sofort.`,
    revoke: 'Widerrufen',
    revokeLabel: (path: string) => `Zugriff auf ${path} widerrufen`,
    revoked: (name: string, path: string) => `${name} kann ${path} nicht mehr verwenden.`,
    revokeFailed: (name: string) => `Ordnerzugriff für ${name} konnte nicht widerrufen werden`,
    pickerTitle: (name: string) => `Ordner für ${name} auswählen`,
    pickerButton: 'Zugriff erlauben',
    refusedProtected: (name: string) =>
      `${name} kann diesen Ordner nicht verwenden: Er enthält A2Assistant-Einstellungen, Schlüssel oder Plugin-Daten. Wählen Sie einen Ordner, der sie nicht enthält.`,
    loadFailed: (name: string) => `Die für ${name} freigegebenen Ordner konnten nicht geladen werden.`
  }
}
