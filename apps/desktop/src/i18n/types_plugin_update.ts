/** Plugins tab copy for the folders a plugin may use (`ctx.files`): the app's
 *  picker, the per-plugin grant list and its Revoke action. */
export interface PluginFolderAccessTranslations {
  title: string
  hint: (name: string) => string
  revoke: string
  revokeLabel: (path: string) => string
  revoked: (name: string, path: string) => string
  revokeFailed: (name: string) => string
  pickerTitle: (name: string) => string
  pickerButton: string
  refusedProtected: (name: string) => string
  loadFailed: (name: string) => string
}

/** Copy for an installed plugin (Plugins tab):
 *  the plugin's folder access. */
export interface PluginUpdateTranslations {
  folderAccess: PluginFolderAccessTranslations
}
