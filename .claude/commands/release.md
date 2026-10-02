---
allowed-tools: Bash, Read, Glob, Grep, TodoWrite
description: Review and merge the Release Please release PR, then verify the GitHub release
---

# Release

Releases are managed by Release Please and published as GitHub releases only. There is no PyPI, Docker, GHCR or FlakeHub publishing. Do not edit the version, create a tag, or create a GitHub Release by hand.

## How it works

1. Conventional commits merged to `main` update the open `release: vX.Y.Z` PR.
2. The release PR updates `pyproject.toml`, `.release-please-manifest.json`, and `RELEASE_NOTES.md`.
3. Merging that PR makes Release Please create the matching tag and GitHub Release.
4. `ci.yml` only validates builds.

Version rules:

- `fix:` produces a patch release; `feat:` produces a minor release.
- `fix!:`, `feat!:`, or a `BREAKING CHANGE:` footer produces a major release.
- `ci:`, `docs:`, `test:`, `refactor:`, `build:`, and `chore:` commits are hidden and do not cause a release by themselves.

## Release checklist

### 1. Review the release PR

```bash
gh pr list --repo olafkfreund/mcp-nixarchy --search 'release: in:title is:open' --json number,title,url,headRefName
gh pr view <PR_NUMBER> --repo olafkfreund/mcp-nixarchy --json files,commits,reviews,statusCheckRollup
git log "$(git describe --tags --abbrev=0)..origin/main" --oneline
```

Confirm that:

- the proposed SemVer bump matches every included change;
- `RELEASE_NOTES.md` is complete and calls out breaking changes;
- `pyproject.toml` and `.release-please-manifest.json` contain the same version;
- CI and review are green.

### 2. Merge the release PR

```bash
gh pr merge <PR_NUMBER> --repo olafkfreund/mcp-nixarchy --squash --delete-branch
```

The `Release Please` workflow owns tag creation and the GitHub Release. Never create or move the release tag manually.

### 3. Watch the workflow

```bash
gh run list --repo olafkfreund/mcp-nixarchy --workflow release-please.yml --limit 3
gh run watch <RUN_ID> --repo olafkfreund/mcp-nixarchy
gh run view <RUN_ID> --repo olafkfreund/mcp-nixarchy --log-failed
```

### 4. Verify the release

```bash
VERSION=X.Y.Z

gh release view "v$VERSION" --repo olafkfreund/mcp-nixarchy --json tagName,isDraft,isPrerelease,publishedAt,url,targetCommitish
nix run "github:olafkfreund/mcp-nixarchy/v$VERSION" -- --help
```

Verify that the tag and GitHub Release target the release PR merge commit, and that `nix run` on the tag starts the server.

## Guardrails

- Treat published tags as immutable; do not delete or retarget them to repair a release.
- Do not release from an unmerged branch or a dirty worktree.
- Do not merge a release PR with incomplete notes or a mismatched version.
- Always pass `--repo olafkfreund/mcp-nixarchy`; `gh` defaults to the upstream parent for forks.
