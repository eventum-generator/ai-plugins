# Official catalog and Hub

## content-packs

`github.com/eventum-generator/content-packs`, default branch `master`, Apache-2.0.

- A generator lives in `generators/<category>-<source>/`: `generator.yml`, `README.md`, `templates/`, `samples/`, `patterns/`, optionally `scripts/`. No `output/`, no working files.
- `<category>` is one already used in `generators/` when one fits.
- Nothing else is registered: `config/startup.yml` stays as it is.
- One generator per pull request; branch `feat/<slug>`; commit and PR title `feat: add <Display Name> generator (<slug>)`.
- The PR body: what the source is and the output shape; event types with shares; the anomaly chain and recurrence, when there is one; validation from the review (verdict, one record per timestamp, and with a chain the chains per mode and recurrence gaps); limits.

## Hub card (docs)

`github.com/eventum-generator/docs`, Next.js + Fumadocs; Hub cards target `master`.

- The card is `lib/hub-data/generators/<slug>.ts` exporting a `GeneratorMeta` constant (camelCase of the slug); the field set is the one in `lib/hub-types.ts` of the checkout - read it rather than assuming.
- Registration: import the constant in `lib/hub-data/index.ts` and add it to the exported array. A card that is not registered is not shown.
- `category` is a `CategoryId` from `lib/hub-categories.ts` - Hub categories differ from slug prefixes; use an existing one.
- `generationModes: ['background', 'anomaly']` and `anomalyChain` (a short description) when the type has them.
- `eventFormat` is the structure of the generated event (`'ECS JSON'` or `'JSON'`); `originalFormat` is the format of the native record in `event.original` (`'Syslog'`, `'CEF'`, `'KV'`, `'XML'`, `'CSV'`, `'JSON'`, `'Plain text'`), omitted when the event carries none. The allowed values are the `EventFormat` and `OriginalFormat` types in `lib/hub-types.ts`.
- Style: the neighbouring cards in `lib/hub-data/generators/`; a sample containing hard-coded addresses keeps the file-level `sonarjs/no-hardcoded-ip` disable comment other cards use.
- Checks: `pnpm install` once, then `npx prettier --write <card>`, `npx eslint --max-warnings 0 <card>`, `pnpm build`.

## Card content

The card is a compact summary of the generator's README; nothing on it is new.

- `slug`, `generatorId` (the `--id` in the README usage), `eventCount` (rows of the README event table), `templateCount` (real `.jinja` files), event types with the README shares, parameters with the exact `generator.yml` defaults, `sampleOutputs` byte-exact to the README sample (a `String.raw` template literal).
- `description`, `highlights`, `realismFeatures` and `anomalyChain` restate README facts, limits included, in data terms: no inputs, templates, guards, generation speed or validation process.
- A README claim the card writer cannot confirm is fixed in the README first.
