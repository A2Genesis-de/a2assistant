# A2Assistant – project knowledge

Entry point for decisions, context and pitfalls. Keep it current when something changes.

- [A2 features](a2-features.md): theme `a2`, the `a2-elevation` plugin, the simpler desktop app.

## History

- 2026-11-11: fork of Hermes Agent v0.23.1 (Nous Research, MIT). `main` was generated from three
  inputs: an upstream release tag, a hand-written A2 layer (branch `a2/layer`) and a generated brand
  commit (`scripts/a2/apply_brand.py` from `a2/brand.yaml`), plus a weekly upstream-sync workflow.
- 2026-11-13: standalone. Joel decided that A2Assistant stays internal and takes no upstream
  releases. The generator, brand overlay, sync workflow, the `upstream` remote and the branches
  `a2/layer`, `upstream-main` and `refactor/brand-overlay` are gone. The current tree is the plain
  source of truth. The GitHub repo was renamed from `A2Genesis-de/hermes-agent` to
  `A2Genesis-de/a2assistant` (GitHub redirects the old URL), and the workstation folder moved to
  `~/Dev/a2genesis/a2assistant`. GitHub still lists the repo as a fork of NousResearch/hermes-agent;
  leaving the fork network needs GitHub support or a fresh repo.
- Product names live in `hermes_cli/branding.py` and `hermes_cli/desktop_bundle.py`. The repository
  identity lives in `hermes_cli/repository.py` and `apps/shared/src/repository.ts`.

## Usage (what the deployment needs)

As of 2026-11-13, from the MacBook configuration:

- **Surfaces:** macOS CLI, desktop app (mac-arm64, built locally by `hermes update`), and the gateway
  as LaunchAgent `ai.hermes.gateway`. Messaging is Telegram only; there are also local sessions and
  cron delivery to Telegram or local.
- **Model providers:** `custom` (A2Intelligence at https://a2intelligence.a2genesis.de/v1),
  `lmstudio` as fallback, all auxiliary tasks on `main`.
- **Toolsets:** a2_elevation, browser (local Chromium), clarify, code_execution, computer_use,
  connections, cronjob, delegation, file, image_gen (openai to A2Intelligence), kanban, memory,
  session_search, skills, terminal (local), todo, tts/stt (openai to A2Intelligence), vision, and web.
  Web search runs on SearXNG (`web.search_backend`), with ddgs still bundled.
- **Plugins:** a2-elevation (bundled). Advanced-delegation, langfuse and memory-wiki are installed
  in `~/.hermes/plugins` from the former Nous plugin catalog. They keep working as user plugins but
  are no longer updated.
- **Optional skills:** 18 official optional skills are installed; `optional-skills/` holds exactly
  those.

## Removed in the standalone step (2026-11-13)

- **Upstream contact:** updates and update checks use our repo's `main` only; the canary and preview
  channels and the upstream-remote nag are gone. Also removed:
  - the remote model catalog (the picker reads `hermes_cli/models.py`)
  - remote skills hub registries and the Nous skills index
  - the plugin catalog (`plugin-catalog/`), plugin update checks and auto-update
  - docs links to hermes-agent.nousresearch.com in visible places (now the README)
- **Nous services:**
  - telemetry upload (shared metrics stay local-only and off) and debug-report upload
  - the connector relay (`gateway/relay`), the Chronos cron provider and its external cron-provider
    seam, and the remote config backend
  - Nous dashboard sign-in and Web Access, managed Telegram onboarding, Hermes Cloud agent
    discovery in the desktop app
- **Messaging:** every platform except Telegram (25 platform plugins, bridges, tools, setup, UI),
  plus `google_meet` and `teams_pipeline`. The `api_server` and the generic `webhook` stay.
- **Integrations:**
  - 33 model providers (kept: custom, lmstudio, anthropic, nous)
  - video generation, and every image provider except openai
  - every web provider except ddgs and searxng, and `x_search`
  - cloud browsers (Browserbase, Browser Use cloud, Firecrawl)
  - ByteRover and RetainDB memory
  - the Modal, Daytona and Vercel terminal backends
  - cloud TTS/STT (ElevenLabs, Edge, MiniMax, Mistral, Gemini, xAI, Groq, DeepInfra) and NeuTTS
  - the plugins hermes-achievements, security-guidance and disk-cleanup
- Size: 23,618 files / 4.97M lines before, 20,195 files / 4.32M lines after (all tracked files, incl.
  lockfiles and assets).

## Pitfalls

- `tests/compat/old_updater_surface.json` lists names that the updater already installed on the
  MacBook imports from the new tree after the checkout swap. These names must stay importable
  (several are network-free shims in `update_cmd`, `source_releases`, `model_catalog`,
  `plugin_catalog`, `plugins_cmd_catalog`, `plugins_updates`, `plugins_transaction`). Deleting one
  breaks `hermes update` halfway.
- A config that still contains keys of removed features loads fine. Rows for retired platforms are
  ignored via `RETIRED_PLATFORMS`.
- The remote shell on the workstation is zsh, but `./activate` is bash. Scripts and generators run
  with `scripts/run-in-hermes-env <cmd>`.
- Running many full test suites in parallel overloaded the workstation (two reboots on 2026-11-13).
  Cap jobs with `-j`.

## Later

Deferred on purpose (scope freeze 2026-11-13):

- **Nous Portal provider and backend:** auth, billing, subscription, account views, `hermes portal`.
  Unfinished WIP is on branch `later/nous-portal-backend`; the matching desktop/TUI removal is on
  `later/nous-portal-frontend`.
- **Nous Tool Gateway** (managed tool billing, `tools/managed_tool_gateway.py` etc.): finished
  commits on branch `later/nous-tool-gateway` (the last two commits); they conflict with the
  integration removals and need a rebase. It contacts Nous only with a Nous login, which the
  deployment does not have. The hosted connector half of the `connections` toolset still targets
  `connector-gateway.nousresearch.com`; it goes with the Portal removal.
- **Windows support:** update paths, MSIX/Store/AppX, PowerShell installers, `*.ps1`, Windows desktop
  variants.
- **Packaging:** Nix (`flake.nix`, `nix/`), Docker publishing (`Dockerfile`, `docker/`, compose
  files), installers/bootstrap (`apps/bootstrap-installer`, `scripts/install.*`, `setup-hermes.*`),
  Termux, the release scripts (`scripts/release*.py`, `scripts/releases`, `release_channels.py`), and
  the PM artifact mirror fallback (`pm/artifact_mirror.py` → hermes-assets.nousresearch.com).
- **Docs and meta:** `website/` (Docusaurus docs; some generators and tests read it),
  `contributors/`, translated READMEs/CONTRIBUTING/SECURITY, upstream `.github` templates.
- **CI:** cut `.github/workflows` down to one CI workflow (lint + Python tests + desktop
  typecheck/tests).
- **Unused but woven into the core:**
  - OpenRouter, openai-codex and xAI OAuth paths, plus the Bedrock, Gemini and Azure adapters
  - `tools/voice_live.py`, `gateway/session_a2a.py`, the Buzz env carve-out
  - the dead multiplex credential-fingerprint code and local shared-metrics collection
- **Small follow-ups:**
  - the `video` toolset (analysis only); the desktop capabilities catalog browser, which has no
    remote entries any more; `optional-mcps/` (needed by `connections`)
  - `HTTP-Referer` headers naming hermes-agent.nousresearch.com
  - dependencies that became unused (discord.py, slack, matrix, teams, pubsub, dingtalk, lark,
    modal, daytona, vercel, fal, exa, firecrawl-py, parallel-web, edge-tts, elevenlabs, neutts,
    mistral, google-auth): drop the extras in `pyproject.toml`, `pm/extras.py` and
    `tests/test_project_metadata.py`, then `hermes pm lock`
  - the prompt-surface snapshot needs a regeneration check
  - vendoring advanced-delegation, langfuse and memory-wiki as bundled plugins: possible, but the
    user copies would shadow the bundled ones until deleted
- **Rename of the internal identifiers:** CLI `hermes`, `~/.hermes`, `HERMES_*`, bundle id,
  LaunchAgent.

## Test status at the standalone merge

Not run: the full Python suite and the desktop JS unit tests.

What ran:
- The area branches each ran their own large subsets; details are in the merge history.
- After merging: ruff, an import smoke test of the entry points, and the CLI (`--help`,
  `config check`, `tools list`) against the MacBook config.
- A targeted pytest set (Telegram, a2_elevation, config, web providers, connectors): 2,050 passed.
- Typechecks of the desktop app and the dashboard.
