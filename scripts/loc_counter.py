#!/usr/bin/env python3
"""
Count total lines of code committed by a GitHub user across ALL their repos.

Strategy:
1. For repos the user OWNS (non-fork): clone and `git log --shortstat`
2. For forks: look up the upstream source repo, then check PRs there
3. For external contributed repos: check PRs via API
4. Merge all counts and generate an SVG badge
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "jlaportebot")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")
FORK_SOURCES_FILE = os.environ.get("FORK_SOURCES_FILE", "")


def run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", 1


def api_get_json(url, timeout=30):
    out, rc = run(f"gh api '{url}' 2>/dev/null", timeout=timeout)
    if not out or rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def get_owned_repos():
    """Get all repos with fork flag."""
    out, rc = run(
        f"gh api users/{USERNAME}/repos --paginate "
        f"--jq '.[] | {{name: .full_name, fork: .fork}}' 2>/dev/null",
        timeout=120
    )
    if not out:
        return []
    repos = []
    for line in out.split("\n"):
        line = line.strip()
        if line:
            try:
                repos.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return repos


def get_fork_sources(fork_repos):
    """For each fork, find the upstream source repo."""
    sources = {}
    for fork in fork_repos:
        out, rc = run(f"gh api repos/{fork} --jq '.source.full_name' 2>/dev/null", timeout=15)
        if out and out != "null":
            sources[fork] = out.strip()
    return sources


def get_contributed_repos():
    """Find repos where user has merged PRs that they don't own."""
    all_repos = set()
    page = 1
    while True:
        out, rc = run(
            f'gh api "search/issues?q=type:pr+author:{USERNAME}+is:merged&per_page=100&page={page}" '
            f"--jq '.items[].repository_url' 2>/dev/null",
            timeout=60
        )
        if not out or rc != 0:
            break
        found = False
        for line in out.split("\n"):
            line = line.strip()
            if line and "/repos/" in line:
                repo = line.split("/repos/")[-1].strip("/")
                all_repos.add(repo)
                found = True
        if not found or page > 5:
            break
        page += 1
    return list(all_repos)


def count_loc_via_clone(repo_full_name, username, tmpdir):
    """Clone and count via git log --shortstat."""
    repo_dir = os.path.join(tmpdir, repo_full_name.replace("/", "_"))
    out, rc = run(
        f"git clone --depth=1000 --single-branch https://github.com/{repo_full_name}.git {repo_dir} 2>/dev/null",
        timeout=120
    )
    if rc != 0:
        return 0, 0, 0
    
    out, rc = run(
        f"cd {repo_dir} && git log --author='{username}' --shortstat --format='' 2>/dev/null",
        timeout=60
    )
    count_out, _ = run(
        f"cd {repo_dir} && git log --author='{username}' --oneline 2>/dev/null | wc -l",
        timeout=30
    )
    commit_count = 0
    try:
        commit_count = int(count_out.strip())
    except ValueError:
        pass
    
    added = 0
    deleted = 0
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        for part in parts:
            part = part.strip()
            if "insertion" in part:
                try:
                    added += int(part.split()[0])
                except (ValueError, IndexError):
                    pass
            elif "deletion" in part:
                try:
                    deleted += int(part.split()[0])
                except (ValueError, IndexError):
                    pass
    
    return added, deleted, commit_count


def count_prs_in_repo(repo_full_name, username):
    """Count lines from PRs by user in a repo via GitHub API."""
    # Use search to find PRs by this user in this repo
    out, rc = run(
        f'gh api "search/issues?q=type:pr+author:{username}+repo:{repo_full_name}&per_page=100" '
        f"--jq '.items[].number' 2>/dev/null",
        timeout=30
    )
    if not out:
        return 0, 0, 0
    
    pr_numbers = [n for n in out.split("\n") if n.strip().isdigit()]
    if not pr_numbers:
        return 0, 0, 0
    
    total_added = 0
    total_deleted = 0
    
    for num in pr_numbers:
        data = api_get_json(f"repos/{repo_full_name}/pulls/{num}")
        if data:
            total_added += data.get("additions", 0)
            total_deleted += data.get("deletions", 0)
    
    return total_added, total_deleted, len(pr_numbers)


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
  
  <!-- Footer row -->
  <rect x="20" y="142" width="460" height="42" rx="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>
  <text x="250" y="168" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13" text-anchor="middle">
    <tspan fill="#c9d1d9" font-weight="600">{commits_str}</tspan> commits across <tspan fill="#c9d1d9" font-weight="600">{repo_count}</tspan> repositories
  </text>
  
  <rect x="490" y="142" width="450" height="42" rx="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>
  <text x="715" y="168" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="11" text-anchor="middle">Updated {datetime.now(timezone.utc).strftime("%b %d, %Y")} • All commits by @{USERNAME}</text>
</svg>'''
    return svg


def main():
    print(f"Counting LOC for @{USERNAME} across all repos...")
    
    owned = get_owned_repos()
    own_repos = [r["name"] for r in owned if not r.get("fork")]
    fork_repos = [r["name"] for r in owned if r.get("fork")]
    
    # Map forks to their upstream source repos
    print(f"Resolving fork sources for {len(fork_repos)} forks...")
    fork_sources = get_fork_sources(fork_repos)
    
    # Get external contributed repos (from search)
    contributed = get_contributed_repos()
    
    # Build the set of upstream repos to check via API
    # These are: fork source repos + external contributed repos
    # Deduplicate against own_repos (we already cloned those)
    own_set = set(own_repos)
    api_repos = set()
    for source in fork_sources.values():
        if source not in own_set:
            api_repos.add(source)
    for repo in contributed:
        if repo not in own_set:
            api_repos.add(repo)
    # Remove any that are already in fork_sources values (dedup)
    
    print(f"Own repos (clone): {len(own_repos)}")
    print(f"Fork upstream repos (API): {len(set(fork_sources.values()))}")
    print(f"External contributed repos (API): {len(api_repos - set(fork_sources.values()))}")
    print(f"Total API repos: {len(api_repos)}")
    
    total_added = 0
    total_deleted = 0
    total_commits = 0
    processed = 0
    
    # Phase 1: Clone own repos
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, repo in enumerate(own_repos):
            print(f"  [clone {i+1}/{len(own_repos)}] {repo}...", end=" ", flush=True)
            a, d, c = count_loc_via_clone(repo, USERNAME, tmpdir)
            if a > 0 or d > 0 or c > 0:
                total_added += a
                total_deleted += d
                total_commits += c
                processed += 1
                print(f"+{a}/-{d} ({c} commits)")
            else:
                print("skip")
    
    # Phase 2: Check upstream repos for PRs
    api_list = sorted(api_repos)
    for i, repo in enumerate(api_list):
        print(f"  [api {i+1}/{len(api_list)}] {repo}...", end=" ", flush=True)
        a, d, c = count_prs_in_repo(repo, USERNAME)
        if a > 0 or d > 0 or c > 0:
            total_added += a
            total_deleted += d
            total_commits += c
            processed += 1
            print(f"+{a}/-{d} ({c} PRs)")
        else:
            print("skip")
    
    print(f"\n=== TOTAL: +{total_added} / -{total_deleted} / net {total_added - total_deleted} across {processed} repos ({total_commits} commits/PRs) ===")
    
    svg = generate_svg(total_added, total_deleted, processed, total_commits)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    svg_path = os.path.join(OUTPUT_DIR, "loc-stats.svg")
    with open(svg_path, "w") as f:
        f.write(svg)
    print(f"SVG written to {svg_path}")
    
    json_path = os.path.join(OUTPUT_DIR, "loc-stats.json")
    with open(json_path, "w") as f:
        json.dump({
            "username": USERNAME,
            "total_added": total_added,
            "total_deleted": total_deleted,
            "net_lines": total_added - total_deleted,
            "total_commits": total_commits,
            "repos_processed": processed,
            "updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)
    print(f"JSON written to {json_path}")


if __name__ == "__main__":
    main()
