#!/usr/bin/env python3
"""Collect public internship feeds and render a freshness-sorted README."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "jobs.json"
STATUS_PATH = ROOT / "data" / "source_status.json"
README_PATH = ROOT / "README.md"
NOW = dt.datetime.now(dt.timezone.utc)
README_LIMIT = 4000
USER_AGENT = "live-tech-internships/1.0 (+https://github.com/AvPa1212/live-tech-internships)"

SOURCES = [
    {
        "name": "Amazon Jobs",
        "url": "https://www.amazon.jobs/en/search.json?base_query=intern&loc_query=United%20States&sort=recent",
        "careers_url": "https://www.amazon.jobs/",
        "kind": "amazon",
    },
    {
        "name": "NVIDIA Careers",
        "url": "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",
        "careers_url": "https://www.nvidia.com/en-us/about-nvidia/careers/",
        "kind": "workday",
        "payload": {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
        "company": "NVIDIA",
    },
    {
        "name": "Google Careers",
        "url": "https://careers.google.com/jobs/results/?q=intern",
        "careers_url": "https://careers.google.com/",
        "kind": "jsonld",
    },
    {
        "name": "Apple Jobs",
        "url": "https://jobs.apple.com/en-us/search?search=intern",
        "careers_url": "https://jobs.apple.com/",
        "kind": "jsonld",
    },
    {
        "name": "Microsoft Careers",
        "url": "https://gcsservices.careers.microsoft.com/search/api/v1/search?pg=1&pgSz=100&query=intern",
        "careers_url": "https://careers.microsoft.com/",
        "kind": "microsoft",
    },
    {
        "name": "Meta Careers",
        "url": "https://www.metacareers.com/jobs?teams[0]=intern",
        "careers_url": "https://www.metacareers.com/",
        "kind": "jsonld",
    },
    {
        "name": "Tesla Careers",
        "url": "https://www.tesla.com/careers/search/?query=intern",
        "careers_url": "https://www.tesla.com/careers/",
        "kind": "jsonld",
    },
    {
        "name": "IBM Careers",
        "url": "https://www.ibm.com/careers/search?q=intern",
        "careers_url": "https://www.ibm.com/careers/",
        "kind": "jsonld",
    },
    {
        "name": "Intel Jobs",
        "url": "https://jobs.intel.com/en/search-jobs/intern/599/1",
        "careers_url": "https://jobs.intel.com/",
        "kind": "jsonld",
    },
    {
        "name": "Salesforce Careers",
        "url": "https://careers.salesforce.com/en/jobs/?q=intern",
        "careers_url": "https://careers.salesforce.com/",
        "kind": "jsonld",
    },
    {
        "name": "OpenAI Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/openai/jobs?content=true",
        "careers_url": "https://openai.com/careers/",
        "kind": "greenhouse",
    },
    {
        "name": "Stripe Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true",
        "careers_url": "https://stripe.com/jobs/",
        "kind": "greenhouse",
    },
    {
        "name": "Cloudflare Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true",
        "careers_url": "https://www.cloudflare.com/careers/",
        "kind": "greenhouse",
    },
    {
        "name": "Datadog Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true",
        "careers_url": "https://careers.datadoghq.com/",
        "kind": "greenhouse",
    },
    {
        "name": "Figma Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/figma/jobs?content=true",
        "careers_url": "https://www.figma.com/careers/",
        "kind": "greenhouse",
    },
    {
        "name": "Coinbase Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/coinbase/jobs?content=true",
        "careers_url": "https://www.coinbase.com/careers",
        "kind": "greenhouse",
    },
    {
        "name": "Dropbox Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/dropbox/jobs?content=true",
        "careers_url": "https://jobs.dropbox.com/",
        "kind": "greenhouse",
    },
    {
        "name": "Reddit Careers",
        "url": "https://boards-api.greenhouse.io/v1/boards/reddit/jobs?content=true",
        "careers_url": "https://www.redditinc.com/careers",
        "kind": "greenhouse",
    },
    {
        "name": "Dreamwork",
        "url": "https://raw.githubusercontent.com/dreamworkhq/Tech-Internships-2027/main/data/listings.json",
        "careers_url": "https://github.com/dreamworkhq/Tech-Internships-2027",
        "kind": "dreamwork",
    },
    {
        "name": "Zshah",
        "url": "https://raw.githubusercontent.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/main/data/jobs.json",
        "careers_url": "https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships",
        "kind": "zshah",
    },
    {
        "name": "Vansh",
        "url": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/main/.github/scripts/listings.json",
        "careers_url": "https://github.com/vanshb03/Summer2027-Internships",
        "kind": "vansh",
    },
    {
        "name": "DereC4",
        "url": "https://raw.githubusercontent.com/DereC4/internships-and-newgrad/main/README.md",
        "careers_url": "https://github.com/DereC4/internships-and-newgrad",
        "kind": "derec4",
    },
]


def fetch(url: str, payload: dict[str, object] | None = None) -> str:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data else "GET")
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


def allowed_by_robots(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        robots = urllib.robotparser.RobotFileParser(robots_url)
        robots.set_url(robots_url)
        robots.read()
        if not robots.can_fetch(USER_AGENT, url):
            return False, f"robots.txt disallows {parsed.path or '/'}"
        return True, "robots.txt allows this public URL"
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        return True, f"robots.txt unavailable; no automated restriction observed ({error})"


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


def expiration_date(item: dict[str, object]) -> object:
    for key in (
        "validThrough",
        "valid_through",
        "expirationDate",
        "expiration_date",
        "expiresAt",
        "expires_at",
        "expires",
        "expiryDate",
        "expiry_date",
        "applicationDeadline",
        "application_deadline",
        "applicationEndDate",
        "application_end_date",
        "closingDate",
        "closing_date",
        "close_date",
        "deadline",
    ):
        if item.get(key):
            return item[key]
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
    expires: object = None,
) -> dict[str, object] | None:
    if not active or not title or not url:
        return None
    expires_on = parse_date(expires)
    if expires_on and dt.date.fromisoformat(expires_on) < NOW.date():
        return None
    return {
        "company": clean(company),
        "title": clean(title),
        "location": clean(location),
        "url": str(url).strip(),
        "posted_at": parse_date(posted),
        "source": source,
    }


def parse_greenhouse(source: str, payload: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    for item in payload.get("jobs", []):
        if not isinstance(item, dict):
            continue
        content = item.get("content") or ""
        if not re.search(r"\bintern(ship)?\b|\bco-?op\b", f"{item.get('title', '')} {content}", re.I):
            continue
        job = normalize(
            source=source,
            company=source.removesuffix(" Careers"),
            title=item.get("title"),
            location=(item.get("location") or {}).get("name") if isinstance(item.get("location"), dict) else item.get("location"),
            url=item.get("absolute_url"),
            posted=item.get("updated_at"),
            expires=expiration_date(item),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_amazon(payload: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    for item in payload.get("jobs", []):
        if not isinstance(item, dict):
            continue
        job = normalize(
            source="Amazon Jobs",
            company="Amazon",
            title=item.get("title"),
            location=item.get("location"),
            url=urljoin("https://www.amazon.jobs", item.get("job_path", "")),
            posted=item.get("posted_date") or item.get("updated_time"),
            expires=expiration_date(item),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_workday(source: str, payload: dict[str, object], company: str) -> list[dict[str, object]]:
    jobs = []
    for item in payload.get("jobPostings", []):
        if not isinstance(item, dict):
            continue
        job = normalize(
            source=source,
            company=company,
            title=item.get("title"),
            location=item.get("locationsText") or item.get("location"),
            url=urljoin("https://nvidia.wd5.myworkdayjobs.com", item.get("externalPath", "")),
            posted=item.get("postedOn"),
            expires=expiration_date(item),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_microsoft(payload: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    result = payload.get("operationResult", {}).get("result", {}) if isinstance(payload.get("operationResult"), dict) else {}
    for item in result.get("jobs", []):
        if not isinstance(item, dict):
            continue
        properties = item.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        job_id = item.get("jobId") or properties.get("jobId")
        locations = properties.get("locations") or properties.get("primaryLocation")
        if isinstance(locations, list):
            locations = ", ".join(str(location) for location in locations)
        job = normalize(
            source="Microsoft Careers",
            company="Microsoft",
            title=item.get("title"),
            location=locations,
            url=f"https://apply.careers.microsoft.com/careers/job/{job_id}" if job_id else None,
            posted=item.get("postingDate"),
            expires=expiration_date(properties) or expiration_date(item),
        )
        if job and re.search(r"\bintern(ship)?\b|\bco-?op\b", str(job["title"]), re.I):
            jobs.append(job)
    return jobs


def parse_jsonld(source: str, text: str) -> list[dict[str, object]]:
    jobs = []
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        text,
        re.I | re.S,
    )
    for script in scripts:
        try:
            payload = json.loads(html.unescape(script))
        except json.JSONDecodeError:
            continue
        objects = payload if isinstance(payload, list) else [payload]
        for item in objects:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            location = item.get("jobLocation", "")
            if isinstance(location, dict):
                address = location.get("address", {})
                location = ", ".join(
                    str(address.get(key, ""))
                    for key in ("addressLocality", "addressRegion", "addressCountry")
                    if address.get(key)
                )
            job = normalize(
                source=source,
                company=item.get("hiringOrganization", {}).get("name") if isinstance(item.get("hiringOrganization"), dict) else source,
                title=item.get("title"),
                location=location,
                url=item.get("url"),
                posted=item.get("datePosted"),
                expires=expiration_date(item),
            )
            if job and re.search(r"\bintern(ship)?\b|\bco-?op\b", str(job["title"]), re.I):
                jobs.append(job)
    return jobs


def parse_repo(source: str, kind: str, payload: object) -> list[dict[str, object]]:
    if kind == "dreamwork":
        return [
            job
            for item in payload.get("listings", [])
            if isinstance(item, dict)
            for job in [normalize(source=source, company=item.get("company"), title=item.get("title"), location=item.get("location"), url=item.get("url"), posted=item.get("postedAt") or item.get("firstIndexedAt"), expires=expiration_date(item))]
            if job
        ]
    if kind == "zshah":
        return [
            job
            for item in payload.values()
            if isinstance(item, dict)
            for job in [normalize(source=source, company=item.get("company"), title=item.get("title"), location=item.get("location"), url=item.get("url"), posted=item.get("posted_at"), active=item.get("is_open", True), expires=expiration_date(item))]
            if job
        ]
    if kind == "vansh":
        return [
            job
            for item in payload
            if isinstance(item, dict)
            for job in [normalize(source=source, company=item.get("company_name"), title=item.get("title"), location=", ".join(item.get("locations", [])), url=item.get("url"), posted=item.get("date_posted"), active=item.get("active", True) and item.get("is_visible", True), expires=expiration_date(item))]
            if job
        ]
    jobs = []
    for line in str(payload).splitlines():
        if not line.startswith("|") or "http" not in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in {"company", "---"}:
            continue
        match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", cells[1])
        age_match = re.search(r"(\d+)d", cells[-1])
        if not match or not age_match:
            continue
        job = normalize(
            source=source,
            company=cells[0],
            title=match.group(1),
            location=cells[2],
            url=match.group(2),
            posted=(NOW.date() - dt.timedelta(days=int(age_match.group(1)))).isoformat(),
        )
        if job:
            jobs.append(job)
    return jobs


def collect(source: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
    allowed, policy = allowed_by_robots(str(source["url"]))
    status = {
        "name": source["name"],
        "careers_url": source["careers_url"],
        "endpoint": source["url"],
        "policy_check": policy,
        "allowed": allowed,
        "jobs": 0,
    }
    if not allowed:
        status["error"] = policy
        return [], status
    text = fetch(str(source["url"]), source.get("payload"))
    kind = source["kind"]
    if kind == "amazon":
        jobs = parse_amazon(json.loads(text))
    elif kind == "workday":
        jobs = parse_workday(str(source["name"]), json.loads(text), str(source["company"]))
    elif kind == "greenhouse":
        jobs = parse_greenhouse(str(source["name"]), json.loads(text))
    elif kind == "microsoft":
        jobs = parse_microsoft(json.loads(text))
    elif kind == "jsonld":
        jobs = parse_jsonld(str(source["name"]), text)
    else:
        jobs = parse_repo(str(source["name"]), str(kind), json.loads(text) if kind != "derec4" else text)
    status["jobs"] = len(jobs)
    return jobs, status


def dedupe(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[str, dict[str, object]] = {}
    for job in jobs:
        key = re.sub(r"[?#].*$", "", str(job["url"])).rstrip("/").lower()
        previous = by_key.get(key)
        if previous is None or str(job["posted_at"] or "") > str(previous["posted_at"] or ""):
            by_key[key] = job
    return sorted(by_key.values(), key=lambda job: (job["posted_at"] is not None, job["posted_at"] or ""), reverse=True)


def age_label(posted_at: str | None) -> str:
    if not posted_at:
        return "Date not reported"
    age = (NOW.date() - dt.date.fromisoformat(posted_at)).days
    return "Posted today" if age <= 0 else "Posted yesterday" if age == 1 else f"Posted {age} days ago"


def render(jobs: list[dict[str, object]], statuses: list[dict[str, object]], generated_at: str) -> str:
    visible_jobs = jobs[:README_LIMIT]
    source_lines = [
        "## Sources and access policy",
        "",
        "The updater uses only public career pages or public job-board endpoints. It checks each endpoint's `robots.txt` before every fetch, sends an identifying User-Agent, uses no login, bypass, proxy, or CAPTCHA solving, and skips a source when robots.txt disallows it. Robots compliance is not legal advice; each source's live check and endpoint are recorded in [`data/source_status.json`](data/source_status.json).",
        "",
        "| Source | Official careers page | Public endpoint | Robots check | Roles |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for status in statuses:
        source_lines.append(
            f"| {status['name']} | [careers]({status['careers_url']}) | [endpoint]({status['endpoint']}) | "
            f"{'allowed' if status['allowed'] else 'skipped'}: {status['policy_check']} | {status['jobs']} |"
        )
    lines = [
        "# Live Tech Internships",
        "",
        f"> **{len(visible_jobs):,} newest open roles** (of {len(jobs):,} collected), sorted by reported posting date.",
        f"> Last updated: **{generated_at}**",
        "",
        "Jobs are deduplicated by canonical application URL. Roles with a reported application deadline are removed after it expires; listings are refreshed regularly from their sources. Roles without a source-provided posting date appear last. The table is capped at the newest 4,000 roles so GitHub can render the README; the complete normalized snapshot is in [`data/jobs.json`](data/jobs.json).",
        "",
        *source_lines,
        "",
        "## Listings",
        "",
        "| Company | Role | Location | Posted | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for job in visible_jobs:
        lines.append(
            f"| {job['company']} | [{job['title']}]({job['url']}) | {job['location']} | "
            f"{job['posted_at'] or 'Not reported'} ({age_label(job['posted_at'])}) | {job['source']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    jobs: list[dict[str, object]] = []
    statuses: list[dict[str, object]] = []
    errors = []
    for source in SOURCES:
        try:
            found, status = collect(source)
            jobs.extend(found)
            statuses.append(status)
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            statuses.append({
                "name": source["name"],
                "careers_url": source["careers_url"],
                "endpoint": source["url"],
                "policy_check": "fetch failed",
                "allowed": True,
                "jobs": 0,
                "error": str(error),
            })
            errors.append(f"{source['name']}: {error}")
    jobs = dedupe(jobs)
    if len(jobs) < 100:
        print("update failed: safety check refused to publish fewer than 100 roles", file=sys.stderr)
        return 1
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps({"generated_at": NOW.isoformat(), "count": len(jobs), "jobs": jobs}, indent=2) + "\n")
    STATUS_PATH.write_text(json.dumps({"checked_at": NOW.isoformat(), "sources": statuses}, indent=2) + "\n")
    README_PATH.write_text(render(jobs, statuses, NOW.strftime("%Y-%m-%d %H:%M UTC")))
    print(f"Rendered {len(jobs)} roles from {sum(status['jobs'] > 0 for status in statuses)} sources")
    for error in errors:
        print(f"warning: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
