"""HTML report: wrap Markdown report in styled HTML."""

from pathlib import Path

import markdown

from pda.report.markdown import render_markdown_report


HTML_WRAPPER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>LLM Product Discoverability Audit</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem; line-height: 1.5; }}
h1 {{ border-bottom: 2px solid #333; }}
h2 {{ margin-top: 1.5rem; color: #444; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
th {{ background: #f5f5f5; }}
code {{ background: #f0f0f0; padding: 0.2em 0.4em; border-radius: 3px; }}
pre {{ background: #f8f8f8; padding: 1rem; overflow-x: auto; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_html_report(
    fact_sheet: object,
    scorecard: object,
    findings: list,
    content_pack: dict,
    prompt_results: list | None = None,
    pdf_path: str = "",
    url_list: list[str] | None = None,
) -> str:
    """Render full report as Markdown then convert to HTML and wrap."""
    md = render_markdown_report(
        fact_sheet=fact_sheet,
        scorecard=scorecard,
        findings=findings,
        content_pack=content_pack,
        prompt_results=prompt_results,
        pdf_path=pdf_path,
        url_list=url_list,
    )
    body = markdown.markdown(md, extensions=["tables", "fenced_code"])
    return HTML_WRAPPER.format(body=body)


def write_html_report(output_path: str | Path, content: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding="utf-8")
