"""Общие помощники стенда: временные git-площадки, запуск скриптов, учёт ворот."""
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
NOW = "2026-11-14T12:00:00Z"
RESULTS = []          # (прошли?, имя, подробности) — общий для всех частей стенда


def sh(cmd, cwd, env_extra=None, ok=True):
    env = dict(os.environ, TASKS_NOW=NOW, TASKS_STAND="1", TASKS_SHARED="/nonexistent-shared", GIT_AUTHOR_NAME="stand", GIT_AUTHOR_EMAIL="stand@example.invalid",
               GIT_COMMITTER_NAME="stand", GIT_COMMITTER_EMAIL="stand@example.invalid")
    env.update(env_extra or {})
    r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, env=env)
    if ok and r.returncode != 0:
        raise SystemExit(f"команда упала: {cmd}\n{r.stdout}\n{r.stderr}")
    return r


def at(date):
    return {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}


def gate(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))


def card(cid, title, status="open", priority=2, area="", blocked="", typ="task", parent="",
         created="2026-11-05", due="", done=True, role="executor", repeat="", size="s"):
    done_txt = "Есть проверяемый результат." if done else ""
    return (f"---\nid: {cid}\ntitle: {title}\ntype: {typ}\nstatus: {status}\npriority: {priority}\n"
            f"role: {role}\nsize: {size}\nparent: {parent}\nblocked_by: [{blocked}]\nfrom:\nworkstream:\n"
            f"area: [{area}]\nassignee:\nclaimed:\ndue: {due}\nquestion:\nrepeat: {repeat}\nsource:\n"
            f"created: {created}\nclosed: {'2026-11-10T10:00Z' if status == 'closed' else ''}\n---\n"
            f"## Что сделать\n\n{title}.\n\n## Готово, когда\n\n{done_txt}\n\n## Как проверить\n\n"
            f"Открыть и посмотреть.\n\n## Журнал\n\n## Результат\n\n{'Сделано.' if status == 'closed' else ''}\n")


def setup_repo(tmp, name):
    remote = os.path.join(tmp, name + ".git")
    sh(f"git init -q --bare -b main {remote}", tmp)
    work = os.path.join(tmp, name + "-coord")
    sh(f"git clone -q {remote} {work}", tmp)
    sh("git checkout -q -b main", work, ok=False)
    os.makedirs(os.path.join(work, "docs/tasks"), exist_ok=True)
    # только скрипты: check-commands.txt и кэш самого эталона в стенд не берём
    shutil.copytree(TOOLS, os.path.join(work, "tools"), ignore=only_scripts)
    return remote, work


def only_scripts(d, names):
    """Из tools/ берём .py и подпапки; кэш и прочие файлы (check-commands.txt) не берём."""
    return [n for n in names if n == "__pycache__"
            or (not os.path.isdir(os.path.join(d, n)) and not n.endswith(".py"))]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def clone_branch(tmp, remote, name, branch):
    d = os.path.join(tmp, name)
    sh(f"git clone -q {remote} {d}", tmp)
    sh(f"git checkout -q -b {branch}", d)
    return d


def T(cwd, args, ok=False):
    return sh(f"python3 tools/tasks.py {args}", cwd, ok=ok)


def C(cwd, args="", ok=False):
    return sh(f"python3 tools/check.py {args}", cwd, ok=ok)


