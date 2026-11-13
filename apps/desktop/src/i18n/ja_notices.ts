import type { TranslationOverrides } from './define-locale'
import { jaDesktopCommands } from './ja_desktop_commands'
import { jaSessionCommands } from './ja_session_commands'

// Shell notices (remote-display toast, butterbar, keep-awake offer), spread into ja.ts.
export const jaNotices = {
  remoteDisplayBanner: {
    message: reason =>
      `ソフトウェアレンダリングが有効です — リモートディスプレイを検出しました（${reason}）。ちらつきを防ぐため GPU アクセラレーションは無効化されています。`
  },
  butterbar: {
    goTo: (index, total) => `お知らせ ${index} / ${total} を表示`
  },
  promptNotices: {
    legacySendUnconfirmed:
      'このサーバーはこのメッセージの前回の送信を確認できなかったため、すでに実行された可能性があります。再送信する前に会話を確認してください。',
    restoredDraftAttachmentsDropped:
      '未送信のメッセージの添付ファイルは復元されませんでした。送信する前にもう一度添付してください。',
    mcpReloadDeferred:
      'このチャットは処理中です。MCP の変更は現在のターンが終わって MCP を再読み込みしたとき、またはチャットを開き直したときに反映されます',
    mcpReloadUnavailable: servers => `接続できませんでした: ${servers}`,
    compactedTurnUnavailable: 'このメッセージはチャットの圧縮時に要約されたため、復元や編集はできなくなりました。',
    staleTurnUnavailable: 'このメッセージはこのチャットの履歴にはもうありません。',
    sessionCommands: jaSessionCommands,
    desktopCommands: jaDesktopCommands
  },
  keepAwakeOffer: {
    title: 'A2Assistant の作業中にコンピューターがスリープしました',
    message:
      'タスクの実行中は、A2Assistant がコンピューターのスリープを防げます。画面はいつもどおりオフになり、バッテリー駆動中はスリープすることがあります。',
    action: '実行中はスリープしない'
  },
  billingBlock: {
    titleProvider: provider => `クレジット不足 — ${provider}`,
    fallbackMessage: 'アカウントのクレジットが不足しています。続行するにはクレジットを追加してください。',
    addCredits: 'クレジットを追加',
    dismiss: '閉じる'
  }
} satisfies Pick<
  TranslationOverrides,
  'remoteDisplayBanner' | 'butterbar' | 'promptNotices' | 'keepAwakeOffer' | 'billingBlock'
>
