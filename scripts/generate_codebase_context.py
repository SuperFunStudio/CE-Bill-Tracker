"""Generate a portable codebase summary you can paste into a web/app Claude chat.

Reads the repo statically — no database, no network, no `import app` — so it runs in a
few seconds anywhere the source tree exists, with no env vars and no venv activation.
Everything except the hand-written PREAMBLE is derived from the tree, so the summary
can't quietly drift from the code the way a hand-maintained doc does.

    python scripts/generate_codebase_context.py                  # docs/CODEBASE_CONTEXT.md
    python scripts/generate_codebase_context.py --level brief    # smaller, for tight context
    python scripts/generate_codebase_context.py --level full     # everything
    python scripts/generate_codebase_context.py -o -             # stdout

Secrets: only *names* of settings are emitted. Values that look like credentials are
redacted (see _safe_default) and .env is never read.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# The part a generator can't infer. Edit this when the product's shape changes.
# ---------------------------------------------------------------------------

PREAMBLE = """\
**Atlas Circular** (repo/dirs still say `SignalScout` / `ce-bill-tracker` — same product,
pre-rename) is a jurisdiction-aware research atlas for circular-economy law: EPR, packaging,
right-to-repair, recycled content, disposal bans, procurement enablers, and adjacent
transboundary-waste rules. It ingests legislation from ~40 regions (US states + federal, EU,
and national adapters for JP/FR/GB/IN/IT/NO/TR/KE and more), classifies each measure with
Claude along several axes (instrument type, material, friction, management model), extracts
structured compliance dimensions, and serves it as a browsable corpus plus an LLM research
surface ("Ask the Atlas") that answers questions with citations back to specific bills.

Stack: **FastAPI + SQLAlchemy 2.0 (typed `Mapped`) + Postgres + Alembic** on the backend,
**Next.js (App Router, static export) + Tailwind** in `dashboard-next/`, Anthropic API for
classification/extraction/synthesis, APScheduler for recurring ingest, SendGrid for email,
Stripe for billing, Firebase Auth for identity.

Hosting is **Google Cloud**, project `ce-bill-tracker`: Cloud Run for the API, Cloud Run Jobs
for the pipeline, Cloud SQL Postgres, Firebase Hosting for the dashboard.

**Deploys are manual and local.** There is no GitHub Actions workflow and no Cloud Build
GitHub trigger — nothing ships on push. `gcloud builds submit` uploads the **working tree**
(minus `.gcloudignore`), not a git commit.

- Prod: `gcloud builds submit --config=cloudbuild.yaml --project=ce-bill-tracker`
  (wrapped by `scripts/deploy-prod.ps1`, which guards clean tree / on `main` / synced with
  `origin/main`, so what's live equals a committed `main` commit).
- Dev: same with `--config=cloudbuild.dev.yaml` — no guard; dev is deliberately the
  working-tree lane (separate DB `signalscout_dev`, service `signalscout-api-dev`,
  Firebase site `ce-bill-tracker-dev`).

Consequence worth holding onto when advising: a remote/cloud agent sees only what's been
**pushed to git**, while a deploy sees whatever is **on disk**. Those two views of "the code"
can differ, and only the prod deploy guard forces them to agree.
"""

DIR_NOTES = {
    "app": "FastAPI backend (all Python application code)",
    "app/api": "HTTP routers — one module per surface",
    "app/ingestion": "Source adapters: LegiScan, OpenStates, EUR-Lex, Federal Register, per-country foreign clients",
    "app/classification": "Claude-backed classifiers + keyword gates that decide scope and axes",
    "app/synthesis": "LLM synthesis (design principles, briefings) over classified bills",
    "app/research": "Ask-the-Atlas retrieval, facet routing, session/turn persistence",
    "app/scheduler": "APScheduler job definitions for recurring ingest/refresh",
    "app/alerts": "Email alerting, digests, subscriber notification triggers",
    "app/scoring": "Company impact scoring (gated, pre-launch)",
    "app/company_intel": "Company entity resolution + exposure briefs",
    "app/links": "Source-link health classification and repair",
    "app/geo": "Jurisdiction tree + region/state normalization",
    "app/evaluation": "Bill strength / fit-score evaluator",
    "app/utils": "Shared helpers",
    "alembic": "Database migrations (single linear history)",
    "dashboard-next": "Next.js App Router frontend (static export -> Firebase Hosting)",
    "dashboard": "Legacy dashboard — superseded by dashboard-next",
    "scripts": "One-off + operational scripts (backfills, audits, ingest runs, deploys)",
    "tests": "pytest suite",
    "docs": "Design specs, roadmaps, plans, assessments",
    "data": "Seed data and exports (data/seed IS shipped into the image)",
    "hackathon": "Hackathon prototypes",
}

SECRETY = re.compile(r"(key|secret|token|password|passwd|credential|dsn|_oc$|webhook)", re.I)
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", ".next", "out",
    ".pytest_cache", "tmp", ".mypy_cache", ".ruff_cache",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def git(*args: str) -> str:
    """Run git and return stdout with trailing newlines removed.

    Deliberately not `.strip()`ed: `status --porcelain` encodes status in the first two
    columns, so stripping would shift the first line's path by one character. Git speaks
    UTF-8 regardless of the Windows console codepage, so decode explicitly.
    """
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
        return out.stdout.rstrip("\n")
    except OSError:
        return ""


def parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return None


def first_doc_line(node) -> str:
    doc = ast.get_docstring(node) or ""
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def literal(node) -> str | None:
    """Best-effort source text for a node, or None if it isn't a simple literal."""
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _safe_default(name: str, node) -> str:
    """Render a settings default without leaking anything credential-shaped."""
    if node is None:
        return ""
    try:
        value = ast.literal_eval(node)
    except Exception:
        return "<computed>"
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return repr(value)
    if isinstance(value, str):
        if value == "":
            return '""'
        if SECRETY.search(name) or "://" in value or len(value) > 48:
            return "<redacted>"
        return repr(value)
    return "<...>"


def rel(path: Path) -> str:
    """Repo-relative posix path, falling back to the absolute path for outside targets."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------

def extract_routes() -> list[dict]:
    """Router modules -> prefix, tags, and every decorated endpoint."""
    modules = []
    for path in sorted((REPO / "app" / "api").glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = parse(path)
        if tree is None:
            continue

        # var name -> (prefix, tags); a module may declare several routers.
        routers: dict[str, tuple[str, str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if not (isinstance(func, ast.Name) and func.id == "APIRouter"):
                continue
            prefix, tags = "", ""
            for kw in node.value.keywords:
                if kw.arg == "prefix":
                    prefix = (literal(kw.value) or "").strip("'\"")
                elif kw.arg == "tags":
                    tags = (literal(kw.value) or "").strip("[]")
            for target in node.targets:
                if isinstance(target, ast.Name):
                    routers[target.id] = (prefix, tags)

        if not routers:
            continue

        endpoints = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                owner = dec.func.value
                if not (isinstance(owner, ast.Name) and owner.id in routers):
                    continue
                method = dec.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue
                sub = (literal(dec.args[0]) if dec.args else "") or ""
                sub = sub.strip("'\"")
                prefix, _ = routers[owner.id]
                endpoints.append({
                    "method": method,
                    "path": (prefix + sub) or "/",
                    "func": node.name,
                    "doc": first_doc_line(node),
                    "line": node.lineno,
                })

        endpoints.sort(key=lambda e: (e["path"], e["method"]))
        modules.append({
            "file": rel(path),
            "routers": routers,
            "endpoints": endpoints,
        })
    return modules


def extract_models() -> list[dict]:
    tree = parse(REPO / "app" / "models.py")
    if tree is None:
        return []
    tables = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        tablename = None
        columns = []
        for stmt in node.body:
            # __tablename__ = "..."
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == "__tablename__":
                        tablename = (literal(stmt.value) or "").strip("'\"")
            # id: Mapped[int] = mapped_column(...)
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                ann = literal(stmt.annotation) or ""
                if not ann.startswith("Mapped["):
                    continue
                kind = "relationship" if (
                    isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Name)
                    and stmt.value.func.id == "relationship"
                ) else "column"
                columns.append({
                    "name": stmt.target.id,
                    "type": ann[len("Mapped["):-1],
                    "kind": kind,
                })
        if tablename:
            tables.append({
                "class": node.name,
                "table": tablename,
                "doc": first_doc_line(node),
                "columns": columns,
                "line": node.lineno,
            })
    return tables


def extract_migrations() -> dict:
    versions = REPO / "alembic" / "versions"
    revs: dict[str, dict] = {}
    downs: set[str] = set()
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rev = re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision(?::[^=]+)?\s*=\s*['\"]([^'\"]+)", text, re.M)
        if not rev:
            continue
        tree = parse(path)
        revs[rev.group(1)] = {
            "file": path.name,
            "down": down.group(1) if down else None,
            "doc": first_doc_line(tree) if tree else "",
        }
        if down:
            downs.add(down.group(1))
    heads = [r for r in revs if r not in downs]

    # Walk back from head so migrations are listed in true apply order.
    ordered = []
    if len(heads) == 1:
        cur = heads[0]
        seen = set()
        while cur and cur in revs and cur not in seen:
            seen.add(cur)
            ordered.append((cur, revs[cur]))
            cur = revs[cur]["down"]
        ordered.reverse()
    return {"heads": heads, "count": len(revs), "ordered": ordered}


def extract_jobs() -> list[dict]:
    path = REPO / "app" / "scheduler" / "jobs.py"
    tree = parse(path)
    if tree is None:
        return []
    jobs = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_job":
            continue
        func = literal(node.args[0]) if node.args else "?"
        trigger = (literal(node.args[1]) if len(node.args) > 1 else "") or ""
        schedule, job_id, name = [], "", ""
        for kw in node.keywords:
            val = literal(kw.value) or "?"
            if kw.arg == "id":
                job_id = val.strip("'\"")
            elif kw.arg == "name":
                name = val.strip("'\"")
            elif kw.arg not in {"replace_existing", "misfire_grace_time", "max_instances"}:
                schedule.append(f"{kw.arg}={val}")
        jobs.append({
            "id": job_id or func,
            "func": func,
            "trigger": trigger.strip("'\""),
            "schedule": ", ".join(schedule),
            "name": name,
            "line": node.lineno,
        })
    return jobs


def extract_settings() -> list[dict]:
    tree = parse(REPO / "app" / "config.py")
    if tree is None:
        return []
    fields = []
    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name == "Settings"):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                if name.startswith("_") or name == "model_config":
                    continue
                fields.append({
                    "name": name,
                    "type": literal(stmt.annotation) or "",
                    "default": _safe_default(name, stmt.value),
                })
    return fields


def extract_frontend_routes() -> list[dict]:
    root = REPO / "dashboard-next" / "src" / "app"
    if not root.exists():
        return []
    routes = []
    for path in sorted(root.rglob("page.tsx")):
        segs = path.relative_to(root).parts[:-1]
        # Route groups like (marketing) don't appear in the URL.
        url = "/" + "/".join(s for s in segs if not s.startswith("("))
        routes.append({"route": url.rstrip("/") or "/", "file": rel(path)})
    return routes


def extract_scripts() -> list[dict]:
    out = []
    for path in sorted((REPO / "scripts").glob("*.py")):
        tree = parse(path)
        out.append({
            "name": path.name,
            "doc": first_doc_line(tree) if tree else "",
        })
    return out


def extract_docs() -> list[dict]:
    root = REPO / "docs"
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob("*.md")):
        title = ""
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("#"):
                    title = line.lstrip("# ").strip()
                    break
        except OSError:
            pass
        out.append({"file": rel(path), "title": title})
    return out


def extract_tree(max_depth: int = 2) -> list[str]:
    lines = []

    def walk(directory: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(
                p for p in directory.iterdir()
                if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")
            )
        except OSError:
            return
        for entry in entries:
            key = rel(entry)
            note = DIR_NOTES.get(key, "")
            py = len(list(entry.glob("*.py")))
            ts = len(list(entry.glob("*.ts*")))
            counts = []
            if py:
                counts.append(f"{py} py")
            if ts:
                counts.append(f"{ts} ts")
            meta = f"  ({', '.join(counts)})" if counts else ""
            lines.append(f"{prefix}{entry.name}/{meta}{'  — ' + note if note else ''}")
            walk(entry, depth + 1, prefix + "  ")

    walk(REPO, 1, "")
    return lines


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def build(level: str) -> str:
    brief = level == "brief"
    full = level == "full"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip() or "?"
    head = git("log", "-1", "--format=%h %ad %s", "--date=short").strip() or "?"
    remote = git("config", "--get", "remote.origin.url").strip() or "(no remote)"
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if ln.strip()]
    ahead = git("rev-list", "--count", "@{u}..HEAD").strip() or "?"

    routes = extract_routes()
    models = extract_models()
    migrations = extract_migrations()
    jobs = extract_jobs()
    settings = extract_settings()
    fe = extract_frontend_routes()
    scripts = extract_scripts()
    docs = extract_docs()

    L: list[str] = []
    w = L.append

    w("# Atlas Circular — Codebase Context")
    w("")
    w(f"_Generated {now} by `scripts/generate_codebase_context.py` (level: {level}). "
      "Regenerate rather than hand-editing — every section below the preamble is derived "
      "from the source tree._")
    w("")
    w("## What this is")
    w("")
    w(PREAMBLE)
    w("")

    w("## Repo state at generation time")
    w("")
    w(f"- Remote: `{remote}`")
    w(f"- Branch: `{branch}` — HEAD `{head}`")
    w(f"- Uncommitted files: **{len(dirty)}**"
      + (f" ({', '.join(ln[2:].strip() for ln in dirty[:8])}{'…' if len(dirty) > 8 else ''})" if dirty else ""))
    w(f"- Unpushed commits on this branch: **{ahead}**")
    w(f"- Alembic head: **{', '.join(migrations['heads']) or '?'}** "
      f"({migrations['count']} migrations)")
    w(f"- Size: {len(models)} tables · "
      f"{sum(len(m['endpoints']) for m in routes)} API endpoints · "
      f"{len(fe)} frontend routes · {len(jobs)} scheduled jobs · {len(scripts)} scripts")
    if dirty or (ahead not in {"0", "?"}):
        w("")
        w("> Note: the working tree is **not** clean/synced, so this summary describes code "
          "that a remote agent cloning `origin` would not see.")
    w("")

    w("## Recent commits")
    w("")
    w("```")
    w(git("log", "-15", "--format=%h %ad  %s", "--date=short"))
    w("```")
    w("")

    w("## Directory map")
    w("")
    w("```")
    for line in extract_tree(max_depth=2 if not brief else 1):
        w(line)
    w("```")
    w("")

    # ---- API ----
    w("## Backend API surface")
    w("")
    w("FastAPI app: `app/main.py`. Routers live in `app/api/` and are registered there.")
    w("")
    for mod in routes:
        prefixes = ", ".join(sorted({f"`{p}`" for p, _ in mod["routers"].values() if p})) or "`/`"
        w(f"### {mod['file']} — {prefixes}")
        w("")
        if brief:
            w(f"{len(mod['endpoints'])} endpoints: "
              + ", ".join(f"`{e['method']} {e['path']}`" for e in mod["endpoints"][:6])
              + ("…" if len(mod["endpoints"]) > 6 else ""))
            w("")
            continue
        w("| Method | Path | Handler | Notes |")
        w("| --- | --- | --- | --- |")
        for e in mod["endpoints"]:
            note = e["doc"].replace("|", "\\|")[:110] if not brief else ""
            w(f"| {e['method']} | `{e['path']}` | `{e['func']}` | {note} |")
        w("")

    # ---- data model ----
    w("## Data model")
    w("")
    w(f"SQLAlchemy 2.0 typed models in `app/models.py` ({len(models)} tables). "
      "Migrations are a single linear Alembic history in `alembic/versions/`.")
    w("")
    if brief:
        w(", ".join(f"`{m['table']}`" for m in models))
        w("")
    else:
        for m in models:
            w(f"### `{m['table']}` — `{m['class']}` "
              f"([app/models.py:{m['line']}](app/models.py#L{m['line']}))")
            if m["doc"]:
                w("")
                w(m["doc"])
            w("")
            cols = [c for c in m["columns"] if c["kind"] == "column"]
            rels = [c for c in m["columns"] if c["kind"] == "relationship"]
            if full:
                for c in cols:
                    w(f"- `{c['name']}`: {c['type']}")
            else:
                w("Columns: " + ", ".join(f"`{c['name']}`" for c in cols))
            if rels:
                w("")
                w("Relationships: " + ", ".join(f"`{c['name']}`" for c in rels))
            w("")

    # ---- migrations ----
    w("## Migration history")
    w("")
    if migrations["ordered"]:
        recent = migrations["ordered"] if full else migrations["ordered"][-15:]
        if not full and len(migrations["ordered"]) > len(recent):
            w(f"_Most recent {len(recent)} of {migrations['count']}; "
              "run with `--level full` for all._")
            w("")
        for rev, info in recent:
            w(f"- `{rev}` — {info['doc'] or info['file']}")
    else:
        w(f"{migrations['count']} migrations; heads: {migrations['heads']} "
          "(non-linear or unparsed — inspect `alembic/versions/`).")
    w("")

    # ---- scheduler ----
    w("## Scheduled jobs")
    w("")
    w("Defined in `app/scheduler/jobs.py` (APScheduler, started by the API process). "
      "Some are conditional on settings flags — check the source for the gates.")
    w("")
    w("| Job | Trigger | Schedule | Function |")
    w("| --- | --- | --- | --- |")
    for j in jobs:
        w(f"| {j['id']} | {j['trigger']} | {j['schedule']} | `{j['func']}` |")
    w("")

    # ---- frontend ----
    w("## Frontend routes")
    w("")
    w("Next.js App Router in `dashboard-next/src/app`, built as a **static export** and "
      "deployed to Firebase Hosting. Shared UI in `src/components`, hooks in `src/hooks`, "
      "chart primitives + API client in `src/lib`.")
    w("")
    for r in fe:
        w(f"- `{r['route']}` — [{r['file']}]({r['file']})")
    w("")

    # ---- config ----
    w("## Configuration surface")
    w("")
    w("`app/config.py` (`pydantic-settings`), read from env / Secret Manager. "
      "**Names and non-secret defaults only — no values are read from `.env`.**")
    w("")
    w("| Setting | Type | Default |")
    w("| --- | --- | --- |")
    for s in settings:
        w(f"| `{s['name']}` | `{s['type']}` | `{s['default']}` |")
    w("")

    # ---- scripts ----
    if not brief:
        w("## Operational scripts")
        w("")
        w(f"`scripts/` ({len(scripts)} files). Most take a `--prod-dsn`/`--dsn` and default "
          "to dry-run; read the docstring before running anything against prod.")
        w("")
        for s in scripts:
            w(f"- `{s['name']}`" + (f" — {s['doc']}" if s["doc"] else ""))
        w("")

    # ---- docs ----
    w("## Design docs")
    w("")
    w("Longer-form plans and specs live in `docs/`:")
    w("")
    for d in docs:
        w(f"- [{d['file']}]({d['file']})" + (f" — {d['title']}" if d["title"] else ""))
    w("")

    w("## Conventions worth knowing")
    w("")
    w("- Bills carry `region` (2-char family: `US`, `EU`, `JP`…) plus `state` "
      "(sub-jurisdiction, namespaced for federations: `CA-BC`, `AU-NSW`). "
      "`jurisdiction_id` is the normalized tree that supersedes the flat pair.")
    w("- Non-US bills key on `celex_id`/`foreign_id`; US bills key on `openstates_id`. "
      "That's what makes dev→prod mirroring of foreign rows collision-free.")
    w("- Foreign law is enacted-only, so only enacted counts are comparable across borders.")
    w("- Classification changes are audit-logged to `classification_changes` with a `run_id` "
      "— reclassification scripts must write there so flips can be undone.")
    w("- `compliance_details` is a JSONB envelope carrying extracted dimensions "
      "(fees, eco-modulation, targets, penalties, lifecycle) with `source_excerpt` provenance.")
    w("")

    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", choices=["brief", "standard", "full"], default="standard",
                    help="how much detail to emit (default: standard)")
    ap.add_argument("-o", "--out", default="docs/CODEBASE_CONTEXT.md",
                    help="output path, or '-' for stdout")
    args = ap.parse_args()

    text = build(args.level)

    if args.out == "-":
        # The Windows console defaults to cp1252, which can't encode the arrows/em-dashes
        # that appear in commit subjects and docstrings.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        sys.stdout.write(text)
        return 0

    out = (REPO / args.out) if not os.path.isabs(args.out) else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    chars = len(text)
    print(f"Wrote {rel(out)}")
    # ASCII separators: the Windows console codepage mangles non-ASCII on print.
    print(f"  {chars:,} chars | ~{chars // 4:,} tokens | {text.count(chr(10)):,} lines")
    if chars // 4 > 100_000:
        print("  (large — consider --level brief for pasting into a chat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
