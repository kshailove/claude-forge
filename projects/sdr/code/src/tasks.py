"""
tasks.py — Factory functions for the 4 CrewAI tasks.

Tasks are assembled inside build_crew() in crew.py. The two-phase approach
(see tech spec Section 5) means tasks are built in two batches:
  Phase 1: research_task + brand_task (no context dependencies)
  Phase 2: value_prop_task + presentation_task (inject truncated research inline)
"""

from __future__ import annotations

from crewai import Agent, Task

from tools import KnowledgeSearchTool


def make_research_task(researcher: Agent, inputs: dict[str, str]) -> Task:
    """
    Create Task 1 — Prospect Business Intelligence Research.

    Instructs Agent 1 to run 2–3 Tavily searches and produce a structured summary.

    Args:
        researcher: The Business Intelligence Researcher Agent.
        inputs: Dict with keys prospect_name, prospect_domain, company_name.

    Returns:
        A CrewAI Task for prospect research.
    """
    prospect_name = inputs["prospect_name"]
    prospect_domain = inputs["prospect_domain"]

    return Task(
        description=(
            f"Search for information about {prospect_name} ({prospect_domain}). "
            "Conduct 2–3 targeted searches covering: "
            "(1) business model and revenue streams, "
            "(2) key customer segments and verticals, "
            "(3) operational pain points and growth challenges. "
            f"If Tavily returns no results, write: 'Limited information found for {prospect_domain}. "
            "Proceeding with general industry context.' "
            "Write a structured summary. Be concise — aim for under 800 words."
        ),
        expected_output=(
            f"A structured text summary (under 800 words) covering {prospect_name}'s "
            "business model, customer segments, and 3–5 specific pain points."
        ),
        agent=researcher,
    )


def make_brand_task(brand_analyst: Agent, inputs: dict[str, str]) -> Task:
    """
    Create Task 2 — Brand Colour and Font Extraction.

    Instructs Agent 2 to use WebsiteThemeScraper and report the JSON theme.

    Args:
        brand_analyst: The Web Design and Brand Analyst Agent.
        inputs: Dict with keys prospect_name, prospect_domain, company_name.

    Returns:
        A CrewAI Task for brand extraction. Has no context dependency on Task 1.
    """
    prospect_domain = inputs["prospect_domain"]

    return Task(
        description=(
            f"Use the WebsiteThemeScraper tool to extract the brand colours and fonts "
            f"from {prospect_domain}. Report the exact JSON theme object returned by the tool. "
            "Do not modify or guess values — report only what the tool returns."
        ),
        expected_output=(
            "A JSON object with exactly these keys: primary_color, secondary_color, "
            "background_color, font_family, accent_color. Each value is a CSS string."
        ),
        agent=brand_analyst,
    )


def make_value_prop_task(
    value_prop_strategist: Agent,
    inputs: dict[str, str],
    truncated_research: str,
    knowledge_tool: KnowledgeSearchTool,
) -> Task:
    """
    Create Task 3 — RAG-Grounded Value Proposition Generation (Phase 2).

    Injects the truncated Agent 1 research directly into the task description
    rather than using context= object chaining, so the 1,500-token cap is enforced.

    Args:
        value_prop_strategist: The Solution Consultant Agent.
        inputs: Dict with keys prospect_name, prospect_domain, company_name.
        truncated_research: Agent 1's output, already truncated to <=1,500 tokens.
        knowledge_tool: The KnowledgeSearchTool instance.

    Returns:
        A CrewAI Task for value proposition generation.
    """
    prospect_name = inputs["prospect_name"]
    company_name = inputs["company_name"]

    # Intentional deviation from PRD F5-AC3: research is injected inline via
    # truncated_research rather than via context=[research_task] chaining.
    # CrewAI context= concatenates the full raw output and cannot enforce a token cap;
    # the two-phase pattern in crew.py truncates to MAX_RESEARCH_TOKENS before this call.
    return Task(
        description=(
            f"Using the KnowledgeSearchTool, search {company_name}'s knowledge base "
            f"for the top 5 capabilities most relevant to {prospect_name}'s pain points. "
            "Produce a prioritised list of 5 value propositions. "
            "Each value prop MUST cite a specific product feature or metric from the retrieved chunks.\n\n"
            f"Research context about {prospect_name}:\n{truncated_research}"
        ),
        expected_output=(
            f"A numbered list of 5 value propositions. Each must: "
            f"(1) name the {prospect_name} pain point, "
            f"(2) name the specific {company_name} capability that addresses it, "
            "(3) include a concrete metric or outcome if available in the knowledge base."
        ),
        agent=value_prop_strategist,
        tools=[knowledge_tool],
    )


def make_presentation_task(
    presentation_designer: Agent,
    inputs: dict[str, str],
    truncated_research: str,
    brand_output: str,
    value_prop_task: Task,
    strict: bool = False,
) -> Task:
    """
    Create Task 4 — 10-Slide HTML Presentation Generation (Phase 2).

    Injects truncated research and brand theme inline into the task description.
    Uses context=[value_prop_task] so Agent 4 also receives the value propositions.

    Args:
        presentation_designer: The B2B SaaS Creative Director Agent.
        inputs: Dict with keys prospect_name, prospect_domain, company_name.
        truncated_research: Agent 1's output, already truncated to <=1,500 tokens.
        brand_output: Agent 2's raw output (JSON theme string).
        value_prop_task: Task 3 instance (used for context chaining).
        strict: If True, appends a strict section-count warning to the description.

    Returns:
        A CrewAI Task for HTML presentation generation.
    """
    prospect_name = inputs["prospect_name"]
    company_name = inputs["company_name"]

    base_description = (
        f"Generate a complete 10-slide HTML presentation. Requirements:\n"
        "- Pure HTML with all CSS inline or in a <style> block in <head>\n"
        "- No external CSS or JS file dependencies\n"
        "- All slides are <section> elements, direct children of <div class='slides'>\n"
        "- Each <section> has style='height:100vh; width:100%; ...'\n"
        "- Apply the brand colours from the brand theme context\n"
        "- If font_family is a Google Fonts name, add a <link> tag to fonts.googleapis.com\n"
        f"- Mandatory slides: title/hook, who is {company_name}, "
        f"  at least 2 slides on {prospect_name} pain points, "
        f"  at least 3 slides on {company_name} value/fit, "
        "  1 ROI/social proof slide, 1 CTA/next steps slide\n"
        f"- Include both {prospect_name} and {company_name} by name in the deck\n"
        "OUTPUT: Only the complete HTML document. No preamble, no explanation, no markdown fences.\n\n"
        f"Research context about {prospect_name}:\n{truncated_research}\n\n"
        f"Brand theme for {prospect_name}:\n{brand_output}"
    )

    if strict:
        base_description += (
            "\n\nCRITICAL: Your previous output had the wrong number of <section> elements. "
            "You MUST output exactly 10 <section> elements as direct children of <div class='slides'>. "
            "Count them before outputting. Do not include any other <section> tags in the document."
        )

    return Task(
        description=base_description,
        expected_output=(
            "A complete, valid HTML5 document. The <div class='slides'> element must contain "
            "exactly 10 <section> child elements. Output only the HTML — no explanation."
        ),
        agent=presentation_designer,
        context=[value_prop_task],
    )
