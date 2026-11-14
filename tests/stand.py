#!/usr/bin/env python3
"""Стенд для tasks.py и check.py: две временные git-площадки с удалённым репозиторием.

Стенд 1: 15 карточек в main и три ветки с заложенными ошибками (цикл, битая ссылка,
общая area, нет критерия, зависшая ветка, две ветки на один id, повтор номера,
закрыто в ветке и открыто в main). Ворота: каждая ошибка поймана, порядок ready
совпадает с ожидаемым, два запуска подряд дают одинаковый результат.

Стенд 2: чистый проект, полный цикл new → prime → claim → land → слияние PR →
закрыто в main без второго PR; repeat; check.py зелёный; ловля секретов, запрещённых
и замороженных файлов, PR без захвата, прямой коммит в main (weekly).

Запуск: python3 tests/stand.py [--keep]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
from standlib import (HERE, TOOLS, NOW, RESULTS, sh, at, gate, card, setup_repo,  # noqa: E402
                      only_scripts, write, clone_branch, T, C)
import stand_safety  # noqa: E402
import stand_time  # noqa: E402


# ======================================================================= стенд 1
def stand1(tmp):
    remote, w = setup_repo(tmp, "s1")
    cards = [
        card("t-0001", "API эндпойнт", priority=1, area="api", created="2026-11-02"),
        card("t-0002", "Страница входа", priority=1, area="web", created="2026-11-05"),
        card("t-0003", "Миграция базы", area="db", created="2026-11-03"),
        card("t-0004", "Срочный фикс", priority=0, blocked="t-0009", created="2026-11-08"),
        card("t-0005", "Отчёт по логам", created="2026-11-06"),
        card("t-0006", "API лимиты", area="api", created="2026-11-01"),
        card("t-0007", "Цикл А", blocked="t-0008", created="2026-11-01"),
        card("t-0008", "Цикл Б", blocked="t-0007", created="2026-11-01"),
        card("t-0009", "Настроить линтер", status="closed", created="2026-11-01"),
        card("t-0010", "Битая ссылка", blocked="t-zzzz", created="2026-11-01"),
        card("t-0011", "Без критерия", done=False, created="2026-11-01"),
        card("t-0012", "Идея из inbox", status="inbox", created="2026-11-01"),
        card("t-0013", "Эпик: новый кабинет", typ="epic", role="planner", size="l", created="2026-11-01"),
        card("t-0014", "Часть эпика со сроком", parent="t-0013", due="2026-11-20", created="2026-11-07"),
        card("t-0015", "Ранняя важная", priority=1, created="2026-11-01"),
    ]
    for i, text in enumerate(cards, 1):
        cid = f"t-{i:04d}"
        write(os.path.join(w, f"docs/tasks/{cid}-card.md"), text)
    sh("git add -A && git commit -q -m 'tasks: seed [skip ci]' && git push -q -u origin main", w,
       at("2026-11-10T09:00:00Z"))

    # ветка A: захват t-0001, затем посадка (закрыто в ветке, открыто в main)
    a = clone_branch(tmp, remote, "s1-a", "claude/branch-a")
    sh("python3 tools/tasks.py --no-fetch claim t-0001 --assignee branch-a --no-push", a, at("2026-11-14T10:00:00Z"))
    sh("python3 tools/tasks.py --no-fetch land t-0001 --result 'Эндпойнт /x' --no-push", a, at("2026-11-14T10:30:00Z"))
    sh("git push -q -u origin HEAD", a)
    # ветка B: тоже t-0001 (две ветки на один id) + новая карточка с повтором номера t-0005
    bdir = clone_branch(tmp, remote, "s1-b", "claude/branch-b")
    sh("python3 tools/tasks.py --no-fetch claim t-0001 --assignee branch-b --force --no-push", bdir, at("2026-11-14T11:00:00Z"))
    write(os.path.join(bdir, "docs/tasks/t-0005-naydennoe.md"), card("t-0005", "Найденное по ходу"))
    sh("git add -A && git commit -q -m 't-0001: discovered'", bdir, at("2026-11-14T11:05:00Z"))
    sh("git push -q -u origin HEAD", bdir)
    # ветка C: захват t-0003 три дня назад — зависла
    c = clone_branch(tmp, remote, "s1-c", "claude/branch-c")
    sh("python3 tools/tasks.py --no-fetch claim t-0003 --assignee branch-c --no-push", c,
       dict(at("2026-11-11T09:00:00Z"), TASKS_NOW="2026-11-11T09:00:00Z"))
    sh("git push -q -u origin HEAD", c)

    # наблюдатель: свежий клон main (как новый координатор)
    obs = os.path.join(tmp, "s1-observer")
    sh(f"git clone -q {remote} {obs}", tmp)
    r1 = T(obs, "check --json")
    checks = json.loads(r1.stdout)
    codes = {}
    for x in checks:
        codes.setdefault(x["code"], []).append(x["text"])
    gate("S1 check падает с кодом 1", r1.returncode == 1)
    gate("S1 цикл t-0007↔t-0008", any("t-0007 → t-0008 → t-0007" in t for t in codes.get("cycle", [])))
    gate("S1 битая ссылка t-zzzz", any("t-zzzz" in t for t in codes.get("broken-link", [])))
    gate("S1 нет критерия t-0011", any("t-0011" in t and "Готово" in t for t in codes.get("no-done", [])))
    gate("S1 зависшая ветка t-0003", any("t-0003" in t and "branch-c" in t for t in codes.get("stale", [])))
    gate("S1 две ветки на t-0001", any("t-0001" in t and "branch-a" in t and "branch-b" in t
                                        for t in codes.get("double-claim", [])))
    gate("S1 повтор номера t-0005", any("t-0005" in t for t in codes.get("dup-id", [])))
    gate("S1 закрыто в ветке, открыто в main → на проверке", any("t-0001" in t for t in codes.get("review", [])))
    unexpected = set(codes) - {"cycle", "broken-link", "no-done", "stale", "double-claim", "dup-id", "review", "big-task"}
    gate("S1 нет ложных срабатываний", not unexpected, ", ".join(sorted(unexpected)))

    rr = json.loads(T(obs, "ready --json", ok=True).stdout)
    order = [x["id"] for x in rr]
    expected = ["t-0004", "t-0015", "t-0002", "t-0014", "t-0003", "t-0005"]
    gate("S1 порядок ready", order == expected, f"получили {order}")
    gate("S1 общая area: t-0006 не готова", "t-0006" not in order)
    gate("S1 зависшая t-0003 помечена для перевыдачи", any(x["id"] == "t-0003" and x["stale"] for x in rr))
    why = T(obs, "prime t-0006").stdout
    gate("S1 prime t-0006 говорит СТОП из-за области", "СТОП" in why and "api" in why)
    lines = T(obs, "prime t-0014").stdout.strip().splitlines()
    gate("S1 prime ≤ 40 строк и заканчивается claim", len(lines) <= 40 and "claim t-0014" in lines[-1], f"{len(lines)} строк")

    # детерминизм: два запуска подряд
    outs = [(T(obs, "check --json").stdout, T(obs, "ready --json").stdout, T(obs, "board --json").stdout) for _ in range(2)]
    gate("S1 два запуска подряд одинаковы", outs[0] == outs[1])
    bj = json.loads(outs[0][2])
    gate("S1 board: в работе пусто, на проверке t-0001, зависла t-0003",
         [x["id"] for x in bj["review"]] == ["t-0001"] and [x["id"] for x in bj["stale"]] == ["t-0003"])
    # claim занятой задачи отклоняется
    d = clone_branch(tmp, remote, "s1-d", "claude/branch-d")
    r = T(d, "claim t-0001 --no-push")
    gate("S1 claim занятой задачи отклонён", r.returncode != 0 and "занята" in r.stderr, r.stderr.strip())
    r = T(d, "claim t-0007 --no-push")
    gate("S1 claim заблокированной задачи отклонён", r.returncode != 0 and "ждёт" in r.stderr, r.stderr.strip())


# ======================================================================= стенд 2
def stand2(tmp):
    remote, w = setup_repo(tmp, "s2")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n\nкоротко\n")
    sh("git add -A && git commit -q -m 'init' && git push -q -u origin main", w, at("2026-11-12T09:00:00Z"))
    # координатор заводит задачи прямо в main
    r = T(w, "new --title 'Еженедельный отчёт' --priority 1 --area reports --repeat weekly --due 2026-11-16 "
             "--done 'Отчёт лежит в docs/reports' --verify 'Файл есть' --commit --push", ok=True)
    tid = r.stdout.split()[0]
    r = T(w, "new --title 'Вторая задача' --area web --done 'Готово' --verify 'Смотреть' --commit --push", ok=True)
    tid2 = r.stdout.split()[0]
    log = sh("git log -1 --format=%s", w).stdout
    gate("S2 new пишет в main с [skip ci]", log.startswith("tasks: new") and "[skip ci]" in log, log.strip())

    # ветка: prime → claim → работа → land → check
    br = clone_branch(tmp, remote, "s2-x", "claude/x")
    pr = T(br, f"prime {tid}", ok=True).stdout
    gate("S2 prime печатает роль и модель", "executor (модель Opus)" in pr)
    T(br, f"claim {tid}", ok=True)
    seen = T(w, "board --json", ok=True).stdout
    gate("S2 захват сразу виден координатору из git", tid in [x["id"] for x in json.loads(seen)["in_progress"]])
    gate("S2 занятая задача пропала из ready у координатора", tid not in T(w, "ready", ok=True).stdout)
    T(br, f"ask {tid} --question 'Какой формат?'", ok=True)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("S2 вопрос ветки виден в «Ждёт тебя»", [x["question"] for x in rb["questions"]] == ["Какой формат?"])
    r = T(br, f"claim {tid}")
    gate("S2 после ответа ветка снова берёт свою задачу", r.returncode == 0, r.stderr.strip())
    write(os.path.join(br, "docs/reports/week.md"), "отчёт\n")
    T(br, f"new --title 'Найдено: поправить шаблон' --from {tid} --done 'Шаблон поправлен' --verify 'diff' ", ok=True)
    sh("git add -A && git commit -q -m 'report'", br)
    r = C(br, "--skip-commands")
    gate("S2 check предупреждает: не посажено", "ещё in_progress" in r.stdout)
    T(br, f"land {tid} --result 'docs/reports/week.md' --log 'отчёт собран'", ok=True)
    r = C(br, f"--title '{tid}: недельный отчёт'")
    gate("S2 check.py зелёный на посаженной ветке", r.returncode == 0, r.stdout[-600:])
    r = C(br, "--title 'без номера'")
    gate("S2 check ловит PR без id в заголовке", r.returncode == 1 and "id в заголовке" in r.stdout)
    files = sh("git diff --name-only origin/main", br).stdout.split()
    nxt = [f for f in files if f.startswith("docs/tasks/") and tid not in f and "naydeno" not in f]
    gate("S2 repeat: следующая карточка создана в том же PR", len(nxt) == 1, str(files))
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("S2 до слияния задача «на проверке»", tid in [x["id"] for x in rb["review"]])

    # слияние PR (squash, как на GitHub)
    sh("git push -q origin HEAD", br)
    sh(f"git pull -q && git merge -q --squash origin/claude/x && git commit -q -m '{tid}: отчёт (#1)' && git push -q", w)
    sh("git push -q origin --delete claude/x", w)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("S2 после слияния закрыто в main без второго PR", tid in [x["id"] for x in rb["closed_week"]])
    rr = [x["id"] for x in json.loads(T(w, "ready --json", ok=True).stdout)]
    gate("S2 найденная в ready, следующая повторяющаяся — ещё нет (не раньше срока)", len(rr) == 2 and tid2 in rr, str(rr))
    later = [x["id"] for x in json.loads(sh("python3 tools/tasks.py ready --json", w,
                                           {"TASKS_NOW": "2026-11-22T08:00:00Z"}).stdout)]
    gate("S2 повторяющаяся готова за сутки до срока", len(later) == 3, str(later))

    # нарушения
    y = clone_branch(tmp, remote, "s2-y", "claude/y")
    write(os.path.join(y, "app.py"), "API_KEY = 'sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789'\n")  # check:allow
    write(os.path.join(y, ".DS_Store"), "x")
    sh("git add -A && git commit -q -m 'oops'", y)
    r = C(y, "--skip-commands")
    gate("S2 ловит секрет", "FAIL секреты" in r.stdout)
    gate("S2 ловит запрещённый файл", "FAIL запрещённые файлы" in r.stdout and ".DS_Store" in r.stdout)
    gate("S2 ловит ветку без захвата", "FAIL захват" in r.stdout)

    write(os.path.join(w, "TODO.md"), "> перенесено в docs/tasks/, не дополнять\n- старое\n")
    write(os.path.join(w, "docs/tasks/frozen.txt"), "TODO.md\n")
    write(os.path.join(w, "CLAUDE.md"), "\n".join(["строка"] * 81) + "\n")
    sh("git add -A && git commit -q -m 'freeze and bloat' && git push -q", w)   # прямой коммит мимо docs/tasks
    z = clone_branch(tmp, remote, "s2-z", "claude/z")
    T(z, f"claim {tid2} --no-push", ok=True)
    with open(os.path.join(z, "TODO.md"), "a") as fh:
        fh.write("- новое\n")
    sh("git add -A && git commit -q -m 'edit frozen'", z)
    r = C(z, "--skip-commands --no-fetch")
    gate("S2 ловит правку замороженного файла", "FAIL замороженные файлы" in r.stdout)
    gate("S2 ловит CLAUDE.md > 80 строк", "FAIL CLAUDE.md: 81" in r.stdout)
    r = C(w, "--weekly")
    gate("S2 weekly ловит прямой коммит мимо docs/tasks", "FAIL прямой коммит в main" in r.stdout and "freeze and bloat" in r.stdout)
    gate("S2 weekly не трогает служебные tasks-коммиты", "служебных коммитов 2" in r.stdout, r.stdout[-300:])
    gate("S2 weekly не считает нарушением первый коммит репозитория",
         "INFO начальный коммит" in r.stdout and r.stdout.count("FAIL прямой коммит в main") == 1, r.stdout[-400:])

    # первый коммит с мусором и секретом: правило «прямой коммит» снято, остальное ловится
    r0 = os.path.join(tmp, "root0")
    os.makedirs(os.path.join(r0, "tools/__pycache__"))
    sh("git init -q -b main", r0)
    with open(os.path.join(r0, "tools/__pycache__/x.cpython-313.pyc"), "wb") as fh:
        fh.write(b"\xf3\r\r\n\x00\x00\xff")   # настоящий двоичный файл: не должен ронять --weekly
    write(os.path.join(r0, "conf.py"), 'API_KEY = "abcdefghijklmnopqrstuvwx"\n')  # check:allow
    write(os.path.join(r0, "README.md"), "ok\n")
    sh("git add -A && git commit -q -m 'init'", r0)
    r = sh(f"python3 {os.path.join(TOOLS, 'check.py')} --weekly --no-fetch", r0, ok=False)
    gate("S2 weekly в первом коммите ловит запрещённый файл и секрет, но не «прямой коммит»",
         "FAIL запрещённые файлы в начальном коммите: tools/__pycache__/x.cpython-313.pyc" in r.stdout
         and "FAIL секреты в начальном коммите: conf.py" in r.stdout
         and "FAIL прямой коммит в main" not in r.stdout, r.stdout[-500:])
    sha0 = sh("git rev-parse HEAD", r0).stdout.strip()
    write(os.path.join(r0, "tools/check-allow.txt"), f"{sha0[:8]} conf.py  # фикстура\n0000000 README.md\n")
    r = sh(f"python3 {os.path.join(TOOLS, 'check.py')} --weekly --no-fetch", r0, ok=False)
    gate("S2 check-allow.txt прощает только названную фикстуру, запрещённый файл остаётся",
         "FAIL секреты в начальном коммите" not in r.stdout and "INFO учебные фикстуры" in r.stdout
         and "FAIL запрещённые файлы в начальном коммите" in r.stdout, r.stdout[-500:])
    sub = os.path.join(tmp, "only")
    os.makedirs(os.path.join(sub, "lib/__pycache__"))
    for n in ("a.py", "check-commands.txt", "lib/b.py", "lib/__pycache__/b.pyc"):
        write(os.path.join(sub, n), "x\n")
    shutil.copytree(sub, os.path.join(tmp, "only-copy"), ignore=only_scripts)
    got = sorted(os.path.relpath(os.path.join(d, f), os.path.join(tmp, "only-copy"))
                 for d, _, fs in os.walk(os.path.join(tmp, "only-copy")) for f in fs)
    gate("S2 стенд копирует из tools .py и подпапки, без кэша и txt", got == ["a.py", "lib/b.py"], str(got))

    # плоская папка без git
    flat = os.path.join(tmp, "flat")
    os.makedirs(os.path.join(flat, "docs/tasks"))
    write(os.path.join(flat, "docs/tasks/t-aaaa-x.md"), card("t-aaaa", "Без git"))
    r = sh(f"python3 {TOOLS}/tasks.py --root {flat} ready", tmp, ok=False)
    gate("S2 работает и без git", "t-aaaa" in r.stdout)


# ======================================================================= стенд 3
def stand3(tmp):
    """Исправления 2.0.3: влитые неудалённые ветки, незакоммиченное, вопрос, карточки из --from."""
    remote, w = setup_repo(tmp, "s3")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    sh("git add -A && git commit -q -m 'init' && git push -q -u origin main", w)
    ids = []
    for i in range(4):
        r = T(w, f"new --title 'Задача {i}' --area a{i} --done 'Готово' --verify 'Смотреть' --commit --push", ok=True)
        ids.append(r.stdout.split()[0])
    t0, t1, t2, t3 = ids

    # 1. ветка посажена и влита squash'ем, но не удалена (платформа удалять не даёт)
    a = clone_branch(tmp, remote, "s3-a", "claude/a")
    T(a, f"claim {t0}", ok=True)
    write(os.path.join(a, "docs/workstreams/a0.md"), "знание\n")
    sh("git add -A && git commit -q -m work", a)
    T(a, f"land {t0} --result 'a0.md' --no-push", ok=True)
    sh("git push -q origin HEAD", a)
    sh(f"git pull -q && git merge -q --squash origin/claude/a && git commit -q -m '{t0}: a (#1)' && git push -q", w)
    # ветка без карточек, тоже влитая squash'ем
    c = clone_branch(tmp, remote, "s3-c", "claude/c")
    write(os.path.join(c, "README.md"), "readme\n")
    sh("git add -A && git commit -q -m readme && git push -q origin HEAD", c)
    sh("git pull -q && git merge -q --squash origin/claude/c && git commit -q -m 'readme (#2)' && git push -q", w)
    # живая ветка с вопросом
    q = clone_branch(tmp, remote, "s3-q", "claude/q")
    T(q, f"claim {t1}", ok=True)
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    chk = T(w, "check", ok=False).stdout
    gate("S3 влитая неудалённая ветка не считается живой", rb["counts"]["live_branches"] == 1, str(rb["counts"]))
    gate("S3 влитые ветки не дают WARN «без захвата»", "no-claim" not in chk, chk[-400:])
    gate("S3 задача влитой ветки закрыта, не на проверке",
         t0 in [x["id"] for x in rb["closed_week"]] and not rb["review"], str(rb["review"]))

    # 2. вопрос и повторный claim
    T(q, f"ask {t1} --question 'Формат?'", ok=True)
    T(q, f"claim {t1}", ok=True)
    txt = open([os.path.join(q, "docs/tasks", f) for f in os.listdir(os.path.join(q, "docs/tasks")) if f.startswith(t1)][0]).read()
    gate("S3 повторный claim очищает question и пишет журнал",
         "\nquestion:\n" in txt and "снова в работе после вопроса" in txt, txt[:400])
    rb = json.loads(T(w, "board --json", ok=True).stdout)
    gate("S3 после ответа вопрос пропал с доски", rb["questions"] == [], str(rb["questions"]))

    # 3. land забирает карточки из new --from и предупреждает о прочем незакоммиченном
    T(q, f"new --title 'Найдено по ходу' --from {t1} --done 'Сделано' --verify 'Смотреть'", ok=True)
    write(os.path.join(q, "docs/workstreams/a1.md"), "результат\n")
    r = T(q, f"land {t1} --result 'a1.md' --no-push", ok=True)
    tracked = sh("git ls-files docs/tasks", q).stdout
    gate("S3 land коммитит карточку из new --from", tracked.count("naydeno-po-hodu") == 1, tracked + r.stdout)
    gate("S3 land предупреждает о незакоммиченном результате",
         "не закоммичено" in r.stdout and "docs/workstreams/a1.md" in r.stdout, r.stdout)
    r = C(q, f"--title '{t1}: a1' --skip-commands --no-fetch")
    gate("S3 check ловит незакоммиченный файл", r.returncode == 1 and "FAIL не закоммичено" in r.stdout
         and "docs/workstreams/a1.md" in r.stdout, r.stdout[-500:])
    sh("git add -A && git commit -q -m result", q)
    r = C(q, f"--title '{t1}: a1' --skip-commands --no-fetch")
    gate("S3 после коммита check зелёный", r.returncode == 0, r.stdout[-500:])

    # 5. check-allow.txt не прощает секрет в diff PR, а его правка видна ревьюеру
    k = clone_branch(tmp, remote, "s3-k", "claude/k")
    T(k, f"claim {t3}", ok=True)
    write(os.path.join(k, "app.py"), "TOKEN = 'abcdefghijklmnopqrstuvwxyz'\n")  # check:allow
    sh("git add -A && git commit -q -m key", k)
    head = sh("git rev-parse HEAD", k).stdout.strip()
    write(os.path.join(k, "tools/check-allow.txt"), f"{head[:8]} app.py\n")
    write(os.path.join(k, "Отчёт.md"), "русское имя\n")
    r = C(k, f"--title '{t3}: k' --skip-commands --no-fetch")
    gate("S3 незакоммиченный файл с русским именем назван как есть", "Отчёт.md" in r.stdout, r.stdout[-400:])
    sh("git add -A && git commit -q -m allow", k)
    r = C(k, f"--title '{t3}: k' --skip-commands --no-fetch")
    gate("S3 check-allow.txt не прощает секрет в diff PR", "FAIL секреты" in r.stdout and "app.py" in r.stdout, r.stdout[-500:])
    gate("S3 правка check-allow.txt даёт WARN ревьюеру", "WARN правка проверок" in r.stdout and "check-allow.txt" in r.stdout, r.stdout[-500:])

    # 4. PR сам замораживает старый файл: список заморозки берётся из main, а не из ветки
    write(os.path.join(w, "TODO.md"), "- старое\n")
    sh("git add -A && git commit -q -m 'todo' && git push -q", w)
    m = clone_branch(tmp, remote, "s3-m", "claude/m")
    T(m, f"claim {t2}", ok=True)
    write(os.path.join(m, "TODO.md"), "> перенесено в docs/tasks/, не дополнять\n- старое\n")
    write(os.path.join(m, "docs/tasks/frozen.txt"), "TODO.md\n")
    sh("git add -A && git commit -q -m freeze", m)
    T(m, f"land {t2} --result 'заморожено' --no-push", ok=True)
    r = C(m, f"--title '{t2}: заморозка' --skip-commands --no-fetch")
    gate("S3 PR, который сам замораживает файл, не ловится как правка замороженного",
         r.returncode == 0 and "FAIL замороженные" not in r.stdout, r.stdout[-500:])



# ======================================================================= стенд 4
def stand4(tmp):
    """2.0.5: «ждёт владельца» не зависает и не выдаётся; доска показывает inbox, эпики, заблокированные."""
    remote, w = setup_repo(tmp, "s4")
    write(os.path.join(w, "tools/__pycache__/junk.pyc"), "x")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w, at("2026-11-12T09:00:00Z"))
    ids = {}
    for key, extra in (("rm", "--area legacy"), ("q", "--area q"), ("e", "--type epic --area e"),
                       ("blk", "--area b"), ("inb", "--status inbox"), ("x", "--area x"), ("y", "--area y")):
        r = T(w, f"new --title 'Карточка {key}' {extra} --done 'Готово' --verify 'Смотреть' --commit --push", ok=True)
        ids[key] = r.stdout.split()[0]
    T(w, f"set {ids['blk']} blocked_by={ids['x']} --commit --push", ok=True)
    later = {"TASKS_NOW": "2026-11-20T12:00:00Z"}
    # координатор поднимает необратимое владельцу прямо в main
    T(w, f"ask {ids['rm']} --question 'Удалить legacy/ насовсем?' --no-push", ok=True)
    sh("git push -q", w)
    d = json.loads(sh("python3 tools/tasks.py board --json", w, later).stdout)
    gate("S4 поднятое владельцу — в «Ждёт владельца», не в «Зависли» и спустя дни",
         [x["id"] for x in d["owner"]] == [ids["rm"]] and not d["stale"], str(d["owner"]) + str(d["stale"]))
    rr = sh("python3 tools/tasks.py ready --json", w, later).stdout
    gate("S4 ready не выдаёт ждущее владельца", ids["rm"] not in rr)
    br = clone_branch(tmp, remote, "s4-b", "claude/b")
    pr = sh(f"python3 tools/tasks.py prime {ids['rm']}", br, later).stdout
    gate("S4 prime на ждущем владельца — СТОП, без «теперь claim»", "СТОП" in pr and "теперь:" not in pr, pr[-300:])
    r = sh(f"python3 tools/tasks.py claim {ids['rm']} --no-push", br, later, ok=False)
    gate("S4 claim на ждущем владельца отказывает", r.returncode != 0 and "владельца" in r.stderr, r.stderr)
    r = sh(f"python3 tools/tasks.py ask {ids['rm']} --question 'обход' --no-push", br, later, ok=False)
    gate("S4 чужая ветка не снимает защиту через ask", r.returncode != 0 and "владельца" in r.stderr, r.stderr)
    r = T(w, f"set {ids['rm']} --release", ok=False)
    gate("S4 set --release на ждущем владельца отказывает без --force", r.returncode != 0, r.stdout + r.stderr)
    # ветка уже работает, а координатор поднял задачу владельцу: посадить нельзя
    wk = clone_branch(tmp, remote, "s4-wk", "claude/wk")
    T(wk, f"claim {ids['y']}", ok=True)
    T(w, f"ask {ids['y']} --question 'Платить за хостинг?'", ok=True)
    d = json.loads(T(w, "board --json", ok=True).stdout)
    gate("S4 поднятое владельцу при живой ветке — «Ждёт владельца» с вопросом из main",
         [(x["id"], x["question"]) for x in d["owner"] if x["id"] == ids["y"]] == [(ids["y"], "Платить за хостинг?")], str(d["owner"]))
    r = T(wk, f"land {ids['y']} --result 'x' --no-push")
    gate("S4 land отказывает на ждущем владельца", r.returncode != 0 and "владельца" in r.stderr, r.stderr)
    sh("git commit -q --allow-empty -m work", wk)
    r = C(wk, f"--title '{ids['y']}: y' --skip-commands")
    gate("S4 check FAIL «посадка» на ждущем владельца", "FAIL посадка" in r.stdout, r.stdout[-500:])

    # вопрос ветки, ветка замолчала: ждёт ответа, а не новой ветки
    q = clone_branch(tmp, remote, "s4-q", "claude/q")
    sh(f"python3 tools/tasks.py claim {ids['q']}", q, at("2026-11-13T10:00:00Z"))
    sh(f"python3 tools/tasks.py ask {ids['q']} --question 'Какой формат?'", q, at("2026-11-13T10:05:00Z"))
    d = json.loads(sh("python3 tools/tasks.py board --json", w, later).stdout)
    gate("S4 вопрос замолчавшей ветки не становится «зависла»",
         ids["q"] in [x["id"] for x in d["questions"]] and ids["q"] not in [x["id"] for x in d["stale"]], str(d["questions"]))
    gate("S4 ready не выдаёт задачу с открытым вопросом", ids["q"] not in sh("python3 tools/tasks.py ready", w, later).stdout)
    # доска списками
    out = T(w, "board", ok=True).stdout
    gate("S4 board перечисляет inbox, эпики и заблокированные",
         all(ids[k] in out for k in ("inb", "e", "blk")) and "Заблокированы" in out and "Эпики" in out, out[-600:])
    allr = T(w, "board --all", ok=True).stdout
    gate("S4 board --all показывает все готовые", "## Готовы (1)" in allr and ids["x"] in allr and "## Следующие" not in allr, allr[:600])
    # мусор первого коммита, уже удалённый из main
    sh("git rm -rq tools/__pycache__ && git commit -q -m 'rm junk (#1)' && git push -q", w)
    r = C(w, "--weekly --no-fetch")
    gate("S4 weekly: удалённый из main мусор первого коммита — WARN, не FAIL",
         "WARN запрещённые файлы в начальном коммите: уже удалены из main" in r.stdout
         and "FAIL запрещённые файлы" not in r.stdout, r.stdout[-500:])
    # а ключи и базы из истории не стёрты: удаление из main не спасает
    e = os.path.join(tmp, "s4-env")
    os.makedirs(e)
    sh("git init -q -b main", e)
    for n in (".env", "cert.p12", "dump.har"):
        write(os.path.join(e, n), "x\n")
    write(os.path.join(e, "README.md"), "ok\n")
    sh("git add -A && git commit -q -m init && git rm -q .env cert.p12 dump.har && git commit -q -m 'rm (#1)'", e)
    r = sh(f"python3 {os.path.join(TOOLS, 'check.py')} --weekly --no-fetch", e, ok=False)
    gate("S4 weekly: .env/.p12/.har первого коммита — FAIL и после удаления из main",
         "FAIL запрещённые файлы в начальном коммите: .env, cert.p12, dump.har" in r.stdout, r.stdout[-500:])



def main():
    keep = "--keep" in sys.argv
    tmp = tempfile.mkdtemp(prefix="stand-")
    try:
        stand1(tmp)
        stand2(tmp)
        stand3(tmp)
        stand4(tmp)
        stand_safety.run(tmp)
        stand_time.run(tmp, quick="--quick" in sys.argv)
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print("стенд оставлен:", tmp)
    ok = sum(1 for r in RESULTS if r[0])
    for passed, name, detail in RESULTS:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed or not detail else f"  [{detail}]"))
    print(f"\nворот пройдено: {ok}/{len(RESULTS)}")
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
