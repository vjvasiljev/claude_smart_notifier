#!/usr/bin/env python3
"""tasks.py — доска задач в git (стандарт «Фундамент v2»).

main хранит решённое, ветки хранят текущее; скрипт складывает картину
из main и живых веток. Python 3.8+, без зависимостей, без вызовов моделей.

Команды:
  new     завести карточку                 ready   что можно брать
  prime   старт ветки (до 40 строк)        claim   занять задачу (коммит + push)
  ask     вопрос владельцу (needs_human)   land    посадка: закрыто + Результат
  set     поменять поля (координатор)      board   картина (--json для артефакта)
  check   целостность доски                stats   счётчики из git
  archive закрытые старше 30 дней в архив
  intake  файлы из общей папки inbox → карточки в main (координатор без оболочки)

Настройки проекта (необязательно): tools/fundament.cfg, строки «ключ: значение»:
  inbox: /mnt/project-files/<проект>/inbox      откуда intake берёт просьбы
  board_out: /mnt/project-files/<проект>/board.json   куда land кладёт свежую доску
  etalon: /mnt/project-files/fundament/tools/VERSION-etalon   версия эталона для weekly
Переменные TASKS_INBOX, TASKS_BOARD_OUT, TASKS_ETALON важнее файла.
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

VERSION = "2.1.1"
TASKS_DIR = "docs/tasks"
BASE = os.environ.get("TASKS_BASE", "main")
LIVE_HOURS = int(os.environ.get("TASKS_LIVE_HOURS", "48"))   # срок годности занятости
SCAN_DAYS = int(os.environ.get("TASKS_SCAN_DAYS", "14"))     # старше не читаем вовсе
MAX_BRANCHES = 3
LIST_LIMIT = 10        # столько строк в длинных разделах доски; остальное — счётчиком и board --all

FIELDS = ["id", "title", "type", "status", "priority", "role", "size", "parent",
          "blocked_by", "from", "workstream", "area", "assignee", "claimed", "due",
          "question", "repeat", "source", "created", "closed", "not_before"]
LIST_FIELDS = {"blocked_by", "area"}
STATUSES = {"inbox", "open", "in_progress", "needs_human", "closed"}
TYPES = {"epic", "task", "bug", "chore"}
ROLES = {"planner", "scout", "executor", "reviewer", "mechanic"}
SIZES = {"s", "m", "l"}
REPEATS = {"", "weekly", "monthly"}
MODEL_BY_ROLE = {"planner": "Fable", "scout": "Opus", "executor": "Opus",
                 "reviewer": "Opus", "mechanic": "Sonnet"}
SECTIONS = ["Что сделать", "Готово, когда", "Как проверить", "Журнал", "Результат"]
ID_RE = re.compile(r"^t-[0-9a-z]{4}$")
STATE_FIELDS = ["status", "assignee", "claimed", "question", "closed"]
RANK = {"inbox": 0, "open": 1, "in_progress": 2, "needs_human": 3, "closed": 4}


# ---------------------------------------------------------------- время
def now():
    s = os.environ.get("TASKS_NOW") if os.environ.get("TASKS_STAND") == "1" else None   # подмена часов — только стенду
    if s:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def stamp(dt=None):
    return (dt or now()).strftime("%Y-%m-%dT%H:%MZ")


def stamp_s(dt=None):
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return now().strftime("%Y-%m-%d")


def parse_date(s):
    if not s:
        return None
    try:
        s = s.strip().replace("Z", "+00:00")
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------- карточка
class Card:
    def __init__(self, path, meta, sections, extra_meta=None, preamble=""):
        self.path = path
        self.meta = meta
        self.sections = sections          # [(заголовок, текст)]
        self.extra = extra_meta or {}
        self.preamble = preamble

    @property
    def id(self):
        return self.meta.get("id", "")

    def get(self, k):
        v = self.meta.get(k, [] if k in LIST_FIELDS else "")
        return v

    def section(self, name):
        for h, t in self.sections:
            if h.strip().lower() == name.lower():
                return t.strip()
        return None

    def set_section(self, name, text):
        for i, (h, _) in enumerate(self.sections):
            if h.strip().lower() == name.lower():
                self.sections[i] = (h, "\n" + text.strip() + "\n\n")
                return
        self.sections.append((name, "\n" + text.strip() + "\n\n"))

    def render(self):
        out = ["---"]
        for k in FIELDS + sorted(self.extra):
            v = self.meta.get(k) if k in FIELDS else self.extra[k]
            if k in LIST_FIELDS:
                v = "[" + ", ".join(v or []) + "]"
            out.append(f"{k}: {v if v is not None else ''}".rstrip())
        out.append("---")
        body = self.preamble
        for h, t in self.sections:
            body += f"## {h}\n{t}"
        return "\n".join(out) + "\n" + body.rstrip() + "\n"


def parse_list(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [x.strip() for x in v.split(",") if x.strip()]


def parse_card(path, text):
    lines = text.splitlines(keepends=True)
    meta, extra = {}, {}
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            ln = lines[i]
            if ":" in ln:
                k, v = ln.split(":", 1)
                k, v = k.strip(), v.strip()
                if k in LIST_FIELDS:
                    meta[k] = parse_list(v)
                elif k in FIELDS:
                    meta[k] = v
                else:
                    extra[k] = v
            i += 1
        i += 1
    for k in FIELDS:
        meta.setdefault(k, [] if k in LIST_FIELDS else "")
    body = "".join(lines[i:])
    parts = re.split(r"(?m)^## (.+)\n", body)
    preamble = parts[0]
    sections = [(parts[j].strip(), parts[j + 1]) for j in range(1, len(parts) - 1, 2)]
    return Card(path, meta, sections, extra, preamble)


# ---------------------------------------------------------------- git
# все git-вызовы скрипта служебные (карточки, чтение): хуки проекта (husky и т. п.) к ним не относятся,
# а в облачной ветке без npm install они падают — поэтому хуки отключены, коммиты с --no-verify
GIT_OPTS = ["-c", "core.quotepath=false", "-c", "core.hooksPath=" + os.devnull]


class Git:
    def __init__(self, root):
        self.root = root

    def run(self, *args, check=True, input=None):
        r = subprocess.run(["git", *GIT_OPTS, *args], cwd=self.root, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", input=input)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout

    def ok(self, *args):
        return subprocess.run(["git", *GIT_OPTS, *args], cwd=self.root,
                              capture_output=True).returncode == 0

    def read_many(self, specs):
        """Читает много файлов одним `git cat-file --batch`."""
        if not specs:
            return {}
        p = subprocess.run(["git", "cat-file", "--batch"], cwd=self.root,
                           input=("\n".join(specs) + "\n").encode(), capture_output=True)
        data, out, pos = p.stdout, {}, 0
        for spec in specs:
            nl = data.index(b"\n", pos)
            head = data[pos:nl].decode().split()
            pos = nl + 1
            if len(head) >= 2 and head[1] == "missing":
                continue
            size = int(head[2])
            out[spec] = data[pos:pos + size].decode("utf-8", "replace")
            pos += size + 1
        return out


def find_root(start):
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                       capture_output=True, text=True)
    return (r.stdout.strip(), True) if r.returncode == 0 else (os.path.abspath(start), False)


def card_key(path):
    """Один и тот же файл до и после архива: docs/tasks/x.md == docs/tasks/archive/2026-11/x.md."""
    return os.path.basename(path)


def is_card_file(path):
    return os.path.basename(path).startswith("t-") and path.endswith(".md")


# ---------------------------------------------------------------- источники
class Source:
    """Одно место, откуда читаются карточки: main, ветка или рабочая папка."""

    def __init__(self, name, kind, cards, changed, age_h=0.0, ahead=0):
        self.name, self.kind = name, kind          # kind: base | live | stale
        self.cards = cards                         # id -> [Card]
        self.changed = changed                     # пути, изменённые в ветке
        self.age_h, self.ahead = age_h, ahead


def cards_from_files(files):
    by_id = {}
    for path, text in files.items():
        c = parse_card(path, text)
        if not c.id:
            c.meta["id"] = os.path.basename(path)[:6]
            c.extra["_noid"] = "1"
        by_id.setdefault(c.id, []).append(c)
    return by_id


def worktree_files(root):
    out, base = {}, os.path.join(root, TASKS_DIR)
    for d, _, files in os.walk(base):
        for f in files:
            full = os.path.join(d, f)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if is_card_file(rel):
                with open(full, encoding="utf-8", errors="replace") as fh:   # битый файл не валит доску
                    out[rel] = fh.read()
    return out


def ref_files(git, ref, only=None):
    names = [n for n in git.run("ls-tree", "-r", "--name-only", ref, "--", TASKS_DIR,
                                check=False).splitlines() if is_card_file(n)]
    if only is not None:
        names = [n for n in names if n in only]      # из ветки читаем только то, что она меняла
    got = git.read_many([f"{ref}:{n}" for n in names])
    return {n: got[f"{ref}:{n}"] for n in names if f"{ref}:{n}" in got}


class Board:
    def __init__(self, start=".", fetch=True):
        self.root, self.in_git = find_root(start)
        self.git = Git(self.root) if self.in_git else None
        self.warnings = []
        self.sources = []
        self.current = None
        self.base_ref = None
        self._load(fetch)
        self._merge()

    # ---- загрузка
    def _load(self, fetch):
        if not self.in_git:
            self.sources.append(Source("рабочая папка", "base",
                                       cards_from_files(worktree_files(self.root)), set()))
            return
        g = self.git
        has_origin = "origin" in g.run("remote", check=False).split()
        if fetch and has_origin:
            if not g.ok("fetch", "--quiet", "--prune", "origin",
                        "+refs/heads/*:refs/remotes/origin/*"):
                self.warnings.append("git fetch не удался: картина по последним известным веткам")
        self.current = g.run("rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
        if has_origin and g.ok("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{BASE}"):
            self.base_ref = f"origin/{BASE}"
            if self.current == BASE:
                self._catch_up()
        elif g.ok("rev-parse", "--verify", "--quiet", f"refs/heads/{BASE}"):
            self.base_ref = BASE
        # main: рабочая папка, если мы на main (координатор), иначе ref
        if self.current == BASE or not self.base_ref:
            files = worktree_files(self.root)
        else:
            files = ref_files(g, self.base_ref)
        self.sources.append(Source(BASE, "base", cards_from_files(files), set()))
        t_now = now().timestamp()
        # текущая ветка (рабочая папка) — всегда живая
        if self.current not in (BASE, "HEAD", "") and self.base_ref:
            mb = g.run("merge-base", self.base_ref, "HEAD", check=False).strip()
            changed = set(g.run("diff", "--name-only", mb, "--", TASKS_DIR, check=False).split()) if mb else set()
            changed |= set(g.run("ls-files", "--others", "--exclude-standard", "--", TASKS_DIR,
                                 check=False).split())
            ahead = int(g.run("rev-list", "--count", "--first-parent", f"{mb}..HEAD", check=False).strip() or 0) if mb else 0
            self.sources.append(Source(self.current, "live",
                                       cards_from_files(worktree_files(self.root)), changed, 0.0, ahead))
        if not has_origin or not self.base_ref:
            return
        for line in g.run("for-each-ref", "--format=%(refname:short) %(committerdate:unix)",
                          "refs/remotes/origin/").splitlines():
            name, ts = line.rsplit(" ", 1)
            short = name[len("origin/"):]
            if short in (BASE, "HEAD", self.current) or name == "origin":
                continue
            age_h = (t_now - int(ts)) / 3600
            if age_h > SCAN_DAYS * 24:
                continue
            mb = g.run("merge-base", self.base_ref, name, check=False).strip()
            if not mb:
                continue
            changed = set(g.run("diff", "--name-only", mb, name, "--", TASKS_DIR, check=False).split())
            ahead = int(g.run("rev-list", "--count", "--first-parent", f"{mb}..{name}", check=False).strip() or 0)
            if ahead == 0:
                continue
            if self._merged(name, mb):
                continue          # уже влита в main (squash/rebase): удалить ветку платформа не даёт
            files = ref_files(g, name, changed) if changed else {}
            kind = "live" if age_h <= LIVE_HOURS else "stale"
            self.sources.append(Source(short, kind, cards_from_files(files), changed, age_h, ahead))

    def _catch_up(self):
        """Координатор на main: рабочая папка не должна отставать от GitHub (иначе ready выдаёт сделанное)."""
        g = self.git
        behind = int(g.run("rev-list", "--count", f"HEAD..origin/{BASE}", check=False).strip() or 0)
        if not behind:
            return
        if g.ok("merge", "--ff-only", "-q", f"origin/{BASE}"):
            self.warnings.append(f"main подтянут с GitHub: +{behind} коммит(ов)")
            print(f"main подтянут с GitHub: +{behind} коммит(ов)", file=sys.stderr)
        else:
            self.warnings.append(f"рабочая папка main отстала от GitHub на {behind} коммит(ов) и сама не подтянулась: "
                                 f"git pull --rebase, потом повтори команду")

    def _merged(self, name, mb):
        """Ветка влита: всё, что она меняла, в main уже такое же, или все её карточки закрыты в main."""
        g = self.git
        files = [f for f in g.run("diff", "--name-only", mb, name, check=False).split("\n") if f]
        if not files:
            return True
        if not g.run("diff", "--name-only", name, self.base_ref, "--", *files, check=False).strip():
            return True
        cards = [f for f in files if f.startswith(TASKS_DIR + "/") and is_card_file(f)]
        if not cards:
            return False
        base = {c.path: c for lst in self.sources[0].cards.values() for c in lst}
        return all(f in base and base[f].get("status") == "closed" for f in cards)

    # ---- сборка картины
    def _merge(self):
        base = self.sources[0]
        self.cards = {}       # id -> Card (эффективная)
        self.dups = []        # (id, [пути/ветки])
        self.claims = {}      # id -> [(ветка, статус, kind)]
        seen_paths = {}       # id -> {(путь, источник)}
        for cid, lst in base.cards.items():
            self.cards[cid] = lst[0]
            for c in lst:
                seen_paths.setdefault(cid, set()).add((c.path, BASE))
        for src in self.sources[1:]:
            for cid, lst in src.cards.items():
                for c in lst:
                    if c.path not in src.changed:
                        continue
                    seen_paths.setdefault(cid, set()).add((c.path, src.name))
                    self.claims.setdefault(cid, []).append((src.name, c.get("status"), src.kind, c))
                    if cid not in self.cards:
                        self.cards[cid] = c
                        c.extra["_new_in"] = src.name
        for cid, paths in seen_paths.items():
            if len({card_key(p) for p, _ in paths}) > 1:
                self.dups.append((cid, sorted(paths)))
        self.eff = {cid: self._effective(cid) for cid in self.cards}
        self.prio = self._inherited_priority()

    def _inherited_priority(self):
        """Порядок: задача берёт лучший приоритет и ранний срок из всех, кого она (по цепочке) держит.
        self.via[cid] = (кто поднял приоритет, кто дал срок) — чтобы ready/prime показывали причину."""
        own, due = {}, {}
        for cid, c in self.cards.items():
            try:
                own[cid] = int(c.get("priority") or 2)
            except ValueError:
                own[cid] = 2
            due[cid] = c.get("due") or ""
        blocks = {}
        for cid, c in self.cards.items():
            if self.eff.get(cid) == "closed":
                continue
            for bl in c.get("blocked_by"):
                blocks.setdefault(bl, []).append(cid)
        out, self.due_eff, self.via = {}, {}, {}
        for cid in self.cards:
            best, bdue, pby, dby = own[cid], due[cid], None, None
            seen, todo = {cid}, list(blocks.get(cid, []))
            while todo:
                n = todo.pop()
                if n in seen:
                    continue
                seen.add(n)
                if own.get(n, 2) < best:
                    best, pby = own.get(n, 2), n
                if due.get(n) and (not bdue or due[n] < bdue):
                    bdue, dby = due[n], n
                todo += blocks.get(n, [])
            out[cid], self.due_eff[cid] = best, bdue
            if pby or dby:
                self.via[cid] = (pby, dby)
        return out

    def prio_label(self, c):
        """«p3» или «p3→p0 (держит t-xxxx)», плюс унаследованный срок."""
        lab = f"p{c.get('priority')}"
        pby, dby = self.via.get(c.id, (None, None))
        if pby:
            lab += f"→p{self.prio[c.id]} (держит {pby})"
        if dby:
            lab += f" срок {self.due_eff[c.id]} (от {dby})"
        return lab

    def _effective(self, cid):
        c = self.cards[cid]
        main_status = c.get("status") if "_new_in" not in c.extra else ""
        if main_status == "closed":
            return "closed"
        if main_status == "needs_human":
            return "owner"          # поднято владельцу в main: сильнее любой ветки, не зависает и не выдаётся
        live = [(b, s) for b, s, k, _ in self.claims.get(cid, []) if k == "live"]
        stale = [(b, s) for b, s, k, _ in self.claims.get(cid, []) if k == "stale" and s in ("in_progress", "needs_human")]
        if live:
            best = max(live, key=lambda x: RANK.get(x[1], 0))[1]
            if best == "closed":
                return "review"
            if RANK.get(best, 0) >= RANK.get(main_status, 0):
                return best
        if any(s == "needs_human" for _, s in stale):
            return "needs_human"    # вопрос ветки без ответа: ждёт ответа, а не новой ветки
        if main_status == "in_progress" and not live:
            return "stale"
        if stale and main_status in ("open", ""):
            return "stale"
        return main_status or "open"

    def live_branch(self, cid):
        if self.eff.get(cid) == "closed":
            return None, None
        for b, s, k, c in self.claims.get(cid, []):
            if k == "live" and s in ("in_progress", "needs_human", "closed"):
                return b, c
        return None, None

    def occupied_areas(self, exclude=None):
        busy = {}
        for cid, st in self.eff.items():
            if cid == exclude or st not in ("in_progress", "needs_human", "review"):
                continue
            _, c = self.live_branch(cid)
            for a in (c or self.cards[cid]).get("area"):
                busy.setdefault(a, cid)
        return busy

    def is_closed_main(self, cid):
        c = self.cards.get(cid)
        return bool(c) and "_new_in" not in c.extra and c.get("status") == "closed"

    def blockers(self, cid):
        return [b for b in self.cards[cid].get("blocked_by") if not self.is_closed_main(b)]

    def ready(self):
        busy = self.occupied_areas()
        out = []
        for cid, c in self.cards.items():
            if self.eff[cid] not in ("open", "stale") or "_new_in" in c.extra:
                continue
            if c.get("type") == "epic" or self.blockers(cid) or not has_done(c):
                continue
            if any(a in busy and busy[a] != cid for a in c.get("area")):
                continue
            nb = parse_date(c.get("not_before"))
            if nb and nb > now():
                continue          # повторяющаяся/отложенная: раньше срока не выдаётся
            out.append(c)
        return sorted(out, key=lambda c: sort_key(c, self.prio, self.due_eff))

    def deferred(self):
        return sorted((c for cid, c in self.cards.items() if self.eff[cid] in ("open", "stale")
                       and parse_date(c.get("not_before")) and parse_date(c.get("not_before")) > now()),
                      key=lambda c: c.get("not_before"))

    def why_not_ready(self, cid):
        c, st = self.cards[cid], self.eff[cid]
        if st == "owner":
            return "ждёт ответа владельца: " + (c.get("question") or "вопрос в карточке")
        if st not in ("open", "stale"):
            return f"статус {st}"
        if c.get("type") == "epic":
            return "это эпик, берут его задачи"
        if not has_done(c):
            return "нет критерия «Готово, когда» — карточку дооформляет координатор"
        bl = self.blockers(cid)
        if bl:
            return "ждёт: " + ", ".join(bl)
        nb = parse_date(c.get("not_before"))
        if nb and nb > now():
            return f"не раньше {c.get('not_before')}"
        busy = self.occupied_areas(exclude=cid)
        hit = [f"{a} (занята {busy[a]})" for a in c.get("area") if a in busy]
        if hit:
            return "область занята: " + ", ".join(hit)
        return ""

    def all_ids(self):
        ids = set(self.cards)
        for s in self.sources:
            ids |= set(s.cards)
        return ids

    def live_count(self):
        return len({b for cid in self.eff if self.eff[cid] != "closed"
                    for b, s, k, _ in self.claims.get(cid, [])
                    if k == "live" and s in ("in_progress", "needs_human")})


def has_done(c):
    t = (c.section("Готово, когда") or "").strip()
    return t not in ("", "-", "…", "...")


def sort_key(c, prio=None, due=None):
    try:
        pr = int(c.get("priority") or 2)
    except ValueError:
        pr = 2
    if prio and c.id in prio:
        pr = min(pr, prio[c.id])
    d = (due or {}).get(c.id) or c.get("due") or "9999-99-99"
    return (pr, d, c.get("created") or "9999-99-99", c.id)


# ---------------------------------------------------------------- проверка целостности
def integrity(b):
    """Возвращает список (уровень, код, текст). Уровни: FAIL, WARN, INFO."""
    res = []
    ids = set(b.cards)
    for cid, paths in b.dups:
        res.append(("FAIL", "dup-id", f"{cid}: один номер у разных файлов: " +
                    "; ".join(f"{p} ({s})" for p, s in paths)))
    for cid, c in sorted(b.cards.items()):
        where = c.extra.get("_new_in", BASE)
        if "_noid" in c.extra or not ID_RE.match(cid):
            res.append(("FAIL", "bad-id", f"{c.path}: id «{c.meta.get('id')}» не по формату t-xxxx"))
        elif not os.path.basename(c.path).startswith(cid):
            res.append(("FAIL", "bad-name", f"{c.path}: имя файла не начинается с {cid}"))
        for k, allowed in (("status", STATUSES), ("type", TYPES), ("role", ROLES)):
            if c.get(k) not in allowed:
                res.append(("FAIL", "bad-field", f"{cid}: {k} = «{c.get(k)}» вне {sorted(allowed)}"))
        if c.get("size") and c.get("size") not in SIZES:
            res.append(("FAIL", "bad-field", f"{cid}: size = «{c.get('size')}» вне s/m/l"))
        if c.get("repeat") not in REPEATS:
            res.append(("FAIL", "bad-field", f"{cid}: repeat = «{c.get('repeat')}»"))
        if not re.fullmatch(r"[0-4]", c.get("priority") or ""):
            res.append(("FAIL", "bad-field", f"{cid}: priority должен быть 0..4"))
        if not c.get("title"):
            res.append(("FAIL", "no-title", f"{cid}: нет title"))
        for k in ("blocked_by",):
            for ref in c.get(k):
                if ref not in ids:
                    res.append(("FAIL", "broken-link", f"{cid}: {k} ссылается на несуществующую {ref}"))
        for k in ("parent", "from"):
            ref = c.get(k)
            if ref and ref not in ids:
                res.append(("FAIL", "broken-link", f"{cid}: {k} ссылается на несуществующую {ref}"))
        if c.get("status") not in ("inbox", "needs_human"):   # критерии нужны к моменту открытия
            for sec in ("Готово, когда", "Как проверить"):
                if not c.section(sec) or c.section(sec).strip() in ("", "-", "…", "..."):
                    res.append(("FAIL", "no-done", f"{cid}: пустой раздел «{sec}»"))
        if c.get("status") == "needs_human" and not c.get("question"):
            res.append(("WARN", "no-question", f"{cid}: needs_human без вопроса"))
        if OWNER_MARK in (c.section("Журнал") or "") and b.eff.get(cid) not in ("closed",):
            res.append(("WARN", "owner-answer-inbox", f"{cid}: открыто ответом владельца из inbox — сверить цитату в журнале"))
        if "\ufffd" in c.render():
            res.append(("WARN", "bad-encoding", f"{c.path}: файл не в UTF-8, битые символы заменены — пересохранить"))
        if c.get("type") == "epic" and b.eff.get(cid) not in ("closed", "owner"):
            kids = [k for k, kc in b.cards.items() if kc.get("parent") == cid]
            if kids and all(b.eff.get(k) == "closed" for k in kids):
                res.append(("INFO", "epic-done", f"{cid}: все {len(kids)} задач эпика закрыты — закрыть эпик (set status=closed)"))
        if c.get("size") == "l" and c.get("type") != "epic" and c.get("role") != "planner" and where == BASE and c.get("status") == "open":
            res.append(("WARN", "big-task", f"{cid}: size l — сначала планировщик дробит"))
    # циклы
    graph = {cid: [x for x in c.get("blocked_by") if x in ids] for cid, c in b.cards.items()}
    color, stack, cycles = {}, [], set()

    def dfs(n):
        color[n] = 1
        stack.append(n)
        for m in graph.get(n, []):
            if color.get(m) == 1:
                cyc = stack[stack.index(m):]
                k = min(range(len(cyc)), key=lambda i: cyc[i])
                cycles.add(tuple(cyc[k:] + cyc[:k]))
            elif not color.get(m):
                dfs(m)
        stack.pop()
        color[n] = 2
    sys.setrecursionlimit(10000)
    for n in sorted(graph):
        if not color.get(n):
            dfs(n)
    for cyc in sorted(cycles):
        res.append(("FAIL", "cycle", "круговая зависимость: " + " → ".join(cyc + (cyc[0],))))
    # ветки
    for cid in sorted(b.claims):
        live = sorted({br for br, s, k, _ in b.claims[cid] if k == "live" and s in ("in_progress", "needs_human", "closed")})
        if len(live) > 1:
            res.append(("FAIL", "double-claim", f"{cid}: две живые ветки на одну задачу: {', '.join(live)}"))
    for cid, st in sorted(b.eff.items()):
        if st == "stale":
            who = [br for br, s, k, _ in b.claims.get(cid, []) if k == "stale"]
            res.append(("WARN", "stale", f"{cid}: зависла (нет коммитов {LIVE_HOURS} ч"
                        + (f", ветка {', '.join(who)}" if who else "") + ") — можно выдать заново"))
        elif st == "review":
            br = next((x for x, st_, k, _ in b.claims.get(cid, []) if k == "live" and st_ == "closed"), None)
            res.append(("INFO", "review", f"{cid}: закрыта в ветке {br}, в main ещё открыта — на проверке"))
    claimed_branches = {br for cid in b.claims for br, s, k, _ in b.claims[cid]}
    for s in b.sources[1:]:
        if s.kind == "live" and s.ahead and s.name not in claimed_branches:
            res.append(("WARN", "no-claim", f"ветка {s.name}: {s.ahead} коммит(ов) без захвата карточки"))
    busy = {}
    for cid, st in b.eff.items():
        if st in ("in_progress", "needs_human"):
            _, c = b.live_branch(cid)
            for a in (c or b.cards[cid]).get("area"):
                busy.setdefault(a, []).append(cid)
    for a, lst in sorted(busy.items()):
        if len(lst) > 1:
            res.append(("WARN", "area-clash", f"область {a}: в работе сразу {', '.join(sorted(lst))}"))
    if b.live_count() > MAX_BRANCHES:
        res.append(("WARN", "too-many", f"живых веток {b.live_count()} > {MAX_BRANCHES}"))
    if b.in_git and b.current and b.current != BASE:
        mech = [cid for cid, lst in b.claims.items() for br, s, k, c in lst
                if br == b.current and c.get("role") == "mechanic"]
        code = [f for f in code_changes(b) if f not in ("tools/tasks.py", "tools/check.py")]
        if mech and code:
            res.append(("WARN", "mechanic-code", f"{', '.join(sorted(mech))}: роль mechanic (Sonnet) меняет код "
                        f"({', '.join(code[:3])}) — правка кода только executor на Opus"))
    for w in b.warnings:
        res.append(("WARN", "git", w))
    return res


# ---------------------------------------------------------------- запись
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o",
                     "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slugify(title):
    s = "".join(TRANSLIT.get(ch, ch) for ch in title.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return "-".join(s.split("-")[:6])[:48] or "task"


def new_id(taken):
    rnd = random.SystemRandom()
    for _ in range(1000):
        cid = "t-" + "".join(rnd.choice("0123456789abcdefghijklmnopqrstuvwxyz") for _ in range(4))
        if cid not in taken:
            return cid
    raise RuntimeError("не удалось подобрать свободный номер")


def write_card(b, c):
    full = os.path.join(b.root, c.path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(c.render())


def local_card(b, cid, strict=True):
    """Карточка из рабочей папки (её мы и правим)."""
    files = worktree_files(b.root)
    for path, text in files.items():
        c = parse_card(path, text)
        if c.id == cid:
            return c
    c = b.cards.get(cid)
    if c and "_new_in" not in c.extra and b.in_git and b.base_ref:
        # карточка свежая в main (например, из intake), а ветка от main старше: берём её из main
        text = b.git.run("show", f"{b.base_ref}:{c.path}", check=False)
        if text:
            os.makedirs(os.path.dirname(os.path.join(b.root, c.path)), exist_ok=True)
            with open(os.path.join(b.root, c.path), "w", encoding="utf-8") as fh:
                fh.write(text)
            return parse_card(c.path, text)
    if cid in b.cards:   # карточка есть только в другой ветке
        if strict:
            die(f"{cid} есть только в ветке {b.cards[cid].extra.get('_new_in', '?')}: менять её можно только там")
        return None
    die(f"нет задачи {cid}")


def commit(b, paths, msg, push=False):
    if not b.in_git:
        return
    b.git.run("add", "--", *paths)
    if not b.git.run("diff", "--cached", "--name-only", "--", *paths).strip():
        print("нечего коммитить")
        return
    # только свои пути: застейдженный чужой файл (его мог отклонить pre-commit) мимо хука не уйдёт
    b.git.run("commit", "-q", "--no-verify", "-m", msg, "--", *paths)
    print(f"коммит: {msg}")
    if push:
        push_or_die(b)


def push_or_die(b):
    """push; если GitHub ушёл вперёд (слили PR) — один раз rebase на свежий и снова push."""
    for attempt in range(3):
        if b.git.ok("push", "-q", "--no-verify", "-u", "origin", "HEAD"):
            print("отправлено на GitHub")
            return
        target = f"origin/{b.current}"
        b.git.ok("fetch", "-q", "origin", f"+refs/heads/{b.current}:refs/remotes/{target}")
        if b.git.ok("rev-parse", "--verify", "--quiet", target) and not b.git.ok("rebase", "-q", target):
            b.git.ok("rebase", "--abort")
            die(f"push отклонён, а rebase на {target} дал конфликт — разреши вручную (git pull --rebase), потом push")
    die("push не прошёл три раза — сеть или права; задача НЕ занята для остальных, повтори позже")


def uncommitted(b):
    """Изменённые и новые файлы рабочей папки (без игнорируемых)."""
    out, parts = [], b.git.run("status", "--porcelain", "-z", "-uall", check=False).split("\0")
    i = 0
    while i < len(parts):
        ent = parts[i]
        i += 1
        if len(ent) < 4:
            continue
        if ent[0] in "RC":
            i += 1        # у переименования следом идёт старое имя
        out.append(ent[3:])
    return sorted(set(out))


def die(msg, code=2):
    print("ОШИБКА: " + msg, file=sys.stderr)
    sys.exit(code)


def build_card(b, a, cid=None):
    cid = cid or new_id(b.all_ids())
    meta = {k: ([] if k in LIST_FIELDS else "") for k in FIELDS}
    meta.update(id=cid, title=clean_line(a.title), type=a.type, status=a.status, priority=str(a.priority),
                role=a.role, size=a.size, parent=a.parent or "", blocked_by=parse_list(a.blocked_by or ""),
                workstream=a.workstream or "", area=parse_list(a.area or ""), due=a.due or "",
                repeat=a.repeat or "", source=a.source or "", created=today(),
                not_before=getattr(a, "not_before", None) or "")
    meta["from"] = getattr(a, "from_") or ""
    secs = [("Что сделать", "\n" + clean_text(a.what) + "\n\n"),
            ("Готово, когда", "\n" + clean_text(a.done) + "\n\n"),
            ("Как проверить", "\n" + clean_text(a.verify) + "\n\n"),
            ("Журнал", "\n\n"), ("Результат", "\n\n")]
    return Card(f"{TASKS_DIR}/{cid}-{slugify(a.title)}.md", meta, secs)


# ---------------------------------------------------------------- настройки и общая папка
# общая папка проекта Claude: у веток /mnt/project-files, у координатора бывает /mnt/attach/project-files
SHARED = os.environ.get("TASKS_SHARED") or next(
    (p for p in ("/mnt/project-files", "/mnt/attach/project-files") if os.path.isdir(p)), "/mnt/project-files")


def project_name(root):
    """Имя проекта для общей папки: tools/fundament.cfg «project:», иначе имя репозитория на GitHub."""
    url = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=root,
                         capture_output=True, text=True).stdout.strip()
    return re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1]) or os.path.basename(root)


def config(root, key):
    env = os.environ.get("TASKS_" + key.upper())
    if env is not None:
        return env.strip()
    path = os.path.join(root, "tools", "fundament.cfg")
    vals = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8", errors="replace"):
            if ":" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split(":", 1)
                vals[k.strip()] = v.strip()
    if vals.get(key):
        return vals[key]
    # без настройки: /mnt/project-files/<проект>/…, но только если папка проекта там уже есть
    proj = os.path.join(SHARED, vals.get("project") or project_name(root))
    if key in ("inbox", "board_out") and os.path.isdir(proj):
        return os.path.join(proj, "inbox" if key == "inbox" else "board.json")
    return ""


INBOX_KEYS = {"title", "priority", "role", "size", "type", "due", "repeat", "not_before", "area",
              "blocked_by", "done", "verify", "owner", "question", "parent", "workstream", "id", "status",
              "owner_answer"}
OWNER_MARK = "[ответ владельца из inbox]"
SECTION_KEYS = {"готово, когда": "done", "как проверить": "verify", "что сделать": "what"}
UPDATE_KEYS = {"title", "priority", "role", "size", "due", "not_before", "area", "blocked_by", "parent", "workstream"}


def parse_inbox(name, text):
    """Файл просьбы — черновик карточки: шапка «ключ: значение» (между --- или просто в начале,
    можно и после строки «# заголовок»), тело со словами владельца; разделы «## Готово, когда»
    и «## Как проверить» становятся критериями. Заголовок: title:, иначе «# …», иначе имя файла."""
    meta, body, head, cur, secs = {}, [], True, None, {}
    for ln in text.splitlines():
        m = re.match(r"^([a-z_]+)\s*:\s*(.*)$", ln)
        if head and m and m.group(1) in INBOX_KEYS:
            meta[m.group(1)] = m.group(2).strip()
            continue
        if head and ln.strip() in ("---", ""):
            continue
        if head and ln.startswith("# ") and not meta.get("title"):
            meta["title"] = ln[2:].strip()
            continue          # шапка может идти и после заголовка
        head = False
        h = re.match(r"^##\s+(.*?)\s*$", ln)
        if h and h.group(1).lower() in SECTION_KEYS:
            cur = SECTION_KEYS[h.group(1).lower()]
            secs.setdefault(cur, [])
            continue
        (secs[cur] if cur else body).append(ln)
    for k, v in secs.items():
        v = "\n".join(v).strip()
        if k == "what":
            body = [v] + body
        elif v and not meta.get(k):
            meta[k] = v
    if not meta.get("title") and not meta.get("id"):
        meta["title"] = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", os.path.splitext(name)[0]).replace("-", " ") or name
    return meta, "\n".join(body).strip()


def inbox_key(name, raw):
    """Просьбу различаем по имени и содержимому: второй request.md с другим текстом — другая просьба."""
    return f"{name}#{hashlib.sha256(raw).hexdigest()[:12]}"


def inbox_card(taken, key, meta, body):
    """Новая карточка из просьбы. Ничего не выдаётся сразу: всё встаёт в inbox (оформляет координатор),
    «owner: да» — сразу «ждёт владельца»."""
    yes = meta.get("owner", "").lower() in ("да", "yes", "true", "1")
    a = argparse.Namespace(
        title=meta["title"], type=meta.get("type") if meta.get("type") in TYPES else "task",
        status="needs_human" if yes else "inbox",
        priority=int(meta["priority"]) if re.fullmatch(r"[0-4]", meta.get("priority", "")) else 2,
        role=meta.get("role") if meta.get("role") in ROLES else "executor",
        size=meta.get("size") if meta.get("size") in SIZES else "s",
        parent=meta.get("parent"), blocked_by=meta.get("blocked_by"), workstream=meta.get("workstream"),
        area=meta.get("area"), due=meta.get("due"), repeat=meta.get("repeat") if meta.get("repeat") in REPEATS else "",
        source="inbox:" + key, what=body or meta["title"], done=meta.get("done", ""),
        verify=meta.get("verify", ""), from_=None, not_before=meta.get("not_before"))
    c = build_card(None, a, new_id(taken))
    if yes:
        c.meta["question"] = clean_line(meta.get("question") or (body.splitlines()[0] if body else meta["title"]))
    return c


def inbox_update(c, key, meta, body):
    """Файл с «id: t-xxxx» — ответ или оформление существующей карточки (координатор без оболочки):
    поля из UPDATE_KEYS, разделы-критерии, «status: open» (выдавать) или «status: inbox».
    «Ждёт владельца» снимает только поле owner_answer: (цитата, дата, ссылка) — оно пишется в журнал.
    Возвращает текст причины, если файл применять нельзя."""
    owner = c.get("status") == "needs_human"
    answer = clean_line(meta.get("owner_answer", ""))
    if owner and not answer:
        return f"{c.id} ждёт владельца: нужен owner_answer: (цитата, дата, ссылка)"
    for k in UPDATE_KEYS & set(meta):
        c.meta[k] = parse_list(meta[k]) if k in LIST_FIELDS else clean_line(meta[k])
    if meta.get("done"):
        c.set_section("Готово, когда", "\n" + clean_text(meta["done"]) + "\n\n")
    if meta.get("verify"):
        c.set_section("Как проверить", "\n" + clean_text(meta["verify"]) + "\n\n")
    st = meta.get("status", "")
    ready_ok = has_done(c) and (c.section("Как проверить") or "").strip() not in ("", "-", "…", "...")
    if owner:
        # ответ получен; без критериев выдавать нельзя — карточка ждёт оформления в inbox
        c.meta["status"], c.meta["question"] = ("open" if ready_ok else "inbox"), ""
        c.set_section("Журнал", (c.section("Журнал") or "") + f"\n- {stamp()} [inbox:{key}] {OWNER_MARK}: {answer[:400]}")
    elif st in ("open", "inbox") and c.get("status") in ("inbox", "open"):
        c.meta["status"] = st if (st == "inbox" or ready_ok) else c.get("status")
    note = clean_line(body)[:400]
    if note or not owner:
        c.set_section("Журнал", (c.section("Журнал") or "") + f"\n- {stamp()} [inbox:{key}] координатор: {note or 'оформлено'}")
    return ""


def cmd_intake(b, a=None):
    """Просьбы из общей папки → карточки в main, ровно один раз. Ключ просьбы — имя файла и хэш
    содержимого (в source карточки или в её журнале). Файл уходит в inbox/done/ только после push."""
    d = (getattr(a, "dir", None) or config(b.root, "inbox")) if a else config(b.root, "inbox")
    quiet = a is None
    if d and not os.path.isdir(d) and os.path.isdir(os.path.dirname(os.path.dirname(d.rstrip("/")))):
        os.makedirs(os.path.join(d, "done"), exist_ok=True)     # общая папка есть, inbox ещё нет — создаём
    if not d or not os.path.isdir(d):
        if not quiet:
            print("inbox не настроен или папки нет" + (f": {d}" if d else " (tools/fundament.cfg: inbox: …)"))
        return 0
    names = sorted(f for f in os.listdir(d) if f.endswith(".md") and os.path.isfile(os.path.join(d, f)))
    if not names:
        if not quiet:
            print("inbox пуст")
        return 0
    if not b.in_git or not b.base_ref or "origin" not in b.git.run("remote", check=False).split():
        die("intake пишет карточки в main на GitHub: нужен git с origin и веткой main")
    raw = {}
    for name in names:
        with open(os.path.join(d, name), "rb") as fh:
            raw[name] = fh.read()
    keys = {name: inbox_key(name, raw[name]) for name in names}
    done, made, skipped = {}, [], []
    for attempt in range(3):
        # всегда во временной копии свежего main: рабочая папка (и main координатора) не получает
        # локальных коммитов, которые потом могли бы сойти за отправленные
        wt = tempfile.mkdtemp(prefix="intake-")
        try:
            b.git.ok("fetch", "-q", "origin", f"+refs/heads/{BASE}:refs/remotes/origin/{BASE}")
            if not b.git.ok("worktree", "add", "-q", "--detach", wt, f"origin/{BASE}"):
                die("intake: не удалось открыть main во временной папке (git worktree)")
            cards = {}
            for path, text in worktree_files(wt).items():
                c = parse_card(path, text)
                cards[c.id] = c
            seen = {}
            for c in cards.values():
                src = c.get("source") or ""
                if src.startswith("inbox:"):
                    seen[src[6:]] = c.id
                for m in re.finditer(r"\[inbox:([^\]]+)\]", c.section("Журнал") or ""):
                    seen[m.group(1)] = c.id
            taken = b.all_ids() | set(cards)
            done, made, skipped, paths = {}, [], [], []
            for name in names:
                key = keys[name]
                if key in seen:
                    done[name] = seen[key]
                    continue
                meta, body = parse_inbox(name, raw[name].decode("utf-8", "replace"))
                if meta.get("id"):
                    c = cards.get(meta["id"])
                    if not c:
                        skipped.append((name, f"{meta['id']} нет в main"))
                        continue
                    why = inbox_update(c, key, meta, body)
                    if why:
                        skipped.append((name, why))
                        continue
                    kind = "ответ"
                else:
                    c = inbox_card(taken, key, meta, body)
                    taken.add(c.id)
                    cards[c.id] = c
                    kind = "новая"
                full = os.path.join(wt, c.path)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(c.render())
                made.append((name, c, kind))
                paths.append(c.path)
                done[name] = c.id
            if paths:
                g = Git(wt)
                g.run("add", "--", *sorted(set(paths)))
                g.run("commit", "-q", "--no-verify", "-m", f"tasks: intake {len(made)} из inbox [skip ci]",
                      "--", *sorted(set(paths)))
                if not g.ok("push", "-q", "--no-verify", "origin", f"HEAD:{BASE}"):
                    continue          # main ушёл вперёд: заново с его свежей копии; файлы не трогаем
            break
        finally:
            b.git.ok("worktree", "remove", "--force", wt)
            shutil.rmtree(wt, ignore_errors=True)
    else:
        die("intake: push в main не прошёл три раза — файлы остались в inbox, повтори позже")
    if made:
        b.git.ok("fetch", "-q", "origin", f"+refs/heads/{BASE}:refs/remotes/origin/{BASE}")
        if not b.git.ok("merge", "--ff-only", "-q", f"origin/{BASE}"):   # ветке без своих коммитов и main — сразу
            if b.current == BASE:
                print("ВНИМАНИЕ: рабочая папка main не подтянулась (git pull --rebase)")
    os.makedirs(os.path.join(d, "done"), exist_ok=True)
    for name, cid in done.items():
        dest = os.path.join(d, "done", f"{cid}-{name}")
        n = 2
        while os.path.exists(dest):          # ничего не перезаписываем
            dest = os.path.join(d, "done", f"{cid}-{n}-{name}")
            n += 1
        try:
            os.replace(os.path.join(d, name), dest)
        except OSError:
            pass          # другая ветка уже перенесла
    for name, c, kind in made:
        print(f"inbox: {name} → {c.id} ({kind}, {c.get('status')}) {c.get('title')}")
    if skipped:
        os.makedirs(os.path.join(d, "skipped"), exist_ok=True)
    for name, why in skipped:
        # не крутим каждый раз: файл уходит в skipped/ с причиной, координатор видит его на доске
        dest = os.path.join(d, "skipped", name)
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(d, "skipped", f"{n}-{name}")
            n += 1
        try:
            os.replace(os.path.join(d, name), dest)
            with open(dest + ".why.txt", "w", encoding="utf-8") as fh:
                fh.write(why + "\n")
        except OSError:
            pass
        print(f"inbox: {name} отложен в skipped/ — {why}")
    if not made and not quiet:
        print("новых просьб нет: всё уже на доске")
    return len(made)


def skipped_files(root):
    d = config(root, "inbox")
    sk = os.path.join(d, "skipped") if d else ""
    if not sk or not os.path.isdir(sk):
        return []
    out = []
    for f in sorted(os.listdir(sk)):
        if f.endswith(".md"):
            why = os.path.join(sk, f + ".why.txt")
            out.append({"file": f, "why": open(why, encoding="utf-8").read().strip() if os.path.exists(why) else "?"})
    return out[:LIST_LIMIT]


def ahead_of_main(b, days=60):
    """Ветки, в которых есть работа, которой нет в main (main отстал): [(ветка, коммитов)]."""
    out = []
    if not b.in_git or not b.base_ref:
        return out
    since = (now() - timedelta(days=days)).timestamp()
    for line in b.git.run("for-each-ref", "--format=%(refname:short) %(committerdate:unix)",
                          "refs/remotes/origin/", check=False).splitlines():
        name, ts = line.rsplit(" ", 1)
        short = name[len("origin/"):]
        if short in (BASE, "HEAD") or name == "origin" or int(ts) < since or short.startswith("claude/"):
            continue
        n = int(b.git.run("rev-list", "--count", "--no-merges", f"{b.base_ref}..{name}", check=False).strip() or 0)
        if n and not b._merged(name, b.git.run("merge-base", b.base_ref, name, check=False).strip()):
            out.append((short, n))
    return sorted(out, key=lambda x: -x[1])


def cmd_init(b, a):
    """Первый запуск в проекте: tools/fundament.cfg с явными путями, папка inbox, проверка «main отстал»."""
    name = a.project or project_name(b.root)
    shared = a.shared or SHARED
    proj = os.path.join(shared, name)
    cfg = os.path.join(b.root, "tools", "fundament.cfg")
    lines = [f"# Фундамент {VERSION}: настройки проекта (tasks.py init)", f"project: {name}",
             f"inbox: {os.path.join(proj, 'inbox')}", f"board_out: {os.path.join(proj, 'board.json')}"]
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"tools/fundament.cfg: проект {name}, inbox {os.path.join(proj, 'inbox')}")
    if os.path.isdir(shared):
        os.makedirs(os.path.join(proj, "inbox", "done"), exist_ok=True)
        print(f"папка создана: {os.path.join(proj, 'inbox')}")
    else:
        print(f"ВНИМАНИЕ: общей папки {shared} здесь нет — inbox создаст первая ветка, где она есть")
    ahead = ahead_of_main(b)
    if ahead:
        print("СТОП перед подключением: main отстал, работа лежит в ветках: "
              + ", ".join(f"{n} (+{k})" for n, k in ahead[:8])
              + ". Сначала задача «свести в main без потерь» (scout, затем planner); владельцу — только если без потери нельзя.")
    else:
        print("main не отстал от рабочих веток")
    if ahead:
        sys.exit(3)


def write_board_out(root):
    """Свежая доска в общую папку проекта: координатор без оболочки читает её оттуда."""
    out = config(root, "board_out")
    if not out and config(root, "inbox"):     # по умолчанию рядом с inbox: <проект>/board.json
        out = os.path.join(os.path.dirname(config(root, "inbox").rstrip("/")), "board.json")
    nb = Board(root, fetch=False)
    if out:
        try:
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            tmp = out + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(board_data(nb), fh, ensure_ascii=False, indent=1)
            os.replace(tmp, out)
            print(f"доска: {out}")
        except OSError as e:
            print(f"ВНИМАНИЕ: доску в {out} записать не удалось: {e}")
    return nb


# ---------------------------------------------------------------- команды
def cmd_new(b, a):
    if a.repeat and not a.due:      # без срока повторяющаяся была бы готова всегда
        a.due = add_period(parse_date(today()), a.repeat).strftime("%Y-%m-%d")
        print(f"срок не задан: due {a.due} (через период от сегодня)", file=sys.stderr)
    c = build_card(b, a)
    write_card(b, c)
    print(f"{c.id}  {c.path}")
    if a.commit:
        on_base = b.current == BASE
        msg = (f"tasks: new {c.id} {a.title} [skip ci]" if on_base else f"{c.id}: new card (from {c.get('from') or '-'})")
        commit(b, [c.path], msg, push=a.push)


def cmd_ready(b, a):
    r = b.ready()
    if a.json:
        print(json.dumps([{"id": c.id, "title": c.get("title"), "priority": c.get("priority"),
                           "priority_eff": b.prio[c.id], "why": b.prio_label(c),
                           "role": c.get("role"), "model": MODEL_BY_ROLE.get(c.get("role"), ""),
                           "size": c.get("size"), "stale": b.eff[c.id] == "stale"} for c in r],
                         ensure_ascii=False, indent=1))
        return
    if not r:
        print("готовых задач нет")
    for c in r[:a.limit]:
        mark = " [зависла, выдать заново]" if b.eff[c.id] == "stale" else ""
        print(f"{c.id}  {b.prio_label(c)}  {c.get('role')}/{MODEL_BY_ROLE.get(c.get('role'), '?')}"
              f"  {c.get('size') or '-'}  {c.get('title')}{mark}")
    lc = b.live_count()
    if lc >= MAX_BRANCHES:
        print(f"! живых веток уже {lc} (предел {MAX_BRANCHES}) — новую не запускать")


def cmd_prime(b, a):
    cid = a.id
    if cid not in b.cards:
        die(f"нет задачи {cid}")
    c = b.cards[cid]
    if not config(b.root, "inbox"):
        print("! inbox не настроен: просьбы из общей папки не попадут на доску — tasks.py init (раздел «Первый запуск»)")
    out = [f"# {cid}: {c.get('title')}",
           f"роль: {c.get('role')} (модель {MODEL_BY_ROLE.get(c.get('role'), '?')}) · размер {c.get('size') or '-'}"
           f" · приоритет {b.prio_label(c)} · статус {b.eff[cid]}"]
    if c.get("area"):
        out.append("область: " + ", ".join(c.get("area")))
    for k in ("parent", "from", "due", "source"):
        if c.get(k):
            out.append(f"{k}: {c.get(k)}")
    for bl in c.get("blocked_by"):
        st = b.eff.get(bl, "нет такой")
        out.append(f"зависит от {bl}: {st}" + ("" if st == "closed" else "  ← НЕ ЗАКРЫТА"))
    ws = c.get("workstream") or (f"docs/workstreams/{c.get('area')[0]}.md" if c.get("area") else "")
    if ws:
        out.append(f"знания: {ws} (пиши только сюда)")
    for sec in ("Что сделать", "Готово, когда", "Как проверить"):
        body = [ln for ln in (c.section(sec) or "").splitlines() if ln.strip()]
        out.append(f"## {sec}")
        out.extend(body[:6] + (["…(полностью в " + c.path + ")"] if len(body) > 6 else []))
    log = [ln for ln in (c.section("Журнал") or "").splitlines() if ln.strip()]
    if log:
        out.append("## Журнал (последнее)")
        out.extend(log[-3:])
    why = b.why_not_ready(cid)
    out += ["## Протокол",
            "1. claim сразу, до работы; одна задача, новая работа — новая карточка (--from).",
            "2. Вопрос: tasks.py ask; координатор ответит, владельцу только деньги/необратимое/наружу.",
            "3. Посадка: остаток в карточки (--from) → tasks.py land --result … [--verified «что запущено, что вышло»] → check.py → PR «id: …».",
            "   PR только с docs/: в конце заголовка «[skip ci]». Ревьюер запускает check.py из main.",
            "4. Свой PR веди до слияния, не больше двух кругов правок; новую работу не бери.",
            "5. Не успеваешь за сутки — сажай готовое, остаток новыми карточками."]
    mine = b.live_branch(cid)[0] == b.current and b.current
    if b.eff[cid] == "owner" or (b.eff[cid] == "needs_human" and not mine):
        out.append(f"СТОП: задачу брать нельзя — {why or 'ждёт ответа на вопрос'}. Ничего не делай, сообщи координатору.")
    elif why and b.eff[cid] not in ("in_progress", "needs_human"):
        out.append(f"СТОП: задачу брать нельзя — {why}. Сообщи координатору.")
    elif b.eff[cid] == "open" or b.eff[cid] == "stale":
        out.append(f"теперь: python3 tools/tasks.py claim {cid}")
    print("\n".join(out[:40]))


def cmd_claim(b, a):
    cid = a.id
    if b.in_git and b.current == BASE:
        die("claim делается в ветке задачи, не в main")
    if cid not in b.cards:
        die(f"нет задачи {cid}")
    br, _ = b.live_branch(cid)
    if br and br != b.current and not a.force:
        die(f"{cid} уже занята живой веткой {br}")
    owner_guard(b, cid, a, "брать")
    why = b.why_not_ready(cid)
    if why and br != b.current and b.eff[cid] != "in_progress" and not a.force:
        die(f"{cid} брать нельзя: {why}")
    c = local_card(b, cid)
    c.meta["status"] = "in_progress"
    c.meta["assignee"] = a.assignee or os.environ.get("TASKS_ASSIGNEE") or b.current or "agent"
    c.meta["claimed"] = stamp_s()      # секунды: гонка в пределах минуты тоже разрешается
    if c.meta.get("question"):
        c.set_section("Журнал", (c.section("Журнал") or "") + f"\n- {stamp()} снова в работе после вопроса")
        c.meta["question"] = ""
    write_card(b, c)
    print(f"{cid} в работе: {c.meta['assignee']}")
    commit(b, [c.path], f"{cid}: claim [skip ci]", push=not a.no_push)
    if not a.no_push and b.in_git:
        race_check(b, cid, c)


def race_check(b, cid, mine):
    """После push перечитать ветки: если кто-то занял ту же задачу раньше — уступить сразу, а не задним числом."""
    far = datetime.max.replace(tzinfo=timezone.utc)
    me = parse_date(mine.get("claimed")) or far

    def rivals():
        fresh = Board(b.root, fetch=True)
        return sorted((parse_date(cc.get("claimed")) or far, br) for br, st, k, cc in fresh.claims.get(cid, [])
                      if br != b.current and k == "live" and st in ("in_progress", "needs_human", "closed"))

    # ничья в одну секунду: уступает ветка с большим именем; меньшая ждёт и смотрит ещё раз —
    # если соперник так и держит задачу (проверил до нашего push и нас не видел), уступает и она
    earlier = [r for r in rivals() if r[0] < me or (r[0] == me and r[1] < b.current)]
    tie = [r for r in rivals() if r[0] == me and r[1] > b.current] if not earlier else []
    pause = 1 if os.environ.get("TASKS_STAND") == "1" else 3
    for _ in range(3 if tie else 0):
        time.sleep(pause)
        tie = [r for r in rivals() if r[0] == me and r[1] > b.current]
        if not tie:
            break
    earlier = earlier or tie
    if not earlier:
        return
    base = b.git.run("show", f"{b.base_ref}:{mine.path}", check=False) if b.base_ref else ""
    if base:
        with open(os.path.join(b.root, mine.path), "w", encoding="utf-8") as fh:
            fh.write(base)
    commit(b, [mine.path], f"{cid}: unclaim, раньше заняла {earlier[0][1]} [skip ci]", push=True)
    die(f"гонка: {cid} раньше заняла ветка {earlier[0][1]} — захват снят, работу не начинай, сообщи координатору")


def code_changes(b):
    """Файлы ветки вне docs/ и не тексты .md/.txt (код, конфиги): для них land требует --verified."""
    if not b.in_git or not b.base_ref or b.current == BASE:
        return []
    mb = b.git.run("merge-base", b.base_ref, "HEAD", check=False).strip()
    if not mb:
        return []
    files = set(b.git.run("diff", "--name-only", mb, check=False).split("\n"))
    files |= set(uncommitted(b))
    return sorted(f for f in files if f and not f.startswith("docs/")
                  and (f.startswith("tools/") or not f.lower().endswith((".md", ".txt"))))   # tools/*.txt — код проверки


def clean_line(v):
    return " ".join((v or "").split())


def clean_text(v):
    """Текст раздела: строка «## …» внутри создала бы новый раздел карточки."""
    return "\n".join(("#" + ln if ln.lstrip().startswith("## ") else ln) for ln in (v or "").splitlines())


def owner_guard(b, cid, a, what):
    if cid in b.eff and b.eff[cid] == "owner":
        if a.force and (not b.in_git or b.current == BASE):
            return          # координатор на main, осознанно
        die(f"{cid} ждёт ответа владельца — {what} нельзя"
            + (" (--force работает только у координатора на main)" if a.force else "")
            + "; после ответа координатор ставит status=open")


def cmd_ask(b, a):
    owner_guard(b, a.id, a, "ask")
    c = local_card(b, a.id)
    c.meta["status"] = "needs_human"
    c.meta["question"] = clean_line(a.question)
    log = (c.section("Журнал") or "") + f"\n- {stamp()} вопрос: {c.meta['question']}"
    c.set_section("Журнал", log)
    write_card(b, c)
    commit(b, [c.path], f"{a.id}: question [skip ci]", push=not a.no_push)


def add_period(d, rep):
    if rep == "weekly":
        return d + timedelta(days=7)
    m = d.month % 12 + 1
    return d.replace(year=d.year + (d.month == 12), month=m, day=min(d.day, 28))


def next_due(due, rep):
    """Следующий срок: прежний плюс период, сдвинутый в будущее (закрыли с опозданием — не копим долг);
    срока не было — через период от сегодня. Выдаётся за сутки до срока (not_before)."""
    d = parse_date(due)
    base = parse_date(today())
    if not d:
        return add_period(base, rep).strftime("%Y-%m-%d")
    d = add_period(d, rep)
    while d <= base:
        d = add_period(d, rep)
    return d.strftime("%Y-%m-%d")


def cmd_land(b, a):
    cid = a.id
    owner_guard(b, cid, a, "сажать")
    c = local_card(b, cid)
    if not c:
        die(f"{cid} нет в рабочей папке")
    if b.in_git and b.current == BASE and not a.force:
        die("land делается в ветке задачи; координатор на main закрывает через set status=closed")
    if not a.result:
        die("нужен --result: что сделано и где лежит")
    code = code_changes(b)
    if code and not a.verified:
        die("ветка меняет код (" + ", ".join(code[:3]) + "): нужен --verified "
            "\"что запущено и что вышло\" — без сквозной проверки задачу не закрывать")
    again = c.get("status") == "closed"      # повторный land: только обновить «Результат»
    c.meta["status"] = "closed"
    c.meta["closed"] = c.get("closed") if again and c.get("closed") else stamp()
    c.meta["question"] = ""
    if a.log:
        c.set_section("Журнал", (c.section("Журнал") or "") + f"\n- {stamp()} {clean_line(a.log)}")
    c.set_section("Результат", clean_text(a.result))
    if a.verified:
        c.set_section("Журнал", (c.section("Журнал") or "") + f"\n- {stamp()} Проверено: {clean_line(a.verified)}")
    write_card(b, c)
    paths = [c.path]
    print(f"{cid} закрыта в ветке; закроется в main со слиянием PR")
    nexts = [k for k, kc in b.cards.items() if kc.get("from") == cid and kc.get("repeat")]
    if c.get("repeat") and (again or nexts):
        print("следующая по repeat уже есть: " + (", ".join(nexts) or "создана прошлым land"))
    elif c.get("repeat"):
        nid = new_id(b.all_ids() | {cid})
        n = Card(f"{TASKS_DIR}/{nid}-{slugify(c.get('title'))}.md", dict(c.meta), [
            (h, "\n\n" if h in ("Журнал", "Результат") else t) for h, t in c.sections])
        nd = next_due(c.get("due"), c.get("repeat"))
        nbd = parse_date(nd)
        n.meta.update(id=nid, status="open", assignee="", claimed="", closed="", question="",
                      created=today(), due=nd,
                      not_before=(nbd - timedelta(days=1)).strftime("%Y-%m-%d") if nbd else "")
        n.meta["from"] = cid
        write_card(b, n)
        paths.append(n.path)
        print(f"следующая по repeat: {nid}")
    if b.in_git:
        pending = uncommitted(b)
        extra = [f for f in pending if is_card_file(f) and f.startswith(TASKS_DIR + "/") and f not in paths]
        paths += extra          # карточки из new --from уезжают вместе с посадкой
        if extra:
            print("с посадкой: " + ", ".join(extra))
        rest = [f for f in pending if f not in paths]
        if rest:
            print("ВНИМАНИЕ: не закоммичено (в PR не попадёт): " + ", ".join(rest[:10]))
    if not a.no_commit:
        commit(b, paths, f"{cid}: land [skip ci]", push=not a.no_push)
    nb = write_board_out(b.root)
    nxt = [c.id for c in nb.ready() if c.id != cid][:3]
    print("дальше по очереди: " + (", ".join(nxt) if nxt else "готовых задач нет"))


def cmd_set(b, a):
    if a.release:
        owner_guard(b, a.id, a, "release")
    c = local_card(b, a.id)
    for kv in a.pairs:
        if "=" not in kv:
            die(f"ожидаю ключ=значение, дано «{kv}»")
        k, v = kv.split("=", 1)
        if k not in FIELDS or k == "id":
            die(f"поле {k} менять нельзя или его нет")
        c.meta[k] = parse_list(v) if k in LIST_FIELDS else clean_line(v)
    if a.release:
        c.meta.update(status="open", assignee="", claimed="")
    write_card(b, c)
    if a.commit:
        msg = f"tasks: {a.id} {' '.join(a.pairs) or 'release'} [skip ci]"
        commit(b, [c.path], msg, push=a.push)


def board_data(b, full=False):
    ready = b.ready()
    week_ago = now() - timedelta(days=7)
    rows = lambda st: [{"id": cid, "title": b.cards[cid].get("title"), "branch": b.live_branch(cid)[0],
                        "question": (b.live_branch(cid)[1] or b.cards[cid]).get("question")}
                       for cid in sorted(b.eff) if b.eff[cid] == st]
    closed = [{"id": cid, "title": c.get("title"), "closed": c.get("closed")} for cid, c in b.cards.items()
              if b.eff[cid] == "closed" and (parse_date(c.get("closed")) or datetime.min.replace(tzinfo=timezone.utc)) >= week_ago]
    probs = integrity(b)
    owner = [{"id": cid, "title": b.cards[cid].get("title"), "branch": None,
              "question": b.cards[cid].get("question")} for cid in sorted(b.eff) if b.eff[cid] == "owner"]
    d = {
        "version": VERSION, "generated": stamp(),
        "owner": owner,
        "questions": rows("needs_human"),
        "inbox": [{"id": cid, "title": c.get("title")} for cid, c in sorted(b.cards.items()) if b.eff[cid] == "inbox"],
        "inbox_dir": config(b.root, "inbox") or "",
        "inbox_skipped": skipped_files(b.root),
        "epics": [{"id": cid, "title": c.get("title")} for cid, c in sorted(b.cards.items())
                  if c.get("type") == "epic" and b.eff[cid] not in ("closed",)],
        "blocked": [{"id": cid, "title": c.get("title"), "waits": b.blockers(cid)} for cid, c in sorted(b.cards.items())
                    if b.eff[cid] in ("open", "stale") and c.get("type") != "epic" and b.blockers(cid)],
        "ready": [{"id": c.id, "title": c.get("title"), "role": c.get("role"), "why": b.prio_label(c)} for c in ready],
        "urgent_waiting": [{"id": cid, "title": c.get("title"), "priority": c.get("priority"),
                            "waits": [f"{x} ({b.eff.get(x, '?')})" for x in b.blockers(cid)]}
                           for cid, c in sorted(b.cards.items(), key=lambda kv: sort_key(kv[1]))
                           if b.eff[cid] in ("open", "stale") and (c.get("priority") or "2") in ("0", "1")
                           and b.blockers(cid)],
        "deferred": [{"id": c.id, "title": c.get("title"), "not_before": c.get("not_before")} for c in b.deferred()],
        "in_progress": rows("in_progress"), "review": rows("review"), "stale": rows("stale"),
        "next": [{"id": c.id, "title": c.get("title"), "role": c.get("role"), "why": b.prio_label(c)} for c in ready[:3]],
        "closed_week": sorted(closed, key=lambda x: x["closed"], reverse=True),
        "counts": {"open": sum(1 for s in b.eff.values() if s == "open"), "ready": len(ready),
                   "owner": sum(1 for s in b.eff.values() if s == "owner"),
                   "inbox": sum(1 for s in b.eff.values() if s == "inbox"),
                   "live_branches": b.live_count(), "branch_limit": MAX_BRANCHES,
                   "fail": sum(1 for p in probs if p[0] == "FAIL"),
                   "warn": sum(1 for p in probs if p[0] == "WARN")},
    }
    # длинные списки режем: доска на 1000 карточек не должна стоить координатору десятки КБ контекста
    d["totals"] = {k: len(d[k]) for k in ("ready", "deferred", "blocked", "epics", "inbox", "closed_week", "urgent_waiting",
                                    "in_progress", "review", "stale", "questions")}
    if not full:
        for k in d["totals"]:
            d[k] = d[k][:LIST_LIMIT]
    return d


def cmd_board(b, a):
    d = board_data(b, full=getattr(a, "all", False))
    if getattr(a, "out", None):
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(board_data(b), fh, ensure_ascii=False, indent=1)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return
    def block(title, items, fmt, key=None):
        total = d["totals"].get(key, len(items)) if key else len(items)
        print(f"## {title} ({total})")
        for x in items:
            print("- " + fmt(x))
        if not items:
            print("- нет")
        elif total > len(items):
            print(f"- … и ещё {total - len(items)} (board --all)")
    block("Ждёт владельца", d["owner"], lambda x: f"{x['id']} {x['title']}: {x['question'] or '?'}")
    if not d["inbox_dir"]:
        print("! inbox не настроен (tasks.py init): просьбы из общей папки на доску не попадут")
    block("Файлы inbox отложены", d["inbox_skipped"], lambda x: f"{x['file']}: {x['why']}")
    block("Срочное ждёт", d["urgent_waiting"], lambda x: f"{x['id']} p{x['priority']} {x['title']} ← из-за {', '.join(x['waits'])}")
    block("Вопросы веток", d["questions"], lambda x: f"{x['id']} {x['title']}: {x['question'] or '?'}"
          + ("" if x["branch"] else " (ветка молчит)"))
    block("В работе", d["in_progress"], lambda x: f"{x['id']} {x['title']} ({x['branch']})", "in_progress")
    block("На проверке", d["review"], lambda x: f"{x['id']} {x['title']} ({x['branch']})", "review")
    block("Зависли", d["stale"], lambda x: f"{x['id']} {x['title']}", "stale")
    if getattr(a, "all", False):
        block("Готовы", d["ready"], lambda x: f"{x['id']} {x['title']} [{x['role']}]", "ready")
    else:
        block("Следующие", d["next"], lambda x: f"{x['id']} {x['title']} [{x['role']}]"
              + (f" {x['why']}" if "→" in x.get("why", "") or "от " in x.get("why", "") else ""))
    block("Отложены (не раньше)", d["deferred"], lambda x: f"{x['id']} {x['title']} — с {x['not_before']}", "deferred")
    block("Заблокированы", d["blocked"], lambda x: f"{x['id']} {x['title']} ← ждёт {', '.join(x['waits'])}", "blocked")
    block("Эпики", d["epics"], lambda x: f"{x['id']} {x['title']}", "epics")
    block("Inbox (дооформить)", d["inbox"], lambda x: f"{x['id']} {x['title']}", "inbox")
    block("Закрыто за неделю", d["closed_week"], lambda x: f"{x['id']} {x['title']}", "closed_week")
    k = d["counts"]
    print(f"\nждёт владельца {k['owner']} · открыто {k['open']} · готово {k['ready']} · inbox {k['inbox']} · веток {k['live_branches']}/{k['branch_limit']}"
          f" · ошибок {k['fail']} · предупреждений {k['warn']}")


def cmd_check(b, a):
    res = integrity(b)
    if a.json:
        print(json.dumps([{"level": l, "code": c, "text": t} for l, c, t in res], ensure_ascii=False, indent=1))
    else:
        for l, c, t in res:
            print(f"{l} {c}: {t}")
        fails = sum(1 for r in res if r[0] == "FAIL")
        print(f"доска: {len(b.cards)} карточек, ошибок {fails}" + (" — OK" if not fails else ""))
    sys.exit(1 if any(r[0] == "FAIL" for r in res) else 0)


def cmd_stats(b, a):
    closed = [c for cid, c in b.cards.items() if b.eff[cid] == "closed"]
    since = now() - timedelta(days=a.days)
    recent = [c for c in closed if (parse_date(c.get("closed")) or datetime.min.replace(tzinfo=timezone.utc)) >= since]
    roles = {}
    for c in recent:
        roles[c.get("role")] = roles.get(c.get("role"), 0) + 1
    prs = {}
    if b.in_git and b.base_ref:
        for subj in b.git.run("log", b.base_ref, "--first-parent", f"--since={a.days * 3}.days",
                              "--format=%s", check=False).splitlines():
            m = re.match(r"^(t-[0-9a-z]{4})\b.*\(#\d+\)$", subj)
            if m:
                prs[m.group(1)] = prs.get(m.group(1), 0) + 1
    per = [prs.get(c.id, 0) for c in recent]
    out = {"days": a.days, "closed": len(recent), "roles": roles,
           "prs_per_closed": round(sum(per) / len(per), 2) if per else None,
           "stale_now": sum(1 for s in b.eff.values() if s == "stale"),
           "planner_share": round(roles.get("planner", 0) / len(recent), 2) if recent else None,
           "note": "ветки старше %d дней не читаются; расход лимита снимается с экрана Usage" % SCAN_DAYS}
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_archive(b, a):
    limit = now() - timedelta(days=30)
    moved = []
    for path, text in worktree_files(b.root).items():
        c = parse_card(path, text)
        d = parse_date(c.get("closed"))
        if c.get("status") == "closed" and d and d < limit and "/archive/" not in path:
            dest = f"{TASKS_DIR}/archive/{d.strftime('%Y-%m')}/{os.path.basename(path)}"
            os.makedirs(os.path.join(b.root, os.path.dirname(dest)), exist_ok=True)
            if b.in_git:
                b.git.run("mv", path, dest)
            else:
                os.rename(os.path.join(b.root, path), os.path.join(b.root, dest))
            moved += [path, dest]
            print(f"{c.id} → {dest}")
    if moved and a.commit and b.in_git:
        b.git.run("commit", "-q", "--no-verify", "-m", f"tasks: archive {len(moved)//2} closed [skip ci]", "--", *moved)
        print("коммит сделан")
        if a.push:
            push_or_die(b)
    if not moved:
        print("архивировать нечего")


def main(argv=None):
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # `| head` не должен давать трассу
    p = argparse.ArgumentParser(prog="tasks.py", description="доска задач Фундамент v2")
    p.add_argument("--root", default=".")
    p.add_argument("--no-fetch", action="store_true", help="не обновлять сведения о ветках")
    p.add_argument("--version", action="version", version=VERSION)
    sp = p.add_subparsers(dest="cmd", required=True)

    n = sp.add_parser("new")
    n.add_argument("--title", required=True)
    n.add_argument("--type", default="task", choices=sorted(TYPES))
    n.add_argument("--status", default="open", choices=["inbox", "open"])
    n.add_argument("--priority", type=int, default=2, choices=range(5))
    n.add_argument("--role", default="executor", choices=sorted(ROLES))
    n.add_argument("--size", default="s", choices=sorted(SIZES))
    for k in ("parent", "blocked-by", "workstream", "area", "due", "source", "what", "done", "verify"):
        n.add_argument("--" + k)
    n.add_argument("--not-before", help="ГГГГ-ММ-ДД: раньше этой даты задача не выдаётся")
    n.add_argument("--from", dest="from_")
    n.add_argument("--repeat", choices=["weekly", "monthly"])
    n.add_argument("--commit", action="store_true")
    n.add_argument("--push", action="store_true")

    r = sp.add_parser("ready")
    r.add_argument("--json", action="store_true")
    r.add_argument("--limit", type=int, default=10)

    for name in ("prime", "claim", "ask", "land", "set"):
        x = sp.add_parser(name)
        x.add_argument("id")
        if name in ("claim", "ask", "land"):
            x.add_argument("--no-push", action="store_true")
        if name == "claim":
            x.add_argument("--assignee")
        if name in ("claim", "ask", "land", "set"):
            x.add_argument("--force", action="store_true", help="мимо защиты «ждёт владельца» — только координатор")
        if name == "ask":
            x.add_argument("--question", required=True)
        if name == "land":
            x.add_argument("--result")
            x.add_argument("--verified", help="что запущено и что вышло (обязательно, если ветка меняет код)")
            x.add_argument("--log")
            x.add_argument("--no-commit", action="store_true")
        if name == "set":
            x.add_argument("pairs", nargs="*")
            x.add_argument("--release", action="store_true", help="снять занятость (зависшая)")
            x.add_argument("--commit", action="store_true")
            x.add_argument("--push", action="store_true")
    for name in ("board", "check"):
        sp_ = sp.add_parser(name)
        sp_.add_argument("--json", action="store_true")
        if name == "board":
            sp_.add_argument("--all", action="store_true", help="все готовые задачи, не только три")
            sp_.add_argument("--out", help="ещё и записать json доски в этот файл")
    st = sp.add_parser("stats")
    st.add_argument("--days", type=int, default=7)
    ar = sp.add_parser("archive")
    ar.add_argument("--commit", action="store_true")
    ar.add_argument("--push", action="store_true")
    it = sp.add_parser("init", help="первый запуск: fundament.cfg, папка inbox, проверка «main отстал»")
    it.add_argument("--project", help="имя проекта в общей папке (по умолчанию имя репозитория)")
    it.add_argument("--shared", help="общая папка (по умолчанию /mnt/project-files)")
    ik = sp.add_parser("intake")
    ik.add_argument("--dir", help="папка inbox (иначе из tools/fundament.cfg)")

    a = p.parse_args(argv)
    try:
        run(a)
    except RuntimeError as e:      # отказ git (хук, права, конфликт) — понятный текст вместо трассы
        die(f"git не выполнил команду: {str(e)[:400]}. Карточка могла остаться изменённой, но не записанной: "
            "git status; повтори команду после исправления")


def run(a):
    b = Board(a.root, fetch=not a.no_fetch)
    if a.cmd == "prime":                        # просьбы из общей папки — на доску до старта ветки
        try:
            if cmd_intake(b):
                b = Board(a.root, fetch=False)
        except SystemExit:
            print("! intake не прошёл (см. выше): просьбы остались в inbox, ветку можно начинать", file=sys.stderr)
    {"new": cmd_new, "ready": cmd_ready, "prime": cmd_prime, "claim": cmd_claim, "ask": cmd_ask,
     "land": cmd_land, "set": cmd_set, "board": cmd_board, "check": cmd_check, "stats": cmd_stats,
     "archive": cmd_archive, "intake": cmd_intake, "init": cmd_init}[a.cmd](b, a)


if __name__ == "__main__":
    main()
