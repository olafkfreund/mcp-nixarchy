---
status: approved
issue: 1
spec: spec/2026-10-02-1-mcp-nixarchy.md
---

# Plan: Turn the fork into mcp-nixarchy

## Approved decisions (self-contained summary)

- **The project becomes `mcp-nixarchy`:**
  - Distribution, CLI, flake outputs and docs are renamed.
  - The Python module stays `mcp_nixos`. The `MCP_NIXOS_*` transport variables stay.
  - The MCP client key stays `nixos`.
  - The `mcp-nixos` CLI, package and app remain as aliases for one release.
- **Generic fixes (A1–A8)** each land as their own commit, with no rename mixed in, so they can be cherry-picked to `utensils/mcp-nixos`.
- **Distribution is the flake plus GitHub releases (release-please).**
  - Delete PyPI, Docker, FlakeHub, the website workflows, the Docker package, and `website/`.
  - Version numbering continues: next is v3.2.0.
- **Keep as is:**
  - the 140-name re-export block in `server.py`;
  - the lazy imports in `flake_inputs.py`;
  - the if/elif dispatch in `nix()`;
  - the `HtmlOptionsCache` class name.
- **New sources:**
  - `nixarchy` (options): read from `$MCP_NIXARCHY_OPTIONS`, then `/etc/nixarchy/options.json`, then the GitHub release asset.
  - `nixarchy-docs` (manual): read from `$MCP_NIXARCHY_DOCS`, then `/etc/nixarchy/docs`, then the GitHub contents API plus raw files.
  - Output states where the data came from.
- **Out of this PR:**
  - nixarchy-side work (spec part D) goes in a nixarchy issue opened in step 20.
  - Upstream PRs (part E) are step 21, after merge.

## Repo traps (apply to every step)

- Never use `# noqa`, `# type: ignore` or similar. Fix the cause instead. ruff line length is 120.
- MCP output is plain text only. No JSON or XML in tool responses.
- Blocking I/O in tools goes through `asyncio.to_thread`. Source functions are sync, except `nixhub` and `flake_inputs`.
- Tests use `@pytest.mark.unit` or `@pytest.mark.integration`.
- Integration tests hit real APIs. Mark flaky ones `@pytest.mark.flaky(reruns=3)`.
- Run everything inside `nix develop -c …`.
- The unit suite baseline is 381 passed. It must not drop, except for the 3 `validate_channel` tests deleted in step 8.
- Commit message format is `type: summary (#1)` with the session trailers. Commit once per step unless a step says otherwise.
- Shell cwd resets between Bash calls. Use absolute paths, or `cd` inside the same command.

Check used by every step, referred to as **CHECK** below:

```
nix develop -c bash -c 'ruff check . && ruff format --check . && mypy mcp_nixos && pytest -m unit -q -p no:cacheprovider'
```

## Steps

### Part A: generic fixes (one commit each, `fix:` or `refactor:`)

**1. A1: `mcp_nixos/config.py:15`**
- Change: `import os`; `NIXOS_API = os.environ.get("ELASTICSEARCH_URL", "https://search.nixos.org/backend").rstrip("/")`.
- Add a unit test: set the env var with `monkeypatch`, then `importlib.reload(config)` and assert the value.
- Reload `config` back in the test's teardown, so other tests keep the default.
- Verify: CHECK.
- Commit: `fix: honour ELASTICSEARCH_URL for the NixOS search backend (#1)`.

**2. A2: `mcp_nixos/utils.py`**
- Add a module-level `HTTP = requests.Session()`.
- Mount `HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.3, status_forcelist=(502, 503, 504), allowed_methods=None, raise_on_status=False))` on `https://` and `http://`. (Deviation: `raise_on_status=False` added during implementation, so an exhausted 5xx returns the response and callers' `raise_for_status()` or `status_code` checks behave as before, instead of urllib3 raising `RetryError`.)
- Add a comment: the session is shared across `to_thread` workers. The pool is thread-safe, and no API used sets cookies.
- Replace all 26 call sites `requests.get(`/`requests.post(`/`requests.head(` with `HTTP.get(`/`HTTP.post(`/`HTTP.head(`. Files: `caches.py` (6), `utils.py` (1), `sources/base.py` (3), `flakehub.py` (3), `flakes.py` (2), `nixdev.py` (1), `nixhub.py` (6), `nixos.py` (2), `wiki.py` (2).
- Import with `from ..utils import HTTP` (or `from .utils import HTTP` in `caches.py`). Keep `import requests` wherever `requests.Timeout`/`RequestException` are still used.
- `sources/nixos.py` imports `requests` inside `_stats_nixos`. Replace that import with the `HTTP` import.
- In tests, `sed` every `patch("mcp_nixos.<mod>.requests.<m>"` to `patch("mcp_nixos.<mod>.HTTP.<m>"`. There are about 125 sites in `tests/test_server.py`, `test_tools.py`, `test_nvf.py` and `test_html_sources.py`. No test patches the same method in two modules, so the shared object does not cause conflicts.
- Add one unit test: `HTTP.get_adapter("https://x").max_retries.total == 2`.
- Verify: CHECK, then `grep -rn "requests\.\(get\|post\|head\)(" mcp_nixos` returns nothing.
- Trap: check `utils.py` for a circular import, since `caches.py` imports from `utils`. `utils` must not import `caches`.
- Commit: `perf: share one HTTP session with retries across sources (#1)`.

**3. A3: `caches.py` `NvfCache.get_options` (~449), `NixDevCache.get_index` (~518), `NoogleCache.get_data` (~560)**
- Add `self._init_lock = threading.Lock()` in each `__init__`.
- Wrap the fetch in the double-checked pattern from `HtmlOptionsCache.get_options`: fast-path return, `with self._init_lock:`, re-check, then fetch.
- Tests: for each cache, patch `HTTP.get` with a mock that sleeps 0.1 s and returns a valid payload. Call `get_*` from two threads, then assert `mock.call_count == 1`.
- Verify: CHECK.
- Commit: `fix: serialize first load of NVF, nix.dev and Noogle caches (#1)`.

**4. A4: `caches.py` `NixvimCache` (306–380)**
- Add `self._failed_at: float | None` and `self._failure: APIError | None` to `__init__`.
- Inside the lock, before fetching: if `_failed_at` is set and `time.monotonic() - _failed_at < 60`, raise `self._failure`.
- Restructure the `except` clauses so each one builds the `APIError`, stores it with the timestamp, and raises it.
- On success, clear both fields.
- Use a constant `_FAILURE_COOLDOWN = 60.0`.
- Test: first call → mocked `HTTP.get` raises `requests.Timeout`; second call → raises `APIError` with no new HTTP call. Then advance `time.monotonic` (patched) past 60 s and assert it fetches again.
- Verify: CHECK.
- Commit: `fix: add failure cooldown to the Nixvim options loader (#1)`.

**5. A5: `server.py` flake-inputs branch (~431–460)**
- Replace `flake_dir = source if source not in KNOWN_SOURCES else "."` with:

  ```python
  if source in KNOWN_SOURCES:
      flake_dir = "."
  else:
      resolved = os.path.realpath(source)
      roots = [os.path.realpath(os.getcwd()), os.path.realpath(os.path.expanduser("~"))]
      if not os.path.isdir(resolved):
          return error(f"Unknown source or not a flake directory: {source!r}")
      if not any(resolved == r or resolved.startswith(r + os.sep) for r in roots):
          return error("flake-inputs only reads flakes under the current directory or $HOME", "SECURITY_ERROR")
      flake_dir = resolved
  ```

- Put this before the transport check below.
- At the top of the branch: if `os.environ.get("MCP_NIXOS_TRANSPORT", "").strip().lower() == "http" and not env_bool("MCP_NIXOS_ALLOW_FLAKE_INPUTS")`, return `error("flake-inputs is disabled over HTTP transport; set MCP_NIXOS_ALLOW_FLAKE_INPUTS=1 to enable")`.
- Tests:
  - `/tmp` path (outside cwd/home; use `tmp_path` only if it is outside `$HOME`, otherwise patch `os.path.expanduser`) → `SECURITY_ERROR`, and `_run_nix_command` is never called (patch and assert not called).
  - `source="nixpkgs-typo"` → "Unknown source".
  - HTTP env without the flag → disabled.
  - HTTP env with the flag → passes through to the patched list function.
  - Keep the existing flake-dir tests passing. If any use a `tmp_path` outside cwd/home, `monkeypatch.chdir(tmp_path)` first.
- Update the `source` parameter docstring to say "a flake directory under cwd or $HOME".
- Verify: CHECK.
- Commit: `fix: restrict flake-inputs to flakes under cwd or $HOME (#1)`.

**6. A6: `sources/flake_inputs.py:168` `_flake_inputs_ls`**
- Add a `limit: int` parameter.
- After building `dirs` and `files`, print at most `limit` entries (directories first). When truncated, append ` showing N of M` to the header, which is the wording `store.py:_store_ls` actually uses. (Deviation: the plan first said `... and N more entries`; implementation matched store.py instead.)
- In `server.py`, call `_flake_inputs_ls(flake_dir, query, ls_limit)` with `ls_limit` computed as in the `store ls` branch (20 → `DEFAULT_LINE_LIMIT`, capped at `MAX_LINE_LIMIT`).
- Fix the existing tests that call `_flake_inputs_ls` positionally.
- Add a test: 30 fake entries with `limit=5` shows 5 lines plus the "more" line.
- Verify: CHECK.
- Commit: `fix: honour limit in flake-inputs ls (#1)`.

**7. A7: `sources/nixos.py:425` `_stats_nixos`**
- Use a helper `_count(kind) -> int | None` that calls `HTTP.post(...)`, then `raise_for_status()`, then `int(resp.json()["count"])`. It returns `None` on any exception.
- If both counts are `None`, return the existing error. Otherwise print `unavailable` for the `None` count.
- Test: package count OK, option count raises HTTP 500 → output contains `Options: unavailable`.
- Verify: CHECK.
- Commit: `fix: report unavailable NixOS stats instead of zero (#1)`.

**8. A8: delete dead code**
- `sources/base.py:41-52`: delete `validate_channel`.
- `sources/__init__.py`: remove it from the import and from `__all__`.
- `server.py`: remove it from the imports (138) and from the re-export list (695). Remove `BASE_CHANNELS` (41, 647) and `NIXVIM_META_BASE` (58, 654).
- `config.py`: delete `BASE_CHANNELS` and `NIXVIM_META_BASE`, including its comment.
- `tests/test_server.py:19, 674-686`: remove the import and the 3 tests that call `validate_channel` (deviation: the plan said 4; `test_suggestions` covers `get_channel_suggestions` and stays).
- Verify: CHECK, then `grep -rn "validate_channel\|BASE_CHANNELS\|NIXVIM_META_BASE" mcp_nixos tests` returns nothing.
- Commit: `refactor: remove unused validate_channel and dead config constants (#1)`.

### Part B: rename and distribution

**9. B1, B2, B3, B4: Python metadata and names**
- `pyproject.toml`:
  - `name = "mcp-nixarchy"`.
  - `description = "MCP server for NixOS, Home Manager, nix-darwin and nixarchy"`.
  - URLs point to `https://github.com/olafkfreund/mcp-nixarchy`.
  - (Deviation, found in implementation:)
    - There was no `[project.urls]`, so one was added (Homepage).
    - Added `[tool.hatch.build.targets.wheel] packages = ["mcp_nixos"]`, because hatchling derives the package directory from the project name, and the wheel build failed without it.
    - Every outgoing User-Agent was renamed, including `sources/base.py` `_GITHUB_USER_AGENT` and four in `sources/nixhub.py`, not only `config.py`.
  - `[project.scripts]` has `mcp-nixarchy = "mcp_nixos.server:main"` and `mcp-nixos = "mcp_nixos.server:main"`. Add the comment `# alias, remove after v3.2`.
- `mcp_nixos/__init__.py`: `version("mcp-nixarchy")`, and the docstring says MCP-nixarchy.
- `server.py`: `FastMCP("mcp-nixarchy", …)`.
- `config.py`: `FLAKEHUB_USER_AGENT = f"mcp-nixarchy/{__version__}"`.
- Fix the 2 test references to `mcp-nixos` (`test_env_file_safety.py`, `test_tools.py`) where they assert the server or package name. Leave them if they only run `python -m`.
- Verify: CHECK, then `nix develop -c python -c "import mcp_nixos; print(mcp_nixos.__version__)"` prints `3.1.0`.
- Commit: `feat: rename distribution to mcp-nixarchy (#1)`. Use no `!`: the decision is v3.2.0, and the aliases keep the change non-breaking.

**10. B5: `flake.nix`**
- Rename `mkMcpNixos` → `mkMcpNixarchy`. Set `pname = "mcp-nixarchy"`, `meta.homepage = "https://github.com/olafkfreund/mcp-nixarchy"`, `mainProgram = "mcp-nixarchy"`.
- `packages`: `mcp-nixarchy = mkMcpNixarchy { inherit pkgs; }; mcp-nixos = mcp-nixarchy; default = mcp-nixarchy;`.
- `apps`: `mcp-nixarchy`, with `mcp-nixos` and `default` as aliases.
- `overlays.default = final: _: rec { mcp-nixarchy = mkMcpNixarchy { pkgs = final; }; mcp-nixos = mcp-nixarchy; };`.
- Update the check at lines ~222-244 to reference `mcp-nixarchy`.
- Delete `packages.docker` (257-275), the `build-docker` devshell command (~409), and the `mcp-nixos-website` devshell (~420 to its end).
- Rename the devshell banner and the `run` command to `mcp-nixarchy`.
- `pyproject` `version` is still read by the flake. Check how the flake gets the version and keep that working.
- `.mcp.json`: args become `["run", ".#mcp-nixarchy"]`.
- (Deviation, found in implementation:)
  - Also removed the `docsCommands` list, the `docs-*` commands and `nodejs_20` from the default devshell. They `cd` into `website/`, which step 11 deletes.
  - Kept `lib.mkMcpNixos` as an alias of `lib.mkMcpNixarchy` for one release, like the other aliases.
- Verify:
  - `nix flake check`;
  - `nix build .#mcp-nixarchy && ls result/bin` shows `mcp-nixarchy` and `mcp-nixos`;
  - `nix build .#mcp-nixos` works;
  - `nix flake show` lists no `docker`.
- Trap: building through the `fastmcp4` overlay pulls wheels; the first build takes a few minutes.
- Commit: `build: rename flake outputs to mcp-nixarchy, drop docker and website shells (#1)`.

**11. B6, B7: workflows and website**
- `git rm -r website .github/workflows/publish.yml .github/workflows/deploy-flakehub.yml .github/workflows/deploy-website.yml`.
- `ci.yml`: delete the `docker-build` job (~132-160) and the `website/**` entries in `paths-ignore`/`paths` (9, 21). Remove any `needs:` that references `docker-build`.
- `release-please-config.json`: `"package-name": "mcp-nixarchy"`.
- `release-please.yml`: remove any step that dispatches `publish.yml` or uses PyPI or Docker secrets. Keep the GitHub release.
- Verify: `grep -rn "docker\|pypi\|website\|flakehub" -i .github` shows only intended remainders, and `nix run nixpkgs#actionlint -- .github/workflows/*.yml` is clean.
- (Deviation, found in implementation:)
  - The `ci.yml` smoke test now runs `mcp-nixarchy --help`.
  - The Codecov `slug` points to the fork. It is `fail_ci_if_error: false`, so it is harmless without a token.
  - The stale `/website/` block was removed from `.gitignore`.
  - `.claude/commands/release.md` moves to step 12.
- Commit: `ci: drop registry publishing and website; GitHub releases only (#1)`.

**12. B8: docs**
- `README.md`: rewrite to at most about 120 lines. (Deviation: it came out at 133 lines; the source and env-var tables and three client configs were kept rather than cut.)
  - What it is, and that it is a fork of utensils/mcp-nixos, with credit.
  - The two tools and their sources, including `nixarchy` and `nixarchy-docs`.
  - Install with `nix run github:olafkfreund/mcp-nixarchy` and the overlay snippet.
  - Claude Code, Codex and opencode config, with the key `nixos`.
  - Environment variables: transport, `ELASTICSEARCH_URL`, `MCP_NIXOS_ALLOW_FLAKE_INPUTS`, `MCP_NIXARCHY_OPTIONS`, `MCP_NIXARCHY_DOCS`.
  - The flake-inputs path rule.
  - Development commands.
- `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`:
  - Project name and description.
  - Remove the `website/` and Docker/PyPI/FlakeHub release lines. Release is release-please to GitHub releases.
  - Add the new sources to the architecture and data-source lists, and the new environment variables.
- `.pi/extensions/mcp-nixos.ts`: update user-visible names and descriptions only.
- `.claude/commands/release.md` (added in step 11): rewrite for this fork. The steps are: review the release-please PR, merge it, verify the GitHub release and tag, and check that `nix run github:olafkfreund/mcp-nixarchy/<tag> -- --help` works. Remove PyPI, Docker, GHCR and FlakeHub.
- `LICENSE`: add the line `Copyright (c) 2026 Olaf K. Freund` under the existing copyright.
- Verify: `grep -rn "utensils/mcp-nixos" --exclude-dir=.git . | grep -v RELEASE_NOTES` leaves only credit or upstream links. Run CHECK.
- Commit: `docs: rebrand README and agent docs as mcp-nixarchy (#1)`.

### Part C: nixarchy sources (`feat:` commits)

**13. C1, part 1: `caches.py` `HtmlOptionsCache` (476-509)**
- Move the `parse_html_options` call into `def _load(self) -> list[dict[str, str]]: return parse_html_options(self.url, limit=None)`.
- `get_options` calls `self._load()`.
- Add `class NixarchyOptionsCache(HtmlOptionsCache)`:
  - `__init__` calls `super().__init__(url="", display_name="nixarchy")` and sets `self.origin = ""`.
  - `_load()`:
    1. Resolve the location: `os.environ.get("MCP_NIXARCHY_OPTIONS")`, else `NIXARCHY_OPTIONS_PATH` if `os.path.isfile`, else `NIXARCHY_OPTIONS_URL`.
    2. Read: a URL uses `HTTP.get(timeout=30)` then `raise_for_status()` then `.json()`; a path uses `json.load`.
    3. Set `origin`: `installed (<path>)` for the default path, `custom (<path or url>)` for the env var, `GitHub release <url> (may differ from your installed nixarchy)` for the fallback.
    4. Map each entry to `{"name", "type", "description", "default", "example", "declared_in"}`. `default` and `example` come from `v.get("default", {}).get("text", "")`. `declared_in` is `", ".join(str(d) for d in v.get("declarations", []))`. Every value is a `str`, using `""` when missing. Strip the description.
    5. Wrap errors as `APIError("nixarchy options catalogue not available (<location>): <exc>. It is installed by nixarchy at /etc/nixarchy/options.json.")`.
- `config.py`: add `NIXARCHY_OPTIONS_PATH = "/etc/nixarchy/options.json"`, `NIXARCHY_OPTIONS_URL = "https://github.com/olafkfreund/nixarchy/releases/latest/download/options.json"`, `NIXARCHY_DOCS_PATH = "/etc/nixarchy/docs"`, `NIXARCHY_REPO = "olafkfreund/nixarchy"`.
- Add `nixarchy_options_cache = NixarchyOptionsCache()`.
- Trap: `HtmlOptionsCache.get_options` raises if the list is empty. Keep that behaviour for nixarchy too.
- Verify: CHECK, with the existing HM and darwin tests unchanged and green.
- Commit with step 14.

**14. C1, part 2: `sources/base.py` and the new `sources/nixarchy.py`**
- `base.py:227` `_html_source_cache`: change to a dict lookup over `{"home-manager": home_manager_cache, "darwin": darwin_cache, "nixarchy": nixarchy_options_cache}`.
- `_info_html_options` (259): after the description, add `for label, key in (("Default", "default"), ("Example", "example"), ("Declared in", "declared_in")): if opt.get(key): info.append(f"{label}: {opt[key]}")`.
- `_stats_html_options` (308): if `getattr(cache, "origin", "")`, append `* Source: {cache.origin}`.
- New `sources/nixarchy.py` with:
  - `_search_nixarchy_options(query, limit)` → `_search_html_options(nixarchy_options_cache, …)`;
  - `_info_nixarchy_options(name)`;
  - `_stats_nixarchy_options()`.
- Browse uses the existing `_browse_options("nixarchy", prefix)`.
- Tests in `tests/test_nixarchy.py` (unit):
  - Write a fixture `options.json` to `tmp_path`. Include `programs.nixarchy.enable` (boolean, default false, a declaration), `programs.nixarchy.mcp` and `home-manager.users.<name>.programs.nixarchy.neovim.enable`.
  - Set `MCP_NIXARCHY_OPTIONS`, and reset the cache in a fixture: `nixarchy_options_cache.options = None`.
  - Assert search ranking, the info fields, browse `programs.nixarchy`, and the stats `Source:` line.
  - With a missing path and an unreachable URL (patch `HTTP.get` to raise), assert the error text says "not available".
- Verify: CHECK.
- Commit: `feat: add nixarchy options source (#1)`.

**15. C2: `nixarchy-docs` in `sources/nixarchy.py` and `caches.py`**
- Add `class NixarchyDocsCache` with an `_init_lock`, `pages: dict[str, tuple[str, str]] | None`, and `origin: str`.
- Load:
  - **Directory** (`$MCP_NIXARCHY_DOCS`, else `NIXARCHY_DOCS_PATH` if `isdir`): read `manual/*.md` and `llms.txt` if present. The id is the file stem; `llms.txt` gets the id `llms`.
  - **Otherwise GitHub:** `HTTP.get(f"https://api.github.com/repos/{NIXARCHY_REPO}/contents/docs/manual", timeout=30)`. For each `.md` entry, `HTTP.get(entry["download_url"])`. Also fetch `https://raw.githubusercontent.com/{NIXARCHY_REPO}/main/docs/llms.txt`.
  - The title is the first line starting with `# `, otherwise the id.
  - Raise `APIError` if no pages load.
- `_search_nixarchy_docs(query, limit)`:
  - `terms = query.casefold().split()`.
  - `score = sum(5 * title.casefold().count(t) + body.casefold().count(t) for t in terms)`.
  - Sort by `(-score, id)` and keep the top `limit`.
  - Output per page: `* <id> — <title>`, a snippet of 200 characters around the first hit with newlines collapsed, and the `Source:` origin line on the header.
- `_info_nixarchy_docs(page)`:
  - Normalise the id: strip `manual/`, a leading `docs/`, and `.md`/`.txt`.
  - Return the markdown, truncated to `DEFAULT_LINE_LIMIT` lines with a `... truncated (N more lines)` note.
  - If not found, return the error `NOT_FOUND` with the 5 closest ids (by substring).
- Tests (unit):
  - A fixture directory with 3 pages: search ranks the title hit first; info works with `ai`, `manual/ai.md` and `ai.md`; truncation is applied.
  - A GitHub fallback with `HTTP.get` mocked returns 2 pages.
- Tests (integration): `MCP_NIXARCHY_DOCS` unset and `/etc/nixarchy/docs` absent (patch `os.path.isdir` for that path), then search for "mcp" → the `ai` page is in the results. Mark it `flaky(reruns=3)`.
- Verify: CHECK, plus `pytest -m integration -k nixarchy_docs`.
- Commit: `feat: add nixarchy-docs source for the nixarchy manual (#1)`.

**16. C wiring: `server.py`, `config.py` `KNOWN_SOURCES`, `sources/__init__.py`**
- Add `"nixarchy"` and `"nixarchy-docs"` to `KNOWN_SOURCES`.
- Dispatch in `nix()`:
  - **search:** `nixarchy` → `_search_nixarchy_options`, `nixarchy-docs` → `_search_nixarchy_docs`.
  - **info:** the same pair of handlers.
  - **stats:** `nixarchy` → `_stats_nixarchy_options`. `nixarchy-docs` joins the "Stats not available" list.
  - **browse:** add `nixarchy` to the allowed list. It falls through to `_browse_options(source, query)`.
- Update every "Must be one of" error string and the `source` parameter description.
- Add docstring intents:
  - `"nixarchy option for X" → {"action":"search","source":"nixarchy","query":"X"}`
  - `"browse nixarchy options" → {"action":"browse","source":"nixarchy","query":"programs.nixarchy"}`
  - `"nixarchy manual on X" → {"action":"search","source":"nixarchy-docs","query":"X"}`
  - `"read nixarchy manual page" → {"action":"info","source":"nixarchy-docs","query":"ai"}`
- Add the same intents to the `_SERVER_INSTRUCTIONS` block.
- Export the new functions from `sources/__init__.py` (`__all__`). Add them to the `server.py` re-export list too, to match the existing pattern.
- Tests: one `nix()`-level unit test per new routing branch, plus an unknown-source error test that names both new sources.
- Verify: CHECK.
- Smoke test:

  ```
  nix develop -c env MCP_NIXARCHY_DOCS=/mnt/data/Source-home/GitHub/nixarchy/docs python -c "import asyncio; from mcp_nixos.server import nix; print(asyncio.run(nix(action='search', source='nixarchy-docs', query='mcp')))"
  ```

  The `ai` page should come first.
- Trap: if `nix` is wrapped by FastMCP as a `FunctionTool`, call the underlying function the way existing tests do. Check `tests/test_server.py` for the pattern.
- Commit: `feat: route nixarchy and nixarchy-docs sources through the nix tool (#1)`.

### Part D/E hand-off (session model, not the coder)

**17. Full verification**
- Run CHECK.
- Run `nix develop -c pytest -m integration -q` and record which failures, if any, are pre-existing network flakes. To find out, compare against `main` with `git stash` or a worktree.
- Run `nix flake check` and `nix build .#mcp-nixarchy`.

**18. Review**
- A fresh `opus` agent reviews, given only this plan path and `git diff main...HEAD`.
- Fix its findings, and update this plan for any deviation in the same commit.

**19. PR**
- `git push -u origin feat/1-mcp-nixarchy`.
- `gh pr create --base main` (the fork's main, not upstream).
  - Body: link intent, spec and plan; list the steps the coder did; `Closes #1`.
  - Check that the PR targets `olafkfreund/mcp-nixarchy`. Pass `--repo olafkfreund/mcp-nixarchy`, because `gh` defaults to the parent repo for forks.
- Watch CI.

**20. nixarchy issue**
- In `olafkfreund/nixarchy`, open an issue carrying spec part D (D1–D5), linked to this PR.
- Mention D6 (machine cleanup) to the user as a manual follow-up. No edits.

**21. Upstream (after merge, ask the user first)**
- Cherry-pick the A1–A8 commits onto a branch from `utensils/mcp-nixos` main.
- Open the PRs only after the user confirms. This is outward-facing.

## Tests

- **Per step:** CHECK (ruff, format, mypy, unit). Expect 0 lint or type errors, and the unit test count to be ≥ 378 + new tests.
- **Integration:** `pytest -m integration -k nixarchy_docs` is green. The full integration run has no new failures compared with `main`.
- **Nix:** `nix flake check`, and `nix build .#mcp-nixarchy .#mcp-nixos`, with both binaries present.
- **Smoke:** step 16's command returns the `ai` page first. `result/bin/mcp-nixarchy` starts and responds to `initialize` over stdio:

  ```
  timeout 5 result/bin/mcp-nixarchy < /dev/null
  ```

  It exits cleanly, with no traceback.

## Rollback

- Before merge: delete the branch. `main` is untouched.
- After merge:
  - `git revert` the merge commit, or individual step commits. Each step is one commit; steps 13 and 14 are shared.
  - Release-please would then cut a fix release.
  - Nothing outside this repo depends on the new outputs until the nixarchy issue lands.
  - The `mcp-nixos` aliases keep old consumers working either way.
