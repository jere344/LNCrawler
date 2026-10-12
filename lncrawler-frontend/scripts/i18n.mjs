#!/usr/bin/env node
// Locale maintenance for the lncrawler frontend.
//
// en.json is the single source of truth; every other locale must mirror its
// keys. This tool lets an agent edit ONLY en.json and then push the translated
// values into all locales without ever reading them.
//
//   node scripts/i18n.mjs pending              print the untranslated delta
//   node scripts/i18n.mjs apply <file.json>    write {key:{locale:value}} everywhere
//   node scripts/i18n.mjs normalize            reorder every locale to en.json order
//   node scripts/i18n.mjs check [--strict]     validate structure/placeholders/ICU
//   node scripts/i18n.mjs --self-test          run built-in assertions
//
// No network, no dependencies.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LOCALES_DIR = path.join(ROOT, 'src', 'i18n', 'locales');
const SOURCE = 'en';

// ---------------------------------------------------------------- helpers

const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const localeCodes = () =>
    fs.readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5));
const localePath = (code) => path.join(LOCALES_DIR, `${code}.json`);

function flatten(obj, prefix = '', out = {}) {
    for (const [key, value] of Object.entries(obj)) {
        const full = prefix ? `${prefix}.${key}` : key;
        if (value && typeof value === 'object' && !Array.isArray(value)) flatten(value, full, out);
        else out[full] = value;
    }
    return out;
}

function place(flat, pathKey, root) {
    const parts = pathKey.split('.');
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
        if (typeof node[parts[i]] !== 'object' || node[parts[i]] === null) node[parts[i]] = {};
        node = node[parts[i]];
    }
    node[parts.at(-1)] = flat;
}

// Rebuild a locale's nested object: canonical keys first (en.json order), then
// any extras so nothing is silently dropped.
function rebuild(flat, order) {
    const result = {};
    const seen = new Set();
    for (const key of order) {
        if (key in flat) {
            place(flat[key], key, result);
            seen.add(key);
        }
    }
    for (const key of Object.keys(flat)) {
        if (!seen.has(key)) place(flat[key], key, result);
    }
    return result;
}

function writeLocale(code, obj) {
    fs.writeFileSync(localePath(code), JSON.stringify(obj, null, 2) + '\n');
}

function load() {
    const enFlat = flatten(readJson(localePath(SOURCE)));
    const order = Object.keys(enFlat);
    const locales = {};
    for (const code of localeCodes()) {
        if (code === SOURCE) continue;
        locales[code] = flatten(readJson(localePath(code)));
    }
    return { enFlat, order, locales };
}

const isBlank = (v) => v === undefined || v === null || String(v).trim() === '';

// ICU argument names at depth 0 only (plural/select branch bodies are ignored).
// ponytail: top-level args only; nested args inside branch bodies aren't checked.
function icuArgs(str) {
    const args = [];
    let depth = 0;
    for (let i = 0; i < str.length; i++) {
        if (str[i] === '{') {
            if (depth === 0) {
                const m = /^\{\s*([A-Za-z0-9_]+)/.exec(str.slice(i));
                if (m) args.push(m[1]);
            }
            depth++;
        } else if (str[i] === '}') {
            depth = Math.max(0, depth - 1);
        }
    }
    return args.sort();
}

const hasPlural = (str) => /,\s*(?:plural|select|selectordinal)\b/.test(str);
const pluralHasOther = (str) => /\bother\s*\{/.test(str);

function argsMatch(a, b) {
    const A = icuArgs(a);
    const B = icuArgs(b);
    return A.length === B.length && A.every((x, i) => x === B[i]);
}

// Validate one translated string against its English source. Returns an error
// string, or null when valid.
function validateValue(key, enValue, value, locale) {
    if (isBlank(value)) return `${locale}:${key}: empty value`;
    if (typeof value !== 'string') return `${locale}:${key}: value must be a string`;
    if (typeof enValue === 'string') {
        if (!argsMatch(enValue, value))
            return `${locale}:${key}: placeholders differ — en=${JSON.stringify(icuArgs(enValue))} got=${JSON.stringify(icuArgs(value))}`;
        if (hasPlural(value) && !pluralHasOther(value))
            return `${locale}:${key}: ICU plural missing an "other" branch`;
    }
    return null;
}

// ---------------------------------------------------------------- commands

function cmdPending() {
    const { enFlat, locales } = load();
    const needed = {};
    for (const flat of Object.values(locales)) {
        for (const [key, value] of Object.entries(enFlat)) {
            if (isBlank(flat[key]) && !(key in needed)) needed[key] = value;
        }
    }
    const count = Object.keys(needed).length;
    process.stderr.write(count === 0 ? 'i18n: all locales are complete\n' : `i18n: ${count} key(s) need translation\n`);
    process.stdout.write(JSON.stringify(needed, null, 2) + '\n');
}

function cmdApply(args) {
    const file = args.find((a) => !a.startsWith('--'));
    const force = args.includes('--force');
    const dryRun = args.includes('--dry-run');
    if (!file) return fail('usage: i18n.mjs apply <file.json> [--force] [--dry-run]');

    const { enFlat, order, locales } = load();
    let input;
    try {
        input = readJson(path.resolve(process.cwd(), file));
    } catch (e) {
        return fail(`cannot read ${file}: ${e.message}`);
    }
    if (!input || typeof input !== 'object' || Array.isArray(input))
        return fail('input must be an object: { "some.key": { "fr": "...", "de": "..." } }');

    const errors = [];
    let written = 0;
    let skipped = 0;
    const touched = new Set();

    for (const [key, byLocale] of Object.entries(input)) {
        if (!(key in enFlat)) {
            errors.push(`${key}: not present in ${SOURCE}.json`);
            continue;
        }
        if (!byLocale || typeof byLocale !== 'object' || Array.isArray(byLocale)) {
            errors.push(`${key}: value must be an object of { locale: string }`);
            continue;
        }
        for (const [locale, value] of Object.entries(byLocale)) {
            if (!(locale in locales)) {
                errors.push(`${key}: unknown locale "${locale}"`);
                continue;
            }
            const err = validateValue(key, enFlat[key], value, locale);
            if (err) {
                errors.push(err);
                continue;
            }
            if (!force && !isBlank(locales[locale][key])) {
                skipped++;
                continue;
            }
            locales[locale][key] = value;
            touched.add(locale);
            written++;
        }
    }

    if (errors.length) {
        fail(`i18n: ${errors.length} invalid entr${errors.length === 1 ? 'y' : 'ies'}, nothing written:\n  ` + errors.join('\n  '));
        return;
    }
    if (dryRun) {
        process.stdout.write(`i18n: dry run — would write ${written} value(s) across ${touched.size} locale(s), skip ${skipped} existing\n`);
        return;
    }
    for (const code of touched) writeLocale(code, rebuild(locales[code], order));
    process.stdout.write(`i18n: wrote ${written} value(s) across ${touched.size} locale(s), skipped ${skipped} existing\n`);
}

function cmdNormalize() {
    const { order, locales } = load();
    let changed = 0;
    for (const [code, flat] of Object.entries(locales)) {
        const next = JSON.stringify(rebuild(flat, order), null, 2) + '\n';
        if (fs.readFileSync(localePath(code), 'utf8') !== next) {
            fs.writeFileSync(localePath(code), next);
            changed++;
        }
    }
    process.stdout.write(`i18n: normalized ${changed} locale(s) to ${SOURCE}.json order\n`);
}

function cmdCheck(args) {
    const strict = args.includes('--strict');
    const { enFlat, locales } = load();
    const errors = [];
    const warnings = [];

    for (const [code, flat] of Object.entries(locales)) {
        for (const [key, value] of Object.entries(enFlat)) {
            if (isBlank(flat[key])) warnings.push(`${code}:${key}: missing`);
            else if (typeof flat[key] === 'string') {
                const err = validateValue(key, value, flat[key], code);
                if (err) errors.push(err);
            }
        }
        for (const key of Object.keys(flat)) {
            if (!(key in enFlat)) errors.push(`${code}:${key}: extra key not in ${SOURCE}.json`);
        }
    }

    for (const w of warnings) process.stderr.write(`warn  ${w}\n`);
    for (const e of errors) process.stderr.write(`error ${e}\n`);

    const hard = errors.length || (strict && warnings.length);
    process.stdout.write(
        `i18n: ${errors.length} error(s), ${warnings.length} warning(s)${strict ? ' (strict)' : ''}\n`
    );
    return hard;
}

function fail(message) {
    process.stderr.write(message + '\n');
    process.exitCode = 1;
}

// ---------------------------------------------------------------- self-test

function selfTest() {
    const assert = (cond, msg) => {
        if (!cond) throw new Error('self-test failed: ' + msg);
    };
    // flatten / rebuild roundtrip preserves values and en order
    const en = { b: { y: '1', z: '2' }, a: '3' };
    const flat = flatten(en);
    assert(JSON.stringify(Object.keys(flat)) === JSON.stringify(['b.y', 'b.z', 'a']), 'flatten order');
    const back = rebuild(flat, Object.keys(flat));
    assert(JSON.stringify(back) === JSON.stringify(en), 'rebuild roundtrip');
    // rebuild reorders to the given order
    const reordered = rebuild({ a: '3', 'b.y': '1', 'b.z': '2' }, ['b.y', 'b.z', 'a']);
    assert(Object.keys(reordered)[0] === 'b', 'rebuild reorders groups');

    // ICU argument extraction: only depth-0 args
    assert(JSON.stringify(icuArgs('{count, plural, one {# item} other {# items}}')) === JSON.stringify(['count']), 'icu plural');
    assert(JSON.stringify(icuArgs('{n} of {total}')) === JSON.stringify(['n', 'total']), 'icu multiple');
    assert(JSON.stringify(icuArgs('parsed, {selected} selected')) === JSON.stringify(['selected']), 'icu after plural');

    // validation
    assert(validateValue('k', '{count} books', '{count} livres', 'fr') === null, 'valid passes');
    assert(validateValue('k', '{count} books', 'livres', 'fr') !== null, 'dropped placeholder fails');
    assert(validateValue('k', '{count, plural, one {# x} other {# y}}', '{count, plural, one {# x}}', 'fr') !== null, 'missing other fails');
    assert(validateValue('k', 'hi', '', 'fr') !== null, 'empty fails');

    process.stdout.write('i18n: self-test passed\n');
}

// ---------------------------------------------------------------- entry

const HELP = `Locale maintenance — see scripts/i18n.mjs header.

  pending                 print { "key": "english value" } for keys missing somewhere
  apply <file> [--force]  write { "key": { "fr": "...", ... } }; fills blanks only
                          unless --force; --dry-run validates without writing
  normalize               reorder every locale to en.json's key order
  check [--strict]        validate structure/placeholders/ICU (--strict fails on gaps)
  --self-test             run built-in assertions
`;

function main() {
    const [command, ...args] = process.argv.slice(2);
    switch (command) {
        case 'pending':
            return cmdPending();
        case 'apply':
            return cmdApply(args);
        case 'normalize':
            return cmdNormalize();
        case 'check':
            if (cmdCheck(args)) process.exitCode = 1;
            return;
        case '--self-test':
            return selfTest();
        case '--help':
        case undefined:
            return void process.stdout.write(HELP);
        default:
            fail(`unknown command "${command}"\n\n${HELP}`);
    }
}

main();
