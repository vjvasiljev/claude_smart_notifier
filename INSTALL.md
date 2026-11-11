# INSTALL.md: instructions for an AI agent

> You are an AI assistant (Claude Desktop / Cowork / Claude Code) and the user asked you to install **Claude Smart Notifier** from this repository. Follow the section that matches your environment. Ask the user before any step that needs their click or approval. Never edit the Claude Desktop config file directly; the extension installer does it.

## A. Claude Code (you have a terminal on the user's machine)

Tell the user to run these two slash commands in Claude Code (you cannot run slash commands yourself):

```text
/plugin marketplace add vjvasiljev/claude_smart_notifier
/plugin install smart-notifier@claude-smart-notifier
```

Then ask them to restart Claude Code. Verify by calling the `notify` tool:
`notify(title="Smart Notifier", message="Installed ✔", level="done")`.

If the plugin system is unavailable, fall back to:
```bash
git clone https://github.com/vjvasiljev/claude_smart_notifier.git ~/.claude-smart-notifier
claude mcp add --scope user smart-notifier -- node ~/.claude-smart-notifier/server/index.js
```

## B. Claude Desktop / Cowork

1. Download the latest bundle to the user's **Downloads** folder:
   `https://github.com/vjvasiljev/claude_smart_notifier/releases/latest/download/claude-smart-notifier.mcpb`
   (If your shell cannot reach GitHub, use a browser tool, or give the user this link to click.)
2. Open the file so Claude Desktop shows its install dialog:
   - macOS: `open ~/Downloads/claude-smart-notifier.mcpb`
   - Windows: `start "" "%USERPROFILE%\Downloads\claude-smart-notifier.mcpb"`
   - If you cannot run commands on the host, ask the user to double-click the downloaded file.
3. Ask the user to click **Install** in the dialog.
4. Optional: tell the user they can pick the label language (`en` / `ru` / `lt`) in *Settings → Extensions → Claude Smart Notifier*.
5. Offer to add this line to *Settings → Your Claude → Instructions* (required in Claude Desktop, where the tool may be deferred): see the README section "Make every project and thread ping you".
6. Tell the user to start a **new** thread (existing threads don't see new tools), then verify with
   `notify(title="Smart Notifier", message="Installed ✔", level="done")`.

## C. Troubleshooting to report to the user

- macOS shows nothing: *System Settings → Notifications → Script Editor* → allow; Focus/DND off.
- Windows shows nothing: *Settings → System → Notifications* on; Focus Assist off.
