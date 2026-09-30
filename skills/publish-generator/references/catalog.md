# Official catalog and Hub

## content-packs

`github.com/eventum-generator/content-packs`, default branch `master`, Apache-2.0, linear history.

- A generator lives in `generators/<slug>/`: `generator.yml`, `README.md`, `templates/`, `samples/`, `patterns/`, optionally `scripts/`; nothing else (no `output/`, no working files, no stray samples at the root). Nothing is registered elsewhere; `config/startup.yml` stays as it is.
- Eventum Studio installs catalog entries: any `generators/<dir>/` with a `generator.yml`, named after the directory; title and summary from the README's first heading and the paragraph under it; regular files only (symlinks and submodules dropped); at most 10,000 files and 512 MiB unpacked.
- The catalog accepts JSON output only (`json` formatter; ECS JSON, or native JSON records).
- One generator per pull request from branch `feat/<slug>`; commit and PR title `feat: add <Display Name> generator`.
- PR body: a lead paragraph (source and version, output shape, estate, records per day, curve); `## Modes` (with a chain: `anomaly_mode: true` with the chain, actor and recurrence, and `false` with background overlap); `## Validation` (numbers from the measurement report and the review verdict with its digest); `## Limits`.

## Hub card (docs)

`github.com/eventum-generator/docs` (Next.js + Fumadocs, static export). Card PRs branch from `master` and target `master`; ordinary docs work goes to `develop`. The repository has no CI: the local checks below are the only gate.

- File `lib/hub-data/generators/<slug>.ts` exporting a `GeneratorMeta` constant named like its neighbours (camelCase of the slug; `application-1c` is `applicationOneC`). `slug` equals the content-packs directory: the page links to `content-packs/tree/master/generators/<slug>` and its quick start runs `--path generators/<slug>/generator.yml --id <generatorId>`.
- Registration: import the constant in `lib/hub-data/index.ts` and append it to the exported array (array order is display order). Registration also creates the page, the sitemap entry and the OG image. A duplicate slug is not detected by any check. `SLUG_CATEGORY_MAP` in `lib/hub-categories.ts` is unused; leave it.
- Fields (`lib/hub-types.ts`, read from the checkout): required `slug`, `displayName`, `category`, `description`, `dataSource`, `format`, `eventFormat`, `eventCount`, `templateCount`, `highlights`, `generatorId`, `eventTypes[] {id, description, frequency, category}`, `realismFeatures`, `parameters[] {name, defaultValue, description}`, `sampleOutputs[] {title, json}`; optional `originalFormat`, `generationModes`, `anomalyChain`.
- `category`: a `CategoryId` of `lib/hub-categories.ts` (application, backup, storage, cloud, database, email, identity, messaging, endpoint, monitoring, network, security, web-access, virtualization); Hub categories differ from slug prefixes (`proxy-*` and `vpn-*` are web-access, `windows-*` endpoint, identity or network).
- `eventFormat`: `'ECS JSON'` or `'JSON'`. `originalFormat`: format of the record in `event.original` (`'Syslog'`, `'CEF'`, `'KV'`, `'XML'`, `'CSV'`, `'JSON'`, `'Plain text'`), omitted when there is none.
- `generationModes`: `['background', 'anomaly']` with a chain; omitted for background only (the page treats a missing value as background).
- Rendered on the page: `description`, `realismFeatures`, event types, parameters, samples and the anomaly icon from `generationModes`. `highlights`, `anomalyChain`, `eventCount` and `templateCount` are stored but not shown, so the chain is also summarised in `description` or `realismFeatures`.
- `sampleOutputs[].json`: one JSON document (a `String.raw` template literal); the page re-indents it, so content is byte-exact and whitespace is not.
- Lint: `sonarjs/no-hardcoded-ip` fails on plain string literals that look like addresses, versions included (`'13.1.1.18'`); then the file starts with `/* eslint-disable sonarjs/no-hardcoded-ip -- sample values are documentation addresses */`.
- Branch `hub/<slug>` (a batch: `hub/<batch-name>`); title `feat(hub): add <Display Name> generator` (a batch: `feat(hub): add <N> generators`); body: the content-packs directory or PR link per card, what each produces, files changed with categories, and a verification line.
- Checks, from the docs checkout: `pnpm install` (once per worktree), `npx prettier --write <cards> lib/hub-data/index.ts`, `npx eslint --max-warnings 0 <cards> lib/hub-data/index.ts`, `pnpm types:check` (about 5 s; categories, formats, field types), `pnpm build` (about 35 s; needs network for fonts; proves every page and OG image renders). eslint does not catch type errors.

## Card content

The card is a compact summary of the generator's README; nothing on it is new.

- `generatorId` (the `--id` in the README usage), `eventCount` (rows of the README event table), `templateCount` (`.jinja` files under `templates/`, macro files included), event types with the README shares, parameters with the exact `generator.yml` defaults, `sampleOutputs` equal to the README sample.
- `description`, `highlights` and `realismFeatures` restate README facts, limits included, in data terms: no inputs, templates, guards, generation speed or validation process.
- A README claim the card writer cannot confirm is fixed in the README first.
