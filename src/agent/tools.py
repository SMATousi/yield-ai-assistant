from __future__ import annotations

import dataclasses
import inspect
import json
import math

import plotly.graph_objects as go

from src.data.grid import KDTreeGrid
from src.data.loader import SummaryDataset
from src.geo import geocoder as _geocoder
from src.geo.geocoder import GeocodingError
from src.plots.recommendation import plot_recommendation
from src.plots.doy_response import plot_doy_response
from src.plots.theme import make_trt_label


class AgentError(Exception):
    pass


@dataclasses.dataclass
class ToolContext:
    dataset: SummaryDataset
    grid: KDTreeGrid


@dataclasses.dataclass
class ToolResult:
    content: str
    figure: go.Figure | None = None


TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_nearest_site",
            "description": (
                "Resolve a free-text location (county name, city, ZIP code, or address "
                "in Missouri) to the nearest grid site in the soybean trial network. "
                "Returns the site key, its coordinates, and the distance from the query "
                "point in degrees. Call this first whenever the user mentions a location, "
                "before generating any plot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Any location string: county name (e.g. 'Audrain County, MO'), "
                            "city (e.g. 'Columbia, MO'), ZIP code (e.g. '65201'), "
                            "street address, or decimal coordinates (e.g. '38.5, -92.3')."
                        ),
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_recommendation_plot",
            "description": (
                "Generate a two-panel soybean management recommendation figure for a specific "
                "location, planting date, and moisture scenario. Panel A ranks treatments by "
                "P(best) with confidence intervals. Panel B shows the risk-return trade-off "
                "as a bubble chart. Returns a Plotly figure. "
                "Pass 'site' (from a prior lookup_nearest_site call) OR 'location' (will be geocoded)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "description": (
                            "Grid site key returned by lookup_nearest_site, e.g. '38.95_-92.33'. "
                            "Preferred when already resolved — avoids a second geocoding call."
                        ),
                    },
                    "location": {
                        "type": "string",
                        "description": (
                            "Free-text location in Missouri. Required only when 'site' is not available."
                        ),
                    },
                    "planting_date": {
                        "type": "string",
                        "description": (
                            "Planting date in 'Mon-DD' format, e.g. 'Apr-15'. "
                            "If the user does not specify a date, use 'Apr-15' as the default."
                        ),
                    },
                    "moisture_scenario": {
                        "type": "string",
                        "enum": ["dry", "all", "wet"],
                        "description": (
                            "One of: 'dry', 'all', 'wet'. Map from natural language: "
                            "'dry spring', 'drought year', 'dry conditions' → 'dry'; "
                            "'wet year', 'above-average precipitation', 'wet season' → 'wet'; "
                            "'average', 'normal', 'typical', 'all conditions' → 'all'."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_doy_response_plot",
            "description": (
                "Generate a three-panel planting-date response figure for a location. "
                "Shows how mean yield varies with planting date for the best treatments, "
                "with one panel each for dry, average, and wet years. Star markers indicate "
                "the winning treatment at each planting date. "
                "Pass 'site' (from a prior lookup_nearest_site call) OR 'location' (will be geocoded)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "description": (
                            "Grid site key returned by lookup_nearest_site, e.g. '38.95_-92.33'. "
                            "Preferred when already resolved."
                        ),
                    },
                    "location": {
                        "type": "string",
                        "description": (
                            "Free-text location in Missouri. Required only when 'site' is not available."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]

_KNOWN_TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


# ── Private tool implementations ───────────────────────────────────────────────

def _site_coords(site: str) -> tuple[float, float]:
    lat_str, lon_str = site.split("_", 1)
    return float(lat_str), float(lon_str)


def _validate_site_key(site: str) -> str | None:
    """Return an error message string if the site key format is invalid, else None."""
    try:
        lat_str, lon_str = site.split("_", 1)
        float(lat_str)
        float(lon_str)
        return None
    except (ValueError, AttributeError):
        return (
            f"Invalid site key {site!r}. Site keys must be 'lat_lon' format "
            f"(e.g. '38.95_-92.33'). Call lookup_nearest_site with a Missouri "
            f"location name to get the correct key."
        )


def _lookup_nearest_site(location: str, ctx: ToolContext) -> ToolResult:
    try:
        lat, lon = _geocoder.geocode(location)
        site = ctx.grid.nearest_site(lat, lon)
        site_lat, site_lon = _site_coords(site)
        distance = math.sqrt((lat - site_lat) ** 2 + (lon - site_lon) ** 2)
        return ToolResult(
            content=json.dumps({
                "site": site,
                "query_lat": round(lat, 6),
                "query_lon": round(lon, 6),
                "site_lat": site_lat,
                "site_lon": site_lon,
                "distance_deg": round(distance, 4),
            })
        )
    except (GeocodingError, ValueError) as exc:
        return ToolResult(content=f"Error resolving location {location!r}: {exc}")


def _generate_recommendation_plot(
    moisture_scenario: str = "all",
    location: str | None = None,
    site: str | None = None,
    planting_date: str = "Apr-15",
    ctx: ToolContext = None,  # type: ignore[assignment]
) -> ToolResult:
    try:
        if site is not None:
            err = _validate_site_key(site)
            if err:
                return ToolResult(content=json.dumps({"error": err}))
        if site is None:
            if not location:
                return ToolResult(content=json.dumps({
                    "error": "either 'site' or 'location' is required.",
                    "hint": "Pass the 'site' key returned by lookup_nearest_site.",
                }))
            lat, lon = _geocoder.geocode(location)
            site = ctx.grid.nearest_site(lat, lon)
        fig = plot_recommendation(
            ctx.dataset.df, site, planting_date, moisture_scenario
        )
        flat = ctx.dataset.df.reset_index()
        sub = flat[
            (flat["site"] == site)
            & (flat["plt_dtDoy"] == planting_date)
            & (flat["moisture_group"] == moisture_scenario)
        ].sort_values("composite", ascending=False)
        top_trt_label = make_trt_label(sub.iloc[0]) if not sub.empty else "N/A"
        top_p_best = float(sub.iloc[0]["P_best"]) if not sub.empty else 0.0
        return ToolResult(
            content=json.dumps({
                "site": site,
                "plt_dtDoy": planting_date,
                "moisture_group": moisture_scenario,
                "top_trt_label": top_trt_label,
                "top_p_best": round(top_p_best, 4),
            }),
            figure=fig,
        )
    except (GeocodingError, ValueError) as exc:
        return ToolResult(content=f"Error generating recommendation plot: {exc}")


def _generate_doy_response_plot(
    location: str | None = None,
    site: str | None = None,
    ctx: ToolContext = None,  # type: ignore[assignment]
) -> ToolResult:
    try:
        if site is not None:
            err = _validate_site_key(site)
            if err:
                return ToolResult(content=json.dumps({"error": err}))
        if site is None:
            if not location:
                return ToolResult(content=json.dumps({
                    "error": "either 'site' or 'location' is required.",
                    "hint": "Pass the 'site' key returned by lookup_nearest_site.",
                }))
            lat, lon = _geocoder.geocode(location)
            site = ctx.grid.nearest_site(lat, lon)
        fig = plot_doy_response(ctx.dataset.df, site)
        flat = ctx.dataset.df.reset_index()
        site_df = flat[flat["site"] == site]
        dates = sorted(site_df["plt_dtDoy"].unique().tolist())
        date_range = f"{dates[0]} to {dates[-1]}" if dates else "N/A"
        return ToolResult(
            content=json.dumps({
                "site": site,
                "date_range": date_range,
                "moisture_groups": ["dry", "all", "wet"],
            }),
            figure=fig,
        )
    except (GeocodingError, ValueError) as exc:
        return ToolResult(content=f"Error generating DOY response plot: {exc}")


# ── Dispatcher ─────────────────────────────────────────────────────────────────

_DISPATCH = {
    "lookup_nearest_site": _lookup_nearest_site,
    "generate_recommendation_plot": _generate_recommendation_plot,
    "generate_doy_response_plot": _generate_doy_response_plot,
}


def execute_tool(name: str, arguments: dict, ctx: ToolContext) -> ToolResult:
    fn = _DISPATCH.get(name)
    if fn is None:
        raise AgentError(f"Unknown tool: {name!r}")
    valid = set(inspect.signature(fn).parameters) - {"ctx"}
    filtered = {k: v for k, v in arguments.items() if k in valid}
    # Some models echo the parameter schema object as the argument value instead of
    # supplying an actual string. Discard any value that looks like a schema property
    # (a dict with a "type" key) so the tool receives only real values.
    filtered = {k: v for k, v in filtered.items() if not (isinstance(v, dict) and "type" in v)}
    return fn(**filtered, ctx=ctx)
