# Changelog

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
