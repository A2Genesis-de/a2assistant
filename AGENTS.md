# A2Assistant – Development Guide

Hub for AI coding assistants and developers. Each area's `AGENTS.md` loads automatically when you
work in that directory; read it before editing there. `python scripts/check` caps this file at 12k
chars. Project knowledge lives in `docs/knowledge/` (start at `index.md`); keep it current.

## Purpose

A2Assistant is the internal autonomous AI assistant of A2Genesis GmbH, running on `a2-macbook`
with A2Intelligence as its model. One agent core serves the CLI/TUI, the Electron desktop app, the
gateway (Telegram, local API server, cron delivery) and the web dashboard. It is based on Hermes
Agent (Nous Research, MIT) and standalone since 2026-11: no upstream sync, no Nous services.

Two invariants shape almost every design decision:

- **Per-conversation prompt caching is sacred.** Never mutate past context, swap toolsets, reload
  memories or rebuild the system prompt mid-conversation; the one exception is compression.
- **The core is a narrow waist; capability lives at the edges** (plugins, skills, MCP).

## Stack & versions

- Python 3.11–3.14 (`pyproject.toml`, locked in `uv.lock`), toolchain provisioned by `pm/`.
- Desktop: Electron 44, React 19, Vite 8, TypeScript 6 (`apps/desktop`, shared code `apps/shared`).
- TUI: Ink (`ui-tui`), dashboard: React (`web`), pnpm workspace (`pnpm-lock.yaml`).
- Targets: macOS arm64 (deployment), Linux (development, tests).

## Commands

```bash
source ./activate                     # provision + activate (bash/zsh)
scripts/run_tests.sh [paths] -q       # Python tests, per-file isolated; never bare pytest
python scripts/check                  # every blocking lint check (`just check`)
ruff check .                          # Python lint
cd apps/desktop && pnpm run typecheck # desktop types (also: pnpm exec vitest run)
cd web && pnpm run typecheck          # dashboard types
just                                  # list all developer recipes
```

Committed generated files: `scripts/gen_serve_handler_ledger.py`, `scripts/boundary_lint.py
--update`, `scripts/ci/prompt_surface.py render` (run via `scripts/run-in-hermes-env`).

## Architecture & modules

```
run_agent.py      AIAgent facade; turn loop in agent/turn_*.py
model_tools.py    tool orchestration; toolsets.py: TOOLSETS, _HERMES_CORE_TOOLS
cli.py            HermesCLI (REPL, slash dispatch) + hermes_cli/cli_*_mixin.py
hermes_state.py   SessionDB facade; hermes_state_*.py siblings
hermes_cli/       CLI, config, setup, update, profiles; branding.py/desktop_bundle.py/repository.py
                  hold product names and the GitHub repository (single source of truth)
gateway/          gateway runner and platforms (api_server, webhook); Telegram in plugins/platforms/telegram
tools/            tools and terminal environments (local, docker, ssh)
plugins/          bundled plugins: a2-elevation, model-providers (custom, lmstudio, anthropic, nous),
                  web (ddgs, searxng), image_gen (openai), computer_use, kanban, memory, ...
apps/desktop      Electron app; web/ dashboard; ui-tui/ + tui_gateway/ TUI
skills/, optional-skills/   bundled skills and the installed "official" optional skills
```

Every former god file is a **facade** plus siblings `<stem>_<topic>.py`. Find code by topic
(`grep -rn "def name" <dir>/<stem>_*.py`); siblings late-import the facade; patch where production
reads. Size ratchets: functions CC ≤ 20, ≤ 300 lines; files ≤ 2,000 lines
(`scripts/code_health/config.py`).

Area guides: `agent/`, `hermes_cli/`, `gateway/`, `tools/`, `plugins/`, `tui_gateway/`, `web/`,
`apps/desktop/`, `skills/`, `cron/`, `tests/`, `pm/`, `hermes_platform/` (each has `AGENTS.md`).

User state: `~/.hermes/config.yaml` (settings), `.env` (secrets only), `logs/`; always through
`get_hermes_home()` / `display_hermes_home()`, never a hard-coded `~/.hermes`.

## AI interface

A2Assistant is itself an agent: it consumes MCP servers (MCP client) and exposes an
OpenAI-compatible API server (`gateway/platforms/api_server.py`), ACP (`acp_adapter/`) and the
`hermes` CLI. No separate MCP server is offered, because other agents reach it through the API
server, Telegram or the CLI.

## Project rules

- Internal product, no upstream sync. Internal identifiers stay as they are until a dedicated
  rename step: command `hermes` (alias `a2assistant`), `~/.hermes`, `HERMES_*`, bundle id
  `com.nousresearch.hermes`, LaunchAgent `ai.hermes.gateway`, keychain services.
- No runtime contact to Nous Research or Hermes infrastructure. Updates and links point at
  `A2Genesis-de/a2assistant` (`hermes_cli/repository.py`, `apps/shared/src/repository.ts`).
- Keep only what the deployment uses (see `docs/knowledge/index.md` § Usage); new integrations
  come as plugins.
- Code: English identifiers, no new comments in source, no defensive clutter, no dead code.
  UI text German via the i18n catalogs (`locales/`, `apps/desktop/src/i18n`).
- Never infer process identity from argv substrings (`gateway.status.looks_like_gateway_command_line`).
- One process serves many profiles: code outside a turn binds the profile scope explicitly
  (`gateway/AGENTS.md` § Profile scope).
- Machine facts and executable lookup go through `hermes_platform`.
- Dependencies carry upper bounds; after editing `pyproject.toml` run `hermes pm lock`; never raw pip.
- Core never imports a specific bundled plugin; plugins use the published API
  (`hermes_cli/data/plugin_api.json`); `scripts/boundary_lint.py` guards new crossings.
- Tests: `scripts/run_tests.sh`, behaviour contracts, never write to `~/.hermes/`.
- Commits in English; work on branches, merge to `main`, never force-push `main` (the MacBook
  fast-forwards it with `hermes update`).
