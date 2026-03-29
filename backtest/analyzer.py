from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


class FactorAnalyzer:
    """Wrapper around alphalens for IC / quantile-return analysis.

    Args:
        output_dir: Directory where plots and CSV reports are saved.
        long_short:  If True, computes long-short portfolio returns.
        show_plots:  If True, renders plots interactively (requires a display).
    """

    def __init__(
        self,
        output_dir: str = "reports",
        long_short: bool = True,
        show_plots: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.long_short = long_short
        self.show_plots = show_plots

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_ic_analysis(self, factor_data: pd.DataFrame, factor_name: str = "factor") -> pd.DataFrame:
        """Compute and save IC (Information Coefficient) time series.

        Returns:
            DataFrame with IC per date and forward-return period.
        """
        from alphalens.performance import factor_information_coefficient

        ic = factor_information_coefficient(factor_data)
        ic_path = self.output_dir / f"{factor_name}_ic.csv"
        ic.to_csv(ic_path)
        logger.info(f"IC analysis saved to {ic_path}")

        ic_mean = ic.mean()
        ic_std = ic.std()
        icir = ic_mean / ic_std
        summary = pd.DataFrame({"IC_mean": ic_mean, "IC_std": ic_std, "ICIR": icir})
        summary_path = self.output_dir / f"{factor_name}_icir.csv"
        summary.to_csv(summary_path)
        logger.info(f"ICIR summary:\n{summary.to_string()}")
        return ic

    def run_quantile_returns(
        self, factor_data: pd.DataFrame, factor_name: str = "factor"
    ) -> pd.DataFrame:
        """Compute mean returns by quantile and save.

        Returns:
            DataFrame of mean returns indexed by quantile.
        """
        from alphalens.performance import mean_return_by_quantile

        mean_ret, _ = mean_return_by_quantile(
            factor_data,
            by_date=False,
            demeaned=self.long_short,
        )
        path = self.output_dir / f"{factor_name}_quantile_returns.csv"
        mean_ret.to_csv(path)
        logger.info(f"Quantile returns saved to {path}")
        return mean_ret

    def create_full_report(
        self,
        factor_data: pd.DataFrame,
        factor_name: str = "factor",
    ) -> None:
        """Generate the full alphalens tear sheet as PNG files.

        Saves individual plots to output_dir instead of displaying them.
        """
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend, safe in headless env
        import matplotlib.pyplot as plt

        try:
            import alphalens.tears as tears  # noqa: F401 kept for compat check
            import alphalens.plotting as plotting
        except ImportError as e:
            raise ImportError("alphalens-reloaded is required.") from e

        logger.info(f"FactorAnalyzer: generating full tear sheet for '{factor_name}'")

        from alphalens import performance as perf

        # --- Returns tear sheet ---
        fig, axes = plt.subplots(3, 1, figsize=(14, 18))
        try:
            mean_ret, mean_ret_std = perf.mean_return_by_quantile(
                factor_data, by_date=False, demeaned=self.long_short
            )
            plotting.plot_quantile_returns_bar(mean_ret, by_group=False, ax=axes[0])
        except Exception as exc:
            logger.warning(f"quantile bar: {exc}")
        try:
            mean_ret_by_date, _ = perf.mean_return_by_quantile(
                factor_data, by_date=True, demeaned=self.long_short
            )
            plotting.plot_cumulative_returns_by_quantile(
                mean_ret_by_date, period="1D", ax=axes[1]
            )
        except Exception as exc:
            logger.warning(f"cumulative returns: {exc}")
        try:
            factor_ret = perf.factor_returns(factor_data, demeaned=self.long_short)
            plotting.plot_cumulative_returns(factor_ret, period="1D", ax=axes[2])
        except Exception as exc:
            logger.warning(f"factor returns: {exc}")
        self._save_fig(fig, f"{factor_name}_returns.png")

        # --- IC tear sheet ---
        ic = self.run_ic_analysis(factor_data, factor_name)
        try:
            ax_ts = plotting.plot_ic_ts(ic)
            self._save_fig(ax_ts[0].get_figure(), f"{factor_name}_ic_ts.png")
        except Exception as exc:
            logger.warning(f"IC ts plot: {exc}")
        try:
            ax_hist = plotting.plot_ic_hist(ic)
            self._save_fig(ax_hist[0].get_figure(), f"{factor_name}_ic_hist.png")
        except Exception as exc:
            logger.warning(f"IC hist: {exc}")

        # Quantile returns CSV
        self.run_quantile_returns(factor_data, factor_name)

        logger.info(f"Full report saved to {self.output_dir}/")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_fig(self, fig, filename: str) -> None:
        import matplotlib.pyplot as plt

        path = self.output_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"Saved plot: {path}")
