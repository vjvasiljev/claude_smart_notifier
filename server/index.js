#!/usr/bin/env node
/**
 * Claude Smart Notifier — desktop notifications for Claude (Desktop, Cowork, Claude Code).
 * Zero dependencies. macOS (osascript), Windows (PowerShell toast), Linux (notify-send).
 *
 * Gives Claude one tool, `notify`, plus server instructions telling every thread
 * to ping you when it finishes a task or needs your answer.
 *
 * Settings (env vars, set by the .mcpb installer UI or by hand):
 *   NOTIFY_LANG            auto | en | ru | de | ja | ...  (labels language; auto = language of the thread's reply, else system)
 *   NOTIFY_SOUND_DONE      macOS sound name      (default Glass)
 *   NOTIFY_SOUND_QUESTION  macOS sound name      (default Ping)
 *   NOTIFY_SOUND_URGENT    macOS sound name      (default Sosumi)
 *   NOTIFY_MUTE            true | false          (default false)
 *   NOTIFY_UPDATE_CHECK    true | false          (default true; once a day asks GitHub for the latest version)
 *   NOTIFY_CONFIG          path to a JSON file overriding everything above (optional)
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const os = require('os');

const VERSION = '1.4.0';
const SERVER_INFO = { name: 'claude-smart-notifier', version: VERSION };

// [done, question, urgent] labels. Add a language with one line, PRs welcome.
const LABELS = {
  en: ['Done', 'Needs your answer', 'Urgent'],
  ru: ['Готово', 'Нужен ответ', 'Срочно'],
  uk: ['Готово', 'Потрібна відповідь', 'Терміново'],
  be: ['Гатова', 'Патрэбны адказ', 'Тэрмінова'],
  lt: ['Atlikta', 'Reikia atsakymo', 'Skubu'],
  lv: ['Gatavs', 'Vajag atbildi', 'Steidzami'],
  et: ['Valmis', 'Vajab vastust', 'Kiire'],
  pl: ['Gotowe', 'Potrzebna odpowiedź', 'Pilne'],
  cs: ['Hotovo', 'Čeká na odpověď', 'Naléhavé'],
  sk: ['Hotovo', 'Čaká na odpoveď', 'Naliehavé'],
  de: ['Fertig', 'Antwort benötigt', 'Dringend'],
  fr: ['Terminé', 'Réponse requise', 'Urgent'],
  es: ['Listo', 'Necesita tu respuesta', 'Urgente'],
  pt: ['Concluído', 'Precisa da sua resposta', 'Urgente'],
  it: ['Fatto', 'Serve la tua risposta', 'Urgente'],
  ca: ['Fet', 'Cal la teva resposta', 'Urgent'],
  nl: ['Klaar', 'Antwoord nodig', 'Dringend'],
  sv: ['Klart', 'Behöver ditt svar', 'Brådskande'],
  no: ['Ferdig', 'Trenger svar', 'Haster'],
  nb: ['Ferdig', 'Trenger svar', 'Haster'],
  da: ['Færdig', 'Kræver dit svar', 'Haster'],
  fi: ['Valmis', 'Tarvitsee vastauksesi', 'Kiireellinen'],
  hu: ['Kész', 'Válaszra vár', 'Sürgős'],
  ro: ['Gata', 'Așteaptă răspunsul tău', 'Urgent'],
  bg: ['Готово', 'Нужен е отговор', 'Спешно'],
  sr: ['Готово', 'Потребан одговор', 'Хитно'],
  hr: ['Gotovo', 'Potreban odgovor', 'Hitno'],
  sl: ['Končano', 'Potreben odgovor', 'Nujno'],
  el: ['Ολοκληρώθηκε', 'Χρειάζεται απάντηση', 'Επείγον'],
  tr: ['Tamamlandı', 'Yanıtın gerekli', 'Acil'],
  az: ['Hazırdır', 'Cavabınız lazımdır', 'Təcili'],
  ka: ['დასრულდა', 'საჭიროა პასუხი', 'სასწრაფო'],
  hy: ['Պատրաստ է', 'Պատասխան է պետք', 'Շտապ'],
  kk: ['Дайын', 'Жауабыңыз керек', 'Шұғыл'],
  uz: ['Tayyor', 'Javobingiz kerak', 'Shoshilinch'],
  he: ['הושלם', 'נדרשת תשובה', 'דחוף'],
  ar: ['تم', 'بحاجة إلى ردك', 'عاجل'],
  fa: ['انجام شد', 'نیاز به پاسخ', 'فوری'],
  hi: ['पूरा हुआ', 'आपका जवाब चाहिए', 'ज़रूरी'],
  bn: ['সম্পন্ন', 'আপনার উত্তর দরকার', 'জরুরি'],
  ja: ['完了', '返信が必要', '至急'],
  ko: ['완료', '답변 필요', '긴급'],
  zh: ['已完成', '需要你的回复', '紧急'],
  'zh-tw': ['已完成', '需要你的回覆', '緊急'],
  vi: ['Xong', 'Cần bạn trả lời', 'Khẩn'],
  th: ['เสร็จแล้ว', 'รอคำตอบของคุณ', 'ด่วน'],
  id: ['Selesai', 'Perlu jawabanmu', 'Mendesak'],
  ms: ['Siap', 'Perlu jawapan anda', 'Segera'],
  sw: ['Imekamilika', 'Inahitaji jibu lako', 'Haraka'],
};

let detectedLocale = null;
function systemLocale() {
  if (detectedLocale) return detectedLocale;
  let loc = process.env.LC_ALL || process.env.LC_MESSAGES || process.env.LANG || '';
  try {
    if (process.platform === 'darwin') {
      const out = require('child_process').execFileSync('/usr/bin/defaults', ['read', '-g', 'AppleLanguages'], { encoding: 'utf8', timeout: 2000 });
      const m = out.match(/"?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)"?/);
      if (m) loc = m[1];
    } else if (process.platform === 'win32') {
      const out = require('child_process').execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', '(Get-UICulture).Name'], { encoding: 'utf8', timeout: 5000, windowsHide: true });
      if (out.trim()) loc = out.trim();
    }
  } catch (_) { /* fall through */ }
  if (!loc || /^(C|POSIX)/.test(loc)) {
    try { loc = Intl.DateTimeFormat().resolvedOptions().locale; } catch (_) { loc = 'en'; }
  }
  detectedLocale = loc.replace('_', '-').split('.')[0].toLowerCase();
  return detectedLocale;
}

function resolveLabels(lang) {
  let code = (lang || 'auto').toLowerCase().replace('_', '-');
  if (code === 'auto' || code === '') code = systemLocale();
  if (code.startsWith('zh') && /(tw|hk|mo|hant)/.test(code)) code = 'zh-tw';
  let arr = LABELS[code] || LABELS[code.split('-')[0]];
  if (!arr && lang && lang !== 'auto') {
    const sys = systemLocale();
    arr = LABELS[sys] || LABELS[sys.split('-')[0]];
  }
  arr = arr || LABELS.en;
  return { done: arr[0], question: arr[1], urgent: arr[2] };
}

const WIN_SOUNDS = {
  done: 'ms-winsoundevent:Notification.Default',
  question: 'ms-winsoundevent:Notification.Reminder',
  urgent: 'ms-winsoundevent:Notification.IM',
};

function env(name, fallback) {
  const v = process.env[name];
  if (v === undefined || v === null || v === '' || String(v).includes('${')) return fallback;
  return String(v).trim();
}

function envFlag(v) {
  return /^(1|true|yes|on)$/i.test(String(v || '').trim());
}

function loadConfig(threadLang) {
  const setting = env('NOTIFY_LANG', 'auto').toLowerCase();
  const labels = resolveLabels(setting === 'auto' && threadLang ? threadLang : setting);
  const cfg = {
    mute: envFlag(env('NOTIFY_MUTE', 'false')),
    emojiInTitle: true,
    defaultLevel: 'done',
    levels: {
      done: { emoji: '✅', sound: env('NOTIFY_SOUND_DONE', 'Glass'), label: labels.done },
      question: { emoji: '🟡', sound: env('NOTIFY_SOUND_QUESTION', 'Ping'), label: labels.question },
      urgent: { emoji: '🔴', sound: env('NOTIFY_SOUND_URGENT', 'Sosumi'), label: labels.urgent },
    },
  };
  const file = env('NOTIFY_CONFIG', '');
  if (file) {
    try {
      const user = JSON.parse(fs.readFileSync(file, 'utf8'));
      for (const [k, v] of Object.entries(user)) {
        if (k === 'levels' && v && typeof v === 'object') {
          for (const [lvl, spec] of Object.entries(v)) {
            cfg.levels[lvl] = Object.assign({}, cfg.levels[lvl] || {}, spec || {});
          }
        } else {
          cfg[k] = v;
        }
      }
    } catch (e) {
      if (e.code !== 'ENOENT') process.stderr.write(`[smart-notifier] config error: ${e.message}\n`);
    }
  }
  return cfg;
}

const INSTRUCTIONS =
  'The user runs many Claude threads in parallel and does not watch them. ' +
  "At the END of every turn where you finished a task or need the user's answer, decision, data or access, " +
  'you MUST call the `notify` tool exactly once, as your last action — this is required, not optional. Skip it for quick back-and-forth replies ' +
  'while the user is clearly chatting live. ' +
  "Fields: title = project or thread name (short); level = 'done' (finished), 'question' (waiting for the user), " +
  "'urgent' (blocked, error, deadline); lang = language code of your reply (e.g. 'en', 'ru'); message = ultra-short summary of what the user must do, " +
  "max ~40 characters, imperative, in the user's language, most important words first " +
  "(e.g. 'Pick a logo: A or B?', 'Report ready, review figures'). " +
  'Never put details in the notification; they stay in the chat.';

function toolsDef(cfg) {
  return [
    {
      name: 'notify',
      description:
        "Show a desktop notification with sound on the user's computer. Call it when a task is finished " +
        "or when you need the user's answer/decision. level: 'done' = finished, 'question' = waiting for " +
        "the user's answer, 'urgent' = blocked/error/time-critical. title = project name; message = " +
        'ultra-short (<= ~40 chars) what exactly the user must do. Details stay in the chat.',
      inputSchema: {
        type: 'object',
        properties: {
          title: { type: 'string', description: 'Project / thread name' },
          message: { type: 'string', description: 'Ultra-short: what the user must do (<= ~40 chars)' },
          level: { type: 'string', enum: Object.keys(cfg.levels), description: 'Importance level' },
          lang: { type: 'string', description: "Language code of your reply to the user (e.g. 'en', 'ru', 'de'); labels follow it when the language setting is auto" },
          subtitle: { type: 'string', description: "Optional; defaults to the level's label" },
          sound: { type: 'string', description: "Optional override of the level's sound (macOS sound name)" },
        },
        required: ['message'],
      },
    },
  ];
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    let stderr = '';
    let done = false;
    const child = spawn(cmd, args, Object.assign({ windowsHide: true }, opts));
    const timer = setTimeout(() => {
      if (!done) { done = true; child.kill(); resolve({ code: -1, stderr: 'timeout' }); }
    }, 15000);
    child.stderr.on('data', (d) => (stderr += d));
    child.on('error', (e) => { if (!done) { done = true; clearTimeout(timer); resolve({ code: -1, stderr: e.message }); } });
    child.on('close', (code) => { if (!done) { done = true; clearTimeout(timer); resolve({ code, stderr }); } });
  });
}

// ---------- platform backends ----------

const APPLESCRIPT = [
  'on run argv',
  'set t to item 1 of argv',
  'set m to item 2 of argv',
  'set s to item 3 of argv',
  'set snd to item 4 of argv',
  'if snd is "" then',
  'if s is "" then',
  'display notification m with title t',
  'else',
  'display notification m with title t subtitle s',
  'end if',
  'else',
  'if s is "" then',
  'display notification m with title t sound name snd',
  'else',
  'display notification m with title t subtitle s sound name snd',
  'end if',
  'end if',
  'end run',
];

function notifyMac(n) {
  const args = [];
  for (const line of APPLESCRIPT) args.push('-e', line);
  args.push(n.title, n.message, n.subtitle, n.sound);
  return run('/usr/bin/osascript', args);
}

function xmlEscape(s) {
  return String(s).replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' }[c]));
}

function notifyWindows(n) {
  const audio = WIN_SOUNDS[n.level] || WIN_SOUNDS.done;
  const lines = [n.subtitle, n.message].filter(Boolean).map((t) => `<text>${xmlEscape(t)}</text>`).join('');
  const scenario = n.level === 'urgent' ? ' scenario="reminder"' : '';
  const actions = n.level === 'urgent' ? '<actions><action content="OK" arguments="dismiss" activationType="system"/></actions>' : '';
  const xml =
    `<toast${scenario}><visual><binding template="ToastGeneric"><text>${xmlEscape(n.title)}</text>${lines}</binding></visual>` +
    `<audio src="${audio}"/>${actions}</toast>`;
  const xmlB64 = Buffer.from(xml, 'utf8').toString('base64');
  const ps = [
    '$ErrorActionPreference = "Stop"',
    '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null',
    '[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null',
    `$x = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("${xmlB64}"))`,
    '$doc = New-Object Windows.Data.Xml.Dom.XmlDocument',
    '$doc.LoadXml($x)',
    '$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)',
    '$appId = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"',
    '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)',
  ].join('\n');
  const encoded = Buffer.from(ps, 'utf16le').toString('base64');
  return run('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded]);
}

function notifyLinux(n) {
  const urgency = n.level === 'urgent' ? 'critical' : 'normal';
  const body = [n.subtitle, n.message].filter(Boolean).join(' — ');
  return run('notify-send', ['-u', urgency, '-a', 'Claude', n.title, body]);
}

async function notify(args) {
  const cfg = loadConfig(args.lang);
  if (cfg.mute) return { text: 'Muted in settings — notification not shown.', isError: false };
  const has = (k) => typeof k === 'string' && Object.prototype.hasOwnProperty.call(cfg.levels, k);
  const level = has(args.level) ? args.level : cfg.defaultLevel;
  const spec = cfg.levels[level] || {};
  const clip = (v, n) => { const t = String(v || '').replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
  let title = clip(args.title || 'Claude', 60);
  if (cfg.emojiInTitle !== false && spec.emoji) title = `${spec.emoji} ${title}`;
  const n = {
    level,
    title,
    message: clip(args.message, 120),
    subtitle: clip(args.subtitle || spec.label, 60),
    sound: String(args.sound || spec.sound || ''),
  };
  let r;
  if (process.platform === 'darwin') r = await notifyMac(n);
  else if (process.platform === 'win32') r = await notifyWindows(n);
  else r = await notifyLinux(n);
  if (r.code !== 0) return { text: `Notification failed (${process.platform}): ${r.stderr.trim()}`, isError: true };
  const note = process.platform === 'darwin'
    ? ' (handed to macOS; delivery cannot be confirmed — if the user saw nothing, Script Editor notifications are off or Focus is on)'
    : '';
  return { text: `Notification sent [${level}]: ${n.title} | ${n.subtitle} | ${n.message}${note}`, isError: false };
}


// ---------- update check (once a day, GitHub releases only, opt-out) ----------

const REPO = 'vjvasiljev/claude_smart_notifier';
const RELEASES_URL = `https://github.com/${REPO}/releases/latest`;
const UPDATE_URL = env('NOTIFY_UPDATE_URL', `https://api.github.com/repos/${REPO}/releases/latest`);
const STATE_FILE = path.join(os.homedir(), '.claude-smart-notifier.json');
const DAY = 24 * 60 * 60 * 1000;
let availableUpdate = null;

function newer(a, b) {
  const pa = String(a).replace(/^v/, '').split('.').map((n) => parseInt(n, 10) || 0);
  const pb = String(b).replace(/^v/, '').split('.').map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < 3; i++) { if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0); }
  return false;
}

function readState() { try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch { return {}; } }
function writeState(st) { try { fs.writeFileSync(STATE_FILE, JSON.stringify(st)); } catch { /* read-only home: ignore */ } }

function fetchLatestTag() {
  return new Promise((resolve) => {
    let mod;
    try { mod = UPDATE_URL.startsWith('http://') ? require('http') : require('https'); } catch { return resolve(null); }
    const req = mod.get(UPDATE_URL, { headers: { 'User-Agent': `claude-smart-notifier/${VERSION}`, Accept: 'application/vnd.github+json' }, timeout: 5000 }, (res) => {
      let body = '';
      res.on('data', (d) => (body += d));
      res.on('end', () => { try { resolve(res.statusCode === 200 ? JSON.parse(body).tag_name || null : null); } catch { resolve(null); } });
    });
    req.on('timeout', () => req.destroy());
    req.on('error', () => resolve(null));
  });
}

async function checkForUpdate() {
  if (!envFlag(env('NOTIFY_UPDATE_CHECK', 'true'))) return;
  const st = readState();
  if (st.lastCheck && Date.now() - st.lastCheck < DAY && !process.env.NOTIFY_UPDATE_URL) {
    if (st.latest && newer(st.latest, VERSION)) availableUpdate = st.latest;
    return;
  }
  const tag = await fetchLatestTag();
  st.lastCheck = Date.now();
  if (tag) st.latest = tag;
  if (tag && newer(tag, VERSION)) {
    availableUpdate = tag;
    if (st.notified !== tag) {
      st.notified = tag;
      await notify({ title: 'Smart Notifier', level: 'done', message: `${tag} available — update from GitHub Releases` });
    }
  }
  writeState(st);
}


// ---------- Claude Code hooks (deterministic, no model involved) ----------
// hooks/hooks.json runs: node server/index.js --hook stop|notification  (event JSON on stdin)

function lastTurnInfo(transcriptPath) {
  // Returns { text, notified } for the latest assistant turn.
  const info = { text: '', notified: false };
  let lines = [];
  try { lines = fs.readFileSync(transcriptPath, 'utf8').trim().split('\n'); } catch { return info; }
  for (let i = lines.length - 1; i >= 0; i--) {
    let e; try { e = JSON.parse(lines[i]); } catch { continue; }
    const content = (e.message && e.message.content) || [];
    if (e.type === 'user') {
      const isToolResult = Array.isArray(content) && content.some((c) => c && c.type === 'tool_result');
      if (!isToolResult) break; // reached the user's prompt: turn boundary
      continue;
    }
    if (e.type !== 'assistant' || !Array.isArray(content)) continue;
    for (const c of content) {
      if (c.type === 'tool_use' && /(^|__)notify$/.test(c.name || '')) info.notified = true;
      if (c.type === 'text' && !info.text && c.text && c.text.trim()) info.text = c.text.trim();
    }
  }
  return info;
}

async function runHook(kind) {
  let raw = '';
  for await (const chunk of process.stdin) raw += chunk;
  let ev = {}; try { ev = JSON.parse(raw || '{}'); } catch { /* ignore */ }
  const project = path.basename(ev.cwd || process.cwd()) || 'Claude Code';
  if (kind === 'notification') {
    const msg = String(ev.message || '');
    if (/waiting for your input/i.test(msg)) return; // the Stop hook already pinged
    await notify({ title: project, level: 'question', message: msg || 'Needs your attention' });
    return;
  }
  if (kind === 'stop') {
    if (ev.stop_hook_active) return;
    const t = lastTurnInfo(ev.transcript_path);
    if (t.notified) return; // the model already called notify with a better message
    const firstLine = (t.text.split('\n').map((l) => l.replace(/[#*_`>]/g, '').trim()).filter(Boolean).pop() || 'Finished');
    const question = /\?\s*$/.test(t.text);
    await notify({ title: project, level: question ? 'question' : 'done', message: firstLine });
  }
}

// ---------- first run in Claude Desktop: tell the user about the one setup line ----------

async function firstRunHint() {
  if (env('NOTIFY_HOST', '') === 'claude-code') return;
  const st = readState();
  if (st.onboarded) return;
  st.onboarded = VERSION; writeState(st);
  await notify({ title: 'Smart Notifier installed', level: 'question',
    message: 'One last step: add 1 line to Claude instructions — see GitHub README' });
}

// ---------- MCP stdio JSON-RPC ----------

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

async function handle(req) {
  const { method, id } = req;
  if (id === undefined || id === null) return; // notification, no reply
  try {
    let result;
    if (method === 'initialize') {
      const pv = (req.params && req.params.protocolVersion) || '2025-06-18';
      result = { protocolVersion: pv, capabilities: { tools: {} }, serverInfo: SERVER_INFO, instructions: INSTRUCTIONS };
    } else if (method === 'ping') {
      result = {};
    } else if (method === 'tools/list') {
      result = { tools: toolsDef(loadConfig()) };
    } else if (method === 'tools/call') {
      const p = req.params || {};
      if (p.name !== 'notify') return send({ jsonrpc: '2.0', id, error: { code: -32602, message: 'Unknown tool' } });
      const r = await notify(p.arguments || {});
      let text = r.text;
      if (availableUpdate) text += `\nUpdate available: Claude Smart Notifier ${availableUpdate} (installed ${VERSION}). Mention it to the user once: ${RELEASES_URL}`;
      result = { content: [{ type: 'text', text }], isError: r.isError };
    } else {
      return send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${method}` } });
    }
    send({ jsonrpc: '2.0', id, result });
  } catch (e) {
    send({ jsonrpc: '2.0', id, error: { code: -32603, message: String(e && e.message || e) } });
  }
}

// CLI test mode: `node index.js --test` shows one notification of each level.
const hookIdx = process.argv.indexOf('--hook');
if (hookIdx !== -1) {
  runHook(process.argv[hookIdx + 1]).catch(() => {}).finally(() => process.exit(0));
} else if (process.argv.includes('--test')) {
  (async () => {
    for (const [level, msg] of [['done', 'Test: done'], ['question', 'Test: needs answer'], ['urgent', 'Test: urgent']]) {
      const r = await notify({ title: 'Smart Notifier', message: msg, level });
      console.log(r.text);
      await new Promise((res) => setTimeout(res, 1500));
    }
  })();
} else {
  setTimeout(() => { firstRunHint().catch(() => {}); }, 3000).unref();
  setTimeout(() => { checkForUpdate().catch(() => {}); }, Number(process.env.NOTIFY_UPDATE_DELAY || 10000)).unref();
  setInterval(() => { checkForUpdate().catch(() => {}); }, DAY).unref();
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  rl.on('line', (line) => {
    line = line.trim();
    if (!line) return;
    let req;
    try { req = JSON.parse(line); } catch { return; }
    handle(req);
  });
}
