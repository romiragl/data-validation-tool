"""
ai_narrator.py
Feeds computed validation results (never raw data) to Gemini API
and returns a plain-English markdown report.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.validators import ValidationResult

# Load .env for local development
load_dotenv(Path(__file__).parent.parent / ".env")


def _get_api_key() -> str:
    """Get Gemini API key — checks st.secrets first (Streamlit Cloud), then .env (local)."""
    # Try Streamlit secrets (set in Streamlit Cloud dashboard)
    try:
        import streamlit as st
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key and key != "your_gemini_api_key_here":
            return key
    except Exception:
        pass
    # Fall back to environment variable / .env
    return os.getenv("GEMINI_API_KEY", "")


def _build_prompt(
    client: str,
    platform: str,
    status: str,
    results: list[ValidationResult],
) -> str:
    """Construct the prompt that gets sent to Gemini. Only computed results go in — never raw data."""

    results_json = json.dumps(
        [
            {
                "rule": r.rule_name,
                "description": r.description,
                "status": r.status,
                "total_checked": r.total_checked,
                "passed": r.passed,
                "failed": r.failed,
                "failure_pct": r.failure_pct,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason if r.skipped else None,
                "sample_failures": r.sample_failures[:3],
            }
            for r in results
        ],
        indent=2,
        default=str,
    )

    passed_rules = sum(1 for r in results if not r.skipped and r.failed == 0)
    failed_rules = sum(1 for r in results if not r.skipped and r.failed > 0)
    total_rows = max((r.total_checked for r in results if not r.skipped), default=0)

    prompt = f"""You are a data quality analyst for a retail intelligence company.

You have just received the results of an automated data validation run on crawl data for:
- **Client**: {client}
- **Platform**: {platform}
- **Data stage**: {status}
- **Total rows checked**: {total_rows:,}
- **Rules passed**: {passed_rules}
- **Rules failed**: {failed_rules}

Here are the validation results in JSON format. Every number here was computed by real SQL queries — your job is purely to narrate and interpret these results clearly for a non-technical business audience.

```json
{results_json}
```

Write a concise data quality report in markdown with these sections:

## Executive Summary
2-3 sentences on overall data health. Use plain language.

## Key Issues Found
For each FAILED or WARN rule, explain:
- What the rule checks
- How many records failed and what % that is
- What the business impact could be (e.g. wrong OSA = wrong availability reporting)
- Any pattern you notice in the sample failures

If no rules failed, say so clearly.

## Rules That Passed
Brief list of what looked clean.

## Skipped Checks
Briefly note any skipped rules and why.

## Recommended Actions
2-4 concrete next steps for the data team, prioritized by impact.

Keep the tone professional but accessible. Do not invent numbers — only use the figures from the JSON above."""

    return prompt


def generate_ai_report(
    client: str,
    platform: str,
    status: str,
    results: list[ValidationResult],
) -> str:
    """
    Call Gemini API with the validation results and return markdown text.
    Falls back to a structured plain-text summary if no API key is set.
    """
    api_key = _get_api_key()

    if not api_key or api_key == "your_gemini_api_key_here":
        return _fallback_report(client, platform, status, results)

    try:
        from google import genai
        from google.genai import types

        client_genai = genai.Client(api_key=api_key)
        prompt = _build_prompt(client, platform, status, results)
        response = client_genai.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        return response.text

    except Exception as e:
        return (
            f"> ⚠️ **AI report generation failed:** {e}\n\n"
            + _fallback_report(client, platform, status, results)
        )


def _fallback_report(
    client: str,
    platform: str,
    status: str,
    results: list[ValidationResult],
) -> str:
    """Plain-text summary used when no Gemini API key is configured."""
    passed = [r for r in results if not r.skipped and r.failed == 0]
    failed = [r for r in results if not r.skipped and r.failed > 0]
    skipped = [r for r in results if r.skipped]

    lines = [
        f"# Validation Report — {client} / {platform} ({status})",
        "",
        "> *AI narration unavailable — add your GEMINI_API_KEY to the `.env` file for a full report.*",
        "",
        "## Summary",
        f"- ✅ Rules passed: **{len(passed)}**",
        f"- ❌ Rules failed: **{len(failed)}**",
        f"- ⚪ Rules skipped: **{len(skipped)}**",
        "",
    ]

    if failed:
        lines.append("## Issues Found")
        for r in failed:
            lines.append(f"### {r.rule_name}")
            lines.append(f"- {r.description}")
            lines.append(f"- **{r.failed:,}** of **{r.total_checked:,}** rows failed ({r.failure_pct:.1f}%)")
            lines.append("")

    if passed:
        lines.append("## Passed")
        for r in passed:
            lines.append(f"- ✅ {r.rule_name} ({r.total_checked:,} rows checked)")
        lines.append("")

    if skipped:
        lines.append("## Skipped")
        for r in skipped:
            lines.append(f"- ⚪ {r.rule_name}: {r.skip_reason}")
        lines.append("")

    return "\n".join(lines)
