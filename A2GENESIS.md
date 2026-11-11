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
- `a2` (default branch) = latest upstream **stable release tag** plus our commits. Never merge `upstream/main` into it.
- `main` mirrors `upstream/main` unchanged (GitHub "Sync fork"); do not commit to it.
- Develop on the workstation in `~/Dev/a2genesis/hermes-agent`; feature branches are merged into `a2`.
- Prefer extension over core changes where possible (skills, plugins, hooks, MCP); keep core changes small to
  limit merge conflicts.

## Taking an upstream release

```bash
scripts/a2/sync-upstream.sh          # merges the newest upstream vX.Y.Z tag into a2
git push origin a2
```

## Deploying to a2-macbook

The MacBook install (`~/.hermes/hermes-agent`) tracks `origin/a2` on the `main` channel (source branch instead of
release tags):

```bash
ssh a2-macbook '~/.local/bin/hermes update --yes --branch a2'
```

`hermes update` reinstalls dependencies, rebuilds the desktop app and restarts the gateway (LaunchAgent
`ai.hermes.gateway`). Never edit the checkout on the MacBook directly.
