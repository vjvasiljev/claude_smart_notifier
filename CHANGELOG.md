# Changelog

## [1.5.0] — 2026-11-11

### Added
- `project` and `thread` arguments: title shows the project, subtitle shows `thread · status`, so you know exactly where to go. `title` still works as an alias of `project`.

## [1.4.0] — 2026-11-11

### Added
- Claude Code plugin hooks (Stop, Notification): zero-config notifications on finish / question / permission request, skipped when the model already called `notify`
- First-run hint in Claude Desktop about the one-line setup

### Docs
- Clear setup table: Claude Code needs nothing; Claude Desktop needs one Instructions line (tools load on demand, server instructions don't reach threads)

## [1.3.0] — 2026-11-11

### Added
- Daily update check against GitHub Releases; notifies once per new version and tells Claude to mention it. Opt-out via *Check for updates* / `NOTIFY_UPDATE_CHECK=false`

## [1.2.1] — 2026-11-11

### Fixed
- Unknown language code now falls back to the system language instead of English
- Unknown level (incl. `__proto__`) falls back to the default level
- Title/subtitle capped at 60 chars, message at 120
- macOS result no longer claims the notification was shown (delivery can't be confirmed)
- Privacy policy link included in the bundle manifest
- README: neutral examples, correct update instructions

## [1.2.0] — 2026-11-11

### Changed
- `auto` language now follows the language the thread replies in (new `lang` tool argument), falling back to the system language
- Stronger server instructions: calling `notify` at the end of a task is required

## [1.1.0] — 2026-11-11

### Added
- 48 label languages; `auto` (default) follows the system language
- Automatic GitHub Release with the `.mcpb` on every version bump
- README: "make every thread ping you", FAQ

## [1.0.0] — 2026-11-11

### Added
- `notify` tool with three levels: ✅ done, 🟡 question, 🔴 urgent
- macOS (osascript), Windows (PowerShell WinRT toast), Linux (notify-send)
- MCP server `instructions` so every thread pings you automatically
- Claude Desktop extension (`.mcpb`) with settings UI: language (en/ru/lt), sounds, mute
- Claude Code plugin + marketplace
- `--test` CLI mode
