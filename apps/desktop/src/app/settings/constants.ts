import { REASONING_EFFORTS } from '@hermes/shared'

import {
  Box,
  Brain,
  Globe,
  type IconComponent,
  Lock,
  MessageCircle,
  Mic,
  Monitor,
  Moon,
  Palette,
  Sun,
  Wrench
} from '@/lib/icons'
import type { ThemeMode } from '@/themes/context'

// Single source of truth for built-in personality names lives in
// lib/personalities (mirrors hermes_cli/personality.py BUILTIN_PERSONALITIES).
export { BUILTIN_PERSONALITIES } from '@/lib/personalities'

import { defineFieldCopy } from './field-copy'
import type { DesktopConfigSection } from './types'

// Provider group definitions used to fold raw env-var names like
// ``XAI_API_KEY`` into a single "xAI" card with a friendly label, short
// description, and signup URL. Membership is determined by longest
// prefix match (see ``providerGroup`` in helpers.ts) so more specific
// prefixes (``MINIMAX_CN_``) correctly beat their general parents
// (``MINIMAX_``). New providers should be added here so they get their
// own card in Settings → Keys instead of being lumped into "Other".
interface ProviderPrefix {
  prefix: string
  name: string
  /** Optional one-line tagline shown beneath the group name. */
  description?: string
  /** Optional canonical signup/console URL surfaced from the card header. */
  docsUrl?: string
  /** Lower numbers float to the top of the providers list. */
  priority: number
}

export const EMPTY_SELECT_VALUE = '__hermes_empty__'
export const CONTROL_TEXT = 'text-xs'

export const PROVIDER_GROUPS: ProviderPrefix[] = [
  {
    prefix: 'NOUS_',
    name: 'Nous Portal',
    description: 'Hosted A2Assistant & Nous-trained models',
    docsUrl: 'https://portal.nousresearch.com',
    priority: 0
  },
  {
    prefix: 'OPENROUTER_',
    name: 'OpenRouter',
    description: 'Aggregator for hundreds of frontier models',
    docsUrl: 'https://openrouter.ai/keys',
    priority: 1
  },
  {
    prefix: 'ANTHROPIC_',
    name: 'Anthropic',
    description: 'Claude API access (Sonnet, Opus, Haiku)',
    docsUrl: 'https://console.anthropic.com/settings/keys',
    priority: 2
  },
  {
    prefix: 'XAI_',
    name: 'xAI',
    description: 'Grok models (use OAuth for SuperGrok / Premium+)',
    docsUrl: 'https://console.x.ai/',
    priority: 3
  },
  {
    prefix: 'GOOGLE_',
    name: 'Gemini',
    description: 'Google AI Studio (Gemini 1.5 / 2.0 / 2.5)',
    docsUrl: 'https://aistudio.google.com/app/apikey',
    priority: 4
  },
  { prefix: 'GEMINI_', name: 'Gemini', priority: 4 },
  {
    prefix: 'MINIMAX_',
    name: 'MiniMax',
    description: 'MiniMax-M2 and Hailuo international endpoints',
    docsUrl: 'https://www.minimax.io/',
    priority: 10
  },
  {
    prefix: 'MINIMAX_CN_',
    name: 'MiniMax (China)',
    description: 'MiniMax mainland China endpoint',
    docsUrl: 'https://www.minimaxi.com/',
    priority: 11
  },
  {
    prefix: 'LM_',
    name: 'LM Studio',
    description: 'Local LM Studio server (OpenAI-compatible)',
    docsUrl: 'https://lmstudio.ai/docs/local-server',
    priority: 17
  }
]

// Schema-side select overrides for desktop-relevant enum fields whose
// backend schema only declares a string type.
export const ENUM_OPTIONS: Record<string, string[]> = {
  'agent.image_input_mode': ['auto', 'native', 'text'],
  'approvals.mode': ['manual', 'smart', 'off'],
  'code_execution.mode': ['project', 'strict'],
  'context.engine': ['compressor', 'default', 'custom'],
  // '' = inherit the agent's own effort; the rest is the shared scale.
  'delegation.reasoning_effort': ['', ...REASONING_EFFORTS],
  // NOTE: memory.provider is intentionally NOT listed here. Its options are
  // discovery-driven and served by the backend config schema (merged
  // per-request in web_server._schema_with_dynamic_provider_options), so
  // config-field consumes schema.options directly — a static list here would
  // shadow that and hide user-installed/pip providers (#49513).
  // Terminal execution backends — kept in sync with the dispatch ladder in
  // tools/terminal_tool.py::_create_environment (local/docker/singularity/
  // ssh). Remote backends need extra env (image, host).
  'terminal.backend': ['local', 'docker', 'singularity', 'ssh'],
  'stt.local.model': ['tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'],
  // Speech-to-text backends — kept in sync with BUILTIN_STT_PROVIDERS in
  // tools/transcription_common.py (local_command is auto-detected, not picked).
  'stt.provider': ['local', 'openai'],
  // How the desktop voice conversation is wired — tools/voice_live.py owns the
  // gpt-live branch (one full-duplex voice model delegating to Hermes).
  'voice.voice_chat_mode': ['chained', 'gpt-live'],
  'voice.gpt_live.voice': [
    'marin',
    'cedar',
    'quartz',
    'ripple',
    'vesper',
    'willow',
    'stone',
    'gleam',
    'meridian',
    'bossa',
    'tempo',
    'beacon',
    'delta',
    'cinder'
  ],
  // OpenAI TTS voices — the union across models (per the OpenAI TTS API
  // docs). Model-specific narrowing happens in enumOptionsFor():
  // tts-1 / tts-1-hd support 9 voices; gpt-4o-mini-tts supports all 13.
  // Free-input field — the list is suggestions, not a gate (FREE_INPUT_KEYS).
  'tts.openai.voice': [
    'alloy',
    'ash',
    'ballad',
    'cedar',
    'coral',
    'echo',
    'fable',
    'marin',
    'nova',
    'onyx',
    'sage',
    'shimmer',
    'verse'
  ],
  'tts.kittentts.model': [
    'KittenML/kitten-tts-nano-0.8-int8',
    'KittenML/kitten-tts-micro-0.8-int8',
    'KittenML/kitten-tts-mini-0.8-int8'
  ],
  'tts.kittentts.voice': ['Jasper'],
  'tts.piper.voice': ['en_US-lessac-medium', 'en_US-amy-medium', 'en_US-ryan-high', 'en_GB-alan-medium'],
  // Text-to-speech backends — kept in sync with the built-in source of truth
  // (agent/tts_registry.py::_BUILTIN_NAMES / tools/tts_tool.py::
  // BUILTIN_TTS_PROVIDERS).
  'tts.provider': ['openai', 'kittentts', 'piper'],
  // STT model lists mirror STT_MODEL_CATALOG in tools/transcription_common.py.
  'stt.openai.model': ['whisper-1', 'gpt-4o-mini-transcribe', 'gpt-4o-transcribe', 'gpt-transcribe'],
  'stt.openai.streaming_model': [
    'gpt-live-transcribe',
    'gpt-transcribe',
    'gpt-4o-transcribe',
    'gpt-4o-mini-transcribe'
  ],
  'tts.openai.model': ['gpt-4o-mini-tts', 'tts-1', 'tts-1-hd'],
  'updates.non_interactive_local_changes': ['stash', 'discard']
}

// Voice/model name fields render as a free-input combobox (Input + datalist)
// instead of a closed Select: providers accept custom voice IDs (OpenAI-compatible
// servers with cloned voices, Piper's voice catalog) and ship new model
// names faster than this list updates. The ENUM_OPTIONS above become
// suggestions rather than a gate for these keys.
export const FREE_INPUT_KEYS = new Set([
  'voice.gpt_live.voice',
  'tts.openai.model',
  'tts.openai.voice',
  'stt.openai.model',
  'tts.kittentts.model',
  'tts.kittentts.voice',
  'tts.piper.voice'
])

export const FIELD_LABELS: Record<string, string> = defineFieldCopy({
  model: 'Default Model',
  modelContextLength: 'Main model context window (override)',
  fallbackProviders: 'Fallback Models',
  toolsets: 'Enabled Toolsets',
  timezone: 'Timezone',
  display: {
    personality: 'Personality',
    showReasoning: 'Reasoning Blocks'
  },
  desktop: {
    repoScanEnabled: 'Automatic Repository Discovery',
    repoScanRoots: 'Repository Discovery Roots',
    repoScanExcludePaths: 'Excluded Repository Paths'
  },
  agent: {
    maxTurns: 'Max Agent Steps',
    imageInputMode: 'Image Attachments',
    apiMaxRetries: 'API Retries',
    serviceTier: 'Service Tier',
    toolUseEnforcement: 'Tool-Use Enforcement'
  },
  terminal: {
    cwd: 'Working Directory',
    backend: 'Execution Backend',
    timeout: 'Command Timeout',
    persistentShell: 'Persistent Shell',
    envPassthrough: 'Environment Passthrough',
    dockerImage: 'Docker Image',
    singularityImage: 'Singularity Image'
  },
  fileReadMaxChars: 'File Read Limit',
  toolOutput: {
    maxBytes: 'Terminal Output Limit',
    maxLines: 'File Page Limit',
    maxLineLength: 'Line Length Limit'
  },
  codeExecution: {
    mode: 'Code Execution Mode'
  },
  approvals: {
    mode: 'Approval Mode',
    timeout: 'Approval Timeout',
    mcpReloadConfirm: 'Confirm MCP Reloads'
  },
  commandAllowlist: 'Command Allowlist',
  security: {
    redactSecrets: 'Redact Secrets',
    allowPrivateUrls: 'Allow Private URLs'
  },
  browser: {
    allowPrivateUrls: 'Browser Private URLs',
    autoLocalForPrivateUrls: 'Local Browser For Private URLs',
    useRealProfile: 'Use My Real Browser Profile'
  },
  checkpoints: {
    enabled: 'File Checkpoints',
    maxSnapshots: 'Checkpoint Limit'
  },
  voice: {
    maxRecordingSeconds: 'Max Recording Length',
    autoTts: 'Read Responses Aloud',
    voiceChatMode: 'Voice Chat Mode',
    gptLive: {
      voice: 'GPT-Live Voice',
      instructions: 'GPT-Live Persona'
    }
  },
  stt: {
    enabled: 'Speech To Text',
    echoTranscripts: 'Echo Transcripts',
    provider: 'Speech-To-Text Provider',
    streaming: 'Live Transcription',
    local: {
      model: 'Local Transcription Model',
      language: 'Transcription Language'
    },
    openai: {
      model: 'OpenAI STT Model',
      streamingModel: 'OpenAI Live Transcription Model'
    }
  },
  tts: {
    provider: 'Text-To-Speech Provider',
    openai: {
      model: 'OpenAI TTS Model',
      voice: 'OpenAI Voice'
    },
    kittentts: {
      model: 'KittenTTS Model',
      voice: 'KittenTTS Voice'
    },
    piper: {
      voice: 'Piper Voice'
    }
  },
  memory: {
    memoryEnabled: 'Persistent Memory',
    userProfileEnabled: 'User Profile',
    memoryCharLimit: 'Memory Budget',
    userCharLimit: 'Profile Budget',
    provider: 'Memory Provider'
  },
  context: {
    engine: 'Context Engine'
  },
  compression: {
    enabled: 'Auto-Compression',
    threshold: 'Compression Threshold',
    codexGpt55Autoraise: 'Codex Compression Auto-Raise',
    targetRatio: 'Compression Target',
    protectLastN: 'Protected Recent Messages'
  },
  auxiliary: {
    compression: {
      timeout: 'Compression model timeout (s)'
    }
  },
  delegation: {
    model: 'Subagent Model',
    provider: 'Subagent Provider',
    maxIterations: 'Subagent Turn Limit',
    maxConcurrentChildren: 'Parallel Subagents',
    childTimeoutSeconds: 'Subagent Timeout',
    reasoningEffort: 'Subagent Reasoning Effort'
  },
  updates: {
    nonInteractiveLocalChanges: 'In-App Update Local Changes'
  }
})

export const FIELD_DESCRIPTIONS: Record<string, string> = defineFieldCopy({
  model: 'Used for new chats unless you pick a different model in the composer.',
  modelContextLength:
    "Overrides the detected context window of the MAIN chat model only (tokens). Leave at 0 to use the selected model's detected value. Does not affect auxiliary/MoA models.",
  fallbackProviders: 'Backup provider:model entries to try if the default model fails.',
  display: {
    personality: 'Default assistant style for new sessions.',
    showReasoning: 'Show reasoning sections when the backend provides them.'
  },
  desktop: {
    repoScanEnabled: 'Scan local folders for Git repositories to show in Projects.',
    repoScanRoots: 'Folders to scan. Leave empty to scan your home directory.',
    repoScanExcludePaths: 'Folders and their descendants to skip during repository discovery.'
  },
  timezone: 'IANA timezone identifier. Blank uses the system timezone.',
  browser: {
    useRealProfile:
      "Local browsing uses your real logins. A2Assistant copies your default browser's profile (cookies, logins, preferences) into a managed snapshot and drives it with its packaged Chromium — your live profile is never opened directly, and the copy is refreshed from it on each run. Also lets the agent open a local real-profile session on request even when a cloud browser backend is configured. Only Chromium browsers (Chrome, Edge, Brave, Brave Origin, Chromium) are supported; a non-Chromium default fails with a clear message. Off by default."
  },
  agent: {
    imageInputMode: 'Controls how image attachments are sent to the model.',
    maxTurns: 'Upper bound for tool-calling turns before A2Assistant stops a run.'
  },
  terminal: {
    cwd: 'Default project folder for tool and terminal work.',
    persistentShell:
      'SSH backend: keep exported variables between commands. Off starts each command from the login environment; the working directory always carries over.',
    envPassthrough: 'Environment variables to pass into tool execution.',
    dockerImage: 'Container image used when the execution backend is Docker.',
    singularityImage: 'Image used when the execution backend is Singularity.'
  },
  codeExecution: {
    mode: 'How strictly code execution is scoped to the current project.'
  },
  fileReadMaxChars: 'Maximum characters A2Assistant can read from one file request.',
  approvals: {
    mode: 'How A2Assistant handles commands that need explicit approval.',
    timeout: 'How long approval prompts wait before timing out.'
  },
  security: {
    redactSecrets: 'Hide detected secrets from model-visible content when possible.'
  },
  checkpoints: {
    enabled: 'Create rollback snapshots before file edits.'
  },
  memory: {
    memoryEnabled: 'Save durable memories that can help future sessions.',
    userProfileEnabled: 'Maintain a compact profile of user preferences.'
  },
  context: {
    engine: 'Strategy for managing long conversations near the context limit.'
  },
  compression: {
    enabled: 'Summarize older context when conversations get large.',
    codexGpt55Autoraise: 'Raise compression to 85% for supported ChatGPT Codex OAuth models.'
  },
  auxiliary: {
    compression: {
      timeout:
        'Seconds to wait for the auxiliary compression model per call (default 120). Raise for slow local models.'
    }
  },
  voice: {
    autoTts: 'Automatically speak assistant responses.',
    voiceChatMode:
      'chained: speech-to-text → A2Assistant → text-to-speech with the providers below. gpt-live: one full-duplex OpenAI voice model (gpt-live-1) listens and talks, and hands every real request to A2Assistant — any model you have selected answers with the full toolset. Needs an OpenAI API key; the voice layer bills $0.05 per minute.',
    gptLive: {
      voice: 'Voice for GPT-Live mode. Custom voice IDs are accepted.',
      instructions:
        'Extra sentences for the live voice persona (tone, pace, language). A2Assistant keeps its own system prompt.'
    }
  },
  stt: {
    enabled: 'Enable local or provider-backed speech transcription.',
    echoTranscripts: 'Post the raw 🎙️ transcript of voice messages back to the chat.',
    streaming: 'Show text while you speak (OpenAI). Falls back to the recording on any failure.'
  },
  updates: {
    nonInteractiveLocalChanges:
      'When A2Assistant updates itself from the app (no terminal prompt), keep local source edits (stash) or throw them away (discard). Terminal updates always ask.'
  }
})

// Curated desktop config surface: only fields a user might tune from the app.
export const SECTIONS: DesktopConfigSection[] = [
  {
    id: 'model',
    label: 'Model',
    icon: Box,
    keys: [
      'model_context_length',
      'fallback_providers',
      'delegation.model',
      'delegation.provider',
      'delegation.max_iterations',
      'delegation.max_concurrent_children',
      'delegation.child_timeout_seconds',
      'delegation.reasoning_effort'
    ]
  },
  {
    id: 'chat',
    label: 'Chat',
    icon: MessageCircle,
    keys: ['display.personality', 'timezone', 'display.show_reasoning', 'agent.image_input_mode']
  },
  {
    id: 'appearance',
    label: 'Appearance',
    icon: Palette,
    keys: []
  },
  {
    id: 'workspace',
    label: 'Workspace',
    icon: Monitor,
    keys: [
      'terminal.cwd',
      'desktop.repo_scan_enabled',
      'desktop.repo_scan_roots',
      'desktop.repo_scan_exclude_paths',
      'code_execution.mode',
      'terminal.persistent_shell',
      'terminal.env_passthrough',
      'file_read_max_chars'
    ]
  },
  {
    id: 'safety',
    label: 'Safety',
    icon: Lock,
    keys: [
      'approvals.mode',
      'approvals.timeout',
      'approvals.mcp_reload_confirm',
      'command_allowlist',
      'security.redact_secrets',
      'security.allow_private_urls',
      'checkpoints.enabled'
    ]
  },
  {
    id: 'browser',
    label: 'Browser',
    icon: Globe,
    keys: ['browser.use_real_profile', 'browser.allow_private_urls', 'browser.auto_local_for_private_urls']
  },
  {
    id: 'memory',
    label: 'Memory & Context',
    icon: Brain,
    keys: [
      'memory.memory_enabled',
      'memory.user_profile_enabled',
      'memory.memory_char_limit',
      'memory.user_char_limit',
      'memory.provider',
      'context.engine',
      'compression.enabled',
      'compression.threshold',
      'compression.codex_gpt55_autoraise',
      'compression.target_ratio',
      'compression.protect_last_n',
      'auxiliary.compression.timeout'
    ]
  },
  {
    id: 'voice',
    label: 'Voice',
    icon: Mic,
    keys: [
      'voice.voice_chat_mode',
      'voice.gpt_live.voice',
      'voice.gpt_live.instructions',
      'tts.provider',
      'stt.enabled',
      'stt.echo_transcripts',
      'stt.provider',
      'stt.streaming',
      'voice.auto_tts',
      'tts.openai.model',
      'tts.openai.voice',
      'tts.kittentts.model',
      'tts.kittentts.voice',
      'tts.piper.voice',
      'stt.local.model',
      'stt.local.language',
      'stt.openai.model',
      'stt.openai.streaming_model',
      'voice.max_recording_seconds',
      'voice.client_direct'
    ]
  },
  {
    id: 'advanced',
    label: 'Advanced',
    icon: Wrench,
    keys: [
      'toolsets',
      'terminal.backend',
      'terminal.timeout',
      'terminal.docker_image',
      'terminal.singularity_image',
      'tool_output.max_bytes',
      'tool_output.max_lines',
      'tool_output.max_line_length',
      'checkpoints.max_snapshots',
      'agent.max_turns',
      'agent.api_max_retries',
      'agent.service_tier',
      'agent.tool_use_enforcement',
      'updates.non_interactive_local_changes'
    ]
  }
]

export interface ModeOption {
  id: ThemeMode
  label: string
  icon: IconComponent
}

export const MODE_OPTIONS: ModeOption[] = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor }
]
