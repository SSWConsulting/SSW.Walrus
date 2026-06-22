// ---------------------------------------------------------------------------
// walkthrough-recorder.mjs — narrated dashboard walkthrough recorder
//
// Adapts the ARMADA `logbook` recorder methodology to Walrus's single known
// surface: a static survey dashboard at a URL (or local index.html). Drives the
// dashboard with Playwright, narrates with a provider-pluggable, env-keyed,
// hash-cached TTS adapter (ElevenLabs bundled), overlays chapter dividers + a
// persistent SURVEY · SECTION lower-third, and muxes one .webm with ffmpeg —
// with a post-record self-check.
//
// Graceful degradation is the design: no TTS key -> burned-in captions (silent
// video); the run NAMES every degrade rather than failing.
//
// Pipeline:
//   1. Resolve narration clips: cache hit -> reuse; key present -> ElevenLabs
//      synth; no key -> caption fallback (estimated duration).
//   2. Launch headed Chromium + Playwright, record the viewport.
//   3. Run each chapter: divider + lower-third + beats, held for narration.
//   4. Build one timestamp-aligned master audio track (adelay + amix).
//   5. Mux audio onto the recording; ffprobe self-check (video + audio + frame).
//
// Run:
//   ELEVENLABS_API_KEY=... LOGBOOK_TTS_PROVIDER=elevenlabs LOGBOOK_VOICE=<id> \
//     node templates/walkthrough-recorder.mjs --plan <plan.json> --out <out.webm>
//   (omit the key to render a captioned, silent walkthrough)
// ---------------------------------------------------------------------------

import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, existsSync, writeFileSync, readFileSync, renameSync, readdirSync, unlinkSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';

// ---------------------------------------------------------------------------
// args
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const a = { plan: null, out: null, fresh: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--plan') a.plan = argv[++i];
    else if (argv[i] === '--out') a.out = argv[++i];
    else if (argv[i] === '--fresh') a.fresh = true;
  }
  return a;
}
const ARGS = parseArgs(process.argv.slice(2));
if (!ARGS.plan || !ARGS.out) {
  console.error('usage: walkthrough-recorder.mjs --plan <plan.json> --out <out.webm> [--fresh]');
  process.exit(2);
}

const plan = JSON.parse(readFileSync(ARGS.plan, 'utf8'));
const ACCENT = plan.accent || '#CC4141';        // SSW red
const CHARCOAL = '#333333';
const DARK = '#1a1a1a';
const SURVEY = plan.survey || 'Survey';
const CHAPTERS = plan.chapters || [];

const ROOT = process.env.RECORDER_ROOT || path.join(process.cwd(), '.walkthrough-tmp');
const VIDEO_DIR = path.join(ROOT, 'videos');
const AUDIO_DIR = path.join(ROOT, 'audio');
mkdirSync(VIDEO_DIR, { recursive: true });
mkdirSync(AUDIO_DIR, { recursive: true });
mkdirSync(path.dirname(path.resolve(ARGS.out)), { recursive: true });
if (ARGS.fresh) for (const f of readdirSync(AUDIO_DIR)) unlinkSync(path.join(AUDIO_DIR, f));

const FFMPEG = process.env.FFMPEG_BIN || 'ffmpeg';
const FFPROBE = process.env.FFPROBE_BIN || 'ffprobe';

const degraded = [];
const note = (m) => { if (!degraded.includes(m)) degraded.push(m); console.error(`[recorder] degrade: ${m}`); };

// ---------------------------------------------------------------------------
// TTS — provider-pluggable, env-keyed, sha256 content-hash cached.
// ElevenLabs is the bundled adapter (matches ARMADA logbook). No key => caption.
// ---------------------------------------------------------------------------
const PROVIDER = (process.env.LOGBOOK_TTS_PROVIDER || 'elevenlabs').toLowerCase().trim();
const KEYVAR = { elevenlabs: 'ELEVENLABS_API_KEY', openai: 'OPENAI_API_KEY' }[PROVIDER] || `${PROVIDER.toUpperCase()}_API_KEY`;
const TTS_KEY = process.env[KEYVAR] || null;
const VOICE = process.env.LOGBOOK_VOICE || '21m00Tcm4TlvDq8ikWAM'; // ElevenLabs "Rachel" default
const MODEL = process.env.LOGBOOK_TTS_MODEL || 'eleven_multilingual_v2';

const clipHash = (text) => createHash('sha256').update(`${PROVIDER} ${VOICE} ${text}`).digest('hex').slice(0, 16);
const probeDurationMs = (file) => {
  try {
    const out = execFileSync(FFPROBE, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]).toString().trim();
    return Math.round(parseFloat(out) * 1000);
  } catch { return null; }
};
// ~165 wpm reading pace, +0.6s breathing room, floor 2.2s.
const estimateMs = (text) => Math.max(2200, Math.round(text.trim().split(/\s+/).length / 165 * 60000) + 600);

async function synthElevenLabs(text, file) {
  const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(VOICE)}`, {
    method: 'POST',
    headers: { 'xi-api-key': TTS_KEY, accept: 'audio/mpeg', 'content-type': 'application/json' },
    body: JSON.stringify({ text, model_id: MODEL, voice_settings: { stability: 0.5, similarity_boost: 0.75 } }),
  });
  if (!res.ok) throw new Error(`ElevenLabs ${res.status}: ${(await res.text()).slice(0, 160)}`);
  writeFileSync(file, Buffer.from(await res.arrayBuffer()));
}

// Resolve every chapter's narration to { hasAudio, path|null, durationMs, text }.
async function resolveClips() {
  const items = [];
  let hits = 0, misses = 0, captioned = 0;
  for (let i = 0; i < CHAPTERS.length; i++) {
    const text = (CHAPTERS[i].narration || '').trim();
    if (!text) { items.push({ hasAudio: false, path: null, durationMs: 1500, text: '' }); continue; }
    const file = path.join(AUDIO_DIR, `${String(i).padStart(2, '0')}-${clipHash(text)}.mp3`);
    if (existsSync(file)) {
      items.push({ hasAudio: true, path: file, durationMs: probeDurationMs(file) || estimateMs(text), text });
      hits++; continue;
    }
    if (!TTS_KEY) { items.push({ hasAudio: false, path: null, durationMs: estimateMs(text), text }); captioned++; continue; }
    if (PROVIDER !== 'elevenlabs') { note(`no adapter for TTS provider "${PROVIDER}" — captioning`); items.push({ hasAudio: false, path: null, durationMs: estimateMs(text), text }); captioned++; continue; }
    try {
      await synthElevenLabs(text, file);
      items.push({ hasAudio: true, path: file, durationMs: probeDurationMs(file) || estimateMs(text), text });
      misses++;
    } catch (e) {
      note(`TTS synth failed for chapter ${i} (${e.message}) — captioning`);
      items.push({ hasAudio: false, path: null, durationMs: estimateMs(text), text });
      captioned++;
    }
  }
  if (!TTS_KEY) note(`${KEYVAR} not set — narration rendered as captions (silent video)`);
  console.error(`[recorder] clips: ${hits} cached, ${misses} synth, ${captioned} captioned`);
  return items;
}

// ---------------------------------------------------------------------------
// browser + overlays
// ---------------------------------------------------------------------------
const clips = await resolveClips();

const browser = await chromium.launch({ headless: true, args: ['--window-size=1920,1080'] });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  recordVideo: { dir: VIDEO_DIR, size: { width: 1920, height: 1080 } },
  ignoreHTTPSErrors: true,
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();
const pause = (ms) => page.waitForTimeout(ms);

const lowerThird = async (label) => {
  await page.evaluate(({ label, accent }) => {
    let lt = document.getElementById('wt-lower-third');
    if (!lt) { lt = document.createElement('div'); lt.id = 'wt-lower-third'; document.body.appendChild(lt); }
    if (!label) { lt.style.display = 'none'; return; }
    lt.style.cssText = `position:fixed;bottom:0;left:0;right:0;z-index:2147483646;
      background:linear-gradient(180deg,rgba(26,26,26,0.92),rgba(26,26,26,0.98));color:#fff;
      font:600 18px/1.4 system-ui;padding:16px 40px;display:flex;align-items:center;gap:16px;
      box-shadow:0 -6px 24px rgba(0,0,0,0.28);pointer-events:none;`;
    lt.innerHTML = `<div style="width:12px;height:12px;border-radius:50%;background:${accent};box-shadow:0 0 0 5px ${accent}33,0 0 20px ${accent}66"></div>
      <span style="font-weight:700">${label.survey || ''}</span>
      <span style="opacity:0.4;font-weight:300">|</span>
      <span style="opacity:0.92;font-weight:400">${label.section || ''}</span>`;
  }, { label, accent: ACCENT });
};

const caption = async (text) => {
  await page.evaluate(({ text }) => {
    let c = document.getElementById('wt-caption');
    if (!c) { c = document.createElement('div'); c.id = 'wt-caption'; document.body.appendChild(c); }
    if (!text) { c.style.display = 'none'; return; }
    c.style.cssText = `position:fixed;bottom:74px;left:50%;transform:translateX(-50%);z-index:2147483645;
      max-width:1100px;background:rgba(0,0,0,0.78);color:#fff;font:500 22px/1.5 system-ui;
      padding:14px 26px;border-radius:10px;text-align:center;pointer-events:none;`;
    c.style.display = 'block';
    c.textContent = text;
  }, { text });
};

const titleCard = async (innerHtml) => {
  await page.goto('about:blank');
  await page.evaluate(({ html, dark, charcoal }) => {
    document.body.style.margin = '0';
    document.body.innerHTML = `<div style="position:fixed;inset:0;background:linear-gradient(135deg,${dark},${charcoal});
      color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;
      font:500 16px system-ui;text-align:center;padding:64px">${html}</div>`;
  }, { html: innerHtml, dark: DARK, charcoal: CHARCOAL });
};

const chapterDivider = async ({ number, title, description, holdMs = 3800 }) => {
  await page.evaluate(({ number, title, description, accent, dark }) => {
    document.getElementById('wt-divider')?.remove();
    const d = document.createElement('div');
    d.id = 'wt-divider';
    d.style.cssText = `position:fixed;inset:0;z-index:2147483647;pointer-events:none;
      background:linear-gradient(135deg,${dark}f5,${dark}fc);color:#fff;display:flex;flex-direction:column;
      align-items:center;justify-content:center;font:500 16px system-ui;text-align:center;padding:64px;
      animation:wt-in 0.45s cubic-bezier(0.16,1,0.3,1)`;
    d.innerHTML = `<style>@keyframes wt-in{from{opacity:0;transform:scale(1.04)}to{opacity:1;transform:scale(1)}}
      @keyframes wt-out{from{opacity:1}to{opacity:0}}</style>
      <div style="width:80px;height:5px;border-radius:3px;background:${accent};box-shadow:0 0 24px ${accent}88;margin-bottom:28px"></div>
      <div style="font:700 16px/1 system-ui;opacity:0.55;letter-spacing:5px;text-transform:uppercase;margin-bottom:24px">Chapter ${number}</div>
      <h1 style="font:700 60px/1.15 system-ui;margin:0 0 32px;max-width:1120px;letter-spacing:-1.1px">${title}</h1>
      <div style="font:400 24px/1.55 system-ui;opacity:0.8;max-width:840px">${description || ''}</div>`;
    document.body.appendChild(d);
  }, { number, title, description, accent: ACCENT, dark: DARK });
  await pause(holdMs);
  await page.evaluate(() => {
    const d = document.getElementById('wt-divider');
    if (!d) return;
    d.style.animation = 'wt-out 0.4s ease-out forwards';
    setTimeout(() => d.remove(), 420);
  });
  await pause(450);
};

// element matcher: text:Exact | text~:Substring | contains:Anywhere | css selector
const findElSrc = `(matcher) => {
  if (matcher.startsWith('text:')) { const t = matcher.slice(5); return Array.from(document.querySelectorAll('button,a,h2,h3')).find(e => (e.textContent||'').trim() === t) || null; }
  if (matcher.startsWith('text~:')) { const t = matcher.slice(6); return Array.from(document.querySelectorAll('button,a,h2,h3')).find(e => (e.textContent||'').includes(t)) || null; }
  if (matcher.startsWith('contains:')) { const t = matcher.slice(9); const all = Array.from(document.querySelectorAll('*')).filter(e => e.isConnected && (e.textContent||'').includes(t) && e.children.length < 30); all.sort((a,b)=>(a.textContent||'').length-(b.textContent||'').length); return all[0]||null; }
  return document.querySelector(matcher);
}`;

const spotlight = async (matcher, ms = 1600) => {
  await page.evaluate(({ matcher, ms, src, accent }) => {
    const findEl = eval('(' + src + ')');
    const t = findEl(matcher);
    if (!t) return;
    t.scrollIntoView({ block: 'center', behavior: 'instant' });
    const r = t.getBoundingClientRect();
    const halo = document.createElement('div');
    halo.style.cssText = `position:fixed;left:${r.left-8}px;top:${r.top-8}px;width:${r.width+16}px;height:${r.height+16}px;
      border:4px solid ${accent};border-radius:10px;box-shadow:0 0 0 6px ${accent}4d,0 0 40px ${accent}d9,0 0 0 9999px rgba(0,0,0,0.28);
      z-index:2147483640;pointer-events:none;animation:wt-pulse 0.7s ease-in-out infinite alternate`;
    if (!document.getElementById('wt-pulse-style')) {
      const s = document.createElement('style'); s.id = 'wt-pulse-style';
      s.textContent = `@keyframes wt-pulse{0%{opacity:0.6}100%{opacity:1}}`;
      document.head.appendChild(s);
    }
    halo.className = 'wt-halo';
    document.querySelectorAll('.wt-halo').forEach(h => h.remove());
    document.body.appendChild(halo);
    setTimeout(() => halo.remove(), ms);
  }, { matcher, ms, src: findElSrc, accent: ACCENT });
  await pause(ms);
};

const clickEl = async (matcher) => {
  const ok = await page.evaluate(({ matcher, src }) => {
    const findEl = eval('(' + src + ')');
    const t = findEl(matcher);
    if (!t) return false;
    t.scrollIntoView({ block: 'center', behavior: 'instant' });
    t.click(); // Alpine listens via addEventListener — native click triggers @click
    return true;
  }, { matcher, src: findElSrc });
  if (!ok) note(`beat: no element matched "${matcher}"`);
  await pause(450);
  return ok;
};

const scrollTo = async (matcher) => {
  await page.evaluate(({ matcher, src }) => {
    const findEl = eval('(' + src + ')');
    const t = findEl(matcher);
    if (t) t.scrollIntoView({ block: 'center', behavior: 'smooth' });
    else window.scrollBy({ top: 500, behavior: 'smooth' });
  }, { matcher, src: findElSrc });
  await pause(700);
};

// Run one beat of a chapter's choreography.
async function runBeat(b) {
  switch (b.action) {
    case 'goto': await page.goto(b.value, { waitUntil: 'domcontentloaded' }); await pause(800); break;
    case 'clickTab': await clickEl(`text~:${b.value}`); await pause(500); break;
    case 'click': await clickEl(b.target); break;
    case 'expand': await clickEl(b.target); await pause(400); break;
    case 'spotlight': await spotlight(b.target, b.ms || 1600); break;
    case 'scrollTo': await scrollTo(b.target); break;
    case 'wait': await pause(b.ms || 1000); break;
    default: note(`unknown beat action "${b.action}"`);
  }
}

// ---------------------------------------------------------------------------
// run chapters, capturing each chapter's start offset for audio alignment
// ---------------------------------------------------------------------------
const recordStart = Date.now();
const timestamps = [];

for (let i = 0; i < CHAPTERS.length; i++) {
  const ch = CHAPTERS[i];
  const clip = clips[i];
  timestamps.push(Date.now() - recordStart);
  const showCaption = !clip.hasAudio && clip.text;

  if (ch.kind === 'intro' || ch.kind === 'outro') {
    const items = (ch.kind === 'intro' ? ch.agenda : ch.recap) || [];
    const mark = ch.kind === 'outro' ? '✓ ' : '';
    await titleCard(`
      <div style="font:600 14px/1 system-ui;opacity:0.6;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:14px">SSW · Free Lunch digest</div>
      <h1 style="font:800 56px/1.1 system-ui;margin:0 0 14px;letter-spacing:-1.2px;max-width:1000px">${esc(ch.title || SURVEY)}</h1>
      <div style="font:500 20px/1.5 system-ui;opacity:0.72;margin-bottom:40px;max-width:820px">${esc(ch.subtitle || plan.date || '')}</div>
      <div style="display:flex;flex-direction:column;gap:12px;width:760px;font:500 18px/1.4 system-ui;text-align:left">
        ${items.map((t, n) => `<div style="display:flex;align-items:center;gap:18px;background:${ACCENT}22;padding:15px 22px;border-radius:12px;border-left:4px solid ${ACCENT}">
          <span style="font-weight:700;opacity:0.6;font-size:14px;letter-spacing:1.5px;min-width:54px">${mark || ('0'+(n+1)).slice(-2)}</span>
          <span style="font-weight:600">${esc(t)}</span></div>`).join('')}
      </div>`);
    await lowerThird(null);
    if (showCaption) await caption(clip.text); else await caption(null);
    await pause(clip.durationMs + 300);
    continue;
  }

  // chapter: divider over a blank dark frame, then drive the live dashboard
  await lowerThird({ survey: SURVEY, section: ch.section || ch.title });
  await caption(null);
  await chapterDivider({ number: ch.number, title: ch.title, description: ch.dividerText || ch.section || '' });

  const actionStart = Date.now();
  if (showCaption) await caption(clip.text);
  for (const b of (ch.beats || [])) {
    await runBeat(b);
    await lowerThird({ survey: SURVEY, section: ch.section || ch.title }); // re-apply (clicks can re-render)
    if (showCaption) await caption(clip.text);
  }
  const remaining = clip.durationMs + 250 - (Date.now() - actionStart);
  if (remaining > 0) await pause(remaining);
  await caption(null);
}

console.error(`[recorder] recorded ${Math.round((Date.now() - recordStart) / 1000)}s across ${CHAPTERS.length} chapters`);

const videoPath = await page.video()?.path();
await page.close();
await ctx.close();
await browser.close();
if (!videoPath || !existsSync(videoPath)) { console.error('[recorder] no video produced'); process.exit(1); }

// ---------------------------------------------------------------------------
// assemble: master audio (adelay + amix) then mux + self-check
// ---------------------------------------------------------------------------
const audioClips = clips.map((c, i) => ({ ...c, i })).filter((c) => c.hasAudio);
const outResolved = path.resolve(ARGS.out);
const tmpOut = path.join(ROOT, 'output.webm');

if (audioClips.length) {
  console.error('[recorder] building master audio...');
  const masterWav = path.join(AUDIO_DIR, 'master.wav');
  const filterParts = audioClips.map((c, n) => `[${n}]adelay=${timestamps[c.i]}|${timestamps[c.i]}[a${n}]`);
  const amixInputs = audioClips.map((_, n) => `[a${n}]`).join('');
  const filterComplex = `${filterParts.join(';')};${amixInputs}amix=inputs=${audioClips.length}:normalize=0:duration=longest[out]`;
  const inputArgs = [];
  for (const c of audioClips) inputArgs.push('-i', c.path);
  inputArgs.push('-filter_complex', filterComplex, '-map', '[out]', '-ar', '22050', '-ac', '1', '-y', masterWav);
  execFileSync(FFMPEG, inputArgs, { stdio: 'ignore' });

  console.error('[recorder] muxing audio onto video...');
  execFileSync(FFMPEG, ['-i', videoPath, '-i', masterWav, '-c:v', 'copy', '-c:a', 'libopus', '-b:a', '96k', '-shortest', '-y', tmpOut], { stdio: 'ignore' });
} else {
  // Caption-only / silent walkthrough — just normalise the container.
  execFileSync(FFMPEG, ['-i', videoPath, '-c', 'copy', '-y', tmpOut], { stdio: 'ignore' });
}

renameSync(tmpOut, outResolved);

// post-record self-check: video stream + (when expected) non-silent audio + a non-blank mid frame
const selfCheck = (() => {
  try {
    const streams = JSON.parse(execFileSync(FFPROBE, ['-v', 'error', '-show_streams', '-of', 'json', outResolved]).toString());
    const hasVideo = streams.streams.some((s) => s.codec_type === 'video');
    const hasAudio = streams.streams.some((s) => s.codec_type === 'audio');
    if (!hasVideo) return { pass: false, reason: 'no video stream' };
    if (audioClips.length && !hasAudio) return { pass: false, reason: 'narration expected but no audio stream' };
    // non-blank mid frame: extract a frame; a blank/flat 1080p PNG compresses to
    // a few KB, a real screenful is much larger — use file size as the heuristic.
    const frame = path.join(ROOT, 'midframe.png');
    const dur = (probeDurationMs(outResolved) || 8000) / 1000;
    execFileSync(FFMPEG, ['-ss', String(Math.max(1, dur / 2)), '-i', outResolved, '-frames:v', '1', '-y', frame], { stdio: 'ignore' });
    const frameBytes = existsSync(frame) ? statSync(frame).size : 0;
    if (frameBytes < 8000) return { pass: false, reason: `mid frame looks blank (${frameBytes}b)` };
    return { pass: true, reason: `video${hasAudio ? '+audio' : ' (silent/captioned)'} ok; mid frame ${Math.round(frameBytes / 1024)}KB`, hasAudio };
  } catch (e) {
    return { pass: true, reason: `self-check inconclusive (${e.message.slice(0, 80)})` };
  }
})();

const summary = {
  out: outResolved,
  durationSec: Math.round((probeDurationMs(outResolved) || 0) / 1000),
  chapters: CHAPTERS.length,
  narration: audioClips.length ? `voice (${PROVIDER})` : 'captions (silent)',
  selfCheck,
  degraded,
};
console.log(JSON.stringify(summary, null, 2));
if (!selfCheck.pass) {
  console.error(`[recorder] WARNING — self-check failed: ${selfCheck.reason}`);
  process.exit(1);
}

function esc(s) { return String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
