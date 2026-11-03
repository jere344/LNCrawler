// patch_server.mjs - breathing pauses between lines in Castwright's chapter render.
//
// Run at image build time against the pinned, built Castwright server:
//
//     node patch_server.mjs [dist]
//
// Default dist: /app/server/dist (files patched in place).
// Castwright concatenates the sentence clips with no gap, so a chapter plays as one
// breathless run. This adds silence after each clip except the last: a paragraph pause
// when the sentence text ends with "\n" (the audiobook worker marks paragraph ends that
// way; normaliseForTts trims it before TTS), a sentence pause after . ! ? …, and a short
// clause pause otherwise. The lengths come from CW_PAUSE_PARAGRAPH_S, CW_PAUSE_SENTENCE_S
// and CW_PAUSE_CLAUSE_S. Segment times exclude the gap, so a segment still spans its
// own speech. The analysis cache's inline-emotion pass trims the text, so it is patched
// to keep the trailing "\n".
// Every anchor must match exactly once. Any other count (0 = drifted, 2+ = ambiguous)
// exits 1 so the image build fails loudly, and so does a file that is already patched.
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const DEFAULT_DIST = '/app/server/dist';

// file -> [label, anchor, replacement]. Anchors are copied verbatim from the build of 3a52b28.
const PATCHES = {
  'tts/synthesise-chapter.js': [
    [
      'concat: pause after each group',
      '        runningBytes += pcmForGroup.length;\n' +
        '        const endSec = pcmDurationSec(runningBytes, sampleRate);\n',
      '        runningBytes += pcmForGroup.length;\n' +
        '        const endSec = pcmDurationSec(runningBytes, sampleRate);\n' +
        '        const lncPause = lncPauseAfterSec(group, groups[groups.indexOf(group) + 1]);\n' +
        '        if (lncPause > 0) {\n' +
        '            const lncGap = buildSilencePcm16(sampleRate, lncPause);\n' +
        '            chunks.push(lncGap);\n' +
        '            runningBytes += lncGap.length;\n' +
        '        }\n',
    ],
    [
      'helper: lncPauseAfterSec',
      'function buildSilencePcm16(sampleRate, seconds) {\n',
      'function lncPauseSec(name, fallback) {\n' +
        '    const value = Number.parseFloat(process.env[name] ?? \'\');\n' +
        '    return Number.isFinite(value) && value >= 0 && value <= 5 ? value : fallback;\n' +
        '}\n' +
        'const LNC_PAUSE_PARAGRAPH_SEC = lncPauseSec(\'CW_PAUSE_PARAGRAPH_S\', 0.6);\n' +
        'const LNC_PAUSE_SENTENCE_SEC = lncPauseSec(\'CW_PAUSE_SENTENCE_S\', 0.3);\n' +
        'const LNC_PAUSE_CLAUSE_SEC = lncPauseSec(\'CW_PAUSE_CLAUSE_S\', 0.12);\n' +
        '/** lncrawler: the silence after a group, by how its text ends. None after the last group. */\n' +
        'function lncPauseAfterSec(group, next) {\n' +
        '    if (!next)\n' +
        '        return 0;\n' +
        '    const raw = typeof group.text === \'string\' ? group.text : \'\';\n' +
        '    if (/\\n\\s*$/.test(raw))\n' +
        '        return LNC_PAUSE_PARAGRAPH_SEC;\n' +
        '    const end = raw.trim().replace(/[\\u201D\\u2019"\'\\u00BB\\u203A\\u300D\\u300F)\\]]+$/u, \'\');\n' +
        '    return /[.!?\\u2026\\u3002\\uFF01\\uFF1F]$/u.test(end) ? LNC_PAUSE_SENTENCE_SEC : LNC_PAUSE_CLAUSE_SEC;\n' +
        '}\n' +
        'function buildSilencePcm16(sampleRate, seconds) {\n',
    ],
  ],
  'store/analysis-cache.js': [
    [
      'cache: keep the paragraph mark',
      '            const { text, emotion } = extractInlineEmotion(s.text, s.emotion);\n',
      '            const { text: lncText, emotion } = extractInlineEmotion(s.text, s.emotion);\n' +
        '            // lncrawler: a trailing "\\n" marks a paragraph end for the pause after it.\n' +
        '            const text = /\\n\\s*$/.test(s.text) && !/\\n\\s*$/.test(lncText) ? lncText + \'\\n\' : lncText;\n',
    ],
  ],
};

const dist = process.argv[2] ?? DEFAULT_DIST;
let count = 0;
for (const [file, patches] of Object.entries(PATCHES)) {
  const path = join(dist, file);
  let source = readFileSync(path, 'utf8');
  // Each replacement keeps its anchor or its marker, so a second run would match again.
  if (source.includes('lncrawler:') || source.includes('lncPauseAfterSec')) {
    console.error(`patch_server: ${path} is already patched`);
    process.exit(1);
  }
  for (const [label, anchor, replacement] of patches) {
    const found = source.split(anchor).length - 1;
    if (found !== 1) {
      console.error(`patch_server: ${file}: ${label}: anchor found ${found} times, expected 1`);
      process.exit(1);
    }
    source = source.replace(anchor, () => replacement);
    count += 1;
  }
  writeFileSync(path, source);
}
console.log(`patch_server: ${count} patches applied under ${dist}`);
