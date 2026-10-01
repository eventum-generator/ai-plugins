---
name: publish-generator
description: Use only when the user asks to share or submit an Eventum generator to the official catalog or the Eventum Hub - "publish this generator", "submit it to content-packs", "add the Hub card", "open the PRs for these packs". Not for building or reviewing a generator.
---

# Publish a generator

Submits reviewed generators to `github.com/eventum-generator/content-packs`, one pull request each, and adds their cards to the Eventum Hub in `github.com/eventum-generator/docs`, one pull request per card or per batch of cards, as the user prefers. Maintainers merge; publishing ends with open pull requests.

## Before starting

- For every generator: `.content-design/<name>/review.md` has verdict CLEAR, every LOW finding in it is fixed or described in the README, and `python3 <skill dir>/../../scripts/measure.py digest <generator> --previous .content-design/<name>/review-digest.json` shows no change, or changes to `README.md` only; anything else needs `review-generator` first.
- `gh auth status` works. One clone per repository, made once (`gh repo clone eventum-generator/<repo>`) or reused. Without push access, the clone is a fork (`gh repo fork eventum-generator/<repo> --clone`): branches start from `upstream/master` instead of `origin/master`, and PRs target `eventum-generator/<repo>`.
- The skill creates branches, commits and pull requests in public repositories; confirm with the user before the first push.

## References

- `references/catalog.md` - content-packs layout and PR conventions, Studio constraints, Hub card fields, rendering, registration, checks.

`<scripts>` is `<skill dir>/../../scripts`; scripts run with `python3` (`py -3` on Windows).

## Process

Git operations on a shared clone run under its slot (`python3 <scripts>/slot.py run --pool git-<repo> -- git ...`), so parallel publishers never collide on its locks. Every branch gets its own worktree next to the clone (`<clone>-worktrees/<branch>`), created with `git worktree add --no-track -b <branch> <path> origin/master` and pushed with `git push -u origin <branch>`.

1. **Catalog fit** - JSON output; the slug is unique in `generators/` of the current `master` and in the files of open PRs (`gh pr list -R eventum-generator/content-packs --state open --json files`); the directory holds only generator files; the README has every section of `../create-generator/references/generator-rules.md`. Fix what does not fit and re-run the digest check.
2. **content-packs PR** - fetch, then a worktree on `feat/<slug>` as above; add `generators/<slug>/` only; commit, push, open the PR to `master` with the body from `references/catalog.md`.
3. **Hub cards** - one docs worktree per card or batch branch from `origin/master`: write each card from its README, register it, run prettier, eslint and `pnpm types:check`, then the build under the single docs-build slot: `python3 <scripts>/slot.py run --pool docs-build --mem 6144 -- pnpm build`. A batch of cards shares one worktree, one install and one build. Open the PR to `master` linking the content-packs PRs.
4. **Report** every PR URL; remove the worktrees (`git worktree remove <path>`).
5. **Feedback** - `../using-content-design/references/feedback.md`.

## Rules

- A generator is published as reviewed; any change beyond the README goes back through review.
- A card says nothing its README does not; its sample equals the README sample.
- No merge, force-push or change to branches other than the ones this skill created.
