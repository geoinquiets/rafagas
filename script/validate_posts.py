# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "python-frontmatter>=0.4.5",
#     "PyYAML>=5.4",
# ]
# ///
"""Validate Rafagas post files (frontmatter shape, rid, date, keywords, lang...).

The rules follow CONTRIBUTING.md. Older posts contain many legacy quirks
(multi-word keywords, lowercase or non-ISO `lang` codes, duplicated rids...),
so errors are only *blocking* for what a change adds or edits:

* a post that is new compared to the base branch is validated strictly;
* in a post that already exists in the base branch, a problem that was
  already there (same field value, or an unchanged link entry) is downgraded
  to a warning, so maintenance edits (link checker, `invalid: true`...) on old
  posts never get blocked.

Usage:

    uv run script/validate_posts.py                    # posts changed vs the base branch
    uv run script/validate_posts.py _posts/2026/x.md   # specific files (pre-commit)
    uv run script/validate_posts.py --base origin/gh-pages
    uv run script/validate_posts.py --all              # report on every post, never fails

Exit code: 1 if there are blocking errors, 2 on usage errors, 0 otherwise.
Under GitHub Actions, findings are printed as workflow annotations.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import frontmatter
import yaml

# ---------------------------------------------------------------------------
# Rules configuration
# ---------------------------------------------------------------------------

POSTS_DIR = "_posts"
BASE_CANDIDATES = ("origin/gh-pages", "gh-pages")

# A link published again within this window gets a warning (same as the
# lookback used by update_rafaga.py to skip already published links).
REPUBLISHED_LOOKBACK_DAYS = 180

POST_KEYS = {"layout", "date", "rid", "rafagas", "author", "title", "permalink", "translator"}
LINK_KEYS = {
    "keyw", "desc", "link", "lang", "via", "invalid", "nocheck",
    "microlink", "lastCheck",  # written by scripts/microlink.py and script/check-links
    "orig", "orig_date", "toot",  # reserved for the translation automation
}
# Keys maintained by scripts: changing them must not make an old entry "new".
VOLATILE_LINK_KEYS = {"microlink", "lastCheck", "invalid", "nocheck"}

KEYW_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"
)
VIA_RE = re.compile(r"^@\S+$")

ISO_639_1 = frozenset(
    """aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch
    co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd
    gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka
    kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi
    mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl
    ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw
    ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo
    za zh zu""".upper().split()
)

# ---------------------------------------------------------------------------
# URL normalization (kept in sync with script/update_rafaga.py)
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = frozenset(
    "utm_source utm_medium utm_campaign utm_term utm_content "
    "fbclid gclid ref source".split()
)
_INDEX_SUFFIXES = ("/index.html", "/index.htm", "/index.php")


def normalize_url(url: str) -> str:
    """Canonical form of *url* used to detect repeated links."""
    try:
        p = urlparse(url)
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path
        for suffix in _INDEX_SUFFIXES:
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break
        path = path.rstrip("/") or "/"
        kept = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING_PARAMS]
        return urlunparse(("https", netloc, path, p.params, urlencode(sorted(kept)), ""))
    except Exception:
        return url.lower().rstrip("/")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    path: str
    line: int
    level: str  # "error" | "warning"
    code: str
    message: str
    field: str | None = None  # frontmatter key, for post-level findings
    entry: str | None = None  # entry id, for link-level findings


@dataclass
class PostInfo:
    path: str
    layout: object
    rid: object
    cal_date: dt.date | None
    links: list


class Index:
    """Lookup tables over every post, so each check is O(1) instead of a full scan."""

    def __init__(self, posts: list[PostInfo]):
        self.posts = posts
        self.by_rid: dict = defaultdict(list)
        self.by_date: dict = defaultdict(list)
        self.by_link: dict = defaultdict(list)
        for p in posts:
            if isinstance(p.rid, int):
                self.by_rid[p.rid].append(p.path)
            if p.cal_date:
                self.by_date[p.cal_date].append(p.path)
                for link in set(p.links):
                    self.by_link[link].append((p.cal_date, p.path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def calendar_date(value) -> dt.date | None:
    """Return the calendar date of a frontmatter `date` value, or None if invalid."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and DATE_RE.match(value):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def entry_id(entry: dict) -> str:
    """Stable identity of a link entry, ignoring script-maintained keys."""
    content = {k: v for k, v in entry.items() if k not in VOLATILE_LINK_KEYS}
    return json.dumps(content, sort_keys=True, default=str, ensure_ascii=False)


def repo_path(path) -> str:
    """Path relative to the repository root (the working directory), with / separators."""
    p = Path(path)
    try:
        if p.is_absolute():
            p = p.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        pass
    return p.as_posix()


def is_template(path) -> bool:
    return "template" in str(path)


class Locator:
    """Best-effort mapping from frontmatter keys / link entries to line numbers."""

    def __init__(self, text: str, n_entries: int):
        self.lines = text.splitlines()
        starts: list[int] = []
        in_rafagas = False
        for i, line in enumerate(self.lines):
            if re.match(r"^rafagas\s*:", line):
                in_rafagas = True
                continue
            if not in_rafagas:
                continue
            if re.match(r"^---\s*$", line):
                break
            if re.match(r"^\s{0,4}-\s+[A-Za-z_]+\s*:", line):
                starts.append(i)
            elif line and not line[0].isspace() and not line.startswith("-"):
                in_rafagas = False
        self.starts = starts if len(starts) == n_entries else []

    def post_line(self, key: str) -> int:
        for i, line in enumerate(self.lines):
            if re.match(rf"^{re.escape(key)}\s*:", line):
                return i + 1
        return 1

    def entry_line(self, index: int, key: str | None = None) -> int:
        if not self.starts:
            return self.post_line("rafagas")
        start = self.starts[index]
        end = self.starts[index + 1] if index + 1 < len(self.starts) else len(self.lines)
        if key:
            for i in range(start, end):
                if re.match(rf"^\s*-?\s*{re.escape(key)}\s*:", self.lines[i]):
                    return i + 1
        return start + 1


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def resolve_base(ref: str | None) -> str | None:
    """Return the merge-base commit between HEAD and the base branch, if any."""
    for candidate in [ref] if ref else BASE_CANDIDATES:
        if git("rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}") is None:
            continue
        merge_base = git("merge-base", "HEAD", candidate)
        return merge_base.strip() if merge_base else candidate
    return None


def changed_files(base: str) -> list[str]:
    """Posts added/modified/renamed in the working tree compared to *base*."""
    out = git("diff", "--name-only", "--diff-filter=AMR", base, "--", POSTS_DIR) or ""
    untracked = git("ls-files", "--others", "--exclude-standard", "--", POSTS_DIR) or ""
    names = {n for n in (out + untracked).splitlines() if n.endswith(".md")}
    return sorted(n for n in names if Path(n).is_file() and not is_template(n))


def base_text(base: str | None, path: str) -> str | None:
    if not base:
        return None
    return git("show", f"{base}:{Path(path).as_posix()}")


# ---------------------------------------------------------------------------
# Index of all posts (uniqueness, ordering, republished links)
# ---------------------------------------------------------------------------


def build_index(posts_dir: str) -> Index:
    posts: list[PostInfo] = []
    for md in sorted(Path(posts_dir).glob("**/*.md")):
        if is_template(md):
            continue
        try:
            post = frontmatter.loads(md.read_text(encoding="utf-8"))
        except Exception:
            continue  # unparsable files are reported when they are validated
        links = []
        rafagas = post.get("rafagas")
        if isinstance(rafagas, list):
            for r in rafagas:
                if isinstance(r, dict) and isinstance(r.get("link"), str):
                    links.append(normalize_url(r["link"]))
        rid = post.get("rid")
        if isinstance(rid, str) and rid.strip().isdigit():
            rid = int(rid)  # legacy posts quote their rid ('127')
        posts.append(
            PostInfo(
                path=md.as_posix(),
                layout=post.get("layout"),
                rid=rid,
                cal_date=calendar_date(post.get("date")),
                links=links,
            )
        )
    return Index(posts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_post(path: str, text: str, index: Index, today: dt.date) -> tuple[list[Finding], dict | None]:
    """Return (findings, metadata). Metadata is None if the post could not be parsed."""
    findings: list[Finding] = []

    def add(level, code, message, line, field=None, entry=None):
        findings.append(Finding(path, line, level, code, message, field, entry))

    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else 1
        problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        add("error", "post-frontmatter", f"Frontmatter is not valid YAML: {problem}", line)
        return findings, None
    except Exception as exc:  # pragma: no cover - defensive
        add("error", "post-frontmatter", f"Could not read frontmatter: {exc}", 1)
        return findings, None

    meta = post.metadata
    rafagas = meta.get("rafagas")
    loc = Locator(text, len(rafagas) if isinstance(rafagas, list) else 0)

    # -- layout: only rafaga posts follow the rules below ---------------------
    layout = meta.get("layout")
    if layout is None:
        add("error", "post-layout", "Missing `layout` (expected `rafaga`).", loc.post_line("layout"), "layout")
        return findings, meta
    if layout != "rafaga":
        return findings, meta  # other layouts (e.g. `post`) are free-form pages

    for key in meta:
        if key not in POST_KEYS:
            add("warning", "post-key", f"Unknown frontmatter key `{key}` (typo?).", loc.post_line(key))

    # -- date -----------------------------------------------------------------
    cal_date = calendar_date(meta.get("date"))
    if "date" not in meta:
        add("error", "post-date", "Missing `date`.", 1, "date")
    elif cal_date is None:
        add("error", "post-date",
            f"`date` {meta.get('date')!r} is not ISO 8601 (e.g. 2026-10-28 or 2026-10-28T09:04:38+0100).",
            loc.post_line("date"), "date")
    elif cal_date > today + dt.timedelta(days=1):
        add("warning", "post-future",
            f"Dated {cal_date}: future-dated posts are not built until a later deploy.",
            loc.post_line("date"))

    # -- rid ------------------------------------------------------------------
    rid = meta.get("rid")
    rid_ok = isinstance(rid, int) and not isinstance(rid, bool) and rid > 0
    if "rid" not in meta:
        add("error", "post-rid", "Missing `rid`.", 1, "rid")
    elif not rid_ok:
        add("error", "post-rid", f"`rid` must be a positive integer, got {rid!r}.", loc.post_line("rid"), "rid")

    # -- filename ----------------------------------------------------------------
    if cal_date is not None and rid_ok:
        p = Path(path)
        expected = f"{cal_date.isoformat()}-{rid}.md"
        if p.name != expected or p.parent.name != str(cal_date.year):
            add("error", "post-filename",
                f"File should be `{POSTS_DIR}/{cal_date.year}/{expected}` (date-rid.md in the year folder).",
                1, "path")

    # -- uniqueness and ordering against the rest of the posts --------------------
    line_rid, line_date = loc.post_line("rid"), loc.post_line("date")
    if rid_ok:
        dup = [o for o in index.by_rid.get(rid, []) if o != path]
        if dup:
            add("error", "post-rid-unique", f"`rid` {rid} is already used by {dup[0]}.", line_rid, "rid")
        elif rid > 1 and not [o for o in index.by_rid.get(rid - 1, []) if o != path]:
            add("warning", "post-gap", f"No post has rid {rid - 1}; rids should be consecutive.", line_rid)
        if cal_date is not None:
            clash = next((o for o in index.posts if o.path != path and isinstance(o.rid, int) and o.cal_date and (
                (o.cal_date < cal_date and o.rid >= rid) or (o.cal_date > cal_date and o.rid <= rid))), None)
            if clash:
                add("warning", "post-order",
                    f"rid {rid} / date {cal_date} are out of order with {clash.path}.", line_rid)
    if cal_date is not None:
        same = [o for o in index.by_date.get(cal_date, []) if o != path]
        if same:
            add("error", "post-date-unique",
                f"Another post already has date {cal_date} ({same[0]}); permalinks would collide.",
                line_date, "date")

    # -- other post-level keys -------------------------------------------------------
    for key in ("author", "translator"):
        if key in meta and not (isinstance(meta[key], str) and meta[key].strip()):
            add("error", "post-key", f"`{key}` must be a non-empty text.", loc.post_line(key), key)

    # -- links ---------------------------------------------------------------------------
    if "rafagas" not in meta:
        add("error", "post-empty", "Missing `rafagas` list.", 1, "rafagas")
        return findings, meta
    if not isinstance(rafagas, list):
        add("error", "post-empty", "`rafagas` must be a list of links.", loc.post_line("rafagas"), "rafagas")
        return findings, meta
    if not rafagas:
        add("error", "post-empty", "`rafagas` is empty: the post has no links yet.", loc.post_line("rafagas"), "rafagas")
        return findings, meta

    seen: dict[str, int] = {}

    for i, entry in enumerate(rafagas):
        if not isinstance(entry, dict):
            add("error", "link-shape", f"Link #{i + 1} is not a mapping of keys.", loc.entry_line(i))
            continue
        eid = entry_id(entry)

        def err(code, message, key=None, level="error"):
            add(level, code, f"Link #{i + 1}: {message}", loc.entry_line(i, key), entry=eid)

        for key in entry:
            if key not in LINK_KEYS:
                err("link-key", f"unknown key `{key}` (typo?).", key, "warning")

        # link
        link = entry.get("link")
        if not isinstance(link, str) or not link.strip():
            err("link-url", "`link` is missing or empty.", "link")
        else:
            parsed = urlparse(link)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or re.search(r"\s", link):
                err("link-url", f"`link` is not a valid http(s) URL: {link!r}.", "link")
            norm = normalize_url(link)
            if norm in seen:
                err("link-dup", f"`link` repeats link #{seen[norm]} of this post.", "link")
            else:
                seen[norm] = i + 1
                before = [
                    other for d, other in index.by_link.get(norm, [])
                    if other != path and cal_date is not None and 0 < (cal_date - d).days <= REPUBLISHED_LOOKBACK_DAYS
                ]
                if before:
                    err("link-republished",
                        f"`link` was already published in {before[0]} (< {REPUBLISHED_LOOKBACK_DAYS} days earlier).",
                        "link", "warning")

        # desc
        desc = entry.get("desc")
        if not isinstance(desc, str) or not desc.strip():
            err("link-desc", "`desc` is missing or empty.", "desc")

        # keyw
        keyw = entry.get("keyw")
        if keyw is None or (isinstance(keyw, str) and not keyw.strip()):
            err("link-keyw", "`keyw` is empty.", "keyw")
        elif not isinstance(keyw, str):
            err("link-keyw", f"`keyw` must be text, got {keyw!r}.", "keyw")
        elif not KEYW_RE.match(keyw):
            err("link-keyw",
                f"`keyw` {keyw!r} must be lowercase letters/digits, hyphens allowed, no spaces.", "keyw")

        # lang
        if "lang" in entry:
            lang = entry["lang"]
            if not isinstance(lang, str) or not re.fullmatch(r"[A-Z]{2}", lang):
                err("link-lang", f"`lang` {lang!r} must be two uppercase letters (ISO 639-1, e.g. ES).", "lang")
            elif lang not in ISO_639_1:
                err("link-lang", f"`lang` {lang!r} is not an ISO 639-1 code.", "lang")
            elif lang == "EN":
                err("link-lang", "`lang: EN` is redundant, only use `lang` for non-English links.", "lang", "warning")

        # via
        if "via" in entry:
            via = entry["via"]
            if not isinstance(via, str) or not VIA_RE.match(via):
                err("link-via", f"`via` {via!r} must be a social handle starting with @ (use single quotes).", "via")

        # maintenance flags
        for flag in ("invalid", "nocheck"):
            if flag in entry and not isinstance(entry[flag], bool):
                err("link-flag", f"`{flag}` must be true or false, got {entry[flag]!r}.", flag)

    return findings, meta


def downgrade_inherited(findings: list[Finding], meta: dict | None, old_text: str | None) -> None:
    """Turn errors that were already in the base version of the post into warnings."""
    if old_text is None or meta is None:
        return
    try:
        old = frontmatter.loads(old_text)
    except Exception:
        return
    old_entries = old.get("rafagas")
    old_ids = {entry_id(e) for e in old_entries if isinstance(e, dict)} if isinstance(old_entries, list) else set()
    for f in findings:
        if f.level != "error":
            continue
        if f.entry is not None:
            inherited = f.entry in old_ids
        elif f.field is not None:
            inherited = f.field == "path" or old.metadata.get(f.field) == meta.get(f.field)
        else:
            inherited = False
        if inherited:
            f.level = "warning"
            f.message += " (already in the base version, not blocking)"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit(f: Finding) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{f.level} file={f.path},line={f.line},title={f.code}::{_escape(f.message)}")
    else:
        print(f"{f.path}:{f.line}: {f.level}: [{f.code}] {f.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Rafagas post files.")
    parser.add_argument("files", nargs="*", help="post files to validate (default: files changed vs the base branch)")
    parser.add_argument("--all", action="store_true", help="report on every post; never fails")
    parser.add_argument("--base", help="base ref to compare with (default: origin/gh-pages, then gh-pages)")
    parser.add_argument("--posts-dir", default=POSTS_DIR, help="posts folder (default: _posts)")
    parser.add_argument("-v", "--verbose", action="store_true", help="with --all, list every finding")
    args = parser.parse_args(argv)

    base = None
    if not args.all:
        base = resolve_base(args.base)
        if args.base and base is None:
            print(f"error: base ref {args.base!r} not found (fetch it, or use fetch-depth: 0 in CI).", file=sys.stderr)
            return 2

    # -- which files -------------------------------------------------------------------
    if args.all:
        targets = [p.as_posix() for p in sorted(Path(args.posts_dir).glob("**/*.md")) if not is_template(p)]
    elif args.files:
        targets = [repo_path(f) for f in args.files if not is_template(f)]
    elif base:
        targets = changed_files(base)
    else:
        print("error: no base branch found to detect changed posts; pass files or use --all.", file=sys.stderr)
        return 2

    targets = list(dict.fromkeys(targets))  # drop duplicates, keep order
    if not targets:
        print("No post files to validate.")
        return 0
    if not args.all and base is None:
        print("note: base branch not found, every problem is treated as blocking.", file=sys.stderr)

    index = build_index(args.posts_dir)
    today = dt.datetime.now(dt.timezone.utc).date()

    all_findings: list[Finding] = []
    for path in targets:
        p = Path(path)
        if not p.is_file():
            print(f"warning: {path} does not exist, skipped.", file=sys.stderr)
            continue
        findings, meta = validate_post(path, p.read_text(encoding="utf-8"), index, today)
        downgrade_inherited(findings, meta, base_text(base, path))
        all_findings.extend(sorted(findings, key=lambda f: f.line))

    errors = [f for f in all_findings if f.level == "error"]
    warnings = [f for f in all_findings if f.level == "warning"]

    # -- report ----------------------------------------------------------------------------
    if args.all and not args.verbose:
        counts = Counter((f.level, f.code) for f in all_findings)
        shown: dict = defaultdict(int)
        for f in all_findings:
            if shown[(f.level, f.code)] < 3:
                shown[(f.level, f.code)] += 1
                emit(f)
        print("\nFindings by rule (first 3 of each shown above, use -v for all):")
        for (level, code), n in sorted(counts.items()):
            print(f"  {n:6d}  {level:7s}  {code}")
    else:
        for f in all_findings:
            emit(f)

    print(f"\nChecked {len(targets)} post(s): {len(errors)} error(s), {len(warnings)} warning(s).")
    if args.all:
        return 0
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
