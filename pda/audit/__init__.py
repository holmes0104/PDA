"""Stage 4 — scoring, gap analysis, and critic verification."""

from pda.audit.scorecard import build_scorecard
from pda.audit.gap_analysis import run_gap_analysis
from pda.audit.critic import run_critic_pass

__all__ = ["build_scorecard", "run_gap_analysis", "run_critic_pass"]
