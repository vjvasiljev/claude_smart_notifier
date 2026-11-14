"""Стенд, часть «безопасность и правила» (2.1): по воротам на каждую находку аудита 2.0.5.

Б1 архив, Б2 секреты и файлы, Б4 отставший main и отказ push, В1 приоритеты, В2 гонка захвата,
В8 мелкие дефекты, В9 большая доска, В10 версия эталона, В11 --verified, intake и доска в общей папке.
"""
import json
import os
import re
import shutil
import time

from standlib import TOOLS, sh, gate, card, setup_repo, write, clone_branch, T, C


def new(w, args):
    return T(w, f"new {args} --done 'Готово' --verify 'Смотреть' --commit --push", ok=True).stdout.split()[0]


def squash(w, branch, title):
    sh(f"git pull -q && git merge -q --squash origin/{branch} && git commit -q -m '{title}' && git push -q", w)


def run(tmp):
    secrets(tmp)
    board_rules(tmp)
    branch_flow(tmp)
    inbox(tmp)
    big_board(tmp)
    v211(tmp)


# ------------------------------------------------------------------ Б2: секреты, файлы, правка проверок
def secrets(tmp):
    remote, w = setup_repo(tmp, "sf")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    write(os.path.join(w, "docs/tasks/frozen.txt"), "docs/old-todo.md\n")
    write(os.path.join(w, "docs/old-todo.md"), "- старое\n")
    write(os.path.join(w, "tools/check-commands.txt"), "test: test ! -f broken.flag\n")
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w)
    tid = new(w, "--title 'Работа'")

    def branch(name):
        d = clone_branch(tmp, remote, "sf-" + name, "claude/" + name)
        T(d, f"claim {tid} --no-push", ok=True)
        return d

    key = "sk-ant-api03-" + "abcdefghijklmnopqrstuvwxyz0123456789"
    a = branch("ru")
    write(os.path.join(a, "папка/файл с пробелом.txt"), f"ключ = {key}\n")
    write(os.path.join(a, "папка/ключ.pem"), "x\n")
    write(os.path.join(a, "папка/.env"), "A=1\n")
    sh("git add -A && git commit -q -m ru", a)
    r = C(a, f"--title '{tid}: ru' --skip-commands --no-fetch")
    gate("SF секрет в файле с русским именем и пробелом пойман",
         "FAIL секреты" in r.stdout and "папка/файл с пробелом.txt" in r.stdout, r.stdout[-600:])
    gate("SF .pem и .env во вложенной русской папке пойманы",
         "FAIL запрещённые файлы" in r.stdout and "папка/ключ.pem" in r.stdout and "папка/.env" in r.stdout, r.stdout[-600:])

    b = branch("gone")
    write(os.path.join(b, "app.py"), f"K = '{key}'\n")
    sh("git add -A && git commit -q -m add", b)
    write(os.path.join(b, "app.py"), "K = None\n")
    sh("git add -A && git commit -q -m remove", b)
    r = C(b, f"--title '{tid}: gone' --skip-commands --no-fetch")
    gate("SF секрет, добавленный и стёртый внутри ветки, пойман по истории",
         "FAIL секреты" in r.stdout and "app.py" in r.stdout, r.stdout[-600:])

    c = branch("frozen")
    sh("git rm -q docs/old-todo.md && git commit -q -m rm", c)
    r = C(c, f"--title '{tid}: rm' --skip-commands --no-fetch")
    gate("SF удаление замороженного файла — FAIL", "FAIL замороженные файлы: удалены: docs/old-todo.md" in r.stdout, r.stdout[-600:])

    d = branch("allow")
    write(os.path.join(d, "fixture.py"), f"K = '{key}'  # check:allow\n")
    sh("git add -A && git commit -q -m fix", d)
    r = C(d, f"--title '{tid}: allow' --skip-commands --no-fetch")
    gate("SF строка с check:allow даёт WARN ревьюеру, не молчит",
         "WARN check:allow" in r.stdout and "fixture.py" in r.stdout and "FAIL секреты" not in r.stdout, r.stdout[-600:])

    h = branch("hist")
    write(os.path.join(h, "fx.py"), f"K = '{key}'\n")
    sh("git add -A && git commit -q -m fx", h)
    sha = sh("git rev-parse HEAD", h).stdout.strip()
    write(os.path.join(h, "fx.py"), f"K = '{key}'  # check:allow\n")
    sh("git add -A && git commit -q -m mark", h)
    # строку-исключение вносят в main отдельным маленьким PR, раньше самой ветки
    write(os.path.join(w, "tools/check-allow.txt"), f"{sha[:8]} fx.py\n")
    sh("git add -A && git commit -q -m 'allow (#90)' && git push -q", w)
    sh("git fetch -q", h)
    r = C(h, f"--title '{tid}: hist' --skip-commands --no-fetch")
    gate("SF фикстура без пометки в промежуточном коммите: прощена по check-allow.txt, но с WARN",
         "FAIL секреты" not in r.stdout and "WARN фикстуры в истории ветки" in r.stdout and sha[:8] in r.stdout, r.stdout[-600:])

    v = branch("codeval")
    write(os.path.join(v, "settings.py"), "api_key = settings.ANTHROPIC_API_KEY\ntoken = self.get_token_value()\n"
          "SECRET_KEY = get_secret_from_vault()\npassword = request.form.password\naccess_token = response.json()\n")
    sh("git add -A && git commit -q -m code", v)
    r = C(v, f"--title '{tid}: code' --skip-commands --no-fetch")
    gate("SF обычный код (settings.X, get_token(), request.form…) — не секрет", "FAIL секреты" not in r.stdout, r.stdout[-500:])
    write(os.path.join(v, "app.ini"), "db_password = sup3r.s3cret.value\n")
    write(os.path.join(v, "conf/.env.local"), "API_TOKEN=abc.def(ghi)jklmnop\n")
    sh("git add -A && git commit -q -m conf", v)
    r = C(v, f"--title '{tid}: code' --skip-commands --no-fetch")
    gate("SF в .env*, *.ini, *.cfg, *.properties значение с точками — всё равно секрет",
         "app.ini (bare-secret)" in r.stdout and "conf/.env.local (bare-secret)" in r.stdout, r.stdout[-500:])

    x = branch("selfallow")
    write(os.path.join(x, "app.py"), f"K = '{key}'\n")
    sh("git add -A && git commit -q -m key", x)
    sx = sh("git rev-parse HEAD", x).stdout.strip()
    write(os.path.join(x, "app.py"), "K = None\n")
    write(os.path.join(x, "tools/check-allow.txt"), f"{sx[:8]} app.py\n")
    sh("git add -A && git commit -q -m hide", x)
    r = C(x, f"--title '{tid}: self' --skip-commands --no-fetch")
    gate("SF строка check-allow.txt из самой ветки ничего не прощает (список из main)",
         "FAIL секреты" in r.stdout and "app.py" in r.stdout, r.stdout[-500:])

    y = branch("cmds")
    write(os.path.join(y, "tools/check-commands.txt"), "test: true\n")
    sh("git add -A && git commit -q -m cmds", y)
    r = T(y, f"land {tid} --result 'cmds' --no-push")
    gate("SF правка tools/check-commands.txt — код: land требует --verified", r.returncode == 2 and "--verified" in r.stderr, r.stderr)

    e = branch("patterns")
    write(os.path.join(e, "db.py"), "URL = 'postgres://admin:hunter2pass@db.example.com:5432/app'\n")  # check:allow
    write(os.path.join(e, "pay.py"), "STRIPE = '" + "sk_live_" + "abcdefghijklmnop1234'\n")
    write(os.path.join(e, "deploy.sh"), "export DB_PASSWORD=Sup3rSecretValue99\n")
    write(os.path.join(e, "credentials.json"), "{}\n")
    write(os.path.join(e, "ok.sh"), "export DB_PASSWORD=${DB_PASSWORD}\nURL='postgres://user:changeme@localhost/x'\n")
    sh("git add -A && git commit -q -m p", e)
    r = C(e, f"--title '{tid}: p' --skip-commands --no-fetch")
    gate("SF новые шаблоны: строка подключения, sk_live_, пароль без кавычек",
         all(f"{f} (" in r.stdout for f in ("db.py", "pay.py", "deploy.sh")), r.stdout[-700:])
    gate("SF credentials.json — запрещённый файл", "credentials.json" in r.stdout and "FAIL запрещённые файлы" in r.stdout, r.stdout[-500:])
    gate("SF заглушки (${VAR}, changeme) не считаются секретом", "ok.sh" not in r.stdout, r.stdout[-500:])

    f = branch("weak")
    write(os.path.join(f, "tools/check.py"), "import sys\nprint('### check.py: OK')\nsys.exit(0)\n")
    write(os.path.join(f, "tools/check-commands.txt"), "test: true\n")
    write(os.path.join(f, "broken.flag"), "x\n")
    write(os.path.join(f, "app.py"), f"K = '{key}'\n")
    sh("git add -A && git commit -q -m weak", f)
    r = C(f, f"--title '{tid}: weak' --no-fetch")
    gate("SF ветка, подменившая check.py, сама себе даёт OK (поэтому ревьюер так не проверяет)", r.returncode == 0, r.stdout[-300:])
    # ревьюер берёт check.py из main, а не из ветки: так ветка не подменит и саму команду
    sh("git show origin/main:tools/check.py > ../ref-check.py", f)
    r = sh(f"python3 ../ref-check.py --tools-from-main --title '{tid}: weak' --no-fetch", f, ok=False)
    gate("SF --tools-from-main: проверка скриптами из main ловит секрет и правку проверок",
         r.returncode == 1 and "скриптами из origin/main" in r.stdout and "FAIL секреты" in r.stdout
         and "WARN правка проверок" in r.stdout and "tools/check.py" in r.stdout, r.stdout[-700:])
    gate("SF команды тестов берутся из main: подмена check-commands.txt не помогает",
         "FAIL test: test ! -f broken.flag" in r.stdout, r.stdout[-700:])

    g = branch("docs")
    write(os.path.join(g, "docs/workstreams/a.md"), "знание\n")
    sh("git add -A && git commit -q -m d", g)
    r = C(g, f"--title '{tid}: знания' --skip-commands --no-fetch")
    gate("SF PR только с docs/ без [skip ci] в заголовке — WARN", "WARN skip ci" in r.stdout, r.stdout[-400:])
    r = C(g, f"--title '{tid}: знания [skip ci]' --skip-commands --no-fetch")
    gate("SF с [skip ci] предупреждения нет", "WARN skip ci" not in r.stdout, r.stdout[-400:])

    write(os.path.join(tmp, "etalon.txt"), "9.9.9\n")
    r = sh("python3 tools/check.py --weekly --no-fetch", w, {"TASKS_ETALON": os.path.join(tmp, "etalon.txt")}, ok=False)
    gate("SF weekly: эталон новее — WARN «обновить»", "WARN версия" in r.stdout and "9.9.9" in r.stdout, r.stdout[-400:])


# ------------------------------------------------------------------ В1, Б3, В8: правила доски
def board_rules(tmp):
    remote, w = setup_repo(tmp, "sb")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    cards = [
        card("t-1000", "Мелочь", priority=3, created="2026-11-01"),
        card("t-1001", "Средняя", priority=1, created="2026-11-02"),
        card("t-1002", "Срочная", priority=0, blocked="t-1000", created="2026-11-03"),
        card("t-2000", "Корень цепи", priority=4, created="2026-11-01"),
        card("t-2001", "Звено цепи", priority=4, blocked="t-2000", created="2026-11-01"),
        card("t-2002", "Хвост цепи", priority=0, blocked="t-2001", created="2026-11-01"),
        card("t-3000", "Держит пятничную", priority=2, created="2026-11-01"),
        card("t-3001", "Пятничная", priority=2, blocked="t-3000", due="2026-11-20", created="2026-11-01"),
        card("t-3002", "Обычная со сроком позже", priority=2, due="2026-11-25", created="2026-11-01"),
        card("t-4000", "Эпик", typ="epic", created="2026-11-01"),
        card("t-4001", "Дитя эпика", status="closed", parent="t-4000", created="2026-11-01"),
    ]
    for c in cards:
        cid = c.split("id: ")[1].split("\n")[0]
        write(os.path.join(w, f"docs/tasks/{cid}-x.md"), c)
    with open(os.path.join(w, "docs/tasks/t-5000-bad.md"), "wb") as fh:
        fh.write(card("t-5000", "Битая кодировка").encode("utf-8").replace("Битая".encode("utf-8"), b"\xc1\xe8\xf2\xe0\xff"))
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w)
    r = T(w, "ready")
    lines = [ln.split()[0] for ln in r.stdout.splitlines() if ln.startswith("t-")]
    gate("SB битый по кодировке файл не валит ready", r.returncode == 0 and lines, r.stderr[-300:])
    gate("SB p0 ждёт p3: мелочь первая", lines[:1] == ["t-1000"] or lines[:2] in (["t-2000", "t-1000"], ["t-1000", "t-2000"]), str(lines))
    gate("SB причина видна: «p3→p0 (держит t-1002)»", "p3→p0 (держит t-1002)" in r.stdout, r.stdout)
    gate("SB цепочка из трёх: корень p4 встаёт к p0", lines.index("t-2000") < lines.index("t-1001"), str(lines))
    gate("SB срок наследуется: держащая пятничную раньше задачи со сроком 25-го",
         lines.index("t-3000") < lines.index("t-3002") and "срок 2026-11-20 (от t-3001)" in r.stdout, r.stdout)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("SB на доске раздел «Срочное ждёт»: t-1002 из-за t-1000",
         any(x["id"] == "t-1002" and "t-1000" in x["waits"][0] for x in rb["urgent_waiting"]), str(rb["urgent_waiting"]))
    chk = T(w, "check").stdout
    gate("SB битая кодировка — WARN bad-encoding", "WARN bad-encoding" in chk, chk[-400:])
    gate("SB эпик с закрытыми детьми — подсказка закрыть", "epic-done" in chk and "t-4000" in chk, chk[-400:])

    # не раньше
    nb = T(w, "new --title 'Позже' --not-before 2026-11-20 --done 'Г' --verify 'С' --commit --push", ok=True).stdout.split()[0]
    rr = [x["id"] for x in json.loads(T(w, "ready --json", ok=True).stdout)]
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("SB new --not-before: не выдаётся до даты, виден в «Отложены»",
         nb not in rr and nb in [x["id"] for x in rb["deferred"]], str(rr))
    rr = [x["id"] for x in json.loads(sh("python3 tools/tasks.py ready --json", w, {"TASKS_NOW": "2026-11-20T09:00:00Z"}).stdout)]
    gate("SB new --not-before: с даты выдаётся", nb in rr, str(rr))

    # грязный ввод
    r = T(w, "new --title 'Две\nстроки' --done 'Готово\n## Журнал\nподделка' --verify 'С' --commit --push", ok=True)
    nid = r.stdout.split()[0]
    path = [f for f in os.listdir(os.path.join(w, "docs/tasks")) if f.startswith(nid)][0]
    txt = open(os.path.join(w, "docs/tasks", path), encoding="utf-8").read()
    gate("SB перенос строки в --title не ломает шапку", "title: Две строки\n" in txt, txt[:300])
    gate("SB «## Журнал» внутри --done не создаёт второй раздел", txt.count("\n## Журнал") == 1, txt)
    gate("SB после грязного ввода check без FAIL", "ошибок 0" in T(w, "check").stdout)

    # land на main и чужая карточка
    r = T(w, "land t-1001 --result x")
    gate("SB land на main отказывает", r.returncode == 2 and "в ветке задачи" in r.stderr, r.stderr)
    a = clone_branch(tmp, remote, "sb-a", "claude/a")
    fid = T(a, "new --title 'Только в ветке a' --done 'Г' --verify 'С' --commit", ok=True).stdout.split()[0]
    sh("git push -q -u origin HEAD", a)
    o = clone_branch(tmp, remote, "sb-o", "claude/o")
    r1, r2 = T(o, f"set {fid} priority=1"), T(o, f"ask {fid} --question 'Что?' --no-push")
    gate("SB set/ask по карточке чужой ветки: понятный отказ, без трассы Python",
         r1.returncode == 2 and r2.returncode == 2 and "Traceback" not in r1.stderr + r2.stderr
         and "только в ветке claude/a" in r1.stderr, r1.stderr + r2.stderr)

    # --force мимо «ждёт владельца»
    T(w, "set t-1001 status=needs_human question=Деньги? --commit --push", ok=True)
    f = clone_branch(tmp, remote, "sb-f", "claude/f")
    r = T(f, "claim t-1001 --force --no-push")
    gate("SB --force в ветке не обходит «ждёт владельца»", r.returncode == 2 and "только у координатора" in r.stderr, r.stderr)


# ------------------------------------------------------------------ Б1, Б4, В2, В11, повторный land
def branch_flow(tmp):
    remote, w = setup_repo(tmp, "sw")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    write(os.path.join(w, "docs/tasks/t-0old-x.md").replace("t-0old", "t-a0ld"),
          card("t-a0ld", "Старая закрытая", status="closed").replace("2026-11-10T10:00Z", "2026-09-01T10:00Z"))
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w)
    t1 = new(w, "--title 'Первая' --area x1")
    t2 = new(w, "--title 'Вторая' --area x2")
    t3 = new(w, "--title 'Еженедельная' --repeat weekly --due 2026-11-14 --area x3")
    tc = new(w, "--title 'Код' --area x4")
    tm = new(w, "--title 'Механика' --role mechanic --area x5")

    # Б1: архив в ветке
    m = clone_branch(tmp, remote, "sw-m", "claude/arch")
    T(m, f"claim {t2}", ok=True)
    T(m, "archive --commit", ok=True)
    sh("git push -q origin HEAD", m)
    o = clone_branch(tmp, remote, "sw-o", "claude/other")
    T(o, f"claim {t1}", ok=True)
    r1 = C(m, f"--title '{t2}: архив' --skip-commands")
    r2 = C(o, f"--title '{t1}: x' --skip-commands")
    gate("SW архив в ветке: своя проверка без dup-id", "dup-id" not in r1.stdout, r1.stdout[-500:])
    gate("SW архив в ветке: чужая проверка без dup-id", "dup-id" not in r2.stdout, r2.stdout[-500:])
    # архив координатором прямо в main с --push
    T(w, "archive --commit --push", ok=True)
    gate("SW archive --commit --push на main уходит на GitHub",
         "archive/2026-09/t-a0ld-x.md" in sh("git ls-tree -r --name-only origin/main", w).stdout)

    # Б4: отставший main и отказ push
    c2 = clone_branch(tmp, remote, "sw-c2", "main-copy")
    sh("git checkout -q main && git branch -q -D main-copy", c2)
    a = clone_branch(tmp, remote, "sw-a", "claude/a")
    T(a, f"claim {t1} --force", ok=False)
    sh(f"git checkout -q main && git pull -q", w)
    sh(f"git -C {w} checkout -q main", tmp)
    # закрываем t1 «слиянием» из другой копии main
    sh("git pull -q", c2)
    p = [f for f in os.listdir(os.path.join(c2, "docs/tasks")) if f.startswith(t1)][0]
    txt = open(os.path.join(c2, "docs/tasks", p), encoding="utf-8").read().replace("status: open", "status: closed")
    write(os.path.join(c2, "docs/tasks", p), txt.replace("## Результат\n\n", "## Результат\n\nСделано.\n"))
    sh(f"git commit -qam '{t1}: x (#5)' && git push -q", c2)
    rr = [x["id"] for x in json.loads(T(w, "ready --json", ok=True).stdout)]
    gate("SW отставший main сам догоняет GitHub и не выдаёт закрытое", t1 not in rr, str(rr))
    sh("git commit -q --allow-empty -m 'чужое слияние (#6)' && git push -q", c2)
    r = T(w, "new --title 'После чужого слияния' --done 'Г' --verify 'С' --commit --push")
    gate("SW new --push после чужого слияния проходит (rebase и повтор)",
         r.returncode == 0 and "отправлено на GitHub" in r.stdout, r.stdout + r.stderr)

    # В2: гонка захвата
    g1 = clone_branch(tmp, remote, "sw-g1", "claude/g1")
    g2 = clone_branch(tmp, remote, "sw-g2", "claude/g2")
    sh("git fetch -q", g2)
    T(g1, f"claim {t2}", ok=False)   # t2 занята claude/arch — берём другую
    tr = new(w, "--title 'Гонка' --area x9")
    sh("git pull -q --rebase origin main", g1)
    sh("git pull -q --rebase origin main", g2)
    r1 = T(g1, f"claim {tr}")
    r2 = sh(f"python3 tools/tasks.py --no-fetch claim {tr}", g2, ok=False)   # не видел захват g1
    gate("SW гонка: поздний захват уступает сразу", r1.returncode == 0 and r2.returncode == 2 and "гонка" in r2.stderr,
         r1.stderr + r2.stdout + r2.stderr)
    chk = T(w, "check").stdout
    gate("SW гонка: на доске один захват", "double-claim" not in chk, chk[-400:])

    # В11 --verified и mechanic
    k = clone_branch(tmp, remote, "sw-k", "claude/k")
    T(k, f"claim {tc}", ok=True)
    write(os.path.join(k, "app.py"), "print(1)\n")
    sh("git add -A && git commit -q -m code", k)
    r = T(k, f"land {tc} --result 'app.py' --no-push")
    gate("SW правка кода без --verified не садится", r.returncode == 2 and "--verified" in r.stderr, r.stderr)
    r = T(k, f"land {tc} --result 'app.py' --verified 'python3 app.py → 1' --no-push")
    txt = open(os.path.join(k, "docs/tasks", [f for f in os.listdir(os.path.join(k, "docs/tasks")) if f.startswith(tc)][0]),
               encoding="utf-8").read()
    gate("SW с --verified садится, в журнале «Проверено:»", r.returncode == 0 and "Проверено: python3 app.py → 1" in txt, r.stderr)
    r = C(k, f"--title '{tc}: код' --skip-commands --no-fetch")
    gate("SW check видит «Проверено» в журнале", "OK проверено" in r.stdout, r.stdout[-400:])
    mm = clone_branch(tmp, remote, "sw-mm", "claude/mm")
    T(mm, f"claim {tm}", ok=True)
    write(os.path.join(mm, "lib.py"), "x = 1\n")
    sh("git add -A && git commit -q -m code", mm)
    chk = T(mm, "check").stdout
    gate("SW mechanic меняет код — WARN", "WARN mechanic-code" in chk, chk[-400:])

    # повторный land повторяющейся
    rp = clone_branch(tmp, remote, "sw-rp", "claude/rp")
    T(rp, f"claim {t3}", ok=True)
    T(rp, f"land {t3} --result 'раз' --no-push", ok=True)
    T(rp, f"land {t3} --result 'два' --no-push", ok=True)
    files = sh("git diff --name-only origin/main", rp).stdout.split()
    nxt = [f for f in files if f.startswith("docs/tasks/") and t3 not in f]
    gate("SW повторный land повторяющейся: следующая карточка одна", len(nxt) == 1, str(files))


# ------------------------------------------------------------------ координатор без оболочки: inbox и доска в общей папке
def inbox(tmp):
    remote, w = setup_repo(tmp, "si")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w)
    shared = os.path.join(tmp, "project-files", "proj")
    ib = os.path.join(shared, "inbox")
    env = {"TASKS_INBOX": ib, "TASKS_BOARD_OUT": os.path.join(shared, "board.json")}
    write(os.path.join(ib, "2026-11-14-otchet.md"),
          "# Отчёт по продажам\npriority: 1\n\nСделать отчёт за неделю.\n\n## Готово, когда\n\nОтчёт лежит в docs/\n\n"
          "## Как проверить\n\nОткрыть файл\n")
    write(os.path.join(ib, "2026-11-14-syroe.md"), "# Сырая мысль\n\nЧто-то про логотип.\n")
    write(os.path.join(ib, "2026-11-14-dengi.md"), "title: Купить домен\nowner: да\nquestion: Платим 12 евро за домен?\n")
    b = clone_branch(tmp, remote, "si-b", "claude/b")
    r = sh("python3 tools/tasks.py intake", b, env, ok=False)
    sh("git fetch -q", w)
    ls = lambda: [f for f in sh("git ls-tree -r --name-only origin/main docs/tasks", w).stdout.split() if f.endswith(".md")]
    gate("SI intake из ветки: три файла — три карточки в main", r.returncode == 0 and len(ls()) == 3, r.stdout + r.stderr)
    done = sorted(os.listdir(os.path.join(ib, "done")))
    gate("SI файлы перенесены в inbox/done с id в имени, не удалены",
         len(done) == 3 and all(re.match(r"t-[0-9a-z]{4}-2026-11-14-", f) for f in done)
         and not [f for f in os.listdir(ib) if f.endswith(".md")], str(done))
    sh("git pull -q", w)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("SI ничего не выдаётся сразу: обычные просьбы в inbox, owner: да — ждёт владельца",
         rb["counts"]["ready"] == 0 and rb["counts"]["inbox"] == 2 and rb["counts"]["owner"] == 1
         and "12 евро" in rb["owner"][0]["question"], json.dumps(rb["counts"]))
    ot = [x["id"] for x in rb["inbox"] if x["title"] == "Отчёт по продажам"]
    txt = sh(f"cat docs/tasks/{ot[0]}-*.md", w).stdout if ot else ""
    gate("SI шапка после «# заголовок» и разделы-критерии разобраны", "priority: 1" in txt and "Отчёт лежит в docs/" in txt, txt[:500])
    # тот же файл снова — дубля нет; то же имя с другим текстом — новая просьба
    shutil.copy(os.path.join(ib, "done", [f for f in done if "otchet" in f][0]), os.path.join(ib, "2026-11-14-otchet.md"))
    r = sh("python3 tools/tasks.py intake", b, env, ok=False)
    sh("git fetch -q", w)
    gate("SI тот же файл повторно ничего не дублирует", len(ls()) == 3 and "новых просьб нет" in r.stdout, r.stdout)
    write(os.path.join(ib, "2026-11-14-otchet.md"), "# Отчёт по возвратам\n\nДругая просьба с тем же именем файла.\n")
    r = sh("python3 tools/tasks.py intake", b, env, ok=False)
    sh("git fetch -q", w)
    otch = [f for f in os.listdir(os.path.join(ib, "done")) if "otchet" in f]
    gate("SI то же имя с другим текстом — новая карточка, в done/ ничего не перезаписано",
         len(ls()) == 4 and len(otch) == 3, str(otch) + r.stdout)
    # координатор оформляет и отвечает файлами
    sh("git pull -q", w)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    own = rb["owner"][0]["id"]
    write(os.path.join(ib, "2026-11-14-oformit.md"), f"id: {ot[0]}\nstatus: open\nrole: executor\n\nОформлено, можно брать.\n")
    write(os.path.join(ib, "2026-11-14-bez-otveta.md"), f"id: {own}\nstatus: open\n\nДумаю, можно.\n")
    write(os.path.join(ib, "2026-11-14-otvet.md"), f"id: {own}\nstatus: open\n"
          "owner_answer: Владелец 14.11 18:20 в чате проекта: «да, платим»\n\n"
          "## Готово, когда\n\nДомен куплен\n\n## Как проверить\n\nwhois\n")
    write(os.path.join(ib, "2026-11-14-mimo.md"), "id: t-zzzz\nstatus: open\n")
    r = sh("python3 tools/tasks.py intake", b, env, ok=False)
    sh("git pull -q", w)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    ready = [x["id"] for x in rb["ready"]]
    gate("SI файл «id: …» оформляет карточку: из inbox в готовые", ot[0] in ready, str(ready) + r.stdout)
    otv = sh(f"cat docs/tasks/{own}-*.md", w).stdout
    gate("SI ответ владельца файлом только с owner_answer: снят вопрос, цитата в журнале", own in ready
         and "ответ владельца из inbox]: Владелец 14.11 18:20" in otv and "\nquestion:\n" in otv, otv[-400:])
    gate("SI без owner_answer «ждёт владельца» не снимается: файл отложен в skipped/ с причиной",
         os.path.exists(os.path.join(ib, "skipped", "2026-11-14-bez-otveta.md")) and "нужен owner_answer" in r.stdout
         and "Думаю, можно" not in otv, r.stdout)
    chk = T(w, "check").stdout
    gate("SI открытое ответом из inbox видно WARN на доске и в weekly", f"WARN owner-answer-inbox: {own}" in chk
         and "owner-answer-inbox" in C(w, "--weekly --no-fetch").stdout, chk[-400:])
    gate("SI ответ на несуществующую карточку не теряется: файл в skipped/, причина в .why.txt",
         "t-zzzz нет в main" in open(os.path.join(ib, "skipped", "2026-11-14-mimo.md.why.txt"), encoding="utf-8").read(), r.stdout)
    bj = json.loads(sh("python3 tools/tasks.py --no-fetch board --json", w, env).stdout)
    gate("SI отложенные файлы видны на доске", sorted(x["file"] for x in bj["inbox_skipped"])
         == ["2026-11-14-bez-otveta.md", "2026-11-14-mimo.md"], str(bj["inbox_skipped"]))
    r = sh("python3 tools/tasks.py intake", b, env, ok=False)
    gate("SI отложенный файл не печатается при каждом intake", "t-zzzz" not in r.stdout, r.stdout)
    # push не прошёл — файлы остаются в inbox
    write(os.path.join(ib, "2026-11-15-net-seti.md"), "# Без сети\n")
    sh("git remote set-url --push origin /nonexistent/remote.git", b)
    r = sh("python3 tools/tasks.py intake", b, env, ok=False)
    sh(f"git remote set-url --push origin {remote}", b)
    gate("SI push в main не прошёл — файл остался в inbox, в done/ не ушёл",
         r.returncode == 2 and os.path.exists(os.path.join(ib, "2026-11-15-net-seti.md")), r.stdout + r.stderr)
    os.remove(os.path.join(ib, "2026-11-15-net-seti.md"))
    # prime сам зовёт intake; land кладёт доску в общую папку
    write(os.path.join(ib, "2026-11-15-eshche.md"), "title: Ещё одна\n")
    tid = rb["ready"][0]["id"]
    c = clone_branch(tmp, remote, "si-c", "claude/c")
    r = sh(f"python3 tools/tasks.py prime {tid}", c, env, ok=False)
    gate("SI prime сам переносит новые просьбы", "2026-11-15-eshche.md" in r.stdout, r.stdout[:400])
    sh(f"python3 tools/tasks.py claim {tid}", c, env)
    r = sh(f"python3 tools/tasks.py land {tid} --result 'docs/x.md'", c, env)
    gate("SI land пишет «дальше по очереди»", "дальше по очереди:" in r.stdout, r.stdout)
    shared_board = json.load(open(env["TASKS_BOARD_OUT"], encoding="utf-8"))
    mine = json.loads(sh("python3 tools/tasks.py --no-fetch board --json", c, env).stdout)
    strip = lambda d: {k: v for k, v in d.items() if k != "generated"}
    gate("SI доска в общей папке совпадает с board --json", strip(shared_board) == strip(mine),
         json.dumps(shared_board["counts"]) + json.dumps(mine["counts"]))
    # подмена часов только для стенда
    r = sh("python3 tools/tasks.py --no-fetch board --json", c, {"TASKS_STAND": "0", "TASKS_NOW": "2030-01-01T00:00:00Z"})
    gate("SI TASKS_NOW без TASKS_STAND=1 не действует", not json.loads(r.stdout)["generated"].startswith("2030"),
         json.loads(r.stdout)["generated"])


# ------------------------------------------------------------------ В9: большая доска
def big_board(tmp):
    remote, w = setup_repo(tmp, "sl")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    for i in range(1000):
        cid = "t-" + format(i, "04d").replace("0", "z")[:4]
        cid = f"t-{i:04d}"
        write(os.path.join(w, f"docs/tasks/{cid}-zadacha.md"),
              card(cid, f"Задача номер {i} с длинным названием для веса", priority=i % 5,
                   status="closed" if i % 3 == 0 else "open", blocked=f"t-{i - 1:04d}" if i % 7 == 0 and i else ""))
    sh("git add -A && git commit -q -m big && git push -q -u origin main", w)
    for j in range(20):
        d = clone_branch(tmp, remote, f"sl-{j}", f"claude/b{j}")
        cid = f"t-{j * 3 + 1:04d}"
        T(d, f"claim {cid} --force", ok=False)
        sh("git push -q -u origin HEAD", d, ok=False)
        if j:
            shutil_rm(d)
    probe = os.path.join(tmp, "sl-0")
    t0 = time.time()
    r = T(probe, "prime t-0001")
    dt = time.time() - t0
    gate(f"SL 1000 карточек и 20 веток: prime быстрее 5 с ({dt:.1f} с)", r.returncode == 0 and dt < 5, r.stderr[-300:])
    out = T(w, "board").stdout
    gate(f"SL вывод board меньше 6 КБ ({len(out.encode('utf-8')) // 1024} КБ)", len(out.encode("utf-8")) < 6 * 1024)


def shutil_rm(d):
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ 2.1.1: находки аудита 2.1.0
def v211(tmp):
    remote, w = setup_repo(tmp, "sv")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w)
    tid = new(w, "--title 'С хуками'")
    t2 = new(w, "--title 'Гонка в минуту'")
    t3 = new(w, "--title 'Гонка в минуту 2'")
    t4 = new(w, "--title 'Гонка обе после push'")
    t5 = new(w, "--title 'Чужой файл в индексе'")

    # Н3: хуки проекта (husky и т. п.) не ломают служебные команды
    h = clone_branch(tmp, remote, "sv-h", "claude/h")
    write(os.path.join(h, ".husky/pre-commit"), "#!/bin/sh\necho 'npm: not found' >&2\nexit 1\n")
    write(os.path.join(h, ".husky/pre-push"), "#!/bin/sh\nexit 1\n")
    write(os.path.join(h, ".husky/commit-msg"), "#!/bin/sh\nexit 1\n")
    sh("chmod +x .husky/* && git config core.hooksPath .husky", h)
    r1 = T(h, f"claim {tid}")
    r2 = T(h, f"ask {tid} --question 'Как?'")
    T(h, f"claim {tid}")
    r3 = T(h, f"land {tid} --result 'x' --verified 'хуки'")
    gate("SV падающие хуки git: claim, ask, land проходят и уходят на GitHub",
         all(r.returncode == 0 for r in (r1, r2, r3)) and "отправлено на GitHub" in r3.stdout,
         (r1.stderr + r2.stderr + r3.stderr)[-500:])
    lk = clone_branch(tmp, remote, "sv-lk", "claude/lk")
    write(os.path.join(lk, ".git/index.lock"), "")
    r = T(lk, f"claim {t2}")
    gate("SV отказ git — понятный текст, без трассы Python", r.returncode == 2 and "Traceback" not in r.stderr
         and "git не выполнил команду" in r.stderr, r.stderr[-400:])

    # Н2: два захвата в одну минуту, в любом порядке имён — остаётся один
    for first, second, cid in (("zz", "aa", t2), ("aa", "zz", t3)):
        a1 = clone_branch(tmp, remote, f"sv-{first}-{cid}", f"claude/{first}-{cid}")
        a2 = clone_branch(tmp, remote, f"sv-{second}-{cid}", f"claude/{second}-{cid}")
        T(a1, f"claim {cid}", ok=True)
        r = sh(f"python3 tools/tasks.py --no-fetch claim {cid}", a2, ok=False)   # тот же момент, чужого не видел
        gate(f"SV гонка в одну секунду ({first} раньше {second}): второй уступает", r.returncode == 2 and "гонка" in r.stderr,
             r.stdout + r.stderr)
    # ничья в одну секунду, обе проверяют уже после обоих push: задачу держит ровно одна
    import subprocess as sp
    b1 = clone_branch(tmp, remote, "sv-p1", "claude/p1")
    b2 = clone_branch(tmp, remote, "sv-p2", "claude/p2")
    env = dict(os.environ, TASKS_NOW="2026-11-14T12:00:00Z", TASKS_STAND="1", TASKS_SHARED="/nonexistent-shared",
               GIT_AUTHOR_NAME="stand", GIT_AUTHOR_EMAIL="s@example.invalid",
               GIT_COMMITTER_NAME="stand", GIT_COMMITTER_EMAIL="s@example.invalid")
    ps = [sp.Popen(f"python3 tools/tasks.py --no-fetch claim {t4}", cwd=d, shell=True, env=env,
                   stdout=sp.PIPE, stderr=sp.PIPE, text=True) for d in (b1, b2)]
    codes = [p.wait() for p in ps]
    sh("git fetch -q origin", w)
    held = [br for br in ("claude/p1", "claude/p2")
            if re.search(r"^status: in_progress", sh(f"git show origin/{br}:$(git ls-tree -r --name-only origin/{br} "
                                                     f"docs/tasks | grep {t4})", w).stdout, re.M)]
    gate("SV гонка в одну секунду, обе проверяют после обоих push: держит ровно одна",
         len(held) == 1 and sorted(codes) == [0, 2], f"{held} {codes}")

    # служебный коммит не забирает чужой застейдженный файл (его мог отклонить pre-commit)
    st = clone_branch(tmp, remote, "sv-st", "claude/st")
    write(os.path.join(st, "leak.txt"), "чужое\n")
    sh("git add leak.txt", st)
    T(st, f"claim {t5}", ok=True)
    files = sh("git ls-tree -r --name-only origin/claude/st", st).stdout
    staged = sh("git diff --cached --name-only", st).stdout
    gate("SV claim не коммитит и не отправляет чужой застейдженный файл",
         "leak.txt" not in files and "leak.txt" in staged, files[-300:] + staged)

    chk = T(w, "check").stdout
    gate("SV после гонок на доске нет двойного захвата", "double-claim" not in chk, chk[-400:])

    # Н1: вопрос владельцу из inbox в три строки не ломает проверку остальным
    shared = os.path.join(tmp, "sv-shared", "proj")
    env = {"TASKS_INBOX": os.path.join(shared, "inbox")}
    write(os.path.join(shared, "inbox", "q.md"), "title: Домен\nowner: да\nquestion: Платим 12 евро?\n")
    o = clone_branch(tmp, remote, "sv-o", "claude/o")
    sh("python3 tools/tasks.py intake", o, env)
    o2 = clone_branch(tmp, remote, "sv-o2", "claude/o2")
    t4 = new(w, "--title 'Другая работа'")
    sh("git pull -q --rebase origin main", o2)
    T(o2, f"claim {t4}", ok=True)
    r = C(o2, f"--title '{t4}: x' --skip-commands")
    gate("SV вопрос владельцу без критериев: проверка чужой ветки зелёная", r.returncode == 0, r.stdout[-500:])
    sh("git pull -q", w)
    own = json.loads(T(w, "board --json", ok=True).stdout)["owner"][0]["id"]
    write(os.path.join(shared, "inbox", "a.md"), f"id: {own}\nowner_answer: Владелец 14.11: «да»\n")
    sh("python3 tools/tasks.py intake", o, env)
    sh("git pull -q", w)
    bj = json.loads(T(w, "board --json", ok=True).stdout)
    gate("SV ответ владельца без критериев: карточка в inbox (дооформить), не готова и не ошибка",
         own in [x["id"] for x in bj["inbox"]] and bj["counts"]["fail"] == 0, json.dumps(bj["counts"]))

    # Н4: повторяющаяся без срока
    r = T(w, "new --title 'Еженедельно' --repeat weekly --done 'Г' --verify 'С' --commit --push", ok=True)
    rid = r.stdout.split()[0]
    txt = sh(f"cat docs/tasks/{rid}-*.md", w).stdout
    gate("SV new --repeat без --due ставит срок через период", "due: 2026-11-21" in txt, txt[:400])
    rp = clone_branch(tmp, remote, "sv-rp", "claude/rp")
    T(rp, f"claim {rid}", ok=True)
    T(rp, f"land {rid} --result 'раз'", ok=True)
    sh(f"git pull -q && git merge -q --squash origin/claude/rp && git commit -q -m '{rid}: раз (#50)' && git push -q", w)
    at = lambda d: [x["id"] for x in json.loads(sh("python3 tools/tasks.py --no-fetch ready --json", w,
                                                   {"TASKS_NOW": d}).stdout) if x["title"] == "Еженедельно"]
    nxt = [x for x in at("2026-11-27T09:00:00Z") if x not in at("2026-11-14T13:00:00Z")]
    gate("SV следующая повторяющаяся не выдаётся сразу, выдаётся за сутки до срока",
         rid not in at("2026-11-14T13:00:00Z") and len(nxt) == 1 and nxt[0] not in at("2026-11-26T09:00:00Z"), str(nxt))

    # Н6: первый запуск
    p = clone_branch(tmp, remote, "sv-p", "claude/p")
    r = T(p, f"prime {t4}")
    gate("SV prime предупреждает: inbox не настроен", "inbox не настроен" in r.stdout, r.stdout[:300])
    sh_dir = os.path.join(tmp, "sv-mnt")
    os.makedirs(sh_dir)
    r = T(p, f"init --project baltic --shared {sh_dir}")
    cfg = open(os.path.join(p, "tools/fundament.cfg"), encoding="utf-8").read()
    gate("SV init: fundament.cfg с явными путями и папка inbox",
         r.returncode == 0 and f"inbox: {sh_dir}/baltic/inbox" in cfg and os.path.isdir(os.path.join(sh_dir, "baltic/inbox")), r.stdout)
    r = T(p, f"prime {t4}")
    gate("SV после init предупреждения нет", "inbox не настроен" not in r.stdout, r.stdout[:300])
    f = clone_branch(tmp, remote, "sv-f", "feat/frontend-v2")
    write(os.path.join(f, "app.js"), "x\n")
    sh("git add -A && git commit -q -m 'фронт' && git push -q -u origin HEAD", f)
    r = T(p, f"init --project baltic --shared {sh_dir}")
    gate("SV init: main отстал от рабочей ветки — СТОП и задача свести", r.returncode == 3 and "feat/frontend-v2 (+1)" in r.stdout
         and "свести в main без потерь" in r.stdout, r.stdout)

    # мелкие: какая ветка закрыла; check.py | head
    k1 = clone_branch(tmp, remote, "sv-k1", "claude/k1")
    t5 = new(w, "--title 'Две ветки'")
    sh("git pull -q --rebase origin main", k1)
    T(k1, f"claim {t5}", ok=True)
    T(k1, f"land {t5} --result 'x'", ok=True)
    chk = T(w, "check").stdout
    gate("SV «закрыта в ветке» называет ту ветку, что закрыла", f"{t5}: закрыта в ветке claude/k1" in chk, chk[-500:])
    r = sh("python3 tools/check.py --skip-commands | head -1", o2, ok=False)
    gate("SV check.py | head — без трассы BrokenPipe", "Traceback" not in r.stderr, r.stderr[-300:])
