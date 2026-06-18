"""
crew.py — Two-phase crew assembly and execution for the SDR Presentation Utility.

Architecture:
  Phase 1: Mini-crew with Agents 1 (Researcher) and 2 (Brand Analyst) running sequentially.
           Agent 1's output is then truncated to <=1,500 tokens via tiktoken.
  Phase 2: Final crew with Agents 3 (Value Prop Strategist) and 4 (Presentation Designer),
           with the truncated research injected directly into task descriptions.

A fresh Crew is instantiated per prospect — CrewAI 1.14.x does not support reuse.
"""

from __future__ import annotations

import os
import warnings
from typing import Optional

import tiktoken
from crewai import Crew, LLM, Process

from agents import (
    make_brand_agent,
    make_presentation_agent,
    make_researcher_agent,
    make_value_prop_agent,
)
from knowledge_store import KnowledgeStore
from tasks import (
    make_brand_task,
    make_presentation_task,
    make_research_task,
    make_value_prop_task,
)
from tools import KnowledgeSearchTool, TavilyWebSearch, WebsiteThemeScraper


_TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
MAX_RESEARCH_TOKENS = 1500


def _make_langfuse_handler(prospect_name: str, company_name: str) -> Optional[object]:
    """
    Return a LangFuse CallbackHandler if LANGFUSE_PUBLIC_KEY is set, else None.

    Each prospect run gets its own handler so traces are keyed per prospect.
    Silently disabled if keys are absent or langfuse is not installed.

    Args:
        prospect_name: Human-readable prospect company name.
        company_name: Selling company name.

    Returns:
        A CallbackHandler instance, or None.
    """
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    if not public_key:
        return None
    try:
        from langfuse.callback import CallbackHandler  # type: ignore[import]

        return CallbackHandler(
            public_key=public_key,
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
            trace_name=f"{company_name}/{prospect_name}",
            tags=[company_name, prospect_name],
        )
    except Exception:
        return None


def _truncate_to_tokens(text: str, max_tokens: int = MAX_RESEARCH_TOKENS) -> str:
    """
    Truncate text to at most max_tokens tokens using the cl100k_base encoder.

    Args:
        text: Input text string.
        max_tokens: Token limit. Defaults to MAX_RESEARCH_TOKENS (1500).

    Returns:
        Truncated (or original) text string.
    """
    tokens = _TIKTOKEN_ENC.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _TIKTOKEN_ENC.decode(tokens[:max_tokens])


def _build_llm(prospect_name: str, company_name: str) -> LLM:
    """
    Build a crewai LLM instance with optional LangFuse callback.

    Args:
        prospect_name: Used to key the LangFuse trace.
        company_name: Used to key the LangFuse trace.

    Returns:
        A configured crewai LLM instance.
    """
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    langfuse_handler = _make_langfuse_handler(prospect_name, company_name)
    callbacks = [langfuse_handler] if langfuse_handler else []
    return LLM(model=model_name, temperature=0.7, callbacks=callbacks)


def run_for_prospect(
    prospect_domain: str,
    prospect_name: str,
    company_name: str,
    knowledge_store: KnowledgeStore,
    strict: bool = False,
) -> str:
    """
    Run the full two-phase crew pipeline for a single prospect.

    Phase 1 runs Agents 1+2 (research + brand analysis).
    Agent 1's output is truncated to MAX_RESEARCH_TOKENS tokens.
    Phase 2 runs Agents 3+4 (value props + HTML presentation) with truncated research inline.

    Args:
        prospect_domain: The prospect's domain (e.g. "stripe.com").
        prospect_name: Human-readable prospect name (e.g. "Stripe").
        company_name: The selling company name (e.g. "hiver").
        knowledge_store: An initialised KnowledgeStore for the selling company.
        strict: If True, appends a strict section-count warning to the presentation task.

    Returns:
        Raw HTML string output from Agent 4.

    Raises:
        Exception: Re-raises any unrecoverable crew error. Caller (main.py) handles isolation.
    """
    inputs = {
        "prospect_name": prospect_name,
        "prospect_domain": prospect_domain,
        "company_name": company_name,
    }

    # ---------------------------------------------------------------
    # Phase 1: Research + Brand Analysis
    # ---------------------------------------------------------------
    # A single LangFuse handler is created here and shared across both phases via the llm
    # instance. During integration testing, verify that both phase 1 (researcher + brand)
    # and phase 2 (value prop + presentation) spans appear under the same trace in LangFuse.
    llm = _build_llm(prospect_name, company_name)

    tavily_tool = TavilyWebSearch(k=3)
    theme_tool = WebsiteThemeScraper()
    knowledge_tool = KnowledgeSearchTool(knowledge_store=knowledge_store)

    researcher = make_researcher_agent(llm, tavily_tool)
    brand_analyst = make_brand_agent(llm, theme_tool)

    research_task = make_research_task(researcher, inputs)
    brand_task = make_brand_task(brand_analyst, inputs)

    mini_crew = Crew(
        agents=[researcher, brand_analyst],
        tasks=[research_task, brand_task],
        process=Process.sequential,
        verbose=False,
    )
    mini_crew.kickoff(inputs=inputs)

    # Extract raw outputs from Phase 1
    research_raw: str = _get_task_output(research_task)
    brand_raw: str = _get_task_output(brand_task)

    # Truncate Agent 1's research to <=1,500 tokens
    truncated_research = _truncate_to_tokens(research_raw, MAX_RESEARCH_TOKENS)

    # ---------------------------------------------------------------
    # Phase 2: Value Props + Presentation (with injected research)
    # ---------------------------------------------------------------
    value_prop_strategist = make_value_prop_agent(llm, knowledge_tool)
    presentation_designer = make_presentation_agent(llm)

    value_prop_task = make_value_prop_task(
        value_prop_strategist, inputs, truncated_research, knowledge_tool
    )
    presentation_task = make_presentation_task(
        presentation_designer,
        inputs,
        truncated_research,
        brand_raw,
        value_prop_task,
        strict=strict,
    )

    final_crew = Crew(
        agents=[value_prop_strategist, presentation_designer],
        tasks=[value_prop_task, presentation_task],
        process=Process.sequential,
        verbose=False,
    )
    final_crew.kickoff(inputs=inputs)

    html_output = _get_task_output(presentation_task)
    return html_output


def _get_task_output(task: object) -> str:
    """
    Extract the raw text output from a completed CrewAI Task.

    CrewAI 1.14.x exposes task output via task.output.raw. Falls back to
    str(task.output) if .raw is not available.

    Args:
        task: A completed CrewAI Task instance.

    Returns:
        The raw output string. Returns empty string if no output is available.
    """
    output = getattr(task, "output", None)
    if output is None:
        return ""
    raw = getattr(output, "raw", None)
    if raw is not None:
        return str(raw)
    warnings.warn(
        f"CrewAI task output has no .raw attribute; falling back to str(output). "
        f"Verify CrewAI version compatibility. "
        f"Task: {str(getattr(task, 'description', ''))[:60]}",
        stacklevel=2,
    )
    return str(output)
