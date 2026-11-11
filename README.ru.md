<p align="center">
  <img src="icon.png" width="120" alt="Claude Smart Notifier">
</p>

<h1 align="center">Claude Smart Notifier</h1>

<p align="center">
  <b>Больше ни одна ветка Claude не будет ждать вас молча.</b><br>
  Системные уведомления, когда ветка закончила задачу или ждёт вашего ответа.
</p>

<p align="center"><img src="assets/demo.gif" width="760" alt="Демо Claude Smart Notifier"></p>

https://github.com/user-attachments/assets/5da68f17-e8fd-4366-bc6e-96da649fcef8

<p align="center"><a href="README.md">English</a></p>

---

## Проблема

Пять веток Claude в трёх проектах. Одна закончила 10 минут назад и ждёт решения, а вы узнаёте об этом, только когда случайно в неё заходите. Работа стоит.

## Решение

Каждая ветка присылает уведомление: **название проекта** и **одна короткая строка**, что от вас нужно. Подробности остаются в чате.

```
✅  Редизайн сайта       Готово        Главная готова, посмотри
🟡  Отчёт за квартал     Нужен ответ   Брать цифры марта или апреля?
🔴  Мобильное приложение Срочно        Сборка упала — нужен API-ключ
```

- Работает в **Claude Desktop** (чаты, проекты, Cowork) и **Claude Code**
- **macOS** и **Windows**

> **Нужны тестировщики на Windows.** Версия для Windows написана, но ещё не проверена на реальном компьютере. Если у вас Windows, попробуйте и отпишитесь в [issue #1](https://github.com/vjvasiljev/claude_smart_notifier/issues/1).
- Установка **в один клик**, настройки прямо в интерфейсе Claude
- **Без зависимостей**, без аккаунтов и серверов, текст уведомлений не покидает компьютер
- **Сообщает об обновлениях**: раз в сутки проверяет GitHub и присылает уведомление о новой версии (можно отключить)
- **Настройка один раз**: одна строка в инструкциях Claude, и вас зовёт каждая ветка в каждом проекте

## Установка

### Claude Desktop (Mac / Windows)

1. Скачайте **[claude-smart-notifier.mcpb](https://github.com/vjvasiljev/claude_smart_notifier/releases/latest/download/claude-smart-notifier.mcpb)**
2. Кликните дважды, потом нажмите **Install**
3. Язык подхватится из системы автоматически (`auto`). Поменять можно в *Settings → Extensions → Claude Smart Notifier*

> **Нужно ли класть файлы на компьютер?** Нет. `.mcpb` — это расширение Claude Desktop: Claude сам его ставит и запускает своим встроенным Node.js. Когда выйдет новая версия, придёт уведомление: скачайте новый `.mcpb` из Releases и установите поверх.

Откройте **новую** ветку, и готово.

### Чтобы звал каждый проект и каждая ветка

- **Claude Code (плагин): ничего делать не нужно.** Встроенные хуки сами зовут вас, когда сессия закончила, задала вопрос или просит разрешение. Работает всегда, без участия модели.
- **Claude Desktop / Cowork / Проекты (.mcpb): одна строка, один раз.** Desktop подгружает инструменты расширений по требованию и не передаёт веткам инструкции сервера, поэтому модели нужно сказать явно. При первом запуске расширение само об этом напомнит.

Для Claude Desktop вставьте в **Settings → Your Claude → Instructions** (действует на все чаты и проекты):

> Always: when you finish a task, and whenever you need my answer, decision, data or access, call the `notify` tool (Claude Smart Notifier) once as your very last action — this is required in every chat and project. The tool is often deferred: if it isn't loaded, load it first with tool search (query "notify"). Arguments: title = project name, level = done / question / urgent, lang = your reply language, message = max 40 chars saying what I must do. Only if no notify tool exists at all (phone or web without my computer), skip it silently.

После этого откройте **новую** ветку.

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
- **Mac: уведомления копятся в Центре уведомлений, но баннера нет.** Идёт запись или трансляция экрана: macOS в это время прячет баннеры. Остановите запись или включите *Уведомления → Разрешать уведомления при повторе или общем доступе к экрану*.
- **Windows:** *Параметры → Система → Уведомления* → включить, «Фокусировку внимания» выключить.
- **Ветка не позвала:** уже открытые ветки видят инструмент только после перезапуска Claude. Для надёжности можно добавить в инструкции проекта: «Когда закончил или нужен мой ответ — вызови notify».

## Лицензия

MIT. Проект не связан с Anthropic.
