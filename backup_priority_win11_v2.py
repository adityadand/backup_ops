"""
╔══════════════════════════════════════════════════════╗
║      Smart Backup Analyzer v2  —  Windows 11         ║
║  Scans drives, scores & categorises everything,      ║
║  then writes a self-contained HTML decision dashboard ║
╚══════════════════════════════════════════════════════╝

Requirements:
    pip install tqdm colorama

Usage:
    python backup_priority_win11_v2.py
"""

import os, json, csv, hashlib, string, sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    def c(text, color): return color + text + Style.RESET_ALL
except ImportError:
    def c(text, _): return text

# ─── CONFIG ────────────────────────────────────────────────────────────────────

# Approximate external HDD write speed (MB/s) — adjust to your drive
HDD_SPEED_MBPS = 80

# A folder must have at least this many files to be grouped as one item
FOLDER_FILE_THRESHOLD = 3

# ─── CATEGORIES ────────────────────────────────────────────────────────────────

CATEGORIES = {
    "Documents": {
        "extensions": {".doc", ".docx", ".pdf", ".txt", ".odt", ".rtf", ".md",
                       ".xls", ".xlsx", ".csv", ".ods", ".ppt", ".pptx", ".odp"},
        "keywords": [],
        "color": "#3b82f6",
        "icon": "📄",
        "base_score": 8,
    },
    "Photos": {
        "extensions": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                       ".webp", ".heic", ".heif", ".raw", ".cr2", ".nef", ".arw"},
        "keywords": ["photos", "pictures", "camera", "dcim"],
        "color": "#f59e0b",
        "icon": "🖼️",
        "base_score": 7,
    },
    "Videos": {
        "extensions": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
                       ".m4v", ".3gp", ".ts", ".mts"},
        "keywords": ["videos", "movies", "recordings"],
        "color": "#ef4444",
        "icon": "🎬",
        "base_score": 6,
    },
    "Audio": {
        "extensions": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".wma", ".m4a"},
        "keywords": ["music", "audio"],
        "color": "#8b5cf6",
        "icon": "🎵",
        "base_score": 5,
    },
    "Code & Projects": {
        "extensions": {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp",
                       ".c", ".h", ".cs", ".go", ".rs", ".rb", ".php",
                       ".sql", ".sh", ".bat", ".ps1", ".json", ".yaml", ".yml",
                       ".toml", ".env", ".gitignore"},
        "keywords": ["projects", "source", "repos", "github"],
        "color": "#10b981",
        "icon": "💻",
        "base_score": 9,
    },
    "Archives": {
        "extensions": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
        "keywords": ["backup", "archive"],
        "color": "#6b7280",
        "icon": "📦",
        "base_score": 4,
    },
    "System / Junk": {
        "extensions": {".dll", ".sys", ".exe", ".msi", ".cab", ".tmp", ".log",
                       ".bak", ".old", ".dmp"},
        "keywords": [],
        "color": "#9ca3af",
        "icon": "⚙️",
        "base_score": 0,
    },
}

# ─── IGNORE RULES ──────────────────────────────────────────────────────────────

# These paths are Windows system/cache/reinstallable — skip entirely
IGNORE_PATH_FRAGMENTS = [
    # Windows internals
    "\\Windows\\WinSxS", "\\Windows\\servicing", "\\Windows\\assembly",
    "\\Windows\\System32", "\\Windows\\SysWOW64", "\\Windows\\Installer",
    "\\Windows\\SoftwareDistribution", "\\Windows\\Prefetch",
    "\\Windows\\Logs", "\\Windows\\Temp", "\\Windows\\inf",
    # Common junk
    "AppData\\Local\\Temp", "AppData\\Local\\Microsoft\\Windows\\INetCache",
    "AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache",
    "AppData\\Local\\Mozilla\\Firefox\\Profiles",
    "AppData\\LocalLow\\Temp",
    "node_modules", ".git\\objects", "__pycache__",
    ".cache", "\\Temp\\", "\\tmp\\", "\\logs\\",
    "ProgramData\\Microsoft", "ProgramData\\Package Cache",
    "$Recycle.Bin", "System Volume Information",
]

# These path fragments REDUCE score but don't fully exclude
DEPRIORITIZE_FRAGMENTS = [
    "AppData\\Roaming", "AppData\\Local",
    "\\Program Files\\", "\\Program Files (x86)\\",
    "ProgramData",
]


def should_ignore(path: str) -> bool:
    lp = path.lower()
    return any(frag.lower() in lp for frag in IGNORE_PATH_FRAGMENTS)


def get_category(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    lp = file_path.lower()
    for cat, cfg in CATEGORIES.items():
        if ext in cfg["extensions"]:
            return cat
        if any(kw in lp for kw in cfg["keywords"]):
            return cat
    return "Other"


# ─── SCORING ───────────────────────────────────────────────────────────────────

def score_file(path: str, stats, category: str) -> int:
    score = 0

    # 1. Category base score
    score += CATEGORIES.get(category, {}).get("base_score", 2)

    # 2. Recency (most important factor — recently modified = likely active work)
    days_old = (datetime.now() - datetime.fromtimestamp(stats.st_mtime)).days
    if days_old < 7:
        score += 20
    elif days_old < 30:
        score += 12
    elif days_old < 90:
        score += 6
    elif days_old < 365:
        score += 2
    # older than a year: +0

    # 3. Size (large files take time; prioritise knowing about them)
    size_mb = stats.st_size / (1024 * 1024)
    if size_mb > 1000:
        score += 5
    elif size_mb > 100:
        score += 3
    elif size_mb > 10:
        score += 1

    # 4. User-data paths (Desktop, Documents, Downloads, etc.)
    lp = path.lower()
    for good_kw in ["\\desktop\\", "\\documents\\", "\\downloads\\",
                     "\\pictures\\", "\\videos\\", "\\music\\",
                     "\\onedrive\\", "crossdevice"]:
        if good_kw in lp:
            score += 5
            break

    # 5. Deprioritise reinstallable locations
    if any(frag.lower() in lp for frag in DEPRIORITIZE_FRAGMENTS):
        score -= 4

    return max(score, 0)


# ─── SCANNER ───────────────────────────────────────────────────────────────────

def count_files(base_path: str) -> int:
    """Quick file count for progress bar."""
    total = 0
    for _, _, files in os.walk(base_path):
        total += len(files)
    return total


def scan_drive(base_path: str) -> list[dict]:
    print(c(f"\n🔍 Pre-counting files in {base_path} …", Fore.CYAN))
    try:
        total_files = count_files(base_path)
    except Exception:
        total_files = None
    print(c(f"   Found ~{total_files or '?'} files. Starting deep scan…\n", Fore.CYAN))

    folder_map: dict[str, list] = defaultdict(list)
    loose_files: list[dict] = []

    iterator = os.walk(base_path)
    if HAS_TQDM and total_files:
        pbar = tqdm(total=total_files, unit="files", ncols=80,
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]")
    else:
        pbar = None

    for root, dirs, files in iterator:
        # Prune dirs in-place so os.walk won't descend into ignored subtrees
        dirs[:] = [d for d in dirs
                   if not should_ignore(os.path.join(root, d))]

        if should_ignore(root):
            if pbar:
                pbar.update(len(files))
            continue

        temp_files = []
        for file in files:
            if pbar:
                pbar.update(1)
            try:
                full_path = os.path.join(root, file)
                if should_ignore(full_path):
                    continue

                stats = os.stat(full_path)
                category = get_category(full_path)
                priority = score_file(full_path, stats, category)

                temp_files.append({
                    "type": "file",
                    "path": full_path,
                    "category": category,
                    "size_mb": round(stats.st_size / (1024 * 1024), 3),
                    "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d"),
                    "priority": priority,
                })
            except (PermissionError, FileNotFoundError, OSError):
                continue

        if len(temp_files) >= FOLDER_FILE_THRESHOLD:
            # Determine dominant category for the folder
            cat_counts: dict[str, int] = defaultdict(int)
            for f in temp_files:
                cat_counts[f["category"]] += 1
            dominant_cat = max(cat_counts, key=cat_counts.__getitem__)

            folder_priority = sum(f["priority"] for f in temp_files)
            folder_size = sum(f["size_mb"] for f in temp_files)

            folder_map[root] = {
                "type": "folder",
                "path": root,
                "category": dominant_cat,
                "file_count": len(temp_files),
                "total_size_mb": round(folder_size, 3),
                "modified": max(f["modified"] for f in temp_files),
                "priority": folder_priority,
                "files_preview": [f["path"] for f in
                                   sorted(temp_files, key=lambda x: x["priority"], reverse=True)[:5]],
            }
        else:
            loose_files.extend(temp_files)

    if pbar:
        pbar.close()

    return list(folder_map.values()) + loose_files


# ─── BACKUP TIME ESTIMATE ──────────────────────────────────────────────────────

def estimate_time(size_mb: float, speed_mbps: float = HDD_SPEED_MBPS) -> str:
    seconds = size_mb / speed_mbps
    if seconds < 60:
        return f"~{int(seconds)}s"
    elif seconds < 3600:
        return f"~{int(seconds/60)}m"
    else:
        h = int(seconds / 3600)
        m = int((seconds % 3600) / 60)
        return f"~{h}h {m}m"


def fmtSize(mb: float) -> str:
    """Human-readable file size for terminal output."""
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    if mb >= 1:
        return f"{mb:.0f} MB"
    return f"{mb*1024:.0f} KB"


def fmtTime(mb: float, speed_mbps: float = HDD_SPEED_MBPS) -> str:
    """Human-readable transfer time estimate for terminal output."""
    seconds = mb / speed_mbps
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"~{int(seconds/60)}m"
    h = int(seconds / 3600)
    m = int((seconds % 3600) / 60)
    return f"~{h}h {m}m"


# ─── HTML DASHBOARD GENERATOR ─────────────────────────────────────────────────

def build_html_dashboard(data: list[dict], drive_letter: str) -> str:
    # Top 500 items for the dashboard (sorted by priority)
    top = sorted(data, key=lambda x: x["priority"], reverse=True)[:500]

    # Stats
    total_size = sum(d.get("total_size_mb", d.get("size_mb", 0)) or 0 for d in data)
    top_size = sum(d.get("total_size_mb", d.get("size_mb", 0)) or 0 for d in top)

    cat_sizes: dict[str, float] = defaultdict(float)
    cat_counts: dict[str, int] = defaultdict(int)
    for d in top:
        cat = d.get("category", "Other")
        cat_sizes[cat] += d.get("total_size_mb", d.get("size_mb", 0)) or 0
        cat_counts[cat] += 1

    rows_json = json.dumps(top, ensure_ascii=False)
    cat_data_json = json.dumps({
        k: {"size_mb": round(v, 1), "count": cat_counts[k], "color": CATEGORIES.get(k, {}).get("color", "#9ca3af")}
        for k, v in sorted(cat_sizes.items(), key=lambda x: -x[1])
    })
    cat_icons_json = json.dumps({k: v["icon"] for k, v in CATEGORIES.items()})
    scan_time = datetime.now().strftime("%d %b %Y, %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backup Dashboard — Drive {drive_letter}:</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

  :root {{
    --bg: #0d0f14;
    --surface: #161922;
    --surface2: #1e2330;
    --border: #2a3040;
    --text: #e2e8f0;
    --muted: #8892a4;
    --accent: #38bdf8;
    --green: #34d399;
    --amber: #fbbf24;
    --red: #f87171;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', sans-serif;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 24px;
  }}

  h1 {{ font-size: 1.5rem; font-weight: 700; letter-spacing: -0.03em; }}
  h2 {{ font-size: 0.85rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.08em; color: var(--muted); margin-bottom: 12px; }}

  .header {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 28px; flex-wrap: wrap; gap: 12px;
  }}
  .badge {{
    font-family: var(--mono); font-size: 0.75rem;
    background: var(--surface2); border: 1px solid var(--border);
    padding: 4px 10px; border-radius: 4px; color: var(--muted);
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }}
  .card .val {{
    font-family: var(--mono); font-size: 1.6rem;
    font-weight: 600; margin-top: 4px;
  }}
  .card .sub {{ font-size: 0.75rem; color: var(--muted); margin-top: 2px; }}

  .two-col {{
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: 16px; margin-bottom: 24px;
  }}
  @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

  .bar-row {{
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 10px; font-size: 0.82rem;
  }}
  .bar-label {{ width: 130px; white-space: nowrap; overflow: hidden;
                text-overflow: ellipsis; flex-shrink: 0; }}
  .bar-wrap {{ flex: 1; background: var(--surface2); border-radius: 3px; height: 14px; }}
  .bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s; }}
  .bar-meta {{ width: 90px; text-align: right; color: var(--muted);
               font-family: var(--mono); font-size: 0.72rem; }}

  /* Controls */
  .controls {{
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px;
    align-items: center;
  }}
  .controls input, .controls select {{
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); border-radius: 5px; padding: 6px 10px;
    font-family: var(--sans); font-size: 0.82rem; outline: none;
  }}
  .controls input {{ flex: 1; min-width: 200px; }}
  .controls input:focus, .controls select:focus {{ border-color: var(--accent); }}

  /* Table */
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.80rem; }}
  thead th {{
    text-align: left; padding: 8px 10px; font-weight: 600;
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); border-bottom: 1px solid var(--border);
    position: sticky; top: 0; background: var(--surface); cursor: pointer;
    user-select: none; white-space: nowrap;
  }}
  thead th:hover {{ color: var(--text); }}
  tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.15s; }}
  tbody tr:hover {{ background: var(--surface2); }}
  tbody td {{ padding: 7px 10px; vertical-align: middle; }}

  .path-cell {{
    max-width: 320px; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; font-family: var(--mono); font-size: 0.72rem;
    color: var(--muted);
  }}
  .path-cell:hover {{ white-space: normal; word-break: break-all; }}

  .pill {{
    display: inline-block; padding: 2px 7px; border-radius: 99px;
    font-size: 0.68rem; font-weight: 600; white-space: nowrap;
  }}

  .score-bar {{
    display: flex; align-items: center; gap: 6px;
  }}
  .score-fill {{
    height: 6px; border-radius: 3px; background: var(--accent);
    min-width: 2px;
  }}
  .score-num {{
    font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    min-width: 36px;
  }}

  .check {{ cursor: pointer; width: 15px; height: 15px; accent-color: var(--accent); }}

  .checked-bar {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: var(--surface); border-top: 2px solid var(--accent);
    padding: 12px 24px; display: flex; align-items: center; gap: 16px;
    font-size: 0.83rem; z-index: 100; transform: translateY(100%);
    transition: transform 0.3s;
  }}
  .checked-bar.visible {{ transform: translateY(0); }}
  .checked-bar strong {{ font-family: var(--mono); color: var(--accent); }}
  .btn {{
    background: var(--accent); color: #000; border: none;
    padding: 6px 14px; border-radius: 5px; font-weight: 700;
    cursor: pointer; font-size: 0.78rem; font-family: var(--sans);
  }}
  .btn.outline {{
    background: transparent; color: var(--muted);
    border: 1px solid var(--border);
  }}
  .btn:hover {{ opacity: 0.85; }}

  .tag-type {{
    font-size: 0.65rem; padding: 2px 5px; border-radius: 3px;
    background: var(--surface2); color: var(--muted);
    font-family: var(--mono);
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>💾 Backup Priority — Drive {drive_letter}:</h1>
    <div style="margin-top:4px;font-size:0.78rem;color:var(--muted)">
      Scanned {scan_time} &nbsp;·&nbsp; Showing top 500 items by priority
    </div>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <span class="badge">⚡ {HDD_SPEED_MBPS} MB/s HDD</span>
    <span class="badge" id="badge-total"></span>
  </div>
</div>

<!-- Stat cards -->
<div class="grid" id="stat-cards"></div>

<!-- Category breakdown + size chart -->
<div class="two-col">
  <div class="card">
    <h2>By Category</h2>
    <div id="cat-bars"></div>
  </div>
  <div class="card">
    <h2>Top 20 Folders / Files</h2>
    <div id="top20"></div>
  </div>
</div>

<!-- Full table -->
<div class="card" style="margin-bottom:80px">
  <h2>All Items — click to select for backup</h2>
  <div class="controls">
    <input type="text" id="search" placeholder="🔍  Filter by path…">
    <select id="filter-cat">
      <option value="">All Categories</option>
    </select>
    <select id="filter-type">
      <option value="">All Types</option>
      <option value="folder">Folders</option>
      <option value="file">Files</option>
    </select>
    <select id="sort-by">
      <option value="priority">Sort: Priority ↓</option>
      <option value="size">Sort: Size ↓</option>
      <option value="modified">Sort: Modified ↓</option>
    </select>
    <span style="color:var(--muted);font-size:0.78rem" id="row-count"></span>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th><input type="checkbox" id="check-all" class="check" title="Select all visible"></th>
          <th>#</th>
          <th>Path</th>
          <th>Category</th>
          <th>Type</th>
          <th>Size</th>
          <th>Modified</th>
          <th>Est. Time</th>
          <th>Priority</th>
        </tr>
      </thead>
      <tbody id="tbl-body"></tbody>
    </table>
  </div>
</div>

<!-- Floating selection bar -->
<div class="checked-bar" id="checked-bar">
  <div>
    <strong id="sel-count">0</strong> items selected &nbsp;·&nbsp;
    <strong id="sel-size">0 GB</strong> &nbsp;·&nbsp;
    <strong id="sel-time">–</strong> estimated
  </div>
  <button class="btn" onclick="exportSelected()">⬇ Export List</button>
  <button class="btn outline" onclick="clearSelection()">✕ Clear</button>
</div>

<script>
const ROWS = {rows_json};
const CAT_DATA = {cat_data_json};
const CAT_ICONS = {cat_icons_json};
const HDD_SPEED = {HDD_SPEED_MBPS};
const TOTAL_SIZE_GB = {total_size / 1024:.1f};
const TOP_SIZE_GB = {top_size / 1024:.1f};

function fmtSize(mb) {{
  if (mb >= 1024) return (mb/1024).toFixed(1) + ' GB';
  if (mb >= 1)    return mb.toFixed(0) + ' MB';
  return (mb*1024).toFixed(0) + ' KB';
}}
function fmtTime(mb) {{
  const s = mb / HDD_SPEED;
  if (s < 60) return '<1m';
  if (s < 3600) return Math.round(s/60) + 'm';
  return Math.round(s/3600) + 'h ' + Math.round((s%3600)/60) + 'm';
}}
function priorityColor(p, max) {{
  const r = p / max;
  if (r > 0.6) return 'var(--red)';
  if (r > 0.3) return 'var(--amber)';
  return 'var(--accent)';
}}

// ── Stat cards ────────────────────────────────────────────────────────────────
const maxPri = Math.max(...ROWS.map(r => r.priority));
const totalItems = ROWS.length;
const foldersCount = ROWS.filter(r => r.type === 'folder').length;
const highPri = ROWS.filter(r => r.priority / maxPri > 0.4).length;

document.getElementById('badge-total').textContent =
  `${{ROWS.length}} items · ${{TOP_SIZE_GB.toFixed(1)}} GB`;

document.getElementById('stat-cards').innerHTML = [
  ['Total Items', totalItems.toLocaleString(), 'in top 500 priority list'],
  ['Folders', foldersCount.toLocaleString(), 'grouped directories'],
  ['High Priority', highPri.toLocaleString(), 'needs backup first'],
  ['Est. Total Time', fmtTime(TOP_SIZE_GB * 1024), `at ${{HDD_SPEED}} MB/s`],
  ['Drive Total', TOTAL_SIZE_GB.toFixed(1) + ' GB', 'full drive size'],
  ['Top 500 Size', TOP_SIZE_GB.toFixed(1) + ' GB', 'priority items'],
].map(([label, val, sub]) =>
  `<div class="card"><h2>${{label}}</h2><div class="val">${{val}}</div><div class="sub">${{sub}}</div></div>`
).join('');

// ── Category bars ─────────────────────────────────────────────────────────────
const maxCatSize = Math.max(...Object.values(CAT_DATA).map(v => v.size_mb));
document.getElementById('cat-bars').innerHTML = Object.entries(CAT_DATA).map(([cat, d]) => {{
  const icon = CAT_ICONS[cat] || '📁';
  const pct = Math.round(d.size_mb / maxCatSize * 100);
  return `<div class="bar-row">
    <div class="bar-label">${{icon}} ${{cat}}</div>
    <div class="bar-wrap"><div class="bar-fill" style="width:${{pct}}%;background:${{d.color}}"></div></div>
    <div class="bar-meta">${{fmtSize(d.size_mb)}}&nbsp;(${{d.count}})</div>
  </div>`;
}}).join('');

// ── Top 20 horizontal ─────────────────────────────────────────────────────────
const top20 = ROWS.slice(0, 20);
const maxTop = Math.max(...top20.map(r => r.priority));
document.getElementById('top20').innerHTML = top20.map((r, i) => {{
  const size = r.total_size_mb ?? r.size_mb ?? 0;
  const name = r.path.split('\\\\').slice(-1)[0] || r.path;
  const pct  = Math.round(r.priority / maxTop * 100);
  const col  = priorityColor(r.priority, maxTop);
  return `<div class="bar-row" title="${{r.path}}">
    <div class="bar-label" style="font-size:0.75rem;font-family:var(--mono)">
      ${{(i+1).toString().padStart(2,'0')}}. ${{name.substring(0,16)}}
    </div>
    <div class="bar-wrap"><div class="bar-fill" style="width:${{pct}}%;background:${{col}}"></div></div>
    <div class="bar-meta">${{fmtSize(size)}}</div>
  </div>`;
}}).join('');

// ── Table ─────────────────────────────────────────────────────────────────────
const categories = [...new Set(ROWS.map(r => r.category))].sort();
const catSel = document.getElementById('filter-cat');
categories.forEach(c => {{
  const o = document.createElement('option'); o.value = c; o.textContent = c;
  catSel.appendChild(o);
}});

let selected = new Set();
let filtered = [...ROWS];

function render() {{
  const q = document.getElementById('search').value.toLowerCase();
  const cat = document.getElementById('filter-cat').value;
  const type = document.getElementById('filter-type').value;
  const sort = document.getElementById('sort-by').value;

  filtered = ROWS.filter(r =>
    (!q || r.path.toLowerCase().includes(q)) &&
    (!cat || r.category === cat) &&
    (!type || r.type === type)
  );

  if (sort === 'size') filtered.sort((a,b) => (b.total_size_mb??b.size_mb??0) - (a.total_size_mb??a.size_mb??0));
  else if (sort === 'modified') filtered.sort((a,b) => (b.modified||'').localeCompare(a.modified||''));
  else filtered.sort((a,b) => b.priority - a.priority);

  document.getElementById('row-count').textContent = `${{filtered.length}} items`;

  const maxP = Math.max(...ROWS.map(r => r.priority));
  const tbody = document.getElementById('tbl-body');
  tbody.innerHTML = filtered.map((r, i) => {{
    const size = r.total_size_mb ?? r.size_mb ?? 0;
    const pct  = Math.round(r.priority / maxP * 100);
    const col  = priorityColor(r.priority, maxP);
    const icon = CAT_ICONS[r.category] || '📁';
    const cat  = CAT_DATA[r.category];
    const catColor = cat ? cat.color : '#6b7280';
    const isChk = selected.has(r.path);
    return `<tr>
      <td><input type="checkbox" class="check row-check" data-path="${{r.path}}" ${{isChk?'checked':''}}></td>
      <td style="color:var(--muted);font-family:var(--mono);font-size:0.7rem">${{i+1}}</td>
      <td class="path-cell">${{r.path}}</td>
      <td><span class="pill" style="background:${{catColor}}20;color:${{catColor}}">${{icon}} ${{r.category}}</span></td>
      <td><span class="tag-type">${{r.type}}</span>
          ${{r.file_count ? `<span style="color:var(--muted);font-size:0.68rem"> ${{r.file_count}} files</span>` : ''}}</td>
      <td style="font-family:var(--mono);font-size:0.75rem;white-space:nowrap">${{fmtSize(size)}}</td>
      <td style="font-family:var(--mono);font-size:0.72rem;color:var(--muted)">${{r.modified||'–'}}</td>
      <td style="font-family:var(--mono);font-size:0.72rem;color:var(--muted)">${{fmtTime(size)}}</td>
      <td>
        <div class="score-bar">
          <div class="score-fill" style="width:${{pct*0.8}}px;background:${{col}}"></div>
          <span class="score-num">${{r.priority}}</span>
        </div>
      </td>
    </tr>`;
  }}).join('');

  // Re-attach checkbox listeners
  tbody.querySelectorAll('.row-check').forEach(cb => {{
    cb.addEventListener('change', e => {{
      const p = e.target.dataset.path;
      e.target.checked ? selected.add(p) : selected.delete(p);
      updateBar();
    }});
  }});
}}

function updateBar() {{
  const items = ROWS.filter(r => selected.has(r.path));
  const totalSizeMb = items.reduce((s, r) => s + (r.total_size_mb ?? r.size_mb ?? 0), 0);
  document.getElementById('sel-count').textContent = selected.size;
  document.getElementById('sel-size').textContent = fmtSize(totalSizeMb);
  document.getElementById('sel-time').textContent = fmtTime(totalSizeMb);
  document.getElementById('checked-bar').classList.toggle('visible', selected.size > 0);
}}

function exportSelected() {{
  const items = ROWS.filter(r => selected.has(r.path));
  const csv = ['Path,Category,Type,Size MB,Modified,Priority']
    .concat(items.map(r =>
      `"${{r.path}}","${{r.category}}","${{r.type}}",${{r.total_size_mb??r.size_mb??0}},${{r.modified}},${{r.priority}}`
    )).join('\\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv,' + encodeURIComponent(csv);
  a.download = 'backup_selected_{drive_letter}.csv';
  a.click();
}}

function clearSelection() {{
  selected.clear();
  render();
  updateBar();
}}

document.getElementById('search').addEventListener('input', render);
document.getElementById('filter-cat').addEventListener('change', render);
document.getElementById('filter-type').addEventListener('change', render);
document.getElementById('sort-by').addEventListener('change', render);
document.getElementById('check-all').addEventListener('change', e => {{
  filtered.forEach(r => e.target.checked ? selected.add(r.path) : selected.delete(r.path));
  render(); updateBar();
}});

render();
</script>
</body>
</html>"""
    return html


# ─── SAVE OUTPUTS ──────────────────────────────────────────────────────────────

def save_results(data: list[dict], drive_letter: str):
    data = sorted(data, key=lambda x: x["priority"], reverse=True)

    json_path = f"{drive_letter}_backup_analysis.json"
    csv_path  = f"{drive_letter}_backup_analysis.csv"
    html_path = f"{drive_letter}_backup_dashboard.html"

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(c(f"  📄 JSON  → {json_path}", Fore.GREEN))

    # CSV
    all_keys = list({k for item in data for k in item.keys()} - {"files_preview"})
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(c(f"  📊 CSV   → {csv_path}", Fore.GREEN))

    # HTML dashboard
    html = build_html_dashboard(data, drive_letter)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(c(f"  🌐 HTML  → {html_path}  ← Open this in your browser!", Fore.CYAN))

    # Quick summary in terminal
    top10 = data[:10]
    print(c(f"\n{'─'*60}", Fore.WHITE))
    print(c("  TOP 10 items to backup FIRST:", Fore.YELLOW))
    for i, item in enumerate(top10, 1):
        size = item.get("total_size_mb", item.get("size_mb", 0)) or 0
        name = item["path"].split("\\")[-1] or item["path"]
        print(f"  {i:2}. [{item['category']:<16}] {name[:40]:<40}"
              f"  {fmtSize(size):>8}  score={item['priority']}")
    print(c(f"{'─'*60}\n", Fore.WHITE))


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def get_available_drives():
    return [d for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]

def ask_for_drives():
    drives = get_available_drives()
    print(c("💽 Available drives: " + ", ".join(f"{d}:" for d in drives), Fore.CYAN))
    raw = input(c("👉 Enter drive letters to scan (e.g. C,D) [default: C]: ", Fore.YELLOW)).upper().strip()
    selected = [d.strip() for d in raw.split(",") if d.strip() in drives]
    return selected if selected else ["C"]

def main():
    print(c("\n╔══════════════════════════════════════╗", Fore.CYAN))
    print(c("║  Smart Backup Analyzer  v2  Win11    ║", Fore.CYAN))
    print(c("╚══════════════════════════════════════╝\n", Fore.CYAN))

    drives = ask_for_drives()

    for d in drives:
        path = f"{d}:\\"
        results = scan_drive(path)

        total_items = len(results)
        total_size  = sum(r.get("total_size_mb", r.get("size_mb", 0)) or 0 for r in results)
        print(c(f"\n✅ Scan complete: {total_items:,} items  |  "
                f"{total_size/1024:.1f} GB  |  "
                f"est. {fmtSize(total_size)} backup @ {HDD_SPEED_MBPS} MB/s = {fmtTime(total_size)}", Fore.GREEN))

        print(c("\n💾 Saving outputs…", Fore.CYAN))
        save_results(results, d)

    print(c("\n🎉 All done! Open the HTML dashboard to plan your backup.\n", Fore.GREEN))

if __name__ == "__main__":
    main()
