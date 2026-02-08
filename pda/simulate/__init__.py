"""Stage 5 — buyer-prompt simulator."""

from pda.simulate.buyer_simulator import (
    build_diff_report,
    generate_prompt_set,
    load_factsheet,
    load_variant_content,
    run_simulator,
    write_simulator_result,
)
from pda.simulate.prompt_sim import run_prompt_simulation, run_prompt_simulation_two_variants

__all__ = [
    "run_prompt_simulation",
    "run_prompt_simulation_two_variants",
    "generate_prompt_set",
    "load_factsheet",
    "load_variant_content",
    "run_simulator",
    "build_diff_report",
    "write_simulator_result",
]
