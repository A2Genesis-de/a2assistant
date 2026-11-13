import type { TranslationOverrides } from './define-locale'

// The boot screen's copy (including the update-hold screen), composed by es.ts.
export const esBoot = {
  boot: {
    ready: 'A2Assistant Desktop está listo',
    desktopBootFailedWithMessage: message => `Falló el arranque del escritorio: ${message}`,
    steps: {
      connectingGateway: 'Conectando el gateway de escritorio en vivo',
      loadingSettings: 'Cargando la configuración de A2Assistant',
      loadingSessions: 'Cargando sesiones recientes',
      retryingRemoteBackend: 'Reconectando al backend remoto de A2Assistant…',
      startingDesktopConnection: 'Iniciando la conexión de escritorio',
      startingHermesDesktop: 'Iniciando A2Assistant Desktop…'
    },
    errors: {
      backgroundExited:
        'El servicio que ejecuta tus chats se cerró de forma inesperada. Reinícialo para continuar; tus chats y ajustes están a salvo.',
      backgroundExitedDuringStartup: 'A2Assistant se detuvo justo después de iniciarse.',
      backendStopped: 'A2Assistant dejó de funcionar en segundo plano',
      restartHermes: 'Reiniciar A2Assistant',
      openLogs: 'Abrir registros',
      desktopBootFailed: 'A2Assistant no pudo iniciarse',
      gatewayConnectionLost: 'A2Assistant perdió la conexión',
      gatewayConnectionLostDetail:
        'Seguimos intentando reconectar. Puedes seguir leyendo y escribiendo borradores. Si continúa, reconecta ahora o revisa los ajustes de conexión.',
      reconnectNow: 'Reconectar ahora',
      connectionSettings: 'Configuración de conexión',
      gatewaySignInRequired: 'Tu A2Assistant remoto cerró tu sesión',
      gatewaySignInRequiredDetail: 'Vuelve a iniciar sesión para reconectar. Tus chats y ajustes están a salvo.',
      signInAgain: 'Volver a iniciar sesión',
      ipcBridgeUnavailable: 'A2Assistant Desktop no pudo comunicarse con su propia capa en segundo plano. Reinicia la app.'
    },
    causes: {
      exitedEarly: 'El servicio en segundo plano de A2Assistant se detuvo justo después de iniciarse.',
      timedOut: 'El servicio en segundo plano de A2Assistant no respondió a tiempo.',
      permission: 'A2Assistant no pudo escribir en su carpeta de datos (problema de permisos).',
      diskFull: 'El disco está lleno, así que A2Assistant no pudo iniciarse.',
      portInUse: 'Otro programa está usando el puerto de red que necesita A2Assistant.',
      installMissing: 'Falta parte de la instalación de A2Assistant. Elige Reparar instalación para restaurarla.'
    },
    failure: {
      title: 'A2Assistant no pudo iniciarse',
      description:
        'El servicio en segundo plano de A2Assistant no arrancó. Prueba uno de los pasos de recuperación de abajo. Nada de esto elimina tus chats ni tus ajustes.',
      details: 'Detalles',
      remoteTitle: 'Se requiere iniciar sesión en el gateway remoto',
      remoteDescription:
        'Tu sesión del gateway remoto caducó. Inicia sesión de nuevo para reconectar. Esto no elimina tus chats ni tu configuración.',
      retry: 'Reintentar',
      repairInstall: 'Reparar instalación',
      useLocalGateway: 'Usar gateway local',
      gatewaySettings: 'Configuración del gateway',
      back: 'Atrás',
      openLogs: 'Abrir registros',
      repairHint: 'La reparación vuelve a ejecutar el instalador y puede tardar unos minutos en una máquina nueva.',
      remoteSignInHint: signInLabel =>
        `Cierra la sesión guardada del navegador remoto y abre ${signInLabel}. Usa el gateway local para cambiar al backend incluido.`,
      signOutAndSignIn: 'Cerrar sesión e iniciar sesión',
      remoteFailureHint: 'Revisa la URL e inicia sesión en Configuración del gateway, o cambia al gateway local.',
      hideRecentLogs: 'Ocultar registros recientes',
      showRecentLogs: 'Mostrar registros recientes',
      signedInTitle: 'Sesión iniciada',
      signedInMessage: 'Reconectando con el gateway remoto…',
      signInIncompleteTitle: 'Inicio de sesión incompleto',
      signInIncompleteMessage: 'La ventana de inicio de sesión se cerró antes de que terminara la autenticación.',
      signInFailed: 'No se pudo iniciar sesión',
      signInToRemoteGateway: 'Iniciar sesión en el gateway remoto',
      signInWithProvider: provider => `Iniciar sesión con ${provider}`,
      identityProvider: 'tu proveedor de identidad'
    },
    updateHold: {
      title: 'Una actualización anterior todavía retiene A2Assistant',
      titleUnverified: 'A2Assistant no puede confirmar que la última actualización terminó',
      description:
        'A2Assistant espera antes de iniciar para no cargar archivos que una actualización quizá todavía esté cambiando. Se inicia solo en cuanto termine la retención.',
      heldByProcess: pid =>
        `La actualización (proceso ${pid}) terminó, pero un proceso que inició todavía retiene la instalación de A2Assistant.`,
      heldUnknown: 'Una actualización terminó, pero un proceso que inició todavía retiene la instalación de A2Assistant.',
      unverified:
        'El asistente de actualización no pudo comprobar quién tiene la instalación de A2Assistant. A2Assistant sigue comprobando.',
      since: time => `Esperando desde ${time}`,
      lastChecked: time => `Última comprobación ${time}`,
      recoveryHint:
        'Esto suele resolverse en unos minutos. Si no: cierra A2Assistant, termina los procesos git o hermes que queden (o reinicia el equipo) y vuelve a abrir A2Assistant.',
      checkAgain: 'Comprobar de nuevo',
      quit: 'Salir de A2Assistant',
      openLogs: 'Abrir registros',
      startAnyway: 'Iniciar de todos modos…',
      confirmTitle: '¿Iniciar A2Assistant mientras la actualización todavía lo retiene?',
      confirmBody:
        'El proceso de actualización restante quizá siga cambiando archivos de A2Assistant. Iniciar ahora puede cargar una instalación a medio actualizar, que puede no funcionar hasta que vuelvas a ejecutar la actualización. A2Assistant registra esta decisión y deja el marcador de actualización en su lugar.',
      confirmKeepWaiting: 'Seguir esperando',
      confirmStart: 'Iniciar de todos modos',
      startAnywayRefused:
        'Lo que retiene la instalación cambió antes de que A2Assistant pudiera iniciar. Revísalo e inténtalo de nuevo.'
    }
  }
} satisfies Pick<TranslationOverrides, 'boot'>
