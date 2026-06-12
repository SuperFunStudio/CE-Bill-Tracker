"""Render tmp/design_guide.md into a branded, print-ready single-file HTML artifact.

Keeps the Markdown draft as the source of truth (this only restyles it) and emits a
self-contained tmp/design_guide.html in the dashboard's "gazette" aesthetic — light paper,
serif masthead between newspaper rules, white principle cards, blue accent. No external assets,
so it shares as one file and "Print → Save as PDF" yields a clean PDF (evidence blocks are
force-expanded for print).

Usage:
    venv/Scripts/python.exe scripts/render_design_guide.py
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

TMP = Path(__file__).parent.parent / "tmp"
SRC = TMP / "design_guide.md"
OUT = TMP / "design_guide.html"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    para: list[str] = []
    li: list[str] = []
    bq: list[str] = []
    section_open = False
    masthead_done = False
    expect_tagline = False

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + " ".join(inline(x) for x in para) + "</p>")
            para = []

    def flush_li():
        nonlocal li
        if li:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in li) + "</ul>")
            li = []

    def flush_bq():
        nonlocal bq
        if bq:
            out.append("<blockquote>" + "<br>".join(inline(x) for x in bq) + "</blockquote>")
            bq = []

    def flush_block():
        flush_bq(); flush_li(); flush_para()

    def close_section():
        nonlocal section_open
        if section_open:
            out.append("</section>")
            section_open = False

    for raw in lines:
        line = raw.rstrip()

        # Raw HTML passthrough (the <details>/<summary> evidence wrappers).
        if line.startswith("<details") or line == "</details>":
            flush_block()
            out.append(line)
            expect_tagline = False
            continue

        # Blockquote accumulation.
        if line.startswith(">"):
            flush_li(); flush_para()
            bq.append(line[1:].lstrip())
            expect_tagline = False
            continue
        if bq:
            flush_bq()

        if not line.strip():
            flush_li(); flush_para()
            continue

        if line.startswith("## "):
            flush_block(); close_section()
            out.append('<section class="lever">')
            section_open = True
            out.append(f"<h2>{inline(line[3:])}</h2>")
            expect_tagline = False
            continue

        if line.startswith("# "):
            flush_block(); close_section()
            text = line[2:]
            if not masthead_done:
                masthead_done = True
                expect_tagline = True
                out.append(
                    '<header class="masthead"><div class="rule-top"></div>'
                    f"<h1>{inline(text)}</h1><div class=\"rule-bot\"></div></header>"
                )
            else:
                out.append(f'<div class="part">{inline(text)}</div>')
                expect_tagline = False
            continue

        if line.startswith("- "):
            flush_para()
            li.append(inline(line[2:]))
            expect_tagline = False
            continue

        if line.strip() == "---":
            flush_block()
            continue

        # Plain text line: kicker label, masthead tagline, or paragraph.
        if li:
            flush_li()
        m = re.match(r"^\*\*(.+)\*\*$", line.strip())
        if m:
            flush_para()
            out.append(f'<p class="kicker">{inline(m.group(1))}</p>')
            expect_tagline = False
            continue
        if expect_tagline and line.lstrip().startswith("_"):
            out.append(f'<p class="tagline">{inline(line.strip())}</p>')
            expect_tagline = False
            continue
        expect_tagline = False
        para.append(line.strip())

    flush_block(); close_section()
    return "\n".join(out)


CSS = """
:root{
  --paper:#f8f9fa; --card:#ffffff; --rule:#dee2e6;
  --ink:#1a1a2e; --ink2:#495057; --muted:#6b7280; --accent:#1e6ae9; --accent-bg:#eff6ff;
}
*{box-sizing:border-box}
html{ -webkit-text-size-adjust:100% }
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.55;
}
.wrap{ max-width:780px; margin:0 auto; padding:32px 22px 80px }
.serif{ font-family:Georgia,Cambria,"Times New Roman",serif }
.masthead{ text-align:center; margin:6px 0 18px }
.masthead .rule-top{ border-top:2px solid var(--ink); }
.masthead .rule-bot{ border-top:1px solid rgba(26,26,46,.3); }
.masthead h1{
  font-family:Georgia,Cambria,serif; text-transform:uppercase; letter-spacing:.05em;
  font-weight:700; font-size:30px; line-height:1.15; margin:14px 8px; color:var(--ink);
}
.tagline{ font-family:Georgia,serif; font-style:italic; color:var(--ink2); text-align:center;
  font-size:15px; margin:-6px 0 4px }
.dateline{ text-align:center; text-transform:uppercase; letter-spacing:.18em; font-size:11px;
  color:var(--muted); margin:0 0 22px }
.part{
  font-family:Georgia,serif; text-transform:uppercase; letter-spacing:.08em; font-weight:700;
  font-size:15px; color:var(--ink); text-align:center; margin:38px 0 18px; padding:8px 0;
  border-top:2px solid var(--ink); border-bottom:1px solid var(--rule);
}
section.lever{
  background:var(--card); border:1px solid var(--rule); border-radius:10px;
  padding:20px 22px; margin:0 0 18px; break-inside:avoid;
}
section.lever h2{
  font-family:Georgia,serif; font-size:20px; font-weight:700; line-height:1.25;
  margin:0 0 8px; color:var(--ink);
}
.kicker{
  text-transform:uppercase; letter-spacing:.1em; font-size:11px; font-weight:700;
  color:var(--accent); margin:16px 0 6px;
}
p{ margin:8px 0; color:var(--ink2); font-size:14.5px }
section.lever > p:first-of-type{ color:var(--ink) }
em{ color:var(--muted) }
ul{ margin:6px 0 4px; padding-left:18px }
li{ margin:6px 0; font-size:14px; color:var(--ink2) }
li strong{ color:var(--ink) }
blockquote{
  margin:8px 0; padding:8px 14px; border-left:3px solid var(--accent);
  background:var(--accent-bg); font-family:Georgia,serif; font-style:italic;
  font-size:13.5px; color:var(--ink2); border-radius:0 6px 6px 0;
}
details{ margin:12px 0 2px }
summary{ cursor:pointer; font-size:11px; text-transform:uppercase; letter-spacing:.08em;
  color:var(--accent); font-weight:700 }
code{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12.5px;
  background:var(--paper); padding:1px 4px; border-radius:3px }
a{ color:var(--accent) }
.printbtn{
  position:fixed; top:14px; right:14px; background:var(--accent); color:#fff; border:0;
  padding:9px 14px; border-radius:7px; font-size:13px; font-weight:600; cursor:pointer;
  box-shadow:0 2px 8px rgba(0,0,0,.15);
}
@media print{
  body{ background:#fff }
  .wrap{ max-width:none; padding:0 }
  .printbtn{ display:none }
  section.lever{ border-color:#ccc; box-shadow:none }
  /* Force evidence blocks open when printing so quotes are not lost. */
  details > *{ display:block !important }
  summary{ display:none }
  a{ color:var(--ink); text-decoration:none }
}
"""


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing {SRC}. Run scripts/build_design_guide.py first.")
    md = SRC.read_text(encoding="utf-8")
    body = convert(md)
    # %d is zero-padded and cross-platform; strip a leading zero for a natural date.
    dateline = ("SignalScout · Circularity Intelligence · Compiled "
                + date.today().strftime("%d %B %Y").lstrip("0"))

    # Insert the dateline right after the masthead header block.
    body = body.replace("</header>", f"</header>\n<p class=\"dateline\">{esc(dateline)}</p>", 1)

    html = (
        "<!doctype html>\n<html lang=\"en\"><head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Designing for Circularity — A Practitioner's Guide</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        "<button class=\"printbtn\" onclick=\"window.print()\">Print / Save as PDF</button>\n"
        f"<div class=\"wrap\">\n{body}\n</div>\n</body></html>\n"
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT}  ({len(html)} chars)")


if __name__ == "__main__":
    main()
