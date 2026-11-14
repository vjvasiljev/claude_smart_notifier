---
id: t-te9a
title: Подключить Фундамент
type: chore
status: in_progress
priority: 1
role: executor
size: m
parent:
blocked_by: []
from:
workstream:
area: [setup]
assignee: fundament-setup
claimed: 2026-11-14T21:43:01Z
due:
question:
repeat:
source:
created: 2026-11-14
closed:
not_before:
---
## Что сделать

Подключить проект к Фундаменту 2.1.1 по эталону vjvasiljev/Skill-spawner: скрипты, доска, CLAUDE.md, проверки, Actions.

## Готово, когда

В main лежат tools/tasks.py, tools/check.py, VERSION-etalon, тесты стенда (PASS), fundament.cfg, docs/tasks, docs/workstreams/setup.md, CLAUDE.md, check-commands.txt; CI игнорирует docs/tasks и docs/workstreams.

## Как проверить

python3 tests/stand.py --quick: всё PASS; python3 tools/check.py --title 't-…: Подключить Фундамент' зелёный; python3 tools/tasks.py board без ошибок.

## Журнал


## Результат
