import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into ru.ts.
export const ruGatewayHost: GatewayHostTranslations = {
  unavailableTitle: 'Настройки шлюза недоступны',
  unavailableDesc: 'IPC-мост приложения не предоставляет настройки шлюза.',
  webappHostTitle: 'Хост A2Assistant',
  webappHostDesc:
    'Webapp всегда работает на хосте A2Assistant, который её обслуживает. Сохранённые подключения ниже — список этого компьютера, общий с приложением A2Assistant Desktop; другие шлюзы доступны через этот хост.',
  webappOauthPaste: {
    title: 'Завершить вход',
    description: 'Если вкладка входа остановилась на адресе, который не открывается (этот браузер не на компьютере шлюза), вставьте этот адрес сюда.',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: 'Завершить',
    failed: 'Не удалось завершить вход'
  }
}
