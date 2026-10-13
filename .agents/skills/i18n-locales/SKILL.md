---
name: i18n-locales
description: Use whenever adding, changing, or translating user-facing text, or touching src/i18n/locales/*.json in the lncrawler frontend.
---

# Locale workflow (lncrawler-frontend)

`en.json` is the ONLY locale file you edit by hand. The other 19 locales mirror
its keys; never read or hand-edit them.

1. Add/edit keys in `src/i18n/locales/en.json`.
2. `npm run i18n:pending` — prints the untranslated delta as `{ "key": "english value" }`.
3. Translate that delta into the other locales and write it to `/tmp/i18n-batch.json`:
   `{ "some.key": { "fr": "…", "de": "…", "ja": "…" } }`.
   Preserve ICU plural syntax and every `{placeholder}`.
4. `npm run i18n:apply /tmp/i18n-batch.json` — writes every locale at the correct path.
5. `npm run i18n:check` — validates structure, placeholders and ICU.

`npm run lint` runs `i18n:check` first. `npm run i18n:normalize` reorders all
locales to `en.json` order (only needed if files drifted).
