#!/usr/bin/env python3
"""Generate anonymized aggregate GitHub metrics for a profile README."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
METRICS_JSON = ASSETS / "private-metrics.json"
METRICS_SVG = ASSETS / "private-metrics.svg"
USER = os.getenv("GH_METRICS_USER", "xyster3k")
TOKEN = os.getenv("GH_METRICS_TOKEN") or os.getenv("GITHUB_TOKEN")
DAYS = int(os.getenv("GH_METRICS_DAYS", "365"))
MAX_LANGUAGE_REPOS = int(os.getenv("GH_METRICS_MAX_LANGUAGE_REPOS", "120"))
API = "https://api.github.com"

CATEGORY_KEYWORDS = {
    "biomedical": [
        "biomedical",
        "clinical",
        "clinic",
        "evidence",
        "health",
        "healthcare",
        "medical",
        "medicine",
        "patient",
        "pubmed",
        "research",
    ],
    "AI": [
        "agent",
        "ai",
        "automation",
        "claude",
        "codex",
        "gpt",
        "llm",
        "openai",
        "prompt",
    ],
    "publishing": [
        "cms",
        "content",
        "editorial",
        "news",
        "publishing",
        "seo",
        "website",
    ],
    "automation": [
        "api",
        "cron",
        "etl",
        "integration",
        "orchestration",
        "pipeline",
        "scraper",
        "workflow",
    ],
    "data": [
        "analytics",
        "database",
        "dataset",
        "postgres",
        "postgresql",
        "search",
        "sql",
    ],
}


def request_json(path: str, params: dict[str, str] | None = None) -> tuple[object, dict[str, str]]:
    if params:
        path = f"{path}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            data = json.loads(response.read().decode("utf-8"))
            return data, headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {exc.code} for {path}: {body}") from exc


def request_graphql(query: str, variables: dict[str, str]) -> dict:
    req = urllib.request.Request(f"{API}/graphql", method="POST")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")

    try:
        with urllib.request.urlopen(req, data=payload, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("errors"):
                raise RuntimeError("GitHub GraphQL returned errors")
            return data["data"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub GraphQL error {exc.code}") from exc


def contribution_counts(since_iso: str, until_iso: str) -> dict[str, int]:
    data = request_graphql(
        """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              totalPullRequestContributions
              restrictedContributionsCount
            }
          }
        }
        """,
        {"login": USER, "from": since_iso, "to": until_iso},
    )
    collection = data["user"]["contributionsCollection"]
    return {
        "commits": int(collection["totalCommitContributions"]),
        "pull_requests": int(collection["totalPullRequestContributions"]),
        "restricted_contributions": int(collection["restrictedContributionsCount"]),
    }


def paged(path: str, params: dict[str, str] | None = None) -> list[dict]:
    params = dict(params or {})
    params.setdefault("per_page", "100")
    page = 1
    rows: list[dict] = []

    while True:
        params["page"] = str(page)
        data, headers = request_json(path, params)
        if not isinstance(data, list):
            raise RuntimeError(f"Expected list from {path}")
        rows.extend(data)

        link = headers.get("link", "")
        if 'rel="next"' not in link:
            return rows
        page += 1


def count_paged(path: str, params: dict[str, str]) -> int:
    params = dict(params)
    params["per_page"] = "1"
    data, headers = request_json(path, params)
    if not isinstance(data, list):
        return 0
    link = headers.get("link", "")
    match = re.search(r"[?&]page=(\d+)>; rel=\"last\"", link)
    if match:
        return int(match.group(1))
    return len(data)


def search_count(query: str) -> int:
    data, _ = request_json("/search/issues", {"q": query, "per_page": "1"})
    if isinstance(data, dict):
        return int(data.get("total_count", 0))
    return 0


def classify(repo: dict) -> set[str]:
    text = " ".join(
        [
            str(repo.get("name") or ""),
            str(repo.get("description") or ""),
            " ".join(repo.get("topics") or []),
            str(repo.get("language") or ""),
        ]
    ).lower()
    categories = set()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            categories.add(category)
    return categories


def format_number(value: int) -> str:
    return f"{value:,}"


def top_languages(language_bytes: dict[str, int], limit: int = 6) -> list[dict[str, object]]:
    total = sum(language_bytes.values()) or 1
    top = sorted(language_bytes.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [
        {
            "name": name,
            "bytes": count,
            "percent": round((count / total) * 100, 1),
        }
        for name, count in top
    ]


def placeholder_metrics(reason: str = "missing_token") -> dict:
    return {
        "generated_at": None,
        "user": USER,
        "days": DAYS,
        "setup_needed": True,
        "setup_reason": reason,
        "privacy": "No repository names, URLs, commit messages, branches, or client names are published.",
        "totals": {
            "accessible_repositories": 0,
            "public_repositories": 0,
            "private_repositories": 0,
            "active_repositories": 0,
            "commits": 0,
            "pull_requests": 0,
            "restricted_contributions": 0,
        },
    "top_languages": [],
    "categories": {},
    }


def collect_metrics() -> dict:
    if not TOKEN:
        return placeholder_metrics()

    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    since = now - dt.timedelta(days=DAYS)
    since_iso = since.isoformat().replace("+00:00", "Z")
    until_iso = now.isoformat().replace("+00:00", "Z")
    contribution_totals = contribution_counts(since_iso, until_iso)

    repos = paged(
        "/user/repos",
        {
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "sort": "updated",
            "direction": "desc",
        },
    )

    visible_repos = [repo for repo in repos if not repo.get("archived")]
    active_repos = [
        repo
        for repo in visible_repos
        if repo.get("pushed_at") and repo["pushed_at"] >= since_iso
    ]

    language_bytes: dict[str, int] = {}
    category_counts = {category: 0 for category in CATEGORY_KEYWORDS}

    for repo in visible_repos:
        full_name = repo.get("full_name")
        if not full_name:
            continue

        for category in classify(repo):
            category_counts[category] += 1

    for repo in active_repos[:MAX_LANGUAGE_REPOS]:
        full_name = repo.get("full_name")
        if not full_name:
            continue

        languages, _ = request_json(f"/repos/{full_name}/languages")
        if isinstance(languages, dict):
            for language, byte_count in languages.items():
                language_bytes[language] = language_bytes.get(language, 0) + int(byte_count)

    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "user": USER,
        "days": DAYS,
        "setup_needed": False,
        "privacy": "No repository names, URLs, commit messages, branches, or client names are published.",
        "totals": {
            "accessible_repositories": len(visible_repos),
            "public_repositories": sum(1 for repo in visible_repos if not repo.get("private")),
            "private_repositories": sum(1 for repo in visible_repos if repo.get("private")),
            "active_repositories": len(active_repos),
            "commits": contribution_totals["commits"],
            "pull_requests": contribution_totals["pull_requests"],
            "restricted_contributions": contribution_totals["restricted_contributions"],
        },
        "top_languages": top_languages(language_bytes),
        "categories": {key: value for key, value in category_counts.items() if value},
    }


def svg_text(x: int, y: int, text: str, size: int = 14, weight: str = "400", fill: str = "#24292f") -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{html.escape(text)}</text>'
    )


def render_svg(metrics: dict) -> str:
    totals = metrics["totals"]
    setup_needed = metrics.get("setup_needed", False)
    setup_reason = metrics.get("setup_reason")
    title = "Private GitHub activity" if not setup_needed else "Private metrics pending"
    if setup_reason == "token_or_api_error":
        title = "Private metrics setup needs attention"
    subtitle = (
        f"Anonymized aggregate activity, last {metrics['days']} days"
        if not setup_needed
        else "Check GH_METRICS_TOKEN permissions and rerun the workflow"
        if setup_reason == "token_or_api_error"
        else "Add GH_METRICS_TOKEN as a repository secret to enable private aggregates"
    )

    languages = metrics.get("top_languages") or []
    categories = metrics.get("categories") or {}

    lines = [
        svg_text(24, 36, title, 18, "700"),
        svg_text(24, 60, subtitle, 13, "400", "#57606a"),
    ]

    cards = [
        ("Commits", format_number(totals["commits"])),
        ("Pull requests", format_number(totals["pull_requests"])),
        ("Active repos", format_number(totals["active_repositories"])),
        ("Private repos", format_number(totals["private_repositories"])),
    ]

    x_positions = [24, 180, 336, 492]
    for x, (label, value) in zip(x_positions, cards):
        lines.append(f'<rect x="{x}" y="84" width="132" height="72" rx="8" fill="#f6f8fa" stroke="#d0d7de" />')
        lines.append(svg_text(x + 14, 112, value, 22, "700"))
        lines.append(svg_text(x + 14, 138, label, 12, "400", "#57606a"))

    lang_text = "Languages: pending"
    if languages:
        lang_text = "Languages: " + ", ".join(
            f"{item['name']} {item['percent']}%" for item in languages[:4]
        )
    lines.append(svg_text(24, 194, lang_text, 13, "400", "#24292f"))

    category_text = "Systems: pending"
    if categories:
        category_text = "Systems: " + ", ".join(
            f"{name} ({count})" for name, count in sorted(categories.items())
        )
    lines.append(svg_text(24, 222, category_text, 13, "400", "#24292f"))
    lines.append(svg_text(24, 252, "No private repository names, URLs, commit messages, or client names are published.", 12, "400", "#57606a"))

    return "\n".join(
        [
            '<svg width="648" height="278" viewBox="0 0 648 278" fill="none" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="648" height="278" rx="10" fill="#ffffff" stroke="#d0d7de" />',
            *lines,
            "</svg>",
            "",
        ]
    )


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    try:
        metrics = collect_metrics()
    except Exception:
        print("Metrics collection failed; wrote a safe setup placeholder. Check GH_METRICS_TOKEN permissions.")
        metrics = placeholder_metrics("token_or_api_error")
    METRICS_JSON.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    METRICS_SVG.write_text(render_svg(metrics), encoding="utf-8")
    print(f"Wrote {METRICS_JSON.relative_to(ROOT)}")
    print(f"Wrote {METRICS_SVG.relative_to(ROOT)}")
    if metrics.get("setup_needed"):
        print("GH_METRICS_TOKEN is not set; wrote setup placeholder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
