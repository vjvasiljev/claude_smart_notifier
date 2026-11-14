# Claude Smart Notifier

Десктопные уведомления для веток Claude (Claude Desktop, Cowork, Claude Code): MCP-сервер `notify` с уровнями done / question / urgent. Open source, MIT, для владельца и друзей.

## Работа (Фундамент 2.1)

- Задачи: `docs/tasks/`, только через `python3 tools/tasks.py` (prime, claim, land, ready, board).
- Перед PR: `python3 tools/check.py --title "<id>: …"`, вывод в описание PR.
- Процедуры: скилл `fundament`. Постоянные правила: инструкции проекта.
- Знания по направлениям: `docs/workstreams/<area>.md`; пиши только в файл своей области.
- В main напрямую ничего, кроме карточек. `--force` и force-push запрещены.
- Не трогать `tools/check*.py`, `tools/tasks.py`, `tools/VERSION-etalon` вне задачи про эталон.

## Стек и команды

- Node.js ≥ 16, без зависимостей. Упаковка: `npx -y @anthropic-ai/mcpb pack . dist/claude-smart-notifier.mcpb`.
- Установка: не нужна.
- Запуск локально: `node server/index.js --test` (три тестовых уведомления).
- Линтер / сборка / тесты: в `tools/check-commands.txt`.

## Устройство

- `server/index.js` — весь сервер: MCP stdio, уведомления (macOS osascript, Windows toast, Linux notify-send), хуки Claude Code, проверка обновлений.
- `manifest.json` — расширение Claude Desktop (.mcpb), настройки пользователя.
- `.claude-plugin/`, `.mcp.json`, `hooks/` — плагин и маркетплейс для Claude Code.
- `README.md`, `README.ru.md`, `INSTALL.md` (инструкция для агента, который ставит по ссылке), `PRIVACY.md`.
- `assets/` — превью, демо-GIF, промо-видео (в .mcpb не входит, см. `.mcpbignore`).

## Выкладка

- Наружу уходит GitHub Release: `.github/workflows/release.yml` сам собирает и публикует `.mcpb`, когда в main меняется `version` в `manifest.json`. Пользователи получают уведомление об обновлении в течение суток.
- Поэтому подъём версии в main = публикация. PR с изменением `version` сливается только после «да» владельца.
- Остальной код в main можно сливать без «да»: до подъёма версии он наружу не уходит (кроме README на странице GitHub).
- `[skip ci]`: Actions его уважают (стандарт GitHub). Пути `docs/tasks/**`, `docs/workstreams/**` исключены из CI.

## Нельзя

- Коммитить секреты, `.env`, базы, `.har`, `.DS_Store`, сборку `dist/` (`check.py` ловит).
- Добавлять зависимости в `server/` (обещание «zero dependencies» в README).
- Править файлы из `docs/tasks/frozen.txt`.
- Удалять что-либо без решения владельца.

## Подводные камни

- Подробности в `docs/workstreams/setup.md` и `docs/workstreams/notifier.md`.
