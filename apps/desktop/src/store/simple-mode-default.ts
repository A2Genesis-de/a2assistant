import { INTERFACE_MODE_STORAGE_KEY, setInterfaceMode } from '@/store/interface-mode'

export const SIMPLE_MODE_SEEDED_KEY = 'a2.desktop.simpleModeSeeded.v1'

export function seedSimpleMode(storage: Storage = window.localStorage): void {
  if (storage.getItem(SIMPLE_MODE_SEEDED_KEY) !== null) {
    return
  }

  storage.setItem(SIMPLE_MODE_SEEDED_KEY, '1')

  if (storage.getItem(INTERFACE_MODE_STORAGE_KEY) === null) {
    setInterfaceMode('simple')
  }
}

seedSimpleMode()
