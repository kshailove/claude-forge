"""
agents.py — Factory functions for the 4 CrewAI agents.

All agents are constructed inside build_crew() (in crew.py) so that fresh LLM
instances are created per prospect run. Do not instantiate agents at module level.
"""

from __future__ import annotations

from typing import Any, Optional

from crewai import Agent, LLM

from tools import KnowledgeSearchTool, TavilyWebSearch, WebsiteThemeScraper


def make_researcher_agent(llm: LLM, tavily_tool: TavilyWebSearch) -> Agent:
    """
    Create Agent 1 — Business Intelligence Researcher.

    Conducts 2–3 targeted searches about the prospect using Tavily.

    Args:
        llm: A configured LLM instance.
        tavily_tool: A TavilyWebSearch tool instance (k=3).

    Returns:
        A CrewAI Agent configured for prospect research.
    """
    return Agent(
        role="Senior Business Intelligence Researcher",
        goal=(
            "Deeply understand the prospect's business model, industry verticals, "
            "key customer segments, and top operational pain points."
        ),
        backstory=(
            "You are a senior analyst who synthesises market intelligence from diverse sources. "
            "You are skilled at identifying the specific operational and strategic pain points "
            "that B2B SaaS companies face in their growth phase. You write concise, structured "
            "summaries that sales teams can immediately act on."
        ),
        tools=[tavily_tool],
        llm=llm,
        verbose=False,
        max_iter=5,
    )


def make_brand_agent(llm: LLM, theme_tool: WebsiteThemeScraper) -> Agent:
    """
    Create Agent 2 — Web Design and Brand Analyst.

    Extracts visual brand identity (colours, fonts) from the prospect's homepage.

    Args:
        llm: A configured LLM instance.
        theme_tool: A WebsiteThemeScraper tool instance.

    Returns:
        A CrewAI Agent configured for brand analysis.
    """
    return Agent(
        role="Web Design and Brand Analyst",
        goal=(
            "Extract the visual identity of the prospect's website, including primary colours, "
            "secondary colours, background colours, and font families."
        ),
        backstory=(
            "You specialise in reverse-engineering brand design from live websites. "
            "You can identify colour palettes from CSS and meta tags, and detect Google Fonts "
            "from link tags. When scraping fails, you fall back to a neutral professional theme "
            "and clearly report which data was derived from the live site versus defaults."
        ),
        tools=[theme_tool],
        llm=llm,
        verbose=False,
        max_iter=3,
    )


def make_value_prop_agent(llm: LLM, knowledge_tool: KnowledgeSearchTool) -> Agent:
    """
    Create Agent 3 — Value Proposition Strategist.

    Retrieves relevant knowledge chunks and maps them to prospect pain points.

    Args:
        llm: A configured LLM instance.
        knowledge_tool: A KnowledgeSearchTool instance connected to the company's KB.

    Returns:
        A CrewAI Agent configured for value proposition generation.
    """
    return Agent(
        role="Solution Consultant",
        goal=(
            "Using retrieved knowledge chunks about the selling company's capabilities, "
            "produce a prioritised list of value propositions specific to the prospect."
        ),
        backstory=(
            "You are a trusted advisor who connects product capabilities to customer needs. "
            "You never fabricate product features — every claim you make is grounded in the "
            "knowledge chunks retrieved from the company's knowledge base. You are skilled at "
            "mapping specific pain points to concrete product capabilities with measurable outcomes."
        ),
        tools=[knowledge_tool],
        llm=llm,
        verbose=False,
        max_iter=3,
    )


def make_presentation_agent(llm: LLM) -> Agent:
    """
    Create Agent 4 — Presentation Designer.

    Generates the complete 10-slide self-contained HTML presentation.

    Args:
        llm: A configured LLM instance.

    Returns:
        A CrewAI Agent configured for HTML presentation generation.
    """
    return Agent(
        role="B2B SaaS Creative Director",
        goal=(
            "Author a complete, beautifully formatted 10-slide HTML presentation "
            "positioning the selling company as the solution to the prospect's pain points."
        ),
        backstory=(
            "You are an award-winning creative director who writes flawless HTML. "
            "You apply brand colours directly in inline CSS and style blocks. "
            "You always output exactly 10 <section> elements as direct children of "
            "<div class='slides'> — no more, no less. Your HTML is self-contained: "
            "all CSS is inline or in a <style> block; there are no external CSS or JS "
            "file dependencies. When a Google Fonts name is provided, you add a <link> "
            "tag to fonts.googleapis.com. You never include placeholder text or lorem ipsum."
        ),
        tools=[],
        llm=llm,
        verbose=False,
        max_iter=3,
    )
