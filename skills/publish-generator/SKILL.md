---
name: publish-generator
description: Use only when the user asks to submit an Eventum generator to the official catalog (content-packs) or the Eventum Hub - "publish this generator", "open the PRs for these packs". Not for building or reviewing a generator.
---

# Publish a generator

Submits reviewed generators to `github.com/eventum-generator/content-packs`, one pull request each, and adds their cards to the Eventum Hub in `github.com/eventum-generator/docs`, one pull request per card or per batch of cards, as the user prefers. Maintainers merge; publishing ends with open pull requests.

## Before starting

- For every generator: `.content-design/<name>/review.md` has verdict CLEAR, every LOW finding in it is fixed or described in the README, and `python3 <skill dir>/../../scripts/measure.py digest <generator> --previous .content-design/<name>/review-digest.json` shows no change, or changes to `README.md` only; anything else needs `review-generator` first.
- `gh auth status` works. One clone per repository: an existing one the user names, or one made once (`gh repo clone eventum-generator/<repo>`). Without push access, the clone is a fork (`gh repo fork eventum-generator/<repo> --clone`): branches start from `upstream/master` instead of `origin/master`, and PRs target `eventum-generator/<repo>`.
- The skill creates branches, commits and pull requests in public repositories; confirm with the user before the first push.
- `<scripts>` is `<skill dir>/../../scripts`; scripts run with `python3` (`py -3` on Windows).

## content-packs

Default branch `master`, Apache-2.0, linear history.

- A generator lives in `generators/<slug>/`: `generator.yml`, `README.md`, `templates/`, and as needed `samples/`, `patterns/`, `scripts/`; nothing else (no `output/`, working files or stray samples). Nothing is registered elsewhere; `config/startup.yml` stays as it is.
- Eventum Studio installs any `generators/<dir>/` with a `generator.yml`, named after the directory, titled and summarised from the README's first heading and the paragraph under it; regular files only (symlinks and submodules dropped), at most 10,000 files and 512 MiB unpacked.
- The catalog takes one JSON object per line: ECS JSON (`json` formatter) or a native JSON record (`plain` formatter when its compact form must be kept).
- PR body: a lead paragraph (source and version, output shape, estate, records per day, curve); `## Modes` (with a chain: `anomaly_mode: true` with the chain, actor and recurrence, and `false` with background overlap); `## Validation` (numbers from `review-report.json`, the verdict with the reviewed digest, and the head digest when the README changed since); `## Limits`.

## Hub card

`github.com/eventum-generator/docs` (Next.js + Fumadocs, static export). Card PRs branch from and target `master`; other docs work goes to `develop`. There is no CI: the local checks are the only gate.

- File `lib/hub-data/generators/<slug>.ts` exporting a `GeneratorMeta` constant named like its neighbours (camelCase of the slug; `application-1c` is `applicationOneC`). `slug` equals the content-packs directory: the page links to `content-packs/tree/master/generators/<slug>` and its quick start runs `--path generators/<slug>/generator.yml --id <generatorId>`.
- Registration: import the constant in `lib/hub-data/index.ts` and append it to the exported array (array order is display order); this also creates the page, the sitemap entry and the OG image. No check detects a duplicate slug. `SLUG_CATEGORY_MAP` in `lib/hub-categories.ts` is unused; leave it.
- Fields come from `lib/hub-types.ts` and categories from `lib/hub-categories.ts` of the checkout; Hub categories differ from slug prefixes (`proxy-*` and `vpn-*` are web-access, `windows-*` endpoint, identity or network).
- `eventFormat`: `'ECS JSON'` or `'JSON'`. `originalFormat`: the format in `event.original` (`'Syslog'`, `'CEF'`, `'KV'`, `'XML'`, `'CSV'`, `'JSON'`, `'Plain text'`), omitted when there is none. `generationModes`: `['background', 'anomaly']` with a chain, omitted for background only.
- Rendered: `description`, `realismFeatures`, event types, parameters and samples on the page; `eventFormat`, `originalFormat` and the anomaly icon on the grid card; `dataSource` feeds the search. `highlights`, `anomalyChain`, `eventCount` and `templateCount` are not shown, so the chain is also summarised in `description` or `realismFeatures`.
- Content, all from the README in data terms (no inputs, templates, guards, speed or validation): `generatorId` (the README's `--id`), `eventCount` (rows of the event table), `templateCount` (`.jinja` files, macros included), event types with the README shares, parameters with the exact `generator.yml` defaults, `sampleOutputs[].json` equal to the README sample as one JSON document (a `String.raw` literal; the page re-indents it). A claim the card writer cannot confirm is fixed in the README first.
- Lint: `sonarjs/no-hardcoded-ip` fails on string literals that look like addresses, versions included (`'13.1.1.18'`); such a file starts with `/* eslint-disable sonarjs/no-hardcoded-ip -- sample values are documentation addresses */`.
- Branch `hub/<slug>` (a batch: `hub/<batch-name>`); title `feat(hub): add <Display Name> generator` (a batch: `feat(hub): add <N> generators`); body: the content-packs PR per card, what each produces, files changed with categories, a verification line.

## Process

Git operations on a shared clone run under its slot (`python3 <scripts>/slot.py run --pool git-<repo> -- git ...`), so parallel publishers never collide on its locks. Every branch gets its own worktree next to the clone (`<clone>-worktrees/<branch>`), created with `git worktree add --no-track -b <branch> <path> origin/master` and pushed with `git push -u origin <branch>`.

1. **Catalog fit** - JSON output; the slug is unique in `generators/` of the current `master` and in the files of open PRs (`gh pr list -R eventum-generator/content-packs --state open --json files`); the directory holds only generator files; the README has every section of `../create-generator/references/generator-rules.md`. Fix what does not fit and re-run the digest check.
2. **content-packs PR** - fetch, then a worktree on `feat/<slug>`; copy the generator directory there as `generators/<slug>/` (wherever it lives, the clone's own working tree included) and add only it; commit and title `feat: add <Display Name> generator`; push and open the PR to `master`.
3. **Hub cards** - one docs worktree per card or batch: write each card from its README, register it, then `pnpm install` (the "Ignored build scripts" warning is harmless), `npx prettier --write <cards> lib/hub-data/index.ts`, `npx eslint --max-warnings 0 <cards> lib/hub-data/index.ts`, `pnpm types:check` (types, categories, formats; eslint does not catch them), and the build under the single docs-build slot: `python3 <scripts>/slot.py run --pool docs-build --mem 6144 -- pnpm build` (about 30 s, up to 6 GB, needs network for fonts). A batch shares one worktree, install and build. Open the PR to `master` linking the content-packs PRs.
4. **Report** every PR URL; remove the worktrees (`git worktree remove <path>`).
5. **Feedback** - `../using-content-design/references/feedback.md`.

## Rules

- A generator is published as reviewed; any change beyond the README goes back through review.
- A card says nothing its README does not; its sample equals the README sample.
- No merge, force-push or change to branches other than the ones this skill created.
