#!/usr/bin/env python3
"""
Count total lines of code committed by a GitHub user across all their repos
AND repos they've contributed to via PRs.

Uses the GitHub API search + commit stats for accuracy.
Outputs an SVG badge and a JSON stats file.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "jlaportebot")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", 1


def api_get(path, paginate=False):
    """Make a GitHub API call, optionally paginating."""
    if paginate:
        out, rc = run(f"gh api '{path}' --paginate --jq '.[]' 2>/dev/null", timeout=120)
        if not out:
            return []
        # Each line is a separate JSON object from --jq
        results = []
        for line in out.split("\n"):
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return results
    else:
        out, rc = run(f"gh api '{path}' 2>/dev/null", timeout=30)
        if not out or rc != 0:
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None


def count_loc_for_pr(repo, pr_number):
    """Get lines added/removed for a specific PR."""
    data = api_get(f"repos/{repo}/pulls/{pr_number}")
    if not data:
        return 0, 0
    
    additions = data.get("additions", 0)
    deletions = data.get("deletions", 0)
    return additions, deletions


def get_all_prs():
    """Find all PRs (merged + open) authored by this user across all repos."""
    all_prs = []
    for state in ("merged", "open"):
        page = 1
        while True:
            q = f"type:pr+author:{USERNAME}+is:{state}"
            out, rc = run(
                f'gh api "search/issues?q={q}&per_page=100&page={page}" '
                f'--jq \'.items[] | {{repo: .repository_url, number: .number, title: .title, state: "{state}"}}\' 2>/dev/null',
                timeout=60
            )
            if not out or rc != 0:
                break
            items = []
            for line in out.split("\n"):
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            if not items:
                break
            all_prs.extend(items)
            if len(items) < 100:
                break
            page += 1
    return all_prs


def format_number(n):
    """Format large numbers with K/M suffixes."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}K"
    else:
        return str(n)


def generate_svg(total_added, total_deleted, pr_count):
    """Generate an SVG badge showing lines of code stats."""
    added_str = format_number(total_added)
    deleted_str = format_number(total_deleted)
    net = total_added - total_deleted
    net_str = format_number(net)
    
    width = 900
    height = 180
    
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
  <text x="30" y="38" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="600">📝 Lifetime Lines of Code</text>
  <text x="{width-30}" y="38" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" text-anchor="end">by @{USERNAME}</text>
  
  <!-- Lines Added -->
  <rect x="30" y="58" width="250" height="90" rx="8" fill="#0d1117" stroke="#238636" stroke-width="1"/>
  <text x="155" y="85" fill="#3fb950" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13" text-anchor="middle" font-weight="500">Lines Added</text>
  <text x="155" y="125" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="36" text-anchor="middle" font-weight="700">{added_str}</text>
  
  <!-- Lines Removed -->
  <rect x="300" y="58" width="250" height="90" rx="8" fill="#0d1117" stroke="#da3633" stroke-width="1"/>
  <text x="425" y="85" fill="#f85149" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13" text-anchor="middle" font-weight="500">Lines Removed</text>
  <text x="425" y="125" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="36" text-anchor="middle" font-weight="700">{deleted_str}</text>
  
  <!-- Net Lines -->
  <rect x="570" y="58" width="300" height="90" rx="8" fill="#0d1117" stroke="#1f6feb" stroke-width="1"/>
  <text x="720" y="85" fill="#58a6ff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13" text-anchor="middle" font-weight="500">Net Lines (Added − Removed)</text>
  <text x="720" y="125" fill="#f0f6fc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="36" text-anchor="middle" font-weight="700">{net_str}</text>
  
  <!-- Footer -->
  <text x="30" y="168" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="11">Across {pr_count} merged pull requests • Updated {datetime.now(timezone.utc).strftime("%b %d, %Y")}</text>
</svg>'''
    return svg


def main():
    print(f"Counting LOC for @{USERNAME} across all merged PRs...")
    
    # Step 1: Find all PRs (merged + open)
    prs = get_all_prs()
    print(f"Found {len(prs)} merged PRs")
    
    if not prs:
        print("No merged PRs found!")
        total_added = 0
        total_deleted = 0
        pr_count = 0
    else:
        total_added = 0
        total_deleted = 0
        pr_count = 0
        
        for i, pr in enumerate(prs):
            repo_url = pr.get("repo", "")
            # Extract repo from URL like "https://api.github.com/repos/owner/repo"
            repo = "/".join(repo_url.rstrip("/").split("/")[-2:])
            number = pr.get("number")
            title = pr.get("title", "")[:50]
            
            if not repo or not number:
                continue
            
            print(f"  [{i+1}/{len(prs)}] {repo}#{number}: {title}...", end=" ", flush=True)
            a, d = count_loc_for_pr(repo, number)
            if a > 0 or d > 0:
                total_added += a
                total_deleted += d
                pr_count += 1
                print(f"+{a}/-{d}")
            else:
                print("skip")
    
    print(f"\n=== TOTAL: +{total_added} / -{total_deleted} / net {total_added - total_deleted} across {pr_count} PRs ===")
    
    # Generate SVG
    svg = generate_svg(total_added, total_deleted, pr_count)
    
    # Write outputs
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
            "merged_prs": pr_count,
            "updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)
    print(f"JSON written to {json_path}")


if __name__ == "__main__":
    main()
