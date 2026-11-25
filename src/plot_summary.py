import csv
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt


def load_counts(csv_path: Path) -> tuple[int, int, Counter[str], Counter[str], Counter[str]]:
    by_itype: Counter[str] = Counter()
    by_cell: Counter[str] = Counter()
    by_safety: Counter[str] = Counter()
    papers: set[str] = set()
    total = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            rid = (row.get("record_id") or "").strip()
            if rid:
                papers.add(rid)

            itype = (row.get("intervention_type") or "").strip() or "(empty)"
            cell = (row.get("cell_type") or "").strip() or "(empty)"
            safety = (row.get("safety_flag") or "").strip() or "(empty)"

            by_itype[itype] += 1
            by_cell[cell] += 1
            by_safety[safety] += 1

    return total, len(papers), by_itype, by_cell, by_safety


def draw_horizontal_bar(
    ax: plt.Axes, counter: Counter[str], title: str, color: str, top_n: int = 8
) -> None:
    items = list(reversed(counter.most_common(top_n)))
    if not items:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        return

    labels = [k for k, _ in items]
    values = [v for _, v in items]

    bars = ax.barh(labels, values, color=color, height=0.62, edgecolor="none")
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10, loc="left")
    ax.set_xlabel("Observations", fontsize=9)
    ax.tick_params(axis="both", labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    max_val = max(values) if values else 1
    ax.set_xlim(0, max_val * 1.18)

    for bar, val in zip(bars, values):
        ax.text(
            val + max_val * 0.02,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
            ha="left",
            fontsize=8.5,
            color="#222222",
        )


def make_summary_figure(csv_path: Path, out_path: Path) -> int:
    if not csv_path.exists():
        print(f"CSV 파일을 찾을 수 없습니다: {csv_path}")
        return 1

    total_rows, paper_count, by_itype, by_cell, by_safety = load_counts(csv_path)

    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.6), dpi=200)
    fig.suptitle(
        f"Aging Intervention DB Summary ({total_rows} observations across {paper_count} papers)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    draw_horizontal_bar(
        axes[0], by_itype, "By Intervention Type", color="#2B6CB0", top_n=6
    )
    draw_horizontal_bar(
        axes[1], by_cell, "Top Cell Types", color="#2F855A", top_n=8
    )
    draw_horizontal_bar(
        axes[2], by_safety, "By Safety Flag", color="#C05621", top_n=6
    )

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"요약 그림 저장 완료 -> {out_path}")
    return 0


def main() -> int:
    return make_summary_figure(
        csv_path=Path("data/curated/observations.csv"),
        out_path=Path("assets/summary_overview.png"),
    )


if __name__ == "__main__":
    sys.exit(main())