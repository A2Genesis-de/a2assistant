# A2Genesis fork of Hermes Agent

Fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT) maintained by A2Genesis.
Upstream documentation (`README.md`, `AGENTS.md`, `website/docs/`) applies unchanged; this file only covers what is
specific to the fork.

## Purpose

Hermes runs as the autonomous AI assistant of A2Genesis on `a2-macbook`, backed by A2Intelligence
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

## White label and design (A2Intelligence)

Visible branding is A2Intelligence; internal identifiers stay upstream (`hermes` command, `~/.hermes`, bundle id
`com.nousresearch.hermes`, userData `Hermes`) so updates, macOS permissions and plugins keep working.

- Design follows a2genesis.de: monochrome, Geist (`apps/desktop/src/fonts`, OFL), soft surfaces instead of borders,
  pill buttons, no focus rings (focus = background tint). Theme `a2` in `apps/shared/src/theme-presets.ts` (palette)
  and `apps/desktop/src/themes/presets.ts` (typography, shape CSS); it is the default (`DEFAULT_SKIN_NAME`).
- Desktop app name `A2Intelligence` (`apps/desktop/product-identity.cjs`), bundle `A2Intelligence.app`; the Python
  side reads the bundle name from `hermes_cli/desktop_bundle.py`.
- Icons from the brand repo (`~/Dev/a2genesis/brand`): diamond logo in `apps/desktop/assets/` incl. the Icon Composer
  package; in-app mark (A glyph of a2genesis.de) in `apps/desktop/src/components/brand-mark.tsx`.
- UI strings: every `Hermes` in desktop locales and onboarding became `A2Intelligence` (third-party services such as
  Nous Portal and Hermes Cloud keep their names). Re-run after upstream merges:
  `python3 scripts/a2/rebrand_strings.py <files>` on new or changed locale files.
- Agent identity (`agent/prompt_builder.py`, `hermes_cli/default_soul.py`, `SOUL.md`) and the CLI/TUI skin `a2`
  (`hermes_cli/skin_engine.py`, default in `hermes_cli/config_defaults.py`).
- Expect merge conflicts in locale files on upstream syncs; resolve by taking upstream and re-running the script.
