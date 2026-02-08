"""CLI entry-point: full audit pipeline."""

import json
from pathlib import Path

import typer
from rich.console import Console

from pda.audit import run_critic_pass, run_gap_analysis
from pda.ingest.pdf_parser import PDFParseError
from pda.audit.scorecard import build_scorecard
from pda.config import get_settings
from pda.content_pack.generator import generate_content_pack
from pda.content_pack.content_pack_from_factsheet import (
    load_factsheet as load_factsheet_strict,
    load_audit,
    generate_content_pack_from_factsheet,
)
from pda.extract.fact_extractor import extract_fact_sheet
from pda.extract.factsheet_extractor import extract_product_fact_sheet
from pda.ingest.chunker import chunk_document
from pda.ingest.ingest_pipeline import run_ingestion
from pda.ingest.pdf_parser import parse_pdf
from pda.llm import get_provider
from pda.report.html import render_html_report, write_html_report
from pda.report.markdown import render_markdown_report, write_markdown_report
from pda.schemas.models import ChunkSource
from pda.simulate.buyer_simulator import (
    build_diff_report,
    generate_prompt_set,
    load_factsheet as load_factsheet_sim,
    load_variant_content,
    run_simulator,
    write_simulator_result,
)
from pda.simulate.prompt_sim import run_prompt_simulation, run_prompt_simulation_two_variants
from pda.store.vectorstore import VectorStore
from pda.verifier import (
    VerifierResult,
    run_verifier_audit_pipeline,
    run_verifier_content_pack,
    run_verifier_factsheet,
    write_verifier_report,
)

app = typer.Typer(help="LLM Product Discoverability Auditor")


@app.command()
def audit(
    pdf_path: str = typer.Argument(..., help="Path to PDF technical brochure"),
    url: list[str] = typer.Option(default=[], help="Optional product page URL(s)"),
    provider: str = typer.Option(None, help="LLM provider: openai | anthropic (default from env)"),
    output: str = typer.Option(None, help="Output directory (default from PDA_OUTPUT_DIR or ./output)"),
    format: str = typer.Option("md,html", help="Report format: md, html, or md,html"),
    allow_unsafe: bool = typer.Option(False, "--allow-unsafe", help="Proceed even if verifier reports blocked issues"),
):
    """Run the full audit pipeline: extract facts, scorecard, gap analysis, content pack, prompt sim."""
    console = Console()
    settings = get_settings()
    out_dir = Path(output) if output else settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    provider_name = (provider or settings.pda_llm_provider).lower()
    formats = [f.strip().lower() for f in format.split(",") if f.strip()]

    try:
        console.print("Parsing PDF...")
        pages = parse_pdf(pdf_path)
    except (PDFParseError, FileNotFoundError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    pdf_name = Path(pdf_path).name
    chunks = chunk_document(pages, source_file=pdf_name, source_type=ChunkSource.PDF)

    url_chunks_list: list[list] = []  # per-URL chunk lists for two-variant sim
    url_chunks: list = []
    if url:
        try:
            from pda.ingest.url_scraper import scrape_url
            for u in url:
                text = scrape_url(u)
                uc = chunk_document(
                    [(0, text)],
                    source_file=u,
                    source_type=ChunkSource.URL,
                )
                url_chunks_list.append(uc)
                url_chunks.extend(uc)
        except Exception as e:
            console.print(f"[yellow]Warning: URL scraping skipped ({e})[/yellow]")
        chunks = chunks + url_chunks

    console.print("Extracting product facts...")
    llm = get_provider(
        provider_name,
        api_key=settings.openai_api_key if provider_name == "openai" else settings.anthropic_api_key,
        model=settings.pda_openai_model if provider_name == "openai" else settings.pda_anthropic_model,
    )
    fact_sheet = extract_fact_sheet(chunks, llm)

    console.print("Building scorecard...")
    prompt_results: list = []
    if len(url) >= 2 and len(url_chunks_list) >= 2:
        chunks_a = chunks[: len(chunks) - len(url_chunks)] + url_chunks_list[0]
        chunks_b = chunks[: len(chunks) - len(url_chunks)] + url_chunks_list[1]
        res_a, res_b = run_prompt_simulation_two_variants(
            chunks_a,
            chunks_b,
            llm,
            label_a="variant_1",
            label_b="variant_2",
        )
        prompt_results = [res_a, res_b]
        buyer_score = (res_a.average_grounding + res_b.average_grounding) / 2
    else:
        pr = run_prompt_simulation(chunks, llm, source_description=pdf_name)
        prompt_results = [pr]
        buyer_score = pr.average_grounding
    scorecard = build_scorecard(
        fact_sheet,
        chunks,
        url_chunks=url_chunks if url_chunks else None,
        buyer_answerability_score=buyer_score,
    )

    console.print("Gap analysis and critic pass...")
    findings = run_gap_analysis(fact_sheet, scorecard)
    scorecard.findings = findings
    findings = run_critic_pass(findings, chunks, llm)

    content_pack = generate_content_pack(fact_sheet)

    console.print("Running verifier pass...")
    verifier_result = run_verifier_audit_pipeline(
        fact_sheet,
        findings=findings,
        content_pack=content_pack,
        prompt_results=prompt_results,
        chunks=chunks,
    )
    verifier_path = out_dir / "verifier_report.md"
    write_verifier_report(verifier_result, verifier_path)
    console.print(f"Wrote {verifier_path}")
    if verifier_result.has_blocked and not allow_unsafe:
        console.print("[red]Verifier found blocked issues. Fix them or use --allow-unsafe to proceed.[/red]")
        raise typer.Exit(1)

    console.print("Writing report...")
    md_content = render_markdown_report(
        fact_sheet=fact_sheet,
        scorecard=scorecard,
        findings=findings,
        content_pack=content_pack,
        prompt_results=prompt_results,
        pdf_path=pdf_path,
        url_list=url if url else None,
    )
    if "md" in formats:
        write_markdown_report(out_dir / "report.md", md_content)
        console.print(f"Wrote {out_dir / 'report.md'}")
    if "html" in formats:
        html_content = render_html_report(
            fact_sheet=fact_sheet,
            scorecard=scorecard,
            findings=findings,
            content_pack=content_pack,
            prompt_results=prompt_results,
            pdf_path=pdf_path,
            url_list=url if url else None,
        )
        write_html_report(out_dir / "report.html", html_content)
        console.print(f"Wrote {out_dir / 'report.html'}")
    with open(out_dir / "audit.json", "w", encoding="utf-8") as f:
        json.dump(
            {"scorecard": scorecard.model_dump(), "findings": [x.model_dump() for x in findings]},
            f,
            indent=2,
        )
    console.print(f"Wrote {out_dir / 'audit.json'}")
    console.print("[green]Done.[/green]")


@app.command()
def factsheet(
    project: str = typer.Option(..., "--project", help="Project directory (PDFs to ingest and query)"),
    out: str = typer.Option("factsheet.json", "--out", help="Output JSON path (provenance written alongside as factsheet_provenance.json)"),
    provider: str = typer.Option(None, help="LLM provider: openai | anthropic (default from env)"),
    allow_unsafe: bool = typer.Option(False, "--allow-unsafe", help="Proceed even if verifier reports blocked issues"),
):
    """Extract Product Fact Sheet via targeted retrieval and LLM; write factsheet.json and factsheet_provenance.json."""
    console = Console()
    settings = get_settings()
    project_dir = Path(project)
    if not project_dir.is_dir():
        console.print(f"[red]Error: project is not a directory: {project_dir}[/red]")
        raise typer.Exit(1)

    # Ingest PDFs from project dir
    pdf_paths = list(project_dir.glob("**/*.pdf"))
    if not pdf_paths:
        console.print(f"[yellow]Warning: no PDFs in {project_dir}[/yellow]")
    chunks: list = []
    for pdf_path in pdf_paths:
        try:
            pages = parse_pdf(str(pdf_path))
            chunks.extend(
                chunk_document(pages, source_file=pdf_path.name, source_type=ChunkSource.PDF)
            )
        except (PDFParseError, FileNotFoundError) as e:
            console.print(f"[yellow]Skipping {pdf_path}: {e}[/yellow]")
    if not chunks:
        console.print("[red]Error: no chunks from project (add PDFs or check paths).[/red]")
        raise typer.Exit(1)

    # Vector store under project
    persist_dir = project_dir / "chroma_data"
    persist_dir.mkdir(parents=True, exist_ok=True)
    store = VectorStore(
        collection_name="pda_factsheet",
        persist_directory=str(persist_dir),
        embedding_model=settings.pda_embedding_model,
        openai_api_key=settings.openai_api_key,
    )
    console.print("Indexing chunks...")
    store.add_chunks(chunks)

    provider_name = (provider or settings.pda_llm_provider).lower()
    llm = get_provider(
        provider_name,
        api_key=settings.openai_api_key if provider_name == "openai" else settings.anthropic_api_key,
        model=settings.pda_openai_model if provider_name == "openai" else settings.pda_anthropic_model,
    )
    console.print("Extracting fact sheet (retrieval + LLM)...")
    sheet, provenance = extract_product_fact_sheet(store, llm)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sheet.model_dump(), f, indent=2)
    console.print(f"Wrote {out_path}")

    prov_path = out_path.parent / "factsheet_provenance.json"
    with open(prov_path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
    console.print(f"Wrote {prov_path}")

    console.print("Running verifier pass...")
    verifier_result = run_verifier_factsheet(sheet, provenance)
    verifier_path = out_path.parent / "verifier_report.md"
    write_verifier_report(verifier_result, verifier_path)
    console.print(f"Wrote {verifier_path}")
    if verifier_result.has_blocked and not allow_unsafe:
        console.print("[red]Verifier found blocked issues. Fix them or use --allow-unsafe to proceed.[/red]")
        raise typer.Exit(1)
    console.print("[green]Done.[/green]")


@app.command("content-pack")
def content_pack(
    project: str = typer.Option(..., "--project", help="Project directory (for context)"),
    factsheet_path: str = typer.Option(..., "--factsheet", help="Path to factsheet.json (strict schema)"),
    audit_path: str = typer.Option(..., "--audit", help="Path to audit.json (scorecard + findings)"),
    out: str = typer.Option(None, "--out", help="Output directory (default: <project>/outputs/)"),
    allow_unsafe: bool = typer.Option(False, "--allow-unsafe", help="Proceed even if verifier reports blocked issues"),
):
    """Generate content pack from factsheet + audit: product_page_outline.md, faq.md, comparison.md, jsonld_product_skeleton.json."""
    console = Console()
    project_dir = Path(project)
    if not project_dir.is_dir():
        console.print(f"[red]Error: project is not a directory: {project_dir}[/red]")
        raise typer.Exit(1)
    out_dir = Path(out) if out else project_dir / "outputs"
    factsheet_file = Path(factsheet_path)
    audit_file = Path(audit_path)
    if not factsheet_file.exists():
        console.print(f"[red]Error: factsheet not found: {factsheet_file}[/red]")
        raise typer.Exit(1)
    if not audit_file.exists():
        console.print(f"[red]Error: audit file not found: {audit_file}[/red]")
        raise typer.Exit(1)
    try:
        sheet = load_factsheet_strict(factsheet_file)
        scorecard, findings = load_audit(audit_file)
    except Exception as e:
        console.print(f"[red]Error loading factsheet or audit: {e}[/red]")
        raise typer.Exit(1)
    console.print("Generating content pack...")
    written = generate_content_pack_from_factsheet(sheet, scorecard, findings, out_dir)
    for name, path in written.items():
        console.print(f"Wrote {path}")

    console.print("Running verifier pass...")
    provenance_path = factsheet_file.parent / "factsheet_provenance.json"
    provenance = {}
    if provenance_path.exists():
        with open(provenance_path, encoding="utf-8") as f:
            provenance = json.load(f)
    verifier_result = run_verifier_content_pack(sheet, findings, provenance)
    verifier_path = out_dir / "verifier_report.md"
    write_verifier_report(verifier_result, verifier_path)
    console.print(f"Wrote {verifier_path}")
    if verifier_result.has_blocked and not allow_unsafe:
        console.print("[red]Verifier found blocked issues. Fix them or use --allow-unsafe to proceed.[/red]")
        raise typer.Exit(1)
    console.print("[green]Done.[/green]")


@app.command()
def simulate(
    project: str = typer.Option(..., "--project", help="Project directory (used to resolve factsheet path if relative)"),
    factsheet: str = typer.Option(..., "--factsheet", help="Path to factsheet.json (relative to project or absolute)"),
    variant_a: str = typer.Option(..., "--variantA", help="Path to Variant A content (current page/brochure summary; .txt, .md, or .json)"),
    variant_b: str | None = typer.Option(None, "--variantB", help="Optional path to Variant B content (LLM-friendly draft)"),
    out: str = typer.Option(..., "--out", help="Output directory (e.g. <dir>/outputs/) for prompts.json, results, and diff"),
    provider: str = typer.Option(None, help="LLM provider: openai | anthropic (default from env)"),
):
    """Run Buyer-Prompt Simulator: generate 50 prompts, answer from variant-only content, score with factsheet rubric, optional A/B diff."""
    console = Console()
    settings = get_settings()
    project_dir = Path(project)
    if not project_dir.is_dir():
        console.print(f"[red]Error: project is not a directory: {project_dir}[/red]")
        raise typer.Exit(1)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve paths: factsheet relative to project if not absolute
    factsheet_path = Path(factsheet)
    if not factsheet_path.is_absolute():
        factsheet_path = project_dir / factsheet_path
    if not factsheet_path.exists():
        console.print(f"[red]Error: factsheet not found: {factsheet_path}[/red]")
        raise typer.Exit(1)

    variant_a_path = Path(variant_a)
    if not variant_a_path.exists():
        console.print(f"[red]Error: variant A not found: {variant_a_path}[/red]")
        raise typer.Exit(1)
    variant_b_path = Path(variant_b) if variant_b else None
    if variant_b_path is not None and not variant_b_path.exists():
        console.print(f"[red]Error: variant B not found: {variant_b_path}[/red]")
        raise typer.Exit(1)

    provider_name = (provider or settings.pda_llm_provider).lower()
    llm = get_provider(
        provider_name,
        api_key=settings.openai_api_key if provider_name == "openai" else settings.anthropic_api_key,
        model=settings.pda_openai_model if provider_name == "openai" else settings.pda_anthropic_model,
    )

    console.print("Loading factsheet...")
    sheet = load_factsheet_sim(factsheet_path)
    console.print("Loading variant A content...")
    content_a = load_variant_content(variant_a_path)

    console.print("Generating prompt set (50 prompts)...")
    prompts = generate_prompt_set(out_dir / "prompts.json")
    console.print(f"Wrote {out_dir / 'prompts.json'}")

    console.print("Running simulator for Variant A...")
    result_a = run_simulator(content_a, "variant_A", prompts, sheet, llm)
    write_simulator_result(result_a, out_dir / "simulator_results_A.json")
    console.print(f"Wrote {out_dir / 'simulator_results_A.json'}")

    if variant_b_path is not None:
        console.print("Loading variant B content...")
        content_b = load_variant_content(variant_b_path)
        console.print("Running simulator for Variant B...")
        result_b = run_simulator(content_b, "variant_B", prompts, sheet, llm)
        write_simulator_result(result_b, out_dir / "simulator_results_B.json")
        console.print(f"Wrote {out_dir / 'simulator_results_B.json'}")
        console.print("Building diff report...")
        build_diff_report(result_a, result_b, out_dir / "simulator_diff.md")
        console.print(f"Wrote {out_dir / 'simulator_diff.md'}")

    console.print("[green]Done.[/green]")


@app.command()
def verify(
    project: str = typer.Option(..., "--project", help="Project directory (for resolving paths)"),
    factsheet: str = typer.Option(..., "--factsheet", help="Path to factsheet.json"),
    audit: str = typer.Option(..., "--audit", help="Path to audit.json"),
    out: str = typer.Option(..., "--out", help="Output directory for verifier_report.md"),
):
    """Run verifier on factsheet + audit and write verifier_report.md (standalone step)."""
    from pda.content_pack.content_pack_from_factsheet import load_factsheet as load_factsheet_strict

    console = Console()
    project_dir = Path(project)
    if not project_dir.is_dir():
        console.print(f"[red]Error: project is not a directory: {project_dir}[/red]")
        raise typer.Exit(1)
    factsheet_path = Path(factsheet)
    if not factsheet_path.is_absolute():
        factsheet_path = project_dir / factsheet_path
    audit_path = Path(audit)
    if not audit_path.is_absolute():
        audit_path = project_dir / audit_path
    if not factsheet_path.exists():
        console.print(f"[red]Error: factsheet not found: {factsheet_path}[/red]")
        raise typer.Exit(1)
    if not audit_path.exists():
        console.print(f"[red]Error: audit file not found: {audit_path}[/red]")
        raise typer.Exit(1)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet = load_factsheet_strict(factsheet_path)
    scorecard, findings = load_audit(audit_path)
    provenance_path = factsheet_path.parent / "factsheet_provenance.json"
    provenance: dict = {}
    if provenance_path.exists():
        with open(provenance_path, encoding="utf-8") as f:
            provenance = json.load(f)

    console.print("Running verifier (factsheet + content-pack checks)...")
    r1 = run_verifier_factsheet(sheet, provenance)
    r2 = run_verifier_content_pack(sheet, findings, provenance)
    merged = VerifierResult(
        blocked_issues=r1.blocked_issues + r2.blocked_issues,
        warnings=r1.warnings + r2.warnings,
        suggested_queries=list(dict.fromkeys(r1.suggested_queries + r2.suggested_queries)),
    )
    verifier_path = out_dir / "verifier_report.md"
    write_verifier_report(merged, verifier_path)
    console.print(f"Wrote {verifier_path}")
    if merged.has_blocked:
        console.print("[yellow]Verifier reported blocked issues. Review the report.[/yellow]")
    console.print("[green]Done.[/green]")


@app.command()
def ingest(
    pdf: str = typer.Option(..., "--pdf", help="Path to PDF"),
    url: str | None = typer.Option(None, "--url", help="Optional product page URL"),
    out: str = typer.Option(..., "--out", help="Output project directory"),
):
    """Extract text from PDF (and optionally URL), chunk, save chunks.jsonl and raw_extraction/."""
    console = Console()
    try:
        chunks = run_ingestion(pdf_path=pdf, url=url, out_dir=Path(out))
        console.print(f"Wrote {Path(out) / 'chunks.jsonl'} ({len(chunks)} chunks)")
        console.print(f"Raw extraction: {Path(out) / 'raw_extraction'}")
        console.print("[green]Done.[/green]")
    except (PDFParseError, FileNotFoundError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
