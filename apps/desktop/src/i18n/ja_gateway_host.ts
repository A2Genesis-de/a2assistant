import type { GatewayHostTranslations } from './types_gateway_host'

// Settings → Gateways copy where the connection cannot change, spread into ja.ts.
export const jaGatewayHost: GatewayHostTranslations = {
  unavailableTitle: 'ゲートウェイ設定は利用できません',
  unavailableDesc: 'デスクトップ IPC ブリッジはゲートウェイ設定を公開していません。',
  webappHostTitle: 'A2Assistant ホスト',
  webappHostDesc:
    'Webapp は常にそれを配信する A2Assistant ホスト上で動作します。下の保存済み接続はこのマシンの一覧で、A2Assistant Desktop アプリと共有されます。他のゲートウェイにはこのホスト経由で接続します。',
  webappOauthPaste: {
    title: 'サインインを完了',
    description: 'サインインのタブが読み込めないアドレスで止まった場合（このブラウザがゲートウェイのマシン上にない場合）、そのアドレスをここに貼り付けてください。',
    placeholder: 'http://127.0.0.1:…/webapp/gateway-connections/oauth/callback?…',
    finish: '完了',
    failed: 'サインインを完了できませんでした'
  }
}
