---
name: publish-generator
description: Use only when the user asks to share or submit an Eventum generator to the official catalog or the Eventum Hub - "publish this generator", "submit it to content-packs", "add the Hub card", "open the PRs for the pack". Not for building or reviewing a generator.
---

# Publish a generator

Submits a reviewed generator to `github.com/eventum-generator/content-packs` and adds its card to the Eventum Hub in `github.com/eventum-generator/docs`. Maintainers merge; publishing ends with two open pull requests.

## Before starting

- `.content-design/<name>/review.md` has verdict CLEAR, and its digest equals `python <skill dir>/../../scripts/chain_check.py digest <generator dir>`. A mismatch means the files changed after the review: changes limited to the README proceed, anything else needs `review-generator` first.
- `gh auth status` works. Without push access to a repository, work in a fork (`gh repo fork --clone`) and open the pull request from it.
- The skill creates branches, commits and pull requests in public repositories; confirm with the user before the first push.

## References

- `references/catalog.md` - content-packs layout and PR conventions, Hub card structure, registration, checks, and what a card may say.

## Process

1. **Catalog fit** - the slug is unique in `generators/` of the current `master` and in open PRs; the directory holds only generator files; the shipped `generator.yml` writes to a local file and runs without parameters or secrets; the README has every section of `../create-generator/references/generator-rules.md`. Fix what does not fit and re-run the digest check.
2. **content-packs PR** - branch `feat/<slug>` from the current `master`, add `generators/<slug>/` only, commit, push, open the PR to `master` with the body from `references/catalog.md`.
3. **Hub card** - in a docs checkout on a branch from the current `master`: write the card from the README, register it, run prettier, eslint and `pnpm build`; open the PR to `master` and link the content-packs PR in its body.
4. **Report** both PR URLs.

## Rules

- The generator is published as reviewed; any change beyond the README goes back through review.
- The card says nothing the README does not; the sample is byte-exact.
- No merge, force-push or change to branches other than the ones this skill created.
