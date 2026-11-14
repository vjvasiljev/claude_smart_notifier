#!/usr/bin/env python3
"""check.py — проверка ветки перед PR (стандарт «Фундамент v2»). Без зависимостей.

Запуск:  python3 tools/check.py [--title "t-ab12: ..."]      перед PR, вывод — в описание PR
         python3 tools/check.py --weekly                     еженедельная проверка main
         python3 tools/check.py --tools-from-main --title …  ревьюер: те же проверки, но скриптами из main
                                                             (ветка не может ослабить проверку собственного PR)
Выход 0 = зелёный, 1 = есть FAIL.

Проверяет: цель PR и id; целостность доски (через tasks.py); запрещённые файлы и
секреты в изменениях; замороженные файлы; размер CLAUDE.md; линтер/сборку/тесты.
Команды линтера/сборки/тестов: tools/check-commands.txt (строки «имя: команда»),
иначе берутся скрипты lint/build/test из package.json (заглушки пропускаются).
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True  # иначе import tasks оставит tools/__pycache__ в рабочей папке
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import tasks  # noqa: E402
except ImportError:      # копия из main без tasks.py рядом (ревьюер): годится только --tools-from-main
    tasks = None

VERSION = tasks.VERSION if tasks else "?"
BASE = os.environ.get("TASKS_BASE", "main")
CLAUDE_MD_MAX = 80
FROZEN_LIST = "docs/tasks/frozen.txt"
# tools/check-allow.txt: «<sha> <путь>» — известные учебные фикстуры в уже записанной истории
FORBIDDEN = [r"(^|/)\.DS_Store$", r"\.har$", r"\.(db|sqlite|sqlite3)$", r"(^|/)\.wrangler/",
             r"(^|/)node_modules/", r"(^|/)__pycache__/", r"\.pyc$", r"(^|/)\.env($|\.)", r"\.(pem|key|p12|pfx)$", r"(^|/)id_(rsa|ed25519)$",
             r"(^|/)credentials\.json$", r"(^|/)service[-_]?account[^/]*\.json$", r"(^|/)\.npmrc$", r"(^|/)\.pypirc$"]
ALLOW_LIST = "tools/check-allow.txt"
GUARDED = ["tools/check.py", "tools/tasks.py", "tools/check-commands.txt", ALLOW_LIST]
BUILD_JUNK = [r"(^|/)\.DS_Store$", r"(^|/)__pycache__/", r"\.pyc$", r"(^|/)node_modules/", r"(^|/)\.wrangler/"]
ALLOW_ENV = re.compile(r"\.env\.(example|sample|template)$")
SECRETS = [
    ("anthropic-key", r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    ("openai-key", r"sk-(proj-)?[A-Za-z0-9]{32,}"),
    ("github-token", r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"),
    ("aws-key", r"AKIA[0-9A-Z]{16}"),
    ("slack-token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("google-key", r"AIza[0-9A-Za-z_\-]{35}"),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("stripe-key", r"\b[sr]k_live_[0-9A-Za-z]{16,}"),
    ("conn-string", r"\b[a-z][a-z0-9+.\-]{1,20}://[^\s:/@'\"]+:[^\s@/'\"]{3,}@[^\s/'\"]+"),
    ("generic-secret", r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"][^'\"\s]{16,}['\"]"),
    ("bare-secret", r"(?i)^\s*(export\s+)?[A-Z0-9_]*(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY)[A-Z0-9_]*\s*[:=]\s*[^\s'\"#$<{][^\s'\"]{11,}\s*$"),
]
PLACEHOLDER = re.compile(r"(?i)(example|changeme|your[_-]|xxx|<|\$\{|placeholder|dummy)")


class Report:
    def __init__(self):
        self.rows = []

    def add(self, level, name, text=""):
        self.rows.append((level, name, text))

    @property
    def failed(self):
        return any(r[0] == "FAIL" for r in self.rows)

    def render(self):
        out = [f"### check.py {VERSION}: " + ("FAIL" if self.failed else "OK")]
        for level, name, text in self.rows:
            out.append(f"- {level} {name}" + (f": {text}" if text else ""))
        return "\n".join(out)


def git(root, *args, check=False):
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout if r.returncode == 0 else ""


def changed_files(root, base_ref):
    mb = git(root, "merge-base", base_ref, "HEAD").strip()
    if not mb:
        return None, []
    files = git(root, "diff", "-z", "--name-only", "--diff-filter=ACMR", mb).split("\0")
    files += git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0")
    return mb, sorted({f for f in files if f})


def deleted_files(root, mb):
    """Удалённые веткой пути: и закоммиченные, и просто стёртые в рабочей папке."""
    out = git(root, "diff", "-z", "--name-only", "--diff-filter=D", mb).split("\0")
    return sorted({f for f in out if f})


def secret_value(name, text):
    """Сама секретная часть совпадения: на ней проверяем заглушки (у строки подключения — пароль)."""
    if name == "conn-string":
        m = re.search(r"://[^:/@]+:([^@]+)@", text)
        return m.group(1) if m else text
    if name in ("bare-secret", "generic-secret"):
        return re.split(r"[:=]", text, maxsplit=1)[-1]
    return ""


def looks_like_code(v):
    """`settings.API_KEY`, `get_token()`, `cfg["x"]` — выражение кода, а не значение секрета."""
    return bool(re.search(r"[.(\[]", v)) and not re.search(r"[^\w.()\[\]'\" ,:-]", v.strip())


SETTINGS_FILE = re.compile(r"(^|/)\.env[^/]*$|\.(ini|cfg|properties)$", re.I)


def secret_hit(ln, path=""):
    # в файлах настроек значение — это значение, а не код: послабление looks_like_code там не действует
    code_ok = not SETTINGS_FILE.search(path or "")
    for name, rx in SECRETS:
        m = re.search(rx, ln)
        if not m:
            continue
        v = secret_value(name, m.group(0))
        if PLACEHOLDER.search(v) or (name == "bare-secret" and code_ok and looks_like_code(v)):
            continue
        return name
    return None


def branch_added_lines(root, mb):
    """Все добавленные строки по всем коммитам ветки (секрет, добавленный и стёртый внутри ветки,
    остаётся в её истории на GitHub), плюс незакоммиченное. Возвращает [(путь, строка, sha|None)]."""
    out, path, sha = [], None, None
    for chunk, committed in ((git(root, "log", "-p", "-U0", "--no-color", "--first-parent",
                                  "--format=@@commit %H", f"{mb}..HEAD"), True),
                             (git(root, "diff", "-U0", "--no-color", "HEAD"), False)):
        sha = None
        for ln in chunk.splitlines():
            if committed and ln.startswith("@@commit "):
                sha = ln[9:].strip()
            elif ln.startswith("+++ "):
                path = ln[6:] if ln.startswith("+++ b/") else None
            elif ln.startswith("+") and path:
                out.append((path, ln[1:], sha))
    for f in git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0"):
        full = os.path.join(root, f)
        if f and os.path.isfile(full) and os.path.getsize(full) <= 2_000_000:
            try:
                with open(full, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            if b"\0" not in raw:
                out += [(f, ln, None) for ln in raw.decode("utf-8", "replace").splitlines()]
    return out


def added_lines(root, mb, path):
    if git(root, "ls-files", "--error-unmatch", path) == "" and os.path.exists(os.path.join(root, path)):
        try:
            with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                return fh.read().splitlines()
        except OSError:
            return []
    diff = git(root, "diff", "-U0", mb, "--", path)
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def check_target(rep, b, title, files):
    if b.current == tasks.BASE:
        rep.add("FAIL", "ветка", "проверка запущена на main: работа идёт в ветке задачи")
        return None
    rep.add("OK", "цель PR", f"{b.current} → {tasks.BASE}")
    ids = set()
    for f in files:
        m = re.match(rf"{tasks.TASKS_DIR}/t-([0-9a-z]{{4}})", f)
        if m:
            ids.add("t-" + m.group(1))
    claimed = [cid for cid in ids if cid in b.cards and
               any(br == b.current and s in ("in_progress", "needs_human", "closed")
                   for br, s, k, _ in b.claims.get(cid, []))]
    if title:
        m = re.match(r"^(t-[0-9a-z]{4})\b", title)
        if not m:
            rep.add("FAIL", "id в заголовке", f"заголовок PR должен начинаться с id задачи: «{title}»")
            return None
        tid = m.group(1)
        if tid not in claimed:
            rep.add("FAIL", "id в заголовке", f"{tid} не захвачена этой веткой (захвачены: {', '.join(sorted(claimed)) or 'нет'})")
        else:
            rep.add("OK", "id в заголовке", tid)
        return tid
    if not claimed:
        rep.add("FAIL", "захват", "ветка не захватила ни одной карточки (tasks.py claim <id>)")
        return None
    main_ids = [cid for cid in claimed if "_new_in" not in b.cards[cid].extra]
    rep.add("OK", "задача ветки", ", ".join(sorted(main_ids or claimed)))
    return (main_ids or claimed)[0]


def check_landed(rep, b, tid):
    if not tid or tid not in b.cards:
        return
    st = [s for br, s, k, _ in b.claims.get(tid, []) if br == b.current]
    if b.eff.get(tid) == "owner":
        rep.add("FAIL", "посадка", f"{tid} ждёт ответа владельца (needs_human в main) — работать по ней нельзя")
    elif st and st[0] == "closed":
        _, c = b.live_branch(tid)
        if c and not (c.section("Результат") or "").strip():
            rep.add("FAIL", "посадка", f"{tid} закрыта без «Результат»")
        else:
            rep.add("OK", "посадка", f"{tid} закрыта в ветке, закроется слиянием")
    elif st and st[0] == "needs_human":
        rep.add("WARN", "посадка", f"{tid} ждёт ответа (needs_human) — PR рано")
    else:
        rep.add("WARN", "посадка", f"{tid} ещё in_progress: перед PR запусти tasks.py land")


def check_verified(rep, b, tid):
    if not tid or tid not in b.cards or not tasks.code_changes(b):
        return
    _, c = b.live_branch(tid)
    c = c or b.cards[tid]
    if "Проверено:" not in (c.section("Журнал") or ""):
        rep.add("WARN", "проверено", f"{tid}: код изменён, а в журнале нет «Проверено:» (land --verified)")
    else:
        rep.add("OK", "проверено", "в журнале есть")


def check_uncommitted(rep, b):
    pending = tasks.uncommitted(b)
    if pending:
        rep.add("FAIL", "не закоммичено", "в PR не попадёт: " + ", ".join(pending[:10])
                + (f" и ещё {len(pending) - 10}" if len(pending) > 10 else ""))
    else:
        rep.add("OK", "не закоммичено", "нет")


def check_board(rep, b):
    res = tasks.integrity(b)
    fails = [r for r in res if r[0] == "FAIL"]
    for level, code, text in res:
        if level in ("FAIL", "WARN"):
            rep.add(level, f"доска/{code}", text)
    if not fails:
        rep.add("OK", "доска", f"{len(b.cards)} карточек, связи и критерии в порядке")


def check_files(rep, root, mb, files, base_ref=None, title=None):
    guarded = [f for f in GUARDED if f in files or f in deleted_files(root, mb)]
    if guarded:
        rep.add("WARN", "правка проверок", "PR меняет " + ", ".join(guarded)
                + ": ревьюер запускает check.py из main и читает каждую строку этих файлов")
    bad = [f for f in files if any(re.search(p, f) for p in FORBIDDEN) and not ALLOW_ENV.search(f)]
    if bad:
        rep.add("FAIL", "запрещённые файлы", ", ".join(bad[:10]))
    else:
        rep.add("OK", "запрещённые файлы", "нет")
    hits, allowed, history = set(), set(), set()
    allow_list = allowed_history(root, base_ref)   # из main: свои новые строки ветка себе не прощает
    final = {}

    def still_there(f, ln):
        if f not in final:
            try:
                final[f] = set(open(os.path.join(root, f), encoding="utf-8", errors="replace").read().splitlines())
            except OSError:
                final[f] = set()
        return ln in final[f]
    for f, ln, sha in branch_added_lines(root, mb):
        name = secret_hit(ln, f)
        if name and "check:allow" in ln:
            allowed.add(f"{f} ({name})")
        elif name and sha and not still_there(f, ln) and any(sha.startswith(p) and f == path for p, path in allow_list):
            history.add(f"{sha[:8]} {f} ({name})")   # фикстура в промежуточном коммите, в итоге помечена или убрана
        elif name:
            hits.add(f"{f} ({name})")
    if history:
        rep.add("WARN", "фикстуры в истории ветки", f"прощены по {ALLOW_LIST}, ревьюер сверяет: " + ", ".join(sorted(history)[:10]))
    if allowed:
        rep.add("WARN", "check:allow", "ревьюер сверяет, что это учебная фикстура: " + ", ".join(sorted(allowed)[:10]))
    if hits:
        rep.add("FAIL", "секреты", "по всем коммитам ветки: " + ", ".join(sorted(hits)[:10])
                + ". Удаление в следующем коммите не помогает: ключ уже в истории, его надо заменить")
    else:
        rep.add("OK", "секреты", "не найдено (все коммиты ветки и незакоммиченное)")
    # список заморозки берём из main: PR, который сам замораживает файлы, правит их законно
    listed = git(root, "show", f"{base_ref}:{FROZEN_LIST}") if base_ref else ""
    if listed:
        frozen = {ln.strip() for ln in listed.splitlines() if ln.strip() and not ln.startswith("#")}
        touched = sorted(frozen & set(files))
        gone = sorted(frozen & set(deleted_files(root, mb)))
        if gone:
            rep.add("FAIL", "замороженные файлы", "удалены: " + ", ".join(gone))
        if touched:
            rep.add("FAIL", "замороженные файлы", "правки в перенесённых списках: " + ", ".join(touched))
        if not gone and not touched:
            rep.add("OK", "замороженные файлы", f"{len(frozen)} под охраной, не тронуты")
    if title and files and all(f.startswith("docs/") for f in files) and "[skip ci]" not in title:
        rep.add("WARN", "skip ci", "PR только с docs/: добавь «[skip ci]» в конец заголовка, "
                "иначе squash-коммит слияния запустит сборку и выкладку")


def check_claude_md(rep, root):
    p = os.path.join(root, "CLAUDE.md")
    if not os.path.exists(p):
        rep.add("WARN", "CLAUDE.md", "нет в корне")
        return
    n = sum(1 for _ in open(p, encoding="utf-8"))
    rep.add("FAIL" if n > CLAUDE_MD_MAX else "OK", "CLAUDE.md", f"{n} строк (предел {CLAUDE_MD_MAX})")


def project_commands(root, base_ref=None):
    cfg = os.path.join(root, "tools", "check-commands.txt")
    ref_text = git(root, "show", f"{base_ref}:tools/check-commands.txt") if base_ref else ""
    if ref_text or os.path.exists(cfg):
        # команды берём из main: ветка не может ослабить свою же проверку (изменение видно WARN выше)
        text = ref_text or open(cfg, encoding="utf-8").read()
        out = []
        for ln in text.splitlines():
            if ":" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split(":", 1)
                out.append((k.strip(), v.strip()))
        return out
    pj = os.path.join(root, "package.json")
    if os.path.exists(pj):
        try:
            scripts = json.load(open(pj, encoding="utf-8")).get("scripts", {})
        except ValueError:
            return []
        return [(k, f"npm run {k} --silent") for k in ("lint", "build", "test")
                if k in scripts and "no test specified" not in scripts[k]]
    return []


def check_commands(rep, root, skip, base_ref=None):
    cmds = project_commands(root, base_ref)
    if not cmds:
        rep.add("OK", "линтер/сборка/тесты", "в проекте не настроены")
        return
    for name, cmd in cmds:
        if skip:
            rep.add("WARN", name, "пропущено (--skip-commands)")
            continue
        r = subprocess.run(cmd, cwd=root, shell=True, capture_output=True, text=True, timeout=1800)
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        rep.add("OK" if r.returncode == 0 else "FAIL", name,
                cmd + ("" if r.returncode == 0 else " → " + " | ".join(tail)))


def allowed_history(root, ref=None):
    """Строки «<начало sha, от 7 знаков> <путь>»: секреты в этом файле этого коммита — учебные фикстуры.
    Только для истории, которую нельзя исправить маркером check:allow; запрещённые файлы не прощаются."""
    out = set()
    path = os.path.join(root, ALLOW_LIST)
    if ref:
        text = git(root, "show", f"{ref}:{ALLOW_LIST}")
    else:
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    if text:
        for ln in text.splitlines():
            parts = ln.split("#", 1)[0].split()
            if len(parts) == 2 and len(parts[0]) >= 7:
                out.add((parts[0].lower(), parts[1]))
    return out


def root_files(rep, root, sha, names, base_ref=None):
    bad = [f for f in names if any(re.search(p, f) for p in FORBIDDEN) and not ALLOW_ENV.search(f)]
    # мусор, уже удалённый из main, опасности не несёт: остался только в истории (секреты — нет, см. ниже)
    # послабление только для мусора сборки; ключи, .env, базы, .har из истории не стёрты — их надо менять, FAIL
    gone = [f for f in bad if any(re.search(p, f) for p in BUILD_JUNK)
            and base_ref and not git(root, "ls-tree", "--name-only", base_ref, "--", f).strip()]
    bad = [f for f in bad if f not in gone]
    if gone:
        rep.add("WARN", "запрещённые файлы в начальном коммите", "уже удалены из main, остались в истории: " + ", ".join(gone[:10]))
    if bad:
        rep.add("FAIL", "запрещённые файлы в начальном коммите", ", ".join(bad[:10]))
    hits = []
    for f in names:
        r = subprocess.run(["git", "show", f"{sha}:{f}"], cwd=root, capture_output=True)
        if r.returncode:
            rep.add("WARN", "начальный коммит", f"{f}: не прочитан ({r.stderr.decode('utf-8', 'replace').strip()[:80]})")
            continue
        raw = r.stdout
        if len(raw) > 2_000_000 or b"\0" in raw:
            continue  # двоичный или большой файл: секреты не ищем, запрещённое имя уже проверено
        text = raw.decode("utf-8", "replace")
        for ln in text.splitlines():
            if secret_hit(ln, f) and "check:allow" not in ln:
                hits.append(f)
                break
    allow = allowed_history(root)
    excused = [f for f in hits if any(sha.startswith(p) and f == path for p, path in allow)]
    hits = [f for f in hits if f not in excused]
    if excused:
        rep.add("INFO", "учебные фикстуры", f"{sha[:8]}: {', '.join(excused)} (по {ALLOW_LIST})")
    if hits:
        rep.add("FAIL", "секреты в начальном коммите", ", ".join(hits[:10]))


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def check_version(rep, root):
    """Сверка с эталоном: путь из tools/fundament.cfg (etalon:) или TASKS_ETALON, иначе tools/VERSION-etalon."""
    src = tasks.config(root, "etalon") or os.path.join(root, "tools", "VERSION-etalon")
    try:
        ref = open(src, encoding="utf-8").read().strip().split()[0]
    except (OSError, IndexError):
        rep.add("INFO", "версия", f"{VERSION}; эталон не найден ({src})")
        return
    if vtuple(ref) > vtuple(VERSION):
        rep.add("WARN", "версия", f"скрипты {VERSION}, эталон {ref}: обновить (карточка mechanic, раздел «Обновление» модуля migrate)")
    else:
        rep.add("OK", "версия", f"{VERSION} (эталон {ref})")


def tools_from_main(argv, root, fetch):
    """Запустить check.py и tasks.py из origin/main на текущей ветке; вернуть код выхода."""
    if fetch:
        git(root, "fetch", "-q", "origin", f"+refs/heads/{BASE}:refs/remotes/origin/{BASE}")
    ref = f"origin/{BASE}" if git(root, "rev-parse", "--verify", "--quiet", f"origin/{BASE}") else BASE
    tmp = tempfile.mkdtemp(prefix="check-main-")
    try:
        for name in ("check.py", "tasks.py"):
            body = subprocess.run(["git", "show", f"{ref}:tools/{name}"], cwd=root, capture_output=True)
            if body.returncode:
                print(f"### check.py: FAIL\n- FAIL инструменты из main: в {ref} нет tools/{name}")
                return 1
            with open(os.path.join(tmp, name), "wb") as fh:
                fh.write(body.stdout)
        rest = [x for x in argv if x != "--tools-from-main"]
        if "--root" not in rest:
            rest = ["--root", root] + rest
        print(f"(проверка скриптами из {ref}, не из ветки)")
        sys.stdout.flush()
        return subprocess.run([sys.executable, "-B", os.path.join(tmp, "check.py"), *rest]).returncode
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def weekly(rep, root, base_ref, days):
    since = (tasks.now() - tasks.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")   # TASKS_NOW — только при TASKS_STAND=1 (стенд)
    log = git(root, "log", base_ref, f"--since={since}", "--first-parent",
              "--format=@@%H|%P|%s", "--name-only")
    direct_ok = viol = 0
    for chunk in log.split("@@")[1:]:
        head, *names = chunk.strip().split("\n")
        sha, parents, subj = head.split("|", 2)
        names = [n for n in names if n]
        if not parents.strip():
            # первый коммит пустого репозитория: PR сделать было не во что, поэтому снимаем
            # только правило «прямой коммит»; запрещённые файлы и секреты проверяем как обычно
            rep.add("INFO", "начальный коммит", f"{sha[:8]} «{subj}»: прямой коммит допустим")
            root_files(rep, root, sha, names, base_ref)
            continue
        via_pr = re.search(r"\(#\d+\)$", subj) or subj.startswith("Merge pull request")
        if via_pr:
            continue
        outside = [n for n in names if not n.startswith(tasks.TASKS_DIR + "/")]
        if outside:
            viol += 1
            rep.add("FAIL", "прямой коммит в main", f"{sha[:8]} «{subj}» тронул {', '.join(outside[:5])}")
        else:
            direct_ok += 1
            if "[skip ci]" not in subj:
                rep.add("WARN", "служебный коммит", f"{sha[:8]} без [skip ci]")
    rep.add("OK" if not viol else "FAIL", "история main", f"за {days} дн.: служебных коммитов {direct_ok}, нарушений {viol}")


def main(argv=None):
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # `check.py | head` без трассы BrokenPipe
    p = argparse.ArgumentParser(prog="check.py")
    p.add_argument("--root", default=".")
    p.add_argument("--title", help="заголовок PR (если уже известен)")
    p.add_argument("--weekly", action="store_true", help="проверка истории main и доски")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--skip-commands", action="store_true")
    p.add_argument("--tools-from-main", action="store_true", help="проверять скриптами из main (так делает ревьюер)")
    a = p.parse_args(argv)
    if a.tools_from_main:
        root = git(os.path.abspath(a.root), "rev-parse", "--show-toplevel").strip() or os.path.abspath(a.root)
        sys.exit(tools_from_main(list(sys.argv[1:] if argv is None else argv), root, not a.no_fetch))
    if tasks is None:
        print("### check.py: FAIL\n- FAIL нет tools/tasks.py рядом с check.py")
        sys.exit(1)
    b = tasks.Board(a.root, fetch=not a.no_fetch)
    rep = Report()
    root = b.root
    if a.weekly:
        weekly(rep, root, b.base_ref or tasks.BASE, a.days)
        check_version(rep, root)
        check_board(rep, b)
        check_claude_md(rep, root)
    else:
        if not b.in_git or not b.base_ref:
            rep.add("FAIL", "git", f"нет git или ветки {tasks.BASE}")
        else:
            mb, files = changed_files(root, b.base_ref)
            tid = check_target(rep, b, a.title, files)
            check_landed(rep, b, tid)
            check_uncommitted(rep, b)
            check_board(rep, b)
            check_files(rep, root, mb, files, b.base_ref, a.title)
            check_verified(rep, b, tid)
            check_claude_md(rep, root)
            check_commands(rep, root, a.skip_commands, b.base_ref)
    print(rep.render())
    sys.exit(1 if rep.failed else 0)


if __name__ == "__main__":
    main()
