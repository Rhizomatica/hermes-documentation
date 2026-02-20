#!/usr/bin/env python3
"""
Generate hermes-documentation/docs/index.html from git-tracked PDFs only.

Design goals:
- Never link untracked/uncommitted files (source of truth is `git ls-files '*.pdf'`).
- Group links by top-level directory (manual-releases, tech_docs, presentation, ...).
- Link PDFs via raw.githubusercontent.com so GitHub Pages (built from /docs) can reference them without duplicating binaries.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
OUT_PATH = DOCS_DIR / "index.html"


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()


def parse_github_raw_base(origin_url: str) -> str:
    """
    Supports:
      - git@github.com:OWNER/REPO.git
      - https://github.com/OWNER/REPO(.git)
    """
    m = re.match(r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?$", origin_url)
    if m:
        owner, repo = m.group(1), m.group(2)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/main/"

    m = re.match(r"^https?://github\.com/([^/]+)/(.+?)(?:\.git)?$", origin_url)
    if m:
        owner, repo = m.group(1), m.group(2)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/main/"

    raise ValueError(f"Unsupported origin URL format: {origin_url}")


def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    raw_base = os.environ.get("HERMES_DOCS_RAW_BASE")
    if not raw_base:
        origin = run(["git", "remote", "get-url", "origin"])
        raw_base = parse_github_raw_base(origin)
    if not raw_base.endswith("/"):
        raw_base += "/"

    pdfs = run(["git", "ls-files", "*.pdf"]).splitlines()
    pdfs = [p for p in pdfs if p]  # drop empty

    groups: dict[str, list[str]] = defaultdict(list)
    for p in pdfs:
        top = p.split("/", 1)[0] if "/" in p else "(root)"
        groups[top].append(p)

    for k in list(groups.keys()):
        groups[k].sort()

    # Prefer this as the primary manual link if present.
    combined_pdf = "manual-releases/0.2/manual_en_complete.pdf"
    combined_pdf_url = raw_base + quote(combined_pdf)
    # Point directly to the latex2html-generated Table of Contents page.
    combined_html_rel = "manual_en_complete/node1.html"

    def link_to_pdf(path: str) -> str:
        return raw_base + quote(path)

    def display_name(path: str) -> str:
        return path

    # Basic HTML page.
    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>HERMES Documentation</title>")
    parts.append('  <link rel="stylesheet" href="style.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <header class="container">')
    parts.append("    <h1>HERMES HF Telecom Documentation</h1>")
    parts.append(
        "    <p>High-Frequency Emergency and Rural Multimedia Exchange System (HERMES) documentation hub.</p>"
    )
    parts.append(
        '    <p>HTML documentation hub: <a href="https://rhizomatica.github.io/hermes-documentation/">https://rhizomatica.github.io/hermes-documentation/</a></p>'
    )
    parts.append("  </header>")

    parts.append('  <main class="container">')
    parts.append('    <section class="card">')
    parts.append("      <h2>Combined manual</h2>")
    parts.append("      <p>Single entry-point manual combining user, installation, software architecture and hardware docs.</p>")
    parts.append("      <ul>")
    parts.append(
        f'        <li><a href="{html.escape(combined_pdf_url)}">PDF: manual_en_complete.pdf</a></li>'
    )
    parts.append(
        f'        <li><a href="{html.escape(combined_html_rel)}">HTML: manual_en_complete (latex2html)</a></li>'
    )
    parts.append("      </ul>")
    parts.append("    </section>")

    parts.append('    <section class="card">')
    parts.append("      <h2>All PDFs</h2>")
    parts.append('      <input id="filter" type="search" placeholder="Filter (type to search)..." autocomplete="off">')

    for group in sorted(groups.keys()):
        parts.append(f'      <h3 class="group-title">{html.escape(group)}</h3>')
        parts.append('      <ul class="pdf-list">')
        for p in groups[group]:
            url = link_to_pdf(p)
            parts.append(
                f'        <li class="pdf-item" data-path="{html.escape(p)}"><a href="{html.escape(url)}">{html.escape(display_name(p))}</a></li>'
            )
        parts.append("      </ul>")

    parts.append("    </section>")
    parts.append("  </main>")

    parts.append(
        """
  <script>
    const input = document.getElementById('filter');
    input.addEventListener('input', () => {
      const q = input.value.toLowerCase();
      for (const li of document.querySelectorAll('.pdf-item')) {
        const p = li.getAttribute('data-path').toLowerCase();
        li.style.display = p.includes(q) ? '' : 'none';
      }
    });
  </script>
"""
    )

    parts.append("</body>")
    parts.append("</html>")

    OUT_PATH.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
