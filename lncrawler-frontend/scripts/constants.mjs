#!/usr/bin/env node
// Shared constants for the lncrawler frontend.
//
// The backend owns lncrawler-api/lncrawler_api/shared_constants.json (language
// codes, RTL languages, novel sort keys). This tool turns it into
// src/generated/sharedConstants.ts, which is committed so that the Docker build
// (which only sees this directory) can compile it.
//
//   node scripts/constants.mjs sync     regenerate src/generated/sharedConstants.ts
//   node scripts/constants.mjs check    fail if the generated file is out of date
//
// When the backend JSON is absent (e.g. inside the frontend Docker build, where
// only this directory is copied), check prints a notice and exits 0.
// No network, no dependencies.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE = path.resolve(ROOT, '..', 'lncrawler-api', 'lncrawler_api', 'shared_constants.json');
const TARGET = path.join(ROOT, 'src', 'generated', 'sharedConstants.ts');

const quote = (value) => `'${value.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

function readSource() {
    const data = JSON.parse(fs.readFileSync(SOURCE, 'utf8'));
    for (const key of ['languages', 'rtl_languages', 'novel_sorts']) {
        if (!Array.isArray(data[key]) || data[key].some((v) => typeof v !== 'string' || !v)) {
            throw new Error(`shared_constants.json: "${key}" must be a list of non-empty strings`);
        }
    }
    for (const code of data.rtl_languages) {
        if (!data.languages.includes(code)) {
            throw new Error(`shared_constants.json: RTL code "${code}" is not in "languages"`);
        }
    }
    return data;
}

function render(data) {
    const list = (values) => `[\n${values.map((v) => `    ${quote(v)},`).join('\n')}\n]`;
    return [
        '// generated — do not edit, run npm run constants:sync',
        '// Source: lncrawler-api/lncrawler_api/shared_constants.json',
        '',
        `export const LANGUAGE_CODES = ${list(data.languages)} as const;`,
        'export type LanguageCode = typeof LANGUAGE_CODES[number];',
        '',
        `export const RTL_LANGUAGES = ${list(data.rtl_languages)} as const;`,
        '',
        `export const NOVEL_SORTS = ${list(data.novel_sorts)} as const;`,
        'export type NovelSort = typeof NOVEL_SORTS[number];',
        '',
    ].join('\n');
}

function cmdSync() {
    const content = render(readSource());
    fs.mkdirSync(path.dirname(TARGET), { recursive: true });
    fs.writeFileSync(TARGET, content);
    process.stdout.write(`constants: wrote ${path.relative(ROOT, TARGET)}\n`);
}

function cmdCheck() {
    if (!fs.existsSync(SOURCE)) {
        process.stdout.write('constants: backend shared_constants.json not found, skipping check\n');
        return;
    }
    const expected = render(readSource());
    const actual = fs.existsSync(TARGET) ? fs.readFileSync(TARGET, 'utf8') : null;
    if (actual !== expected) {
        process.stderr.write(`constants: ${path.relative(ROOT, TARGET)} is out of date, run npm run constants:sync\n`);
        process.exitCode = 1;
        return;
    }
    process.stdout.write('constants: up to date\n');
}

function main() {
    const [command] = process.argv.slice(2);
    switch (command) {
        case 'sync':
            return cmdSync();
        case 'check':
            return cmdCheck();
        default:
            process.stderr.write('usage: node scripts/constants.mjs <sync|check>\n');
            process.exitCode = 1;
    }
}

main();
