# mcp-nixarchy

An MCP server that gives AI assistants accurate, real-time NixOS data: packages, options,
Home Manager, nix-darwin, Nixvim, NVF, flakes, and the [nixarchy](https://github.com/olafkfreund/nixarchy)
distribution's own options and manual. It queries official APIs and docs, so your AI stops
inventing package names.

This is a fork of [utensils/mcp-nixos](https://github.com/utensils/mcp-nixos) by James Brink
(Utensils Union), which does the heavy lifting. Generic fixes are kept as separate commits so they
can go back upstream. The Python module (`mcp_nixos`), the `MCP_NIXOS_*` variables and the MCP client
key `nixos` are unchanged. The `mcp-nixos` command, package and flake app stay as aliases for one release.

## Tools

Two tools, to keep the context cost small.

**`nix(action, query, source, type, channel, limit, version, system)`**

| Action | What it does |
|--------|-------------|
| `search` / `info` / `stats` | Search, inspect, or count packages, options and docs |
| `browse` | Walk option prefixes (Home Manager, darwin, Nixvim, NVF, nixarchy, Noogle) |
| `channels` | List NixOS channels |
| `flake-inputs` | List, `ls` or `read` the inputs of a local flake |
| `cache` | Binary cache status for a package (`version` and `system` apply here) |
| `store` | Read or list an explicit `/nix/store` path |

| Source | Queries |
|--------|---------|
| `nixos` | Packages, options, programs (search.nixos.org) |
| `home-manager`, `darwin` | Option catalogues from the official docs |
| `nixvim`, `nvf` | Neovim option catalogues (NVF accepts `vim.*`, `programs.nvf.vim.*`, `programs.nvf.settings.vim.*`) |
| `nixarchy` | nixarchy module options (`programs.nixarchy.*`) |
| `nixarchy-docs` | The nixarchy manual (markdown pages and `llms.txt`) |
| `flakes`, `flakehub` | Flake search (search.nixos.org, flakehub.com) |
| `noogle`, `wiki`, `nix-dev` | Nix functions, NixOS Wiki, nix.dev |
| `nixhub` | Package metadata and store paths |

**`nix_versions(package, version, limit)`** gives package version history with nixpkgs commits (NixHub).

```python
nix(action="search", query="firefox", source="nixos", type="packages")
nix(action="search", query="git", source="home-manager")
nix(action="browse", source="nixarchy", query="programs.nixarchy")
nix(action="search", query="mcp", source="nixarchy-docs")
nix(action="info", query="ai", source="nixarchy-docs")
nix(action="flake-inputs", type="read", query="nixpkgs:flake.nix")
```

### nixarchy sources

Both say where their data came from. They look in this order:

- `nixarchy` options: `$MCP_NIXARCHY_OPTIONS`, then `/etc/nixarchy/options.json`, then the GitHub release asset.
- `nixarchy-docs`: `$MCP_NIXARCHY_DOCS`, then `/etc/nixarchy/docs`, then the GitHub repository.

The GitHub fallback may differ from the nixarchy you have installed.

## Install

```bash
nix run github:olafkfreund/mcp-nixarchy
```

Flake overlay (adds `pkgs.mcp-nixarchy`, with its own FastMCP 4 stack, so nothing else in your Python set changes):

```nix
{
  inputs.mcp-nixarchy.url = "github:olafkfreund/mcp-nixarchy";
  # nixpkgs.overlays = [ mcp-nixarchy.overlays.default ];
  # environment.systemPackages = [ pkgs.mcp-nixarchy ];
}
```

Releases are GitHub releases (tags `vX.Y.Z`); there is no PyPI, Docker or FlakeHub publishing.

## Client configuration

Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "nixos": { "type": "stdio", "command": "nix", "args": ["run", "github:olafkfreund/mcp-nixarchy", "--"] }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.nixos]
command = "nix"
args = ["run", "github:olafkfreund/mcp-nixarchy", "--"]
```

opencode (`opencode.json`):

```json
{
  "mcp": {
    "nixos": { "type": "local", "command": ["nix", "run", "github:olafkfreund/mcp-nixarchy", "--"] }
  }
}
```

## Environment variables

| Variable | Meaning |
|----------|---------|
| `MCP_NIXOS_TRANSPORT` | `stdio` (default) or `http` |
| `MCP_NIXOS_HOST`, `MCP_NIXOS_PORT`, `MCP_NIXOS_PATH` | HTTP bind address (`127.0.0.1`), port (`8000`), endpoint (`/mcp`) |
| `MCP_NIXOS_STATELESS_HTTP` | `1` disables per-client session state |
| `ELASTICSEARCH_URL` | Replace the search.nixos.org backend (local testing) |
| `MCP_NIXOS_ALLOW_FLAKE_INPUTS` | `1` allows `flake-inputs` over HTTP (it is refused there by default) |
| `MCP_NIXARCHY_OPTIONS` | Path or URL of a nixarchy `options.json` |
| `MCP_NIXARCHY_DOCS` | Directory holding the nixarchy docs (`manual/*.md`, `llms.txt`) |

**flake-inputs path rule:** `source` may name a flake directory only under the current working
directory or `$HOME`. Anything else returns `SECURITY_ERROR`, and unknown names return "Unknown source".

## Development

```bash
nix develop           # dev shell; `run`, `run-tests`, `lint`, `format`, `typecheck`, `build`
pytest -m unit        # offline tests
pytest -m integration # hits real APIs
ruff check . && ruff format --check . && mypy mcp_nixos
```

## License

MIT. Thanks to NixHub, search.nixos.org, FlakeHub, Noogle, NuschtOS, Nixvim and NVF for the data this serves.
