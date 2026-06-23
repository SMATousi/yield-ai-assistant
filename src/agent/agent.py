from __future__ import annotations

import dataclasses
import json
from collections.abc import Generator

import litellm
import plotly.graph_objects as go

from config import LLM_MODEL
from src.agent.tools import AgentError, ToolContext, ToolResult, TOOLS, execute_tool
from src.agent.interpreter import interpret

__all__ = ["AgentError", "AgentEvent", "AgentResponse", "SYSTEM_PROMPT", "run_agent"]


@dataclasses.dataclass
class AgentResponse:
    text: str
    figures: dict[str, go.Figure]   # keyed by tool name
    site: str | None
    raw_messages: list[dict]


@dataclasses.dataclass
class AgentEvent:
    type: str          # "log" | "result" | "error"
    text: str = ""
    response: AgentResponse | None = None
    exc: BaseException | None = None


SYSTEM_PROMPT = """\
You are an agronomic advisor assistant for MU Extension in Missouri. You help field \
agronomists interpret soybean management trial results and give site-specific \
recommendations based on 30 years of simulated weather scenarios.

## Tool use rules
- Always call a tool before providing agronomic advice about a specific location or plot.
- When the user mentions a location, call `lookup_nearest_site` first to get the site key. \
Then pass that exact site key to the plot tool. Never call a plot tool without either 'site' \
(from a prior lookup) or 'location'.
- Never fabricate plot data or treatment rankings — all numbers must come from a tool result.
- Do not repeat a tool call with the same arguments in the same turn.
- For any recommendation query (best treatment, top management, what to plant, how to manage), \
call BOTH `generate_recommendation_plot` AND `generate_doy_response_plot` for the same site. \
Call them in the same turn; order does not matter.
- If the user asks only to see a planting-date response curve (no recommendation needed), \
call only `generate_doy_response_plot`.

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


def _get_message_text(msg) -> str:
    """Return the best available text from a litellm Message.

    Thinking models (qwen3, deepseek-r1, etc.) via Ollama can produce an empty
    `content` field when all output goes into reasoning tokens. Fall back to
    `reasoning_content` so the user sees something instead of a blank reply.
    """
    content = (msg.content or "").strip() if msg else ""
    if not content:
        content = (getattr(msg, "reasoning_content", None) or "").strip()
    return content


def run_agent(
    user_query: str,
    ctx: ToolContext,
    max_iterations: int = 10,
    model: str = LLM_MODEL,
    prior_messages: list[dict] | None = None,
) -> Generator[AgentEvent, None, None]:
    """Generator — yields AgentEvent(type='log') progress entries then one
    AgentEvent(type='result') or AgentEvent(type='error') at the end."""

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if prior_messages:
        messages.extend(prior_messages)
    messages.append({"role": "user", "content": user_query})

    figures: dict[str, go.Figure] = {}
    site: str | None = None
    plt_dtDoy: str | None = None
    moisture_group: str | None = None
    msg = None
    _consecutive_failures = 0
    _called_tools: set[tuple[str, str]] = set()

    try:
        for i in range(max_iterations):
            yield AgentEvent("log", text=f"[→] Calling {model} (turn {i + 1})…")
            response = litellm.completion(model=model, messages=messages, tools=TOOLS)
            msg = response.choices[0].message

            if not msg.tool_calls:
                yield AgentEvent("log", text="[✓] Final response received.")
                break

            messages.append(_make_assistant_dict(msg))

            _had_new_tool_call = False

            for tc in msg.tool_calls:
                if tc.function.name not in _KNOWN_TOOL_NAMES:
                    available = ", ".join(sorted(_KNOWN_TOOL_NAMES))
                    messages.append(_tool_error_message(
                        tc.id,
                        f"Unknown tool {tc.function.name!r}. "
                        f"Available tools: {available}. "
                        f"To resolve a location, call lookup_nearest_site first.",
                    ))
                    yield AgentEvent("log", text=f"[✗] Unknown tool: {tc.function.name!r}")
                    _consecutive_failures += 1
                    continue

                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    messages.append(_tool_error_message(tc.id, "Invalid JSON in tool arguments"))
                    yield AgentEvent("log", text=f"[✗] Bad JSON args for {tc.function.name}")
                    _consecutive_failures += 1
                    continue

                call_key = (tc.function.name, tc.function.arguments)
                if call_key in _called_tools:
                    messages.append(_tool_error_message(
                        tc.id,
                        f"Tool {tc.function.name!r} was already called with these arguments. "
                        "You have all the data you need. Stop calling tools and write your "
                        "final agronomic response now.",
                    ))
                    yield AgentEvent("log", text=f"[✗] Duplicate blocked: {tc.function.name}")
                    continue
                _called_tools.add(call_key)
                _had_new_tool_call = True

                args_preview = tc.function.arguments[:300]
                yield AgentEvent("log", text=f"[⚙] {tc.function.name}({args_preview})")

                result: ToolResult = execute_tool(tc.function.name, args, ctx)

                preview = result.content[:400] + ("…" if len(result.content) > 400 else "")
                yield AgentEvent("log", text=f"    ↳ {preview}")

                # Count tool-level errors (e.g. invalid site key) as failures too
                _parsed_result = _try_parse_json(result.content)
                if _parsed_result and "error" in _parsed_result:
                    _consecutive_failures += 1
                else:
                    _consecutive_failures = 0

                if result.figure is not None:
                    figures[tc.function.name] = result.figure

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

            # All calls this turn were duplicates — the model is stuck; break and
            # use whatever data was collected to generate the final response.
            if not _had_new_tool_call:
                yield AgentEvent("log", text="[✓] All tool calls were duplicates — proceeding to response.")
                break

            if _consecutive_failures >= 4:
                raise AgentError(
                    "The model made 4 consecutive failed tool calls "
                    "(unknown tools or invalid arguments). "
                    "Try a more capable model."
                )

        else:
            raise AgentError(
                f"Agent did not converge after {max_iterations} iterations. "
                "Check model tool-use capability."
            )

        base_text: str = _get_message_text(msg)

        # Thinking models sometimes echo the tool error JSON as their final content
        # instead of writing a real response. Discard it so only the interpretation
        # (generated below) is shown.
        _parsed_base = _try_parse_json(base_text)
        if _parsed_base and "error" in _parsed_base and len(_parsed_base) <= 2:
            base_text = ""

        interpretation = ""
        if figures and site and plt_dtDoy and moisture_group:
            yield AgentEvent("log", text="[→] Generating interpretation…")
            try:
                interpretation = interpret(ctx.dataset.df, site, plt_dtDoy, moisture_group, model=model)
                yield AgentEvent("log", text="[✓] Interpretation complete.")
            except Exception:
                pass

        if interpretation:
            text = (base_text + "\n\n---\n\n" + interpretation) if base_text else interpretation
        elif base_text:
            text = base_text
        else:
            text = (
                "I wasn't able to generate a recommendation. "
                "Please rephrase your query or verify the location is in Missouri."
            )

        # Always append the final assistant turn so raw_messages is complete.
        messages.append({"role": "assistant", "content": text})

        yield AgentEvent(
            "result",
            response=AgentResponse(
                text=text,
                figures=figures,
                site=site,
                raw_messages=messages,
            ),
        )

    except Exception as exc:
        yield AgentEvent("error", text=f"Error: {exc}", exc=exc)
