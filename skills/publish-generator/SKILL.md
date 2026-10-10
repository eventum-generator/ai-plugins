---
name: publish-generator
description: Use only when the user asks to submit an Eventum generator to the official catalog (content-packs) or the Eventum Hub - "publish this generator", "open the PRs for these packs". Not for building or reviewing a generator.
---

# Publish a generator

Opens one pull request per reviewed generator in `eventum-generator/content-packs` and, as the user prefers, one per card or per batch of cards in `eventum-generator/docs` (the Eventum Hub). Maintainers merge.

## Before starting

- For every generator: `.content-design/<name>/review.md` has verdict CLEAR, every LOW finding in it is fixed or described in the README, and `python3 <skill dir>/../../scripts/measure.py digest <generator> --previous .content-design/<name>/review-digest.json` shows no change, or changes to `README.md` only; anything else needs `review-generator` first.
- `gh auth status` works. One clone per repository: an existing one the user names, or one made once (`gh repo clone eventum-generator/<repo>`). Without push access, the clone is a fork (`gh repo fork eventum-generator/<repo> --clone`): branches start from `upstream/master` instead of `origin/master`, and PRs target `eventum-generator/<repo>`.
- The skill creates branches, commits and pull requests in public repositories; confirm with the user before the first push.
- `<scripts>` is `<skill dir>/../../scripts`; scripts run with `python3` (`py -3` on Windows).

## content-packs

- A generator is `generators/<slug>/`: `generator.yml`, `README.md`, `templates/`, and as needed `samples/`, `patterns/`, `scripts/`; nothing else, and nothing registered elsewhere. Eventum Studio installs it under the directory name, titled and summarised from the README's first heading and the paragraph under it, regular files only.
- CI on every PR checks each changed generator: structure and README sections, the sample as one JSON object, a one-day batch run (`capture.py one`; every input needs an explicit `start`), a 20-second live run of the shipped configuration with an empty log, gitleaks, and warnings for public IPv4 literals. The catalog fit step makes it pass before pushing.
- PR body: a lead paragraph (source and version, output shape, estate, records per day, curve); `## Modes` (`anomaly_mode: true` with the chain, actor and recurrence; `false` with background overlap); `## Validation` (numbers from `review-report.json`, the verdict with the reviewed digest, and the head digest when the README changed since); `## Limits`.

## Hub card

Card PRs branch from and target `master` of `eventum-generator/docs` (other docs work goes to `develop`). CI reruns prettier and eslint on changed files, the Hub card check (unique slug, file name, registration), `types:check` and the build; the same checks run locally before the push.

- `lib/hub-data/generators/<slug>.ts` exports a `GeneratorMeta` constant named like its neighbours (`application-1c` is `applicationOneC`); `slug` equals the content-packs directory, which the page links to and runs in its quick start. It is imported in `lib/hub-data/index.ts` and appended to the array (array order is display order).
- Fields and allowed values come from `lib/hub-types.ts` and `lib/hub-categories.ts` of the checkout. Hub categories differ from slug prefixes (`proxy-*` and `vpn-*` are web-access, `windows-*` endpoint, identity or network); `originalFormat` is omitted when the event has no native record; `generationModes` is `['background', 'anomaly']` with a chain and omitted without one.
- Shown: `description`, `realismFeatures`, event types, parameters and samples on the page, `eventFormat`, `originalFormat` and the anomaly icon on the grid card, `dataSource` in search; `highlights`, `anomalyChain`, `eventCount` and `templateCount` are stored only, so the chain is also summarised in `description` or `realismFeatures`.
- Content in data terms (no inputs, templates, guards, speed or validation): `generatorId` is the README's `--id`, `eventCount` the rows of its event table, `templateCount` the `.jinja` files, parameters carry the exact `generator.yml` defaults, `sampleOutputs[].json` is the README sample as one JSON document in a `String.raw` literal.
- A file with address-like string literals, versions included (`'13.1.1.18'`), starts with `/* eslint-disable sonarjs/no-hardcoded-ip -- sample values are documentation addresses */`.
- Branch `hub/<slug>` or `hub/<batch-name>`; title `feat(hub): add <Display Name> generator` or `feat(hub): add <N> generators`; body: the content-packs PR per card, what each produces, files and categories, a verification line.

## Process

Git operations on a shared clone run under its slot (`python3 <scripts>/slot.py run --pool git-<repo> -- git ...`), so parallel publishers never collide on its locks. Every branch gets its own worktree next to the clone (`<clone>-worktrees/<branch>`), created with `git worktree add --no-track -b <branch> <path> origin/master` and pushed with `git push -u origin <branch>`.

1. **Catalog fit** - one JSON object per line (ECS JSON, or a native JSON record); the slug is unique in `generators/` of the current `master` and in the files of open PRs (`gh pr list -R eventum-generator/content-packs --state open --json files`); the directory holds only generator files; the README has every section of `../create-generator/references/generator-rules.md`. Fix what does not fit and re-run the digest check.
2. **content-packs PR** - fetch, then a worktree on `feat/<slug>`; copy the generator directory there as `generators/<slug>/` (wherever it lives, the clone's own working tree included) and add only it; commit and title `feat: add <Display Name> generator`; push and open the PR to `master`.
3. **Hub cards** - one docs worktree per card or batch: write each card from its README, register it, then `pnpm install` (the "Ignored build scripts" warning is harmless), `npx prettier --write <cards> lib/hub-data/index.ts`, `npx eslint --max-warnings 0 <cards> lib/hub-data/index.ts`, `pnpm types:check` (types, categories, formats; eslint does not catch them), and the build under the single docs-build slot: `python3 <scripts>/slot.py run --pool docs-build --mem 6144 -- pnpm build` (about 30 s, up to 6 GB, needs network for fonts). A batch shares one worktree, install and build. Open the PR to `master` linking the content-packs PRs.
4. **Report** every PR URL; remove the worktrees (`git worktree remove <path>`).
5. **Feedback** - `../using-content-design/references/feedback.md`.

## Rules

- A generator is published as reviewed; any change beyond the README goes back through review.
- A card says nothing its README does not; a claim the card writer cannot confirm is fixed in the README first.
- No merge, force-push or change to branches other than the ones this skill created.
