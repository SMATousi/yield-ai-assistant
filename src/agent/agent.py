from __future__ import annotations

import dataclasses
import json

import litellm
import plotly.graph_objects as go

from config import LLM_MODEL
from src.agent.tools import AgentError, ToolContext, ToolResult, TOOLS, execute_tool
from src.agent.interpreter import interpret

__all__ = ["AgentError", "AgentResponse", "SYSTEM_PROMPT", "run_agent"]


@dataclasses.dataclass
class AgentResponse:
    text: str
    figure: go.Figure | None
    site: str | None
    raw_messages: list[dict]


SYSTEM_PROMPT = """\
You are an agronomic advisor assistant for MU Extension in Missouri. You help field \
agronomists interpret soybean management trial results and give site-specific \
recommendations based on 30 years of simulated weather scenarios.

## Tool use rules
- Always call a tool before providing agronomic advice about a specific location or plot.
- When the user mentions a location, call `lookup_nearest_site` first to confirm which \
grid point will be used. Then call the appropriate plot tool.
- Never fabricate plot data or treatment rankings — all numbers must come from a tool result.
- If the user asks to see a planting-date response curve, call `generate_doy_response_plot`.
- If the user asks for a recommendation (best treatment, top management, what to plant), \
call `generate_recommendation_plot`.

## Moisture scenario mapping
When the user describes weather or seasonal conditions, map to the `moisture_scenario` \
parameter as follows:
- "dry spring", "drought year", "dry conditions", "dry year" → "dry"
- "wet year", "wet spring", "above-average precipitation", "wet season" → "wet"
- "average", "normal", "typical", "all conditions", "average year" → "all"

## Response style
- Write in plain English at a level appropriate for an experienced field agronomist.
- Be concise. Reference P(best) values and CVaR when discussing trade-offs.
- Avoid statistical jargon and never mention Python, Plotly, or data science tools.
"""

_KNOWN_TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def _make_assistant_dict(msg) -> dict:
    d: dict = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def _tool_error_message(tool_call_id: str, error: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": f"Error: {error}",
    }


def _try_parse_json(s: str) -> dict | None:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def run_agent(
    user_query: str,
    ctx: ToolContext,
    max_iterations: int = 10,
    model: str = LLM_MODEL,
    prior_messages: list[dict] | None = None,
) -> AgentResponse:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if prior_messages:
        messages.extend(prior_messages)
    messages.append({"role": "user", "content": user_query})

    figure: go.Figure | None = None
    site: str | None = None
    plt_dtDoy: str | None = None
    moisture_group: str | None = None
    msg = None

    for _ in range(max_iterations):
        response = litellm.completion(model=model, messages=messages, tools=TOOLS)
        msg = response.choices[0].message

        if not msg.tool_calls:
            break

        messages.append(_make_assistant_dict(msg))

        for tc in msg.tool_calls:
            if tc.function.name not in _KNOWN_TOOL_NAMES:
                messages.append(_tool_error_message(tc.id, f"Unknown tool: {tc.function.name!r}"))
                continue

            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append(_tool_error_message(tc.id, "Invalid JSON in tool arguments"))
                continue

            result: ToolResult = execute_tool(tc.function.name, args, ctx)

            if result.figure is not None:
                figure = result.figure

            parsed = _try_parse_json(result.content)
            if parsed:
                if "site" in parsed:
                    site = parsed["site"]
                if "plt_dtDoy" in parsed:
                    plt_dtDoy = parsed["plt_dtDoy"]
                if "moisture_group" in parsed:
                    moisture_group = parsed["moisture_group"]

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": result.content,
            })
    else:
        raise AgentError(
            f"Agent did not converge after {max_iterations} iterations. "
            "Check model tool-use capability."
        )

    base_text: str = (msg.content or "") if msg else ""

    interpretation = ""
    if figure is not None and site and plt_dtDoy and moisture_group:
        try:
            interpretation = interpret(ctx.dataset.df, site, plt_dtDoy, moisture_group, model=model)
        except Exception:
            pass

    text = base_text
    if interpretation:
        text = base_text + "\n\n---\n\n" + interpretation

    return AgentResponse(
        text=text,
        figure=figure,
        site=site,
        raw_messages=messages,
    )
