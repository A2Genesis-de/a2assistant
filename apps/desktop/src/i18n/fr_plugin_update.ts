import type { PluginUpdateTranslations } from './types_plugin_update'

/** Copy for an installed plugin (Plugins tab): its folder access. */
export const frPluginUpdate: PluginUpdateTranslations = {
  folderAccess: {
    title: 'Accès aux dossiers',
    hint: (name: string) => `${name} peut lire et modifier les fichiers de ces dossiers. Une révocation prend effet immédiatement.`,
    revoke: 'Révoquer',
    revokeLabel: (path: string) => `Révoquer l’accès à ${path}`,
    revoked: (name: string, path: string) => `${name} ne peut plus utiliser ${path}.`,
    revokeFailed: (name: string) => `Impossible de révoquer l’accès aux dossiers de ${name}`,
    pickerTitle: (name: string) => `Choisir un dossier pour ${name}`,
    pickerButton: 'Autoriser l’accès',
    refusedProtected: (name: string) =>
      `${name} ne peut pas utiliser ce dossier : il contient des réglages, des clés ou des données de plugins A2Assistant. Choisissez un dossier qui ne les contient pas.`,
    loadFailed: (name: string) => `Impossible de charger les dossiers partagés avec ${name}.`
  }
}
