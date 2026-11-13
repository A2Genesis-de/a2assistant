import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into zh.ts.
export const zhGatewayHost: GatewayHostTranslations = {
  unavailableTitle: '网关设置不可用',
  unavailableDesc: '桌面 IPC 桥未暴露网关设置。',
  webappHostTitle: 'A2Assistant 主机',
  webappHostDesc:
    'Webapp 始终运行在提供它的 A2Assistant 主机上。下方已保存的连接是这台机器的列表，与 A2Assistant Desktop 应用共享；其他网关通过此主机访问。',
  webappOauthPaste: {
    title: '完成登录',
    description: '如果登录标签页停在无法打开的地址（此浏览器不在网关所在的机器上），请将该地址粘贴到这里。',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: '完成',
    failed: '无法完成登录'
  }
}
