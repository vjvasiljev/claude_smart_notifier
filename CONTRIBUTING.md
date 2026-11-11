# Contributing

Thanks for helping! This project is intentionally tiny: one file, zero dependencies.

## Dev setup

```bash
git clone https://github.com/vjvasiljev/claude_smart_notifier.git
cd claude_smart_notifier
node server/index.js --test        # shows 3 notifications
```

Pack the Desktop extension:

```bash
npm i -g @anthropic-ai/mcpb
mcpb validate manifest.json
mcpb pack . dist/claude-smart-notifier.mcpb
```

## Rules

- Keep **zero runtime dependencies**.
- Test on the platform you change (macOS / Windows / Linux) and say so in the PR.
- Keep notification text short; that's the whole point.
- Bump the version in `manifest.json`, `package.json`, `.claude-plugin/plugin.json` and `server/index.js`, and add a CHANGELOG entry.

## Releasing

Create a GitHub Release with tag `vX.Y.Z` (Releases → Draft a new release → Publish). GitHub Actions builds `claude-smart-notifier.mcpb` and attaches it to the release.
