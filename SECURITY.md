# Security

The server runs locally, has no network access, stores nothing, and only executes the OS notification command (`osascript`, `powershell.exe`, or `notify-send`) with arguments passed safely (argv / base64), never through a shell.

Found a problem? Please open a private security advisory on GitHub instead of a public issue.
