---
status: approved
issue: 1
intent: intent/2026-10-02-1-mcp-nixarchy.md
---

# Spec: Turn the fork into mcp-nixarchy

Three parts, landed in this order:

- **A.** Generic fixes, each in its own commit so it can be cherry-picked upstream.
- **B.** Rename and distribution changes.
- **C.** nixarchy sources.

**D** is the nixarchy-side contract. It is tracked in its own nixarchy issue and lands afterwards.

## Design

### A. Generic fixes (one commit each, no rename mixed in)

**A1. `ELASTICSEARCH_URL` is read** (`mcp_nixos/config.py:15`)

- Change to `NIXOS_API = os.environ.get("ELASTICSEARCH_URL", "https://search.nixos.org/backend").rstrip("/")`.
- `NIXOS_AUTH` stays a constant. Upstream does not document an override, and there is no need for one yet.

**A2. One HTTP session with retries** (`mcp_nixos/utils.py`)

- Add a module-level `HTTP = requests.Session()`.
- Mount `HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.3, status_forcelist=(502, 503, 504), allowed_methods=None))` for `https://`.
- Replace the 26 `requests.get/post/head(` calls in `caches.py`, `utils.py` and `sources/{base,flakehub,flakes,nixdev,nixhub,nixos,wiki}.py` with `HTTP.get/post/head(`.
- Exception classes such as `requests.Timeout` are unchanged.
- In tests, change `patch("mcp_nixos.X.requests.get")` to `patch("mcp_nixos.X.HTTP.get")` mechanically. These are about 125 sites, and the patch still lands on the one shared session object.
- `allowed_methods=None` makes the Elasticsearch POST queries retry as well. They are read-only searches.

**A3. Init locks on the three unlocked caches** (`caches.py`: `NvfCache`, `NixDevCache`, `NoogleCache`)

- Copy the double-checked `_init_lock` pattern from `HtmlOptionsCache.get_options`: three copies of about 4 lines each.
- No shared base class. ponytail: three call sites, and a base class would not be smaller.

**A4. Failure cooldown for Nixvim** (`NixvimCache.get_options`, `caches.py:325`)

- On failure, record `time.monotonic()` and the exception.
- For 60 s after a failure, re-raise that `APIError` immediately instead of fetching all 60 chunks again behind the lock.
- This is the same idea as `ChannelCache._DISCOVERY_RETRY_COOLDOWN`.

**A5. Bound `flake-inputs` to safe directories** (`server.py` flake-inputs branch, `sources/flake_inputs.py`)

- When `source` is not a known source, it must resolve with `os.path.realpath` to a directory inside `os.getcwd()` or `$HOME`. Otherwise return an error and never run `nix`.
- A `source` that is neither a known source nor an existing directory gets the error `Unknown source or not a flake directory: …`. Today the misleading `nix` error leaks through.
- Under HTTP transport (`MCP_NIXOS_TRANSPORT=http`), `flake-inputs` is refused unless `MCP_NIXOS_ALLOW_FLAKE_INPUTS=1` is set. A remote client should not make the server evaluate local flakes.

**A6. `flake-inputs ls` honours `limit`** (`flake_inputs.py:168`)

- Add a `limit` parameter and truncate as `store.py:_store_ls` does: directories first, then a `... and N more` line.
- `server.py` passes `limit` through.

**A7. Stats report failed counts** (`sources/nixos.py:425`)

- Call `raise_for_status()` on each count.
- A count that fails prints `unavailable` instead of `0`.
- If both fail, the existing error message is kept.

**A8. Delete dead code**

- Delete `validate_channel` (`base.py:41`) and its export and 4 tests.
- Delete `BASE_CHANNELS` and `NIXVIM_META_BASE` (`config.py`) and their re-exports in `server.py`.

### B. Rename and distribution (decisions 1 and 3 of the intent)

The Python module `mcp_nixos` and the `MCP_NIXOS_*` transport variables stay as they are, so upstream merges stay cheap.

**B1. `pyproject.toml`**

- `name = "mcp-nixarchy"`, with a new description and new URLs.
- `[project.scripts]` lists both `mcp-nixarchy` and `mcp-nixos`. The alias is kept for one release.

**B2. `mcp_nixos/__init__.py`**

- `version("mcp-nixarchy")`.
- Update the docstring.

**B3. `server.py`**

- `FastMCP("mcp-nixarchy", …)`.
- Update the server instructions and the `nix` docstring to cover the new sources (see C).

**B4. `config.py`**

- `FLAKEHUB_USER_AGENT = f"mcp-nixarchy/{__version__}"`.

**B5. `flake.nix`**

- `packages.mcp-nixarchy` becomes the default package. `packages.mcp-nixos` and `apps.mcp-nixos` become aliases.
- `overlays.default` provides `mcp-nixarchy` and an alias `mcp-nixos`.
- `meta.homepage` points to the fork, and `mainProgram = "mcp-nixarchy"`.
- Delete `packages.docker`, the `build-docker` command, and the `mcp-nixos-website` devshell.
- `overlays.fastmcp4` stays. The deprecated `overlays.fastmcp3` alias stays too, because it is upstream's to remove.

**B6. Workflows**

- Delete `publish.yml`, `deploy-flakehub.yml` and `deploy-website.yml`.
- Delete the `docker-build` job and the `website/**` path filters in `ci.yml`.
- `release-please.yml` stays and creates GitHub releases. In `release-please-config.json`, set `package-name: mcp-nixarchy`.

**B7. Delete `website/`.**

**B8. Docs**

- Rewrite `README.md` to be short: what it is, install through the flake, client config, the nixarchy sources, and credit to upstream.
- Update `CLAUDE.md`, `AGENTS.md` and `.github/copilot-instructions.md`.
- Point `.mcp.json` at `.#mcp-nixarchy`.
- Update the names in `.pi/extensions/mcp-nixos.ts`. The file name stays.
- `LICENSE` keeps upstream's copyright line and adds one for the fork.

**B9. Version**

- Keep upstream's numbering. The next release-please release is `v3.2.0`, triggered by the `feat:` commits.

### C. nixarchy sources

There are two new `source` values, one catalogue each, which matches the existing `nix-dev` and `wiki` split.

**C1. `source=nixarchy`: nixarchy module options**

- **Data format:** the `optionsJSON` format from `nixosOptionsDoc`, `{name: {type, description, default?, example?, declarations, readOnly, loc}}`. `default` and `example` are `{_type, text}`.
- **Location:**
  - `$MCP_NIXARCHY_OPTIONS` if set. It may be a path or an `https://` URL.
  - Otherwise `/etc/nixarchy/options.json` if it exists.
  - Otherwise `https://github.com/olafkfreund/nixarchy/releases/latest/download/options.json`.
- **Cache:** `HtmlOptionsCache.get_options` is refactored to call `self._load()`; the HTML class's `_load` is `parse_html_options(self.url, limit=None)`. A new `NixarchyOptionsCache(HtmlOptionsCache)` overrides `_load` to read the JSON and map each entry to the existing dict shape:
  - `{name, type, description}` as strings.
  - Plus `default`, `example` and `declared_in`, as strings and empty when absent.
  - `origin`: `installed (/etc/nixarchy/options.json)` or `GitHub release (may differ from your installed nixarchy)`.
  - The class name `HtmlOptionsCache` is kept for upstream merges.
- **Actions:**
  - `search`, `info`, `browse` and `stats` reuse `_search_html_options`, `_info_html_options`, `_browse_options` and `_stats_html_options`.
  - `_html_source_cache` becomes a dict lookup with the new cache added.
  - `_info_html_options` also prints `Default`, `Example` and `Declared in` when the key is present and non-empty. HM and darwin entries lack these keys, so their output does not change.
  - `stats` prints the `origin` line.
  - `browse` with an empty prefix lists the categories as it does today. The docstring examples use `browse "programs.nixarchy"`.

**C2. `source=nixarchy-docs`: the nixarchy manual**

- **Location:**
  - `$MCP_NIXARCHY_DOCS` if set (a directory).
  - Otherwise `/etc/nixarchy/docs` if it exists.
  - Otherwise GitHub: list `docs/manual` once through `https://api.github.com/repos/olafkfreund/nixarchy/contents/docs/manual`, then fetch each `.md` from `raw.githubusercontent.com/olafkfreund/nixarchy/main/…`.
- **Pages:** `manual/*.md` plus `llms.txt`. The page id is the file stem, for example `ai` or `getting-started`.
- **Cache:** `NixarchyDocsCache` loads all pages once into `{id: (title, markdown)}` under an init lock. The title is the first `# ` line.
- **search:** the score is title hits × 5 plus body term hits, using casefolded query terms. It returns the id, the title, and a 200-character snippet around the first hit. No `stats` and no `browse`, the same as `nix-dev`.
- **info:** returns the page markdown, truncated to 500 lines (`DEFAULT_LINE_LIMIT`) with a note when truncated. It also accepts an id with a `.md` suffix or a `manual/` prefix.
- **Code:** one new module, `sources/nixarchy.py`, with `_search/_info/_stats_nixarchy_options`, `_search/_info_nixarchy_docs` and `_browse_nixarchy`. Both names are added to `KNOWN_SOURCES`, the `server.py` dispatch, and the error lists.

### D. nixarchy-side contract (separate nixarchy issue, after this repo)

D1. **Use this flake for the server.**
- Add a flake input `mcp-nixarchy` that follows nixarchy's `nixpkgs`.
- In `modules/home.nix` `mcpConfig`, set `programs.nixos.package = inputs.mcp-nixarchy.packages.${system}.mcp-nixarchy`.
- The server key stays `nixos`, so tool names and permissions do not change.

D2. **`/etc/nixarchy/options.json`.**
- Build it with `pkgs.nixosOptionsDoc` over `options.programs.nixarchy`, plus the Home Manager options at their real NixOS path, `home-manager.users.<user>.programs.nixarchy.*`, which come from `options.home-manager.users.type.getSubOptions`. HM and NixOS both define `programs.nixarchy.enable`, so using the real path avoids the name clash.
- Rewrite `declarations` to GitHub URLs with `transformOptions`.
- Install it with `environment.etc."nixarchy/options.json".source`.

D3. **Install the manual.** Set `environment.etc."nixarchy/docs".source` to the flake's `docs/` (the manual plus `llms.txt`).

D4. **Publish options.json.** The nixarchy release workflow attaches `options.json` to each GitHub release. That is the fallback in C1.

D5. **Skills and docs.**
- In `pkgs/omarchy/skills/nixos/SKILL.md:174-182, 271` and `nixos-binaries/SKILL.md:93`, tell agents to use the `nix` MCP tool first (with the channel matching the machine). The fallbacks are `nixarchy-search` and `nix search`. Mention `source=nixarchy` and `source=nixarchy-docs`.
- In `docs/manual/ai.md:113-128`, link this repo.
- Adjust `tests/options.nix` and `tests/ai-mirror-mcp-remove.nix`.

D6. **This machine (`~/.config/nixos`, manual follow-up, not in either PR).**
- Drop the `mcp-nixos` input at `flake.nix:47` and its uses at `:451`, `modules/ai/mcp-servers.nix:257` and `modules/packages/sets.nix:243`.
- Delete the stale `"mcp-nixos"` 2.3.1 entry in `~/.claude.json`.
- This is already planned in `plan/2026-09-21-1933-mcp-drift.md`.

### E. Upstream PRs (decision 2)

- After A is merged here, cherry-pick A1–A8 onto a branch from `utensils/mcp-nixos` main and open one PR per fix, or a single PR if the maintainer prefers.
- No rename or nixarchy code goes upstream.

## Alternatives rejected

- **Delete the 140-name re-export block in `server.py` and the lazy-import indirection in `flake_inputs.py`, as the review suggested.**
  - It saves about 150 lines.
  - But it rewrites the patch targets across most of the 6.6k test lines, and it conflicts with every upstream merge, which goes against decision 1.
  - Do it upstream first, if at all.
- **Turn the `nix()` if/elif dispatch into a table.** It has the same merge cost for a cosmetic gain.
- **Rename the module `mcp_nixos` to `mcp_nixarchy`.** Rejected by decision 1.
- **One `nixarchy` source with `type=options|docs`.** `type` already defaults to `packages`, so small models would have to pass two parameters correctly. Two sources fail more clearly.
- **Have the server evaluate the nixarchy flake for options (`nix eval`).** It needs `nix` and network access at query time, takes seconds per evaluation, and is a second path that runs `nix` on behalf of the client (see A5). Rejected by decision 4.
- **A new `MCP_NIXARCHY_*` name for every transport variable.** It breaks existing configs and upstream merges, for a cosmetic gain.
- **A shared `LockedLazyCache` base class.** Three copies of 4 lines are smaller and easier to read.

## Risks

- **Thread safety of `requests.Session`.** It is used from many `asyncio.to_thread` workers. The connection pool is thread-safe. Session cookie handling is not, but none of these APIs set cookies. A2 states this in a comment.
- **Retries can triple latency** when an upstream host is down. `total=2` and short backoff keep the worst case at about 1 s added per call on top of the existing timeouts.
- **A5 could reject a legitimate flake directory** outside `$HOME` and cwd, for example `/etc/nixos` when the client runs elsewhere. The error message names the rule. Moving the cwd, or symlinking into `$HOME`, works around it.
- **The GitHub fallbacks** (the release asset, the contents API at 60 unauthenticated requests per hour) can return data newer than the installed nixarchy, or hit the rate limit. Output always states the origin, and the docs listing is fetched once per process.
- **Before D lands**, `/etc/nixarchy/*` does not exist anywhere, and nixarchy has no release with `options.json`. Until then `source=nixarchy` returns a clear "options catalogue not available" error, and `nixarchy-docs` uses GitHub.
- **Some consumers still run the `mcp-nixos` binary**: this machine's config and anyone using `nix run .#mcp-nixos`. The aliases in B1 and B5 cover them for one release.
- **Deleting `website/` and the Docker output** removes things upstream still ships. Upstream merges will conflict there and must resolve as deletions.

## Verification

- `nix develop -c ruff check . && ruff format --check . && mypy mcp_nixos` is clean.
- `pytest -m unit` passes, including new tests:
  - A3: two threads cause one fetch.
  - A4: a second call within the cooldown makes no HTTP call.
  - A5: a path outside cwd or `$HOME` is refused without running a subprocess, an unknown name is refused, and the action is refused under HTTP transport without the flag.
  - A6: `ls` truncates.
  - A7: a partial failure prints `unavailable`.
  - C1: a fixture `options.json` covers search, info (default, example, declared in), browse, stats and origin, through `MCP_NIXARCHY_OPTIONS`, plus the "not available" error.
  - C2: a fixture docs directory covers search ranking, info, the `.md` and `manual/` id forms, and truncation.
- `pytest -m integration -k "nixarchy_docs"` passes against GitHub (the fallback path).
- `nix flake check` and `nix build .#mcp-nixarchy .#mcp-nixos` pass, and `result/bin/` contains both `mcp-nixarchy` and `mcp-nixos`.
- Smoke test: `MCP_NIXARCHY_DOCS=../nixarchy/docs` run through `uv run python -c` calling `nix(action="search", source="nixarchy-docs", query="mcp")` returns `ai` first.
- In CI on the PR, every remaining job is green, and no deleted workflow is referenced.
