<p align="center">
  <img src="icon.png" width="120" alt="Claude Smart Notifier">
</p>

<h1 align="center">Claude Smart Notifier</h1>
<p align="center"><i>Desktop notifications for Claude Code, Claude Desktop &amp; Cowork: an MCP server that pings you when a thread is done or needs you</i></p>

<p align="center">
  <b>Never miss a Claude thread that's waiting for you.</b><br>
  Native desktop notifications when any Claude thread finishes a task or needs your answer.
</p>

<p align="center">
  <a href="https://github.com/vjvasiljev/claude_smart_notifier/releases/latest"><img src="https://img.shields.io/github/v/release/vjvasiljev/claude_smart_notifier?label=release" alt="Release"></a>
  <img src="https://img.shields.io/badge/macOS-supported-black" alt="macOS">
  <a href="https://github.com/vjvasiljev/claude_smart_notifier/issues/1"><img src="https://img.shields.io/badge/Windows-needs%20testers-orange" alt="Windows: needs testers"></a>
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero dependencies">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT"></a>
</p>

<p align="center">
  <a href="#-install">Install</a> ·
  <a href="#-ask-claude-to-install-it">Ask Claude to install it</a> ·
  <a href="#%EF%B8%8F-settings">Settings</a> ·
  <a href="#-troubleshooting">Troubleshooting</a> ·
  <a href="README.ru.md">Русский</a>
</p>

<p align="center"><img src="assets/demo.gif" width="760" alt="Claude Smart Notifier demo: notifications arrive for each project with done / needs answer / urgent levels"></p>

https://github.com/user-attachments/assets/5da68f17-e8fd-4366-bc6e-96da649fcef8


---

## The problem

You run five Claude threads across three projects. One of them finished ten minutes ago and is waiting for a decision. You find out only when you happen to click on it. Work stalls.

## The fix

Every thread pings you, with the **project name** and **one ultra-short line** saying exactly what it needs. Details stay in the chat.

```
✅  Website redesign     Done                Homepage ready, review it
🟡  Q3 report            Needs your answer   Use March or April figures?
🔴  Mobile app           Urgent              Build failed — need API key
```

| Level | When | Default sound (macOS) |
|---|---|---|
| ✅ `done` | Task finished | Glass |
| 🟡 `question` | Waiting for your answer, decision, data or access | Ping |
| 🔴 `urgent` | Blocked, error, deadline | Sosumi |

**Highlights**

- Works in **Claude Desktop** (chats, Projects, Cowork) and **Claude Code**
- **macOS** and **Windows** (Linux via `notify-send`)

> [!IMPORTANT]
> **Windows testers wanted.** The Windows version is written but not yet tested on a real Windows machine. On Windows? Please try it and report in [issue #1](https://github.com/vjvasiljev/claude_smart_notifier/issues/1). It takes 2 minutes.
- **One-click install**, settings in Claude's UI, no config files
- **Zero dependencies**, no accounts, no servers. Your notification text never leaves your computer
- **Update alerts**: once a day it checks GitHub and pings you when a new version is out (can be turned off)
- **Set up once**: one line in your Claude instructions and every thread, in every project, pings you

---

## 📦 Install

### Claude Desktop (macOS / Windows): one click

1. Download **[claude-smart-notifier.mcpb](https://github.com/vjvasiljev/claude_smart_notifier/releases/latest/download/claude-smart-notifier.mcpb)**
2. Double-click it. Claude opens the install dialog, then click **Install**
3. *(optional)* **Settings → Extensions → Claude Smart Notifier**: language (`auto` = same as the thread, 48 languages), sounds, mute

> **Do I need to put any files on my computer?** No. The `.mcpb` is a Claude Desktop extension: Claude installs it and runs it with its own built-in Node.js. When a new version is out you get a notification; download the new `.mcpb` from Releases and install it over the old one. Nothing to configure by hand.

Start a **new** chat and give it something that takes a while. You'll get pinged when it's done.

### Claude Code

```text
/plugin marketplace add vjvasiljev/claude_smart_notifier
/plugin install smart-notifier@claude-smart-notifier
```

Restart Claude Code.

### 🤖 Ask Claude to install it

Paste this into Claude (Desktop/Cowork with access to your computer, or Claude Code):

> Install Claude Smart Notifier for me: https://github.com/vjvasiljev/claude_smart_notifier — follow INSTALL.md in that repo.

Claude follows [`INSTALL.md`](INSTALL.md): it downloads the bundle and opens the installer (Desktop) or runs the plugin commands (Code). You only click **Install**.

<details>
<summary><b>Manual install (any MCP client)</b></summary>

Requires Node.js ≥ 16.

```bash
git clone https://github.com/vjvasiljev/claude_smart_notifier.git
```

```json
{
  "mcpServers": {
    "smart-notifier": {
      "command": "node",
      "args": ["/absolute/path/to/claude_smart_notifier/server/index.js"],
      "env": { "NOTIFY_LANG": "en" }
    }
  }
}
```
</details>

### Make every project and thread ping you

| Where | Setup after install |
|---|---|
| **Claude Code** (plugin) | **Nothing.** Built-in hooks ping you when a session finishes, asks a question, or needs a permission. No model involvement, works every time. |
| **Claude Desktop / Cowork / Projects** (.mcpb) | **One line, once.** Claude Desktop loads extension tools on demand and doesn't pass server instructions to threads, so the model has to be told. The extension reminds you on first run. |

For Claude Desktop, paste this into **Settings → Your Claude → Instructions** (applies to every chat and project):

> Always: when you finish a task, and whenever you need my answer, decision, data or access, call the `notify` tool (Claude Smart Notifier) once as your very last action — this is required in every chat and project. The tool is often deferred: if it isn't loaded, load it first with tool search (query "notify"). Arguments: title = project name, level = done / question / urgent, lang = your reply language, message = max 40 chars saying what I must do. Only if no notify tool exists at all (phone or web without my computer), skip it silently.

Start a **new** thread afterwards.

### Check it works

```bash
node server/index.js --test
```
Shows one notification of each level.

---

## ⚙️ Settings

In Claude Desktop, change these in **Settings → Extensions**. Elsewhere, set them as environment variables.

| Setting | Env var | Default | |
|---|---|---|---|
| Language | `NOTIFY_LANG` | `auto` | Labels language. `auto` = the language the thread replies in (fallback: system language). 48 supported: en ru uk be lt lv et pl cs sk de fr es pt it ca nl sv no da fi hu ro bg sr hr sl el tr az ka hy kk uz he ar fa hi bn ja ko zh zh-tw vi th id ms sw |
| Sound: done | `NOTIFY_SOUND_DONE` | `Glass` | macOS sound name |
| Sound: needs answer | `NOTIFY_SOUND_QUESTION` | `Ping` | macOS sound name |
| Sound: urgent | `NOTIFY_SOUND_URGENT` | `Sosumi` | macOS sound name |
| Mute | `NOTIFY_MUTE` | `false` | Silence everything |
| Check for updates | `NOTIFY_UPDATE_CHECK` | `true` | Once a day ask GitHub for the latest release and notify you about a new version |
| Advanced | `NOTIFY_CONFIG` | — | Path to a JSON file (below) |

**Advanced: custom emoji, labels and sounds per level**

```json
{
  "levels": {
    "done":     { "emoji": "🟢", "sound": "Hero",  "label": "Finished" },
    "question": { "emoji": "🟡", "sound": "Ping",  "label": "Your turn" },
    "urgent":   { "emoji": "🔴", "sound": "Basso", "label": "Blocked" }
  },
  "emojiInTitle": true
}
```

macOS sounds: `Basso` `Blow` `Bottle` `Frog` `Funk` `Glass` `Hero` `Morse` `Ping` `Pop` `Purr` `Sosumi` `Submarine` `Tink`.
On Windows each level uses a system sound (Default / Reminder / IM), and 🔴 urgent stays on screen until dismissed.

---

## 🩺 Troubleshooting

| Symptom | Fix |
|---|---|
| **macOS: nothing appears** (the tool still reports "sent": macOS gives no delivery confirmation) | Notifications go through `osascript`, which macOS attributes to **Script Editor**. Open *System Settings → Notifications → Script Editor* and allow them. Turn off Focus / Do Not Disturb. |
| **macOS: notifications land in Notification Center but no banner pops up** | You're recording or sharing the screen — macOS hides banners then. Stop the recording, or enable *System Settings → Notifications → Allow notifications when mirroring or sharing the display*. |
| **macOS: click opens Script Editor** | Known `osascript` limitation. Switch to Claude manually. |
| **Windows: nothing appears** | *Settings → System → Notifications* must be on; Focus Assist off. Toasts appear under *Windows PowerShell*. |
| **A thread says it has no `notify` tool** | The thread isn't linked to your computer (e.g. started on the web or phone). Send a message in it from **Claude Desktop** on that computer, or on web/phone pick your computer under **+ → Devices** before sending. The computer must be on with Claude Desktop open. |
| **A thread didn't ping me** | The server instructs Claude, but the model decides when to call the tool. Already-open threads only pick it up after a restart. To make a project more reliable, add to its instructions: *"When you finish or need my answer, call notify."* |
| **Old threads don't have the tool** | Restart Claude and start a new thread. |

---

## ❓ FAQ

**How do I get notified when Claude Code finishes a task?**
Install the Claude Code plugin (two commands above). Every session will ping you when it's done or waiting for input.

**How do I know when a Claude Desktop / Cowork / Projects chat is waiting for me?**
Install the `.mcpb` extension. Any thread that needs your decision sends a 🟡 notification with the project name.

**Does it work with many parallel threads and projects?**
That's what it's built for. Each notification starts with the project name, so you know where to go.

**Does it send my data anywhere?**
No. Your notifications are shown locally via the OS. The only network request is a once-a-day version check to GitHub's public releases API (no data about you, can be turned off). No telemetry.

**Can it play a different sound per level?**
Yes. Set sounds in the extension settings, or emoji/labels/sounds per level via `NOTIFY_CONFIG`.

**My language isn't there.**
Add one line to `LABELS` in `server/index.js` and open a PR.

## 🛠 How it works

A ~350-line, zero-dependency Node.js [MCP](https://modelcontextprotocol.io) server with one tool:

```
notify(title, message, level = done | question | urgent, subtitle?, sound?)
```

- Speaks MCP over stdio
- Calls the native notification API: `osascript` (macOS), PowerShell WinRT toast (Windows), `notify-send` (Linux)
- Returns MCP **`instructions`**, so every connected Claude thread knows to call `notify` once at the end of a task, with a ≤ 40-character message in your language

```
server/index.js           MCP server (the whole thing)
manifest.json             Claude Desktop extension manifest (.mcpb)
.claude-plugin/           Claude Code plugin + marketplace
.mcp.json                 MCP config used by the Claude Code plugin
```

## 🗺 Roadmap

- [ ] **Verify on Windows** ([help wanted](https://github.com/vjvasiljev/claude_smart_notifier/issues/1))
- [ ] Click a notification to open the exact thread
- [ ] Quiet hours
- [ ] Phone push (ntfy / Pushover) as an optional channel
- [ ] Per-project sounds
- [ ] Native dropdown for language (when Claude extension settings support it)

Ideas and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © vjvasiljev

<sub>Not affiliated with or endorsed by Anthropic. "Claude" is a trademark of Anthropic, PBC.</sub>
