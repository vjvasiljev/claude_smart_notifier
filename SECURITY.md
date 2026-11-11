# Security

The server runs locally, makes one daily version check to GitHub (opt-out), never downloads or runs code, and only executes the OS notification command (`osascript`, `powershell.exe`, or `notify-send`) with arguments passed safely (argv / base64), never through a shell.

Found a problem? Please open a private security advisory on GitHub instead of a public issue.
