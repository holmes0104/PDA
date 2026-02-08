"""Simulate API routes."""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from pda.config import get_settings
from pda.llm import get_provider
from pda.simulate.buyer_simulator import (
    build_diff_report,
    generate_prompt_set,
    load_factsheet,
    load_variant_content,
    run_simulator,
    write_simulator_result,
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class SimulateRequest(BaseModel):
    project_id: str
    factsheet_path: str
    variant_a_path: str
    variant_b_path: Optional[str] = None


class SimulateResponse(BaseModel):
    project_id: str
    prompts_path: str
    results_a_path: str
    results_b_path: Optional[str] = None
    diff_path: Optional[str] = None


@router.post("/simulate", response_model=SimulateResponse, status_code=status.HTTP_201_CREATED)
async def run_simulation(request: SimulateRequest):
    """Run buyer-prompt simulator."""
    project_dir = settings.data_dir / "projects" / request.project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    # Resolve paths relative to project
    factsheet_path = project_dir / request.factsheet_path if not Path(request.factsheet_path).is_absolute() else Path(request.factsheet_path)
    variant_a_path = project_dir / request.variant_a_path if not Path(request.variant_a_path).is_absolute() else Path(request.variant_a_path)
    variant_b_path = None
    if request.variant_b_path:
        variant_b_path = project_dir / request.variant_b_path if not Path(request.variant_b_path).is_absolute() else Path(request.variant_b_path)

    if not factsheet_path.exists():
        raise HTTPException(status_code=404, detail=f"Factsheet not found: {factsheet_path}")
    if not variant_a_path.exists():
        raise HTTPException(status_code=404, detail=f"Variant A not found: {variant_a_path}")
    if variant_b_path and not variant_b_path.exists():
        raise HTTPException(status_code=404, detail=f"Variant B not found: {variant_b_path}")

    output_dir = project_dir / "outputs"
    output_dir.mkdir(exist_ok=True)

    provider_name = settings.pda_llm_provider.lower()
    llm = get_provider(
        provider_name,
        api_key=settings.openai_api_key if provider_name == "openai" else settings.anthropic_api_key,
        model=settings.pda_openai_model if provider_name == "openai" else settings.pda_anthropic_model,
    )

    sheet = load_factsheet(factsheet_path)
    content_a = load_variant_content(variant_a_path)

    prompts = generate_prompt_set(output_dir / "prompts.json")
    result_a = run_simulator(content_a, "variant_A", prompts, sheet, llm)
    write_simulator_result(result_a, output_dir / "simulator_results_A.json")

    results_b_path = None
    diff_path = None
    if variant_b_path:
        content_b = load_variant_content(variant_b_path)
        result_b = run_simulator(content_b, "variant_B", prompts, sheet, llm)
        results_b_path = str(output_dir / "simulator_results_B.json")
        write_simulator_result(result_b, output_dir / "simulator_results_B.json")
        build_diff_report(result_a, result_b, output_dir / "simulator_diff.md")
        diff_path = str(output_dir / "simulator_diff.md")

    return SimulateResponse(
        project_id=request.project_id,
        prompts_path=str(output_dir / "prompts.json"),
        results_a_path=str(output_dir / "simulator_results_A.json"),
        results_b_path=results_b_path,
        diff_path=diff_path,
    )
