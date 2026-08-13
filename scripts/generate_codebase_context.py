"""Generate a portable codebase summary you can paste into a web/app Claude chat.

Reads the repo statically — no database, no network, no `import app` — so it runs in a
few seconds anywhere the source tree exists, with no env vars and no venv activation.
Everything except the hand-written PREAMBLE is derived from the tree, so the summary
can't quietly drift from the code the way a hand-maintained doc does.

    python scripts/generate_codebase_context.py                  # docs/CODEBASE_CONTEXT.md
    python scripts/generate_codebase_context.py --level brief    # smaller, for tight context
    python scripts/generate_codebase_context.py --level full     # everything
    python scripts/generate_codebase_context.py -o -             # stdout
    python scripts/generate_codebase_context.py --diff           # just what changed

Two things aren't derivable and live outside this file: `docs/FOCUS.md` (what's actively
being worked — the generator only stamps its age and flags it stale) and `CLUSTERS` below
(which pages and routers serve the same user-facing job).

A normal run rewrites `docs/codebase_context.snapshot.json`, the baseline the diff compares
against — so commit it, and use `--diff`/`--no-snapshot` when you want to look without
consuming the baseline.

Secrets: only *names* of settings are emitted. Values that look like credentials are
redacted (see _safe_default) and .env is never read.
"""

from __future__ import annotations

import argparse
import ast
import json
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
classification/extraction/synthesis, APScheduler for recurring ingest, SendGrid for email
(with a Postmark transport wired behind `EMAIL_PROVIDER` — both are implemented, callers gate on
`settings.email_configured` and never name one), Stripe for billing, Firebase Auth for identity.

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

# ---------------------------------------------------------------------------
# Capability clusters. The *grouping* is hand-declared (nothing in the tree says which
# page and which router serve the same user-facing job); the *contents* are derived, so a
# new page or router shows up on its own — under a cluster if it matches, otherwise in the
# "Unclustered" bucket at the end, which is the signal to edit this table.
#
#   routes: frontend paths — exact match, or a `/x/*` prefix
#   tags:   APIRouter tags, i.e. which backend routers serve this capability
# ---------------------------------------------------------------------------
CLUSTERS: list[dict] = [
    {
        "name": "Corpus browse & filter",
        "blurb": "The atlas itself: the bill corpus, per-bill pages, jurisdiction and "
                 "state profiles, and the embeddable/anonymous slices.",
        "routes": ["/", "/bill/*", "/jurisdictions/*", "/states", "/states/*", "/library",
                   "/embed"],
        "tags": ["bills", "scope"],
    },
    {
        "name": "Ask the Atlas (research)",
        "blurb": "LLM research surface — cited answers over the corpus, persisted research "
                 "sessions, shared `/r/` links and published `/p/` pages.",
        "routes": ["/ask", "/r", "/p"],
        "tags": ["research"],
    },
    {
        "name": "Compliance pathways",
        "blurb": "What a given obligation actually requires: deadlines, structured "
                 "compliance dimensions, and how-to-comply links.",
        "routes": ["/compliance"],
        "tags": ["compliance"],
    },
    {
        "name": "Company exposure & bill evaluation",
        "blurb": "Producer attribution — which companies a measure reaches — plus the "
                 "fit-score evaluator for a single bill.",
        "routes": ["/company", "/evaluate"],
        "tags": ["companies", "evaluate"],
    },
    {
        "name": "Federal actions & litigation",
        "blurb": "US federal regulatory actions and tracked litigation, alongside the "
                 "legislative corpus.",
        "routes": ["/federal"],
        "tags": ["federal", "litigation"],
    },
    {
        "name": "Insights & analytics",
        "blurb": "Momentum, heatmaps, passage-rate baselines and real-world outcomes.",
        "routes": ["/insights"],
        "tags": ["insights"],
    },
    {
        "name": "Design guide & packaging studio",
        "blurb": "Design-for-EPR principles, the packaging reference catalog, material "
                 "swatches and labeling.",
        "routes": ["/design-guide", "/studio", "/label"],
        "tags": ["design-guide"],
    },
    {
        "name": "Watchlist & alerts",
        "blurb": "Per-user tracking with new-bill, deadline and digest email triggers.",
        "routes": ["/watchlist"],
        "tags": ["alerts"],
    },
    {
        "name": "Accounts, billing & access",
        "blurb": "Identity, entitlements and plan resolution, Stripe checkout and "
                 "webhooks, referrals, beta access requests.",
        "routes": ["/account", "/pricing", "/beta"],
        "tags": ["auth", "me", "billing", "webhooks", "referrals", "access"],
    },
    {
        "name": "Admin & pipeline ops",
        "blurb": "Internal only: corpus review queues, the research log, and manual "
                 "triggers for the ingest/classify pipeline.",
        "routes": ["/admin", "/admin/*"],
        "tags": ["admin", "pipeline"],
    },
    {
        "name": "Static & marketing",
        "blurb": "Content pages with no backing API surface of their own.",
        "routes": ["/about", "/faq", "/methodology", "/privacy", "/terms", "/developers"],
        "tags": [],
    },
]

# Gate spelling -> how to describe it in the capability table.
GATE_LABELS = {
    "require_admin": "admin",
    "require_pro": "Pro",
    "require_user": "signed in",
    "require_verified": "verified email",
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

def _gates(node) -> list[str]:
    """Auth gates named inside `Depends(...)` anywhere under `node`.

    Covers both spellings the codebase uses: a router-level
    `dependencies=[Depends(require_admin)]` and a per-handler
    `_user: AuthedUser = Depends(require_capability(CAP_ASK))`. Returns the gate as written
    (`require_admin`, `require_capability(CAP_ASK)`) so the caller can map it to a plan.
    """
    found: list[str] = []
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)):
            continue
        if sub.func.id != "Depends" or not sub.args:
            continue
        text = literal(sub.args[0]) or ""
        if text.startswith("require_") and text not in found:
            found.append(text)
    return found


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
        router_gates: dict[str, list[str]] = {}
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
            gates = _gates(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    routers[target.id] = (prefix, tags)
                    router_gates[target.id] = gates

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
                prefix, tags = routers[owner.id]
                # Signature-level gates only — walking the body would pick up unrelated
                # Depends() calls made inside the handler.
                gates = _gates(node.args) + [
                    g for g in router_gates.get(owner.id, []) if g not in _gates(node.args)
                ]
                endpoints.append({
                    "method": method,
                    "path": (prefix + sub) or "/",
                    "func": node.name,
                    "doc": first_doc_line(node),
                    "line": node.lineno,
                    "tags": tags.strip("'\""),
                    "gates": gates,
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


def extract_capability_model() -> dict:
    """The membership capability model in `app/api/auth.py`: CAP_* consts and PLAN_CAPS.

    Resolves the set algebra (`_CAPS_RESEARCH = _CAPS_STUDENT | {...}`) so each capability
    can report the cheapest plan that carries it. Returns {} if auth.py stops looking like
    this, rather than guessing.
    """
    path = REPO / "app" / "api" / "auth.py"
    tree = parse(path)
    if tree is None:
        return {}

    # CAP_ASK = "ask"  # Ask the Atlas (research Q&A)  <- the comment is the human label,
    # and comments aren't in the AST, so read those off the source text.
    labels: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^CAP_\w+\s*=\s*['\"]([^'\"]+)['\"]\s*(?:#\s*(.*))?$", line)
        if m:
            labels[m.group(1)] = (m.group(2) or "").strip()

    consts: dict[str, str] = {}          # CAP_ASK -> "ask"
    sets: dict[str, set[str]] = {}       # _CAPS_PRO -> {"ask", ...}
    plans: dict[str, set[str]] = {}

    def resolve(node) -> set[str] | None:
        """Evaluate a capability-set expression: names, {…}, a | b, frozenset(x)."""
        if isinstance(node, ast.Name):
            if node.id in sets:
                return set(sets[node.id])
            if node.id in consts:
                return {consts[node.id]}
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Set):
            out: set[str] = set()
            for elt in node.elts:
                part = resolve(elt)
                if part is None:
                    return None
                out |= part
            return out
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left, right = resolve(node.left), resolve(node.right)
            return None if left is None or right is None else left | right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in {"frozenset", "set"}:
            return resolve(node.args[0]) if node.args else set()
        return None

    for node in tree.body:
        if isinstance(node, ast.Assign):
            target = node.targets[0] if len(node.targets) == 1 else None
            name = target.id if isinstance(target, ast.Name) else None
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        else:
            continue
        if not name or node.value is None:
            continue

        if name.startswith("CAP_") and isinstance(node.value, ast.Constant):
            consts[name] = str(node.value.value)
        elif name.startswith("_CAPS_"):
            got = resolve(node.value)
            if got is not None:
                sets[name] = got
        elif name == "PLAN_CAPS" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    got = resolve(v)
                    if got is not None:
                        plans[k.value] = got

    if not consts or not plans:
        return {}

    # Plans in the order they're declared = cheapest first, so "first plan carrying X" is
    # the entry price for X.
    order = list(plans)
    caps = []
    for cap in consts.values():
        carriers = [p for p in order if cap in plans[p]]
        caps.append({
            "cap": cap,
            "label": labels.get(cap, ""),
            "plans": carriers,
            "entry": carriers[0] if carriers else "—",
        })
    return {"caps": caps, "plans": plans, "order": order}


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


def _route_matches(route: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if pat.endswith("/*"):
            if route.startswith(pat[:-1]):
                return True
        elif route == pat:
            return True
    return False


def _gate_label(gate: str, caps_by_name: dict[str, dict]) -> str:
    """Render one gate as a plan requirement: require_capability(CAP_ASK) -> "ask (student+)"."""
    m = re.match(r"require_capability\(\s*CAP_(\w+)\s*\)", gate)
    if m:
        cap = m.group(1).lower()
        info = caps_by_name.get(cap)
        return f"{cap} ({info['entry']}+)" if info else cap
    return GATE_LABELS.get(gate, gate)


def build_capabilities(routes: list[dict], fe: list[dict], capmodel: dict) -> list[dict]:
    """Join frontend routes + backend endpoints into user-facing capability clusters.

    Everything that matches no cluster lands in a trailing "Unclustered" entry — a missing
    capability should be visible as a gap, not vanish.
    """
    caps_by_name = {c["cap"]: c for c in capmodel.get("caps", [])}
    endpoints = [
        {**e, "file": mod["file"]}
        for mod in routes for e in mod["endpoints"]
    ]

    claimed_routes: set[str] = set()
    claimed_tags: set[str] = set()
    out = []
    for cluster in CLUSTERS:
        pages = [f["route"] for f in fe if _route_matches(f["route"], cluster["routes"])]
        claimed_routes.update(pages)
        claimed_tags.update(cluster["tags"])
        eps = [e for e in endpoints if e["tags"] in cluster["tags"]]

        gates: list[str] = []
        for e in eps:
            for g in e["gates"]:
                label = _gate_label(g, caps_by_name)
                if label not in gates:
                    gates.append(label)
        open_eps = sum(1 for e in eps if not e["gates"])
        out.append({
            "name": cluster["name"],
            "blurb": cluster["blurb"],
            "pages": sorted(pages),
            "endpoints": eps,
            "gates": gates,
            "open": open_eps,
        })

    stray_pages = sorted(f["route"] for f in fe if f["route"] not in claimed_routes)
    stray_eps = [e for e in endpoints if e["tags"] not in claimed_tags]
    if stray_pages or stray_eps:
        out.append({
            "name": "Unclustered",
            "blurb": "Not claimed by any cluster above — add them to `CLUSTERS` in "
                     "`scripts/generate_codebase_context.py`.",
            "pages": stray_pages,
            "endpoints": stray_eps,
            "gates": [],
            "open": sum(1 for e in stray_eps if not e["gates"]),
        })
    return out


# ---------------------------------------------------------------------------
# focus
# ---------------------------------------------------------------------------

FOCUS_FILE = "docs/FOCUS.md"
FOCUS_STALE_DAYS = 21


def extract_focus() -> dict:
    """The hand-written `docs/FOCUS.md`, plus derived evidence of what's actually moving.

    The prose can't be derived — nothing in the tree says which of 107 endpoints matters
    this week. So it's hand-written, and the generator's job is to keep it *honest*: it
    stamps the file's git age and flags it as stale, and prints the directories git says
    have actually changed lately, so a reader can see prose and reality side by side.
    """
    path = REPO / FOCUS_FILE
    text = ""
    if path.exists():
        raw = path.read_text(encoding="utf-8", errors="replace")
        # HTML comments hold the how-to-edit note for whoever opens FOCUS.md; they're not
        # for the reader of the generated doc.
        raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
        # Drop a leading H1 so the block nests under our own heading.
        lines = [ln for ln in raw.splitlines() if not ln.startswith("# ")]
        text = "\n".join(lines).strip()

    age_days, edited = None, ""
    stamp = git("log", "-1", "--format=%ad|%ar", "--date=short", "--", FOCUS_FILE).strip()
    if "|" in stamp:
        edited, rel_age = stamp.split("|", 1)
        edited = f"{edited} ({rel_age})"
        m = re.match(r"(\d+)\s+(day|week|month|year)", rel_age)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            age_days = n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]

    # Which directories git says are actually moving, independent of what the prose claims.
    hot: dict[str, int] = {}
    for line in git("log", "--since=21.days", "--name-only", "--format=").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("/")
        key = "/".join(parts[:3]) if line.startswith("dashboard-next/") else "/".join(parts[:2])
        key = key if "/" in key else parts[0]
        hot[key] = hot.get(key, 0) + 1
    top = sorted(hot.items(), key=lambda kv: (-kv[1], kv[0]))[:8]

    return {
        "text": text,
        "edited": edited,
        "age_days": age_days,
        "stale": age_days is not None and age_days > FOCUS_STALE_DAYS,
        "missing": not text,
        "hot": top,
        "recent_subjects": [
            ln for ln in git("log", "-8", "--since=21.days", "--format=%s").splitlines() if ln
        ],
    }


# ---------------------------------------------------------------------------
# snapshot + diff
# ---------------------------------------------------------------------------

SNAPSHOT_FILE = "docs/codebase_context.snapshot.json"


def build_snapshot(routes, models, fe, jobs, settings, migrations) -> dict:
    """The structural facts, flattened to comparable keys.

    Level-independent on purpose: `--level brief` must not look like half the API was
    deleted. Only things whose *change* is worth a line in the diff go in here.
    """
    endpoints = {}
    for mod in routes:
        for e in mod["endpoints"]:
            endpoints[f"{e['method']} {e['path']}"] = {
                "func": e["func"],
                "file": mod["file"],
                "gates": sorted(e["gates"]),
            }
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "head": git("rev-parse", "--short", "HEAD").strip(),
        "endpoints": endpoints,
        "tables": {
            m["table"]: sorted(c["name"] for c in m["columns"] if c["kind"] == "column")
            for m in models
        },
        "frontend": sorted(r["route"] for r in fe),
        "jobs": {j["id"]: f"{j['trigger']} {j['schedule']}" for j in jobs},
        "settings": {s["name"]: s["default"] for s in settings},
        "migration_head": ", ".join(migrations["heads"]),
        "migrations": migrations["count"],
    }


def load_snapshot() -> dict | None:
    path = REPO / SNAPSHOT_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def diff_snapshots(old: dict | None, new: dict) -> dict:
    """What changed between two snapshots, as lists of human-readable lines."""
    if not old:
        return {}
    out: dict[str, list[str]] = {}

    def add(section: str, lines: list[str]) -> None:
        if lines:
            out[section] = lines

    o_eps, n_eps = old.get("endpoints", {}), new["endpoints"]
    add("New endpoints", [
        f"`{k}` — `{n_eps[k]['func']}` in {n_eps[k]['file']}"
        + (f" (gated: {', '.join(n_eps[k]['gates'])})" if n_eps[k]["gates"] else "")
        for k in sorted(set(n_eps) - set(o_eps))
    ])
    add("Removed endpoints", [f"`{k}`" for k in sorted(set(o_eps) - set(n_eps))])
    add("Moved gates", [
        f"`{k}` — was {', '.join(o_eps[k]['gates']) or 'ungated'}"
        f" → now {', '.join(n_eps[k]['gates']) or 'ungated'}"
        for k in sorted(set(o_eps) & set(n_eps))
        if o_eps[k].get("gates", []) != n_eps[k]["gates"]
    ])

    o_tb, n_tb = old.get("tables", {}), new["tables"]
    add("New tables", [
        f"`{t}` ({len(n_tb[t])} columns)" for t in sorted(set(n_tb) - set(o_tb))
    ])
    add("Removed tables", [f"`{t}`" for t in sorted(set(o_tb) - set(n_tb))])
    col_changes = []
    for t in sorted(set(o_tb) & set(n_tb)):
        added = sorted(set(n_tb[t]) - set(o_tb[t]))
        dropped = sorted(set(o_tb[t]) - set(n_tb[t]))
        if added or dropped:
            bits = []
            if added:
                bits.append("+" + ", ".join(f"`{c}`" for c in added))
            if dropped:
                bits.append("-" + ", ".join(f"`{c}`" for c in dropped))
            col_changes.append(f"`{t}`: " + "; ".join(bits))
    add("Changed columns", col_changes)

    o_fe, n_fe = set(old.get("frontend", [])), set(new["frontend"])
    add("New pages", [f"`{r}`" for r in sorted(n_fe - o_fe)])
    add("Removed pages", [f"`{r}`" for r in sorted(o_fe - n_fe)])

    o_jb, n_jb = old.get("jobs", {}), new["jobs"]
    add("New jobs", [f"`{j}` ({n_jb[j]})" for j in sorted(set(n_jb) - set(o_jb))])
    add("Removed jobs", [f"`{j}`" for j in sorted(set(o_jb) - set(n_jb))])
    add("Rescheduled jobs", [
        f"`{j}` — was `{o_jb[j]}` → now `{n_jb[j]}`"
        for j in sorted(set(o_jb) & set(n_jb)) if o_jb[j] != n_jb[j]
    ])

    o_st, n_st = old.get("settings", {}), new["settings"]
    add("New settings", [f"`{s.upper()}` (default `{n_st[s]}`)" for s in sorted(set(n_st) - set(o_st))])
    add("Removed settings", [f"`{s.upper()}`" for s in sorted(set(o_st) - set(n_st))])
    add("Changed defaults", [
        f"`{s.upper()}` — was `{o_st[s]}` → now `{n_st[s]}`"
        for s in sorted(set(o_st) & set(n_st)) if o_st[s] != n_st[s]
    ])

    if old.get("migration_head") != new["migration_head"]:
        delta = new["migrations"] - old.get("migrations", 0)
        add("Migrations", [
            f"head `{old.get('migration_head') or '?'}` → `{new['migration_head']}` "
            f"({delta:+d} revision{'' if abs(delta) == 1 else 's'})"
        ])
    return out


def render_diff(old: dict | None, changes: dict, cap: int = 25) -> list[str]:
    L: list[str] = []
    w = L.append
    w("## Changed since last generation")
    w("")
    if not old:
        w(f"_No previous snapshot at `{SNAPSHOT_FILE}` — this run creates the baseline, so "
          "the next run can diff against it._")
        w("")
        return L
    w(f"_Baseline: snapshot taken {old.get('generated', '?')} at "
      f"`{old.get('head', '?')}`. Structural only — a rewritten function body with the "
      "same signature doesn't appear here._")
    w("")
    if not changes:
        w("Nothing structural changed.")
        w("")
        return L
    for section, lines in changes.items():
        w(f"**{section}**")
        w("")
        for line in lines[:cap]:
            w(f"- {line}")
        if len(lines) > cap:
            w(f"- _…and {len(lines) - cap} more_")
        w("")
    return L


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def build(level: str) -> tuple[str, dict]:
    """Render the document; also return the snapshot so the caller can persist it."""
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
    capmodel = extract_capability_model()
    capabilities = build_capabilities(routes, fe, capmodel)
    focus = extract_focus()
    snapshot = build_snapshot(routes, models, fe, jobs, settings, migrations)
    previous = load_snapshot()
    changes = diff_snapshots(previous, snapshot)

    L: list[str] = []
    w = L.append

    w("# Atlas Circular — Codebase Context")
    w("")
    w(f"_Generated {now} by `scripts/generate_codebase_context.py` (level: {level}). "
      "Regenerate rather than hand-editing — every section below the preamble is derived "
      "from the source tree._")
    w("")
    # ---- current focus ----
    # Deliberately first: the derived sections say what exists, not what matters, and a
    # pasted-in agent reads top-down.
    w("## Current focus")
    w("")
    if focus["missing"]:
        w(f"_No `{FOCUS_FILE}` in the repo — create it with three or four lines on what's "
          "actively being worked, and it will appear here._")
    else:
        w(focus["text"])
        w("")
        if focus["stale"]:
            w(f"> ⚠️ **Possibly stale** — `{FOCUS_FILE}` was last edited {focus['edited']}, "
              f"more than {FOCUS_STALE_DAYS} days ago. Treat the block above as history "
              "and trust the activity below.")
        else:
            w(f"_Source: [{FOCUS_FILE}]({FOCUS_FILE}), last edited {focus['edited'] or '(uncommitted)'}._")
    w("")
    if focus["hot"]:
        w("Where the commits have actually landed in the last 21 days — derived, so it "
          "corroborates or contradicts the block above:")
        w("")
        w(" · ".join(f"`{d}` ({n})" for d, n in focus["hot"]))
        w("")

    w("## What this is")
    w("")
    w(PREAMBLE)
    w("")

    # ---- capabilities ----
    w("## Capabilities")
    w("")
    w("What the product can do, grouped by user-facing job. Each cluster's pages and "
      "endpoints are derived from the tree; only the grouping is hand-declared "
      "(`CLUSTERS` in the generator), so anything new shows up either in a cluster or in "
      "**Unclustered** at the end.")
    w("")
    w("\"Gated by\" lists the auth dependencies the backend actually enforces — a "
      "capability name maps to the cheapest plan carrying it, per `PLAN_CAPS`. Endpoints "
      "with no gate are public.")
    w("")
    for cap in capabilities:
        w(f"### {cap['name']}")
        w("")
        w(cap["blurb"])
        w("")
        if cap["pages"]:
            w("- Pages: " + ", ".join(f"`{p}`" for p in cap["pages"]))
        if cap["endpoints"]:
            files = sorted({e["file"] for e in cap["endpoints"]})
            n = len(cap["endpoints"])
            w(f"- API: {n} endpoint{'' if n == 1 else 's'} "
              f"({cap['open']} public) in " + ", ".join(f"`{f}`" for f in files))
        w("- Gated by: " + (", ".join(cap["gates"]) if cap["gates"] else "nothing — fully public"))
        w("")

    if capmodel.get("caps"):
        w("### Plan matrix")
        w("")
        w("From `PLAN_CAPS` in `app/api/auth.py` — plans in declaration order, "
          "cheapest first.")
        w("")
        order = capmodel["order"]
        w("| Capability | " + " | ".join(p.title() for p in order) + " | What it unlocks |")
        w("| --- | " + " | ".join("---" for _ in order) + " | --- |")
        for c in capmodel["caps"]:
            marks = " | ".join("●" if p in c["plans"] else "·" for p in order)
            w(f"| `{c['cap']}` | {marks} | {c['label']} |")
        w("")

        # Which of those capabilities any route actually checks. A capability nobody
        # depends on is enforced in the UI only, so the API behind it is open.
        enforced = {
            m.group(1).lower()
            for mod in routes for e in mod["endpoints"] for g in e["gates"]
            if (m := re.match(r"require_capability\(\s*CAP_(\w+)\s*\)", g))
        }
        unenforced = [c["cap"] for c in capmodel["caps"] if c["cap"] not in enforced]
        if unenforced:
            w(f"> **Enforced server-side: {', '.join(f'`{c}`' for c in sorted(enforced)) or 'none'}.** "
              "The rest — " + ", ".join(f"`{c}`" for c in unenforced) + " — appear in "
              "`PLAN_CAPS` but are not required by any route, so the paywall for them is "
              "client-side and the API is reachable without the plan.")
            w("")

    off = [s for s in settings
           if s["name"].startswith("enable_") and s["default"] == "False"]
    if off:
        w("### Behavior behind default-off flags")
        w("")
        w("These `app/config.py` settings default to **False**, so the code exists but is "
          "inert unless the environment turns it on. Reading the code alone will "
          "overstate what's running.")
        w("")
        w(", ".join(f"`{s['name'].upper()}`" for s in off))
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

    L.extend(render_diff(previous, changes))

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

    return "\n".join(L) + "\n", snapshot


def _stdout_utf8() -> None:
    """The Windows console defaults to cp1252, which can't encode the arrows/em-dashes
    that appear in commit subjects and docstrings."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", choices=["brief", "standard", "full"], default="standard",
                    help="how much detail to emit (default: standard)")
    ap.add_argument("-o", "--out", default="docs/CODEBASE_CONTEXT.md",
                    help="output path, or '-' for stdout")
    ap.add_argument("--diff", action="store_true",
                    help="print only what changed since the last snapshot, and leave the "
                         "snapshot alone")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="don't update the baseline snapshot (the next run then diffs "
                         "against the same older baseline)")
    args = ap.parse_args()

    text, snapshot = build(args.level)

    # The baseline is only consumed when we actually write the doc: a preview to stdout or
    # a --diff must not silently reset it and make the next real run look empty.
    writing = args.out != "-" and not args.diff and not args.no_snapshot

    if args.diff:
        _stdout_utf8()
        changes = diff_snapshots(load_snapshot(), snapshot)
        sys.stdout.write("\n".join(render_diff(load_snapshot(), changes)) + "\n")
        return 0

    if args.out == "-":
        _stdout_utf8()
        sys.stdout.write(text)
        return 0

    out = (REPO / args.out) if not os.path.isabs(args.out) else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    if writing:
        snap = REPO / SNAPSHOT_FILE
        snap.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    chars = len(text)
    print(f"Wrote {rel(out)}")
    if writing:
        print(f"  baseline updated: {SNAPSHOT_FILE} (commit it so diffs work across machines)")
    # ASCII separators: the Windows console codepage mangles non-ASCII on print.
    print(f"  {chars:,} chars | ~{chars // 4:,} tokens | {text.count(chr(10)):,} lines")
    if chars // 4 > 100_000:
        print("  (large — consider --level brief for pasting into a chat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
