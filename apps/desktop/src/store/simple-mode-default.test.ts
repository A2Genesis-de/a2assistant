import { beforeEach, describe, expect, it, vi } from 'vitest'

const MODE_KEY = 'hermes.desktop.interfaceMode.v1'
const SEEDED_KEY = 'a2.desktop.simpleModeSeeded.v1'

const load = async () => {
  await import('./simple-mode-default')

  return import('./interface-mode')
}

describe('A2 Simple mode default', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.resetModules()
  })

  it('starts a fresh install in Simple and seeds only once', async () => {
    const { $interfaceMode, setInterfaceMode } = await load()

    expect($interfaceMode.get()).toBe('simple')
    expect(window.localStorage.getItem(SEEDED_KEY)).not.toBeNull()

    setInterfaceMode('advanced')
    vi.resetModules()
    expect((await load()).$interfaceMode.get()).toBe('advanced')
  })

  it('keeps a mode the user already chose', async () => {
    window.localStorage.setItem(MODE_KEY, 'simple')
    const { $interfaceMode } = await load()

    expect($interfaceMode.get()).toBe('simple')
    expect(window.localStorage.getItem(MODE_KEY)).toBe('simple')
  })
})
