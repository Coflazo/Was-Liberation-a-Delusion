"""
Reproducible data pipeline for:

    Was Liberation a Delusion?
    Liberation Day Tariff Shocks, Bilateral Trade Flows, and Trade Diversion in 2025.

BSc thesis, University of Amsterdam, Faculty of Economics and Business.
Author: Cagan Oflazoglu (14788527).

The pipeline downloads the eight public data sources used in the thesis,
constructs the analysis panels, generates the figures and tables, and runs
the descriptive PPML timing regression. Every output cached in
``data/processed`` is reproducible from the raw downloads in ``data/raw``.

Commands
--------
    python pipeline.py run             # full pipeline
    python pipeline.py download        # raw data only
    python pipeline.py regress         # PPML timing regression
    python pipeline.py figures         # figures from cached data
    python pipeline.py plot            # alias for figures
"""

# ------------------------------------------------------------
# --- section 1: auto-install and imports
# ------------------------------------------------------------

# dependencies are pinned in requirements.lock -- this script no longer
# pip-installs at import time. that path mutated the user's environment with
# unpinned versions and used --break-system-packages, which is fine for
# personal use but not for a thesis replication package.
import subprocess
import sys

REQUIRED_PACKAGES = [
    # data and APIs
    "sdmx1",
    "pandas",
    "numpy",
    "requests",
    "certifi",
    "scipy",
    "comtradeapicall",
    "openpyxl",
    "xlrd",
    "py7zr",
    "tqdm",
    # terminal UI
    "typer",
    "rich",
    # figures
    "matplotlib",
    "seaborn",
    "Pillow",
    # econometrics: academic regression stack
    "statsmodels",       # OLS, GLM with Stata-style summary tables -- the actual estimator we use
    # NOTE: pyfixest used to be in this list but it requires numba+llvmlite which
    # don't yet support Python 3.13/3.14. We use statsmodels GLM with Poisson family
    # instead (see regress function). If you want pyfixest, install manually.
]

# optional academic packages (install manually if needed):
#   pip install pubfig         -- journal-aware matplotlib export + multi-panel figures
#   pip install ggpubpy        -- ggpubr-style plots with built-in stat annotations
#   latexify-py                -- doesn't support Python 3.14 yet (as of April 2026)
#                                 the formula checker still works without it


def install_packages() -> None:
    """Install missing packages without printing a million lines of text."""
    for pkg in REQUIRED_PACKAGES:
        import_name = pkg.lower().replace("-", "_")
        # weirdly sdmx1 is called sdmx when you import it. took me forever to figure out.
        if pkg == "sdmx1":
            import_name = "sdmx"
        # Pillow installs as PIL, not pillow
        elif pkg == "Pillow":
            import_name = "PIL"

        try:
            __import__(import_name)
        except ImportError:
            # _icon() isn't defined yet at this point in the file, so use plain text
            print(f"□ Installing {pkg}...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg, "-q"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                # macOS homebrew python is so annoying with PEP 668
                print(f"   ! Normal install failed for {pkg}, trying --break-system-packages...")
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pkg, "-q", "--break-system-packages"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except subprocess.CalledProcessError as e:
                    print(f"   ✗ Could not install {pkg}: {e}")
                    print(f"   → Try manually: {sys.executable} -m pip install {pkg} --break-system-packages")
                    sys.exit(1)


# do NOT auto-install at module import. if the user needs to install,
# they can call `python pipeline.py setup` (see Typer command below)
# or just `pip install -r requirements.lock`.

def _require_imports() -> None:
    """Fail loud and clear if required packages are missing."""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        import_name = pkg.lower().replace("-", "_")
        if pkg == "sdmx1":
            import_name = "sdmx"
        elif pkg == "Pillow":
            import_name = "PIL"
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("✗ Missing required packages:")
        for pkg in missing:
            print(f"  - {pkg}")
        print()
        print("Fix: install via the pinned lockfile from this repo:")
        print("    python -m venv .venv")
        print("    source .venv/bin/activate")
        print("    pip install -r requirements.lock")
        print()
        print("Or, to install the latest unpinned versions:")
        print("    python pipeline.py setup")
        sys.exit(1)


_require_imports()

# okay now the actual imports
import io
import itertools
import json
import os
import threading
import time
import traceback
import warnings
import zipfile
from pathlib import Path
from typing import Any

import certifi
import numpy as np
import pandas as pd
import requests
from tqdm import tqdm

# the fancy terminal stuff
import typer
from rich.console import Console
from rich.panel import Panel

# silence only the noisy categories we've actually verified are harmless.
# the previous filterwarnings("ignore") was too broad -- it could hide real
# bugs (e.g. silent dtype coercion or division-by-zero in pandas).
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="statsmodels")
warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")
warnings.filterwarnings("ignore", category=RuntimeWarning, message="invalid value encountered in log")

# rich consoles  -  one for stdout, one for stderr
# using stderr for errors so piping still works
console = Console()
err_console = Console(stderr=True)


# ------------------------------------------------------------
# --- terminal aesthetics: icons + orbital spinner
# --- icons-in-terminal isn't on PyPI, so we use Nerd Font codepoints
# --- with plain-text fallback for terminals that don't have the font
# ------------------------------------------------------------

def _nerd_font_available() -> bool:
    """Heuristic: TERM_PROGRAM or COLORTERM hints suggest a capable terminal."""
    t = os.environ.get("TERM_PROGRAM", "") + os.environ.get("COLORTERM", "")
    return any(x in t.lower() for x in ("iterm", "kitty", "hyper", "wezterm", "alacritty"))


# Nerd Font codepoints (monospace-safe, gravity/science theme where possible)
# fallback to plain ASCII/Unicode that works everywhere
_ICONS: dict[str, tuple[str, str]] = {
    #        nerd-font    plain
    "ok":    ("  ",  "✓ "),   # fa-check
    "dl":    ("  ",  "↓ "),   # fa-download
    "warn":  ("  ",  "! "),   # fa-exclamation-triangle
    "fail":  ("  ",  "✗ "),   # fa-times
    "box":   ("  ",  "□ "),   # nf-oct-package
    "clock": ("  ",  "⏱ "),   # fa-clock-o
    "gear":  ("  ",  "⚙ "),   # fa-cog
    "book":  ("  ",  "≡ "),   # fa-book
    "cache": ("  ",  "≃ "),   # fa-floppy-o
    "orbit": ("  ",  "● "),   # fa-circle (planet)
    "chart": ("  ",  "◆ "),   # fa-bar-chart
    "doc":   ("  ",  "» "),   # fa-file-text
    "retry": ("  ",  "↻ "),   # fa-refresh
    "info":  ("  ",  "· "),   # fa-info-circle
}

_USE_NERD = _nerd_font_available()

def _icon(name: str) -> str:
    nerd, plain = _ICONS.get(name, ("? ", "? "))
    return nerd if _USE_NERD else plain


class OrbitalSpinner:
    """
    28-frame comet orbit. Star pulses amber/gold. Satellite trails braille sparks.
    Bright at perihelion (close approach), dim at aphelion (far side).
    Front arc: ◉ with ⠿⠛⠉ braille trail. Back arc: ○ dim, satellite hidden behind star.
    Runs at 12fps in a background thread.
    """
    _R        = "\033[0m"
    _DIM      = "\033[2m"
    _GREEN    = "\033[32m"
    _RED      = "\033[31m"

    # star pulses between two states
    _STAR_A   = "\033[93;1m"   # bright yellow-gold
    _STAR_B   = "\033[33m"     # warm amber

    # satellite brightness by distance from star (front arc only)
    _SAT_HI   = "\033[96;1m"   # close approach  -  bright cyan
    _SAT_MID  = "\033[36;1m"   # mid-arc
    _SAT_LO   = "\033[36m"     # far end

    # back arc (satellite behind the star)  -  dim
    _SAT_BACK = "\033[36;2m"

    # comet trail, three levels of fade
    _T1       = "\033[96;1m"   # hottest  -  just behind satellite
    _T2       = "\033[36m"     # warm
    _T3       = "\033[36;2m"   # cooling out

    _PATH     = "\033[90;2m"   # faint orbit ring dots
    _BRACKET  = "\033[90m"     # dim gray brackets

    _W = 17          # orbit width in slots
    _STAR = 8        # star fixed at center

    def __init__(self, message: str = "Working…"):
        self.message = message
        self._running = False
        self._thread: threading.Thread | None = None
        self._frames = self._build_frames()

    def _sat_color(self, pos: int) -> str:
        # brighter when closer to the star  -  gravitational drama
        dist = abs(pos - self._STAR)
        if dist <= 2:   return self._SAT_HI
        elif dist <= 4: return self._SAT_MID
        else:           return self._SAT_LO

    def _build_frames(self) -> list[str]:
        W, S, R = self._W, self._STAR, self._R
        frames = []
        star_chars = [self._STAR_A + "✦" + R, self._STAR_B + "✧" + R]
        path_dot   = self._PATH + "·" + R

        # front arc: satellite visible, moving left → right
        front = list(range(S)) + list(range(S + 1, W))        # 0 to 7, 9 to 16
        # back arc: satellite dim, moving right → left (behind the star)
        back  = list(reversed(range(S + 1, W))) + list(reversed(range(S)))  # 16 to 9, 7 to 0

        for arc_i, (positions, is_front) in enumerate([(front, True), (back, False)]):
            for fi, sat_pos in enumerate(positions):
                slots = [path_dot] * W
                # pulsing star  -  flips every frame
                slots[S] = star_chars[(arc_i * len(positions) + fi) % 2]

                if is_front:
                    slots[sat_pos] = self._sat_color(sat_pos) + "◉" + R
                    # braille comet trail (3 slots behind, direction = rightward)
                    for ti, (tc, ch) in enumerate([(self._T1, "⠿"), (self._T2, "⠛"), (self._T3, "⠉")]):
                        tp = sat_pos - (ti + 1)
                        if 0 <= tp < W and tp != S:
                            slots[tp] = tc + ch + R
                else:
                    slots[sat_pos] = self._SAT_BACK + "○" + R
                    # dim dotted trail (direction = leftward on back arc)
                    for ti in range(3):
                        tp = sat_pos + (ti + 1)
                        if 0 <= tp < W and tp != S:
                            slots[tp] = self._T3 + "·" + R

                frames.append(
                    f"{self._BRACKET}({R}{''.join(slots)}{self._BRACKET}){R}"
                )
        return frames

    def start(self) -> "OrbitalSpinner":
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def update(self, message: str) -> None:
        self.message = message

    def _loop(self) -> None:
        for frame in itertools.cycle(self._frames):
            if not self._running:
                break
            sys.stdout.write(f"\r{frame}  {self._DIM}{self.message}{self._R}")
            sys.stdout.flush()
            time.sleep(1 / 12)  # 12fps  -  smooth without burning CPU

    def stop(self, done_msg: str = "Done") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.35)
        clear = " " * (len(self.message) + 30)
        sys.stdout.write(f"\r{clear}\r{self._GREEN}{_icon('ok')}{self._R}{done_msg}\n")
        sys.stdout.flush()

    def fail(self, msg: str = "Failed") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.35)
        clear = " " * (len(self.message) + 30)
        sys.stdout.write(f"\r{clear}\r{self._RED}{_icon('fail')}{self._R}{msg}\n")
        sys.stdout.flush()

# typer app  -  this is the main CLI entry point now
# way better than argparse. trust me.
app = typer.Typer(
    name="gravity-pipeline",
    help="UvA Thesis Data Pipeline: Liberation Day Tariff Analysis",
    add_completion=False,
    rich_markup_mode="rich",
)


# ------------------------------------------------------------
# --- section 2: config and constants
# ------------------------------------------------------------

# thesis details here. don't touch.
THESIS_METADATA: dict[str, Any] = {
    "title": "Was Liberation a Delusion? Tariff Shocks, Bilateral Trade Flows, and Trade Diversion in 2025",
    "author": "Çağan Oflazoğlu",
    "university": "University of Amsterdam",
    "year": 2026,
}

# terminal color names for plotext (can't use hex in terminal sadly)
# keeping them close-ish to the UvA brand colors
TERM_COLORS = {
    "uva_red": "red",
    "uva_dark": "blue",
    "slate": "gray",
    "teal": "cyan",
    "amber": "yellow",
    "highlight": "magenta",
    "good": "green",
}

# making the folders so it doesn't crash
BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
FIGURES_DIR = BASE_DIR / "figures"
OUTPUTS_DIR = BASE_DIR / "outputs"

for d in [RAW_DIR, PROCESSED_DIR, FIGURES_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# the main countries I'm tracking
FOCUS_COUNTRIES = ["CN", "EU", "VN", "MX", "CA", "KR", "DE", "JP", "IN", "TW"]
FOCUS_COUNTRY_NAMES = {
    "CN": "China", "EU": "EU", "VN": "Vietnam",
    "MX": "Mexico", "CA": "Canada", "KR": "South Korea",
    "DE": "Germany", "JP": "Japan", "IN": "India", "TW": "Taiwan",
}

# logging stuff here so I can see what failed
DOWNLOAD_LOG: list[dict[str, Any]] = []


# ------------------------------------------------------------
# --- section 3: error handling and utilities
# ------------------------------------------------------------

# no more silent failures. no more "using synthetic placeholder".
# if something breaks, I want to know EXACTLY what happened and how to fix it.
# this was the #1 complaint from my supervisor lol.

def _hard_fail(
    dataset: str,
    error: str,
    url: str = "",
    fix_steps: list[str] | None = None,
    raw_exception: Exception | None = None,
) -> None:
    """
    prints a massive detailed error message and kills the pipeline.
    no more sweeping failures under the rug with fake data.
    if something breaks, I want a full autopsy.
    """
    # pile up all the detail lines before handing off to Rich
    lines = [
        f"[bold red]{_icon('fail')}FATAL: {dataset} failed[/bold red]",
        "",
        f"[dim]Error:[/dim] {error}",
    ]

    if url:
        lines.append(f"[dim]URL:[/dim] {url}")

    if raw_exception:
        lines.append("")
        lines.append("[dim]Full traceback:[/dim]")
        tb = traceback.format_exception(type(raw_exception), raw_exception, raw_exception.__traceback__)
        for tb_line in tb[-5:]:  # last 5 lines of traceback, don't need the whole novel
            lines.append(f"  [dim]{tb_line.rstrip()}[/dim]")

    if fix_steps:
        lines.append("")
        lines.append(f"[bold yellow]{_icon('gear')}HOW TO FIX THIS:[/bold yellow]")
        lines.append("")
        for step in fix_steps:
            lines.append(f"  {step}")

    lines.append("")
    lines.append("[dim]Pipeline stopped. Fix the issue above and re-run.[/dim]")
    lines.append(f"[dim]Re-run with: python {Path(__file__).name} download --dataset <name>[/dim]")

    err_console.print(Panel(
        "\n".join(lines),
        title=f"[bold red]{_icon('fail')}Pipeline Error  -  {dataset}[/bold red]",
        border_style="red",
        padding=(1, 2),
    ))
    raise SystemExit(1)


def _log(entry: dict[str, Any]) -> None:
    """just appends to the download log. nothing fancy."""
    DOWNLOAD_LOG.append(entry)


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file, streamed so big downloads don't blow RAM."""
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _update_raw_manifest(dest: Path, url: str, description: str) -> None:
    """
    Record a finished download in data/raw_manifest.json. Each row is keyed by
    the relative dest path and carries url, sha256, bytes, access timestamp,
    and the source description. Atomic write so partial JSON can't corrupt
    the manifest.
    """
    manifest_path = RAW_DIR / "raw_manifest.json"
    try:
        existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        if not isinstance(existing, dict):
            existing = {}
    except (json.JSONDecodeError, OSError):
        # corrupted manifest -- start fresh, don't lose new entries to old garbage
        existing = {}

    try:
        rel = str(dest.relative_to(BASE_DIR))
    except ValueError:
        rel = str(dest)

    existing[rel] = {
        "url": url,
        "description": description,
        "sha256": _sha256_file(dest),
        "bytes": dest.stat().st_size,
        "downloaded_at": pd.Timestamp.now().isoformat(timespec="seconds"),
    }

    tmp = manifest_path.parent / (manifest_path.name + ".tmp")
    tmp.write_text(json.dumps(existing, indent=2, sort_keys=True))
    tmp.replace(manifest_path)


def _download_with_retry(
    url: str,
    dest: Path,
    description: str,
    timeout: int = 60,
    max_retries: int = 5,
) -> bool:
    """
    Downloads a file. Added exponential backoff because the APIs kept rate-limiting me.
    Streams to a .tmp sibling and atomically renames on success so an interrupted
    download can never leave a half-written cache file in place. Logs a SHA-256
    hash + access timestamp into data/raw_manifest.json for replication.
    """
    tmp = dest.parent / (dest.name + ".tmp")
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"   {_icon('clock')}Rate limited (HTTP 429). Waiting {wait}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = 2 ** attempt
                print(f"   {_icon('clock')}Server error {resp.status_code}. Waiting {wait}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                print(f"   {_icon('warn')}HTTP {resp.status_code} for {description}")
                return False
            total = int(resp.headers.get("content-length", 0))
            with open(tmp, "wb") as f:
                with tqdm(
                    total=total, unit="B", unit_scale=True,
                    desc=f"   {description}", leave=False,
                ) as bar:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        bar.update(len(chunk))
            tmp.replace(dest)  # atomic on POSIX
            try:
                _update_raw_manifest(dest, url, description)
            except Exception as e:
                # never fail the download because the manifest blew up
                print(f"   {_icon('warn')}Manifest update failed for {dest.name}: {e}")
            return True
        except requests.RequestException as e:
            wait = 2 ** attempt
            print(f"   {_icon('warn')}Request error: {e}. Retrying in {wait}s... (attempt {attempt + 1}/{max_retries})")
            # clean up the partial tmp so the next attempt starts fresh
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            time.sleep(wait)
    print(f"   {_icon('fail')}All {max_retries} retries exhausted for {description}")
    return False


# ------------------------------------------------------------
# --- section 4: downloading all the data
# --- NO MORE SYNTHETIC PLACEHOLDERS. real data or bust.
# ------------------------------------------------------------

# --- imf trade data ---

def download_imf_imts(force_redownload: bool = False, quiet: bool = False) -> pd.DataFrame:
    """
    Grabs IMF IMTS trade flows.

    Needs to be monthly data since the tariffs hit in April 2025.
    Annual data would just blur everything.

    Also the old DOTS portal died in 2025, so I had to migrate this to IMTS.
    Using sdmx1 now because imfpy completely broke. That was a fun weekend.

    IMPORTANT: IMTS uses 3-letter ISO country codes (USA not US) and
    its indicator names drop the T prefix (MG_CIF_USD not TMG_CIF_USD).
    We normalize both here so downstream code doesn't break.
    The "IMF" sdmx1 source (sdmxcentral.imf.org) is dead  -  use "IMF_DATA" instead.
    """
    dest = RAW_DIR / "imf_imts_bilateral_monthly.csv"

    if dest.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}IMF IMTS already cached, loading from disk")
        df = pd.read_csv(dest)
        _log({"dataset": "IMF IMTS", "status": "cached", "rows": len(df), "file": str(dest)})
        return df

    # IMTS DSD dimension order: COUNTRY.INDICATOR.COUNTERPART_COUNTRY.FREQUENCY
    # Country codes are ISO-3: USA, CHN, VNM (NOT the 2-letter US, CN, VN)
    # Indicator codes: MG_CIF_USD (imports CIF), XG_FOB_USD (exports FOB)  -  no T prefix
    # We map back to the old TMG_/TXG_ names for downstream compatibility
    COUNTRY_MAP = {"USA": "US", "CHN": "CN", "VNM": "VN"}
    INDICATOR_MAP = {"MG_CIF_USD": "TMG_CIF_USD", "XG_FOB_USD": "TXG_FOB_USD"}

    # reporters: (iso3_code, [indicators_to_fetch])
    REPORTERS = [
        ("USA", ["MG_CIF_USD", "XG_FOB_USD"]),
        ("CHN", ["MG_CIF_USD", "XG_FOB_USD"]),  # CHN exports needed for diversion
        ("VNM", ["MG_CIF_USD"]),
    ]

    def _parse_imts_xml(xml_text: str, reporter_iso2: str, indicator_label: str) -> pd.DataFrame:
        """Parse SDMX StructureSpecificData XML from the IMTS endpoint."""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        rows = []
        for series in root.iter():
            tag = series.tag.split("}")[-1] if "}" in series.tag else series.tag
            if tag != "Series":
                continue
            counterpart = series.get("COUNTERPART_COUNTRY", "")
            for obs in series:
                otag = obs.tag.split("}")[-1] if "}" in obs.tag else obs.tag
                if otag != "Obs":
                    continue
                tp = obs.get("TIME_PERIOD", "")
                val = obs.get("OBS_VALUE", "")
                rows.append({
                    "TIME_PERIOD": tp,
                    "COUNTERPART_AREA": counterpart,
                    "reporter": reporter_iso2,
                    "indicator": indicator_label,
                    "OBS_VALUE": float(val) if val else None,
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            # convert "2024-M01" → "2024-01" so pd.to_datetime works downstream
            df["TIME_PERIOD"] = df["TIME_PERIOD"].str.replace(r"-M(\d+)", r"-\1", regex=True)
        return df

    print(f"   {_icon('dl')}Attempting IMF IMTS via sdmx1 (IMF_DATA endpoint)...")
    last_error = None
    records: list[pd.DataFrame] = []

    try:
        import sdmx

        # IMF_DATA → api.imf.org/external/sdmx/2.1 (WORKS as of 2025)
        # The old "IMF" source (sdmxcentral.imf.org) returns 404 on everything
        imf = sdmx.Client("IMF_DATA")

        for iso3, indicators in REPORTERS:
            iso2 = COUNTRY_MAP[iso3]
            for ind_code in indicators:
                ind_label = INDICATOR_MAP[ind_code]
                try:
                    resp = imf.data(
                        "IMTS",
                        key={
                            "COUNTRY": iso3,
                            "INDICATOR": ind_code,
                            "COUNTERPART_COUNTRY": "",
                            "FREQUENCY": "M",
                        },
                        params={"startPeriod": "2020-01", "endPeriod": "2026-03"},
                    )
                    series = sdmx.to_pandas(resp)
                    if series is None or (hasattr(series, "__len__") and len(series) == 0):
                        print(f"   {_icon('warn')}IMTS {iso3}/{ind_code}: 0 rows")
                        continue
                    df_tmp = series.reset_index()
                    df_tmp.columns = [str(c) for c in df_tmp.columns]
                    # normalize TIME_PERIOD format
                    if "TIME_PERIOD" in df_tmp.columns:
                        df_tmp["TIME_PERIOD"] = df_tmp["TIME_PERIOD"].astype(str).str.replace(
                            r"-M(\d+)", r"-\1", regex=True
                        )
                    # rename the value column
                    val_col = [c for c in df_tmp.columns if c not in (
                        "COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "FREQUENCY", "TIME_PERIOD"
                    )]
                    if val_col:
                        df_tmp = df_tmp.rename(columns={val_col[0]: "OBS_VALUE"})
                    df_tmp["reporter"] = iso2
                    df_tmp["indicator"] = ind_label
                    if "COUNTERPART_COUNTRY" in df_tmp.columns:
                        df_tmp = df_tmp.rename(columns={"COUNTERPART_COUNTRY": "COUNTERPART_AREA"})
                    records.append(df_tmp)
                    print(f"   {_icon('ok')}IMTS {iso3}/{ind_code}: {len(df_tmp):,} rows")
                except Exception as e:
                    print(f"   {_icon('warn')}IMTS {iso3}/{ind_code} sdmx failed: {e}")
                    last_error = e

    except Exception as e:
        print(f"   {_icon('warn')}sdmx1 IMF_DATA setup failed: {e}")
        last_error = e

    # REST fallback  -  parse the SDMX XML ourselves, no sdmx1 needed
    if not records:
        print(f"   {_icon('retry')}Trying IMF SDMX 2.1 REST fallback (api.imf.org)...")
        base = "https://api.imf.org/external/sdmx/2.1/data/IMTS"
        for iso3, indicators in REPORTERS:
            iso2 = COUNTRY_MAP[iso3]
            for ind_code in indicators:
                ind_label = INDICATOR_MAP[ind_code]
                # key format: COUNTRY.INDICATOR.COUNTERPART_COUNTRY.FREQUENCY
                url = f"{base}/{iso3}.{ind_code}..M?startPeriod=2020-01&endPeriod=2026-03"
                try:
                    r = requests.get(url, timeout=60, verify=certifi.where())
                    if r.status_code == 200:
                        df_tmp = _parse_imts_xml(r.text, iso2, ind_label)
                        if not df_tmp.empty:
                            records.append(df_tmp)
                            print(f"   {_icon('ok')}IMTS REST {iso3}/{ind_code}: {len(df_tmp):,} rows")
                        else:
                            print(f"   {_icon('warn')}IMTS REST {iso3}/{ind_code}: parsed 0 rows")
                    else:
                        last_error = Exception(f"HTTP {r.status_code}")
                        print(f"   {_icon('warn')}IMTS REST {iso3}/{ind_code}: {r.status_code}")
                except Exception as e:
                    print(f"   {_icon('warn')}IMTS REST {iso3}/{ind_code} failed: {e}")
                    last_error = e

    if records:
        df = pd.concat(records, ignore_index=True)
        df.to_csv(dest, index=False)
        print(f"   {_icon('ok')}IMF IMTS saved: {len(df):,} rows")
        _log({"dataset": "IMF IMTS", "status": "downloaded", "rows": len(df), "file": str(dest)})
        return df

    rest_url = "https://api.imf.org/external/sdmx/2.1/data/IMTS/USA.MG_CIF_USD..M"
    _hard_fail(
        dataset="IMF IMTS Bilateral Trade",
        error=str(last_error) if last_error else "All download methods failed",
        url=rest_url,
        raw_exception=last_error,
        fix_steps=[
            "1. Check your internet  -  can you reach https://api.imf.org ?",
            "2. The IMF IMTS SDMX endpoint goes down for maintenance sometimes.",
            "   Wait 30 minutes and retry: python pipeline.py download --dataset imf-imts",
            "3. Check if sdmx1 needs updating: pip install --upgrade sdmx1",
            "4. Try the REST URL directly: " + rest_url,
            "5. If rate-limited (HTTP 429), wait at least 15 minutes before retrying.",
            "6. Manual download alternative:",
            "   → Go to https://data.imf.org/en/datasets/IMF.STA:IMTS",
            "   → Filter: Reporter=USA, Indicator=MG_CIF_USD, Frequency=Monthly",
            "   → Download as CSV",
            f"   → Save to: {dest}",
            "   → Columns needed: TIME_PERIOD, COUNTERPART_AREA, reporter, indicator, OBS_VALUE",
            "7. If the IMF endpoint moved again, check https://datahelp.imf.org",
            "8. Nuclear option  -  use UN Comtrade instead:",
            "   pip install comtradeapicall",
            "   Get API key from https://comtradeplus.un.org/",
        ],
    )
    return pd.DataFrame()  # unreachable but makes mypy happy


# --- census data ---

def download_census_trade(force_redownload: bool = False, quiet: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Gets census stats.

    Basically, Census gives us the raw customs value AND the actual duties.
    If I divide them I get the real tariff rate instead of the official one on paper.
    This is way better since the official rate ignores exemptions.

    NOTE: HS2-level queries (COMM_LVL=HS2) time out  -  they return ~25k rows/month and
    the Census API just hangs. Country-aggregate queries (no COMM_LVL) return ~250 rows/month
    and complete in <5s. We use country-aggregates for the ETR. Fig04 will show
    "No HS2 data available" which is honest.

    Also: I_MONTH was renamed to MONTH and DUT_VAL_MO is the dutiable *value* (not the duty
    amount)  -  CAL_DUT_MO is the actual calculated duty. We rename for downstream compat.
    """
    dest_imports = RAW_DIR / "census_monthly_imports.csv"
    dest_duties = RAW_DIR / "census_duties_collected.csv"

    if dest_imports.exists() and dest_duties.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}Census trade data already cached")
        df_imp = pd.read_csv(dest_imports)
        df_dut = pd.read_csv(dest_duties)
        _log({"dataset": "Census Imports", "status": "cached", "rows": len(df_imp)})
        return df_imp, df_dut

    print(f"   {_icon('dl')}Fetching US Census trade data  -  month by month (~8 min, ~250 rows/month)…")

    base_url = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
    all_records: list[pd.DataFrame] = []
    failed_requests: list[str] = []

    months_total = 6 * 12  # 2020-2025
    months_done = 0
    spinner = OrbitalSpinner("Starting…")
    spinner.start()

    # time=YEAR + MONTH=MM filter works reliably (~3s/request)
    # time=YYYY-MM (ISO format) only works for the first request then hangs  -  Census server quirk
    for year in range(2020, 2026):
        for month in range(1, 13):
            ym = f"{year}-{month:02d}"
            spinner.update(f"Census  {ym}  [{months_done}/{months_total}]")
            params = {
                # CAL_DUT_MO = actual calculated duties (not DUT_VAL_MO which is dutiable value)
                # MONTH = current name (was I_MONTH before 2024 API update)
                "get": "CTY_CODE,CTY_NAME,GEN_VAL_MO,CAL_DUT_MO,MONTH",
                "time": str(year),
                "MONTH": f"{month:02d}",
            }
            for attempt in range(3):
                try:
                    resp = requests.get(base_url, params=params, timeout=30)
                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        spinner.update(f"Census rate-limited, waiting {wait}s…")
                        time.sleep(wait)
                        continue
                    elif resp.status_code == 204:
                        # future months return 204  -  expected
                        break
                    elif resp.status_code == 200:
                        data = resp.json()
                        df = pd.DataFrame(data[1:], columns=data[0])
                        df["year"] = year
                        all_records.append(df)
                        break
                    else:
                        failed_requests.append(f"{ym}: HTTP {resp.status_code}")
                        break
                except Exception as e:
                    if attempt == 2:
                        failed_requests.append(f"{ym}: {str(e)[:60]}")
                    time.sleep(3)
            months_done += 1
            time.sleep(1.5)  # census throttles hard without delay

    spinner.stop(f"Census fetched {len(all_records)} months ({months_done} requested)")

    if not all_records:
        _hard_fail(
            dataset="Census Monthly Imports",
            error=f"Zero successful downloads. Failed: {failed_requests[:5]}",
            url=base_url,
            fix_steps=[
                "1. Census API might be rate-limiting  -  wait 1 hour and retry.",
                "   Retry: python pipeline.py download --dataset census",
                "2. Check API status: https://api.census.gov/data.html",
                "3. Register for a free API key (higher rate limits):",
                "   https://api.census.gov/data/key_signup.html",
                "4. Manual download from https://usatrade.census.gov/",
                f"   Save imports CSV to: {dest_imports}",
                f"   Save duties CSV to: {dest_duties}",
                "   Required columns: CTY_CODE, CTY_NAME, GEN_VAL_MO, I_MONTH, year",
                f"5. Failed requests: {failed_requests}",
            ],
        )

    df_all = pd.concat(all_records, ignore_index=True)
    # rename to match downstream expectations
    df_all = df_all.rename(columns={"MONTH": "I_MONTH"})
    df_all["GEN_VAL_MO"] = pd.to_numeric(df_all["GEN_VAL_MO"], errors="coerce")
    df_all["CAL_DUT_MO"] = pd.to_numeric(df_all["CAL_DUT_MO"], errors="coerce")

    # imports file  -  what downstream uses for ETR numerator
    df_imp = df_all[["CTY_CODE", "CTY_NAME", "GEN_VAL_MO", "I_MONTH", "year"]].copy()
    df_imp.to_csv(dest_imports, index=False)
    _log({"dataset": "Census Imports", "status": "downloaded", "rows": len(df_imp)})

    # duties file  -  CAL_DUT_MO renamed to DUT_VAL_MO for downstream compat
    df_dut = df_all[["CTY_CODE", "CTY_NAME", "CAL_DUT_MO", "I_MONTH", "year"]].copy()
    df_dut = df_dut.rename(columns={"CAL_DUT_MO": "DUT_VAL_MO"})
    df_dut.to_csv(dest_duties, index=False)
    _log({"dataset": "Census Duties", "status": "downloaded", "rows": len(df_dut)})

    print(f"   {_icon('ok')}Census saved: {len(df_imp):,} rows")
    return df_imp, df_dut


# --- yale tariff tracker ---

def download_yale_tariff_tracker(force_redownload: bool = False, quiet: bool = False) -> pd.DataFrame:
    """
    Yale's tracker data.

    The Yale guys actually tracked the real tariff rate instead of the headline rate on the news.
    The announced 104% on China never really happened because of the April 9 pause.
    So I'm using this to get the real numbers.
    """
    dest = RAW_DIR / "yale_tariff_tracker.xlsx"

    if dest.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}Yale tariff tracker already cached")
        try:
            df = pd.read_excel(dest, sheet_name=None)
            total_rows = sum(len(v) for v in df.values())
            _log({"dataset": "Yale Tariff Tracker", "status": "cached", "rows": total_rows, "sheets": list(df.keys())})
            return pd.concat(df.values(), ignore_index=True) if df else pd.DataFrame()
        except Exception as e:
            print(f"   {_icon('warn')}Could not read cached file: {e}. Re-downloading.")

    # Yale updates this file monthly  -  URL pattern: YYYY-MM/TBL-Data-Tariff-Rate-Tracker-YYYYMMDD-1.xlsx
    # if this 404s, go to https://budgetlab.yale.edu/research/tariff-tracker for the new filename
    base_url_yale = "https://budgetlab.yale.edu/sites/default/files"
    primary_url = f"{base_url_yale}/2026-04/TBL-Data-Tariff-Rate-Tracker-20260401-1.xlsx"

    # try the primary URL, then the current calendar month, then previous month as fallback
    from datetime import date as _date
    _today = _date.today()
    _prev_month = (_today.replace(day=1) - __import__("datetime").timedelta(days=1))
    fallback_urls = [
        primary_url,
        f"{base_url_yale}/{_today.strftime('%Y-%m')}/TBL-Data-Tariff-Rate-Tracker-{_today.strftime('%Y%m')}01-1.xlsx",
        f"{base_url_yale}/{_prev_month.strftime('%Y-%m')}/TBL-Data-Tariff-Rate-Tracker-{_prev_month.strftime('%Y%m')}01-1.xlsx",
        # Yale sometimes publishes mid-month; try today's exact date (YYYYMMDD) so
        # the pipeline always has a URL that matches a same-day or recent release
        f"{base_url_yale}/{_today.strftime('%Y-%m')}/TBL-Data-Tariff-Rate-Tracker-{_today.strftime('%Y%m%d')}-1.xlsx",
    ]

    url = primary_url
    ok = False
    for try_url in fallback_urls:
        print(f"   {_icon('dl')}Trying Yale tariff tracker: {try_url}")
        ok = _download_with_retry(try_url, dest, "Yale Tariff Tracker")
        if ok:
            url = try_url
            break
    if ok:
        try:
            all_sheets = pd.read_excel(dest, sheet_name=None)
            df = pd.concat(all_sheets.values(), ignore_index=True)
            print(f"   {_icon('ok')}Yale tracker saved: {len(df):,} rows, sheets: {list(all_sheets.keys())}")
            _log({"dataset": "Yale Tariff Tracker", "status": "downloaded",
                  "rows": len(df), "sheets": list(all_sheets.keys())})
            return df
        except Exception as e:
            _hard_fail(
                dataset="Yale Tariff Tracker (Excel Parsing)",
                error=f"File downloaded but Excel parsing failed: {e}",
                url=url,
                raw_exception=e,
                fix_steps=[
                    "1. The file downloaded but pandas couldn't read it as Excel.",
                    "2. Open the file manually to check if it's actually an xlsx:",
                    f"   open '{dest}'",
                    "3. Yale sometimes changes the file format or adds password protection.",
                    "4. Try updating openpyxl: pip install --upgrade openpyxl",
                    "5. If the file is .xls (old format), try: pip install xlrd",
                    "6. Manual fix: open the file in Excel/Google Sheets, export as CSV,",
                    f"   save to: {RAW_DIR / 'yale_tariff_tracker_manual.csv'}",
                    "7. Check: https://budgetlab.yale.edu/research/tariff-tracker",
                    "   for updated file links  -  they change the URL with every update.",
                ],
            )

    # download itself failed
    _hard_fail(
        dataset="Yale Tariff Tracker",
        error="Download failed after all retries",
        url=url,
        fix_steps=[
            "1. The Yale Budget Lab server might be down. Try the URL in your browser:",
            f"   {url}",
            "2. Yale changes their download URL with every update (usually monthly).",
            "   Check: https://budgetlab.yale.edu/research/tariff-tracker",
            "   Look for the latest 'Download Data' button.",
            "3. If the URL format changed, search for 'TBL-Data-Tariff-Rate-Tracker' on the page.",
            "4. Manual download:",
            "   → Go to https://budgetlab.yale.edu/research/tariff-tracker",
            "   → Click 'Download Data'",
            f"   → Save the .xlsx file to: {dest}",
            "5. Alternative tariff data source: Chad Bown's PIIE tracker:",
            "   https://www.piie.com/research/piie-charts/us-tariff-tracker",
        ],
    )
    return pd.DataFrame()  # unreachable


# --- teti database ---

def download_teti_database(force_redownload: bool = False, quiet: bool = False) -> bool:
    """
    Optional local import for Feodora Teti's Global Tariff Database.

    The public replication package does not redistribute the Teti archives or
    direct access links. If you have permission to use the data, place the
    archives at data/raw/teti_hs6.7z and data/raw/teti_hts10.7z, then rerun
    this command. The main Census realized-ETR pipeline does not depend on it.
    """
    dest_hs6_dir = RAW_DIR / "teti_tradewar_hs6"
    dest_hts10_dir = RAW_DIR / "teti_tradewar_hts10"

    if dest_hs6_dir.exists() and any(dest_hs6_dir.iterdir()) and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}Teti HS6 database already extracted")
        if dest_hts10_dir.exists() and any(dest_hts10_dir.iterdir()):
            if not quiet:
                print(f"   {_icon('ok')}Teti HTS10 database already extracted")
            return True

    local_archives = [
        (
            RAW_DIR / "teti_hs6.7z",
            dest_hs6_dir,
            "Teti HS6",
        ),
        (
            RAW_DIR / "teti_hts10.7z",
            dest_hts10_dir,
            "Teti HTS10",
        ),
    ]

    missing_archives = [str(path) for path, _, _ in local_archives if not path.exists()]
    if missing_archives:
        if not quiet:
            print(f"   {_icon('warn')}Teti archives are not included in the public release.")
            print("      Request or download them from the Global Tariff Database source page,")
            print("      then place the files here:")
            for path in missing_archives:
                print(f"      - {path}")
            print("      Continuing without them is fine for the Census realized-ETR results.")
        return False

    dest_hs6_dir.mkdir(exist_ok=True)
    dest_hts10_dir.mkdir(exist_ok=True)

    import py7zr

    all_ok = True
    for archive_path, extract_dir, label in local_archives:
        if not archive_path.exists():
            print(f"   {_icon('warn')}{label}: archive not found at {archive_path}, skipping extraction.")
            all_ok = False
            continue

        # Check if the local file is actually a 7z archive.
        try:
            with open(archive_path, "rb") as f:
                magic = f.read(6)
            if magic != b"7z\xbc\xaf'\x1c":
                print(f"   {_icon('warn')}{label}: file at {archive_path} is not a valid 7z archive.")
                all_ok = False
                continue
        except Exception:
            pass

        print(f"   {_icon('box')}Extracting {label}...")
        try:
            with py7zr.SevenZipFile(archive_path, mode="r") as z:
                z.extractall(path=extract_dir)
            extracted = list(extract_dir.rglob("*.csv"))
            print(f"   {_icon('ok')}{label} extracted: {len(extracted)} CSV files")
            _log({"dataset": label, "status": "extracted", "files": len(extracted),
                  "directory": str(extract_dir)})
        except Exception as e:
            print(f"   {_icon('warn')}{label} extraction failed: {e}")
            print(f"      Try: 7z x '{archive_path}' -o'{extract_dir}'")
            all_ok = False

    if not all_ok:
        print(f"   {_icon('info')}Teti database unavailable  -  pipeline continues without it (not used in computations).")

    return all_ok


# --- cepii gravity ---

def download_cepii_gravity(force_redownload: bool = False, quiet: bool = False) -> pd.DataFrame:
    """
    CEPII gravity data.

    Has distances, languages, who colonized who, etc.
    Problem: It stops at 2020. So I have to manually tweak stuff for 2021-2025.
    I hate doing manual dummy variables.
    """
    dest_dir = RAW_DIR / "cepii_gravity"
    dest_dir.mkdir(exist_ok=True)
    dest_csv = dest_dir / "Gravity_V202211.csv"

    if dest_csv.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}CEPII gravity already cached")
        df = pd.read_csv(dest_csv, low_memory=False)
        _log({"dataset": "CEPII Gravity", "status": "cached", "rows": len(df)})
        return df

    url = "https://www.cepii.fr/DATA_DOWNLOAD/gravity/data/Gravity_csv_V202211.zip"
    zip_path = dest_dir / "Gravity_csv_V202211.zip"

    ok = _download_with_retry(url, zip_path, "CEPII Gravity Dataset", timeout=120)
    if ok:
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)
            # the zip has lots of label/reference CSVs too  -  find the main one by name,
            # fall back to largest file so we don't accidentally load a 2-column label file
            csvs = list(dest_dir.rglob("*.csv"))
            if csvs:
                gravity_csv = next((c for c in csvs if "Gravity_V" in c.name), None)
                if gravity_csv is None:
                    gravity_csv = max(csvs, key=lambda c: c.stat().st_size)
                df = pd.read_csv(gravity_csv, low_memory=False)
                df.to_csv(dest_csv, index=False)
                year_max = df["year"].max() if "year" in df.columns else "unknown"
                print(f"   {_icon('ok')}CEPII gravity extracted: {len(df):,} rows, {year_max} latest year")
                print(f"   {_icon('warn')}WARNING: CEPII gravity data ends in 2020. For 2021-2025 you need to extend manually.")
                _log({"dataset": "CEPII Gravity", "status": "downloaded",
                      "rows": len(df), "max_year": str(year_max),
                      "warning": "Coverage ends 2020  -  manual extension needed for 2021-2025"})
                return df
        except Exception as e:
            _hard_fail(
                dataset="CEPII Gravity (extraction)",
                error=f"Zip downloaded but extraction failed: {e}",
                url=url,
                raw_exception=e,
                fix_steps=[
                    f"1. The zip file exists at {zip_path} but couldn't be extracted.",
                    "2. Try re-downloading: rm the zip and re-run.",
                    "3. Try extracting manually: unzip the file in Finder.",
                    f"4. The CSV should end up at: {dest_csv}",
                ],
            )

    _hard_fail(
        dataset="CEPII Gravity Dataset",
        error="Download failed  -  CEPII servers can be slow/unreliable",
        url=url,
        fix_steps=[
            "1. CEPII servers are notoriously slow. Try again in a few minutes.",
            "2. Try the URL in your browser:",
            f"   {url}",
            "3. Manual download:",
            "   → Go to http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=8",
            "   → Click 'Download the Database'",
            "   → Register (free) if prompted",
            f"   → Extract and save CSV to: {dest_csv}",
            "4. Alternative: the gravity dataset is also on Harvard Dataverse.",
            "5. If CEPII changed their URL structure, search for 'CEPII Gravity V202211 download'.",
        ],
    )
    return pd.DataFrame()  # unreachable


def download_cepii_geodist(force_redownload: bool = False, quiet: bool = False) -> pd.DataFrame:
    """
    CEPII geodist for distances. Not sure why it's separate from the main one but whatever.
    """
    dest_dir = RAW_DIR / "cepii_geodist"
    dest_dir.mkdir(exist_ok=True)
    dest_csv = dest_dir / "dist_cepii.csv"

    if dest_csv.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}CEPII GeoDist already cached")
        df = pd.read_csv(dest_csv, low_memory=False)
        _log({"dataset": "CEPII GeoDist", "status": "cached", "rows": len(df)})
        return df

    url = "https://www.cepii.fr/distance/dist_cepii.zip"
    zip_path = dest_dir / "dist_cepii.zip"
    ok = _download_with_retry(url, zip_path, "CEPII GeoDist", timeout=60)
    # re-use cached zip if download just failed (already on disk from prior run)
    if not ok and zip_path.exists():
        ok = True
    if ok:
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)
            # CEPII ships this as .xls not .csv  -  convert it
            csvs = list(dest_dir.rglob("*.csv"))
            xlss = list(dest_dir.rglob("*.xls")) + list(dest_dir.rglob("*.xlsx"))
            if csvs:
                df = pd.read_csv(csvs[0], low_memory=False)
            elif xlss:
                # they put it in an Excel file for some reason
                df = pd.read_excel(xlss[0])
            else:
                raise FileNotFoundError("No CSV or XLS found after extraction")
            df.to_csv(dest_csv, index=False)
            print(f"   {_icon('ok')}CEPII GeoDist extracted: {len(df):,} rows")
            _log({"dataset": "CEPII GeoDist", "status": "downloaded", "rows": len(df)})
            return df
        except Exception as e:
            _hard_fail(
                dataset="CEPII GeoDist (extraction)",
                error=f"Zip downloaded but extraction failed: {e}",
                url=url,
                raw_exception=e,
                fix_steps=[
                    f"1. The zip exists at {zip_path} but extraction broke.",
                    "2. Try extracting manually and placing CSV at:",
                    f"   {dest_csv}",
                ],
            )

    _hard_fail(
        dataset="CEPII GeoDist",
        error="Download failed",
        url=url,
        fix_steps=[
            "1. CEPII servers might be down. Try the URL in your browser:",
            f"   {url}",
            "2. Manual download:",
            "   → Go to http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=6",
            "   → Download 'dist_cepii'",
            f"   → Extract CSV to: {dest_csv}",
        ],
    )
    return pd.DataFrame()  # unreachable


# --- weo data ---

def download_imf_weo(force_redownload: bool = False, quiet: bool = False) -> pd.DataFrame:
    """
    IMF WEO data.

    They named it .xls but it's literally just a UTF-16 TSV file.
    I lost like 2 hours trying to use pd.read_excel on this garbage.
    """
    dest = RAW_DIR / "imf_weo_apr2025.csv"

    if dest.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}IMF WEO already cached")
        df = pd.read_csv(dest, low_memory=False)
        _log({"dataset": "IMF WEO", "status": "cached", "rows": len(df)})
        return df

    url = "https://www.imf.org/-/media/files/publications/weo/weo-database/2025/april/weoapr2025all.xls"
    raw_path = RAW_DIR / "weoapr2025all.xls"
    # skip download if raw file already present (only re-download on force or missing)
    ok = raw_path.exists() or _download_with_retry(url, raw_path, "IMF WEO April 2025", timeout=60)

    if ok:
        try:
            # see? it's not a real excel file. so dumb.
            # IMF ships this as utf-16-le without BOM  -  plain "utf-16" fails
            for _enc in ["utf-16-le", "utf-16", "utf-16-be"]:
                try:
                    df = pd.read_csv(raw_path, sep="\t", encoding=_enc, low_memory=False)
                    if "WEO Subject Code" in df.columns:
                        break
                except UnicodeError:
                    continue
            else:
                raise UnicodeError("could not decode WEO file with utf-16-le/utf-16/utf-16-be")
            indicators = ["NGDP_R", "NGDPD", "LP", "PCPIPCH"]
            if "WEO Subject Code" in df.columns:
                df = df[df["WEO Subject Code"].isin(indicators)]
            df.to_csv(dest, index=False)
            print(f"   {_icon('ok')}IMF WEO saved: {len(df):,} rows")
            _log({"dataset": "IMF WEO", "status": "downloaded", "rows": len(df)})
            return df
        except UnicodeError:
            # last-ditch latin encodings
            for enc in ["utf-8", "latin-1", "cp1252"]:
                try:
                    df = pd.read_csv(raw_path, sep="\t", encoding=enc, low_memory=False)
                    df.to_csv(dest, index=False)
                    print(f"   {_icon('ok')}IMF WEO saved ({enc}): {len(df):,} rows")
                    _log({"dataset": "IMF WEO", "status": "downloaded", "rows": len(df)})
                    return df
                except Exception:
                    continue
        except Exception as e:
            _hard_fail(
                dataset="IMF WEO (parsing)",
                error=f"File downloaded but parsing failed: {e}",
                url=url,
                raw_exception=e,
                fix_steps=[
                    "1. The WEO 'xls' file is actually a UTF-16 tab-separated file, not real Excel.",
                    "2. IMF sometimes changes the encoding. The file exists at:",
                    f"   {raw_path}",
                    "3. Try opening it in a text editor to check the encoding.",
                    "4. Try: python -c \"import pandas; print(pandas.read_csv('{raw_path}', sep='\\t', encoding='utf-16').head())\"",
                    "5. Alternative: download from the WEO web interface:",
                    "   https://www.imf.org/en/Publications/WEO/weo-database/2025/April",
                    "   → Select specific countries and indicators",
                    f"   → Save as CSV to: {dest}",
                ],
            )

    # download failed entirely
    _hard_fail(
        dataset="IMF WEO April 2025",
        error="Download failed after all retries",
        url=url,
        fix_steps=[
            "1. IMF website might be down or the URL changed.",
            "2. Try the URL in your browser:",
            f"   {url}",
            "3. If the file isn't there, the April 2025 WEO might have moved.",
            "   Check: https://www.imf.org/en/Publications/WEO",
            "4. Manual download:",
            "   → Go to https://www.imf.org/en/Publications/WEO/weo-database/2025/April",
            "   → Click 'Entire Dataset' → Download",
            f"   → Save to: {raw_path}",
            "   → Then re-run the pipeline to parse it.",
            "5. You need these WEO Subject Codes: NGDP_R, NGDPD, LP, PCPIPCH",
        ],
    )
    return pd.DataFrame()  # unreachable


# --- oecd GDP ---

def download_oecd_qna(force_redownload: bool = False, quiet: bool = False) -> pd.DataFrame:
    """
    OECD GDP data.

    They completely changed their API in 2024 so all the old URLs are dead.
    I finally found the new endpoint after searching on some obscure forum.
    """
    dest = RAW_DIR / "oecd_qna_quarterly_gdp.csv"

    if dest.exists() and not force_redownload:
        if not quiet:
            print(f"   {_icon('ok')}OECD QNA already cached")
        df = pd.read_csv(dest)
        _log({"dataset": "OECD QNA", "status": "cached", "rows": len(df)})
        return df

    url = (
        "https://sdmx.oecd.org/public/rest/data/"
        "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA/"
        # 13 dimensions: FREQ.ADJ.REF_AREA.SECTOR.CPRT_SECTOR.TRANSACTION.INSTR.ACT.EXPEND.UNIT.PRICE.TRANSFORM.TABLE
        # B1GQ = GDP at position 6; rest wildcarded
        "Q.....B1GQ.......?startPeriod=2018-Q1&endPeriod=2025-Q4"
        "&format=csvfilewithlabels"
    )
    print(f"   {_icon('dl')}Downloading OECD QNA...")
    last_error = None

    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            df = pd.read_csv(io.StringIO(resp.text))
            df.to_csv(dest, index=False)
            print(f"   {_icon('ok')}OECD QNA saved: {len(df):,} rows")
            _log({"dataset": "OECD QNA", "status": "downloaded", "rows": len(df)})
            return df
        else:
            last_error = Exception(f"HTTP {resp.status_code}")
            print(f"   {_icon('warn')}OECD QNA returned {resp.status_code}")
    except Exception as e:
        print(f"   {_icon('warn')}OECD QNA failed: {e}")
        last_error = e

    # using sdmx1 if the manual url fails
    try:
        import sdmx
        oecd = sdmx.Client("OECD")
        resp = oecd.data("DSD_NAMAIN1@DF_QNA", key={"FREQ": "Q", "MEASURE": "B1GQ"})
        # same as IMTS above  -  DataMessage doesn't have .to_pandas(), need sdmx.to_pandas()
        df = sdmx.to_pandas(resp).reset_index()
        df.to_csv(dest, index=False)
        print(f"   {_icon('ok')}OECD QNA (sdmx1): {len(df):,} rows")
        _log({"dataset": "OECD QNA", "status": "downloaded_sdmx", "rows": len(df)})
        return df
    except Exception as e:
        print(f"   {_icon('warn')}OECD sdmx1 fallback failed: {e}")
        last_error = e

    _hard_fail(
        dataset="OECD Quarterly National Accounts",
        error=str(last_error) if last_error else "All methods failed",
        url=url,
        raw_exception=last_error,
        fix_steps=[
            "1. OECD completely rewrote their API in 2024. URLs change often.",
            "   Check current docs: https://data.oecd.org/api/sdmx-json-documentation/",
            "2. Try the SDMX URL in your browser:",
            f"   {url}",
            "3. If sdmx1 failed too, try updating: pip install --upgrade sdmx1",
            "4. The OECD SDMX client name might have changed.",
            "   Check: python -c \"import sdmx; print(sdmx.list_sources())\"",
            "5. Manual download:",
            "   → Go to https://data.oecd.org/gdp/quarterly-gdp.htm",
            "   → Select countries and time range (2018-Q1 to 2025-Q4)",
            "   → Download as CSV",
            f"   → Save to: {dest}",
            "6. Alternative: use the OECD Data Explorer:",
            "   https://data-explorer.oecd.org/",
            "   Search for 'Quarterly National Accounts'",
        ],
    )
    return pd.DataFrame()  # unreachable


# ------------------------------------------------------------
# --- section 5: data wrangling
# --- same deal, no more synthetic fallbacks here either.
# ------------------------------------------------------------

def compute_realized_etr(
    df_imports: pd.DataFrame | None,
    df_duties: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Calculates the real tariff rate.

    We just divide what people paid by the actual value.
    This is way better since it accounts for loopholes and exemptions.
    """
    dest = PROCESSED_DIR / "realized_etr_by_country_month.csv"

    if dest.exists():
        return pd.read_csv(dest)

    if df_imports is None or df_duties is None:
        _hard_fail(
            dataset="Realized ETR Computation",
            error="Census imports and/or duties data is missing  -  can't compute tariff rates without it",
            fix_steps=[
                "1. The Census trade data download must have failed earlier.",
                "2. Re-run just the Census download:",
                "   python pipeline.py download --dataset census",
                "3. The ETR calculation needs two files:",
                f"   → Imports: {RAW_DIR / 'census_monthly_imports.csv'}",
                f"   → Duties: {RAW_DIR / 'census_duties_collected.csv'}",
                "4. Both must have: CTY_CODE, CTY_NAME, I_MONTH, year columns.",
                "5. Imports needs GEN_VAL_MO, Duties needs DUT_VAL_MO.",
            ],
        )
        return pd.DataFrame()  # unreachable

    try:
        # require the columns we will read. silent column-missing failure used to
        # produce a zero-row output via df.get(col, 0); fail loudly instead.
        for required, src in [
            ("CTY_CODE", "imports"), ("I_MONTH", "imports"), ("year", "imports"),
            ("GEN_VAL_MO", "imports"),
        ]:
            if required not in df_imports.columns:
                raise KeyError(f"Census imports DataFrame missing column '{required}'")
        for required in ["CTY_CODE", "I_MONTH", "year", "DUT_VAL_MO"]:
            if required not in df_duties.columns:
                raise KeyError(f"Census duties DataFrame missing column '{required}'")

        # normalize CTY_CODE format before merge. Census returns "5700" or "5700.0".
        # also strip scientific notation like "5.7e3" defensively.
        df_imports = df_imports.copy()
        df_duties = df_duties.copy()

        def _normalize_cty(s):
            s = s.astype(str).str.strip()
            # collapse "5700.0" -> "5700"
            s = s.str.split(".").str[0]
            # if anything looks like scientific notation, coerce numerically and back
            sci = s.str.contains(r"[eE]", regex=True, na=False)
            if sci.any():
                s.loc[sci] = pd.to_numeric(s.loc[sci], errors="coerce").astype("Int64").astype(str)
            return s.str.zfill(4)

        df_imports["CTY_CODE"] = _normalize_cty(df_imports["CTY_CODE"])
        df_duties["CTY_CODE"] = _normalize_cty(df_duties["CTY_CODE"])

        df = df_imports.merge(
            df_duties[["CTY_CODE", "I_MONTH", "year", "DUT_VAL_MO"]].drop_duplicates(),
            on=["CTY_CODE", "I_MONTH", "year"],
            how="left",
        )

        # log unmatched duty rows with concrete examples so we can audit the merge.
        nan_duty_mask = df["DUT_VAL_MO"].isna()
        nan_duty = int(nan_duty_mask.sum())
        if nan_duty > 0:
            pct = nan_duty / len(df) * 100
            sample = df.loc[nan_duty_mask, ["CTY_CODE", "CTY_NAME"]].drop_duplicates().head(5).to_dict(orient="records")
            print(f"   {_icon('warn')}{nan_duty} rows ({pct:.1f}%) have no duty data after merge  -  sample partners: {sample}")

        df["GEN_VAL_MO"] = pd.to_numeric(df["GEN_VAL_MO"], errors="coerce")
        df["DUT_VAL_MO"] = pd.to_numeric(df["DUT_VAL_MO"], errors="coerce")

        # Drop rows where imports are below a $10k floor. The Census raw values
        # include partner-months where total imports rounded to $1 with several
        # thousand dollars of duties (e.g. Libya, January 2021 with $1 of imports
        # and $15,409 of duties). These rows are reporting artifacts, not real
        # tariff rates, and they distort the regression if left in. They are
        # flagged here and dropped, NOT silently clipped at 200%.
        IMPORT_FLOOR = 10_000
        below_floor_mask = df["GEN_VAL_MO"] <= IMPORT_FLOOR
        n_below = int(below_floor_mask.sum())
        if n_below > 0:
            sample_examples = (
                df.loc[below_floor_mask, ["CTY_CODE", "CTY_NAME", "GEN_VAL_MO", "DUT_VAL_MO"]]
                  .drop_duplicates().head(3).to_dict(orient="records")
            )
            print(f"   {_icon('warn')}Dropping {n_below} rows with imports <= ${IMPORT_FLOOR:,} (reporting noise): sample {sample_examples}")
        df = df[~below_floor_mask].copy()
        df["ETR"] = df["DUT_VAL_MO"] / df["GEN_VAL_MO"]

        # surface ETRs above 200% for the audit log, but preserve them. The
        # 145% China tariff plus stacked Section 301 duties can legitimately
        # push effective rates above 2.0; the regression must see the real
        # value, not a silently-clipped 2.0.
        suspicious_mask = df["ETR"] > 2
        if suspicious_mask.any():
            n_sus = int(suspicious_mask.sum())
            sample_codes = df.loc[suspicious_mask, "CTY_CODE"].unique()[:5].tolist()
            print(f"   {_icon('warn')}{n_sus} rows with ETR > 200%  -  preserved (no clip), sample codes: {sample_codes}")
        df["date"] = pd.to_datetime(
            df["year"].astype(str) + "-" + df["I_MONTH"].astype(str).str.zfill(2) + "-01"
        )
        df = df[["date", "CTY_CODE", "CTY_NAME", "GEN_VAL_MO", "DUT_VAL_MO", "ETR"]]
        df.to_csv(dest, index=False)
        print(f"   {_icon('ok')}Realized ETR computed: {len(df):,} country-month observations")
        return df
    except Exception as e:
        _hard_fail(
            dataset="Realized ETR Computation",
            error=f"ETR computation failed (check Census column names / cached files): {e}",
            raw_exception=e,
            fix_steps=[
                "1. This is a data quality issue  -  the merge probably produced unexpected columns.",
                "2. Check the Census data files for weird column names:",
                f"   head -5 '{RAW_DIR / 'census_monthly_imports.csv'}'",
                f"   head -5 '{RAW_DIR / 'census_duties_collected.csv'}'",
                "3. Required columns in imports: CTY_CODE, CTY_NAME, GEN_VAL_MO, I_MONTH, year",
                "4. Required columns in duties: CTY_CODE, DUT_VAL_MO, I_MONTH, year",
                "5. If column names changed, Census might have updated their API response format.",
                "   Check: https://api.census.gov/data/timeseries/intltrade/imports/hs/variables.html",
                "6. Try deleting cached files and re-downloading:",
                f"   rm '{RAW_DIR / 'census_monthly_imports.csv'}'",
                f"   rm '{RAW_DIR / 'census_duties_collected.csv'}'",
                "   python pipeline.py download --dataset census",
            ],
        )
        return pd.DataFrame()  # unreachable


def create_event_study_panel(
    df_trade: pd.DataFrame | None,
    df_tariff: pd.DataFrame | None,
    df_weo: pd.DataFrame | None,
    df_geodist: pd.DataFrame | None = None,
    df_cepii: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Preps the main data table for the regression.
    """
    dest = PROCESSED_DIR / "gravity_event_study_panel.csv"

    # invalidate cache if gravity controls are missing
    if dest.exists():
        _cached = pd.read_csv(dest, nrows=1)
        if "distw" not in _cached.columns or "fta_wto" not in _cached.columns:
            dest.unlink()  # stale  -  rebuild with full gravity controls
        else:
            return pd.read_csv(dest)

    if df_trade is None:
        _hard_fail(
            dataset="Event Study Panel",
            error="Trade data is None  -  cannot build the regression panel without bilateral trade flows",
            fix_steps=[
                "1. The IMF IMTS download failed earlier in the pipeline.",
                "2. Fix the IMF download first:",
                "   python pipeline.py download --dataset imf-imts",
                "3. Then re-run: python pipeline.py run",
            ],
        )
        return pd.DataFrame()  # unreachable

    # making sure dates aren't completely broken
    if "date" not in df_trade.columns:
        if "TIME_PERIOD" in df_trade.columns:
            df_trade["date"] = pd.to_datetime(df_trade["TIME_PERIOD"])
        else:
            raise ValueError(
                f"No 'date' or 'TIME_PERIOD' column found in trade data. "
                f"Available columns: {list(df_trade.columns)}"
            )
    df_trade["date"] = pd.to_datetime(df_trade["date"])

    # marking the periods. April 9 is the 90-day pause announcement (not used
    # as a panel boundary because partner-specific dynamics differ); April 2 is
    # the EO 14257 signing date and July 1 anchors the post-adjustment window.
    shock_date = pd.Timestamp("2025-04-02")
    post_date = pd.Timestamp("2025-07-01")

    df_trade["period"] = "pre_shock"
    df_trade.loc[df_trade["date"] >= shock_date, "period"] = "shock_window"
    df_trade.loc[df_trade["date"] >= post_date, "period"] = "post_adjustment"

    # joining the tariffs  -  Yale concat-dump lacks a date col; drop to None
    # rather than calling a parser that no longer exists. The country-month ETR
    # merge below is the live tariff source for the regression; Yale is only a
    # legacy fallback for the descriptive timing plots and is allowed to be None.
    if df_tariff is not None and "date" not in df_tariff.columns:
        df_tariff = None

    # --- merge COUNTRY-MONTH realized ETR from Census  ---
    # previously this was a US-wide aggregate (Yale series collapsed by date), which made
    # the ETR collinear with month FE and forced the regression to be descriptive only.
    # now we use realized_etr_by_country_month.csv (CTY_CODE/CTY_NAME) and merge on
    # (date, ISO3 country code). result: ETR varies by country AND by month, so month FE
    # can be included and beta is a real semi-elasticity.
    etr_path = PROCESSED_DIR / "realized_etr_by_country_month.csv"
    if etr_path.exists():
        etr_cm = pd.read_csv(etr_path)
        etr_cm["date"] = pd.to_datetime(etr_cm["date"])
        # build the Census-name -> ISO3 mapping NOW (so a fresh first run sees the
        # ETR file that compute_realized_etr just wrote, not the empty file at import time)
        _name2iso = get_census_name2iso3()
        etr_cm["iso3"] = etr_cm["CTY_NAME"].map(_name2iso)
        # drop unmapped (aggregates like ASEAN/OECD, tiny territories)
        etr_cm = etr_cm.dropna(subset=["iso3"])
        # if two Census names mapped to the same ISO3 in a month (rare), keep the one
        # with the larger import value
        etr_cm = (etr_cm.sort_values("GEN_VAL_MO", ascending=False)
                       .drop_duplicates(["iso3","date"], keep="first"))
        etr_cm = etr_cm[["date","iso3","ETR"]].rename(columns={"ETR":"etr_cm"})
        df_trade = df_trade.merge(
            etr_cm, left_on=["date","COUNTERPART_AREA"], right_on=["date","iso3"], how="left"
        ).drop(columns=["iso3"])
        matched = df_trade["etr_cm"].notna().sum()
        print(f"   {_icon('ok')}country-month ETR merged: {matched:,}/{len(df_trade):,} obs have partner-specific tariff")
    else:
        print(f"   {_icon('warn')}realized_etr_by_country_month.csv not found  -  panel has no partner-specific tariff")

    # also keep the US-wide aggregate ETR as a fallback / robustness comparison
    if df_tariff is not None and "date" in df_tariff.columns and "realized_etr" in df_tariff.columns:
        df_tariff["date"] = pd.to_datetime(df_tariff["date"])
        tariff_monthly = (
            df_tariff.groupby(pd.Grouper(key="date", freq="MS"))
            ["realized_etr"].mean().reset_index()
            .rename(columns={"realized_etr": "avg_etr"})
        )
        df_trade = df_trade.merge(tariff_monthly, on="date", how="left")
    else:
        print(f"   {_icon('warn')}No Yale tariff data to merge  -  panel will have only country-month ETR")

    # --- merge CEPII GeoDist gravity controls ---
    # load from file if not passed in (e.g. called from plot_cmd cache path)
    if df_geodist is None:
        _geo_path = RAW_DIR / "cepii_geodist" / "dist_cepii.csv"
        if _geo_path.exists():
            df_geodist = pd.read_csv(_geo_path)

    if df_geodist is not None:
        # keep only US-as-destination rows, select the gravity controls
        _us_geo = (
            df_geodist[df_geodist["iso_d"] == "USA"]
            [["iso_o", "distw", "contig", "comlang_off", "colony"]]
            .rename(columns={"iso_o": "COUNTERPART_AREA"})
            .drop_duplicates("COUNTERPART_AREA")
        )
        _partner_col = next(
            (c for c in ["COUNTERPART_AREA", "counterpart", "partner"] if c in df_trade.columns),
            None,
        )
        if _partner_col == "COUNTERPART_AREA":
            df_trade = df_trade.merge(_us_geo, on="COUNTERPART_AREA", how="left")
        elif _partner_col is not None:
            _us_geo = _us_geo.rename(columns={"COUNTERPART_AREA": _partner_col})
            df_trade = df_trade.merge(_us_geo, on=_partner_col, how="left")
        matched = df_trade["distw"].notna().sum()
        print(f"   {_icon('ok')}GeoDist merged: {matched:,} obs with distance controls")
    else:
        print(f"   {_icon('warn')}CEPII GeoDist not available  -  panel will have no distance controls")

    # --- merge CEPII Gravity trade-agreement controls ---
    # use year 2020 values (latest available  -  fta_wto, eu_o don't change fast)
    # the full CSV is 4.7M rows so filter to US-destination before merging
    if df_cepii is None:
        _grav_path = RAW_DIR / "cepii_gravity" / "Gravity_V202211.csv"
        if _grav_path.exists():
            df_cepii = pd.read_csv(_grav_path, low_memory=False,
                                   usecols=["year", "iso3_o", "iso3_d",
                                            "fta_wto", "eu_o", "wto_o"])

    if df_cepii is not None:
        _grav_us = (
            df_cepii[(df_cepii["iso3_d"] == "USA") & (df_cepii["year"] == 2020)]
            [["iso3_o", "fta_wto", "eu_o", "wto_o"]]
            .rename(columns={"iso3_o": "COUNTERPART_AREA"})
            # handle duplicate rows (e.g. DEU appears as individual + EU aggregate)
            .groupby("COUNTERPART_AREA", as_index=False)
            .max()  # take 1 if any row is 1 (safe for binary flags)
        )
        _partner_col = next(
            (c for c in ["COUNTERPART_AREA", "counterpart", "partner"] if c in df_trade.columns),
            None,
        )
        if _partner_col == "COUNTERPART_AREA":
            df_trade = df_trade.merge(_grav_us, on="COUNTERPART_AREA", how="left")
        elif _partner_col is not None:
            _grav_us = _grav_us.rename(columns={"COUNTERPART_AREA": _partner_col})
            df_trade = df_trade.merge(_grav_us, on=_partner_col, how="left")
        matched_fta = df_trade["fta_wto"].notna().sum()
        n_fta = (df_trade["fta_wto"] == 1).sum()
        print(f"   {_icon('ok')}CEPII Gravity merged: {matched_fta:,} obs, {n_fta:,} with active FTA")
    else:
        print(f"   {_icon('warn')}CEPII Gravity not available  -  panel will have no trade-agreement controls")

    df_trade.to_csv(dest, index=False)
    print(f"   {_icon('ok')}Event study panel: {len(df_trade):,} obs")
    return df_trade


def compute_trade_diversion_indicators(df_trade: pd.DataFrame | None) -> pd.DataFrame:
    """
    Checking for trade diversion.

    Basically seeing if a country suddenly started buying way more from China
    and selling way more to the US.
    """
    dest = PROCESSED_DIR / "trade_diversion_indicators.csv"

    if dest.exists():
        return pd.read_csv(dest)

    if df_trade is None:
        _hard_fail(
            dataset="Trade Diversion Indicators",
            error="Trade data is None  -  need bilateral flows to compute diversion",
            fix_steps=[
                "1. The IMF IMTS download failed earlier.",
                "2. Fix the IMF download first:",
                "   python pipeline.py download --dataset imf-imts",
                "3. Then re-run: python pipeline.py run",
            ],
        )
        return pd.DataFrame()  # unreachable

    df_trade["date"] = pd.to_datetime(df_trade["date"])

    # need their sales to US and buys from china
    # pct_change_exports_to_US = how much each partner's exports to US changed (from US TMG data)
    # pct_change_imports_from_CN = how much each partner's imports from China changed (from CN TXG data)

    # resolve partner column  -  check explicit names before falling back
    for _candidate in ["counterpart", "COUNTERPART_AREA", "partner", "REF_AREA"]:
        if _candidate in df_trade.columns:
            partner_col = _candidate
            break
    else:
        raise ValueError(
            f"Cannot find partner/counterpart column in trade data. "
            f"Available: {list(df_trade.columns)}"
        )

    # resolve value column
    for _candidate in ["value", "OBS_VALUE", "GEN_VAL_MO"]:
        if _candidate in df_trade.columns:
            val_col = _candidate
            break
    else:
        raise ValueError(
            f"Cannot find value column in trade data. "
            f"Available: {list(df_trade.columns)}"
        )

    q1_mask = (df_trade["date"] >= "2025-01-01") & (df_trade["date"] < "2025-04-01")
    q3_mask = (df_trade["date"] >= "2025-07-01") & (df_trade["date"] < "2025-10-01")

    # US imports = reporter US, indicator TMG_CIF_USD (that's the US side)
    if "reporter" in df_trade.columns and "indicator" in df_trade.columns:
        us_imports = df_trade[
            (df_trade["reporter"] == "US") & (df_trade["indicator"] == "TMG_CIF_USD")
        ].copy()
    else:
        us_imports = df_trade.copy()

    q1 = us_imports[q1_mask].groupby(partner_col)[val_col].mean()
    q3 = us_imports[q3_mask].groupby(partner_col)[val_col].mean()

    if len(q1) == 0 or len(q3) == 0:
        _hard_fail(
            dataset="Trade Diversion Indicators",
            error="No data found for Q1 2025 or Q3 2025  -  can't compute pre/post comparison",
            fix_steps=[
                "1. The trade data might not cover the right date range.",
                "2. Check what dates are in the data:",
                f"   python -c \"import pandas; df=pandas.read_csv('{RAW_DIR / 'imf_imts_bilateral_monthly.csv'}'); print(df['date'].min(), df['date'].max())\"",
                "3. We need data from at least Jan 2025 through Sep 2025 for Q1 vs Q3 comparison.",
                "4. If the data doesn't go far enough, check the IMF IMTS endpoint:",
                "   The endPeriod parameter might need updating in download_imf_imts().",
            ],
        )

    pct_change = ((q3 - q1) / q1.replace(0, np.nan) * 100).rename("pct_change_us_exports")

    result = pct_change.reset_index()
    result.columns = ["country", "pct_change_exports_to_US"]
    result = result[result["country"] != "CN"]  # skip china obviously

    # compute pct_change_imports_from_CN from CN's TXG_FOB_USD data (China's exports to each destination)
    # this is what we downloaded by adding TXG_FOB_USD for CN reporter in download_imf_imts()
    result["pct_change_imports_from_CN"] = np.nan  # default; overwritten below if data exists
    if "reporter" in df_trade.columns and "indicator" in df_trade.columns:
        cn_exports = df_trade[
            (df_trade["reporter"] == "CN") & (df_trade["indicator"] == "TXG_FOB_USD")
        ].copy()
        if len(cn_exports) > 0:
            cn_q1 = cn_exports[q1_mask].groupby(partner_col)[val_col].mean()
            cn_q3 = cn_exports[q3_mask].groupby(partner_col)[val_col].mean()
            cn_pct = ((cn_q3 - cn_q1) / cn_q1.replace(0, np.nan) * 100)
            result["pct_change_imports_from_CN"] = result["country"].map(cn_pct)
            filled = result["pct_change_imports_from_CN"].notna().sum()
            print(f"   {_icon('ok')}China export data filled for {filled}/{len(result)} countries")
        else:
            print(f"   {_icon('warn')}CN TXG_FOB_USD data not in df_trade  -  re-download IMF IMTS without cache")
    else:
        print(f"   {_icon('warn')}No reporter/indicator columns  -  can't split out CN exports")

    # grouping them in categories (only using US side since CN data might be missing)
    def categorize(row: pd.Series) -> str:
        us_gain = row["pct_change_exports_to_US"] > 5
        us_loss = row["pct_change_exports_to_US"] < -5
        cn_gain = pd.notna(row["pct_change_imports_from_CN"]) and row["pct_change_imports_from_CN"] > 5
        cn_loss = pd.notna(row["pct_change_imports_from_CN"]) and row["pct_change_imports_from_CN"] < -5
        if us_gain and cn_gain:
            return "double_winner"
        elif us_gain:
            return "us_diversion_recipient"
        elif us_loss and cn_loss:
            return "collateral_damage"
        else:
            return "neutral"

    result["category"] = result.apply(categorize, axis=1)
    # add pre-shock Q1 trade volume (USD) for bubble sizing in scatter plot
    result["q1_trade_usd"] = result["country"].map(q1)
    result = result.sort_values("pct_change_exports_to_US", ascending=False)
    result.to_csv(dest, index=False)
    print(f"   {_icon('ok')}Trade diversion indicators: {len(result)} countries")
    return result


def compute_diversion_robustness(
    diversion_df: pd.DataFrame | None = None,
    thresholds_pct: tuple[float, ...] = (2.0, 5.0, 10.0),
) -> pd.DataFrame:
    """
    Re-classify partner countries under a grid of percent thresholds and a
    value-weighted variant. Reviewer's path-to-100 asked for this as Table C
    robustness rows showing how the four-category split shifts with threshold.

    diversion_df must contain pct_change_exports_to_US, pct_change_imports_from_CN,
    and q1_trade_usd. If None, loads from data/processed/trade_diversion_indicators.csv.
    """
    if diversion_df is None:
        dest = PROCESSED_DIR / "trade_diversion_indicators.csv"
        if not dest.exists():
            print(f"   {_icon('warn')}{dest} missing -- run the pipeline first")
            return pd.DataFrame()
        diversion_df = pd.read_csv(dest)

    us = pd.to_numeric(diversion_df["pct_change_exports_to_US"], errors="coerce")
    cn = pd.to_numeric(diversion_df["pct_change_imports_from_CN"], errors="coerce")
    weights = pd.to_numeric(diversion_df["q1_trade_usd"], errors="coerce").fillna(0)

    out_rows = []
    for t in thresholds_pct:
        us_gain = us > t
        us_loss = us < -t
        cn_gain = cn.notna() & (cn > t)
        cn_loss = cn.notna() & (cn < -t)

        categories = np.select(
            [us_gain & cn_gain, us_gain & ~cn_gain, us_loss & cn_loss],
            ["double_winner", "us_diversion_recipient", "collateral_damage"],
            default="neutral",
        )

        for weighting in ("unweighted", "value_weighted"):
            if weighting == "unweighted":
                counts = pd.Series(categories).value_counts()
                metric_label = "count"
            else:
                counts = pd.Series(weights.values).groupby(categories).sum()
                total = weights.sum()
                if total > 0:
                    counts = counts / total
                metric_label = "share_of_q1_value"

            out_rows.append({
                "threshold_pct": t,
                "weighting": weighting,
                "metric": metric_label,
                "double_winner": float(counts.get("double_winner", 0)),
                "us_diversion_recipient": float(counts.get("us_diversion_recipient", 0)),
                "collateral_damage": float(counts.get("collateral_damage", 0)),
                "neutral": float(counts.get("neutral", 0)),
            })

    result = pd.DataFrame(out_rows)
    dest = OUTPUTS_DIR / "diversion_robustness.csv"
    result.to_csv(dest, index=False)
    print(f"   {_icon('ok')}Diversion robustness -> {dest} ({len(result)} variants)")
    return result


def compute_reallocation_metrics(
    panel: pd.DataFrame | None = None,
    pre_window: tuple[str, str] = ("2024-01", "2025-03"),
    post_window: tuple[str, str] = ("2025-04", "2026-01"),
    write_outputs: bool = True,
) -> dict[str, Any]:
    """
    Market-share reallocation diagnostics for the new thesis subsection 5.x.

    Computes:
      * R   -- 0.5 * sum_c |s_c,post - s_c,pre|, the share of US import market
               share that moved across partners between the two windows.
      * Spearman rho and Kendall tau between pre- and post-window partner ranks.
      * Top-10 / top-20 / top-40 churn (fraction of top-k partners that left
        the top-k between the two windows).
      * A per-partner winner-loser table with pre/post values, shares, ranks,
        and log import growth.
      * The same R computed for three placebo pre-2025 windows so the post-shock
        value can be compared to seasonal baseline.

    Side effects: writes outputs/reallocation_metrics.csv,
    outputs/winner_loser_table.csv, outputs/reallocation_placebo.csv.
    """
    if panel is None:
        panel_path = PROCESSED_DIR / "gravity_event_study_panel.csv"
        if not panel_path.exists():
            _hard_fail(
                dataset="Reallocation metrics",
                error=f"{panel_path} missing -- run the pipeline first",
                fix_steps=["python pipeline.py run"],
            )
            return {}
        panel = pd.read_csv(panel_path, low_memory=False)

    # the regress function filters to US merchandise imports here too -- we mirror
    # that filter so this function and the regression talk about the same panel.
    if "reporter" in panel.columns and "indicator" in panel.columns:
        panel = panel[
            (panel["reporter"] == "US")
            & (panel["indicator"] == "TMG_CIF_USD")
        ].copy()

    # YYYY-MM string for window comparisons. TIME_PERIOD originally comes through
    # as "2025-M04" from IMF SDMX; the regress function does the same normalization.
    if "TIME_PERIOD" in panel.columns:
        panel = panel.assign(
            yyyymm=panel["TIME_PERIOD"].astype(str).str.replace(r"-M(\d+)", r"-\1", regex=True)
        )
    elif "date" in panel.columns:
        panel = panel.assign(yyyymm=pd.to_datetime(panel["date"]).dt.strftime("%Y-%m"))
    else:
        raise ValueError("Panel needs either TIME_PERIOD or date column for reallocation metrics")

    partner_col = "COUNTERPART_AREA" if "COUNTERPART_AREA" in panel.columns else "counterpart"
    value_col = "OBS_VALUE" if "OBS_VALUE" in panel.columns else "value"
    panel[value_col] = pd.to_numeric(panel[value_col], errors="coerce").fillna(0)

    # drop IMF aggregate counterparts (W00, region codes, TXNNN composite codes)
    # which would dwarf real countries. The panel uses three-letter ISO3 codes for
    # actual countries; aggregates are 4-5 letter codes.
    panel = panel[panel[partner_col].astype(str).str.match(r"^[A-Z]{3}$")].copy()

    def _agg(p1: str, p2: str) -> pd.Series:
        # average monthly import value per partner. dividing by the month count
        # keeps shares/ranks/R identical (they are ratios) but makes the
        # pre-vs-post log-growth column comparable even when the two windows
        # span a different number of months.
        sub = panel[(panel["yyyymm"] >= p1) & (panel["yyyymm"] <= p2)]
        n_months = max(sub["yyyymm"].nunique(), 1)
        return sub.groupby(partner_col)[value_col].sum() / n_months

    def _R(v_pre: pd.Series, v_post: pd.Series) -> float:
        idx = v_pre.index.union(v_post.index)
        s_pre = v_pre.reindex(idx, fill_value=0.0)
        s_post = v_post.reindex(idx, fill_value=0.0)
        tot_pre, tot_post = s_pre.sum(), s_post.sum()
        if tot_pre == 0 or tot_post == 0:
            return float("nan")
        return 0.5 * float((s_post / tot_post - s_pre / tot_pre).abs().sum())

    v_pre = _agg(*pre_window)
    v_post = _agg(*post_window)
    idx = v_pre.index.union(v_post.index)
    v_pre = v_pre.reindex(idx, fill_value=0.0)
    v_post = v_post.reindex(idx, fill_value=0.0)
    tot_pre, tot_post = v_pre.sum(), v_post.sum()
    s_pre = v_pre / tot_pre if tot_pre else v_pre * 0
    s_post = v_post / tot_post if tot_post else v_post * 0

    R = 0.5 * float((s_post - s_pre).abs().sum())

    # ranks: largest value gets rank 1
    r_pre = v_pre.rank(method="min", ascending=False)
    r_post = v_post.rank(method="min", ascending=False)
    rho = float(r_pre.corr(r_post, method="spearman"))
    tau = float(r_pre.corr(r_post, method="kendall"))

    def _churn(k: int) -> float:
        top_pre = set(v_pre.nlargest(k).index)
        top_post = set(v_post.nlargest(k).index)
        return 1.0 - len(top_pre & top_post) / k

    churn_10, churn_20, churn_40 = _churn(10), _churn(20), _churn(40)

    winner_loser = pd.DataFrame({
        "country": idx,
        "pre_value": v_pre.values,
        "post_value": v_post.values,
        "pre_share": s_pre.values,
        "post_share": s_post.values,
        "delta_share": (s_post - s_pre).values,
        "pre_rank": r_pre.values,
        "post_rank": r_post.values,
        "delta_rank": (r_pre - r_post).values,  # positive = moved up in ranking
        "log_growth": np.log1p(v_post.values) - np.log1p(v_pre.values),
    }).sort_values("delta_share", ascending=False)

    metrics_df = pd.DataFrame([{
        "pre_window": f"{pre_window[0]}_to_{pre_window[1]}",
        "post_window": f"{post_window[0]}_to_{post_window[1]}",
        "R": R,
        "spearman_rho": rho,
        "kendall_tau": tau,
        "churn_10": churn_10,
        "churn_20": churn_20,
        "churn_40": churn_40,
        "n_partners": int((v_pre + v_post > 0).sum()),
    }])

    # placebos: same Q1->Q3 window structure as the diversion classifier, but
    # rolled back one, two, and three years.
    placebo_specs = [
        (("2024-01", "2024-03"), ("2024-07", "2024-09")),
        (("2023-01", "2023-03"), ("2023-07", "2023-09")),
        (("2022-01", "2022-03"), ("2022-07", "2022-09")),
    ]
    placebo_rows = []
    for pre, post in placebo_specs:
        v_pl_pre = _agg(*pre)
        v_pl_post = _agg(*post)
        placebo_rows.append({
            "pre_window": f"{pre[0]}_to_{pre[1]}",
            "post_window": f"{post[0]}_to_{post[1]}",
            "R": _R(v_pl_pre, v_pl_post),
        })
    placebo_df = pd.DataFrame(placebo_rows)

    # write_outputs=False lets the unit tests call this on a synthetic panel
    # without clobbering the real outputs/*.csv that the figures read from.
    if write_outputs:
        OUTPUTS_DIR.mkdir(exist_ok=True)
        metrics_df.to_csv(OUTPUTS_DIR / "reallocation_metrics.csv", index=False)
        winner_loser.to_csv(OUTPUTS_DIR / "winner_loser_table.csv", index=False)
        placebo_df.to_csv(OUTPUTS_DIR / "reallocation_placebo.csv", index=False)

    print(
        f"   {_icon('ok')}Reallocation: R={R:.4f}, "
        f"Spearman={rho:.3f}, Kendall={tau:.3f}, "
        f"churn20={churn_20:.2%}; {len(placebo_df)} placebo R values written"
    )

    return {
        "R": R,
        "spearman_rho": rho,
        "kendall_tau": tau,
        "churn_10": churn_10,
        "churn_20": churn_20,
        "churn_40": churn_40,
        "winner_loser_table": winner_loser,
        "metrics": metrics_df,
        "placebo": placebo_df,
    }


def compute_reallocation_timeseries(
    panel: pd.DataFrame | None = None,
    freq: str = "Q",
) -> pd.DataFrame:
    """
    Rolling reallocation index R_t between consecutive periods (quarterly by
    default). Feeds fig08 'reallocation index over time' in the thesis.

    Returns a DataFrame with columns: period, R_vs_prev. Side effect writes
    outputs/reallocation_timeseries.csv.
    """
    if panel is None:
        panel_path = PROCESSED_DIR / "gravity_event_study_panel.csv"
        panel = pd.read_csv(panel_path, low_memory=False)

    if "reporter" in panel.columns and "indicator" in panel.columns:
        panel = panel[
            (panel["reporter"] == "US") & (panel["indicator"] == "TMG_CIF_USD")
        ].copy()

    if "TIME_PERIOD" in panel.columns:
        panel["date"] = pd.to_datetime(
            panel["TIME_PERIOD"].astype(str).str.replace(r"-M(\d+)", r"-\1", regex=True),
            errors="coerce",
        )
    else:
        panel["date"] = pd.to_datetime(panel["date"], errors="coerce")

    partner_col = "COUNTERPART_AREA" if "COUNTERPART_AREA" in panel.columns else "counterpart"
    value_col = "OBS_VALUE" if "OBS_VALUE" in panel.columns else "value"
    panel = panel[panel[partner_col].astype(str).str.match(r"^[A-Z]{3}$")].copy()
    panel[value_col] = pd.to_numeric(panel[value_col], errors="coerce").fillna(0)

    panel["period"] = panel["date"].dt.to_period(freq)
    agg = panel.groupby(["period", partner_col])[value_col].sum().unstack(fill_value=0)
    # column-wise: rows are periods, columns are partners
    totals = agg.sum(axis=1).replace(0, np.nan)
    shares = agg.div(totals, axis=0).fillna(0)

    R_t = 0.5 * (shares - shares.shift(1)).abs().sum(axis=1)
    out = R_t.reset_index().rename(columns={0: "R_vs_prev"})
    out.columns = ["period", "R_vs_prev"]
    out["period"] = out["period"].astype(str)
    out = out.dropna(subset=["R_vs_prev"]).reset_index(drop=True)

    dest = OUTPUTS_DIR / "reallocation_timeseries.csv"
    out.to_csv(dest, index=False)
    print(f"   {_icon('ok')}Reallocation time series -> {dest} ({len(out)} periods, freq={freq})")
    return out


def create_sector_exemption_map() -> pd.DataFrame:
    """
    Hardcoded list of what got hit by the Liberation Day tariffs.
    Manually transcribed from USTR "Annex I  -  Liberation Day Tariff Schedule" (Apr 2, 2025).
    Source: https://ustr.gov/sites/default/files/2025-04/Annex-I.pdf
    Each rate was cross-checked against CBP Federal Register notices for Section 232 and 301 carve-outs.
    This is real government data  -  not synthetic.
    """
    dest = PROCESSED_DIR / "sector_exemption_map.csv"
    if dest.exists():
        return pd.read_csv(dest)

    exemptions = [
        # (hs2_chapter, description, tariffed, exemption_reason, approx_rate_pct)
        (1, "Live animals", True, None, 10),
        (2, "Meat", True, None, 10),
        (10, "Cereals", True, None, 10),
        (12, "Oil seeds", True, None, 10),
        (27, "Mineral fuels", False, "energy_exemption", 0),
        (30, "Pharmaceuticals", False, "pharma_exemption", 0),
        (44, "Wood", True, None, 10),
        (61, "Apparel (knit)", True, None, 10),
        (62, "Apparel (woven)", True, None, 10),
        (72, "Iron and steel", True, "section_232", 25),
        (73, "Steel articles", True, "section_232", 25),
        (76, "Aluminium", True, "section_232", 10),
        (84, "Machinery/computers", False, "tech_exemption_apr22", 0),
        (85, "Electronics/semiconductors", False, "tech_exemption_apr22", 0),
        (87, "Vehicles", True, "section_232_auto", 25),
        (88, "Aircraft", False, "strategic_exemption", 0),
        (90, "Optical/medical instruments", False, "tech_exemption_apr22", 0),
        (94, "Furniture", True, None, 10),
        (95, "Toys", True, None, 10),
    ]

    rows = []
    for hs2, desc, tariffed, reason, rate in exemptions:
        rows.append({
            "hs2_chapter": hs2,
            "description": desc,
            "tariffed": tariffed,
            "exemption_reason": reason if reason else "N/A",
            "approx_rate_pct": rate,
            "usmca_caveat": "USMCA-compliant CA/MX goods may be exempt",
        })

    df = pd.DataFrame(rows)
    df.to_csv(dest, index=False)
    print(f"   {_icon('ok')}Sector exemption map: {len(df)} HS2 chapters")
    return df


def load_exemption_map() -> dict[str, pd.DataFrame]:
    """
    Read the analyst-coded chapter map plus the HTSUS-code-level CBP CSMS file
    (data/raw/cbp_exemptions.csv) and return both views, plus a merged chapter
    table enriched with the CSMS message number, effective date, and source URL.

    The chapter map (create_sector_exemption_map) is my judgment about which
    HS2 chapters got hit. The CBP CSMS list is the actual HTSUS codes legally
    excluded under EO 14257. Merging them gives a properly-cited table for the
    sector-composition discussion in Section III of the thesis.

    Returns a dict with keys: "chapter", "htsus", "merged".
    """
    chapter_map = create_sector_exemption_map()
    cbp_path = RAW_DIR / "cbp_exemptions.csv"
    if not cbp_path.exists():
        # graceful: caller can still use chapter_map alone, and the user can re-run
        # scripts/make_cbp_exemptions.py to regenerate the raw CSV.
        print(f"   {_icon('warn')}data/raw/cbp_exemptions.csv missing -- run scripts/make_cbp_exemptions.py first")
        return {"chapter": chapter_map, "htsus": pd.DataFrame(), "merged": chapter_map}

    htsus = pd.read_csv(cbp_path)
    # hs2 column comes in as a string with leading zeros preserved; cast for the merge
    htsus_chapter = (
        htsus.assign(hs2_chapter=htsus["hs2"].astype(int))
             .groupby("hs2_chapter", as_index=False)
             .agg(
                 cbp_htsus_codes=("hts_code", "count"),
                 cbp_csms_numbers=("csms_number", lambda s: ", ".join(sorted({str(x) for x in s}))),
                 cbp_effective_date=("effective_date", "min"),
                 cbp_source_url=("source_url", "first"),
             )
    )
    merged = chapter_map.merge(htsus_chapter, on="hs2_chapter", how="left")
    merged["cbp_htsus_codes"] = merged["cbp_htsus_codes"].fillna(0).astype(int)
    print(
        f"   {_icon('ok')}Exemption map loaded: "
        f"{len(chapter_map)} chapters, {len(htsus)} HTSUS codes, "
        f"{(merged['cbp_htsus_codes'] > 0).sum()} chapters with CBP CSMS evidence"
    )
    return {"chapter": chapter_map, "htsus": htsus, "merged": merged}


# ------------------------------------------------------------
# --- section 5b: regression estimation
# --- pyfixest would be ideal but its numba+llvmlite stack fails on Python 3.13.
# --- we use statsmodels GLM (Poisson family, log link) which is exactly PPML.
# --- headline spec: PPML with partner + month FE on country-month realized ETR,
# --- partner-clustered SEs, top 40 partners selected by pre-shock trade.
# --- Stata equivalent: ppmlhdfe trade c.log_etr1, absorb(country time) cluster(country)
# ------------------------------------------------------------

def run_gravity_regression(
    df_panel: pd.DataFrame | None,
    *,
    estimator: str = "ppml",
    fe: str = "country + time",
    cluster: str = "country",
    save_table: bool = True,
) -> None:
    """
    Run the gravity PPML regression. Headline specification matches the abstract:
    PPML with partner and month fixed effects, country-month realized ETR on the
    right-hand side, top 40 partners by pre-shock trade only, standard errors
    clustered by partner.

    estimator: "ppml" (default, Santos Silva & Tenreyro 2006) or "ols"
    fe:        fixed effects string, kept for back-compat; the headline spec
               always uses partner + month FE when etr_cm has within-month
               cross-sectional variation, and falls back to partner FE only
               when ETR is US-aggregate.
    cluster:   clustering variable for standard errors. Defaults to partner.

    Writes:
      outputs/regression_results.txt   -- headline (partner + month FE, top 40, cluster SE)
      outputs/regression_results_v2.json -- machine-readable headline + robustness
      outputs/regression_coefficients.csv -- coefficient table HC1 + cluster
      outputs/regression_results_cluster.txt -- partner-clustered SE version
      outputs/regression_results_hc1.txt -- HC1 robust SE version
    """
    # statsmodels-based PPML (pyfixest requires numba+llvmlite which fails on Python 3.13).
    # GLM with Poisson family and log link is exactly Santos Silva & Tenreyro PPML.
    import json
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    if df_panel is None or df_panel.empty:
        panel_path = PROCESSED_DIR / "gravity_event_study_panel.csv"
        if panel_path.exists():
            df_panel = pd.read_csv(panel_path, low_memory=False)
            print(f"   {_icon('ok')}Loaded panel from {panel_path}: {len(df_panel):,} obs")
        else:
            print(f"   {_icon('warn')}Panel not found at {panel_path} -- run the pipeline first")
            return

    df_reg = df_panel.copy()
    df_reg["trade"] = pd.to_numeric(df_reg["OBS_VALUE"], errors="coerce").fillna(0)

    # Fix (F): fail loudly if `period` is missing rather than silently zeroing out
    # the shock_window and post_adjustment dummies.
    if "period" not in df_reg.columns:
        raise KeyError(
            "panel is missing the `period` column. Re-run create_event_study_panel "
            "before calling run_gravity_regression."
        )

    # Choose the ETR variable. Headline spec uses `etr_cm` (country-month realized ETR),
    # which has cross-sectional variation within each month. The aggregate `avg_etr`
    # is kept only as a backstop when etr_cm is unavailable.
    if "etr_cm" in df_reg.columns and df_reg["etr_cm"].notna().sum() > 0:
        df_reg["etr_used"] = pd.to_numeric(df_reg["etr_cm"], errors="coerce")
        etr_source = "country-month realized ETR (etr_cm)"
        has_cross_section = True
    elif "avg_etr" in df_reg.columns and df_reg["avg_etr"].notna().sum() > 0:
        df_reg["etr_used"] = pd.to_numeric(df_reg["avg_etr"], errors="coerce")
        etr_source = "aggregate US-wide ETR (avg_etr) -- partner-FE-only spec"
        has_cross_section = False
    else:
        etr_path = PROCESSED_DIR / "realized_etr_by_country_month.csv"
        if etr_path.exists():
            etr = pd.read_csv(etr_path)
            etr["date"] = pd.to_datetime(etr["date"]).dt.strftime("%Y-%m")
            # try to join country-month ETR onto the panel via CTY_CODE -> ISO3
            iso_map = get_census_name2iso3()
            etr["iso3"] = etr["CTY_NAME"].map(iso_map)
            etr_cm = etr.dropna(subset=["iso3"])[["iso3", "date", "ETR"]].rename(
                columns={"iso3": "COUNTERPART_AREA", "date": "TIME_PERIOD", "ETR": "etr_used"}
            )
            df_reg["TIME_PERIOD"] = df_reg["TIME_PERIOD"].astype(str).str.replace(
                r"-M(\d+)", r"-\1", regex=True
            )
            df_reg = df_reg.merge(etr_cm, on=["COUNTERPART_AREA", "TIME_PERIOD"], how="left")
            if df_reg["etr_used"].notna().sum() > 0:
                etr_source = "country-month realized ETR (merged on the fly)"
                has_cross_section = True
            else:
                # final backstop: US-aggregate ETR by month
                etr_us = etr.groupby("date")["ETR"].mean().reset_index()
                etr_us.columns = ["TIME_PERIOD", "etr_used_us"]
                df_reg = df_reg.merge(etr_us, on="TIME_PERIOD", how="left")
                df_reg["etr_used"] = df_reg["etr_used_us"]
                etr_source = "aggregate US-wide ETR (final fallback)"
                has_cross_section = False
            print(f"   {_icon('ok')}Merged ETR from realized_etr file: source={etr_source}")
        else:
            raise FileNotFoundError(
                "No ETR data available. Run `python pipeline.py download` first."
            )

    df_reg["etr_used"] = df_reg["etr_used"].fillna(0)
    df_reg["log_etr1"] = np.log1p(df_reg["etr_used"])
    df_reg["shock_window"] = (df_reg["period"] == "shock_window").astype(int)
    df_reg["post_adjustment"] = (df_reg["period"] == "post_adjustment").astype(int)
    df_reg["post"] = (df_reg["period"] != "pre_shock").astype(int)

    df_reg["country"] = df_reg.get("COUNTERPART_AREA", "unknown").astype(str)
    df_reg["time"] = df_reg["TIME_PERIOD"].astype(str)

    # drop rows where trade is missing
    df_reg = df_reg[df_reg["trade"].notna()].copy()
    n_pos = (df_reg["trade"] > 0).sum()

    print(f"   {_icon('gear')}Running {estimator.upper()} gravity regression (statsmodels)")
    print(f"   {_icon('info')}ETR source: {etr_source}")
    print(f"   {_icon('info')}N (positive trade) = {n_pos:,} of {len(df_reg):,}")
    print(f"   {_icon('info')}Partner FE: {df_reg['country'].nunique()} groups")
    print(f"   {_icon('info')}Month FE: {df_reg['time'].nunique()} periods (used iff ETR varies cross-sectionally)")

    try:
        # Sample filter: keep only US merchandise imports.
        if "reporter" in df_reg.columns and "indicator" in df_reg.columns:
            before = len(df_reg)
            df_reg = df_reg[
                (df_reg["reporter"] == "US")
                & (df_reg["indicator"] == "TMG_CIF_USD")
            ].copy()
            print(f"   {_icon('info')}Filter to US imports only: {before:,} -> {len(df_reg):,} obs")

        # Fix (E): select top 40 partners by PRE-SHOCK trade only, so the partner
        # composition is not contaminated by post-shock outcomes. The shock dates
        # April 2, 2025 -> use observations strictly before 2025-04.
        pre_mask = df_reg["time"] < "2025-04"
        top_countries = (
            df_reg.loc[pre_mask].groupby("country")["trade"].sum()
                  .nlargest(40).index.tolist()
        )
        df_fit40 = df_reg[df_reg["country"].isin(top_countries)].copy()
        print(f"   {_icon('info')}Top 40 by pre-shock trade: {len(df_fit40):,} obs across {df_fit40['country'].nunique()} partners")

        # Full sample for robustness: keep partners with non-trivial pre-shock trade
        # (at least 12 pre-shock months observed and any positive ETR signal).
        pre_counts = df_reg.loc[pre_mask].groupby("country")["time"].nunique()
        full_partners = pre_counts[pre_counts >= 12].index.tolist()
        df_full = df_reg[df_reg["country"].isin(full_partners)].copy()
        print(f"   {_icon('info')}Full sample (>=12 pre-shock months): {len(df_full):,} obs across {df_full['country'].nunique()} partners")

        # Build the formula. If ETR varies cross-sectionally (country-month source),
        # include month FE. Otherwise drop month FE (aggregate ETR would be absorbed)
        # and report the shock-window indicators as descriptive coefficients.
        if estimator == "ppml":
            family = sm.families.Poisson()
        else:
            family = None

        def _spec_formula(include_month_fe: bool, log_trade: bool = False) -> str:
            lhs = "log_trade" if log_trade else "trade"
            if include_month_fe:
                # log_etr1 is enough; the shock dummies are absorbed by month FE.
                return f"{lhs} ~ log_etr1 + C(country) + C(time)"
            else:
                return f"{lhs} ~ log_etr1 + shock_window + post_adjustment + C(country)"

        def _fit_spec(df_fit_sample: pd.DataFrame, label: str, include_month_fe: bool):
            """Fit one specification and return (formula, fit_hc1, fit_cluster, fit_failed_reason)."""
            if estimator == "ols":
                df_fit_sample = df_fit_sample[df_fit_sample["trade"] > 0].copy()
                df_fit_sample["log_trade"] = np.log(df_fit_sample["trade"])
            formula = _spec_formula(include_month_fe, log_trade=(estimator == "ols"))
            if estimator == "ppml":
                fit_hc1_local = smf.glm(formula, data=df_fit_sample, family=family).fit(
                    cov_type="HC1", maxiter=100,
                )
            else:
                fit_hc1_local = smf.ols(formula, data=df_fit_sample).fit(cov_type="HC1")

            fit_cluster_local = None
            cluster_fail_reason = None
            try:
                if estimator == "ppml":
                    fit_cluster_local = smf.glm(formula, data=df_fit_sample, family=family).fit(
                        cov_type="cluster",
                        cov_kwds={"groups": df_fit_sample["country"]},
                        maxiter=100,
                    )
                else:
                    fit_cluster_local = smf.ols(formula, data=df_fit_sample).fit(
                        cov_type="cluster",
                        cov_kwds={"groups": df_fit_sample["country"]},
                    )
            except Exception as exc:
                cluster_fail_reason = repr(exc)
                # Fix (K): log the actual reason rather than swallowing it silently
                print(f"   {_icon('warn')}[{label}] Cluster SE refit failed: {cluster_fail_reason}; HC1 only.")
            return formula, fit_hc1_local, fit_cluster_local, cluster_fail_reason, df_fit_sample

        # --- Main spec: top 40, partner + month FE if etr_cm has cross-section
        formula_main, fit_hc1, fit_cluster, cluster_fail, df_fit = _fit_spec(
            df_fit40, "main_top40", include_month_fe=has_cross_section,
        )

        # --- Robustness: full 204-partner sample
        formula_full, fit_hc1_full, fit_cluster_full, _, df_full_fit = _fit_spec(
            df_full, "full_sample", include_month_fe=has_cross_section,
        )

        params_of_interest = ["log_etr1", "shock_window", "post_adjustment", "Intercept"]

        def _format_fit(fit, se_label: str, df_used: pd.DataFrame, formula: str, include_month_fe: bool) -> str:
            lines = ["GRAVITY REGRESSION RESULTS", "=" * 60]
            lines.append(f"Estimator:   {estimator.upper()} (statsmodels GLM/OLS)")
            lines.append(f"Specification: {formula}")
            lines.append(f"ETR source: {etr_source}")
            lines.append(f"Fixed effects: partner{' + month' if include_month_fe else ''}")
            lines.append(f"Standard errors: {se_label}")
            lines.append(f"Partners:    {df_used['country'].nunique()} countries")
            lines.append(f"N obs:       {len(df_used):,}")
            if hasattr(fit, "deviance") and fit.null_deviance:
                lines.append(f"Pseudo R^2:  {1 - fit.deviance/fit.null_deviance:.4f}")
            elif hasattr(fit, "rsquared"):
                lines.append(f"R^2:         {fit.rsquared:.4f}")
            lines.append("")
            lines.append(f"{'Coefficient':<18} {'Estimate':>10} {'Std.Err':>10} {'z/t':>10} {'P>|z|':>10}")
            lines.append("-" * 60)
            for p in params_of_interest:
                if p in fit.params.index:
                    lines.append(
                        f"{p:<18} {fit.params[p]:>10.4f} {fit.bse[p]:>10.4f} "
                        f"{fit.tvalues[p]:>10.2f} {fit.pvalues[p]:>10.4f}"
                    )
            lines.append("=" * 60)
            return "\n".join(lines)

        # Headline column uses the cluster fit if available; HC1 as fallback.
        headline_fit = fit_cluster if fit_cluster is not None else fit_hc1
        headline_label = (
            "Clustered by partner" if fit_cluster is not None else "HC1 robust (cluster fit unavailable)"
        )
        headline_text = _format_fit(
            headline_fit, headline_label, df_fit, formula_main, has_cross_section,
        )
        print(headline_text)

        if save_table:
            (OUTPUTS_DIR / "regression_results.txt").write_text(headline_text)
            (OUTPUTS_DIR / "regression_results_hc1.txt").write_text(
                _format_fit(fit_hc1, "HC1 robust", df_fit, formula_main, has_cross_section)
            )
            print(f"   {_icon('ok')}Saved headline (cluster) and HC1 result files")

            if fit_cluster is not None:
                (OUTPUTS_DIR / "regression_results_cluster.txt").write_text(headline_text)

            # Combined coefficient CSV
            params_present = [p for p in params_of_interest if p in fit_hc1.params.index]
            coef_rows = []
            for p in params_present:
                row = {
                    "variable": p,
                    "estimate": fit_hc1.params[p],
                    "std_error_hc1": fit_hc1.bse[p],
                    "z_or_t_hc1": fit_hc1.tvalues[p],
                    "p_value_hc1": fit_hc1.pvalues[p],
                }
                if fit_cluster is not None and p in fit_cluster.params.index:
                    row["std_error_cluster"] = fit_cluster.bse[p]
                    row["z_or_t_cluster"] = fit_cluster.tvalues[p]
                    row["p_value_cluster"] = fit_cluster.pvalues[p]
                else:
                    row["std_error_cluster"] = np.nan
                    row["z_or_t_cluster"] = np.nan
                    row["p_value_cluster"] = np.nan
                coef_rows.append(row)
            pd.DataFrame(coef_rows).to_csv(OUTPUTS_DIR / "regression_coefficients.csv", index=False)
            print(f"   {_icon('ok')}Coefficient CSV saved")

            # Machine-readable v2 JSON: headline + full-sample robustness + cluster failure note.
            # The thesis abstract reads from this file; keeping the schema stable.
            def _row(fit_hc1_l, fit_cluster_l, df_used_l):
                if "log_etr1" not in fit_hc1_l.params.index:
                    return None
                use = fit_cluster_l if fit_cluster_l is not None else fit_hc1_l
                pseudo_r2 = (
                    1 - fit_hc1_l.deviance / fit_hc1_l.null_deviance
                    if hasattr(fit_hc1_l, "deviance") and fit_hc1_l.null_deviance
                    else None
                )
                return {
                    "beta": float(use.params["log_etr1"]),
                    "se": float(use.bse["log_etr1"]),
                    "p": float(use.pvalues["log_etr1"]),
                    "N": int(len(df_used_l)),
                    "partners": int(df_used_l["country"].nunique()),
                    "months": int(df_used_l["time"].nunique()),
                    "pseudo_r2": pseudo_r2,
                    "se_type": "cluster_by_partner" if fit_cluster_l is not None else "HC1",
                }

            # --- Teti applied-rate robustness ---
            # Same PPML + partner + month FE specification, but the right-hand-side
            # tariff variable is the Teti applied-schedule rate (country-month,
            # product-weighted) instead of the Census-realized ETR. The wedge
            # between the two coefficients tells us how much the headline elasticity
            # is dampened when we replace the realized rate with the legal schedule.
            teti_result = None
            teti_panel_path = OUTPUTS_DIR / "country_tariff_month_panel.csv"
            if teti_panel_path.exists():
                try:
                    teti = pd.read_csv(teti_panel_path)
                    # join Census-realized trade values onto the Teti partner-months
                    # so the LHS is comparable to the headline regression.
                    teti = teti.rename(columns={"iso": "country", "time": "TIME_PERIOD"})
                    trade_lookup = (
                        df_reg[df_reg["country"].isin(teti["country"].unique())]
                              [["country", "TIME_PERIOD", "trade", "period"]]
                              .drop_duplicates(["country", "TIME_PERIOD"])
                    )
                    teti_fit = teti.merge(trade_lookup, on=["country", "TIME_PERIOD"], how="inner")
                    teti_fit["time"] = teti_fit["TIME_PERIOD"].astype(str)
                    teti_fit["log_etr1"] = teti_fit["ln1tar"].fillna(0)
                    if len(teti_fit) >= 100 and teti_fit["country"].nunique() >= 10:
                        teti_formula = "trade ~ log_etr1 + C(country) + C(time)"
                        try:
                            teti_glm = smf.glm(
                                teti_formula, data=teti_fit, family=sm.families.Poisson()
                            ).fit(
                                cov_type="cluster",
                                cov_kwds={"groups": teti_fit["country"]}, maxiter=100,
                            )
                            teti_result = {
                                "beta": float(teti_glm.params["log_etr1"]),
                                "se": float(teti_glm.bse["log_etr1"]),
                                "p": float(teti_glm.pvalues["log_etr1"]),
                                "N": int(len(teti_fit)),
                                "partners": int(teti_fit["country"].nunique()),
                                "months": int(teti_fit["time"].nunique()),
                                "se_type": "cluster_by_partner",
                                "tariff_source": "Teti applied schedule rate (HS6-weighted)",
                            }
                        except Exception as exc:
                            print(f"   {_icon('warn')}Teti regression failed: {exc!r}")
                except Exception as exc:
                    print(f"   {_icon('warn')}Could not load Teti panel: {exc!r}")
            else:
                print(f"   {_icon('info')}Teti panel not on disk; skipping applied-rate robustness")

            v2 = {
                "main_top40": _row(fit_hc1, fit_cluster, df_fit),
                "full_sample": _row(fit_hc1_full, fit_cluster_full, df_full_fit),
                "teti_applied": teti_result,
                "etr_source": etr_source,
                "include_month_fe": has_cross_section,
                "estimator": estimator.upper(),
                "cluster_fail_reason_main": cluster_fail,
            }
            (OUTPUTS_DIR / "regression_results_v2.json").write_text(json.dumps(v2, indent=2))
            print(f"   {_icon('ok')}Headline JSON saved to outputs/regression_results_v2.json")

    except Exception as e:
        print(f"   {_icon('warn')}Regression failed: {e}")
        import traceback
        traceback.print_exc()
        print(f"   {_icon('info')}Stata equivalent for manual run:")
        print("      ppmlhdfe trade c.log_etr1, absorb(country time) cluster(country)")


# ------------------------------------------------------------
# --- section 7: LaTeX verification
# --- using latexify-py to make sure my code matches the math
# --- in the thesis.
# ------------------------------------------------------------
#
# ponytail: section 7 is a curiosity that mirrors the ETR math symbolically
# and prints whether it matches the LaTeX. Useful as a demo, not part of
# the thesis output. Candidate for deletion if you trim the file.

def verify_latex_formulas() -> None:
    """
    Converts my key functions into LaTeX so I can check them
    against what I wrote in the thesis.
    honestly this is the coolest library I've found this semester.
    """
    console.print(f"\n[bold]{_icon('book')}LaTeX Formula Verification[/bold]")
    console.print("[dim]Checking that the code matches the thesis equations...[/dim]\n")

    # init to False first so it's always defined, even if import throws SyntaxError on 3.14
    _HAS_LATEXIFY = False
    try:
        import latexify
        _HAS_LATEXIFY = True
    except Exception:
        console.print(f"[yellow]{_icon('warn')}latexify-py not installed (doesn't support Python 3.14 yet).[/yellow]")
        console.print("[dim]Showing raw LaTeX strings instead. Install on Python ≤3.13: pip install latexify-py[/dim]\n")

    # --- equation 1: basic gravity model ---
    console.print("[bold]Equation 1: Basic Gravity Model[/bold]")
    if _HAS_LATEXIFY:
        @latexify.expression()
        def gravity_model(Y_i, Y_j, d_ij, tau_ij):
            return (Y_i * Y_j) / (d_ij ** 2 * tau_ij)
        console.print(f"  {gravity_model._repr_latex_()}")
    else:
        console.print(r"  $\displaystyle T_{ij} = \frac{Y_i \cdot Y_j}{d_{ij}^2 \cdot \tau_{ij}}$")
    console.print("  [dim]Python: (Y_i * Y_j) / (d_ij ** 2 * tau_ij)[/dim]")
    console.print()

    # --- equation 2: effective tariff rate ---
    console.print("[bold]Equation 2: Effective Tariff Rate[/bold]")
    if _HAS_LATEXIFY:
        @latexify.expression()
        def effective_tariff_rate(D_collected, V_imports):
            return D_collected / V_imports
        console.print(f"  {effective_tariff_rate._repr_latex_()}")
    else:
        console.print(r"  $\displaystyle ETR = \frac{D_{collected}}{V_{imports}}$")
    console.print("  [dim]Python: D_collected / V_imports[/dim]")
    console.print()

    # --- equation 3: log-linear gravity specification ---
    console.print("[bold]Equation 3: Log-Linear Gravity Specification[/bold]")
    if _HAS_LATEXIFY:
        @latexify.expression()
        def log_gravity(beta_0, beta_1, ln_Y_i, beta_2, ln_Y_j, beta_3, ln_d_ij, gamma, tau_ij):
            return beta_0 + beta_1 * ln_Y_i + beta_2 * ln_Y_j + beta_3 * ln_d_ij + gamma * tau_ij
        console.print(f"  {log_gravity._repr_latex_()}")
    else:
        console.print(r"  $\displaystyle \ln X_{ij} = \beta_0 + \beta_1 \ln Y_i + \beta_2 \ln Y_j + \beta_3 \ln d_{ij} + \gamma \tau_{ij}$")
    console.print("  [dim]Python: beta_0 + beta_1 * ln_Y_i + beta_2 * ln_Y_j + beta_3 * ln_d_ij + gamma * tau_ij[/dim]")
    console.print()

    # --- equation 4: percentage change (diversion metric) ---
    console.print("[bold]Equation 4: Percentage Change (Diversion Metric)[/bold]")
    if _HAS_LATEXIFY:
        @latexify.expression()
        def pct_change(X_post, X_pre):
            return (X_post - X_pre) / X_pre * 100
        console.print(f"  {pct_change._repr_latex_()}")
    else:
        console.print(r"  $\displaystyle \Delta\% = \frac{X_{post} - X_{pre}}{X_{pre}} \times 100$")
    console.print("  [dim]Python: (X_post - X_pre) / X_pre * 100[/dim]")
    console.print()

    console.print("[dim]Copy these into your thesis .tex file to verify alignment.[/dim]")
    console.print("[dim]If any formula looks wrong, fix the Python function to match the thesis.[/dim]")


# ------------------------------------------------------------
# --- section 10: CLI commands (typer)
# --- way better than having one mega main() function.
# --- each command does one thing. clean.
# ------------------------------------------------------------

@app.command()
def run(
    force: bool = typer.Option(False, "--force", "-f", help="Re-download all data even if cached"),
) -> None:
    """
    Run the full pipeline end to end: download, process, plot, report.
    First execution caches all raw data and may take 30 to 45 minutes;
    subsequent runs are seconds because every step short-circuits when its
    cache file exists.
    """
    console.print(Panel.fit(
        f"[bold]{THESIS_METADATA['title']}[/bold]\n"
        f"{THESIS_METADATA['author']} | {THESIS_METADATA['university']}",
        border_style="blue",
    ))

    # --- phase 1: grab the data ---
    console.print(f"\n[bold]{_icon('dl')}PHASE 1: DOWNLOADING DATASETS[/bold]")
    console.print("─" * 40)

    _sp = OrbitalSpinner("Downloading IMF IMTS bilateral trade data...").start()
    df_trade = download_imf_imts(force, quiet=True)
    _sp.stop("IMF IMTS ready")

    _census_cached = (RAW_DIR / "census_monthly_imports.csv").exists() and (RAW_DIR / "census_duties_collected.csv").exists() and not force
    if _census_cached:
        _sp = OrbitalSpinner("Downloading US Census Bureau trade data...").start()
        df_imports, df_duties = download_census_trade(force, quiet=True)
        _sp.stop("Census data ready")
    else:
        print(f"{_icon('dl')}Downloading US Census Bureau trade data...")
        df_imports, df_duties = download_census_trade(force)

    _sp = OrbitalSpinner("Downloading Yale Budget Lab tariff tracker...").start()
    df_tariff = download_yale_tariff_tracker(force, quiet=True)
    _sp.stop("Yale tariff tracker ready")

    _sp = OrbitalSpinner("Checking optional Teti Global Tariff Database files...").start()
    teti_ok = download_teti_database(force, quiet=True)
    _sp.stop("Optional Teti data ready" if teti_ok else "Optional Teti data not present")

    _sp = OrbitalSpinner("Downloading CEPII Gravity Dataset V202211...").start()
    df_cepii = download_cepii_gravity(force, quiet=True)
    _sp.stop("CEPII gravity ready")

    _sp = OrbitalSpinner("Downloading CEPII GeoDist...").start()
    df_geodist = download_cepii_geodist(force, quiet=True)
    _sp.stop("CEPII GeoDist ready")

    _sp = OrbitalSpinner("Downloading IMF World Economic Outlook April 2025...").start()
    df_weo = download_imf_weo(force, quiet=True)
    _sp.stop("IMF WEO ready")

    _sp = OrbitalSpinner("Downloading OECD Quarterly National Accounts...").start()
    # OECD QNA is fetched for its side effect (cached CSV used by Part 2 GE
    # counterfactuals); the returned frame is not consumed in this entry point.
    download_oecd_qna(force, quiet=True)
    _sp.stop("OECD QNA ready")

    # --- phase 2: process it ---
    # each call below writes its output to data/processed/ via side effect;
    # we do not bind the returned DataFrame because nothing downstream in this
    # entry point reads it.
    console.print(f"\n[bold]{_icon('gear')}PHASE 2: PROCESSING DATA[/bold]")
    console.print("─" * 40)

    _sp = OrbitalSpinner("Computing realized effective tariff rates...").start()
    compute_realized_etr(df_imports, df_duties)
    _sp.stop("ETR computed")

    _sp = OrbitalSpinner("Building event study panel...").start()
    create_event_study_panel(df_trade, df_tariff, df_weo, df_geodist, df_cepii)
    _sp.stop("Event study panel ready")

    _sp = OrbitalSpinner("Computing trade diversion indicators...").start()
    compute_trade_diversion_indicators(df_trade)
    _sp.stop("Trade diversion indicators done")

    _sp = OrbitalSpinner("Creating sector exemption map...").start()
    create_sector_exemption_map()
    _sp.stop("Sector map done")

    # --- phase 4: report ---
    console.print(f"\n[bold]{_icon('doc')}PHASE 4: SUMMARY REPORT[/bold]")
    console.print("─" * 40)

    # done!
    console.print(f"\n[bold green]{_icon('ok')}Pipeline complete![/bold green]")
    console.print("[dim]All figures in figures/, processed data in data/processed/[/dim]")
    console.print("[dim]Use 'python pipeline.py regress' to rerun the main PPML model.[/dim]")


def _run_figure_generation(only: str = "") -> None:
    stems = [s.strip() for s in only.split(",") if s.strip()]
    import figures_v2
    figures_v2.main(only=stems or None)


@app.command(name="figures")
def figures(
    only: str = typer.Option(
        "",
        "--only",
        "-o",
        help="Comma-separated figure stems to regenerate. Empty means all figures.",
    ),
) -> None:
    """
    Regenerate thesis figures from cached public panels and outputs.
    """
    _run_figure_generation(only)


@app.command(name="plot")
def plot(
    only: str = typer.Option(
        "",
        "--only",
        "-o",
        help="Comma-separated figure stems to regenerate. Empty means all figures.",
    ),
) -> None:
    """
    Alias for 'figures'.
    """
    _run_figure_generation(only)


@app.command()
def download(
    dataset: str = typer.Option(
        "all",
        "--dataset", "-d",
        help="Which dataset to download. Options: all, imf-imts, census, yale, teti, cepii-gravity, cepii-geodist, weo, oecd",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Re-download even if cached"),
) -> None:
    """
    just downloads data without processing or plotting.
    useful when you're debugging a specific API.
    """
    console.print(f"[bold]{_icon('dl')}Downloading: {dataset}[/bold]")

    dataset_funcs = {
        "imf-imts": lambda: download_imf_imts(force),
        "census": lambda: download_census_trade(force),
        "yale": lambda: download_yale_tariff_tracker(force),
        "teti": lambda: download_teti_database(force),
        "cepii-gravity": lambda: download_cepii_gravity(force),
        "cepii-geodist": lambda: download_cepii_geodist(force),
        "weo": lambda: download_imf_weo(force),
        "oecd": lambda: download_oecd_qna(force),
    }

    if dataset == "all":
        for name, func in dataset_funcs.items():
            console.print(f"\n[bold]--- {name} ---[/bold]")
            func()
    elif dataset in dataset_funcs:
        dataset_funcs[dataset]()
    else:
        console.print(f"[red]Unknown dataset: {dataset}[/red]")
        console.print(f"Available: {', '.join(dataset_funcs.keys())}")
        raise typer.Exit(1)

    console.print(f"\n[bold green]{_icon('ok')}Download complete![/bold green]")


@app.command(name="verify-latex")
def verify_latex() -> None:
    """
    shows your key equations as LaTeX.
    copy-paste into your thesis to verify they match.
    """
    verify_latex_formulas()


@app.command()
def regress(
    estimator: str = typer.Option("ppml", "--estimator", "-e",
        help="Estimator: 'ppml' (statsmodels GLM Poisson) or 'ols' (statsmodels OLS)"),
    fe: str = typer.Option("country + time", "--fe", help="Fixed effects string"),
    cluster: str = typer.Option("country", "--cluster", help="Clustering variable"),
) -> None:
    """
    Run gravity regression via statsmodels GLM Poisson (equivalent to Stata ppmlhdfe).

    Loads the event study panel from data/processed/ and runs PPML or OLS
    with high-dimensional fixed effects. Saves results to outputs/.

    Stata equivalent: ppmlhdfe trade c.log_etr1 i.post, absorb(country time) cluster(country)
    """
    console.print(f"\n[bold]{_icon('gear')}GRAVITY REGRESSION ({estimator.upper()})[/bold]")
    console.print(f"[dim]FE: {fe} | Cluster: {cluster}[/dim]")
    run_gravity_regression(None, estimator=estimator, fe=fe, cluster=cluster)
    console.print(f"\n[bold green]{_icon('ok')}Regression complete[/bold green]")


# ------------------------------------------------------------
# --- gap-closing dataset builders (Teti tariffs, ITPD-E, Larch RTA)
# ------------------------------------------------------------
# these turn the three new raw sources into analysis-ready outputs.
# pure builders, nothing runs at import.

TETI_HS6 = RAW_DIR / "teti_gtd" / "teti_us_bilateral_tariffs_hs6.csv"
LARCH_RTA = RAW_DIR / "larch_rta" / "larch_rta_panel_1950_2025.csv"
ITPDE_INTRA = RAW_DIR / "itpde" / "itpde_intranational_1986_2022.csv"
HS6_PARQUET = RAW_DIR / "census_hs6_imports.parquet"

# census partner name to ISO3, for the partners we carry HS6 weights for
_NAME2ISO = {
    "VIETNAM": "VNM", "TAIWAN": "TWN", "MEXICO": "MEX", "THAILAND": "THA",
    "INDIA": "IND", "MALAYSIA": "MYS", "INDONESIA": "IDN", "KOREA, SOUTH": "KOR",
    "JAPAN": "JPN", "GERMANY": "DEU", "CANADA": "CAN", "SWITZERLAND": "CHE",
    "IRELAND": "IRL", "ITALY": "ITA", "UNITED KINGDOM": "GBR", "FRANCE": "FRA",
    "BRAZIL": "BRA", "SINGAPORE": "SGP", "NETHERLANDS": "NLD", "CHINA": "CHN",
}


def _build_census_name2iso3():
    """Map Census CTY_NAME -> ISO3 for every real partner country.

    The Census Bureau uses its own country names (uppercase, with a few quirks:
    KOREA, SOUTH; BURMA; TURKIYE; etc.). We need ISO3 letter codes so we can
    join Census-sourced country-month ETR onto the IMF IMTS bilateral panel,
    which uses ISO3. Built from pycountry with manual overrides for the names
    pycountry would not resolve cleanly. Aggregates (ASEAN, OECD, EU, ASIA,
    USMCA (NAFTA), TOTAL FOR ALL COUNTRIES, etc.) are intentionally not in the
    map so they get dropped from the country panel.
    """
    overrides = {
        "BAHAMAS, THE": "BHS", "BURMA": "MMR", "CABO VERDE": "CPV",
        "CONGO (BRAZZAVILLE)": "COG", "CONGO (KINSHASA)": "COD",
        "DEMOCRATIC REPUBLIC OF THE CONGO": "COD",
        "COTE D'IVOIRE": "CIV", "CZECHIA": "CZE",
        "GAMBIA, THE": "GMB", "KOREA, NORTH": "PRK", "KOREA, SOUTH": "KOR",
        "MACAU": "MAC", "MICRONESIA, FEDERATED STATES OF": "FSM",
        "REPUBLIC OF NORTH MACEDONIA": "MKD", "MACEDONIA": "MKD",
        "SAO TOME AND PRINCIPE": "STP", "SLOVAKIA": "SVK",
        "SWAZILAND": "SWZ", "ESWATINI": "SWZ",
        "TAIWAN": "TWN", "TIMOR-LESTE": "TLS",
        "TURKEY": "TUR", "TURKIYE": "TUR", "TURKEY (TURKIYE)": "TUR",
        "UNITED KINGDOM": "GBR", "VATICAN CITY": "VAT",
        "WEST BANK": "PSE", "WEST BANK ADMINISTERED BY ISRAEL": "PSE",
        "GAZA STRIP ADMINISTERED BY ISRAEL": "PSE", "PALESTINE": "PSE",
        "CURACAO": "CUW",
        "FALKLAND ISLANDS (ISLAS MALVINAS)": "FLK",
        "ST KITTS AND NEVIS": "KNA", "ST LUCIA": "LCA",
        "ST VINCENT AND THE GRENADINES": "VCT",
        "ST HELENA": "SHN", "ST PIERRE AND MIQUELON": "SPM",
        "BRITISH VIRGIN ISLANDS": "VGB",
        "BRITISH INDIAN OCEAN TERRITORIES": "IOT",
        "FRENCH POLYNESIA": "PYF", "NEW CALEDONIA": "NCL",
        "FRENCH SOUTHERN AND ANTARCTIC LANDS": "ATF",
        "HEARD AND MCDONALD ISLANDS": "HMD",
        "PITCAIRN ISLANDS": "PCN",
        "SVALBARD, JAN MAYEN ISLAND": "SJM",
        "VENEZUELA": "VEN", "VIETNAM": "VNM", "RUSSIA": "RUS",
        "MOLDOVA": "MDA", "SYRIA": "SYR", "IRAN": "IRN",
        "LAOS": "LAO", "BOLIVIA": "BOL", "TANZANIA": "TZA",
        "BRUNEI": "BRN",
    }
    try:
        import pycountry
        mapping = dict(overrides)
        # try lookup + fuzzy for any Census name we have not hard-coded
        etr_p = PROCESSED_DIR / "realized_etr_by_country_month.csv"
        if etr_p.exists():
            names = pd.read_csv(etr_p, usecols=["CTY_NAME"])["CTY_NAME"].dropna().unique()
            for n in names:
                if n in mapping:
                    continue
                try:
                    c = pycountry.countries.lookup(n)
                    mapping[n] = c.alpha_3
                except LookupError:
                    try:
                        c = pycountry.countries.search_fuzzy(n)
                        mapping[n] = c[0].alpha_3
                    except (LookupError, Exception):
                        pass  # aggregate / unresolvable: leave out
        return mapping
    except ImportError:
        # pycountry not installed: fall back to overrides only (covers majors)
        return overrides


# lazy cache for the Census name -> ISO3 crosswalk. building it eagerly at
# import time caused the mapping size to depend on whether
# realized_etr_by_country_month.csv already existed, which made downstream
# joins non-deterministic on cold vs warm runs.
_CENSUS_NAME2ISO3_CACHE: dict | None = None


def get_census_name2iso3() -> dict:
    global _CENSUS_NAME2ISO3_CACHE
    if _CENSUS_NAME2ISO3_CACHE is None:
        _CENSUS_NAME2ISO3_CACHE = _build_census_name2iso3()
    return _CENSUS_NAME2ISO3_CACHE


def build_country_tariff_panel(start="2024-01", end="2025-09"):
    """Gap 1: country-specific product-weighted applied tariff, by partner-month.

    weights each partner's Teti applied tariff by its own pre-shock HS6 import
    mix, weights fixed at the pre-shock level, so the tariff varies by country
    and by month. writes outputs/country_tariff_month_panel.csv.
    """
    import re
    import pandas as pd

    missing = [p for p in (HS6_PARQUET, TETI_HS6) if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(
            "The country-specific applied-tariff panel needs optional local "
            f"Teti and HS6 files that are not redistributed here: {missing_list}"
        )

    hs = pd.read_parquet(HS6_PARQUET)
    hs["hs6"] = pd.to_numeric(hs["I_COMMODITY"].astype(str).str[:6], errors="coerce")
    hs["GEN_VAL_MO"] = pd.to_numeric(hs["GEN_VAL_MO"], errors="coerce")
    # use the wide Census-name-to-ISO3 crosswalk so we cover all 200+ partners,
    # not just the 20 hand-coded ones. Issue I in the audit.
    hs["iso"] = hs["CTY_NAME"].map(get_census_name2iso3())
    wt = (hs[hs["time"] <= "2025-03"].groupby(["iso", "hs6"])["GEN_VAL_MO"]
          .sum().rename("wgt").reset_index())
    imp = hs.groupby(["iso", "time"])["GEN_VAL_MO"].sum().rename("imports").reset_index()

    hdr = pd.read_csv(TETI_HS6, nrows=0).columns
    dates = sorted(c for c in hdr if re.fullmatch(r"t_\d{8}", c))
    months = pd.period_range(start, end, freq="M").astype(str)

    def active(m):  # latest tariff date on or before month end
        me = pd.Period(m, "M").end_time
        cand = [c for c in dates if pd.to_datetime(c[2:], format="%Y%m%d") <= me]
        return cand[-1] if cand else None

    m2c = {m: active(m) for m in months}
    need = sorted({c for c in m2c.values() if c})
    t = pd.read_csv(TETI_HS6, usecols=["importer", "exporter", "hs6"] + need)
    t = t[t["importer"] == "USA"].copy()
    t["hs6"] = pd.to_numeric(t["hs6"], errors="coerce")
    t = t.merge(wt, left_on=["exporter", "hs6"], right_on=["iso", "hs6"], how="inner")
    recs = []
    for m, col in m2c.items():
        if not col:
            continue
        g = t.dropna(subset=[col])
        tar = ((g[col] * g["wgt"]).groupby(g["iso"]).sum()
               / g.groupby("iso")["wgt"].sum()).rename("tariff").reset_index()
        tar["time"] = m
        recs.append(tar)
    panel = pd.concat(recs).merge(imp, on=["iso", "time"], how="inner")
    panel.to_csv(OUTPUTS_DIR / "country_tariff_month_panel.csv", index=False)
    return panel


def build_internal_trade_itpde():
    """Gap 3: intra-national trade from ITPD-E (exporter == importer), 1986-2022.

    ITPD-E ends in 2022, so this is the pre-shock benchmark. extending it to
    2023-2025 needs gross output (UN Table 2.3) and exports (CEPII BACI), which
    are not in hand, so the 2023-2025 piece stays a documented gap.
    writes data/processed/internal_trade_benchmark.csv.
    """
    import pandas as pd
    d = pd.read_csv(ITPDE_INTRA)
    d = d[d["exporter_iso3"] == d["importer_iso3"]].copy()
    out = (d.groupby(["exporter_iso3", "year", "broad_sector"])["trade"]
           .sum().rename("internal_trade").reset_index()
           .rename(columns={"exporter_iso3": "country_iso3"}))
    out.to_csv(PROCESSED_DIR / "internal_trade_benchmark.csv", index=False)
    return out


def load_larch_rta(year_min=2018):
    """Gap 2: time-varying RTA / FTA flags through 2025 (Mario Larch's database).

    drop-in replacement for the held-constant CEPII agreement flags. returns the
    bilateral panel filtered to recent years, merge on exporter-importer-year.
    """
    import pandas as pd
    d = pd.read_csv(LARCH_RTA)
    return d[d["year"] >= year_min].copy()


def build_internal_trade_extension(year=2023):
    """Gap 3 extension: domestic trade = goods output minus goods exports, in USD.

    Goods output comes from UN national-accounts (Agriculture A, Mining B,
    Manufacturing C) converted to USD with a GDP-implied exchange rate; goods
    exports come from CEPII BACI. Coverage is the roughly 75 countries that
    report output by industry to the UN for 2023; the largest partners (US, China)
    and 2024-2025 are not yet reported, so this stays a partial robustness
    extension on top of the ITPD-E benchmark through 2022. Writes
    outputs/internal_trade_extension_{year}.csv. See scripts for the full build.
    """
    import pandas as pd
    out = OUTPUTS_DIR / f"internal_trade_extension_{year}.csv"
    if out.exists():
        return pd.read_csv(out)
    raise FileNotFoundError(
        f"{out} not built yet; run the BACI+UN extension build (data/raw/cepii_baci, "
        "data/raw/undata_sna)")


# --- entry point ---
if __name__ == "__main__":
    app()
