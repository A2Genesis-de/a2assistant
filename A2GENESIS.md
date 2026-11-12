# A2Genesis fork of Hermes Agent

Fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT) maintained by A2Genesis.
Upstream documentation (`README.md`, `AGENTS.md`, `website/docs/`) applies unchanged; this file only covers what is
specific to the fork.

## Purpose

Hermes runs as A2Assistant, the autonomous AI assistant of A2Genesis on `a2-macbook`, backed by A2Intelligence
(`https://a2intelligence.a2genesis.de/v1`, model `a2intelligence`, gateway key alias `hermes-macbook`).
The fork lets us change the core while still taking every upstream release.

## How the fork is built

`main` is never edited directly. Every `main` tree is produced from three inputs:

1. **Upstream** – the newest upstream stable release tag `vX.Y.Z` (date tags like `v2026.9.24` are ignored).
2. **A2 layer** – the hand-written A2 commits on top of that tag: this guide, the brand definition and tooling,
   design (theme `a2`, Geist, borderless composer), the `a2-elevation` plugin, the simpler German desktop,
   icons and brand assets, and the few texts a rule cannot derive (box padding, regexes that accept both names,
   packaging code). It is a small, linear commit series, so upstream conflicts stay rare and local.
3. **Brand layer** – one generated commit, `Apply A2Assistant brand (generated)`, produced by
   `scripts/a2/apply_brand.py` from `a2/brand.yaml`. It is never edited by hand.

`main` only moves forward: each build is integrated as a merge commit whose first parent is the previous `main`,
whose second parent is the build commit and whose tree is exactly the build tree. Its trailers record the inputs:

```
A2-Upstream: v0.23.1
A2-Layer: <layer tip>
A2-Build: <brand commit>
```

`hermes update` on the MacBook therefore keeps fast-forwarding, and force-pushes are never needed.

## Brand definition (`a2/brand.yaml`)

The single source of truth for the white label:

- `brand` – product `A2Assistant`, command `a2assistant`, model `A2Intelligence`, company, contact and macOS app name.
- `keep` / `keep_lines` – what stays upstream: third-party names (Hermes Cloud, Hermes 3/4 models), the wake word,
  `X-Hermes-*` headers, `Hermes.app`/`Hermes-Setup` file names, Electron `userData`, install and executable paths,
  the Electron `pascal` identity (userData dir, single-instance lock), keychain service names, `TERM_PROGRAM`, and the
  legacy SOUL.md texts that seeded installs are upgraded from. `keep_lines` entries may be scoped to one `path`.
- `rules` – regex rules per text kind: `code` (Python and TS/JS source and tests: product names only), `copy`
  (skill docs, SOUL, intro copy: names plus the CLI command), `catalog` (non-English desktop and dashboard
  catalogs: no English articles) and `locale` (`locales/*.yaml`, with Hungarian and Turkish suffix rules).
- `targets` – which files get which treatment. Python and TS/JS files are tokenized, so only string literals
  (including f-strings, template literals and regex literals) change; comments, docstrings and identifiers never do.
  Tests get the same rules as the code they assert on, so assertions on visible strings stay consistent.
- Command names: `hermes <subcommand>` becomes `a2assistant <subcommand>` only in translated `locales/*.yaml`
  values, the hermes-agent skill docs and SOUL. English source strings, desktop catalogs and all Python/TS runtime
  strings keep `hermes`: there the same literal is often executed or matched against process command lines (service
  units, profile wrappers, restart guards), upstream tests assert it verbatim, and `hermes` keeps working next to
  the `a2assistant` alias.
- `generate` – files rendered entirely from the brand values: `hermes_cli/branding.py` (`PRODUCT_NAME`,
  `CLI_COMMAND`, `MODEL_NAME`, `COMPANY`) and `hermes_cli/desktop_bundle.py` (`MACOS_APP_NAME`, `MACOS_APP_BUNDLE`,
  `MACOS_APP_EXECUTABLE`). Code imports names from there instead of hard-coding them. Both are also committed on the
  layer, so a layer checkout runs on its own; the build always regenerates them from `a2/brand.yaml`.
- `edits` – exact per-file substitutions for packaging metadata (author, publisher, copyright, maintainer).
  An edit that matches nothing and whose result is missing fails the run, so upstream drift is noticed.
- `derived` – commands that regenerate committed artifacts after rebranding (the prompt-surface snapshot in
  `tests/fixtures/prompt_surface/`).
- `workflows.disabled` – upstream workflows that make no sense on the fork (releases, canary, docs deploy, Docker
  and sandbox publishing, index bots, autofix, live-provider runs). They stay in the tree, because upstream tests read
  them, and are disabled on GitHub by `scripts/a2/disable-upstream-workflows.sh`.

Internal identifiers stay upstream so updates, macOS permissions and plugins keep working: the `hermes` command
(the CLI also answers to `a2assistant`), `~/.hermes`, `HERMES_*`, package names, bundle id
`com.nousresearch.hermes`, launchd label, keychain services and git author ids. The model is told it runs on
Hermes Agent internally but must call itself A2Assistant. The MIT notice ships as
`ThirdPartyNotices-HermesAgent.txt` in the app resources and as `LICENSE` in the repo.

## Commands

```bash
uv run scripts/a2/apply_brand.py            # apply the brand layer to the working tree (idempotent)
uv run scripts/a2/apply_brand.py --check    # exit 1 if anything would change
uv run scripts/a2/apply_brand.py --derived  # also regenerate derived files (needs the Hermes env)
scripts/a2/test-build.sh                    # brand check, Python suite, JS/TS workspace checks
```

### Taking an upstream release

```bash
scripts/a2/sync-upstream.sh       # newest vX.Y.Z: rebase layer, generate brand, test, fast-forward main
git push origin main
```

The script works in a temporary worktree: it rebases the layer from the previous tag onto the new tag, runs the
generator, commits the brand layer, runs `scripts/a2/test-build.sh` and integrates the result into `main`. On a
layer conflict it keeps the worktree and prints how to continue (`git rebase --continue`, then rerun with `--layer`).
Options: `--tag vX.Y.Z`, `--target <branch>` (build onto another branch), `--skip-tests`, `--keep-workdir`.

### Changing the A2 layer

Hand-written changes go onto the layer, never onto `main`:

```bash
git switch -c feat/x "$(scripts/a2/sync-upstream.sh --layer-tip)"
# edit, commit (code, docs, a2/brand.yaml, ...)
scripts/a2/sync-upstream.sh --layer feat/x   # rebuild main from the same upstream tag with the new layer
git push origin main
```

The script refuses to build when `main` contains changes that are not part of its last build.

### Automation

`.github/workflows/a2-upstream-sync.yml` runs weekly (Monday 05:17 UTC) and on demand (optional `tag` input). It
detects a new stable upstream tag, builds it onto `sync/<tag>` with `scripts/a2/sync-upstream.sh`, runs
`scripts/a2/test-build.sh` and opens a pull request to `main`. Merge it with a merge commit or fast-forward, never
squash. Pushing commits that change workflow files needs a token with `workflow` scope: store a fine-grained token
as the secret `A2_SYNC_TOKEN` (contents, pull requests, actions and workflows: read/write); without it the job falls
back to `GITHUB_TOKEN`, which GitHub rejects as soon as upstream touched `.github/workflows/`.

## Deploying to a2-macbook

The MacBook install (`~/.hermes/hermes-agent`) tracks `origin/main` on the `main` channel (source branch instead of
release tags):

```bash
ssh a2-macbook '~/.local/bin/hermes update --yes'
```

`hermes update` reinstalls dependencies, rebuilds the desktop app and restarts the gateway (LaunchAgent
`ai.hermes.gateway`). Never edit the checkout on the MacBook directly.

## Design (theme `a2`)

- Design follows a2genesis.de: monochrome, Geist (`apps/desktop/src/fonts`, OFL), soft surfaces instead of borders,
  pill buttons, no focus rings (focus = background tint). Theme `a2` in `apps/shared/src/theme-presets.ts` (palette)
  and `apps/desktop/src/themes/presets.ts` (typography, shape CSS); it is the default (`DEFAULT_SKIN_NAME`).
- CLI/TUI skin `a2` (`hermes_cli/skin_engine.py`, default in `hermes_cli/config_defaults.py`).
- Icons from the brand repo (`~/Dev/a2genesis/brand`): diamond logo in `apps/desktop/assets/` incl. the Icon Composer
  package; in-app mark (A glyph of a2genesis.de) in `apps/desktop/src/components/brand-mark.tsx` and
  `web/src/components/BrandMark.tsx`.

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
  into `deOverrides` in `de.ts`. After an upstream sync run
  `OVERLAY_GAPS_UPDATE=1 pnpm exec vitest run src/i18n/overlay-completeness.test.ts` in `apps/desktop` and translate
  new gaps on the layer.
