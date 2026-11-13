import type { Translations } from './types'

// The boot screen's copy (including the update-hold screen), composed by en.ts.
export const enBoot = {
  boot: {
    ready: 'A2Assistant Desktop is ready',
    desktopBootFailedWithMessage: message => `Desktop boot failed: ${message}`,
    steps: {
      connectingGateway: 'Connecting live desktop gateway',
      loadingSettings: 'Loading A2Assistant settings',
      loadingSessions: 'Loading recent sessions',
      retryingRemoteBackend: 'Reconnecting to the remote A2Assistant backend…',
      startingDesktopConnection: 'Starting desktop connection',
      startingHermesDesktop: 'Starting A2Assistant Desktop…'
    },
    errors: {
      backgroundExited:
        'The service that runs your chats closed unexpectedly. Restart it to keep going — your chats and settings are safe.',
      backgroundExitedDuringStartup: 'A2Assistant stopped right after it started.',
      backendStopped: 'A2Assistant stopped working in the background',
      restartHermes: 'Restart A2Assistant',
      openLogs: 'Open logs',
      desktopBootFailed: "A2Assistant couldn't start",
      gatewayConnectionLost: 'A2Assistant lost its connection',
      gatewayConnectionLostDetail:
        'Still trying to reconnect. You can keep reading and drafting. If this keeps up, reconnect now or check your connection settings.',
      reconnectNow: 'Reconnect now',
      connectionSettings: 'Connection settings',
      gatewaySignInRequired: 'Your remote A2Assistant signed you out',
      gatewaySignInRequiredDetail: 'Sign in again to reconnect. Your chats and settings are safe.',
      signInAgain: 'Sign in again',
      ipcBridgeUnavailable: "A2Assistant Desktop couldn't talk to its own background layer. Restart the app."
    },
    // Plain causes for a local backend boot failure (`classifyBootFailure`);
    // the raw output stays behind "Show recent logs".
    causes: {
      exitedEarly: "A2Assistant's background service stopped right after starting.",
      timedOut: "A2Assistant's background service didn't answer in time.",
      permission: "A2Assistant couldn't write to its data folder (permission problem).",
      diskFull: 'The disk is full, so A2Assistant could not start.',
      portInUse: 'Another program is using the network port A2Assistant needs.',
      installMissing: "Part of A2Assistant's installation is missing. Choose Repair install to put it back."
    },
    failure: {
      title: "A2Assistant couldn't start",
      description:
        "A2Assistant's background service didn't come up. Try one of the recovery steps below. Nothing here deletes your chats or settings.",
      details: 'Details',
      remoteTitle: 'Remote gateway sign-in required',
      remoteDescription:
        'Your remote gateway session has expired. Sign in again to reconnect. Nothing here deletes your chats or settings.',
      webappTitle: 'Sign in to A2Assistant',
      webappDescription: 'Run hermes webapp on this computer to sign this browser in.',
      retry: 'Retry',
      repairInstall: 'Repair install',
      useLocalGateway: 'Use local gateway',
      gatewaySettings: 'Gateway settings',
      back: 'Back',
      openLogs: 'Open logs',
      repairHint: 'Repair re-runs the installer and can take a few minutes on a fresh machine.',
      bundledReinstallHint:
        'This bundled install can’t repair itself from inside the app — reinstall the app to restore its backend.',
      reinstallApp: 'Reinstall the app',
      remoteSignInHint: signInLabel =>
        `Signs out of the saved remote browser session, then opens ${signInLabel}. Use local gateway to switch to the bundled backend instead.`,
      signOutAndSignIn: 'Sign out & sign in',
      remoteFailureHint: 'Check the gateway URL and sign-in under Gateway settings, or switch to the local gateway.',
      hideRecentLogs: 'Hide recent logs',
      showRecentLogs: 'Show recent logs',
      signedInTitle: 'Signed in',
      signedInMessage: 'Reconnecting to the remote gateway…',
      signInIncompleteTitle: 'Sign-in incomplete',
      signInIncompleteMessage: 'The login window closed before authentication finished.',
      signInFailed: 'Sign-in failed',
      signInToRemoteGateway: 'Sign in to remote gateway',
      signInWithProvider: provider => `Sign in with ${provider}`,
      identityProvider: 'your identity provider'
    },
    updateHold: {
      title: 'An earlier update still holds A2Assistant',
      titleUnverified: "A2Assistant can't confirm the last update finished",
      description:
        "A2Assistant is holding off on starting so it can't load files an update may still be changing. It starts by itself as soon as the hold ends.",
      heldByProcess: pid =>
        `The update (process ${pid}) exited, but a process it started still holds the A2Assistant install.`,
      heldUnknown: 'An update exited, but a process it started still holds the A2Assistant install.',
      unverified: "The update helper couldn't check who owns the A2Assistant install right now. A2Assistant keeps checking.",
      since: time => `Waiting since ${time}`,
      lastChecked: time => `Last checked ${time}`,
      recoveryHint:
        'This usually clears in a few minutes. If it does not: quit A2Assistant, end leftover git or hermes processes (or restart the computer), then open A2Assistant again.',
      checkAgain: 'Check again',
      quit: 'Quit A2Assistant',
      openLogs: 'Open logs',
      startAnyway: 'Start anyway…',
      confirmTitle: 'Start A2Assistant while the update still holds it?',
      confirmBody:
        "The leftover update process may still be changing A2Assistant's files. Starting now can load a half-updated install, which may not work until you run the update again. A2Assistant records this choice in its log and leaves the update marker in place.",
      confirmKeepWaiting: 'Keep waiting',
      confirmStart: 'Start anyway',
      startAnywayRefused: 'What holds the install changed before A2Assistant could start. Review it and try again.'
    }
  }
} satisfies Pick<Translations, 'boot'>
