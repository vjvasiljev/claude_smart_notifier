<p align="center">
  <img src="icon.png" width="120" alt="Claude Smart Notifier">
</p>

<h1 align="center">Claude Smart Notifier</h1>

<p align="center">
  <b>Больше ни одна ветка Claude не будет ждать вас молча.</b><br>
  Системные уведомления, когда ветка закончила задачу или ждёт вашего ответа.
</p>

<p align="center"><a href="README.md">English</a></p>

---

## Проблема

Пять веток Claude в трёх проектах. Одна закончила 10 минут назад и ждёт решения, а вы узнаёте об этом, только когда случайно в неё заходите. Работа стоит.

## Решение

Каждая ветка присылает уведомление: **название проекта** и **одна короткая строка**, что от вас нужно. Подробности остаются в чате.

```
✅  IKI 467              Готово        Смета готова, проверь цены
🟡  Дата-центры Nordic   Нужен ответ   Отправить оффер в 3 компании?
🔴  Интернет-магазин     Срочно        WordPress не пускает — дай логин
```

- Работает в **Claude Desktop** (чаты, проекты, Cowork) и **Claude Code**
- **macOS** и **Windows**
- Установка **в один клик**, настройки прямо в интерфейсе Claude
- **Без зависимостей**, без аккаунтов и серверов, ничего не уходит с компьютера
- Сервер сам объясняет каждой ветке, когда и как вас звать, так что промпты править не надо

## Установка

### Claude Desktop (Mac / Windows)

1. Скачайте **[claude-smart-notifier.mcpb](https://github.com/vjvasiljev/claude_smart_notifier/releases/latest/download/claude-smart-notifier.mcpb)**
2. Кликните дважды, потом нажмите **Install**
3. В *Settings → Extensions → Claude Smart Notifier* поставьте язык **ru**

Откройте **новую** ветку, и готово.

### Claude Code

```text
/plugin marketplace add vjvasiljev/claude_smart_notifier
/plugin install smart-notifier@claude-smart-notifier
```

### Попросить Claude установить

Вставьте в Claude:

> Установи мне Claude Smart Notifier: https://github.com/vjvasiljev/claude_smart_notifier — следуй INSTALL.md из репозитория.

## Если уведомления не приходят

- **Mac:** *Системные настройки → Уведомления → Script Editor* → разрешить. Выключите «Не беспокоить».
- **Windows:** *Параметры → Система → Уведомления* → включить, «Фокусировку внимания» выключить.
- **Ветка не позвала:** уже открытые ветки видят инструмент только после перезапуска Claude. Для надёжности можно добавить в инструкции проекта: «Когда закончил или нужен мой ответ — вызови notify».

## Лицензия

MIT. Проект не связан с Anthropic.
