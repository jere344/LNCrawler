/**
 * Curated catalog of the HD (neural) voices that run in the reader's browser.
 *
 * - Piper voices come from the official rhasspy/piper-voices repository on
 *   Hugging Face. Only single-speaker, medium/high quality voices whose
 *   phonemes come from espeak are listed: the browser phonemizer is espeak
 *   only, so Japanese (OpenJTalk) and Thai voices can't run here.
 * - Kokoro is a single ~90 MB model with many English voices; its quality is
 *   the best available in the browser, but it is slower on weak devices.
 *
 * - Supertonic 3 is one ~400 MB model (OpenRAIL-M) reading 31 languages
 *   straight from text (no phonemizer), with 10 preset voices shared by all
 *   languages. The most natural outside English, but heavier to run; the
 *   project is archived, so the weights are frozen.
 *
 * Neural voice ids are prefixed by their engine: `piper:<id>`, `kokoro:<id>`,
 * `supertonic:<lang>:<style>` (the language is part of the id because the
 * same style reads every language).
 */

export type NeuralEngine = 'supertonic' | 'piper' | 'kokoro';
export type KokoroDevice = 'wasm' | 'webgpu';
export type SupertonicDevice = 'auto' | 'wasm' | 'webgpu';

/** Engine options that change how (not which) a voice is generated. */
export interface NeuralOptions {
  kokoroDevice: KokoroDevice;
  supertonicDevice: SupertonicDevice;
  /** Denoising steps: fewer is faster, more sounds cleaner. */
  supertonicSteps: number;
}

export interface NeuralVoice {
  /** Prefixed id stored in settings, e.g. `piper:fr_FR-siwis-medium`. */
  id: string;
  engine: NeuralEngine;
  /** Two-letter site language code this voice reads. */
  lang: string;
  /** Human readable name, e.g. "Siwis". */
  name: string;
  /** Accent/locale label shown next to the name, e.g. "FR", "US", "GB" ('' if none). */
  accent: string;
  gender: 'female' | 'male';
  /** Approximate download size in MB (shared model for Kokoro). */
  sizeMb: number;
  /** Shown first in its language and used when the user hasn't picked one. */
  isDefault?: boolean;
}

/** Cache API bucket holding the Piper models (Kokoro uses transformers.js' own). */
export const TTS_CACHE_NAME = 'lncrawler-tts-v1';

export const PIPER_VOICES_BASE = 'https://huggingface.co/rhasspy/piper-voices/resolve/main';

export const KOKORO_MODEL_ID = 'onnx-community/Kokoro-82M-v1.0-ONNX';
/** Download size of the Kokoro model per device (q8 for wasm, fp32 for webgpu). */
export const KOKORO_SIZE_MB: Record<KokoroDevice, number> = { wasm: 92, webgpu: 326 };

type PiperRow = [id: string, name: string, gender: 'female' | 'male', sizeMb: number, isDefault?: boolean];

// [piper id, display name, gender, size MB, default?]
const PIPER_ROWS: PiperRow[] = [
  ['ar_JO-kareem-medium', 'Kareem', 'male', 63, true],
  ['da_DK-talesyntese-medium', 'Talesyntese', 'male', 63, true],
  ['de_DE-thorsten-medium', 'Thorsten', 'male', 63, true],
  ['de_DE-thorsten-high', 'Thorsten HQ', 'male', 114],
  ['en_US-lessac-medium', 'Lessac', 'female', 63, true],
  ['en_US-lessac-high', 'Lessac HQ', 'female', 114],
  ['en_US-amy-medium', 'Amy', 'female', 63],
  ['en_US-kristin-medium', 'Kristin', 'female', 64],
  ['en_US-hfc_female-medium', 'HFC', 'female', 63],
  ['en_US-ryan-high', 'Ryan HQ', 'male', 121],
  ['en_US-joe-medium', 'Joe', 'male', 63],
  ['en_US-hfc_male-medium', 'HFC', 'male', 63],
  ['en_US-norman-medium', 'Norman', 'male', 64],
  ['en_GB-alba-medium', 'Alba', 'female', 63],
  ['en_GB-cori-high', 'Cori HQ', 'female', 114],
  ['en_GB-jenny_dioco-medium', 'Jenny', 'female', 63],
  ['en_GB-alan-medium', 'Alan', 'male', 63],
  ['en_GB-northern_english_male-medium', 'Northern English', 'male', 63],
  ['es_ES-davefx-medium', 'Davefx', 'male', 63, true],
  ['es_MX-claude-high', 'Claude HQ', 'female', 63],
  ['es_AR-daniela-high', 'Daniela HQ', 'female', 114],
  ['es_MX-ald-medium', 'Ald', 'male', 63],
  ['fr_FR-siwis-medium', 'Siwis', 'female', 63, true],
  ['fr_FR-tom-medium', 'Tom', 'male', 64],
  ['hi_IN-priyamvada-medium', 'Priyamvada', 'female', 64, true],
  ['hi_IN-pratham-medium', 'Pratham', 'male', 64],
  ['hi_IN-rohan-medium', 'Rohan', 'male', 63],
  ['id_ID-news_tts-medium', 'News', 'female', 63, true],
  ['it_IT-paola-medium', 'Paola', 'female', 64, true],
  ['it_IT-serena-high', 'Serena HQ', 'female', 114],
  ['it_IT-serena-medium', 'Serena', 'female', 64],
  ['ko_KR-kss-medium', 'KSS', 'female', 63, true],
  ['nl_NL-pim-medium', 'Pim', 'male', 64, true],
  ['nl_NL-ronnie-medium', 'Ronnie', 'male', 63],
  ['nl_NL-alex-medium', 'Alex', 'male', 64],
  ['nl_BE-nathalie-medium', 'Nathalie', 'female', 63],
  ['nl_BE-rdh-medium', 'RDH', 'male', 63],
  ['pl_PL-gosia-medium', 'Gosia', 'female', 63, true],
  ['pl_PL-darkman-medium', 'Darkman', 'male', 63],
  ['pl_PL-mc_speech-medium', 'MC Speech', 'male', 63],
  ['pl_PL-bass-high', 'Bass HQ', 'male', 114],
  ['pt_BR-faber-medium', 'Faber', 'male', 63, true],
  ['pt_BR-cadu-medium', 'Cadu', 'male', 63],
  ['pt_BR-jeff-medium', 'Jeff', 'male', 63],
  ['ru_RU-irina-medium', 'Irina', 'female', 63, true],
  ['ru_RU-denis-medium', 'Denis', 'male', 63],
  ['ru_RU-dmitri-medium', 'Dmitri', 'male', 63],
  ['ru_RU-ruslan-medium', 'Ruslan', 'male', 63],
  ['sv_SE-lisa-medium', 'Lisa', 'female', 64, true],
  ['sv_SE-alma-medium', 'Alma', 'female', 63],
  ['sv_SE-nst-medium', 'NST', 'male', 63],
  ['tr_TR-dfki-medium', 'DFKI', 'male', 63, true],
  ['vi_VN-vais1000-medium', 'Vais1000', 'female', 63, true],
  ['zh_CN-huayan-medium', 'Huayan', 'female', 63, true],
];

type KokoroRow = [id: string, name: string, gender: 'female' | 'male', accent: 'US' | 'GB'];

// Only the voices graded C+ or better on the Kokoro model card.
const KOKORO_ROWS: KokoroRow[] = [
  ['af_heart', 'Heart', 'female', 'US'],
  ['af_bella', 'Bella', 'female', 'US'],
  ['af_nicole', 'Nicole', 'female', 'US'],
  ['af_aoede', 'Aoede', 'female', 'US'],
  ['af_kore', 'Kore', 'female', 'US'],
  ['af_sarah', 'Sarah', 'female', 'US'],
  ['am_michael', 'Michael', 'male', 'US'],
  ['am_fenrir', 'Fenrir', 'male', 'US'],
  ['am_puck', 'Puck', 'male', 'US'],
  ['bf_emma', 'Emma', 'female', 'GB'],
  ['bf_isabella', 'Isabella', 'female', 'GB'],
  ['bm_george', 'George', 'male', 'GB'],
  ['bm_fable', 'Fable', 'male', 'GB'],
];

const piperVoices: NeuralVoice[] = PIPER_ROWS.map(([id, name, gender, sizeMb, isDefault]) => {
  const locale = id.split('-')[0];
  return {
    id: `piper:${id}`,
    engine: 'piper',
    lang: locale.split('_')[0],
    name,
    accent: locale.split('_')[1],
    gender,
    sizeMb,
    isDefault,
  };
});

const kokoroVoices: NeuralVoice[] = KOKORO_ROWS.map(([id, name, gender, accent]) => ({
  id: `kokoro:${id}`,
  engine: 'kokoro',
  lang: 'en',
  name,
  accent,
  gender,
  sizeMb: KOKORO_SIZE_MB.wasm,
}));

export const SUPERTONIC_BASE = 'https://huggingface.co/supertone-oss-archive/supertonic-3/resolve/main';
export const SUPERTONIC_LICENSE_URL = 'https://huggingface.co/supertone-oss-archive/supertonic-3/blob/main/LICENSE';
export const SUPERTONIC_SIZE_MB = 398;
export const SUPERTONIC_MODELS = ['duration_predictor', 'text_encoder', 'vector_estimator', 'vocoder'] as const;
export const SUPERTONIC_STEPS = { fast: 4, balanced: 6, best: 8 } as const;

/** Site languages Supertonic 3 reads (it lacks Chinese and Thai). */
const SUPERTONIC_LANGS = ['en', 'fr', 'es', 'de', 'it', 'ja', 'ko', 'pt', 'ru', 'ar', 'hi', 'vi', 'id', 'tr', 'pl', 'nl', 'sv', 'da'];
const SUPERTONIC_STYLES = ['F1', 'F2', 'F3', 'F4', 'F5', 'M1', 'M2', 'M3', 'M4', 'M5'];

const supertonicVoices: NeuralVoice[] = SUPERTONIC_LANGS.flatMap(lang =>
  SUPERTONIC_STYLES.map(style => ({
    id: `supertonic:${lang}:${style}`,
    engine: 'supertonic' as const,
    lang,
    name: `Supertonic ${style}`,
    accent: '',
    gender: style.startsWith('F') ? 'female' as const : 'male' as const,
    sizeMb: SUPERTONIC_SIZE_MB,
    isDefault: style === 'F1',
  })),
);

export const NEURAL_VOICES: NeuralVoice[] = [...supertonicVoices, ...kokoroVoices, ...piperVoices];

export const getNeuralVoice = (id: string | undefined): NeuralVoice | undefined =>
  id ? NEURAL_VOICES.find(v => v.id === id) : undefined;

export const getNeuralVoicesForLang = (lang: string): NeuralVoice[] =>
  NEURAL_VOICES.filter(v => v.lang === lang);

export const hasNeuralVoices = (lang: string): boolean =>
  NEURAL_VOICES.some(v => v.lang === lang);

/** The user's pick for `lang` if still valid, else the catalog default
 *  (Supertonic where it reads the language, Piper otherwise). */
export const resolveNeuralVoice = (
  lang: string,
  picks: Record<string, string>,
): NeuralVoice | undefined => {
  const picked = getNeuralVoice(picks[lang]);
  if (picked && picked.lang === lang) return picked;
  return supertonicVoices.find(v => v.lang === lang && v.isDefault)
    ?? piperVoices.find(v => v.lang === lang && v.isDefault)
    ?? getNeuralVoicesForLang(lang)[0];
};

export const supertonicFileUrls = (): string[] => [
  `${SUPERTONIC_BASE}/onnx/tts.json`,
  `${SUPERTONIC_BASE}/onnx/unicode_indexer.json`,
  ...SUPERTONIC_MODELS.map(m => `${SUPERTONIC_BASE}/onnx/${m}.onnx`),
];

export const supertonicStyleUrl = (style: string): string => `${SUPERTONIC_BASE}/voice_styles/${style}.json`;

/** Path of a Piper voice inside the piper-voices repository, without extension. */
export const piperVoicePath = (piperId: string): string => {
  const [locale, speaker, quality] = piperId.split('-');
  return `${locale.split('_')[0]}/${locale}/${speaker}/${quality}/${piperId}`;
};

export const piperModelUrls = (piperId: string) => {
  const path = piperVoicePath(piperId);
  return {
    model: `${PIPER_VOICES_BASE}/${path}.onnx`,
    config: `${PIPER_VOICES_BASE}/${path}.onnx.json`,
  };
};

export const kokoroModelUrl = (device: KokoroDevice): string =>
  `https://huggingface.co/${KOKORO_MODEL_ID}/resolve/main/onnx/${device === 'webgpu' ? 'model.onnx' : 'model_quantized.onnx'}`;

/** Short sample sentence per language for the voice preview button. */
export const PREVIEW_TEXT: Record<string, string> = {
  en: 'The night was quiet as she opened the old book and began to read.',
  fr: 'La nuit était calme lorsqu’elle ouvrit le vieux livre et commença à lire.',
  es: 'La noche estaba tranquila cuando abrió el viejo libro y empezó a leer.',
  de: 'Die Nacht war still, als sie das alte Buch öffnete und zu lesen begann.',
  it: 'La notte era tranquilla quando aprì il vecchio libro e cominciò a leggere.',
  ja: '彼女が古い本を開いて読み始めたとき、夜は静かだった。',
  ko: '그녀가 오래된 책을 펼쳐 읽기 시작했을 때 밤은 조용했다.',
  zh: '她打开那本旧书开始阅读时，夜晚十分宁静。',
  pt: 'A noite estava tranquila quando ela abriu o velho livro e começou a ler.',
  ru: 'Ночь была тихой, когда она открыла старую книгу и начала читать.',
  ar: 'كان الليل هادئًا عندما فتحت الكتاب القديم وبدأت القراءة.',
  hi: 'रात शांत थी जब उसने पुरानी किताब खोली और पढ़ना शुरू किया।',
  th: 'คืนนั้นเงียบสงบเมื่อเธอเปิดหนังสือเล่มเก่าและเริ่มอ่าน',
  vi: 'Đêm thật yên tĩnh khi cô mở cuốn sách cũ và bắt đầu đọc.',
  id: 'Malam itu sunyi ketika dia membuka buku tua itu dan mulai membaca.',
  tr: 'Eski kitabı açıp okumaya başladığında gece sessizdi.',
  pl: 'Noc była cicha, gdy otworzyła starą książkę i zaczęła czytać.',
  nl: 'De nacht was stil toen ze het oude boek opende en begon te lezen.',
  sv: 'Natten var stilla när hon öppnade den gamla boken och började läsa.',
  da: 'Natten var stille, da hun åbnede den gamle bog og begyndte at læse.',
};
