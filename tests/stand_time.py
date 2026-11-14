"""Стенд, часть «машина времени» (2.1): 60 дней работы на подменённых часах вместо месяцев ожидания.

Каждый день: координатор (через inbox, как без оболочки) заводит задачи, ветка берёт первую
из ready, садит, PR сливается squash'ем. Раз в неделю еженедельная задача и архив в main.
Одна ветка брошена на полпути. В конце: ни одной потерянной задачи, ни одного FAIL,
еженедельная выдавалась раз в неделю, брошенная перевыдана, архив собран.
"""
import json
import os
from datetime import datetime, timedelta

from standlib import sh, gate, setup_repo, write, clone_branch

START = datetime(2026, 11, 2, 8, 0)


def run(tmp, quick=False):
    days = 21 if quick else 60
    remote, w = setup_repo(tmp, "st")
    write(os.path.join(w, "CLAUDE.md"), "# Проект\n")
    sh("git add -A && git commit -q -m init && git push -q -u origin main", w)
    ib = os.path.join(tmp, "st-shared", "inbox")
    created, fails, weekly_runs, abandoned, n = [], [], [], None, 0

    def env(day, hour=9):
        t = START + timedelta(days=day, hours=hour - 8)
        stamp = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"TASKS_NOW": stamp, "TASKS_INBOX": ib, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}

    def tasks(cwd, args, e, ok=True):
        return sh(f"python3 tools/tasks.py {args}", cwd, e, ok=ok)

    # еженедельная задача с первого дня
    write(os.path.join(ib, "weekly.md"), "title: Еженедельная проверка\npriority: 1\nrole: mechanic\nrepeat: weekly\n"
          f"due: {START.strftime('%Y-%m-%d')}\ndone: Отчёт в журнале\nverify: check.py --weekly\n")
    for day in range(days):
        e = env(day)
        for k in range(2):           # две просьбы в день
            n += 1
            write(os.path.join(ib, f"d{day:02d}-{k}.md"), f"title: Задача {n}\npriority: {n % 4}\n"
                  f"done: Сделано {n}\nverify: Посмотреть\n")
            created.append(f"Задача {n}")
        for slot in range(3):        # до трёх веток в день (предел живых веток)
            name = f"d{day}s{slot}"
            br = clone_branch(tmp, remote, "st-" + name, "claude/" + name)
            tasks(br, "intake", e)
            # координатор без оболочки оформляет новые карточки файлом «id: … status: open»
            todo = json.loads(tasks(br, "--no-fetch board --json --all", e).stdout)["inbox"]
            for x in todo:
                write(os.path.join(ib, f"ok-{x['id']}.md"), f"id: {x['id']}\nstatus: open\n\nОформлено.\n")
            if todo:
                tasks(br, "intake", e)
            ready = json.loads(tasks(br, "ready --json", e).stdout)
            if not ready:
                sh(f"rm -rf {br}", tmp)
                break
            tid, title = ready[0]["id"], ready[0]["title"]
            pr = tasks(br, f"prime {tid}", e)
            if "СТОП" in pr.stdout:
                fails.append(f"день {day}: prime СТОП по первой из ready {tid}")
                break
            tasks(br, f"claim {tid}", e)
            if title == "Еженедельная проверка":
                weekly_runs.append(day)
            if day == 5 and abandoned is None and title != "Еженедельная проверка":
                abandoned = tid          # ветку бросили: ни land, ни слияния
                sh(f"rm -rf {br}", tmp)
                continue
            write(os.path.join(br, f"docs/workstreams/{name}.md"), f"итог {name}\n")
            sh("git add -A && git commit -q -m work", br, e)
            tasks(br, f"land {tid} --result 'docs/workstreams/{name}.md'", e)
            c = sh(f"python3 tools/check.py --title '{tid}: {name} [skip ci]' --skip-commands", br, e, ok=False)
            if c.returncode:
                fails.append(f"день {day}: check FAIL\n" + c.stdout[-400:])
            sh(f"git pull -q && git merge -q --squash origin/claude/{name} && "
               f"git commit -q -m '{tid}: {name} [skip ci] (#{day * 3 + slot + 100})' && git push -q", w, env(day, 10 + slot))
            sh(f"rm -rf {br}", tmp)
        if day % 7 == 6:
            sh("python3 tools/tasks.py archive --commit --push", w, env(day, 16))
    e = env(days)
    sh("git pull -q", w, e)
    sh("python3 tools/tasks.py intake", w, e)
    rb = json.loads(sh("python3 tools/tasks.py board --json --all", w, e).stdout)
    allc = {}
    for root, _, fs in os.walk(os.path.join(w, "docs/tasks")):
        for f in fs:
            if f.endswith(".md") and f.startswith("t-"):
                t = open(os.path.join(root, f), encoding="utf-8").read()
                allc[t.split("\ntitle: ")[1].split("\n")[0]] = t
    lost = [t for t in created if t not in allc]
    gate(f"ST {days} дней: ни одной потерянной задачи ({len(created)} просьб)", not lost, str(lost[:5]))
    gate(f"ST {days} дней: ни одного FAIL проверки и пустого ready", not fails, "\n".join(fails[:3]))
    gaps = [b - a for a, b in zip(weekly_runs, weekly_runs[1:])]
    gate(f"ST еженедельная выдавалась раз в неделю (дни {weekly_runs})",
         len(weekly_runs) >= days // 7 and all(g >= 6 for g in gaps), str(gaps))
    gate("ST брошенная задача перевыдана и закрыта", abandoned and abandoned not in [x["id"] for x in rb["stale"]]
         and any(abandoned in t and "status: closed" in t for t in allc.values()) or not abandoned, abandoned)
    arch = [r for r, _, fs in os.walk(os.path.join(w, "docs/tasks/archive")) for f in fs]
    gate("ST архив собран (закрытые старше 30 дней)", days < 35 or len(arch) > 0, str(len(arch)))
    chk = sh("python3 tools/tasks.py check", w, e, ok=False).stdout
    gate("ST в конце доска без ошибок", "ошибок 0" in chk, chk[-500:])
