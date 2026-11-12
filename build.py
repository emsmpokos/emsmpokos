#!/usr/bin/env python3
"""Generate dark.svg / light.svg profile cards from config.json.

Usage:
    python3 build.py            # use numbers from config.json
    python3 build.py --fetch    # pull stats from the GitHub API first
                                # (set GITHUB_TOKEN to also get total contributions)
"""
import json
import math
import os
import random
import sys
import urllib.request
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
COLS = 58            # characters per info line
CW = 8.4             # approx monospace char width at 14px
LH = 22              # line height
FS = 14

THEMES = {
    "dark": dict(bg="#0b0e1a", border="#252a41", text="#c9d1e6", key="#5eead4",
                 val="#f0abfc", head="#fbbf24", dots="#3a4060", prompt="#86efac",
                 star="#fde68a", glow="#f59e0b", d1="#fb923c", d2="#c084fc", d3="#7c86b8",
                 bg_star="#56608f"),
    "light": dict(bg="#fbfbfd", border="#dcdfeb", text="#2b2f45", key="#0f766e",
                  val="#9d174d", head="#b45309", dots="#c3c8db", prompt="#15803d",
                  star="#d97706", glow="#ea580c", d1="#c2410c", d2="#7e22ce", d3="#6470a8",
                  bg_star="#a7aecb"),
}


def make_art(W=41, H=27, seed=11):
    """A star with a tilted debris disk, built only from keyboard characters.
    Returns rows of (char, role) cells."""
    rng = random.Random(seed)
    cx, cy = (W - 1) / 2, (H - 1) / 2
    aspect = 2.6                      # row height / char width
    tilt, flat = -0.32, 0.68          # disk rotation (rad) and flattening
    ct, st = math.cos(tilt), math.sin(tilt)
    r_in, r_out = 12.0, 21.0
    grid = [[(" ", None) for _ in range(W)] for _ in range(H)]

    for r in range(H):
        for c in range(W):
            x, y = c - cx, (r - cy) * aspect
            d = math.hypot(x, y)
            xr, yr = x * ct + y * st, -x * st + y * ct
            rho = math.hypot(xr, yr / flat)

            if d <= 3.9:
                grid[r][c] = ("@", "star")
            elif d <= 6.3:
                grid[r][c] = ("O" if d <= 5.2 else "o", "glow")
            elif r_in <= rho <= r_out:
                t = (rho - r_in) / (r_out - r_in)
                if rng.random() < 0.97 - 0.55 * t:
                    ramp = "#%+=:."
                    ch = ramp[min(int(t * len(ramp)), len(ramp) - 1)]
                    role = "d1" if t < 0.33 else "d2" if t < 0.66 else "d3"
                    grid[r][c] = (ch, role)
            elif r_out < rho <= r_out * 1.35:
                if rng.random() < 0.05:
                    grid[r][c] = (rng.choice(".,'"), "d3")
            elif rng.random() < 0.012 and d > 5:
                grid[r][c] = (rng.choice(".+*'"), "bg_star")

    # diffraction spikes
    for k in range(8, 11):
        for sx in (-1, 1):
            c = int(round(cx + sx * k))
            if 0 <= c < W and grid[int(cy)][c][0] == " ":
                grid[int(cy)][c] = ("-", "glow")
    for dr in (-5, -4, 4, 5):
        r = int(cy) + dr
        if 0 <= r < H and grid[r][int(cx)][0] == " ":
            grid[r][int(cx)] = ("|", "glow")
    return grid


ART = make_art()


def fetch_stats(user, stats):
    token = os.environ.get("GITHUB_TOKEN")

    def get(url, data=None):
        req = urllib.request.Request(url, data=data)
        req.add_header("Accept", "application/vnd.github+json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    u = get(f"https://api.github.com/users/{user}")
    stats["repos"] = str(u["public_repos"])
    stars, page = 0, 1
    while True:
        repos = get(f"https://api.github.com/users/{user}/repos?per_page=100&page={page}")
        if not repos:
            break
        stars += sum(r["stargazers_count"] for r in repos)
        page += 1
    stats["stars"] = str(stars)
    try:
        c = get(f"https://api.github.com/search/commits?q=author:{user}&per_page=1")
        stats["commits"] = f"{c['total_count']:,}"
    except Exception as e:
        print("commit count skipped:", e)
    if token:
        q = json.dumps({"query": 'query { user(login: "%s") { contributionsCollection '
                        '{ contributionCalendar { totalContributions } } } }' % user}).encode()
        g = get("https://api.github.com/graphql", q)
        stats["contributions"] = f"{g['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']:,}"
    else:
        print("set GITHUB_TOKEN to fetch total contributions")


def build_lines(cfg):
    lines = []
    lines.append([(f"{cfg['prompt_user']}@{cfg['prompt_host']}", "prompt"), (" ~ $ ", "text"),
                  (cfg.get("command", "neofetch"), "val")])
    lines.append([])
    sections = list(cfg["sections"])
    s = cfg["stats"]
    sections.append({"title": "github stats", "rows": [
        ["repos", s["repos"]], ["stars", s["stars"]],
        ["commits", s["commits"]], ["total contributions", s["contributions"]]]})
    for sec in sections:
        title = f" {sec['title']} "
        lines.append([("╭─", "dots"), (title, "head"), ("─" * (COLS - 2 - len(title)), "dots")])
        for key, val in sec["rows"]:
            dots = max(COLS - 2 - len(key) - len(val) - 2, 2)
            lines.append([("│ ", "dots"), (key, "key"), (" " + "·" * dots + " ", "dots"), (val, "val")])
        lines.append([])
    lines.pop()
    return lines


def render(cfg, name, t):
    lines = build_lines(cfg)
    pad_x, pad_y = 32, 40
    art_w, art_h = len(ART[0]), len(ART)
    art_x = pad_x + COLS * CW + 36
    width = int(art_x + art_w * CW + pad_x)
    height = int(pad_y * 2 + len(lines) * LH)
    art_top = pad_y + 14 + max(0, (len(lines) - art_h) // 2 + 1) * LH
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="14" fill="{t["bg"]}" stroke="{t["border"]}"/>',
           '<circle cx="26" cy="22" r="5" fill="#ff5f57"/><circle cx="44" cy="22" r="5" fill="#febc2e"/><circle cx="62" cy="22" r="5" fill="#28c840"/>',
           f'<g font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,\'DejaVu Sans Mono\',monospace" font-size="{FS}" xml:space="preserve">']
    for i, parts in enumerate(lines):
        if not parts:
            continue
        y = pad_y + 14 + i * LH
        n = sum(len(p[0]) for p in parts)
        spans = "".join(f'<tspan fill="{t[role]}">{escape(txt)}</tspan>' for txt, role in parts)
        out.append(f'<text x="{pad_x}" y="{y}" textLength="{n*CW:.1f}" lengthAdjust="spacingAndGlyphs">{spans}</text>')
    for i, row in enumerate(ART):
        if all(ch == " " for ch, _ in row):
            continue
        # one <text> per run of same-role chars, positioned absolutely so colours never shift columns
        j = 0
        while j < len(row):
            ch, role = row[j]
            if ch == " ":
                j += 1
                continue
            k = j
            while k < len(row) and row[k][1] == role and row[k][0] != " ":
                k += 1
            seg = "".join(c for c, _ in row[j:k])
            out.append(f'<text x="{art_x + j*CW:.1f}" y="{art_top + i*LH}" textLength="{len(seg)*CW:.1f}" '
                       f'lengthAdjust="spacingAndGlyphs" fill="{t[role]}">{escape(seg)}</text>')
            j = k
    out.append("</g></svg>")
    (HERE / f"{name}.svg").write_text("\n".join(out), encoding="utf-8")


def main():
    cfg = json.loads((HERE / "config.json").read_text())
    if "--fetch" in sys.argv:
        fetch_stats(cfg["github_username"], cfg["stats"])
    for name, theme in THEMES.items():
        render(cfg, name, theme)
    print("wrote dark.svg and light.svg")


if __name__ == "__main__":
    main()
