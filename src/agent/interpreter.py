from __future__ import annotations

import pandas as pd

from config import LLM_MODEL
from src.plots.theme import make_trt_label


def build_interpretation_prompt(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
) -> str:
    flat = df.reset_index()
    sub = flat[
        (flat["site"] == site)
        & (flat["plt_dtDoy"] == plt_dtDoy)
        & (flat["moisture_group"] == moisture_group)
    ].sort_values("composite", ascending=False)

    if sub.empty:
        raise ValueError(
            f"No data for site={site!r}, plt_dtDoy={plt_dtDoy!r}, "
            f"moisture_group={moisture_group!r}"
        )

    top3 = sub.head(3)
    top3 = top3.copy()
    top3["trt_label"] = top3.apply(make_trt_label, axis=1)

    rows_text = "\n".join(
        f"  #{i + 1}: {row['trt_label']}  "
        f"P(best)={row['P_best']:.1%}  "
        f"CVaR_20={row['CVaR_20']:.1f} bu/acre  "
        f"composite={row['composite']:.3f}"
        for i, (_, row) in enumerate(top3.iterrows())
    )

    moisture_label = {"dry": "dry", "all": "average", "wet": "wet"}.get(
        moisture_group, moisture_group
    )

    return (
        f"You are an agronomic advisor. The following are the top 3 soybean management "
        f"combinations for the grid point nearest to site {site}, planted around "
        f"{plt_dtDoy}, under {moisture_label} year conditions:\n\n"
        f"{rows_text}\n\n"
        f"Write a plain-language explanation (≥150 words) for a Missouri Extension field "
        f"agronomist. Your explanation must cover: (1) why the #1 combination is recommended, "
        f"referencing its P(best) value and composite score; (2) the risk–return trade-off "
        f"among the top 3 — CVaR_20 measures mean yield in the worst 20% of simulated "
        f"weather years, so a higher CVaR_20 means better downside protection; "
        f"(3) a brief caveat that this recommendation comes from the nearest grid point in "
        f"the trial network and actual performance may vary with local soil conditions. "
        f"Do not mention Python, Plotly, or data science terminology."
    )


def interpret(
    df: pd.DataFrame,
    site: str,
    plt_dtDoy: str,
    moisture_group: str,
    model: str = LLM_MODEL,
) -> str:
    import litellm

    prompt = build_interpretation_prompt(df, site, plt_dtDoy, moisture_group)
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
