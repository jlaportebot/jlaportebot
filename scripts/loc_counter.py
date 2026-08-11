#!/usr/bin/env python3
"""
Deterministic LOC counter for jlaportebot.

Strategy (API-only, no cloning, fully deterministic):
1. OWNED repos (public + private): use stats/contributors API for per-author LOC
2. EXTERNAL repos (no fork/own): use pulls API for PR diff stats
3. LIFETIME cache: per-repo values cached in loc_lifetime_cache.json
   — if a repo returns 0 this run (API failure/rate limit), keep stale cached value
4. Monotonic: LOC should only increase or stay the same, never drop

Root causes fixed:
- Clone timeouts (120s) silently returning (0,0,0) → entire repos vanish each run
- Public-only API endpoint missing private repos (lobster-os, cruisewatch-pro)
- No caching → non-deterministic results based on network conditions
"""
import json
import os
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "jlaportebot")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")
CACHE_FILE = Path(__file__).parent / "loc_lifetime_cache.json"

EMAILS = [
    f"{USERNAME}@gmail.com",
    f"{USERNAME}@users.noreply.github.com",
]


def run(cmd, timeout=60):
    """Run a shell command, return (stdout, returncode)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", 1
    except Exception:
        return "", 1


def load_cache():
    """Load the per-repo lifetime cache."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"repos": {}, "last_updated": None, "lifetime_total": {"added": 0, "deleted": 0, "commits": 0}}


def save_cache(cache):
    """Save the per-repo lifetime cache."""
    cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def get_owned_repos():
    """Fetch ALL owned repos (public + private) via authenticated API."""
    cmd = (
        "gh api 'user/repos?per_page=100&affiliation=owner' --paginate "
        "--jq '.[].full_name' 2>/dev/null"
    )
    out, rc = run(cmd, timeout=120)
    if not out or rc != 0:
        return []
    return sorted(set(line.strip() for line in out.split("\n") if line.strip()))


def get_owned_repo_stats(repo):
    """Get per-author LOC via stats/contributors API. Handles 202 async."""
    cmd = f"gh api repos/{repo}/stats/contributors 2>/dev/null"
    for attempt in range(2):
        out, rc = run(cmd, timeout=60)
        if not out or rc != 0:
            time.sleep(1)
            continue
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            time.sleep(1)
            continue
        if not isinstance(data, list):
            time.sleep(1)
            continue
        for contributor in data:
            author = contributor.get("author") or {}
            if author.get("login", "").lower() == USERNAME.lower():
                weeks = contributor.get("weeks", [])
                added = sum(w.get("a", 0) for w in weeks)
                deleted = sum(w.get("d", 0) for w in weeks)
                commits = sum(w.get("c", 0) for w in weeks)
                return added, deleted, commits
        return 0, 0, 0
    return None, None, None


def get_external_repos_stats():
    """Get ALL external PR diff stats. Uses search/issues for PR numbers,
    then pulls API for additions/deletions per repo.
    Returns dict: {repo_name: (added, deleted, pr_count)}"""
    # Step 1: Get all closed PRs by user via search/issues (gets PR numbers + repos)
    pr_list = []  # list of (repo, pr_number)
    page = 1
    while True:
        cmd = (
            f'gh api "search/issues?q=type:pr+author:{USERNAME}+is:closed'
            f'&per_page=100&page={page}" --jq \'.items[] | '
            f'{{repo: .repository_url, number}}\' 2>/dev/null'
        )
        out, rc = run(cmd, timeout=120)
        if not out or rc != 0:
            break
        items = []
        for line in out.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if not items:
            break
        for pr in items:
            repo_url = pr.get("repo", "")
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                repo = f"{parts[-2]}/{parts[-1]}"
                if not repo.startswith(f"{USERNAME}/"):
                    pr_list.append((repo, pr.get("number")))
        if len(items) < 100:
            break
        page += 1
        if page > 10:
            break

    print(f"  Found {len(pr_list)} external PRs total", flush=True)

    # Step 2: Group by repo and fetch additions/deletions per PR
    repo_prs = {}
    for repo, num in pr_list:
        if num is None:
            continue
        repo_prs.setdefault(repo, []).append(num)

    stats = {}
    for repo, pr_nums in repo_prs.items():
        added = 0
        deleted = 0
        for num in pr_nums:
            out, rc = run(
                f"gh api repos/{repo}/pulls/{num} --jq '.additions,.deletions' 2>/dev/null",
                timeout=15
            )
            if out:
                lines = out.strip().split("\n")
                if len(lines) >= 2:
                    try:
                        added += int(lines[0].strip())
                        deleted += int(lines[1].strip())
                    except ValueError:
                        pass
        stats[repo] = {"added": added, "deleted": deleted, "count": len(pr_nums)}

    return stats


def count_prs_in_repo(repo):
    """Count PR diff stats via pulls API for external repos."""
    all_prs = []
    for state in ["merged", "open"]:
        out, rc = run(
            f'gh api "search/issues?q=type:pr+author:{USERNAME}+repo:{repo}+is:{state}'
            f'&per_page=100" --jq \'.items[].number\' 2>/dev/null',
            timeout=30
        )
        if out:
            for n in out.split("\n"):
                if n.strip().isdigit():
                    all_prs.append(int(n.strip()))

    if not all_prs:
        return 0, 0, 0

    total_added = 0
    total_deleted = 0
    for num in all_prs:
        out, rc = run(
            f"gh api repos/{repo}/pulls/{num} --jq '{{a:.additions,d:.deletions}}' 2>/dev/null",
            timeout=15
        )
        if out:
            try:
                data = json.loads(out)
                total_added += data.get("a", 0)
                total_deleted += data.get("d", 0)
            except json.JSONDecodeError:
                pass

    return total_added, total_deleted, len(all_prs)


def format_number(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}K"
    else:
        return str(n)


def generate_svg(total_added, total_deleted, repo_count, commit_count):
    added_str = format_number(total_added)
    deleted_str = format_number(total_deleted)
    net = total_added - total_deleted
    net_str = format_number(net)
    commits_str = format_number(commit_count)

    width = 960
    height = 200

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0d1117"/>
      <stop offset="100%" style="stop-color:#161b22"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="{width}" height="{height}" rx="12" fill="url(#bg)" stroke="#30363d" stroke-width="1"/>

  <!-- Title -->
  <text x="30" y="36" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="600">📝 Lifetime Lines of Code</text>
  <text x="{width-30}" y="36" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" text-anchor="end">by @{USERNAME}</text>

  <!-- Lines Added -->
  <rect x="20" y="52" width="300" height="80" rx="8" fill="#0d1117" stroke="#238636" stroke-width="1"/>
  <text x="170" y="75" fill="#3fb950" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" text-anchor="middle" font-weight="500">Lines Added</text>
  <text x="170" y="115" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="34" text-anchor="middle" font-weight="700">{added_str}</text>

  <!-- Lines Removed -->
  <rect x="330" y="52" width="300" height="80" rx="8" fill="#0d1117" stroke="#da3633" stroke-width="1"/>
  <text x="480" y="75" fill="#f85149" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" text-anchor="middle" font-weight="500">Lines Removed</text>
  <text x="480" y="115" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="34" text-anchor="middle" font-weight="700">{deleted_str}</text>

  <!-- Net Lines -->
  <rect x="640" y="52" width="300" height="80" rx="8" fill="#0d1117" stroke="#1f6feb" stroke-width="1"/>
  <text x="790" y="75" fill="#58a6ff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" text-anchor="middle" font-weight="500">Net Lines (Added − Removed)</text>
  <text x="790" y="115" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="34" text-anchor="middle" font-weight="700">{net_str}</text>

  <!-- Footer -->
  <rect x="20" y="142" width="460" height="42" rx="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>
  <text x="250" y="168" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13" text-anchor="middle">
    <tspan fill="#c9d1d9" font-weight="600">{commits_str}</tspan> commits across <tspan fill="#c9d1d9" font-weight="600">{repo_count}</tspan> repositories
  </text>

  <rect x="490" y="142" width="450" height="42" rx="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>
  <text x="715" y="168" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="11" text-anchor="middle">Updated {datetime.now(timezone.utc).strftime("%b %d, %Y")} • All commits by @{USERNAME}</text>
</svg>'''
    return svg


def main():
    print(f"Counting Loc for @{USERNAME} via API (deterministic, no cloning)...", flush=True)

    cache = load_cache()

    total_added = 0
    total_deleted = 0
    total_commits = 0
    repos_with_commits = 0
    repos_failed = 0
    cached_repos_used = 0

    # === Phase 1: Owned repos via stats/contributors API ===
    owned_repos = get_owned_repos()
    print(f"\nPhase 1: Owned repos ({len(owned_repos)} via user/repos?affiliation=owner)", flush=True)

    for i, repo in enumerate(owned_repos):
        print(f"  [own {i+1}/{len(owned_repos)}] {repo}... ", end="", flush=True)
        a, d, c = get_owned_repo_stats(repo)

        if a is None:
            # API failure — use cached value
            cached = cache["repos"].get(repo)
            cached_a = cached.get("added", 0) if cached else 0
            if cached_a > 0:
                a = cached_a
                d = cached.get("deleted", 0) if cached else 0
                c = cached.get("commits", 0) if cached else 0
                cached_repos_used += 1
                print(f"CACHED +{a}/-{d} ({c} commits)", flush=True)
            else:
                repos_failed += 1
                print("FAIL (no cache)", flush=True)
            continue

        # Update cache — enforce monotonic: never decrease a repo's LOC
        cached = cache["repos"].get(repo, {})
        cached_a = cached.get("added", 0) if cached else 0
        cached_d = cached.get("deleted", 0) if cached else 0
        cached_c = cached.get("commits", 0) if cached else 0
        # Use max of cached vs fresh API result to prevent GitHub's lazy
        # stats recomputation from producing lower numbers on different runs
        final_a = max(a, cached_a)
        final_d = max(d, cached_d)
        final_c = max(c, cached_c)

        cache["repos"][repo] = {
            "added": final_a, "deleted": final_d, "commits": final_c,
            "type": "owned",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

        if final_a > 0 or final_d > 0 or final_c > 0:
            total_added += final_a
            total_deleted += final_d
            total_commits += final_c
            repos_with_commits += 1
            print(f"+{final_a}/-{final_d} ({final_c} commits)", flush=True)
        else:
            print("no commits", flush=True)

    # === Phase 2: External repos via PR diff API (single batch call) ===
    print(f"\nPhase 2: External repos (single batch via gh search prs)", flush=True)
    ext_stats = get_external_repos_stats()
    print(f"  Found {len(ext_stats)} external repos with PRs", flush=True)

    for i, repo in enumerate(sorted(ext_stats.keys())):
        s = ext_stats[repo]
        a = s["added"]
        d = s["deleted"]
        c = s["count"]
        print(f"  [ext {i+1}/{len(ext_stats)}] {repo}... +{a}/-{d} ({c} PRs)", flush=True)

        total_added += a
        total_deleted += d
        total_commits += c
        repos_with_commits += 1
        cache["repos"][repo] = {
            "added": a, "deleted": d, "commits": c,
            "type": "external",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    # Check cache for external repos not found this run (API failure/rate limit)
    for repo, cached in cache["repos"].items():
        if cached.get("type") == "external" and repo not in ext_stats:
            a = cached.get("added", 0)
            d = cached.get("deleted", 0)
            c = cached.get("commits", 0)
            if a > 0 or c > 0:
                total_added += a
                total_deleted += d
                total_commits += c
                repos_with_commits += 1
                cached_repos_used += 1
                print(f"  [cache] {repo}... +{a}/-{d} ({c} PRs)", flush=True)

    # === Summary ===
    net = total_added - total_deleted
    print(f"\n{'='*60}", flush=True)
    print(f"TOTAL: +{total_added:,} / -{total_deleted:,} / net {net:,}", flush=True)
    print(f"Across {repos_with_commits} repos, {total_commits} commits/PRs", flush=True)
    print(f"Cache: {cached_repos_used} repos used cached values, {repos_failed} failed", flush=True)
    print(f"{'='*60}", flush=True)

    # Save cache with lifetime totals
    cache["lifetime_total"] = {
        "added": total_added,
        "deleted": total_deleted,
        "commits": total_commits,
        "net": net,
        "repos_with_commits": repos_with_commits
    }
    save_cache(cache)
    print(f"Cache → {CACHE_FILE}", flush=True)

    # Generate SVG
    svg = generate_svg(total_added, total_deleted, repos_with_commits, total_commits)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    svg_path = os.path.join(OUTPUT_DIR, "loc-stats.svg")
    with open(svg_path, "w") as f:
        f.write(svg)
    print(f"SVG → {svg_path}", flush=True)

    json_path = os.path.join(OUTPUT_DIR, "loc-stats.json")
    with open(json_path, "w") as f:
        json.dump({
            "username": USERNAME,
            "emails_matched": EMAILS,
            "total_added": total_added,
            "total_deleted": total_deleted,
            "net_lines": net,
            "total_commits": total_commits,
            "repos_with_commits": repos_with_commits,
            "repos_failed": repos_failed,
            "cached_repos_used": cached_repos_used,
            "method": "api_stats_contributors",
            "updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)
    print(f"JSON → {json_path}", flush=True)


if __name__ == "__main__":
    main()
