#!/usr/bin/env python3
"""
Count total lines of code committed by a GitHub user across ALL their repos.

Strategy:
1. ALL repos (owned + forks): blobless clone (--filter=blob:none) + all branches
   Count every commit matching user's email(s)
2. For fork upstreams where the fork had 0 local commits: count PR diff stats via API
3. For external contributed repos (no fork/own): count PR diff stats via API
4. NO double counting
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "jlaportebot")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")

EMAILS = [
    f"{USERNAME}@gmail.com",
    f"{USERNAME}@users.noreply.github.com",
]

GH_TOKEN = os.environ.get("GH_TOKEN")


def run(cmd, timeout=300):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", 1


# Repos known to be too large for full history traversal (skip clone, use API only)
SKIP_CLONE_REPOS = {
    "google/go-github",                    # upstream of jlaportebot/go-github
    "sphinx-doc/sphinx",                   # upstream of jlaportebot/sphinx (large)
    "Lightning-AI/torchmetrics",           # upstream of jlaportebot/torchmetrics
    "apache/airflow",                      # upstream of jlaportebot/airflow (641MB - huge)
    "microsoft/agent-governance-toolkit",  # upstream of jlaportebot/agent-governance-toolkit (40MB)
    "Automattic/harper",                   # upstream of jlaportebot/harper (41MB)
}

# Owned repos too large for full history traversal (skip clone, use API only)
SKIP_OWNED_REPOS = {
    "jlaportebot/qemu",                    # 373MB - too large for blobless clone
}


def gh_auth_login():
    """Authenticate gh CLI with GH_TOKEN if available."""
    if not GH_TOKEN:
        return
    # Write token to temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(GH_TOKEN)
        token_file = f.name
    try:
        out, rc = run(f"gh auth login --with-token < {token_file} 2>/dev/null", timeout=10)
    finally:
        os.unlink(token_file)
    if rc != 0:
        print("Warning: gh auth login failed, proceeding anyway", flush=True)


def get_all_repos():
    # Use double quotes with escaped ampersands to avoid shell quoting issues
    out, rc = run("gh api \"user/repos?per_page=100\\&visibility=all\\&affiliation=owner\" --paginate 2>/dev/null", timeout=120)
    if not out:
        return []
    try:
        repos = json.loads(out)
    except json.JSONDecodeError:
        return []
    return [{"name": r["full_name"], "fork": r.get("fork", False)} for r in repos]


def get_fork_sources(fork_repos):
    sources = {}
    for fork in fork_repos:
        out, rc = run(f"gh api repos/{fork} --jq '.source.full_name' 2>/dev/null", timeout=15)
        if out and out != "null":
            sources[fork] = out.strip()
    return sources


def get_contributed_repos():
    """Find external repos where user has PRs (not owned, not forked)."""
    all_repos = set()
    # Use gh search prs (not the deprecated search/issues endpoint)
    # state=closed includes both merged and closed-without-merge
    out, rc = run(
        f"gh search prs --author={USERNAME} --state=closed --limit 1000 "
        f"--json url --jq '.[].url' 2>/dev/null",
        timeout=120
    )
    if not out or rc != 0:
        return []
    for line in out.split("\n"):
        line = line.strip()
        # PR URLs: https://github.com/owner/repo/pull/123
        parts = line.split("/")
        if len(parts) >= 5 and "github.com" in line:
            repo = f"{parts[3]}/{parts[4]}"
            all_repos.add(repo)
    return list(all_repos)


def count_loc_via_clone(repo_full_name, tmpdir):
    repo_dir = os.path.join(tmpdir, repo_full_name.replace("/", "_"))
    clone_cmd = (
        f"git clone --filter=blob:none --no-single-branch "
        f"https://github.com/{repo_full_name}.git {repo_dir} 2>/dev/null"
    )
    out, rc = run(clone_cmd, timeout=120)
    if rc != 0:
        return 0, 0, 0

    author_args = " ".join(f"--author='{e}'" for e in EMAILS)

    out, rc = run(
        f"cd {repo_dir} && git log --all {author_args} --shortstat --format='' 2>/dev/null",
        timeout=60
    )
    count_out, _ = run(
        f"cd {repo_dir} && git log --all {author_args} --oneline 2>/dev/null | wc -l",
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
    all_prs = []
    for state in ["merged", "open"]:
        out, rc = run(
            f'gh api "search/issues?q=type:pr+author:{username}+repo:{repo_full_name}+is:{state}&per_page=100" '
            f"--jq '.items[].number' 2>/dev/null",
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
            f"gh api repos/{repo_full_name}/pulls/{num} --jq '{{a:.additions,d:.deletions}}' 2>/dev/null",
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
    print(f"Counting LOC for @{USERNAME} across all repos...", flush=True)

    # Authenticate gh CLI with GITHUB_TOKEN if available
    gh_auth_login()

    all_repos = get_all_repos()
    own_repos = [r["name"] for r in all_repos if not r.get("fork")]
    fork_repos = [r["name"] for r in all_repos if r.get("fork")]

    print(f"Resolving fork sources for {len(fork_repos)} forks...", flush=True)
    fork_sources = get_fork_sources(fork_repos)

    print(f"Own repos: {len(own_repos)}, Forks: {len(fork_repos)}", flush=True)

    total_added = 0
    total_deleted = 0
    total_commits = 0
    repos_with_commits = 0
    forks_with_commits = set()
    forks_no_commits = set()

    # Phase 1: Clone ALL repos and count every commit
    all_clone_repos = own_repos + fork_repos

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, repo in enumerate(all_clone_repos):
            is_fork = repo in fork_repos
            label = "fork" if is_fork else "own"
            print(f"  [{label} {i+1}/{len(all_clone_repos)}] {repo}...", end=" ", flush=True)

            # Skip cloning for known-large repos (use API fallback instead)
            skip_clone = False
            if is_fork and repo in fork_sources:
                if fork_sources[repo] in SKIP_CLONE_REPOS:
                    skip_clone = True
            elif not is_fork:
                if repo in SKIP_CLONE_REPOS or repo in SKIP_OWNED_REPOS:
                    skip_clone = True

            if skip_clone:
                print("skipped (too large for clone)", flush=True)
                continue

            a, d, c = count_loc_via_clone(repo, tmpdir)
            if a > 0 or d > 0 or c > 0:
                total_added += a
                total_deleted += d
                total_commits += c
                repos_with_commits += 1
                if is_fork:
                    forks_with_commits.add(repo)
                print(f"+{a}/-{d} ({c} commits)", flush=True)
            else:
                if is_fork:
                    forks_no_commits.add(repo)
                print("no commits", flush=True)

    # Phase 2: API PR counting for:
    # a) Fork upstreams where the fork had 0 commits (pristine forks)
    # b) External repos with no fork/own
    own_set = set(own_repos)
    fork_set = set(fork_repos)

    api_repos = set()

    # a) Upstreams of forks with no commits
    for fork in forks_no_commits:
        if fork in fork_sources:
            api_repos.add(fork_sources[fork])

    # b) Upstreams of forks we skipped due to size
    for fork in fork_repos:
        if fork in fork_sources and fork_sources[fork] in SKIP_CLONE_REPOS:
            api_repos.add(fork_sources[fork])

    # c) Owned repos we skipped due to size
    for repo in own_repos:
        if repo in SKIP_OWNED_REPOS:
            api_repos.add(repo)

    # d) External contributed repos
    contributed = get_contributed_repos()
    fork_source_set = set(fork_sources.values())
    for repo in contributed:
        if repo not in own_set and repo not in fork_set and repo not in fork_source_set:
            api_repos.add(repo)

    api_list = sorted(api_repos)
    print(f"\nAPI repos (pristine forks + skipped forks + external): {len(api_list)}", flush=True)

    for i, repo in enumerate(api_list):
        print(f"  [api {i+1}/{len(api_list)}] {repo}...", end=" ", flush=True)
        a, d, c = count_prs_in_repo(repo, USERNAME)
        if a > 0 or d > 0 or c > 0:
            total_added += a
            total_deleted += d
            total_commits += c
            repos_with_commits += 1
            print(f"+{a}/-{d} ({c} PRs)", flush=True)
        else:
            print("skip", flush=True)

    net = total_added - total_deleted
    print(f"\n{'='*60}", flush=True)
    print(f"TOTAL: +{total_added:,} / -{total_deleted:,} / net {net:,}", flush=True)
    print(f"Across {repos_with_commits} repos, {total_commits} commits/PRs", flush=True)
    print(f"{'='*60}", flush=True)

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
            "updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)
    print(f"JSON → {json_path}", flush=True)


if __name__ == "__main__":
    main()