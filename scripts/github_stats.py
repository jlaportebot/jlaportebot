#!/usr/bin/env python3
"""Collect functional GitHub stats for the jlaportebot profile.

Every number here comes from the live GitHub API through the authenticated
`gh` CLI. Output is a JSON document consumed by the chart renderers.
"""

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

USERNAME = "jlaportebot"

LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Rust": "#dea584",
    "C": "#555555",
    "C++": "#f34b7d",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Lua": "#000080",
    "Luau": "#000080",
    "Jupyter": "#DA5B0B",
}


def gh(args, timeout=120):
    """Run a gh command and return stdout, or an empty string on failure."""
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def gh_json(args, timeout=120, default=None):
    """Run a gh command and parse JSON output."""
    raw = gh(args, timeout=timeout)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def gh_jsonl(args, timeout=180, default=None):
    """Run a gh command producing one JSON object per line."""
    raw = gh(args, timeout=timeout)
    if not raw:
        return default if default is not None else []
    items = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def fetch_user():
    """Profile-level stats."""
    return gh_json(["api", "user"], default={}) or {}


def fetch_repos():
    """All owned repos (public + private) via the authenticated API."""
    repos = gh_jsonl(
        ["api", "user/repos?per_page=100&affiliation=owner", "--paginate",
         "--jq", ".[] | {name:.full_name, stars:.stargazers_count, forks:.forks_count,"
         " watchers:.watchers_count, open_issues:.open_issues_count, lang:.language,"
         " private:.private, fork:.fork, size:.size, created:.created_at,"
         " pushed:.pushed_at, desc:.description, topics:.topics}"],
        default=[],
    )
    return repos


def fetch_search_counts():
    """Lifetime PR and issue counts authored by the user."""
    counts = {}
    for label, kind in (("prs", "pr"), ("issues", "issue")):
        raw = gh(
            ["api", f"search/issues?q=author:{USERNAME}+type:{kind}&per_page=1",
             "--jq", ".total_count"],
            timeout=60,
        )
        try:
            counts[label] = int(raw)
        except (TypeError, ValueError):
            counts[label] = 0
    return counts


def fetch_events():
    """Recent public activity events."""
    return gh_json(
        ["api", f"users/{USERNAME}/events/public?per_page=100"], default=[] ) or []


def summarize(user, repos, counts, events):
    """Fold raw API payloads into the flat stat document."""
    public_repos = [r for r in repos if not r.get("private")]
    private_repos = [r for r in repos if r.get("private")]
    forks = [r for r in repos if r.get("fork")]
    langs = Counter(r.get("lang") for r in repos if r.get("lang"))

    pushed_days = set()
    for repo in repos:
        if repo.get("pushed"):
            pushed_days.add(repo["pushed"][:10])

    event_kinds = Counter(e.get("type") for e in events)

    return {
        "username": USERNAME,
        "name": user.get("name") or USERNAME,
        "bio": user.get("bio") or "",
        "location": user.get("location") or "",
        "blog": user.get("blog") or "",
        "account_created": user.get("created_at") or "",
        "followers": user.get("followers") or 0,
        "following": user.get("following") or 0,
        "total_repos": len(repos),
        "public_repos": len(public_repos),
        "private_repos": len(private_repos),
        "forked_repos": len(forks),
        "original_repos": len(repos) - len(forks),
        "stars": sum(r.get("stars") or 0 for r in repos),
        "forks_received": sum(r.get("forks") or 0 for r in repos),
        "watchers": sum(r.get("watchers") or 0 for r in repos),
        "open_issues": sum(r.get("open_issues") or 0 for r in repos),
        "repo_size_kb": sum(r.get("size") or 0 for r in repos),
        "prs_authored": counts.get("prs", 0),
        "issues_authored": counts.get("issues", 0),
        "languages": [
            {"name": name, "count": count, "color": LANG_COLORS.get(name, "#8b949e")}
            for name, count in langs.most_common(10)
        ],
        "active_days": len(pushed_days),
        "recent_events": len(events),
        "event_kinds": dict(event_kinds.most_common(8)),
        "top_repos": sorted(
            [
                {
                    "name": r["name"],
                    "stars": r.get("stars") or 0,
                    "lang": r.get("lang") or "—",
                    "desc": (r.get("desc") or "")[:120],
                    "private": bool(r.get("private")),
                }
                for r in repos
            ],
            key=lambda r: (-r["stars"], r["name"].lower()),
        )[:6],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    user = fetch_user()
    if not user:
        print("ERROR: could not read GitHub user (auth or network failure)", file=sys.stderr)
        return 1

    repos = fetch_repos()
    if not repos:
        print("ERROR: could not list repositories", file=sys.stderr)
        return 1

    counts = fetch_search_counts()
    events = fetch_events()
    stats = summarize(user, repos, counts, events)

    path = out_dir / "bot-stats.json"
    path.write_text(json.dumps(stats, indent=2))
    print(f"Stats → {path} ({stats['total_repos']} repos, {stats['stars']} stars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
