import type { PluginUpdateTranslations } from './types_plugin_update'

/** Copy for an installed plugin (Plugins tab): its folder access. */
export const enPluginUpdate: PluginUpdateTranslations = {
  folderAccess: {
    title: 'Folder access',
    hint: (name: string) => `${name} can read and change files in these folders. Revoking takes effect at once.`,
    revoke: 'Revoke',
    revokeLabel: (path: string) => `Revoke access to ${path}`,
    revoked: (name: string, path: string) => `${name} can no longer use ${path}.`,
    revokeFailed: (name: string) => `Could not revoke folder access for ${name}`,
    pickerTitle: (name: string) => `Choose a folder for ${name}`,
    pickerButton: 'Allow access',
    refusedProtected: (name: string) =>
      `${name} cannot use that folder: it holds A2Assistant settings, keys or plugin data. Choose a folder that does not contain them.`,
    loadFailed: (name: string) => `Could not load the folders shared with ${name}.`
  },
}
