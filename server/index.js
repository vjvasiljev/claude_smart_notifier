#!/usr/bin/env node
/**
 * Claude Smart Notifier — desktop notifications for Claude (Desktop, Cowork, Claude Code).
 * Zero dependencies. macOS (osascript), Windows (PowerShell toast), Linux (notify-send).
 *
 * Gives Claude one tool, `notify`, plus server instructions telling every thread
 * to ping you when it finishes a task or needs your answer.
 *
 * Settings (env vars, set by the .mcpb installer UI or by hand):
 *   NOTIFY_LANG            en | ru | lt          (labels language, default en)
 *   NOTIFY_SOUND_DONE      macOS sound name      (default Glass)
 *   NOTIFY_SOUND_QUESTION  macOS sound name      (default Ping)
 *   NOTIFY_SOUND_URGENT    macOS sound name      (default Sosumi)
 *   NOTIFY_MUTE            true | false          (default false)
 *   NOTIFY_CONFIG          path to a JSON file overriding everything above (optional)
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const VERSION = '1.0.0';
const SERVER_INFO = { name: 'claude-smart-notifier', version: VERSION };

const LABELS = {
  en: { done: 'Done', question: 'Needs your answer', urgent: 'Urgent' },
  ru: { done: 'Готово', question: 'Нужен ответ', urgent: 'Срочно' },
  lt: { done: 'Atlikta', question: 'Reikia atsakymo', urgent: 'Skubu' },
};

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

function loadConfig() {
  const lang = env('NOTIFY_LANG', 'en').toLowerCase();
  const labels = LABELS[lang] || LABELS.en;
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
  'call the `notify` tool exactly once, as your last action. Skip it for quick back-and-forth replies ' +
  'while the user is clearly chatting live. ' +
  "Fields: title = project or thread name (short); level = 'done' (finished), 'question' (waiting for the user), " +
  "'urgent' (blocked, error, deadline); message = ultra-short summary of what the user must do, " +
  "max ~40 characters, imperative, in the user's language, most important words first " +
  "(e.g. 'Pick NVR: Dahua or Hikvision?', 'Quote ready, check prices'). " +
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
  const cfg = loadConfig();
  if (cfg.mute) return { text: 'Muted in settings — notification not shown.', isError: false };
  const level = cfg.levels[args.level] ? args.level : cfg.defaultLevel;
  const spec = cfg.levels[level] || {};
  let title = String(args.title || 'Claude');
  if (cfg.emojiInTitle !== false && spec.emoji) title = `${spec.emoji} ${title}`;
  const n = {
    level,
    title,
    message: String(args.message || ''),
    subtitle: String(args.subtitle || spec.label || ''),
    sound: String(args.sound || spec.sound || ''),
  };
  let r;
  if (process.platform === 'darwin') r = await notifyMac(n);
  else if (process.platform === 'win32') r = await notifyWindows(n);
  else r = await notifyLinux(n);
  if (r.code !== 0) return { text: `Notification failed (${process.platform}): ${r.stderr.trim()}`, isError: true };
  return { text: `Notification shown [${level}]: ${n.title} | ${n.subtitle} | ${n.message}`, isError: false };
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
      result = { content: [{ type: 'text', text: r.text }], isError: r.isError };
    } else {
      return send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${method}` } });
    }
    send({ jsonrpc: '2.0', id, result });
  } catch (e) {
    send({ jsonrpc: '2.0', id, error: { code: -32603, message: String(e && e.message || e) } });
  }
}

// CLI test mode: `node index.js --test` shows one notification of each level.
if (process.argv.includes('--test')) {
  (async () => {
    for (const [level, msg] of [['done', 'Test: done'], ['question', 'Test: needs answer'], ['urgent', 'Test: urgent']]) {
      const r = await notify({ title: 'Smart Notifier', message: msg, level });
      console.log(r.text);
      await new Promise((res) => setTimeout(res, 1500));
    }
  })();
} else {
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  rl.on('line', (line) => {
    line = line.trim();
    if (!line) return;
    let req;
    try { req = JSON.parse(line); } catch { return; }
    handle(req);
  });
}
