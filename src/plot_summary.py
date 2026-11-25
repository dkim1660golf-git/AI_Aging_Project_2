import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def load_observations(csv_path: Path) -> tuple[int, int, list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    papers: set[str] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {k: (v or "").strip() for k, v in row.items() if k is not None}
            rows.append(cleaned)
            rid = cleaned.get("record_id", "")
            if rid:
                papers.add(rid)

    return len(rows), len(papers), rows


def build_marker_comparison_rows(
    rows: list[dict[str, str]],
) -> list[tuple[str, int, int, str, str]]:
    """마커별 (marker, senolytic_cnt, partial_reprog_cnt, top_seno_dir, top_reprog_dir)를 반환합니다."""
    marker_totals: Counter[str] = Counter()
    by_group_marker: dict[str, Counter[str]] = {
        "senolytic": Counter(),
        "partial_reprogramming": Counter(),
    }
    dir_by_group_marker: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    for r in rows:
        itype = r.get("intervention_type", "")
        marker = r.get("marker_or_endpoint") or "(empty)"
        direction = r.get("direction") or "unclear"
        if itype in by_group_marker:
            by_group_marker[itype][marker] += 1
            marker_totals[marker] += 1
            dir_by_group_marker[(itype, marker)][direction] += 1

    table_rows: list[tuple[str, int, int, str, str]] = []
    for marker, _ in marker_totals.most_common():
        s_cnt = by_group_marker["senolytic"][marker]
        p_cnt = by_group_marker["partial_reprogramming"][marker]
        s_top = dir_by_group_marker[("senolytic", marker)].most_common(1)
        p_top = dir_by_group_marker[("partial_reprogramming", marker)].most_common(1)
        s_dir = f"{s_top[0][0]} ({s_top[0][1]})" if s_top else "-"
        p_dir = f"{p_top[0][0]} ({p_top[0][1]})" if p_top else "-"
        table_rows.append((marker, s_cnt, p_cnt, s_dir, p_dir))

    return table_rows


def draw_horizontal_bar(
    ax: plt.Axes,
    counter: Counter[str],
    title: str,
    color: str,
    top_n: int | None = None,
) -> None:
    raw_items = counter.most_common() if top_n is None else counter.most_common(top_n)
    items = list(reversed(raw_items))
    if not items:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        return

    labels = [k for k, _ in items]
    values = [v for _, v in items]

    bars = ax.barh(labels, values, color=color, height=0.65, edgecolor="none")
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10, loc="left")
    ax.set_xlabel("Observations", fontsize=9)
    ax.tick_params(axis="both", labelsize=8.5)
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


def draw_stacked_horizontal_bar(
    ax: plt.Axes,
    matrix: dict[str, Counter[str]],
    category_specs: list[tuple[str, str]],
    title: str,
    palette: dict[str, str],
    top_groups: int = 8,
) -> None:
    """행 그룹별 하위 범주 누적 막대그래프를 그립니다. category_specs는 (원본값, 범례표시명) 리스트입니다."""
    group_totals = {grp: sum(cnts.values()) for grp, cnts in matrix.items()}
    ordered_groups = [
        grp
        for grp, _ in sorted(group_totals.items(), key=lambda x: x[1], reverse=True)[:top_groups]
    ]
    ordered_groups = list(reversed(ordered_groups))

    if not ordered_groups:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10, loc="left")
        return

    y_pos = list(range(len(ordered_groups)))
    lefts = [0] * len(ordered_groups)

    for raw_cat, display_label in category_specs:
        vals = [matrix[grp][raw_cat] for grp in ordered_groups]
        if sum(vals) == 0:
            continue
        ax.barh(
            y_pos,
            vals,
            left=lefts,
            height=0.62,
            label=display_label,
            color=palette.get(raw_cat, "#718096"),
            edgecolor="none",
        )
        lefts = [l + v for l, v in zip(lefts, vals)]

    ax.set_yticks(y_pos)
    ax.set_yticklabels(ordered_groups, fontsize=8.5)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=10, loc="left")
    ax.set_xlabel("Observations", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    max_total = max(lefts) if lefts else 1
    ax.set_xlim(0, max_total * 1.15)
    for idx, tot in enumerate(lefts):
        ax.text(
            tot + max_total * 0.02,
            idx,
            str(tot),
            va="center",
            ha="left",
            fontsize=8.5,
            color="#222222",
        )

    ax.legend(loc="lower right", fontsize=7.5, frameon=True, facecolor="white", framealpha=0.88)


def print_marker_comparison_table(rows: list[dict[str, str]]) -> None:
    """senolytic vs partial_reprogramming 마커별 건수와 주요 direction을 콘솔에 출력합니다."""
    table_rows = build_marker_comparison_rows(rows)

    print("\n=== Senolytic vs Partial Reprogramming (Marker Comparison) ===")
    print(f"  {'Marker':<24} | {'Senolytic':>9} | {'Partial_Reprog':>14} | Top Direction (S / PR)")
    print(f"  {'-' * 24}-+-{'-' * 9}-+-{'-' * 14}-+-{'-' * 32}")

    for marker, s_cnt, p_cnt, s_dir, p_dir in table_rows:
        print(f"  {marker:<24} | {s_cnt:>9} | {p_cnt:>14} | {s_dir} / {p_dir}")


def make_marker_comparison_figure(
    total_rows: int,
    paper_count: int,
    rows: list[dict[str, str]],
    out_path: Path,
) -> None:
    """senolytic과 partial_reprogramming 간 마커 비교 그래프를 생성합니다."""
    marker_order_counter: Counter[str] = Counter()
    seno_counts: Counter[str] = Counter()
    reprog_counts: Counter[str] = Counter()

    for r in rows:
        itype = r.get("intervention_type", "")
        marker = r.get("marker_or_endpoint") or "(empty)"
        if itype == "senolytic":
            seno_counts[marker] += 1
            marker_order_counter[marker] += 1
        elif itype == "partial_reprogramming":
            reprog_counts[marker] += 1
            marker_order_counter[marker] += 1

    markers = list(reversed([m for m, _ in marker_order_counter.most_common()]))
    if not markers:
        markers = ["(no matched markers)"]
    s_vals = [seno_counts[m] for m in markers]
    p_vals = [reprog_counts[m] for m in markers]

    fig_height = max(5.0, min(10.0, 0.55 * len(markers) + 2.0))
    fig, ax = plt.subplots(figsize=(11.5, fig_height), dpi=200)

    y_idx = list(range(len(markers)))
    bar_h = 0.36

    bars_s = ax.barh(
        [y - bar_h / 2 for y in y_idx],
        s_vals,
        height=bar_h,
        label="senolytic",
        color="#2B6CB0",
    )
    bars_p = ax.barh(
        [y + bar_h / 2 for y in y_idx],
        p_vals,
        height=bar_h,
        label="partial_reprogramming",
        color="#805AD5",
    )

    ax.set_yticks(y_idx)
    ax.set_yticklabels(markers, fontsize=9)
    ax.set_xlabel("Observations", fontsize=9.5)
    ax.set_title(
        f"Senolytic vs. Partial Reprogramming by Marker ({total_rows} obs across {paper_count} papers)",
        fontsize=12.5,
        fontweight="bold",
        loc="left",
        pad=12,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    max_v = max([1, *s_vals, *p_vals])
    ax.set_xlim(0, max_v * 1.16)

    for b in bars_s:
        w = b.get_width()
        if w > 0:
            ax.text(w + max_v * 0.015, b.get_y() + b.get_height() / 2, str(int(w)), va="center", ha="left", fontsize=8)
    for b in bars_p:
        w = b.get_width()
        if w > 0:
            ax.text(w + max_v * 0.015, b.get_y() + b.get_height() / 2, str(int(w)), va="center", ha="left", fontsize=8)

    ax.legend(loc="lower right", fontsize=9, frameon=True, facecolor="white", framealpha=0.9)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"마커 비교 그림 저장 완료 -> {out_path}")


def make_overview_figure(
    total_rows: int,
    paper_count: int,
    rows: list[dict[str, str]],
    out_path: Path,
) -> None:
    by_itype: Counter[str] = Counter()
    by_cell: Counter[str] = Counter()
    by_safety: Counter[str] = Counter()

    for r in rows:
        by_itype[r.get("intervention_type") or "(empty)"] += 1
        by_cell[r.get("cell_type") or "(empty)"] += 1
        by_safety[r.get("safety_flag") or "(empty)"] += 1

    max_rows = max(len(by_itype), len(by_cell), len(by_safety), 6)
    fig_height = max(4.8, min(12.0, 0.42 * max_rows + 1.8))

    fig, axes = plt.subplots(1, 3, figsize=(15.5, fig_height), dpi=200)
    fig.suptitle(
        f"Aging Intervention DB Summary ({total_rows} observations across {paper_count} papers)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    draw_horizontal_bar(axes[0], by_itype, "By Intervention Type", color="#2B6CB0", top_n=None)
    draw_horizontal_bar(axes[1], by_cell, "All Cell Types", color="#2F855A", top_n=None)
    draw_horizontal_bar(axes[2], by_safety, "By Safety Flag", color="#C05621", top_n=None)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"기본 요약 그림 저장 완료 -> {out_path}")


def make_extended_figure(
    total_rows: int,
    paper_count: int,
    rows: list[dict[str, str]],
    out_path: Path,
) -> None:
    itype_by_safety: dict[str, Counter[str]] = defaultdict(Counter)
    itype_by_aspect: dict[str, Counter[str]] = defaultdict(Counter)

    for r in rows:
        itype = r.get("intervention_type") or "unknown"
        aspect = r.get("aspect_category") or "unknown"
        safety = r.get("safety_flag") or "none_reported"

        itype_by_safety[itype][safety] += 1
        itype_by_aspect[itype][aspect] += 1

    safety_specs = [
        ("none_reported", "none_reported (no direct mention in abstract)"),
        ("potential_toxicity", "potential_toxicity"),
        ("oncogenic_risk", "oncogenic_risk"),
        ("mixed_or_unclear", "mixed_or_unclear"),
    ]
    safety_palette = {
        "none_reported": "#4A5568",
        "potential_toxicity": "#DD6B20",
        "oncogenic_risk": "#C53030",
        "mixed_or_unclear": "#D69E2E",
    }

    aspect_specs = [
        ("aging_marker", "aging_marker"),
        ("senescence_clearance", "senescence_clearance"),
        ("rejuvenation_phenotype", "rejuvenation_phenotype"),
        ("toxicity", "toxicity"),
        ("oncogenesis", "oncogenesis"),
    ]
    aspect_palette = {
        "aging_marker": "#2B6CB0",
        "senescence_clearance": "#2F855A",
        "rejuvenation_phenotype": "#6B46C1",
        "toxicity": "#DD6B20",
        "oncogenesis": "#C53030",
    }

    fig, axes = plt.subplots(1, 2, figsize=(15.0, 5.2), dpi=200)
    fig.suptitle(
        f"Intervention Context Breakdown ({total_rows} observations across {paper_count} papers)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    draw_stacked_horizontal_bar(
        axes[0],
        itype_by_safety,
        safety_specs,
        "Intervention Type x Safety Flag",
        safety_palette,
    )
    draw_stacked_horizontal_bar(
        axes[1],
        itype_by_aspect,
        aspect_specs,
        "Intervention Type x Measured Aspect",
        aspect_palette,
    )

    fig.text(
        0.01,
        0.01,
        "Note: none_reported indicates no direct mention of toxicity or oncogenesis in the abstract (not proof of safety).",
        fontsize=8.5,
        color="#4A5568",
    )

    fig.tight_layout(rect=[0, 0.04, 1, 0.93])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"확장 분석 그림 저장 완료 -> {out_path}")


def main() -> int:
    csv_path = Path("data/curated/observations.csv")
    if not csv_path.exists():
        print(f"CSV 파일을 찾을 수 없습니다: {csv_path}")
        return 1

    total_rows, paper_count, rows = load_observations(csv_path)

    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False

    print_marker_comparison_table(rows)
    make_overview_figure(
        total_rows, paper_count, rows, Path("assets/summary_overview.png")
    )
    make_extended_figure(
        total_rows, paper_count, rows, Path("assets/summary_extended.png")
    )
    make_marker_comparison_figure(
        total_rows, paper_count, rows, Path("assets/summary_markers_comparison.png")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())