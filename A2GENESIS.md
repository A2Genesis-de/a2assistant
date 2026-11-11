# A2Genesis fork of Hermes Agent

Fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT) maintained by A2Genesis.
Upstream documentation (`README.md`, `AGENTS.md`, `website/docs/`) applies unchanged; this file only covers what is
specific to the fork.

## Purpose

Hermes runs as A2Assistant, the autonomous AI assistant of A2Genesis on `a2-macbook`, backed by A2Intelligence
(`https://a2intelligence.a2genesis.de/v1`, model `a2intelligence`, gateway key alias `hermes-macbook`).
The fork lets us change the core while still taking every upstream release.

## Branches and remotes

- `origin` = `A2Genesis-de/hermes-agent`, `upstream` = `NousResearch/hermes-agent`.
- `main` (default branch) = latest upstream **stable release tag** plus our commits. Never merge `upstream/main` into it.
- `upstream-main` mirrors `upstream/main` unchanged; do not commit to it.
- Develop on the workstation in `~/Dev/a2genesis/hermes-agent`; feature branches are merged into `main`.
- Prefer extension over core changes where possible (skills, plugins, hooks, MCP); keep core changes small to
  limit merge conflicts.

## Taking an upstream release

```bash
scripts/a2/sync-upstream.sh          # merges the newest upstream vX.Y.Z tag into main
git push origin main
```

## Deploying to a2-macbook

The MacBook install (`~/.hermes/hermes-agent`) tracks `origin/main` on the `main` channel (source branch instead of
release tags):

```bash
ssh a2-macbook '~/.local/bin/hermes update --yes'
```

`hermes update` reinstalls dependencies, rebuilds the desktop app and restarts the gateway (LaunchAgent
`ai.hermes.gateway`). Never edit the checkout on the MacBook directly.

## White label and design (A2Assistant)

Visible branding is A2Assistant (the assistant); A2Intelligence is the name of the models behind it; internal identifiers stay upstream (`hermes` command, `~/.hermes`, bundle id
`com.nousresearch.hermes`, userData `Hermes`) so updates, macOS permissions and plugins keep working.

- Design follows a2genesis.de: monochrome, Geist (`apps/desktop/src/fonts`, OFL), soft surfaces instead of borders,
  pill buttons, no focus rings (focus = background tint). Theme `a2` in `apps/shared/src/theme-presets.ts` (palette)
  and `apps/desktop/src/themes/presets.ts` (typography, shape CSS); it is the default (`DEFAULT_SKIN_NAME`).
- Desktop app name `A2Assistant` (`apps/desktop/product-identity.cjs`), bundle `A2Assistant.app`; the Python
  side reads the bundle name from `hermes_cli/desktop_bundle.py`.
- Icons from the brand repo (`~/Dev/a2genesis/brand`): diamond logo in `apps/desktop/assets/` incl. the Icon Composer
  package; in-app mark (A glyph of a2genesis.de) in `apps/desktop/src/components/brand-mark.tsx`.
- UI strings: every `Hermes` in desktop locales and onboarding became `A2Assistant` (third-party services such as
  Nous Portal and Hermes Cloud keep their names). Re-run after upstream merges:
  `python3 scripts/a2/rebrand_strings.py <files>` on new or changed locale files.
- Agent identity (`agent/prompt_builder.py`, `hermes_cli/default_soul.py`, `SOUL.md`) and the CLI/TUI skin `a2`
  (`hermes_cli/skin_engine.py`, default in `hermes_cli/config_defaults.py`).
- Expect merge conflicts in locale files on upstream syncs; resolve by taking upstream and re-running the script.

## Elevation (plugin `a2-elevation`)

Protected resources need a time-limited grant instead of being forbidden: `~/Admin/keys`, the keychain, production
servers (`a2-server`, `kraftmatch-server`, `babau-server`, `gunna-server`), `a2-denise` and `sudo`.

- `plugins/a2-elevation/policy.py` decides what is protected (terminal commands, executed code, file-tool paths).
- A `pre_tool_call` hook blocks protected calls without a grant and tells the agent to call `request_elevation`.
- `request_elevation` shows a native macOS dialog (`a2_elevate.swift`, compiled on first use with `swiftc` into
  `~/.hermes/elevation/bin/`), verifies Joel's password with OpenDirectory and stores a grant for 10 minutes in
  `~/.hermes/elevation/grant.json`; every decision is appended to `~/.hermes/elevation/audit.jsonl`.
- Scope `admin` also hands the verified password to the sudo cache for the same 10 minutes
  (`tools/terminal_tool_sudo.py`: cache entries now expire after `SUDO_PASSWORD_TTL_SECONDS`).
- Enable on a new machine: `hermes plugins enable a2-elevation` and `hermes tools enable a2_elevation --platform cli`
  (also `cron`, `telegram`).

## Simpler desktop

- Simple mode is the default (`apps/desktop/src/store/interface-mode.ts`, only Advanced is stored).
- Messaging and the layout picker are Advanced-only; Bot Mode is off and the Kanban board on by default.
- German labels use plain words; missing German strings live in `apps/desktop/src/i18n/de_a2_gaps.ts`, deep-merged
  into `deOverrides` in `de.ts`. After upstream merges re-run
  `OVERLAY_GAPS_UPDATE=1 pnpm exec vitest run src/i18n/overlay-completeness.test.ts` and translate new gaps there.

## Full white label (nothing visible says Hermes)

Every user-visible "Hermes" reads **A2Assistant**: desktop app, Ink TUI, CLI output, gateway and messaging texts
(Telegram menu, notices), web dashboard, tool descriptions and the agent identity (the model is told it runs on
Hermes Agent internally but must call itself A2Assistant). The CLI also answers to `a2assistant` (published next to
`hermes` by `hermes_cli/_launchers.py`); texts name `a2assistant`. Name constants: `hermes_cli/branding.py`.

Deliberately unchanged: internal identifiers (package names, `~/.hermes`, `HERMES_*`, `X-Hermes-*` headers, bundle
id, launchd label, keychain service, git author ids), third-party names ("Hermes Cloud", the Nous Portal "Hermes Agent"
page, models "Hermes 3/4"), the wake word "Hey Hermes" (trained model) and log-only messages. The MIT notice ships as
`ThirdPartyNotices-HermesAgent.txt` in the app resources and as `LICENSE` in the repo.

After upstream merges re-run the rebrand and review the diff:
- Locales: `uv run scripts/a2/rebrand_locales.py` (`--check` only reports).
- TS string catalogs: `python3 scripts/a2/rebrand_strings.py <files>` (catalog files only, never on code with regexes).
- New hard-coded strings in Python/TS: `git grep -n "Hermes"` on the merge diff and fix by hand.
