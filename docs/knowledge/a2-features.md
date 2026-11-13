# A2 features

What A2Genesis added on top of the Hermes Agent base. Formerly part of `A2GENESIS.md`.

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

- `policy.py` decides what is protected (terminal commands, executed code, file-tool paths) and with which scope
  (`protected`, or `admin` for sudo, which also covers `protected`).
- A `pre_tool_call` hook blocks protected calls without a covering grant and tells the agent to call
  `request_elevation`; `elevation.py` (`ElevationService`) holds that check, the request flow and the status.
- `grants.py` (`GrantStore`, injectable clock) keeps the grant for 10 minutes in `~/.hermes/elevation/grant.json`
  and appends every decision to `~/.hermes/elevation/audit.jsonl` with the `channel` that answered (`mac`,
  `telegram`, `none`, `cli`) and, for Telegram, the `actor`.
- Approval channels (`approval.py`): each channel is an `Approver` (`supports`, blocking `ask(request, stop)`,
  `conclude(request, final)`). `FirstAnswerApprover` asks all supporting channels in parallel; the first decisive
  answer (approved, denied, three wrong passwords) wins, the others are stopped and then told the final outcome.
  A new channel is one more `Approver` in `build_service()` (`__init__.py`).
  - `MacDialogApprover` (`mac_dialog.py`): native dialog `a2_elevate.swift`, compiled on first use with `swiftc`
    into `~/.hermes/elevation/bin/`; verifies Joel's password with OpenDirectory. Texts and the app icon (from
    `/Applications/<MACOS_APP_BUNDLE>`, `hermes_cli/desktop_bundle.py`) are passed as arguments; the dialog process
    is killed when another channel wins.
  - `TelegramApprover` (`telegram_bridge.py`): scope `protected` only (an `admin` grant needs the sudo password,
    which never travels over Telegram). It posts "A2Assistant bittet um Freigabe: <reason> – gilt 10 Minuten" with
    the buttons Freigeben / Ablehnen to the Telegram home channel (`TELEGRAM_HOME_CHANNEL`) and edits the message to
    the outcome. It goes through the running gateway: `ctx.register_telegram_handler` hands the plugin the live PTB
    `Application` at connect; the plugin binds its bot and loop and adds a `CallbackQueryHandler` scoped to
    `^a2el:`, so the gateway's own polling delivers the taps and core button flows stay untouched. Only user ids
    listed explicitly in `TELEGRAM_ALLOWED_USERS` may decide (`*` never counts); callback tokens are random per
    request.
- Where Telegram works: when the tool runs inside the gateway process (Telegram sessions, cron jobs). CLI, TUI and
  desktop sessions run in their own process without the bot and use the Mac dialog alone.
- Scope `admin` also hands the verified password to the sudo cache for the same 10 minutes
  (`tools/terminal_tool_sudo.py`: cache entries expire after `SUDO_PASSWORD_TTL_SECONDS`).
- All user-facing German texts live in `texts.py` (product name from `hermes_cli/branding.py`).
- `hermes elevation status|revoke` shows or ends the current grant early.
- Intended core crossings, baselined in `scripts/boundary_lint_baseline.json`: `tools.terminal_tool_sudo`,
  `hermes_cli.branding`, `hermes_cli.desktop_bundle`.
- Tests: `tests/plugins/a2_elevation/`, `tests/tools/test_elevated_sudo_cache.py`.
- Enable on a new machine: `hermes plugins enable a2-elevation` and `hermes tools enable a2_elevation --platform cli`
  (also `cron`, `telegram`).

## Simpler desktop

- Simple mode is the default: `apps/desktop/src/store/simple-mode-default.ts` (imported by `main.tsx`) switches a
  fresh install to Simple once and records that in `a2.desktop.simpleModeSeeded.v1`; the mode store itself keeps
  its original encoding, so its tests and an explicit Advanced choice stay untouched.
- Messaging and the layout picker are Advanced-only; Bot Mode is off and the Kanban board on by default.
- German labels use plain words; missing German strings live in `apps/desktop/src/i18n/de_a2_gaps.ts`, deep-merged
  into `deOverrides` in `de.ts`. To find untranslated strings run
  `OVERLAY_GAPS_UPDATE=1 pnpm exec vitest run src/i18n/overlay-completeness.test.ts` in `apps/desktop` and translate
  the new gaps.
