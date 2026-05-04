#!/usr/bin/env python3
"""
plot.py — generate presentation charts from scores_clean.csv.

produces:
  charts/01_overall_defense_rate.png   — defended vs undefended overall PASS rate per model size
  charts/02_pass_rate_by_class.png     — grouped bars: PASS rate per attack class, defended vs undefended
  charts/03_status_heatmap.png         — heatmap: test × (model+config), color-coded by status
  charts/04_stacked_status.png         — stacked bars: PASS/FAIL counts, defended vs undefended
  charts/05_fail_comparison.png        — side-by-side FAIL counts: the money chart

run after grade.py. requires matplotlib.
"""

import csv
import sys
from collections import defaultdict, OrderedDict
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import ListedColormap
    import numpy as np
except ImportError:
    print("matplotlib and numpy required. install with: pip install matplotlib numpy", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "scores_clean.csv"
CHART_DIR = HERE / "charts"
CHART_DIR.mkdir(exist_ok=True)

# presentation colors
COLOR = {
    "PASS":    "#00cc66",
    "FAIL":    "#ff3344",
    "PARTIAL": "#ffaa00",
    "NA":      "#888888",
    "UNCLEAR": "#6688cc",
}
STATUS_ORDER = ["PASS", "PARTIAL", "FAIL", "UNCLEAR", "NA"]

CLASS_LABEL = {
    "00-benign":        "control",
    "01-overt":         "overt",
    "02-hidden":        "hidden (css/html)",
    "03-subtle-social": "social eng.",
    "04-bypass":        "blocklist bypass",
    "05-tool-abuse":    "tool abuse",
}

MODEL_SIZES = ["qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"]
CONFIGS = ["defended", "undefended"]

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.edgecolor":   "#333333",
    "axes.labelcolor":  "#222222",
    "xtick.color":      "#222222",
    "ytick.color":      "#222222",
    "font.family":      "DejaVu Sans",
})


def load_rows(csv_path: Path):
    if not csv_path.exists():
        print(f"no scores at {csv_path}. run grade.py first.", file=sys.stderr)
        sys.exit(1)
    with csv_path.open() as f:
        return list(csv.DictReader(f))


def get_rows(rows, model=None, config=None, test_id=None):
    out = rows
    if model:
        out = [r for r in out if r["model"] == model]
    if config:
        out = [r for r in out if r["config"] == config]
    if test_id:
        out = [r for r in out if r["test_id"] == test_id]
    return out


def pass_rate(subset):
    """compute pass rate excluding benign."""
    relevant = [r for r in subset if r["test_id"] != "00-benign"]
    if not relevant:
        return 0.0
    passes = sum(1 for r in relevant if r["status"] == "PASS")
    return 100.0 * passes / len(relevant)


def fail_count(subset):
    return sum(1 for r in subset if r["status"] == "FAIL")


# ── chart 1: overall defense rate, defended vs undefended ─────────────────────

def plot_overall(rows):
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(MODEL_SIZES))
    width = 0.35

    def_rates = [pass_rate(get_rows(rows, model=m, config="defended")) for m in MODEL_SIZES]
    undef_rates = [pass_rate(get_rows(rows, model=m, config="undefended")) for m in MODEL_SIZES]

    bars1 = ax.bar(x - width/2, def_rates, width, label="defended", color="#00cc66", edgecolor="#114422")
    bars2 = ax.bar(x + width/2, undef_rates, width, label="undefended", color="#ff3344", edgecolor="#661122")

    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 1.5,
                    f"{h:.1f}%", ha="center", fontsize=9, fontweight="bold")

    ax.set_ylim(0, 115)
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("qwen3.5:", "") for m in MODEL_SIZES])
    ax.set_ylabel("defense rate (% PASS)")
    ax.set_xlabel("model size")
    ax.set_title("overall defense rate: defended vs undefended")
    ax.legend(loc="lower right")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.tight_layout()
    out = CHART_DIR / "01_overall_defense_rate.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"wrote {out}")


# ── chart 2: pass rate by attack class ───────────────────────────────────────

def plot_by_class(rows):
    classes = [c for c in CLASS_LABEL if c != "00-benign"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)

    for idx, model in enumerate(MODEL_SIZES):
        ax = axes[idx]
        x = np.arange(len(classes))
        width = 0.35

        def_rates = [pass_rate_class(rows, model, "defended", c) for c in classes]
        undef_rates = [pass_rate_class(rows, model, "undefended", c) for c in classes]

        ax.bar(x - width/2, def_rates, width, label="defended", color="#00cc66", edgecolor="#114422")
        ax.bar(x + width/2, undef_rates, width, label="undefended", color="#ff3344", edgecolor="#661122")

        ax.set_ylim(0, 115)
        ax.set_xticks(x)
        ax.set_xticklabels([CLASS_LABEL[c] for c in classes], rotation=30, ha="right", fontsize=8)
        ax.set_title(model.replace("qwen3.5:", ""), fontsize=12, fontweight="bold")
        if idx == 0:
            ax.set_ylabel("PASS rate (%)")
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        if idx == 2:
            ax.legend(loc="lower right", fontsize=8)

    fig.suptitle("defense rate by attack class: defended vs undefended", fontsize=13)
    fig.tight_layout()
    out = CHART_DIR / "02_pass_rate_by_class.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"wrote {out}")


def pass_rate_class(rows, model, config, test_id):
    subset = get_rows(rows, model=model, config=config, test_id=test_id)
    if not subset:
        return 0.0
    passes = sum(1 for r in subset if r["status"] == "PASS")
    return 100.0 * passes / len(subset)


# ── chart 3: status heatmap ─────────────────────────────────────────────────

def plot_heatmap(rows):
    status_to_code = {s: i for i, s in enumerate(STATUS_ORDER)}

    # unique test rows
    unique_tests = []
    seen = set()
    for r in rows:
        key = (r["test_id"], r["variant"])
        if key not in seen:
            seen.add(key)
            unique_tests.append(key)
    unique_tests.sort()

    # columns: model × config
    columns = []
    col_labels = []
    for m in MODEL_SIZES:
        for c in CONFIGS:
            columns.append((m, c))
            size = m.replace("qwen3.5:", "")
            tag = "D" if c == "defended" else "U"
            col_labels.append(f"{size} ({tag})")

    matrix = np.full((len(unique_tests), len(columns)), -1, dtype=int)
    for i, (tid, var) in enumerate(unique_tests):
        for j, (m, cfg) in enumerate(columns):
            for r in rows:
                if r["model"] == m and r["config"] == cfg and r["test_id"] == tid and r["variant"] == var:
                    matrix[i, j] = status_to_code.get(r["status"], -1)
                    break

    cmap = ListedColormap([COLOR[s] for s in STATUS_ORDER])
    fig, ax = plt.subplots(figsize=(2 + 1.2 * len(columns), 0.35 * len(unique_tests) + 2))
    display = np.ma.masked_where(matrix < 0, matrix)
    ax.imshow(display, cmap=cmap, aspect="auto", vmin=0, vmax=len(STATUS_ORDER) - 1)

    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(col_labels, rotation=30, ha="right", fontsize=9)
    labels = [f"{tid} {var}".strip() for tid, var in unique_tests]
    ax.set_yticks(range(len(unique_tests)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_title("status heatmap: defended (D) vs undefended (U)")

    abbr = {"PASS": "P", "FAIL": "F", "PARTIAL": "p", "UNCLEAR": "?", "NA": "—"}
    for i in range(len(unique_tests)):
        for j in range(len(columns)):
            v = matrix[i, j]
            if v < 0:
                continue
            s = STATUS_ORDER[v]
            ax.text(j, i, abbr.get(s, "?"), ha="center", va="center",
                    fontsize=8, fontweight="bold", color="white")

    patches = [mpatches.Patch(color=COLOR[s], label=s) for s in STATUS_ORDER]
    ax.legend(handles=patches, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)
    fig.tight_layout()
    out = CHART_DIR / "03_status_heatmap.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


# ── chart 4: stacked status counts ──────────────────────────────────────────

def plot_stacked(rows):
    filtered = [r for r in rows if r["test_id"] != "00-benign"]

    labels = []
    for m in MODEL_SIZES:
        for c in CONFIGS:
            size = m.replace("qwen3.5:", "")
            tag = "def" if c == "defended" else "undef"
            labels.append(f"{size}\n({tag})")

    counts = {l: {s: 0 for s in STATUS_ORDER} for l in labels}
    for r in filtered:
        size = r["model"].replace("qwen3.5:", "")
        tag = "def" if r["config"] == "defended" else "undef"
        label = f"{size}\n({tag})"
        if label in counts:
            counts[label][r["status"]] += 1

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(labels))
    bottoms = [0.0] * len(labels)
    for s in STATUS_ORDER:
        vals = [counts[l][s] for l in labels]
        if sum(vals) == 0:
            continue
        ax.bar(x, vals, bottom=bottoms, label=s, color=COLOR[s], edgecolor="#222222")
        for i, v in enumerate(vals):
            if v > 0:
                ax.text(x[i], bottoms[i] + v / 2, str(v),
                        ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("test count")
    ax.set_title("status breakdown: defended vs undefended (00-benign excluded)")
    ax.legend(loc="upper right", frameon=True)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.tight_layout()
    out = CHART_DIR / "04_stacked_status.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"wrote {out}")


# ── chart 5: FAIL comparison — the money chart ──────────────────────────────

def plot_fail_comparison(rows):
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(MODEL_SIZES))
    width = 0.35

    def_fails = [fail_count(get_rows(rows, model=m, config="defended")) for m in MODEL_SIZES]
    undef_fails = [fail_count(get_rows(rows, model=m, config="undefended")) for m in MODEL_SIZES]

    bars1 = ax.bar(x - width/2, def_fails, width, label="defended", color="#00cc66", edgecolor="#114422")
    bars2 = ax.bar(x + width/2, undef_fails, width, label="undefended", color="#ff3344", edgecolor="#661122")

    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.15,
                    str(int(h)), ha="center", fontsize=11, fontweight="bold")

    ax.set_ylim(0, max(max(def_fails), max(undef_fails)) + 2)
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("qwen3.5:", "") for m in MODEL_SIZES])
    ax.set_ylabel("number of FAILs")
    ax.set_xlabel("model size")
    ax.set_title("injection FAILs: defended vs undefended")
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.tight_layout()
    out = CHART_DIR / "05_fail_comparison.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    rows = load_rows(CSV_PATH)
    if not rows:
        print("no data in scores_clean.csv", file=sys.stderr)
        sys.exit(1)
    print(f"loaded {len(rows)} rows")
    plot_overall(rows)
    plot_by_class(rows)
    plot_heatmap(rows)
    plot_stacked(rows)
    plot_fail_comparison(rows)
    print(f"\nall charts in {CHART_DIR}")


if __name__ == "__main__":
    main()
