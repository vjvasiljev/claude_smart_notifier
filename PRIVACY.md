# Privacy Policy: Claude Smart Notifier

Claude Smart Notifier runs entirely on your computer.

- **Data collected:** none. The server stores nothing and has no analytics or telemetry.
- **Network:** one request per day to GitHub's public API (`api.github.com/repos/vjvasiljev/claude_smart_notifier/releases/latest`) to check for a newer version. It sends nothing about you except a standard User-Agent with the version number. Turn it off with the *Check for updates* setting (`NOTIFY_UPDATE_CHECK=false`).
- **Local file:** `~/.claude-smart-notifier.json` stores the last check time and latest version seen.
- **What it processes:** only the notification text Claude passes to the `notify` tool (title, short message, level, language code). This text goes straight to your operating system's notification API (`osascript` on macOS, PowerShell toast on Windows, `notify-send` on Linux) and is not saved.
- **Credentials:** none are read or used.
- **Third parties:** none.

Questions: open an issue at https://github.com/vjvasiljev/claude_smart_notifier/issues
