from __future__ import annotations

import os
import tempfile

import gradio as gr
import plotly.graph_objects as go

from config import AGGREGATE_CSV, LLM_MODEL
from src.data.loader import load_dataset
from src.data.grid import build_grid
from src.agent.tools import ToolContext
from src.agent.agent import run_agent, AgentError
from src.app.state import (
    KNOWN_CLOUD_MODELS,
    SessionState,
    clear_session,
    doy_sort_key,
    list_ollama_models,
    make_session_state,
)

# ── Startup singletons (fail fast if CSV missing) ─────────────────────────────
_ds = load_dataset(AGGREGATE_CSV)
_grid = build_grid(_ds)
_ctx = ToolContext(dataset=_ds, grid=_grid)

_DATE_CHOICES: list[str] = sorted(
    _ds.df.index.get_level_values("plt_dtDoy").unique(),
    key=doy_sort_key,
)


# ── Pure helper functions (testable without Gradio) ───────────────────────────

def _resolve_model_str(
    provider: str,
    ollama_model: str | None,
    cloud_model: str | None,
    custom_model: str | None,
) -> str:
    if provider == "Ollama (local)":
        name = (ollama_model or "").strip()
        return f"ollama/{name}" if name else LLM_MODEL
    elif provider in ("Claude API", "OpenAI"):
        return (cloud_model or LLM_MODEL).strip()
    else:
        return (custom_model or LLM_MODEL).strip()


def _augment_query(
    query: str,
    default_date: str,
    default_moisture: str,
    top_n: int,
) -> str:
    q_lower = query.lower()
    has_date = default_date.lower() in q_lower
    has_moisture = default_moisture in q_lower
    has_top = "top" in q_lower
    if not (has_date or has_moisture or has_top):
        return (
            f"{query} "
            f"[defaults: planting {default_date}, moisture {default_moisture}, "
            f"show top {top_n}]"
        )
    return query


def _save_figure_html(figure: go.Figure) -> str:
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        path = f.name
    figure.write_html(path)
    return path


# ── Gradio event handlers ─────────────────────────────────────────────────────

def _update_provider_visibility(provider: str) -> tuple:
    is_ollama = provider == "Ollama (local)"
    is_cloud = provider in ("Claude API", "OpenAI")
    is_custom = provider == "Custom"
    return (
        gr.update(visible=is_ollama),   # ollama_dd
        gr.update(visible=is_ollama),   # refresh_btn
        gr.update(visible=is_cloud),    # cloud_dd
        gr.update(visible=is_cloud),    # api_key_box
        gr.update(visible=is_custom),   # custom_model_box
    )


def _refresh_ollama_models() -> gr.update:
    return gr.update(choices=list_ollama_models())


def _handle_query(
    query: str,
    state: SessionState,
    provider: str,
    ollama_model: str | None,
    cloud_model: str | None,
    custom_model: str | None,
    api_key: str,
    default_date: str,
    default_moisture: str,
    top_n: int,
) -> tuple:
    if not query.strip():
        return state, state.chat_history, None, gr.update(), "Site: —", ""

    # Inject API key into environment before the LLM call
    if api_key.strip():
        if provider == "Claude API":
            os.environ["ANTHROPIC_API_KEY"] = api_key.strip()
        elif provider == "OpenAI":
            os.environ["OPENAI_API_KEY"] = api_key.strip()

    model_str = _resolve_model_str(provider, ollama_model, cloud_model, custom_model)
    augmented = _augment_query(query, default_date, default_moisture, int(top_n))

    # Build prior context: everything except the system message from previous turns
    prior = [m for m in state.messages if m.get("role") != "system"]

    try:
        response = run_agent(
            augmented,
            _ctx,
            model=model_str,
            prior_messages=prior if prior else None,
        )
    except (AgentError, Exception) as exc:
        error_text = f"Error: {exc}"
        state.chat_history.append({"role": "user", "content": query})
        state.chat_history.append({"role": "assistant", "content": error_text})
        return (
            state,
            state.chat_history,
            None,
            gr.update(visible=False),
            f"Site: {state.last_site or '—'}  |  Model: {model_str}",
            "",
        )

    state.chat_history.append({"role": "user", "content": query})
    state.chat_history.append({"role": "assistant", "content": response.text})
    state.messages = [
        m for m in response.raw_messages if m.get("role") != "system"
    ]
    if response.site:
        state.last_site = response.site

    html_path = None
    download_update = gr.update(visible=False)
    if response.figure is not None:
        html_path = _save_figure_html(response.figure)
        download_update = gr.update(visible=True, value=html_path)

    status = f"Site: {state.last_site or '—'}  |  Model: {model_str}"

    return (
        state,
        state.chat_history,
        response.figure,
        download_update,
        status,
        "",
    )


def _clear_session_handler() -> tuple:
    return (
        make_session_state(),
        [],
        None,
        gr.update(visible=False),
        "Site: —",
        "",
    )


# ── App builder ───────────────────────────────────────────────────────────────

def build_app() -> gr.Blocks:
    initial_ollama_models = list_ollama_models()

    with gr.Blocks(title="Yield AI Assistant") as demo:
        gr.Markdown("# Yield AI Assistant\nSoybean management recommendations for Missouri.")

        state = gr.State(value=make_session_state())

        with gr.Row():
            # ── Settings sidebar ──────────────────────────────────────────────
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### Model")

                provider_radio = gr.Radio(
                    choices=["Ollama (local)", "Claude API", "OpenAI", "Custom"],
                    value="Ollama (local)",
                    label="LLM provider",
                )

                ollama_dd = gr.Dropdown(
                    choices=initial_ollama_models,
                    value=initial_ollama_models[0] if initial_ollama_models else None,
                    label="Ollama model",
                    visible=True,
                )
                refresh_btn = gr.Button("Refresh models", size="sm", visible=True)

                cloud_dd = gr.Dropdown(
                    choices=KNOWN_CLOUD_MODELS,
                    value=KNOWN_CLOUD_MODELS[0],
                    label="Model",
                    visible=False,
                )

                api_key_box = gr.Textbox(
                    label="API key",
                    type="password",
                    visible=False,
                    placeholder="sk-...",
                )

                custom_model_box = gr.Textbox(
                    label="Custom model string",
                    visible=False,
                    placeholder="ollama/llama3.1:8b",
                )

                with gr.Accordion("Plot defaults", open=False):
                    default_date_dd = gr.Dropdown(
                        choices=_DATE_CHOICES,
                        value="Apr-15" if "Apr-15" in _DATE_CHOICES else _DATE_CHOICES[0],
                        label="Default planting date",
                    )
                    default_moisture_dd = gr.Dropdown(
                        choices=["dry", "all", "wet"],
                        value="all",
                        label="Default moisture scenario",
                    )
                    top_n_slider = gr.Slider(
                        minimum=1,
                        maximum=10,
                        value=3,
                        step=1,
                        label="Top N treatments",
                    )

            # ── Main area ─────────────────────────────────────────────────────
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    height=420,
                    show_label=False,
                    placeholder="Your conversation will appear here.",
                )

                with gr.Row():
                    query_box = gr.Textbox(
                        show_label=False,
                        placeholder=(
                            "Ask about your farm — e.g. 'Best management for "
                            "Audrain County in a dry spring'"
                        ),
                        lines=2,
                        scale=5,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                figure_display = gr.Plot(label="Figure")

                download_btn = gr.DownloadButton(
                    label="Download figure (HTML)",
                    visible=False,
                )

                status_md = gr.Markdown("Site: —")

                clear_btn = gr.Button("Clear", size="sm")

        # ── Event wiring ──────────────────────────────────────────────────────

        _query_inputs = [
            query_box, state,
            provider_radio, ollama_dd, cloud_dd, custom_model_box, api_key_box,
            default_date_dd, default_moisture_dd, top_n_slider,
        ]
        _query_outputs = [state, chatbot, figure_display, download_btn, status_md, query_box]

        send_btn.click(fn=_handle_query, inputs=_query_inputs, outputs=_query_outputs)
        query_box.submit(fn=_handle_query, inputs=_query_inputs, outputs=_query_outputs)

        refresh_btn.click(fn=_refresh_ollama_models, inputs=[], outputs=[ollama_dd])

        provider_radio.change(
            fn=_update_provider_visibility,
            inputs=[provider_radio],
            outputs=[ollama_dd, refresh_btn, cloud_dd, api_key_box, custom_model_box],
        )

        clear_btn.click(
            fn=_clear_session_handler,
            inputs=[],
            outputs=[state, chatbot, figure_display, download_btn, status_md, query_box],
        )

    return demo


if __name__ == "__main__":
    build_app().launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(),
    )
