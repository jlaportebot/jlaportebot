<img src="./gh-activity-chart.svg" alt="GitHub Activity Chart" width="960"/>

**What this tracks:** Cumulative counts over time
- 🟠 **Repos** — all public repos (owned + forks)
- 🔵 **PRs Opened** — total pull requests submitted
- 🟢 **Open PRs** — currently awaiting review
- 🟣 **Merged** — successfully merged PRs
- 🔴 **Closed** — PRs closed without merge

Auto-updated daily.

---

<img src="./loc-stats.svg" alt="Lifetime Lines of Code" width="960"/>

**What this tracks:** Total lines of code committed across all repositories
- 🟢 **Lines Added** — all insertions across every commit
- 🔴 **Lines Removed** — all deletions across every commit
- 🔵 **Net Lines** — added minus removed (actual code standing)

Updated daily via GitHub Actions. Counts only commits by @jlaportebot.

---

<img src="./token-stats.svg" alt="Lifetime Token Consumption" width="960"/>

**What this tracks:** Total LLM tokens consumed across all Hermes Agent sessions
- 🟣 **Total Tokens** — lifetime cumulative (input + output + cache, never resets)

**Lifetime Total:** 8,245,465,299 tokens (from 2,090 sessions)

Updated daily via cron job. Tracks all sessions in state.db.