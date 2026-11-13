# A2Assistant

A2Assistant is the autonomous AI assistant of A2Genesis GmbH. It runs on `a2-macbook` as a CLI, an
Electron desktop app and a messaging gateway (Telegram), and uses A2Intelligence, the company's own
OpenAI-compatible model endpoint, as its model. It keeps memory and skills across sessions,
delegates to subagents, runs scheduled jobs (cron, kanban) and drives a real terminal, browser and,
on macOS, the desktop (computer use).

The product is internal. It started as a fork of Hermes Agent and has been standalone since
November 2026: no upstream sync, no contact to Nous Research infrastructure, unused integrations
removed.

## What is in it

- **Surfaces:** CLI and TUI (`hermes`, alias `a2assistant`), desktop app (macOS, Apple Silicon),
  gateway as a LaunchAgent with Telegram and the local API server, web dashboard.
- **Models:** any OpenAI-compatible endpoint (`provider: custom`), LM Studio (`lmstudio`, used as
  fallback) and Anthropic-compatible endpoints.
- **Tools:** terminal (local, Docker, SSH), files, web search (ddgs, SearXNG), local Chromium
  browser, vision, image generation, TTS and STT through OpenAI-compatible endpoints, computer use
  (cua-driver), delegation, memory, skills, cron, kanban, MCP client, connections.
- **A2 additions:** the `a2-elevation` plugin (time-limited grants for protected resources via a
  native macOS dialog or Telegram), the `a2` theme and skin, a simpler German desktop app.

## Getting started (development, on the workstation)

```bash
git clone https://github.com/A2Genesis-de/a2assistant.git
cd a2assistant
source ./activate            # bash/zsh; provisions the pinned toolchain and the venv
hermes --help
```

Use an isolated `HERMES_HOME` while developing. Commands, architecture and rules: [AGENTS.md](AGENTS.md).
Project knowledge (decisions, pitfalls, later work): [docs/knowledge/index.md](docs/knowledge/index.md).

## Deployment

`a2-macbook` runs a git clone in `~/.hermes/hermes-agent` on channel `main`:

```bash
hermes update --yes
```

`hermes update` fetches `origin/main`, reinstalls dependencies, rebuilds the desktop app and
restarts the gateway (LaunchAgent `ai.hermes.gateway`). Never edit the clone on the MacBook.

## Based on Hermes Agent

A2Assistant is based on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous
Research, licensed under the MIT License. The original copyright notice is kept in
[LICENSE](LICENSE); see also [NOTICE](NOTICE).
