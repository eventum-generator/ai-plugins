---
name: publish-generator
description: Use only when the user asks to share or submit an Eventum generator to the official catalog or the Eventum Hub - "publish this generator", "submit it to content-packs", "add the Hub card", "open the PRs for these packs". Not for building or reviewing a generator.
---

# Publish a generator

Submits reviewed generators to `github.com/eventum-generator/content-packs`, one pull request each, and adds their cards to the Eventum Hub in `github.com/eventum-generator/docs`, one pull request per card or per batch of cards, as the user prefers. Maintainers merge; publishing ends with open pull requests.

## Before starting

- For every generator: `.content-design/<name>/review.md` has verdict CLEAR, and its digest equals `python <skill dir>/../../scripts/measure.py digest <generator>`. A mismatch means the files changed after the review: changes limited to the README proceed, anything else needs `review-generator` first.
- `gh auth status` works. Without push access to a repository, work in a fork (`gh repo fork --clone`).
- The skill creates branches, commits and pull requests in public repositories; confirm with the user before the first push.

## References

- `references/catalog.md` - content-packs layout and PR conventions, Studio constraints, Hub card fields, rendering, registration, checks.

Scripts are at `<skill dir>/../../scripts/`.

## Process

Git operations on a shared clone run under its slot (`python <scripts>/slot.py run --pool git-<repo> -- git ...`), so parallel publishers never collide on its locks; every branch gets its own worktree.

1. **Catalog fit** - JSON output; the slug is unique in `generators/` of the current `master` and in open PRs; the directory holds only generator files; the README has every section of `../create-generator/references/generator-rules.md`. Fix what does not fit and re-run the digest check.
2. **content-packs PR** - fetch, then `git worktree add <path> -b feat/<slug> origin/master`; add `generators/<slug>/` only; commit, push, open the PR to `master` with the body from `references/catalog.md`.
3. **Hub cards** - one docs worktree per card or batch branch from `origin/master`: write each card from its README, register it, run prettier, eslint and `pnpm types:check`, then the build under the single docs-build slot: `python <scripts>/slot.py run --pool docs-build --mem 4096 -- pnpm build`. Open the PR to `master` linking the content-packs PRs.
4. **Report** every PR URL; remove the worktrees.
5. **Feedback** - `../using-content-design/references/feedback.md`.

## Rules

- A generator is published as reviewed; any change beyond the README goes back through review.
- A card says nothing its README does not; its sample equals the README sample.
- No merge, force-push or change to branches other than the ones this skill created.
