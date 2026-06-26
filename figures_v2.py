"""
figures_v2.py
Nobel-style figure overhaul for the Liberation Day thesis.

Six main-text figures + three appendix figures, all matplotlib-based with
publication-grade defaults. No internal plot titles (titles live in LaTeX
captions). Direct line labels over legends. Vector PDF + PNG output.

Run with:
    python figures_v2.py
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mtick

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent
PROCESSED = BASE / "data" / "processed"
RAW = BASE / "data" / "raw"
OUTPUTS = BASE / "outputs"
FIGURES = BASE / "figures"
FIGURES.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# House style (Matplotlib-only, no Proplot dependency)
# ---------------------------------------------------------------------------
NAVY = "#12354e"
SIENNA = "#ae5224"
GRAY = "#888888"
LIGHT_GRAY = "#E0E0E0"
VERY_LIGHT = "#F6F6F6"
TEXT = "#111314"

plt.rcParams.update({
    "font.family":        "STIXGeneral",
    "mathtext.fontset":   "stix",
    "font.size":           9,
    "axes.labelsize":      9,
    "axes.titlesize":     10,
    "xtick.labelsize":     8,
    "ytick.labelsize":     8,
    "legend.fontsize":     8,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.edgecolor":     "#333333",
    "axes.labelcolor":    TEXT,
    "text.color":         TEXT,
    "xtick.color":        TEXT,
    "ytick.color":        TEXT,
    "axes.linewidth":      0.7,
    "lines.linewidth":     1.8,
    "savefig.dpi":       300,
    "figure.dpi":        150,
    "axes.titlepad":       8,
    "axes.titleweight":   "normal",
    "figure.facecolor":   "white",
    "axes.facecolor":     "white",
})


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def require_columns(df: pd.DataFrame, cols: list, fig_name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{fig_name}: missing required columns: {missing}")


def filter_low_denominators(df: pd.DataFrame, value_col: str,
                            min_value: float = 10_000_000) -> pd.DataFrame:
    """Filter out country-months with tiny denominators (avoid ratio noise)."""
    return df[df[value_col] >= min_value].copy()


def load_main_coefficient() -> tuple[float, float]:
    """Load the public main estimate and clustered standard error."""
    coef_path = OUTPUTS / "regression_coefficients.csv"
    if coef_path.exists():
        coef = pd.read_csv(coef_path)
        row = coef.loc[coef["variable"].eq("log_etr1")].iloc[0]
        return float(row["estimate"]), float(row["std_error_cluster"])

    import json
    v2_path = OUTPUTS / "regression_results_v2.json"
    if v2_path.exists():
        v2 = json.loads(v2_path.read_text())
        return float(v2["main_top40"]["beta"]), float(v2["main_top40"]["se"])

    raise FileNotFoundError(
        "Figure C needs outputs/regression_coefficients.csv, which is part of "
        "the public release, or the optional local regression_results_v2.json."
    )


def save_fig(fig, stem: str) -> None:
    pdf_path = FIGURES / f"{stem}.pdf"
    png_path = FIGURES / f"{stem}.png"
    fig.savefig(pdf_path, format="pdf", bbox_inches="tight")
    fig.savefig(png_path, format="png", dpi=300, bbox_inches="tight")
    print(f"  saved {stem}.pdf and {stem}.png")


def despine(ax, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if grid_axis == "y":
        ax.yaxis.grid(True, color=LIGHT_GRAY, linewidth=0.5, zorder=0)
        ax.xaxis.grid(False)
    elif grid_axis == "x":
        ax.xaxis.grid(True, color=LIGHT_GRAY, linewidth=0.5, zorder=0)
        ax.yaxis.grid(False)
    elif grid_axis == "both":
        ax.grid(True, color=LIGHT_GRAY, linewidth=0.5, zorder=0)
    else:
        ax.grid(False)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def load_etr() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "realized_etr_by_country_month.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M")
    return df


def load_panel() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "gravity_event_study_panel.csv", low_memory=False)
    if "date" not in df.columns and "TIME_PERIOD" in df.columns:
        df["date"] = pd.to_datetime(
            df["TIME_PERIOD"].astype(str).str.replace(r"-M(\d+)", r"-\1", regex=True)
        )
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_diversion() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "trade_diversion_indicators.csv")


def load_sectors() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "sector_exemption_map.csv")


# ---------------------------------------------------------------------------
# Figure I: Policy Timeline and Estimation Windows
# ---------------------------------------------------------------------------
def fig_policy_timeline() -> None:
    print("Figure I: Policy timeline and estimation windows")
    fig, ax = plt.subplots(figsize=(11.5, 4.4))

    # Extend the x-axis back to February 2025 to fit the policy-review event
    # and forward to October 2025 so the August events sit clear of the right edge.
    x_min = pd.Timestamp("2025-02-01")
    x_max = pd.Timestamp("2025-11-01")

    # background shading for estimation windows
    ax.axvspan(x_min, pd.Timestamp("2025-04-02"),
               color=LIGHT_GRAY, alpha=0.35, zorder=0)
    ax.axvspan(pd.Timestamp("2025-04-02"), pd.Timestamp("2025-07-01"),
               color=SIENNA, alpha=0.10, zorder=0)
    ax.axvspan(pd.Timestamp("2025-07-01"), x_max,
               color=NAVY, alpha=0.08, zorder=0)

    # window labels at top
    ax.text(pd.Timestamp("2025-03-05"), 0.96, "Pre-shock baseline",
            ha="center", fontsize=8.5, color=GRAY)
    ax.text(pd.Timestamp("2025-05-15"), 0.96, "Shock window",
            ha="center", fontsize=8.5, color=SIENNA)
    ax.text(pd.Timestamp("2025-09-01"), 0.96, "Post-adjustment",
            ha="center", fontsize=8.5, color=NAVY)

    # central timeline
    ax.axhline(0.4, xmin=0.02, xmax=0.98, color=TEXT, linewidth=1.5, zorder=2)

    # Major events get full label boxes; minor events appear only as small
    # tick marks with a date label below the line. Heights stagger to keep
    # label boxes from colliding when events are close in time.
    events = [
        ("2025-04-02", "Apr 2",  "EO 14257\nsigned",                  0.86, NAVY),
        ("2025-04-09", "Apr 9",  "90-day pause;\nChina escalates",    0.58, SIENNA),
        ("2025-05-14", "May 14", "US-China deal\neffective",          0.86, NAVY),
        ("2025-07-07", "Jul 7",  "Pause extended\nto Aug 1",          0.14, SIENNA),
        ("2025-08-07", "Aug 7",  "Revised country\nrates effective",  0.86, NAVY),
    ]
    # Minor events: small ticks with date-only labels below the spine.
    minor_events = [
        ("2025-02-13", "Feb 13", "Review ordered"),
        ("2025-04-05", "Apr 5",  "Baseline 10\\% effective"),
        ("2025-04-11", "Apr 11", "Tech exclusion guidance"),
        ("2025-04-22", "Apr 22", "Tech carve-out clarified"),
        ("2025-05-12", "May 12", "US-China deal announced"),
        ("2025-07-31", "Jul 31", "EO 14326 signed"),
        ("2025-08-12", "Aug 12", "China truce to Nov 10"),
    ]
    # Draw minor events first (under everything) as small ticks with date
    # and short label rotated below the spine.
    for date_str, short_date, sub_label in minor_events:
        d = pd.Timestamp(date_str)
        # short tick mark
        ax.plot([d, d], [0.38, 0.42], color=GRAY, linewidth=1.0, zorder=3)
        # date label just below the spine, no box
        ax.text(d, 0.31, short_date, ha="center", va="top",
                fontsize=6.8, color=GRAY)
        # sub-label rotated to fit
        ax.text(d, 0.21, sub_label, ha="center", va="top",
                fontsize=6.5, color=GRAY, rotation=35,
                rotation_mode="anchor")

    # Draw major events on top with full label boxes
    for date_str, short_date, label, ypos, col in events:
        d = pd.Timestamp(date_str)
        ax.plot([d, d], [0.34, 0.46], color=col, linewidth=2.2, zorder=4)
        # leader line
        ax.plot([d, d], [0.4, ypos], color=col, linewidth=0.9,
                linestyle=":", zorder=3)
        va = "bottom" if ypos > 0.5 else "top"
        ax.text(d, ypos, label, ha="center", va=va, fontsize=8,
                color=col,
                bbox=dict(boxstyle="round,pad=0.22", facecolor="white",
                          edgecolor=col, linewidth=0.7),
                zorder=5)
        # short date label right at the spine
        if ypos > 0.5:
            ax.text(d, 0.48, short_date, ha="center", va="bottom",
                    fontsize=7.5, color=col, fontweight="bold")
        else:
            ax.text(d, 0.32, short_date, ha="center", va="top",
                    fontsize=7.5, color=col, fontweight="bold")

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", which="both", length=0, labelsize=8)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    fig.tight_layout(pad=1.4)
    save_fig(fig, "fig01_policy_timeline")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure II: Announced vs. Realized Tariff Exposure (flagship)
# ---------------------------------------------------------------------------
def fig_announced_vs_realized() -> None:
    print("Figure II: Announced vs realized tariff exposure")
    etr = load_etr()
    require_columns(etr, ["date", "ETR", "GEN_VAL_MO"], "Fig II")

    # filter low denominators
    etr_f = filter_low_denominators(etr, "GEN_VAL_MO", min_value=1_000_000)

    # Panel A: US-wide import-weighted realized ETR vs. simple announced rate
    monthly = (etr_f.groupby("date")
                    .apply(lambda d: pd.Series({
                        "realized_wtd": (d["DUT_VAL_MO"].sum() / d["GEN_VAL_MO"].sum()),
                        "realized_unwtd": d["ETR"].mean(),
                    }))
                    .reset_index())
    # synthetic announced rate: 0% pre-Apr 2025, then steps to 10% Apr, 9.6% per Faj-Khan
    monthly["announced"] = 0.015  # baseline pre-period
    monthly.loc[monthly["date"] >= "2025-04-02", "announced"] = 0.10
    monthly.loc[monthly["date"] >= "2025-04-09", "announced"] = 0.096  # weighted post-pause

    # China: pull China-specific ETR
    china = etr_f[etr_f["CTY_NAME"].str.contains("CHINA", case=False, na=False)].copy()
    china_monthly = china.groupby("date")["ETR"].mean().reset_index()
    china_monthly.columns = ["date", "realized"]
    china_monthly["announced"] = 0.034
    china_monthly.loc[china_monthly["date"] >= "2025-04-02", "announced"] = 0.34
    china_monthly.loc[china_monthly["date"] >= "2025-04-09", "announced"] = 1.45
    china_monthly.loc[china_monthly["date"] >= "2025-05-14", "announced"] = 0.30

    # Restrict to 2024-2025 for visual focus
    monthly_plot = monthly[monthly["date"] >= "2024-01-01"]
    china_plot = china_monthly[china_monthly["date"] >= "2024-01-01"]

    fig, axes = plt.subplots(ncols=2, figsize=(11, 4.2), sharey=False)
    # Panel A: US average
    ax = axes[0]
    ax.plot(monthly_plot["date"], monthly_plot["announced"] * 100,
            linestyle="--", color=SIENNA, linewidth=2.0)
    ax.plot(monthly_plot["date"], monthly_plot["realized_wtd"] * 100,
            linestyle="-", color=NAVY, linewidth=2.0)
    # shaded gap
    ax.fill_between(monthly_plot["date"],
                    monthly_plot["realized_wtd"] * 100,
                    monthly_plot["announced"] * 100,
                    where=(monthly_plot["announced"] >= monthly_plot["realized_wtd"]),
                    color=SIENNA, alpha=0.10, zorder=0)
    # event line
    ax.axvline(pd.Timestamp("2025-04-02"), color=GRAY, linewidth=0.8,
               linestyle=":", zorder=1)
    # direct labels
    last = monthly_plot.iloc[-1]
    ax.text(last["date"], last["announced"] * 100 + 0.3, "Announced",
            color=SIENNA, fontsize=9, va="bottom", ha="right")
    ax.text(last["date"], last["realized_wtd"] * 100 - 0.3, "Realized",
            color=NAVY, fontsize=9, va="top", ha="right")
    ax.text(pd.Timestamp("2025-04-02"), ax.get_ylim()[1] * 0.95,
            " Apr 2", color=GRAY, fontsize=7.5, va="top", ha="left")
    ax.set_ylabel("Tariff rate (percent)")
    ax.text(0.02, 0.95, "(a) US average", transform=ax.transAxes,
            fontsize=9.5, fontweight="bold", va="top")
    despine(ax, grid_axis="y")

    # Panel B: China-specific
    ax = axes[1]
    ax.plot(china_plot["date"], china_plot["announced"] * 100,
            linestyle="--", color=SIENNA, linewidth=2.0)
    ax.plot(china_plot["date"], china_plot["realized"] * 100,
            linestyle="-", color=NAVY, linewidth=2.0)
    ax.fill_between(china_plot["date"],
                    china_plot["realized"] * 100,
                    china_plot["announced"] * 100,
                    where=(china_plot["announced"] >= china_plot["realized"]),
                    color=SIENNA, alpha=0.10, zorder=0)
    ax.axvline(pd.Timestamp("2025-04-22"), color=GRAY, linewidth=0.8,
               linestyle=":", zorder=1)
    ax.text(pd.Timestamp("2025-04-22"), ax.get_ylim()[1] * 0.85,
            " Tech\n exemption", color=GRAY, fontsize=7.5,
            va="top", ha="left")
    lastc = china_plot.iloc[-1]
    ax.text(lastc["date"], lastc["announced"] * 100, " Announced",
            color=SIENNA, fontsize=9, va="bottom", ha="right")
    ax.text(lastc["date"], lastc["realized"] * 100, " Realized",
            color=NAVY, fontsize=9, va="top", ha="right")
    ax.set_ylabel("Tariff rate (percent)")
    ax.text(0.02, 0.95, "(b) China", transform=ax.transAxes,
            fontsize=9.5, fontweight="bold", va="top")
    despine(ax, grid_axis="y")

    import matplotlib.dates as mdates
    for ax in axes:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        for label in ax.get_xticklabels():
            label.set_rotation(0)

    fig.tight_layout(pad=1.4)
    save_fig(fig, "fig02_announced_vs_realized")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure III: Sector composition with tariff status
# (Simpler version: sectors ordered by rate + status, since HS2 China-import
#  values are not in the current processed panel.)
# ---------------------------------------------------------------------------
def fig_sector_composition() -> None:
    print("Figure III: Sector composition and tariff status")
    df = load_sectors()
    require_columns(df, ["hs2_chapter", "description", "tariffed",
                         "approx_rate_pct"], "Fig III")
    df = df.copy()
    df["rate"] = pd.to_numeric(df["approx_rate_pct"], errors="coerce").fillna(0)
    df["is_tariffed"] = df["tariffed"].astype(str).str.lower().str.strip() == "true"
    # sort: exempt first, then tariffed by rate
    df = df.sort_values(["is_tariffed", "rate"], ascending=[True, True])

    fig, ax = plt.subplots(figsize=(9, max(4.5, len(df) * 0.42 + 1.2)))
    y = np.arange(len(df))

    colors = [NAVY if t else LIGHT_GRAY for t in df["is_tariffed"]]
    bars = ax.barh(y, df["rate"], color=colors, edgecolor="none", height=0.62)

    # rate labels at end of each bar
    for i, (rate, tariffed) in enumerate(zip(df["rate"], df["is_tariffed"])):
        label = f"{int(rate)}%" if rate > 0 else "exempt"
        ax.text(rate + 0.5, i, label, va="center", ha="left",
                fontsize=8.5, color=TEXT)

    ax.set_yticks(y)
    ax.set_yticklabels([f"HS {int(c)}: {d}" for c, d in
                        zip(df["hs2_chapter"], df["description"])],
                       fontsize=8.5)
    ax.set_xlabel("Tariff rate (percent)")
    ax.set_xlim(0, max(df["rate"].max() + 5, 30))

    # legend below
    handles = [
        mpatches.Patch(facecolor=NAVY, edgecolor="none", label="Tariffed"),
        mpatches.Patch(facecolor=LIGHT_GRAY, edgecolor="none", label="Exempt"),
    ]
    ax.legend(handles=handles, loc="upper center",
              bbox_to_anchor=(0.5, -0.10), ncol=2, frameon=False)

    despine(ax, grid_axis="x")
    ax.spines["left"].set_visible(False)
    fig.tight_layout(pad=1.4)
    fig.subplots_adjust(bottom=0.12)
    save_fig(fig, "fig03_sector_composition")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure IV: Distribution of realized ETR by period
# ---------------------------------------------------------------------------
def fig_etr_distribution() -> None:
    print("Figure IV: Distribution of realized ETR by period")
    etr = load_etr()
    require_columns(etr, ["date", "ETR", "GEN_VAL_MO"], "Fig IV")

    # Filter low denominators
    etr_f = filter_low_denominators(etr, "GEN_VAL_MO", min_value=10_000_000)
    # Cap extreme ETR at 50% for visual clarity (already capped at 2.0 in data)
    etr_f["ETR_pct"] = (etr_f["ETR"] * 100).clip(0, 50)

    # Define periods
    def _period(d):
        if d < pd.Timestamp("2025-04-02"):
            return "Pre-shock\n(2020-Mar 2025)"
        elif d < pd.Timestamp("2025-07-01"):
            return "Shock window\n(Apr-Jun 2025)"
        else:
            return "Post-adjustment\n(Jul 2025+)"
    etr_f["period"] = etr_f["date"].apply(_period)

    periods = ["Pre-shock\n(2020-Mar 2025)",
               "Shock window\n(Apr-Jun 2025)",
               "Post-adjustment\n(Jul 2025+)"]
    data_by_period = [etr_f.loc[etr_f["period"] == p, "ETR_pct"].dropna().values
                      for p in periods]

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    box = ax.boxplot(data_by_period, vert=True, widths=0.55,
                     patch_artist=True,
                     showfliers=False,
                     medianprops=dict(color=TEXT, linewidth=1.5),
                     boxprops=dict(linewidth=0.8),
                     whiskerprops=dict(color=GRAY, linewidth=0.8),
                     capprops=dict(color=GRAY, linewidth=0.8))

    colors = [LIGHT_GRAY, SIENNA, NAVY]
    for patch, col in zip(box["boxes"], colors):
        patch.set_facecolor(col)
        patch.set_alpha(0.55 if col != LIGHT_GRAY else 0.9)
        patch.set_edgecolor(TEXT)

    # add import-weighted mean as a diamond marker
    for i, p in enumerate(periods, start=1):
        sub = etr_f[etr_f["period"] == p]
        if len(sub) > 0:
            wtd = (sub["DUT_VAL_MO"].sum() / sub["GEN_VAL_MO"].sum()) * 100
            ax.scatter([i], [wtd], marker="D", s=55, color=TEXT,
                       edgecolor="white", linewidth=1.2, zorder=4,
                       label="Import-weighted mean" if i == 1 else None)

    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(periods, fontsize=9)
    ax.set_ylabel("Realized ETR (percent)")
    ax.set_ylim(0, 30)
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    despine(ax, grid_axis="y")
    fig.tight_layout(pad=1.4)
    save_fig(fig, "fig04_etr_distribution")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure V: Import dynamics by exposure group (event study)
# ---------------------------------------------------------------------------
def fig_event_study() -> None:
    print("Figure V: Import dynamics by exposure group")
    panel = load_panel()
    etr = load_etr()

    # Map Census country names to IMF partner codes via fuzzy match on
    # iso-style codes is complex; use direct name keys for the largest partners.
    big_partners = {
        "CN": "CHINA",
        "MX": "MEXICO",
        "CA": "CANADA",
        "VN": "VIETNAM",
        "DE": "GERMANY",
        "JP": "JAPAN",
        "KR": "KOREA, SOUTH",
        "IN": "INDIA",
        "TW": "TAIWAN",
        "GB": "UNITED KINGDOM",
        "IT": "ITALY",
        "FR": "FRANCE",
        "MY": "MALAYSIA",
        "TH": "THAILAND",
        "ID": "INDONESIA",
    }

    # Build a US-imports-only subset of the panel
    if "reporter" in panel.columns and "indicator" in panel.columns:
        panel_us = panel[(panel["reporter"] == "US") &
                         (panel["indicator"] == "TMG_CIF_USD")].copy()
    else:
        panel_us = panel.copy()

    # ISO3 to ISO2 map for the panel
    iso3_to_iso2 = {"CHN": "CN", "MEX": "MX", "CAN": "CA", "VNM": "VN",
                    "DEU": "DE", "JPN": "JP", "KOR": "KR", "IND": "IN",
                    "TWN": "TW", "GBR": "GB", "ITA": "IT", "FRA": "FR",
                    "MYS": "MY", "THA": "TH", "IDN": "ID"}
    panel_us["iso2"] = panel_us["COUNTERPART_AREA"].astype(str).map(iso3_to_iso2)

    # Compute 2025 average ETR per partner to assign exposure quartile
    etr_2025 = etr[etr["date"] >= "2025-04-02"].groupby("CTY_NAME")["ETR"].mean()
    # Map iso2 -> Census name via the big_partners dict
    iso2_to_etr = {iso2: etr_2025.get(name, np.nan)
                   for iso2, name in big_partners.items()}
    panel_us["partner_etr"] = panel_us["iso2"].map(iso2_to_etr)

    # Group: China separate; rest into terciles by exposure
    panel_us = panel_us.dropna(subset=["partner_etr", "iso2"]).copy()
    non_china = panel_us[panel_us["iso2"] != "CN"]
    if len(non_china) == 0:
        print("  no data for event study; skipping")
        return
    terciles = pd.qcut(non_china["partner_etr"], q=3,
                       labels=["Low exposure", "Medium exposure", "High exposure"])
    panel_us["group"] = "China"
    panel_us.loc[panel_us["iso2"] != "CN", "group"] = terciles.astype(str).values

    # Index US imports per partner to pre-shock 2024 average = 100
    pre = panel_us[(panel_us["date"] >= "2024-01-01") &
                   (panel_us["date"] < "2025-04-01")]
    base = pre.groupby("iso2")["OBS_VALUE"].mean().rename("base")
    panel_us = panel_us.merge(base, on="iso2", how="left")
    panel_us["index"] = 100 * panel_us["OBS_VALUE"] / panel_us["base"]

    # Restrict to 12 months pre + 9 months post around April 2025
    panel_us["months_rel"] = ((panel_us["date"].dt.year - 2025) * 12 +
                              panel_us["date"].dt.month - 4)
    panel_us = panel_us[(panel_us["months_rel"] >= -12) &
                        (panel_us["months_rel"] <= 8)]

    # Group means with bootstrap-like 95% bands (1.96 * SE of mean)
    agg = (panel_us.groupby(["group", "months_rel"])["index"]
                   .agg(["mean", "std", "count"])
                   .reset_index())
    agg["se"] = agg["std"] / np.sqrt(agg["count"].clip(lower=1))
    agg["lo"] = agg["mean"] - 1.96 * agg["se"]
    agg["hi"] = agg["mean"] + 1.96 * agg["se"]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    colors = {
        "High exposure": NAVY,
        "Medium exposure": SIENNA,
        "Low exposure": GRAY,
        "China": "#4A1F2B",
    }
    for group_name, col in colors.items():
        sub = agg[agg["group"] == group_name].sort_values("months_rel")
        if sub.empty:
            continue
        ls = "--" if group_name == "China" else "-"
        ax.plot(sub["months_rel"], sub["mean"], color=col,
                linewidth=2.0, linestyle=ls, label=group_name)
        ax.fill_between(sub["months_rel"], sub["lo"], sub["hi"],
                        color=col, alpha=0.12, zorder=1)

    # event line at zero
    ax.axvline(0, color=TEXT, linewidth=0.8, linestyle=":", zorder=1)
    ax.axhline(100, color=GRAY, linewidth=0.5, zorder=1)
    ax.text(0.2, ax.get_ylim()[1] * 0.95, "Apr 2025",
            fontsize=8, color=TEXT, va="top")

    ax.set_xlabel("Months relative to April 2025")
    ax.set_ylabel("US imports (pre-shock 2024 = 100)")
    ax.set_xlim(-12, 8)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    despine(ax, grid_axis="y")
    fig.tight_layout(pad=1.4)
    save_fig(fig, "fig05_event_study")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure VI: Trade diversion quadrant plot
# ---------------------------------------------------------------------------
_DIVERSION_CAT_COLOR = {
    "double_winner": NAVY,
    "us_diversion_recipient": SIENNA,
    "collateral_damage": GRAY,
    "neutral": LIGHT_GRAY,
}
_DIVERSION_CAT_MARKER = {
    "double_winner": "o",            # circle
    "us_diversion_recipient": "^",   # triangle
    "collateral_damage": "s",        # square
    "neutral": "o",                  # small dot
}
_IMTS_AGGREGATE_NAMES = {
    "G001": "World total", "G110": "Advanced econ.", "G200": "Emerging mkt.",
    "G092": "Other adv.", "G505": "Asia agg.", "G998": "Special trade",
    "G163": "EU agg.", "G205": "Other emrg.", "G080": "MENA agg.",
    "G400": "Sub-Sah. Africa", "G603": "ASEAN agg.", "G903": "Western Hem.",
    "GX170": "EU export grp.", "GX605": "Asia export grp.", "GX440": "Pac. Rim grp.",
    "GX405": "Latin Am. grp.", "GX901": "Special grp.", "GCANCEX": "Cancun excl.",
}


def _draw_diversion_panel(ax, plot_df, scale_max, *, n_labels, title, show_legend,
                          force_label_countries: list[str] | None = None,
                          label_mode: str = "leader"):
    """
    Draw one trade-diversion quadrant panel. plot_df is the subset of points to
    scatter; scale_max is the max q1_trade_usd across the FULL sample so bubble
    sizes are comparable between the two panels. n_labels controls how many
    out-of-band points get leader-arrow labels (0 = no labels).

    force_label_countries: explicit list of partner codes to label regardless of
        whether they sit in the neutral band. Used to label top-N-per-category on
        the All-Partners panel and to label every point on the Top-40 panel.
    label_mode: "leader" puts labels around the perimeter with leader arrows
        (good for sparse labelling); "direct" puts the country code right next
        to the bubble in a small white-haloed font (good when every point is
        labeled and leader-line crossings would be unreadable).
    """
    import matplotlib.patheffects as pe

    # Shaded neutral band ±5% + quadrant threshold lines
    ax.axvspan(-5, 5, color=VERY_LIGHT, alpha=0.6, zorder=0)
    ax.axhspan(-5, 5, color=VERY_LIGHT, alpha=0.6, zorder=0)
    for v in (5, -5):
        ax.axvline(v, color=GRAY, linewidth=0.7, linestyle="--", zorder=1)
        ax.axhline(v, color=GRAY, linewidth=0.7, linestyle="--", zorder=1)

    # Plot each category with its shape; neutral plotted first (background)
    for cat in ["neutral", "collateral_damage", "us_diversion_recipient", "double_winner"]:
        sub = plot_df[plot_df["category"] == cat]
        if sub.empty:
            continue
        col = _DIVERSION_CAT_COLOR.get(cat, LIGHT_GRAY)
        m = _DIVERSION_CAT_MARKER.get(cat, "o")
        s_factor = 0.4 if cat == "neutral" else 1.0
        ax.scatter(sub["x"], sub["y"],
                   s=np.sqrt(sub["q1_trade_usd"].clip(lower=1).values) /
                     np.sqrt(scale_max) * 220 * s_factor + 12,
                   c=col, marker=m,
                   edgecolor=TEXT if cat != "neutral" else "none",
                   linewidth=0.4, alpha=0.85 if cat != "neutral" else 0.4,
                   zorder=3 + (cat != "neutral"))

    # Quadrant labels, inward, white box so they stay readable over points
    box = dict(facecolor="white", edgecolor="none", alpha=0.92, pad=2)
    ax.text(245, 245, "Double\nwinners", fontsize=9, color=NAVY,
            ha="center", va="center", fontweight="bold", bbox=box)
    ax.text(245, -245, "US diversion\nonly", fontsize=9, color=SIENNA,
            ha="center", va="center", fontweight="bold", bbox=box)
    ax.text(-245, -245, "Collateral\ndamage", fontsize=9, color="#555555",
            ha="center", va="center", fontweight="bold", bbox=box)
    ax.text(-245, 245, "China substitution\nonly", fontsize=8.5, color=TEXT,
            ha="center", va="center", bbox=box)

    ax.annotate(
        r"neutral band $(\pm 5\%)$",
        xy=(0, 5), xytext=(0, 285),
        fontsize=7.5, color=GRAY, ha="center", va="bottom", style="italic",
        arrowprops=dict(arrowstyle="-", color=GRAY, linewidth=0.5,
                        linestyle="--", shrinkA=0, shrinkB=2),
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                  edgecolor="none", alpha=0.9),
        zorder=5,
    )

    # Labels.
    halo = [pe.withStroke(linewidth=2.6, foreground="white")]

    if force_label_countries is not None:
        labeled = plot_df[plot_df["country"].astype(str).isin(force_label_countries)].copy()
    else:
        out_of_band = plot_df[
            ((plot_df["x"].abs() > 5) | (plot_df["y"].abs() > 5))
            & plot_df["x"].notna() & plot_df["y"].notna()
        ]
        labeled = out_of_band.nlargest(n_labels, "q1_trade_usd") if n_labels else out_of_band.iloc[0:0]

    n = len(labeled)
    if n > 0 and label_mode == "leader":
        # Quadrant-anchored label placement: each label sits at an angle that
        # keeps it inside the same 90-degree quadrant as its data point. This
        # guarantees a Vietnam (double-winner, upper right) does not get
        # labelled inside the "China substitution" quadrant just because
        # np.linspace assigned it there. Within each quadrant the labels are
        # evenly spaced so neighbours never overlap each other.
        radius = 195
        labeled = labeled.copy()
        # Map each point to an angle in [0, 360).
        labeled["_angle"] = np.degrees(
            np.arctan2(labeled["y"].fillna(0), labeled["x"].fillna(0))
        ) % 360.0
        # Assign a quadrant index 0..3 from the angle: 0=top-right, 1=top-left,
        # 2=bottom-left, 3=bottom-right.
        labeled["_quad"] = (labeled["_angle"] // 90).astype(int)
        labeled = labeled.sort_values(["_quad", "_angle"]).reset_index(drop=True)
        # Inside each quadrant distribute labels uniformly across the 90-degree
        # arc. Padding keeps labels off the axis lines.
        pad_deg = 6.0
        placed_angles: list[float] = []
        for q, group in labeled.groupby("_quad", sort=True):
            m = len(group)
            base = int(q) * 90.0 + pad_deg
            span = 90.0 - 2 * pad_deg
            if m == 1:
                placed_angles.extend([base + span / 2.0])
            else:
                step = span / (m - 1)
                placed_angles.extend([base + i * step for i in range(m)])
        for placed_angle, (_, row) in zip(placed_angles, labeled.iterrows()):
            xt = radius * np.cos(np.radians(placed_angle))
            yt = radius * np.sin(np.radians(placed_angle))
            pt_color = _DIVERSION_CAT_COLOR.get(row["category"], LIGHT_GRAY)
            is_agg = (str(row["country"]).startswith("G")
                      and not str(row["country"]).isalpha())
            face_color = "#FFF7E6" if is_agg else "white"
            t = ax.annotate(
                str(row["display_label"]),
                xy=(row["x"], row["y"]), xytext=(xt, yt),
                fontsize=7, color=TEXT, ha="center", va="center",
                arrowprops=dict(arrowstyle="-", color=pt_color, linewidth=1.0,
                                linestyle="--", shrinkA=0, shrinkB=4,
                                connectionstyle="arc3,rad=0.12", alpha=0.85),
                bbox=dict(boxstyle="round,pad=0.22", facecolor=face_color,
                          edgecolor=pt_color, linewidth=0.8, alpha=0.95),
            )
            t.set_path_effects(halo)
    elif n > 0 and label_mode == "direct":
        # tight direct labels next to each bubble. small font, white halo so
        # overlaps remain readable. 40-point variant of the panel.
        for _, row in labeled.iterrows():
            pt_color = _DIVERSION_CAT_COLOR.get(row["category"], LIGHT_GRAY)
            # offset slightly up-right of the bubble
            t = ax.text(row["x"] + 7, row["y"] + 7, str(row["display_label"]),
                        fontsize=6.4, color=pt_color, fontweight="bold",
                        ha="left", va="bottom", zorder=6)
            t.set_path_effects(halo)

    if show_legend:
        legend_x, legend_y_base = -260, -180
        ax.text(legend_x, legend_y_base + 30, "Pre-shock trade volume:",
                fontsize=7, color=TEXT)
        for i, (val_label, rel_size) in enumerate([("\\$1bn", 30), ("\\$10bn", 90), ("\\$100bn", 200)]):
            x_pos = legend_x + 20 + i * 50
            ax.scatter(x_pos, legend_y_base, s=rel_size, color=NAVY, alpha=0.5,
                       edgecolor=TEXT, linewidth=0.4, zorder=4)
            ax.text(x_pos, legend_y_base - 20, val_label, fontsize=6.5,
                    color=TEXT, ha="center")

    ax.set_xlim(-310, 310)
    ax.set_ylim(-310, 310)
    ax.set_xlabel("Change in exports to US (percent, Q1 vs Q3 2025)")
    ax.set_ylabel("Change in imports from China (percent, Q1 vs Q3 2025)")
    ax.set_title(title, fontsize=10, color=TEXT)
    despine(ax, grid_axis="none")


def fig_diversion_quadrant() -> None:
    print("Figure VI: Trade diversion quadrant plot (two-panel)")
    df = load_diversion()
    require_columns(df, ["country", "pct_change_exports_to_US",
                         "pct_change_imports_from_CN", "category",
                         "q1_trade_usd"], "Fig VI")

    df = df.copy()
    # drop IMF aggregate counterparts (G001 World total, G110 Advanced econ, etc).
    # they dwarf real countries by trade value and would crowd out the country
    # labels the reviewer wants to see. Real partners are 3-letter ISO3 codes.
    df = df[df["country"].astype(str).str.fullmatch(r"[A-Z]{3}")].copy()
    df["x"] = df["pct_change_exports_to_US"].clip(-300, 300)   # winsorize at ±300%
    df["y"] = df["pct_change_imports_from_CN"].clip(-300, 300)
    df["q1_trade_usd"] = pd.to_numeric(df["q1_trade_usd"], errors="coerce").fillna(0)
    df["display_label"] = df["country"].astype(str)

    scale_max = float(np.sqrt(df["q1_trade_usd"].clip(lower=1).max()) ** 2)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 6.6))

    # left panel: full sample. Label the top 5 partners per category by
    # pre-shock trade volume so the reader can identify which countries drive
    # each quadrant without trying to read the whole 200+ point cloud.
    top5_per_cat = (
        df.sort_values("q1_trade_usd", ascending=False)
          .groupby("category", group_keys=False).head(5)
    )
    left_label_countries = top5_per_cat["country"].astype(str).tolist()
    _draw_diversion_panel(
        axL, df, scale_max, n_labels=0,
        title=f"All {len(df)} partner countries (top 5 per category labelled)",
        show_legend=True,
        force_label_countries=left_label_countries,
        label_mode="leader",
    )

    # right panel: top 40 by pre-shock trade value. Label the largest
    # out-of-band points (14 leader-arrow labels) plus every double-winner
    # among the top 40, since double winners are the visual focus of the
    # diversion classification and the reader needs to identify each one.
    top = df.nlargest(40, "q1_trade_usd")
    out_of_band_top14 = (
        top[((top["x"].abs() > 5) | (top["y"].abs() > 5))]
            .nlargest(14, "q1_trade_usd")["country"].astype(str).tolist()
    )
    double_winners_top40 = top[top["category"] == "double_winner"]["country"].astype(str).tolist()
    right_labels = list(dict.fromkeys(out_of_band_top14 + double_winners_top40))
    _draw_diversion_panel(
        axR, top, scale_max, n_labels=0,
        title="Top 40 partners by pre-shock trade value",
        show_legend=False,
        force_label_countries=right_labels,
        label_mode="leader",
    )

    fig.tight_layout(pad=1.4)
    save_fig(fig, "fig06_diversion_quadrant")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Appendix Figure A: Statutory vs. realized slopegraph
# ---------------------------------------------------------------------------
# ponytail: fig_slopegraph removed (not referenced in the thesis; figure II already covers
# the announced-vs-realized comparison with real Yale data, not synthetic per-country
# announced rates). Deleted on the country-month-ETR cleanup pass.

# ---------------------------------------------------------------------------
# Appendix Figure B: Pre-shock gravity diagnostic
# ---------------------------------------------------------------------------
def fig_gravity_diagnostic() -> None:
    print("Appendix Figure B: Pre-shock gravity diagnostic")
    # Use WEO + IMTS data already saved by the main pipeline
    weo_path = RAW / "imf_weo_apr2025.csv"
    if not weo_path.exists():
        print("  WEO file not found; skipping")
        return
    weo = pd.read_csv(weo_path)
    panel = load_panel()
    if "reporter" in panel.columns:
        panel = panel[(panel["reporter"] == "US") &
                      (panel["indicator"] == "TMG_CIF_USD")].copy()

    # Aggregate panel to 2024 total per partner
    panel["year"] = panel["date"].dt.year
    trade_2024 = (panel[panel["year"] == 2024]
                  .groupby("COUNTERPART_AREA")["OBS_VALUE"].sum()
                  .reset_index())
    trade_2024.columns = ["iso2", "trade_usd"]
    trade_2024 = trade_2024[trade_2024["trade_usd"] > 1e6]

    if "ISO" in weo.columns:
        gdp = weo[weo["WEO Subject Code"] == "NGDPD"][["ISO", "2024"]].copy()
        gdp.columns = ["iso2", "gdp_bn"]
        gdp["gdp_bn"] = pd.to_numeric(gdp["gdp_bn"], errors="coerce")
        merged = trade_2024.merge(gdp, on="iso2", how="inner").dropna()
        merged = merged[merged["gdp_bn"] > 0]
    else:
        print("  WEO format unexpected; skipping")
        return

    if len(merged) < 5:
        print("  too few merged points; skipping")
        return

    x = np.log(merged["gdp_bn"].astype(float))
    y = np.log(merged["trade_usd"].astype(float) / 1e9)

    # OLS via statsmodels
    import statsmodels.api as sm
    X = sm.add_constant(x)
    res = sm.OLS(y, X).fit(cov_type="HC1")
    # Predict + CI
    x_line = np.linspace(x.min(), x.max(), 100)
    X_line = sm.add_constant(x_line)
    pred = res.get_prediction(X_line)
    pred_mean = pred.predicted_mean
    pred_ci = pred.conf_int(alpha=0.05)

    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.scatter(x, y, s=22, color=GRAY, alpha=0.55, edgecolor=TEXT,
               linewidth=0.3, zorder=3)
    ax.plot(x_line, pred_mean, color=NAVY, linewidth=1.6, zorder=4)
    ax.fill_between(x_line, pred_ci[:, 0], pred_ci[:, 1],
                    color=NAVY, alpha=0.15, zorder=2)

    # annotate key countries
    label_codes = {"CN", "DE", "JP", "VN", "CA", "MX", "KR", "IN", "GB"}
    for _, row in merged.iterrows():
        if row["iso2"] in label_codes:
            ax.annotate(row["iso2"],
                        (np.log(row["gdp_bn"]),
                         np.log(row["trade_usd"] / 1e9)),
                        xytext=(4, 4), textcoords="offset points",
                        fontsize=7.5, color=TEXT)

    slope = res.params[1]
    r2 = res.rsquared
    ax.text(0.05, 0.95,
            f"OLS slope: {slope:.2f}\n$R^2 = {r2:.2f}$",
            transform=ax.transAxes, fontsize=9, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=GRAY, linewidth=0.5))
    ax.set_xlabel("log(GDP, USD billion)")
    ax.set_ylabel("log(US imports, USD billion)")
    despine(ax, grid_axis="both")
    fig.tight_layout(pad=1.4)
    save_fig(fig, "figB_gravity_diag")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Appendix Figure C: PPML coefficient plot (kept as diagnostic)
# ---------------------------------------------------------------------------
def fig_coef_plot() -> None:
    """Main PPML coefficient on ln(1+ETR) placed against the Boehm bands."""
    print("Appendix Figure C: PPML coefficient plot")
    beta, se = load_main_coefficient()
    lo, hi = beta - 1.96 * se, beta + 1.96 * se

    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    # Boehm short-run (impact to year 1) and long-run bands
    ax.axvspan(-0.76, -0.26, color=SIENNA, alpha=0.10, zorder=0)
    ax.axvspan(-2.25, -1.75, color=NAVY, alpha=0.10, zorder=0)
    ax.axvline(0, color="black", lw=0.7, ls="--", alpha=0.6)
    # main estimate
    ax.errorbar([beta], [0], xerr=[[beta - lo], [hi - beta]], fmt="o",
                color=NAVY, capsize=4, lw=1.5, ms=8, zorder=3)
    # Point estimate label and the horizon over which it was estimated.
    ax.text(beta, 0.30, fr"$\hat{{\beta}} = {beta:.2f}$",
            ha="center", va="bottom", fontsize=11, color=NAVY)
    ax.text(beta, 0.16, "in 10 months (Apr 2025 to Jan 2026)",
            ha="center", va="bottom", fontsize=8, color=NAVY, style="italic")
    ax.text(-0.51, -0.50, "Boehm impact-year 1\n($-0.76$ to $-0.26$)",
            ha="center", color=SIENNA, fontsize=8)
    ax.text(-2.0, -0.50, "Boehm long-run, 7--10 yr\n($-2.25$ to $-1.75$)",
            ha="center", color=NAVY, fontsize=8)
    ax.set_xlim(-3.6, 0.6)
    ax.set_ylim(-0.85, 0.85)
    ax.set_yticks([])
    ax.set_xlabel(r"PPML coefficient on $\ln(1+\mathrm{ETR})$")
    despine(ax, grid_axis="x")
    ax.spines["left"].set_visible(False)
    fig.tight_layout(pad=1.4)
    save_fig(fig, "figC_coef_plot")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Appendix Figure D: Pipeline architecture (clean 4-layer process diagram)
# ---------------------------------------------------------------------------
def fig_pipeline_architecture() -> None:
    print("Appendix Figure D: Pipeline architecture (4-layer)")
    # Use scienceplots minimal style for the architecture diagram
    try:
        import scienceplots  # noqa: F401
        with plt.style.context(["science", "no-latex"]):
            _render_pipeline_arch()
    except Exception:
        _render_pipeline_arch()


def _render_pipeline_arch() -> None:
    fig, ax = plt.subplots(figsize=(11, 7.2))

    layers = [
        ("RAW SOURCES",
         [("IMF IMTS",        "trade flows"),
          ("Census",          "duties + values"),
          ("Yale Budget Lab", "announced rates"),
          ("CEPII",           "gravity controls"),
          ("IMF WEO",         "GDP"),
          ("Teti",            "tariff schedules")],
         "#F4F4F4", "#888888"),
        ("ACQUISITION AND CACHE",
         [("Download APIs",   ""),
          ("Parse files",     ""),
          ("Validate schemas",""),
          ("Write manifest",  "")],
         "#E8EEF2", "#547076"),
        ("PROCESSED PANELS",
         [("US imports",       "panel"),
          ("Realized ETR",     "panel"),
          ("Gravity controls", ""),
          ("Sector map",       ""),
          ("Diversion",        "indicators")],
         "#DEE5EB", "#3A5A6E"),
        ("RESEARCH OUTPUTS",
         [("Summary tables", ""),
          ("Main figures",   ""),
          ("Appendix figs",  ""),
          ("Regression",     "output"),
          ("Data-quality",   "report")],
         NAVY, NAVY),
    ]

    n_layers = len(layers)
    # Layer band geometry: each band gets a header strip + box area
    band_top = 0.97
    band_bot = 0.03
    band_height = (band_top - band_bot) / n_layers
    header_h = 0.06   # height of the label header inside each band
    box_h = 0.10
    box_w = 0.14
    text_size = 8.5
    sub_size = 7.5

    band_palette = ["#FAFAFA", "#F5F7F8", "#F0F4F6", "#E7EEF2"]

    for li, (label, boxes, fill, edge) in enumerate(layers):
        band_y_top = band_top - li * band_height
        band_y_bot = band_y_top - band_height

        # band background
        ax.add_patch(mpatches.Rectangle(
            (0.02, band_y_bot + 0.005), 0.96, band_height - 0.012,
            facecolor=band_palette[li], edgecolor="none", zorder=0,
        ))

        # row label as a section header at the top of the band
        ax.text(0.04, band_y_top - 0.015, label,
                fontsize=10, color=TEXT, fontweight="bold",
                ha="left", va="top")

        # boxes centered horizontally inside the band, below the header
        n_boxes = len(boxes)
        total_width = 0.92
        gap = total_width / n_boxes
        x_start = 0.04 + gap / 2
        box_y_center = band_y_bot + (band_height - header_h) / 2 + 0.005

        for bi, (main, sub) in enumerate(boxes):
            x = x_start + bi * gap
            text_color = "white" if li == 3 else TEXT
            ax.add_patch(mpatches.FancyBboxPatch(
                (x - box_w/2, box_y_center - box_h/2),
                box_w, box_h,
                boxstyle="round,pad=0.010,rounding_size=0.018",
                linewidth=0.9, edgecolor=edge, facecolor=fill,
            ))
            # main label
            if sub:
                ax.text(x, box_y_center + 0.012, main,
                        ha="center", va="center", fontsize=text_size,
                        color=text_color, fontweight="bold" if li == 3 else "normal")
                ax.text(x, box_y_center - 0.018, sub,
                        ha="center", va="center", fontsize=sub_size,
                        color=text_color, style="italic")
            else:
                ax.text(x, box_y_center, main,
                        ha="center", va="center", fontsize=text_size,
                        color=text_color, fontweight="bold" if li == 3 else "normal")

    # Vertical arrows between band centres
    for li in range(n_layers - 1):
        band_y_top_below = band_top - (li + 1) * band_height
        ax.annotate("", xy=(0.5, band_y_top_below - 0.005),
                    xytext=(0.5, band_y_top_below + 0.020),
                    arrowprops=dict(arrowstyle="-|>", color=GRAY,
                                    linewidth=2.0, mutation_scale=18),
                    zorder=5)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.tight_layout(pad=0.5)
    save_fig(fig, "figD_pipeline_architecture")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Figure VII: Market-share mirror -- top winners and losers (new for subsection 5.x)
# ---------------------------------------------------------------------------
def fig_market_share_mirror(top_k: int = 10) -> None:
    print(f"Figure VII: Market-share mirror -- top {top_k} winners and losers")
    path = OUTPUTS / "winner_loser_table.csv"
    if not path.exists():
        print(f"  ! {path} missing -- run compute_reallocation_metrics() first")
        return
    df = pd.read_csv(path)
    df = df.sort_values("delta_share", ascending=False)
    # convert share to percentage points for readability
    df["delta_pp"] = df["delta_share"] * 100

    winners = df.head(top_k).iloc[::-1]  # reverse so largest plots at top
    losers = df.tail(top_k)

    fig, (ax_l, ax_r) = plt.subplots(
        1, 2, figsize=(11.5, 5.4),
        gridspec_kw={"width_ratios": [1, 1], "wspace": 0.30},
        sharey=False,
    )

    # left: losers (negative deltas), true diverging chart -- bars extend from 0
    # toward the LEFT, zero at the right edge of the panel.
    bar_colors_l = [SIENNA if c == "CHN" else GRAY for c in losers["country"]]
    ax_l.barh(losers["country"], losers["delta_pp"], color=bar_colors_l, edgecolor="white", linewidth=0.6)
    ax_l.axvline(0, color="#333333", linewidth=0.6)
    ax_l.set_xlim(losers["delta_pp"].min() * 1.15, 0)
    ax_l.yaxis.tick_right()
    ax_l.set_xlabel(r"$\Delta$ market share (pp)")
    despine(ax_l, grid_axis="x")

    # right: winners (positive deltas)
    bar_colors_r = [NAVY for _ in winners["country"]]
    ax_r.barh(winners["country"], winners["delta_pp"], color=bar_colors_r, edgecolor="white", linewidth=0.6)
    ax_r.axvline(0, color="#333333", linewidth=0.6)
    ax_r.set_xlim(0, winners["delta_pp"].max() * 1.15)
    ax_r.set_xlabel(r"$\Delta$ market share (pp)")
    despine(ax_r, grid_axis="x")

    # annotate each bar with the value (right-aligned for left panel, left-aligned for right panel)
    for c, v in zip(losers["country"], losers["delta_pp"]):
        ax_l.text(v - 0.05, c, f"{v:+.2f}", va="center", ha="right", fontsize=7, color=TEXT)
    for c, v in zip(winners["country"], winners["delta_pp"]):
        ax_r.text(v + 0.05, c, f"{v:+.2f}", va="center", ha="left", fontsize=7, color=TEXT)

    fig.text(0.27, 0.94, "Lost US import share", ha="center", fontsize=10, color=TEXT, weight="bold")
    fig.text(0.73, 0.94, "Gained US import share", ha="center", fontsize=10, color=TEXT, weight="bold")

    save_fig(fig, "fig07_market_share_mirror")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure VIII: Reallocation index over time (new for subsection 5.x)
# ---------------------------------------------------------------------------
def fig_reallocation_timeseries() -> None:
    print("Figure VIII: Quarterly reallocation index R_t")
    path = OUTPUTS / "reallocation_timeseries.csv"
    if not path.exists():
        print(f"  ! {path} missing -- run compute_reallocation_timeseries() first")
        return
    df = pd.read_csv(path)
    # rebuild a real datetime from the period string for plotting
    df["dt"] = pd.PeriodIndex(df["period"], freq="Q").to_timestamp(how="end")

    fig, ax = plt.subplots(figsize=(11.5, 4.4))

    # shade the post-shock window (Apr 2025 onwards)
    ax.axvspan(pd.Timestamp("2025-04-02"), df["dt"].max(), color=SIENNA, alpha=0.10, zorder=0)

    # pre-2025 mean as a horizontal reference
    pre = df[df["period"] < "2025"]["R_vs_prev"]
    pre_mean = pre.mean() if len(pre) else float("nan")
    if not np.isnan(pre_mean):
        ax.axhline(pre_mean, color=GRAY, linewidth=0.8, linestyle="--", zorder=1)
        # single horizontal label pinned to the upper-left corner (axes coords)
        ax.text(
            0.012, 0.96, f"pre-2025 mean = {pre_mean:.3f}",
            transform=ax.transAxes, va="top", ha="left", color=GRAY, fontsize=8,
        )

    # the line itself
    ax.plot(df["dt"], df["R_vs_prev"], color=NAVY, linewidth=1.6, marker="o", markersize=3.5, zorder=3)

    # vertical event line at Liberation Day
    ax.axvline(pd.Timestamp("2025-04-02"), color=SIENNA, linewidth=1.0, linestyle=":", zorder=2)
    ax.text(
        pd.Timestamp("2025-04-02"), df["R_vs_prev"].max() * 1.05,
        " Apr 2, 2025",
        color=SIENNA, fontsize=8, ha="left", va="bottom",
    )

    ax.set_ylabel(r"$R_t = \frac{1}{2}\sum_c\,|s_{c,t} - s_{c,t-1}|$")
    ax.set_xlabel("Quarter")
    ax.set_ylim(0, df["R_vs_prev"].max() * 1.18)
    despine(ax, grid_axis="y")

    save_fig(fig, "fig08_reallocation_timeseries")
    plt.close(fig)


# single source of truth for thesis figure stem -> function mapping.
# stems match the \includegraphics filenames in thesis-writing/finalized_main.tex.
# `python figures_v2.py` regenerates everything in this dict; pass a stem on the
# CLI to regenerate just that one.
# ---------------------------------------------------------------------------
# Figure E: product-level rerouting fingerprint
# China-product overlap vs change in US market share, one bubble per partner.
# ---------------------------------------------------------------------------
def fig_product_exposure() -> None:
    print("Figure E: product-level China overlap vs market-share change")
    pe = pd.read_csv(OUTPUTS / "product_exposure.csv")
    wl = pd.read_csv(OUTPUTS / "winner_loser_table.csv")
    # winner_loser uses ISO3 codes; product_exposure uses Census names. bridge them.
    iso2name = {
        "VNM": "VIETNAM", "TWN": "TAIWAN", "MEX": "MEXICO", "THA": "THAILAND",
        "IND": "INDIA", "MYS": "MALAYSIA", "IDN": "INDONESIA",
        "KOR": "KOREA, SOUTH", "JPN": "JAPAN", "DEU": "GERMANY",
        "CAN": "CANADA", "CHE": "SWITZERLAND", "IRL": "IRELAND", "ITA": "ITALY",
        "GBR": "UNITED KINGDOM", "FRA": "FRANCE", "BRA": "BRAZIL",
        "SGP": "SINGAPORE", "NLD": "NETHERLANDS",
    }
    wl = wl.copy()
    wl["iso3"] = wl["country"]
    wl["name"] = wl["country"].map(iso2name)
    m = (wl.dropna(subset=["name"])
           .merge(pe[["country", "china_overlap_share", "pre_shock_value_usd"]],
                  left_on="name", right_on="country", how="inner"))
    m["overlap_pct"] = m["china_overlap_share"] * 100
    m["delta_pp"] = m["delta_share"] * 100
    m["val"] = pd.to_numeric(m["pre_shock_value_usd"], errors="coerce").fillna(0)
    sizes = (m["val"] / m["val"].max()) * 850 + 40

    from adjustText import adjust_text

    fig, ax = plt.subplots(figsize=(9.2, 6.6))
    ax.axhline(0, color=GRAY, lw=0.9, ls=(0, (4, 3)), zorder=1)
    xs = m["overlap_pct"].to_numpy()
    ys = m["delta_pp"].to_numpy()
    ax.scatter(xs, ys, s=sizes,
               c=[NAVY if d > 0 else SIENNA for d in m["delta_pp"]],
               alpha=0.78, edgecolor="white", linewidth=0.6, zorder=3)
    # Repel the country-code labels into open space and draw thin leader lines,
    # so the crowded cluster near the origin stays readable.
    ax.set_xlim(-2.5, 40)
    ax.set_ylim(-2.2, 4.0)
    texts = [ax.text(x, y, iso, fontsize=7.3, color=TEXT, zorder=5)
             for x, y, iso in zip(xs, ys, m["iso3"])]
    adjust_text(texts, x=xs, y=ys, ax=ax,
                force_text=(0.8, 1.6), force_static=(0.5, 1.0),
                expand=(2.0, 2.6), max_move=120, iter_lim=400,
                arrowprops=dict(arrowstyle="-", color="#777777", lw=0.5))
    vn = m[m["iso3"] == "VNM"]
    if len(vn):
        ax.annotate("highest overlap and a clear\nshare gain",
                    xy=(vn["overlap_pct"].iloc[0], vn["delta_pp"].iloc[0]),
                    xytext=(23.5, 2.55), fontsize=7.8, color=NAVY,
                    ha="left", va="top",
                    arrowprops=dict(arrowstyle="->", color=NAVY, lw=0.8))
    ax.set_xlabel("Pre-shock overlap with China-dominated products\n"
                  "(percent of the partner's US exports)")
    ax.set_ylabel("Change in US import market share (percentage points)")
    h_gain = ax.scatter([], [], s=70, c=NAVY, edgecolor="white", label="Gained US share")
    h_loss = ax.scatter([], [], s=70, c=SIENNA, edgecolor="white", label="Lost US share")
    ax.legend(handles=[h_gain, h_loss], loc="lower right", frameon=False, fontsize=8)
    ax.text(0.015, 0.02, r"Bubble area $\propto$ pre-shock US imports",
            transform=ax.transAxes, fontsize=7.5, color=GRAY)
    despine(ax, grid_axis="both")
    fig.tight_layout(pad=1.2)
    save_fig(fig, "figE_product_exposure")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure F: Census vs USITC DataWeb agreement (cross-source validation)
# ---------------------------------------------------------------------------
def fig_usitc_validation() -> None:
    print("Figure F: Census vs USITC DataWeb agreement")
    d = pd.read_csv(OUTPUTS / "usitc_census_discrepancy.csv")
    d["census_bn"] = d["census_value"] / 1e9
    d["usitc_bn"] = d["usitc_value"] / 1e9
    qcolor = {"Q1": NAVY, "Q3": SIENNA}

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.5, 5.6))

    # left: 45-degree agreement on log-log axes
    lo = min(d["usitc_bn"].min(), d["census_bn"].min()) * 0.7
    hi = max(d["usitc_bn"].max(), d["census_bn"].max()) * 1.3
    axL.plot([lo, hi], [lo, hi], color=GRAY, lw=1.0, ls="--", zorder=1)
    for q in ["Q1", "Q3"]:
        s = d[d["q"] == q]
        axL.scatter(s["usitc_bn"], s["census_bn"], s=36, c=qcolor[q], alpha=0.75,
                    edgecolor="white", linewidth=0.5, label=f"{q} 2025", zorder=3)
    axL.set_xscale("log")
    axL.set_yscale("log")
    axL.set_xlim(lo, hi)
    axL.set_ylim(lo, hi)
    axL.set_aspect("equal")
    for _, r in d[d["q"] == "Q1"].iterrows():
        if r["key"] in {"CHINA", "MEXICO", "CANADA"}:
            axL.annotate(r["key"].title(), (r["usitc_bn"], r["census_bn"]),
                         xytext=(5, -2), textcoords="offset points",
                         fontsize=7.5, color=TEXT)
    axL.text(0.04, 0.96, r"45$^\circ$ line: perfect agreement",
             transform=axL.transAxes, fontsize=8, va="top", color=GRAY)
    axL.set_xlabel("USITC DataWeb customs value (USD billion, log scale)")
    axL.set_ylabel("Census general import value (USD billion, log scale)")
    axL.legend(loc="lower right", frameon=False, fontsize=8)
    despine(axL, grid_axis="both")

    # right: distribution of the absolute percentage differences
    axR.hist(d["pct_diff"], bins=np.arange(0, 8.5, 0.5), color=NAVY,
             alpha=0.85, edgecolor="white", zorder=3)
    mean_d = d["pct_diff"].mean()
    axR.axvline(mean_d, color=SIENNA, lw=1.5, ls="--", zorder=4)
    axR.text(mean_d + 0.2, axR.get_ylim()[1] * 0.9,
             f"mean {mean_d:.1f}%\nmax {d['pct_diff'].max():.1f}%",
             fontsize=8, color=SIENNA, va="top")
    axR.set_xlabel("Absolute difference, Census vs USITC (percent)")
    axR.set_ylabel("Number of partner-quarters")
    despine(axR, grid_axis="y")

    fig.tight_layout(pad=1.4)
    save_fig(fig, "figF_usitc_validation")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure G: country-specific product-weighted applied tariff (Teti, Gap 1)
# ---------------------------------------------------------------------------
def fig_country_tariff() -> None:
    print("Figure G: country-specific product-weighted applied tariff")
    source = OUTPUTS / "country_etr_teti.csv"
    if not source.exists():
        print("  skip figG_country_tariff: optional Teti output is not included in the public release.")
        return
    d = pd.read_csv(source).sort_values("tariff_sep2025")
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(8.4, 6.8))
    for i, (_, r) in enumerate(d.iterrows()):
        ax.plot([r["tariff_jan2025"], r["tariff_sep2025"]], [i, i],
                color=LIGHT_GRAY, lw=2.2, zorder=1)
    ax.scatter(d["tariff_jan2025"], y, s=34, color=GRAY, zorder=3, label="January 2025")
    ax.scatter(d["tariff_sep2025"], y, s=48, color=NAVY, zorder=3, label="September 2025")
    ax.axvline(5.68, color=SIENNA, lw=1.2, ls="--", zorder=2)
    ax.text(5.68, len(d) - 0.4, " US-wide realized ETR, 5.68%", color=SIENNA,
            fontsize=7.5, va="top")
    ax.set_yticks(y)
    ax.set_yticklabels([n.title() for n in d["name"]], fontsize=8)
    ax.set_xlabel("Product-weighted applied tariff (percent)")
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    despine(ax, grid_axis="x")
    fig.tight_layout(pad=1.2)
    save_fig(fig, "figG_country_tariff")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure H: realized (Census) vs applied (Teti) tariff coefficient
# ---------------------------------------------------------------------------
def fig_coef_compare() -> None:
    print("Figure H: realized vs applied tariff coefficient")
    import json
    source = OUTPUTS / "regression_results_v2.json"
    if not source.exists():
        print("  skip figH_coef_compare: optional Teti comparison JSON is not included in the public release.")
        return
    _v2 = json.loads(source.read_text())
    if not _v2.get("teti_applied"):
        print("  skip figH_coef_compare: optional Teti coefficient is missing.")
        return
    _realized_b, _realized_se = load_main_coefficient()
    _teti_b, _teti_se = _v2["teti_applied"]["beta"], _v2["teti_applied"]["se"]
    specs = [("Census realized ETR\n(main, partner and month FE)", _realized_b, _realized_se, NAVY),
             ("Teti applied tariff\n(partner and month FE)",        _teti_b,     _teti_se,     SIENNA)]
    fig, ax = plt.subplots(figsize=(8.2, 3.3))
    ax.axvspan(-2.25, -0.26, color=VERY_LIGHT, zorder=0)
    ax.text(-1.255, 1.55, "Boehm et al. range\n(impact through long-run)",
            color=GRAY, fontsize=7.3, ha="center", va="top")
    ax.axvline(0, color=GRAY, lw=0.9, ls=(0, (4, 3)), zorder=1)
    for i, (lab, b, se, c) in enumerate(specs):
        ax.errorbar(b, i, xerr=1.96 * se, fmt="o", color=c, ecolor=c,
                    elinewidth=1.5, capsize=4, ms=8, zorder=3)
        ax.text(b, i + 0.22, f"{b:+.2f}", color=c, fontsize=9, ha="center")
    ax.set_yticks([0, 1])
    ax.set_yticklabels([specs[0][0], specs[1][0]], fontsize=8.5)
    ax.set_ylim(-0.6, 1.85)
    ax.set_xlim(-4.6, 0.6)
    ax.set_xlabel("Coefficient on ln(1 + tariff), with 95 percent confidence interval")
    despine(ax, grid_axis="x")
    fig.tight_layout(pad=1.2)
    save_fig(fig, "figH_coef_compare")
    plt.close(fig)


FIGURE_REGISTRY = {
    "fig01_policy_timeline":         fig_policy_timeline,
    "fig02_announced_vs_realized":   fig_announced_vs_realized,
    "fig03_sector_composition":      fig_sector_composition,
    "fig04_etr_distribution":        fig_etr_distribution,
    "fig05_event_study":             fig_event_study,
    "fig06_diversion_quadrant":      fig_diversion_quadrant,
    "fig07_market_share_mirror":     fig_market_share_mirror,
    "fig08_reallocation_timeseries": fig_reallocation_timeseries,
    "figB_gravity_diag":             fig_gravity_diagnostic,
    "figC_coef_plot":                fig_coef_plot,
    "figD_pipeline_architecture":    fig_pipeline_architecture,
    "figE_product_exposure":         fig_product_exposure,
    "figF_usitc_validation":         fig_usitc_validation,
    "figG_country_tariff":           fig_country_tariff,
    "figH_coef_compare":             fig_coef_compare,
}


def main(only: list[str] | None = None) -> None:
    print("Regenerating publication-grade figures (Matplotlib only)\n")
    stems = only if only else list(FIGURE_REGISTRY.keys())
    for stem in stems:
        if stem not in FIGURE_REGISTRY:
            print(f"  ! unknown figure stem: {stem} (skip)")
            continue
        FIGURE_REGISTRY[stem]()
    print("\nAll figures written to figures/ as both PDF and PNG.")


if __name__ == "__main__":
    import sys
    cli_stems = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(only=cli_stems or None)
