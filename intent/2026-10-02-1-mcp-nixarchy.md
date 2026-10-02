---
status: approved
issue: 1
author: olafkfreund
---

# Intent: Turn the fork into mcp-nixarchy

## Problem

This repository is a fork of `utensils/mcp-nixos` with no changes of its own:
HEAD `6a51781` matches upstream HEAD, and nothing in it mentions nixarchy.
nixarchy does not use this fork. It installs upstream `mcp-nixos` from nixpkgs
through `mcp-servers-nix` (`nixarchy/modules/home.nix:186-193`).

That leaves three problems.

1. **Defects in the inherited code** (from the review on 2026-10-02):
   - `ELASTICSEARCH_URL` is documented but never read. `NIXOS_API` and
     `NIXOS_AUTH` are hardcoded in `mcp_nixos/config.py`.
   - None of the 26 bare `requests` calls reuse a connection or retry.
   - `NvfCache`, `NixDevCache` and `NoogleCache` have no init lock, so
     concurrent first calls each download the full payload.
   - `NixvimCache` fetches about 60 chunks while holding its lock, with no
     cooldown after a failure, so one bad chunk restarts the whole fetch on
     every call.
   - `flake-inputs` runs `nix flake archive` in whatever directory the caller
     passes as `source`. A prompt-injected agent can make it evaluate an
     untrusted flake.
   - `flake-inputs ls` ignores `limit`.
   - `_stats_nixos` reports a failed count as a real `0`.
   - Dead code: `validate_channel`, `NIXVIM_META_BASE`, `BASE_CHANNELS`, and a
     re-export block of about 140 names in `server.py` that exists only so
     tests can patch it.
   - The inherited publish and deploy workflows (PyPI, GHCR, Docker Hub,
     FlakeHub, the S3 website) target upstream's registries and secrets.
2. **The server knows nothing about nixarchy.** nixarchy has about 108
   options under `programs.nixarchy.*`, a 37-page manual in `docs/manual/`,
   and `docs/llms.txt`. Agents on a nixarchy machine cannot query any of it;
   option docs exist only as `description` strings inside the modules.
3. **nixarchy's agent setup works against the server it installs:**
   - The `nixos` skill (`pkgs/omarchy/skills/nixos/SKILL.md:174-182, 271`)
     tells agents to use `nix search` and search.nixos.org instead of the MCP
     tool.
   - On this machine, `~/.claude.json` holds a stale hand-added `mcp-nixos`
     2.3.1 entry next to nixarchy's managed `nixos` entry.
   - `~/.config/nixos/flake.nix:47` pulls a separate upstream input only to
     install the package as a system package.

## Proposed outcome

- The project is named **mcp-nixarchy** (package, CLI, flake outputs, docs,
  README). It keeps every existing mcp-nixos capability.
- Every defect listed above is fixed and covered by a test.
- An agent on a nixarchy machine can:
  - search, look up, and browse `programs.nixarchy.*` options with
    descriptions, types, defaults and declaring files, matching the version
    of nixarchy actually installed;
  - search and read the nixarchy manual.
- nixarchy installs mcp-nixarchy from this flake instead of upstream
  `mcp-nixos`, and its skills tell agents to use the MCP tool first, with
  `nixarchy-search` or `nix search` as the fallback.
- CI passes on the fork: flake check, build, lint, typecheck, unit tests.
  Workflows that publish to registries are removed or disabled.

## Affected users and systems

- This repo: `mcp_nixos/`, `tests/`, `flake.nix`, `nix/`, `pyproject.toml`,
  `.github/workflows/`, `website/`, README, CLAUDE.md, AGENTS.md, `.pi/`.
- nixarchy repo:
  - `flake.nix`: new input.
  - `modules/home.nix`: MCP registration for Claude Code, Codex and opencode.
  - `modules/nixos.nix`: the `programs.nixarchy.mcp` option.
  - Generated options JSON.
  - `pkgs/omarchy/skills/{nixos,nixos-binaries}/SKILL.md`.
  - `docs/manual/ai.md`.
  - Tests in `tests/options.nix` and `tests/ai-mirror-mcp-remove.nix`.
- This machine's config: `~/.config/nixos/flake.nix`, `~/.claude.json`.
- Agents using the server: Claude Code, Codex, opencode, Pi.

## Constraints

- Must keep the two-tool surface (`nix`, `nix_versions`) and plain-text
  output. nixarchy is added as a new `source`, not a new tool.
- Must not break existing nixarchy users during the switch. The MCP client
  key stays `nixos`, so tool names (`mcp__nixos__*`) and permission rules
  keep working.
- Must not publish to upstream's PyPI, Docker or FlakeHub names.
- No `# noqa` or `# type: ignore` (repo rule).
- Must not add a runtime dependency on network access to answer nixarchy
  option questions on a nixarchy machine. Local data comes first.
- `flake-inputs` must stay usable for the current project's flake.

## Decisions (approved 2026-10-02)

1. Rename the distribution, CLI, flake outputs and docs to `mcp-nixarchy`.
   Keep the `mcp_nixos` Python module so upstream merges stay cheap. Keep a
   `mcp-nixos` CLI alias for one release.
2. Send the generic fixes upstream as PRs, and keep merging from upstream.
3. Distribute through the flake and GitHub releases only. Delete `website/`
   and the PyPI, Docker, FlakeHub and website workflows.
4. nixarchy option data comes from an `options.json` that nixarchy builds with
   `nixosOptionsDoc` and installs at a stable path. A copy published on GitHub
   is the fallback.
5. The nixarchy-side changes get their own issue in the nixarchy repo, linked
   to this one, and land after this repo.
6. The nixarchy manual is read from the installed system first, with GitHub
   as the fallback.
