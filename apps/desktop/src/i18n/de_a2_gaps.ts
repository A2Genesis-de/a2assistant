import type { TranslationOverrides } from './define-locale'

export const deA2Gaps = {
  appTour: {
    capabilities: {
      title: 'Werkzeuge',
      text: 'Skills, Werkzeuge und Plugins, die A2Assistant nutzen kann. Hier fügen Sie weitere hinzu.'
    },
    composer: {
      title: 'Hier fragen',
      text: 'Sagen Sie, was erledigt werden soll. Mit @ fügen Sie eine Datei hinzu.'
    },
    messaging: {
      title: 'Messenger',
      text: 'Erreichen Sie A2Assistant über Telegram.'
    },
    model: {
      title: 'Modellauswahl',
      text: 'Legt fest, welches Modell Ihnen antwortet.'
    },
    modelLocal: 'Dieser Computer kann ein Modell lokal ausführen: Einstellungen > Anbieter > Lokale Modelle.',
    newSession: {
      title: 'Neu beginnen',
      text: 'Ein neuer Chat hat seinen eigenen Kontext. Nutzen Sie einen Chat pro Aufgabe.'
    },
    rightPane: {
      title: 'Der Arbeitsbereich',
      text: 'Öffnet rechts Dateien, Terminal, Review und den In-App-Browser.'
    },
    sessions: {
      title: 'Ihre Chats',
      text: 'Hier liegen alle Unterhaltungen. Durchsuchen, anheften oder wieder öffnen.'
    }
  },
  assistant: {
    approval: {
      commandDetails: 'Befehlsdetails'
    },
    catalogInstall: {
      alreadyInstalled: 'Bereits installiert; unverändert gelassen',
      envVar: name => `Umgebungsvariable ${name}`,
      missingEnv: names => `Setzen Sie ${names}, um die Einrichtung abzuschließen`,
      notEnabled: 'Installiert, aber nicht eingeschaltet',
      phase: {
        downloading: 'Wird heruntergeladen…',
        loading_tools: 'Werkzeuge werden geladen…',
        python_packages: 'Python-Pakete werden installiert…'
      },
      requiresHermes: range => `A2Assistant ${range}`,
      serverNotConnected: (server, reason) => `MCP-Server ${server} nicht verbunden${reason ? `: ${reason}` : ''}`
    },
    thread: {
      errorCodes: {
        SESSION_OWNER_BUSY: {
          title: 'A2Assistant ist in diesem Chat beschäftigt',
          body: 'Hier läuft gerade eine andere Antwort, und Ihre Nachricht konnte nicht in die Warteschlange aufgenommen werden. Es wurde nichts gesendet. Versuchen Sie es erneut, sobald diese Antwort fertig ist.'
        },
        SESSION_OWNER_UNCONFIRMED: {
          title: 'Ihre Nachricht ist möglicherweise schon in der Warteschlange',
          body: 'Das Gateway hat Ihre Nachricht nicht rechtzeitig bestätigt. Falls sie in der Warteschlange ist, wird sie ausgeführt, sobald die vorherige Antwort fertig oder erledigt ist. Prüfen Sie den Chat, bevor Sie sie erneut senden.'
        }
      }
    }
  },
  boot: {
    failure: {
      bundledReinstallHint:
        'Diese mitgelieferte Installation kann sich nicht innerhalb der App reparieren – installieren Sie die App neu, um ihr Backend wiederherzustellen.',
      reinstallApp: 'App neu installieren',
      webappDescription: 'Führen Sie hermes webapp auf diesem Computer aus, um diesen Browser anzumelden.',
      webappTitle: 'Bei A2Assistant anmelden'
    }
  },
  catalog: {
    about: 'Über',
    add: 'Hinzufügen',
    added: 'Hinzugefügt',
    addedDate: 'Hinzugefügt',
    allCategories: 'Alle Kategorien',
    allSources: 'Alle Quellen',
    alphabetical: 'Name',
    author: 'Autor',
    back: 'Zurück zu den Ergebnissen',
    cardView: 'Kartenansicht',
    category: 'Kategorie',
    clearFilters: 'Filter zurücksetzen',
    commands: 'Befehle',
    destinationChanged:
      'Das Ziel hat sich geändert. Schließen Sie diesen Dialog und öffnen Sie den Installationslink erneut.',
    developer: {
      docs: 'Entwicklerdokumentation',
      heading: 'Entwicklermodus',
      pitch: 'Sie haben ein Werkzeug, einen Konnektor, ein Plugin oder einen Mod gebaut?',
      pitchFollowUp: 'Sie möchten, wissen aber nicht wie?',
      submit: 'Mod einreichen',
      title: 'Für A2Assistant entwickeln'
    },
    discover: 'Entdecken',
    discoverKind: kind => `${kind} entdecken`,
    documentation: 'Dokumentation',
    explorePlugins: 'Plugins entdecken',
    exploreSkills: 'Skills entdecken',
    featured: 'Empfohlen',
    filters: 'Filter',
    hooks: 'Hooks',
    install: 'Installieren',
    installComplete: name => `„${name}“ installiert`,
    installDescription:
      'Dieser Skill steht in neuen Chats zur Verfügung. Installieren Sie nur aus Quellen, denen Sie vertrauen.',
    installHint: 'Prüfen Sie die Quelle vor der Installation. Änderungen gelten für neue Chats.',
    installTitle: name => `„${name}“ installieren?`,
    installTo: 'Installieren auf',
    installed: 'Installiert',
    installing: 'Wird installiert…',
    license: 'Lizenz',
    listView: 'Listenansicht',
    loadFailed: 'Der Katalog konnte nicht geladen werden',
    middleware: 'Middleware',
    more: 'Mehr anzeigen',
    moreToExplore: 'Mehr entdecken',
    moreToExploreBlurb: 'Kleinere Bereiche des Katalogs, alle an einem Ort.',
    mostStarred: 'Meiste Sterne',
    newest: 'Neueste',
    nextSlide: 'Nächste Empfehlung',
    noResults: 'Keine Treffer',
    pinned: 'Geprüfter Commit',
    platforms: 'Plattformen',
    previousSlide: 'Vorherige Empfehlung',
    recentlyUpdated: 'Kürzlich aktualisiert',
    related: 'Ähnliches',
    repository: 'Repository',
    requires: 'Erfordert',
    results: count => `${count.toLocaleString()} ${count === 1 ? 'Ergebnis' : 'Ergebnisse'}`,
    retry: 'Erneut versuchen',
    screenshots: 'Screenshots',
    searchPlugins: 'Plugins durchsuchen',
    searchSkills: 'Skills durchsuchen',
    seeAll: 'Alle anzeigen',
    skillsFor: category => `Skills für ${category}.`,
    slideOf: (index, count) => `${index} von ${count}`,
    snapshotHint: 'Aus dem A2Assistant-Katalog. Beim Stöbern werden keine Quell-Repositories kontaktiert.',
    sortBy: 'Sortieren nach',
    source: 'Quelle',
    tags: 'Tags',
    thisComputer: 'Dieser Computer',
    tier: 'Stufe',
    tierLabels: {
      community: 'Community',
      official: 'Offiziell',
      verified: 'Verifiziert'
    },
    tiers: {
      official: {
        title: 'Offizielle Plugins',
        blurb: 'Von Nous Research entwickelt und gepflegt.'
      },
      verified: {
        title: 'Verifizierte Plugins',
        blurb: 'Vom Unternehmen hinter der Integration, von Nous verifiziert.'
      }
    },
    tools: 'Werkzeuge',
    toolsets: {
      callCount: (count, calls) => `${count} ${calls === 1 ? 'Aufruf' : 'Aufrufe'}`,
      essentials: 'Grundausstattung',
      essentialsBlurb: 'Worauf die meiste Arbeit von A2Assistant aufbaut.',
      mostUsed: 'Am häufigsten genutzt',
      mostUsedBlurb: 'Die Werkzeugsätze, die A2Assistant in diesem Profil am häufigsten nutzt.',
      themes: {
        connect: {
          label: 'Verbinden und kommunizieren',
          blurb: 'Konten, andere Agenten, das Smart Home und Suche über das Web hinaus.'
        },
        create: {
          label: 'Sehen, hören und erstellen',
          blurb: 'Bilder und Videos ansehen, Sprache transkribieren und Medien erzeugen.'
        },
        more: {
          label: 'Weitere Werkzeuge',
          blurb: 'Alles Weitere, das sich in diesem Profil einschalten lässt.'
        },
        recall: {
          label: 'Gedächtnis und Wissen',
          blurb: 'Was A2Assistant sich merkt, und die Skills und der Verlauf, die es durchsuchen kann.'
        },
        work: {
          label: 'Browsen, arbeiten und automatisieren',
          blurb: 'Browser und Desktop steuern, Dateien bearbeiten, Code ausführen und Aufgaben planen.'
        }
      },
      toolCount: count => `${count} ${count === 1 ? 'Werkzeug' : 'Werkzeuge'}`
    },
    tryAnother: 'Versuchen Sie eine andere Suche oder setzen Sie die Filter zurück.',
    updatedDate: 'Aktualisiert',
    version: 'Version'
  },
  composer: {
    queuedTerminalSelectionExpiredBody:
      'Diese eingereihte Terminal-Auswahl ist nicht mehr verfügbar. Wählen Sie die Zeilen erneut aus (Ctrl/Cmd+L) und reihen Sie die Nachricht erneut ein.',
    terminalSelectionMissingBody:
      'Wählen Sie die Terminal-Zeilen vor dem Senden erneut aus (Ctrl/Cmd+L) – dieser Chip enthält keinen Originaltext.',
    terminalSelectionMissingTitle: 'Terminal-Auswahl nicht verfügbar'
  },
  connectorOffer: {
    heading: 'Verbundene Apps behalten',
    body: 'Melden Sie sich mit einem kostenlosen Nous-Konto an, damit verbundene Apps wie Gmail oder Slack in Ihrem Konto erhalten bleiben.'
  },
  desktop: {
    resetZoom: 'Zoom zurücksetzen',
    slashCommandIgnoredBody:
      'Slash-Befehle lassen sich nicht mit Anhängen kombinieren. Entfernen Sie den Anhang oder senden Sie den Befehl separat.',
    slashCommandIgnoredTitle: 'Befehl nicht gesendet',
    zoomIn: 'Vergrößern',
    zoomOut: 'Verkleinern'
  },
  externalOpenFailed: {
    close: 'Schließen',
    copyUrl: 'Link kopieren',
    message: 'Für diese Adresse ist kein Browser registriert. Kopieren Sie den Link und öffnen Sie ihn manuell.',
    missing: {
      title: 'Datei nicht gefunden',
      message:
        'Diese Datei existiert nicht – sie wurde möglicherweise gelöscht oder verschoben oder liegt auf einem anderen Rechner.'
    },
    title: 'Dieser Link konnte nicht geöffnet werden'
  },
  install: {
    bundledLocalDesc:
      'Die mit dieser App gelieferte A2Assistant-Laufzeit verwenden – das mitgelieferte Backend ist die lokale Installation.',
    setupChoiceDescLocal:
      'Installieren Sie A2Assistant auf diesem Computer oder verbinden Sie sich mit einem bereits laufenden A2Assistant-Gateway.',
    useLocalDesc:
      'Hier ist bereits eine A2Assistant-Laufzeit installiert – starten Sie sie mit einem Klick. Es wird nichts heruntergeladen.',
    useLocalTitle: 'A2Assistant auf diesem Computer verwenden'
  },
  keybinds: {
    actions: {
      'composer.dictate': 'Diktat starten / beenden',
      'conversation.scrollPageDown': 'Unterhaltung eine Seite nach unten scrollen',
      'conversation.scrollPageUp': 'Unterhaltung eine Seite nach oben scrollen'
    },
    clear: 'Löschen'
  },
  notifications: {
    compressDeferredDone: 'Kontextkomprimierung abgeschlossen',
    sharedProfileWarning:
      'Eine andere A2Assistant-Installation verwendet dieses Profil. Beide Installationen teilen sich Einstellungen und Daten, daher können Änderungen kollidieren. Sie können fortfahren oder die andere Installation vor Änderungen schließen.',
    updateReadyMessageAppInstaller:
      'Eine neue Version von A2Assistant ist bereit. Aktualisieren Sie jetzt, Windows schließt den Vorgang für Sie ab.'
  },
  preview: {
    missingBody: label =>
      `${label} wurde gelöscht, verschoben oder sein temporärer Speicherort wurde geleert. Dieser Tab wird beim nächsten Start nicht wiederhergestellt.`,
    missingTarget: 'Dieser Pfad existiert auf diesem Computer nicht',
    missingTitle: 'Datei existiert nicht mehr'
  },
  profiles: {
    soulMissing:
      'Für dieses Profil gibt es noch keine SOUL.md. Fügen Sie unten Anweisungen hinzu und speichern Sie, um sie anzulegen. Persönlichkeitsvorlagen in config.yaml werden separat verwaltet.'
  },
  rightSidebar: {
    terminalDropControl: paths =>
      `Diese Namen enthalten Steuerzeichen, die die Shell als Tastendruck ausführen würde: ${paths}`,
    terminalDropControlTitle: 'Nicht ins Terminal eingegeben',
    terminalDropTooLarge: (names, limit) => `Jede Datei darf höchstens ${limit} groß sein. Nicht hochgeladen: ${names}`,
    terminalDropTooLargeTitle: 'Zu groß zum Hochladen',
    terminalDropUploadFailed: name => `${name} konnte nicht hochgeladen werden`,
    terminalOpenInteractive: 'Neues Terminal öffnen',
    terminalReadOnly: 'Nur-Lese-Ausgabe',
    terminalReadOnlyHelp:
      'Um auf Eingabeaufforderungen zu antworten, beenden Sie den Hintergrundbefehl und führen Sie ihn in einem neuen Terminal aus. Das neue Terminal öffnet eine eigene Shell und verbindet sich nicht mit diesem Prozess.'
  },
  settings: {
    config: {
      alwaysExternalLinksDesc:
        'Jeden angeklickten Link im Systembrowser statt im In-App-Browser öffnen. „Im In-App-Browser öffnen“ im Kontextmenü funktioniert weiterhin.',
      alwaysExternalLinksTitle: 'Links immer im externen Browser öffnen',
      voiceShortcutHintDesc:
        'Das Tastenkürzel für Sprachaufnahmen legen Sie unter Einstellungen → Tastaturkürzel fest („Sprachkonversation starten / stoppen“). Der Konfigurationswert voice.record_key gilt nur für CLI und TUI.',
      voiceShortcutHintTitle: 'Tastenkürzel für Sprachaufnahme'
    },
    fieldDescriptions: {
      'stt.streaming':
        'Text anzeigen, während Sie sprechen (OpenAI, xAI, ElevenLabs). Bei Fehlern wird auf die Aufnahme zurückgegriffen.'
    },
    fieldLabels: {
      'stt.deepinfra.model': 'DeepInfra-STT-Modell',
      'stt.openai.streamingModel': 'OpenAI-Modell für Live-Transkription',
      'stt.streaming': 'Live-Transkription',
      'stt.xai.model': 'xAI-STT-Modell'
    },
    localModels: {
      downloadEta: time => `noch ca. ${time}`,
      downloadEtaHours: (hours, minutes) => (minutes ? `${hours} h ${minutes} min` : `${hours} h`),
      downloadEtaMinutes: count => `${count} min`,
      downloadEtaSeconds: count => `${count} s`,
      downloadPauseAction: 'Pausieren',
      downloadPauseFailed: model => `Der Download von ${model} konnte nicht pausiert werden`,
      downloadPausedLabel: 'Pausiert',
      downloadResumeAction: 'Fortsetzen',
      downloadResumeFailed: model => `Der Download von ${model} konnte nicht fortgesetzt werden`,
      downloadSpeed: rate => `${rate}`,
      downloadStatusRunning: 'Wird heruntergeladen'
    },
    nav: {
      plugins: 'Plugins'
    },
    uninstallSection: {
      dataKept: path =>
        `Ihre Konfiguration, Chats und Geheimnisse liegen in ${path}. Beim Entfernen der App werden sie nicht gelöscht.`,
      managedBody:
        'Diese Installation wird von Ihrem System verwaltet, daher kann A2Assistant sich nicht selbst entfernen.',
      openAppsSettings: 'App-Einstellungen öffnen'
    }
  },
  shell: {
    statusbar: {
      backend: 'Backend',
      compressions: count => `Komprimierungen: ${count}`,
      messagingDegraded: name => `${name} ausgefallen`,
      messagingStopped: 'Messenger gestoppt',
      planUsageTitle: (used, resetsIn) =>
        `${used} Ihres Tarifkontingents verbraucht${resetsIn ? ` · wird in ${resetsIn} zurückgesetzt` : ''} · Abrechnung öffnen`,
      releaseAvailable: tag => `Version ${tag} ist verfügbar.`,
      togglePlanUsage: 'Tarifnutzung'
    }
  },
  skillDeepLink: {
    destinationChanged:
      'Das Ziel hat sich geändert. Schließen Sie diesen Dialog und öffnen Sie den Installationslink erneut.',
    installComplete: name => `„${name}“ installiert`,
    installDescription:
      'Dieser Skill steht in neuen Chats zur Verfügung. Installieren Sie nur aus Quellen, denen Sie vertrauen.',
    installTitle: name => `„${name}“ installieren?`,
    installTo: 'Installieren auf',
    installed: 'Installiert',
    installing: 'Wird installiert…',
    source: 'Quelle',
    thisComputer: 'Dieser Computer'
  },
  skills: {
    plugins: {
      settingsForm: {
        optional: '(optional)'
      }
    }
  },
  statusStack: {
    coding: {
      readOnlyScope: 'Nur-Lese-Ansicht – Stagen, Zurücksetzen und Committen gelten für „Nicht committet“'
    }
  },
  updates: {
    applyStatus: {
      owed: steps =>
        `Backend aktualisiert, aber noch ausstehend: ${steps}. Führen Sie \`hermes update\` erneut aus, um den Vorgang abzuschließen.`
    }
  }
} satisfies TranslationOverrides
