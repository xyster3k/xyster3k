#!/usr/bin/env python3
"""Validate aggregate profile assets before committing them to a public repo."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from generate_private_metrics import CATEGORY_KEYWORDS, render_svg


class ValidationError(ValueError):
    """A fixed diagnostic message that contains no source data."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValidationError(reason)


def integer(value: object) -> bool:
    return type(value) is int and value >= 0


def validate(metrics: dict, svg: str) -> None:
    require(isinstance(metrics, dict), "Expected aggregate object")
    require(set(metrics) == {
        "generated_at", "user", "days", "setup_needed", "privacy", "totals",
        "metric_sources", "top_languages", "categories",
    }, "Unexpected or missing aggregate fields")
    require(metrics["setup_needed"] is False, "Collection requires setup")
    require(isinstance(metrics["user"], str) and bool(re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", metrics["user"]
    )), "Invalid account identifier")
    require(integer(metrics["days"]) and 1 <= metrics["days"] <= 365,
            "Expected a window from 1 to 365 days")
    require(isinstance(metrics["generated_at"], str), "Missing collection time")
    generated = dt.datetime.fromisoformat(metrics["generated_at"].replace("Z", "+00:00"))
    require(generated.utcoffset() == dt.timedelta(0), "Expected UTC collection time")
    age = dt.datetime.now(dt.UTC) - generated
    require(dt.timedelta(minutes=-5) <= age <= dt.timedelta(hours=24),
            "Collection time is stale or in the future")
    require(metrics["privacy"] == (
        "No repository names, URLs, commit messages, branches, or client names are published."
    ), "Unexpected privacy field")

    totals = metrics["totals"]
    require(isinstance(totals, dict) and set(totals) == {
        "accessible_repositories", "public_repositories", "private_repositories",
        "active_repositories", "commits", "pull_requests", "restricted_contributions",
    }, "Unexpected totals fields")
    require(all(integer(value) for value in totals.values()), "Invalid totals")
    require(totals["public_repositories"] + totals["private_repositories"] ==
            totals["accessible_repositories"], "Repository counts disagree")
    require(totals["active_repositories"] <= totals["accessible_repositories"],
            "Active repository count exceeds total")

    sources = metrics["metric_sources"]
    require(isinstance(sources, dict) and set(sources) == {
        "commits", "pull_requests", "commit_search_incomplete",
        "commit_graph_contributions", "restricted_contributions",
    }, "Unexpected metric source fields")
    require(sources["commits"] == "commit_search_author_date", "Commit source changed")
    require(sources["pull_requests"] == "issue_search_author_created", "PR source changed")
    require(sources["commit_search_incomplete"] is False, "Commit search is incomplete")
    require(integer(sources["commit_graph_contributions"]) and
            integer(sources["restricted_contributions"]) and
            sources["restricted_contributions"] == totals["restricted_contributions"],
            "Invalid contribution diagnostics")

    categories = metrics["categories"]
    require(isinstance(categories, dict) and set(categories) <= set(CATEGORY_KEYWORDS),
            "Unexpected category")
    require(all(integer(value) and value <= totals["accessible_repositories"]
                for value in categories.values()), "Invalid category count")
    languages = metrics["top_languages"]
    require(isinstance(languages, list) and len(languages) <= 6, "Invalid language list")
    for language in languages:
        require(isinstance(language, dict) and set(language) == {"name", "bytes", "percent"},
                "Unexpected language fields")
        require(isinstance(language["name"], str) and bool(re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9 #+._()/-]{0,79}", language["name"]
        )), "Invalid language identifier")
        require(integer(language["bytes"]), "Invalid language size")
        require(type(language["percent"]) in (int, float) and
                0 <= language["percent"] <= 100, "Invalid language percentage")

    root = ET.fromstring(svg)
    namespace = "{http://www.w3.org/2000/svg}"
    require(root.tag == namespace + "svg", "Expected SVG image")
    require(all(element.tag in {namespace + tag for tag in ("svg", "rect", "text")}
                for element in root.iter()), "Unexpected SVG element")
    require(all("href" not in key.lower() and not key.lower().startswith("on")
                for element in root.iter() for key in element.attrib),
            "Unexpected SVG reference or handler")
    require(svg == render_svg(metrics), "SVG differs from validated data and renderer")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: validate_public_metrics.py METRICS_JSON METRICS_SVG", file=sys.stderr)
        return 2
    try:
        metrics = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        svg = Path(sys.argv[2]).read_text(encoding="utf-8")
        validate(metrics, svg)
    except ValidationError as exc:
        print(f"::error::Metrics validation failed: {exc}")
        return 1
    except Exception:
        # Values and exceptions may contain private API data. Keep public logs generic.
        print("::error::Metrics validation failed. Check collection status, schema, sources and freshness.")
        return 1
    print("Aggregate JSON and SVG validated for publication.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
