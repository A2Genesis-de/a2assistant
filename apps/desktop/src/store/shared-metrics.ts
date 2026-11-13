import type { SharedMetricsStatusResult } from '@hermes/shared'

export type SharedMetricsRequester = <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>

export function sharedMetricsProfileRequester(
  request: SharedMetricsRequester,
  profile: string
): SharedMetricsRequester {
  return profile === 'custom' ? request : (method, params = {}) => request(method, { ...params, profile })
}

export async function readSharedMetricsEnabled(request: SharedMetricsRequester): Promise<boolean | null> {
  try {
    const status = await request<SharedMetricsStatusResult>('shared_metrics.status')

    return typeof status?.enabled === 'boolean' ? status.enabled : null
  } catch {
    return null
  }
}

export async function reportPendingUpdateRun(request: SharedMetricsRequester): Promise<void> {
  const updates = window.hermesDesktop?.updates

  try {
    const run = await updates?.takePendingRun?.()

    if (!run) {
      return
    }

    let sent = false

    try {
      await request('shared_metrics.update_run', { ...run })
      sent = true
    } finally {
      await updates?.ackPendingRun?.(sent)
    }
  } catch {
    return
  }
}
