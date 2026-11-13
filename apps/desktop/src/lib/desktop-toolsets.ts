const DESKTOP_HIDDEN_TOOLSETS = new Set(['context_engine', 'moa'])

export function isDesktopToolsetVisible(name: string): boolean {
  return !DESKTOP_HIDDEN_TOOLSETS.has(name)
}

/** Desktop plugin id → the agent toolset carrying the same feature's
 *  agent-side tools. The Plugins page's Desktop switch toggles this app's UI
 *  panel; for these entries it also flips the toolset opt-in through the same
 *  `PUT /api/tools/toolsets/{name}` the Toolsets tab uses, so the panel is
 *  never UI-only (#96969). The kanban board is the built-in case: it has no
 *  agent-plugin package half, its agent tools live in the `kanban` toolset. */
export const DESKTOP_PLUGIN_TOOLSETS: Readonly<Record<string, string>> = {
  kanban: 'kanban'
}
