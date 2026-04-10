import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict

TOKEN = os.environ["STATS_TOKEN"]
USERNAME = "limmen20"
HEADERS = {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"}

# ── GraphQL query ──────────────────────────────────────────────────────────────

QUERY = """
query($username: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $username) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: BOTH) {
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
"""

def fetch():
    now = datetime.utcnow()
    one_year_ago = now - timedelta(days=365)
    variables = {
        "username": USERNAME,
        "from": one_year_ago.strftime("%Y-%m-%dT00:00:00Z"),
        "to": now.strftime("%Y-%m-%dT23:59:59Z"),
    }
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": QUERY, "variables": variables},
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()["data"]["user"]

def process(data):
    cc = data["contributionsCollection"]
    total_commits = cc["totalCommitContributions"]

    # contribution heatmap grid (last 52 weeks)
    weeks = cc["contributionCalendar"]["weeks"]
    heatmap = []
    for week in weeks:
        row = []
        for day in week["contributionDays"]:
            row.append(day["contributionCount"])
        heatmap.append(row)

    # language sizes
    lang_sizes = defaultdict(int)
    lang_colors = {}
    for repo in data["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_sizes[name] += edge["size"]
            lang_colors[name] = edge["node"]["color"] or "#888"

    total_size = sum(lang_sizes.values()) or 1
    languages = sorted(lang_sizes.items(), key=lambda x: x[1], reverse=True)[:6]
    lang_pcts = [(name, round(size / total_size * 100, 1), lang_colors[name]) for name, size in languages]

    return total_commits, lang_pcts, heatmap

# ── SVG generation ─────────────────────────────────────────────────────────────

def heat_color(count, max_count):
    if count == 0:
        return "#161b22"
    ratio = count / max(max_count, 1)
    if ratio < 0.25:  return "#0e4429"
    if ratio < 0.5:   return "#006d32"
    if ratio < 0.75:  return "#26a641"
    return "#39d353"

def generate_svg(total_commits, lang_pcts, heatmap):
    W, H = 480, 310
    BG       = "#0d1117"
    FG       = "#e6edf3"
    MUTED    = "#8b949e"
    BORDER   = "#30363d"
    ACCENT   = "#39d353"

    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    lines.append(f'<rect width="{W}" height="{H}" fill="{BG}" rx="12"/>')

    # ── border ──
    lines.append(f'<rect width="{W}" height="{H}" fill="none" stroke="{BORDER}" stroke-width="1" rx="12"/>')

    # ── total commits ──
    lines.append(f'<text x="24" y="44" font-family="monospace" font-size="11" fill="{MUTED}">total commits</text>')
    lines.append(f'<text x="24" y="76" font-family="monospace" font-size="32" font-weight="bold" fill="{FG}">{total_commits:,}</text>')
    lines.append(f'<line x1="24" y1="92" x2="{W-24}" y2="92" stroke="{BORDER}" stroke-width="1"/>')

    # ── language bars ──
    lines.append(f'<text x="24" y="114" font-family="monospace" font-size="11" fill="{MUTED}">languages</text>')

    bar_x = 24
    bar_y = 124
    bar_h = 6
    bar_w = W - 48
    cursor = bar_x

    # segmented bar
    for name, pct, color in lang_pcts:
        seg_w = bar_w * pct / 100
        lines.append(f'<rect x="{cursor:.1f}" y="{bar_y}" width="{seg_w:.1f}" height="{bar_h}" fill="{color}" rx="0"/>')
        cursor += seg_w

    # round ends
    lines.append(f'<rect x="{bar_x}" y="{bar_y}" width="4" height="{bar_h}" fill="{lang_pcts[0][2]}" rx="3"/>')
    lines.append(f'<rect x="{bar_x+bar_w-4:.1f}" y="{bar_y}" width="4" height="{bar_h}" fill="{lang_pcts[-1][2]}" rx="3"/>')

    # legend
    leg_y = bar_y + 22
    leg_x = bar_x
    for i, (name, pct, color) in enumerate(lang_pcts):
        if i == 3:
            leg_x = bar_x
            leg_y += 18
        lines.append(f'<circle cx="{leg_x+5}" cy="{leg_y+4}" r="4" fill="{color}"/>')
        lines.append(f'<text x="{leg_x+14}" y="{leg_y+8}" font-family="monospace" font-size="11" fill="{FG}">{name}</text>')
        lines.append(f'<text x="{leg_x+14+len(name)*7}" y="{leg_y+8}" font-family="monospace" font-size="11" fill="{MUTED}"> {pct}%</text>')
        leg_x += 155 if i < 2 else 155

    lines.append(f'<line x1="24" y1="186" x2="{W-24}" y2="186" stroke="{BORDER}" stroke-width="1"/>')

    # ── heatmap ──
    lines.append(f'<text x="24" y="204" font-family="monospace" font-size="11" fill="{MUTED}">contributions — last 12 months</text>')

    all_counts = [c for week in heatmap for c in week]
    max_count = max(all_counts) if all_counts else 1

    cell = 7
    gap = 2
    hm_x = 24
    hm_y = 214

    for wi, week in enumerate(heatmap):
        for di, count in enumerate(week):
            cx = hm_x + wi * (cell + gap)
            cy = hm_y + di * (cell + gap)
            color = heat_color(count, max_count)
            lines.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" fill="{color}" rx="2"/>')

    # legend scale
    scale_x = W - 24 - 5 * (cell + gap)
    scale_y = H - 18
    lines.append(f'<text x="{scale_x - 28}" y="{scale_y + 6}" font-family="monospace" font-size="9" fill="{MUTED}">less</text>')
    for i, col in enumerate(["#161b22","#0e4429","#006d32","#26a641","#39d353"]):
        lines.append(f'<rect x="{scale_x + i*(cell+gap)}" y="{scale_y}" width="{cell}" height="{cell}" fill="{col}" rx="2"/>')
    lines.append(f'<text x="{scale_x + 5*(cell+gap) + 2}" y="{scale_y + 6}" font-family="monospace" font-size="9" fill="{MUTED}">more</text>')

    lines.append('</svg>')
    return "\n".join(lines)

# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching GitHub data...")
    data = fetch()
    total_commits, lang_pcts, heatmap = process(data)
    print(f"Commits: {total_commits}")
    print(f"Languages: {lang_pcts}")
    svg = generate_svg(total_commits, lang_pcts, heatmap)
    with open("stats.svg", "w") as f:
        f.write(svg)
    print("stats.svg written.")
