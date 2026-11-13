#!/usr/bin/env python3
"""Fetch internship feeds and render a freshness-sorted README."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "jobs.json"
README_PATH = ROOT / "README.md"
NOW = dt.datetime.now(dt.timezone.utc)
README_LIMIT = 4000

FEEDS = {
    "Dreamwork": "https://raw.githubusercontent.com/dreamworkhq/Tech-Internships-2027/main/data/listings.json",
    "Zshah": "https://raw.githubusercontent.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/main/data/jobs.json",
    "Vansh": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/main/.github/scripts/listings.json",
}
README_FEED = (
    "https://raw.githubusercontent.com/DereC4/internships-and-newgrad/main/README.md"
)


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "live-tech-internships/1.0"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def parse_date(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date().isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def clean(value: object, default: str = "—") -> str:
    text = re.sub(r"\s+", " ", html.unescape(str(value or "")).strip())
    return text or default


def normalize(
    *,
    source: str,
    company: object,
    title: object,
    location: object,
    url: object,
    posted: object,
    active: bool = True,
) -> dict[str, object] | None:
    if not active or not title or not url:
        return None
    posted_at = parse_date(posted)
    return {
        "company": clean(company),
        "title": clean(title),
        "location": clean(location),
        "url": str(url).strip(),
        "posted_at": posted_at,
        "source": source,
    }


def parse_dreamwork(payload: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    for item in payload.get("listings", []):
        if not isinstance(item, dict):
            continue
        job = normalize(
            source="Dreamwork",
            company=item.get("company"),
            title=item.get("title"),
            location=item.get("location"),
            url=item.get("url"),
            posted=item.get("postedAt") or item.get("firstIndexedAt"),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_zshah(payload: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    for item in payload.values():
        if not isinstance(item, dict):
            continue
        job = normalize(
            source="Zshah",
            company=item.get("company"),
            title=item.get("title"),
            location=item.get("location"),
            url=item.get("url"),
            posted=item.get("posted_at"),
            active=item.get("is_open", True),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_vansh(payload: list[object]) -> list[dict[str, object]]:
    jobs = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        job = normalize(
            source="Vansh",
            company=item.get("company_name"),
            title=item.get("title"),
            location=", ".join(item.get("locations", [])),
            url=item.get("url"),
            posted=item.get("date_posted"),
            active=item.get("active", True) and item.get("is_visible", True),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_readme(text: str) -> list[dict[str, object]]:
    jobs = []
    for line in text.splitlines():
        if not line.startswith("|") or "http" not in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in {"company", "---"}:
            continue
        match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", cells[1])
        age_match = re.search(r"(\d+)d", cells[-1])
        if not match or not age_match:
            continue
        posted = NOW.date() - dt.timedelta(days=int(age_match.group(1)))
        job = normalize(
            source="DereC4",
            company=re.sub(r"\[|\]", "", cells[0]),
            title=match.group(1),
            location=cells[2],
            url=match.group(2),
            posted=posted.isoformat(),
        )
        if job:
            jobs.append(job)
    return jobs


def dedupe(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[str, dict[str, object]] = {}
    for job in jobs:
        key = re.sub(r"[?#].*$", "", str(job["url"])).rstrip("/").lower()
        previous = by_key.get(key)
        if previous is None or str(job["posted_at"] or "") > str(previous["posted_at"] or ""):
            by_key[key] = job
    return sorted(
        by_key.values(),
        key=lambda job: (job["posted_at"] is not None, job["posted_at"] or ""),
        reverse=True,
    )


def age_label(posted_at: str | None) -> str:
    if not posted_at:
        return "Date not reported"
    age = (NOW.date() - dt.date.fromisoformat(posted_at)).days
    if age <= 0:
        return "Posted today"
    if age == 1:
        return "Posted yesterday"
    return f"Posted {age} days ago"


def render(jobs: list[dict[str, object]], generated_at: str) -> str:
    visible_jobs = jobs[:README_LIMIT]
    counts = len(visible_jobs)
    source_counts = ", ".join(
        f"{source}: {sum(job['source'] == source for job in jobs)}"
        for source in FEEDS | {"DereC4": ""}
        if any(job["source"] == source for job in jobs)
    )
    lines = [
        "# Live Tech Internships",
        "",
        f"> **{counts:,} newest open roles** (of {len(jobs):,} collected), sorted by the posting date reported by each upstream feed.",
        f"> Last updated: **{generated_at}** · Sources: {source_counts}",
        "",
        "This README is regenerated automatically every 30 minutes. Jobs are deduplicated by canonical application URL; roles without a source-provided posting date appear last. The complete normalized snapshot is available in [`data/jobs.json`](data/jobs.json).",
        "",
        "| Company | Role | Location | Posted | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for job in visible_jobs:
        posted = job["posted_at"] or "Not reported"
        age = age_label(job["posted_at"])
        lines.append(
            f"| {job['company']} | [{job['title']}]({job['url']}) | "
            f"{job['location']} | {posted} ({age}) | {job['source']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        dreamwork = json.loads(fetch(FEEDS["Dreamwork"]))
        zshah = json.loads(fetch(FEEDS["Zshah"]))
        vansh = json.loads(fetch(FEEDS["Vansh"]))
        jobs = parse_dreamwork(dreamwork) + parse_zshah(zshah) + parse_vansh(vansh)
        if not jobs:
            raise RuntimeError("All machine-readable feeds returned zero usable roles")
        try:
            jobs += parse_readme(fetch(README_FEED))
        except RuntimeError as error:
            print(f"warning: README fallback unavailable: {error}", file=sys.stderr)
        jobs = dedupe(jobs)
        if len(jobs) < 100:
            raise RuntimeError(f"Safety check refused to publish only {len(jobs)} roles")
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(
            json.dumps(
                {"generated_at": NOW.isoformat(), "count": len(jobs), "jobs": jobs},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        README_PATH.write_text(render(jobs, NOW.strftime("%Y-%m-%d %H:%M UTC")), encoding="utf-8")
        print(f"Rendered {len(jobs)} roles")
        return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"update failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
