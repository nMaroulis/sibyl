"""Chronos reads forecast models, held-out evidence and the separate price baseline.

The model chooses typed ProtoLink evidence or help tools; it does not train a
forecast model. Tool descriptions explain their purpose to the reasoning model.
"""

from typing import Annotated

from protolink import Agent, ToolRejectedError
from pydantic import Field

from sibyl.agents.guides import read_guide
from sibyl.agents.guides.chronos import GUIDES, Topic
from sibyl.agents.utils.common import COMMON_PROMPT, Services, selected
from sibyl.services.markets.analytics import forecast

NAME = "Chronos"
TAGLINE = "Explore what comes next"
DESCRIPTION = (
    "Explain selected trained forecasts, model evaluation and baseline assumptions; guide Forecasting."
)
SYSTEM_PROMPT = (
    "Read the selected model's numerical family, saved feature recipe and notes. Optional causal trend/volatility context does not establish better future accuracy. "
    "Portable imported models are locally refitted research with unverified source origin, never prospective live evidence. Archived models keep saved evidence and existing outcome monitors; they must be restored for new forecasts. Use page_help models/portability for library controls. "
    "Use forecast_outcomes for live prospective scorecards, distinct from historical held-out or rolling evaluations. Missing future or archived targets remain missing; repeated horizon errors and selected forecast runs do not establish reliable future accuracy. "
    "Use rolling_evaluation to inspect selected saved rolling reports or list evaluations for a model. These refit a fixed recipe over earlier windows; they do not evaluate the original saved weights. Disclose per-fold variation, pooled benchmark skill, overlapping targets and repeated-experiment limitations. Never claim a rolling run trained or deployed a production model. "
    "Use page_help for Forecasting controls and setup, forecast_method for conceptual methodology, "
    "and price_forecast for a selected trained result or baseline. Use trained_models and model_report "
    "to inspect registry versions, chronological evaluation, naive/drift benchmarks, calibration and data provenance. "
    "Ask for a model, symbol or horizon when ambiguous. Trained autoregressive ridge coefficients and "
    "the untrained drift baseline are distinct. Negative skill means the naive benchmark performed better. "
    "Bands and input-shift checks provide research evidence, not guaranteed coverage, calibrated regime detection "
    "or profitable trade probabilities. You can read model evidence but cannot train, refit or save forecasts. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Chronos's tools and expose them through ProtoLink's runtime transport."""
    market = services.market

    def price_forecast(
        symbol: str | None = None,
        horizon: Annotated[int | None, Field(ge=1, le=30)] = None,
        model_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
    ) -> dict:
        """Read the page's saved trained forecast, or calculate its selected statistical baseline.

        Omit symbol and horizon to use the Forecasting page selection (otherwise
        BTC/USDT and 14 days). Supply an exact BASE/QUOTE pair for another market.
        Supply model_id from trained_models to choose a saved version outside this page.
        Returns the path, last price, source and relevant uncertainty evidence.
        When a trained model is selected, returns that version's retained result or an
        offline calculation from its frozen input, with empirical bands and provenance.
        Otherwise uses the untrained log-return baseline and theoretical interval.
        """
        explicit_model = model_id is not None
        identity = selected("forecast_model_id", model_id)
        if identity:
            if not services.forecasts:
                raise ValueError("Trained forecasting is unavailable in this workspace.")
            try:
                model = services.forecasts.detail(identity)["model"]
            except LookupError as exc:
                raise ToolRejectedError(
                    "That trained model version is not retained in this workspace.",
                    code="forecast_model_not_found",
                    suggestion="Call trained_models() to find saved versions, or explain that the selected version is missing. Never silently replace it with the untrained baseline.",
                ) from exc
            symbol = symbol or (
                model["symbol"] if explicit_model else selected("symbol", None, model["symbol"])
            )
            horizon = horizon or (
                min(14, model["parameters"]["max_horizon"])
                if explicit_model
                else selected("horizon", None, min(14, model["parameters"]["max_horizon"]))
            )
            if symbol != model["symbol"]:
                raise ValueError("The selected trained model uses a different market. Choose its exact pair.")
            run_id = (
                selected("forecast_run_id", None)
                if not explicit_model or identity == selected("forecast_model_id", None)
                else None
            )
            return services.forecasts.preview(identity, horizon, run_id=run_id)
        symbol = selected("symbol", symbol, "BTC/USDT")
        horizon = selected("horizon", horizon, 14)
        if not 1 <= horizon <= 30:
            raise ValueError("Forecast horizon must be between 1 and 30 days.")
        with market.snapshot(selected("market_source", None, None)):
            return {
                "symbol": symbol,
                "source": market.source,
                **forecast(market.candles(symbol, 180), horizon),
            }

    def forecast_outcomes(model_id: str | None = None, run_id: str | None = None) -> dict:
        """Compare saved prospective forecasts with later observed prices from their exact source.

        Follow the selected trained model/run when IDs are omitted. With a model only,
        return up to 20 compact tracked-output summaries and equal-horizon aggregates; with a run, inspect original
        predictions, actuals, correction versions, missing targets and naïve/drift benchmarks.
        Historical saved-input and Demo forecasts cannot establish live performance.
        Overlapping/operator-selected forecasts are not an unbiased accuracy leaderboard.
        This tool never refreshes prices, starts tracking, retrains or deploys a model.
        """
        identity = selected("forecast_model_id", model_id)
        run = selected("forecast_run_id", run_id) if model_id is None else run_id
        if not services.forecasts or not identity:
            raise ToolRejectedError("Select a trained model first.", code="forecast_model_required")
        try:
            result = (
                services.forecasts.forward.detail(run) if run else services.forecasts.forward.list(identity)
            )
        except LookupError as exc:
            raise ToolRejectedError(
                "That tracked forecast is not retained.",
                code="forecast_tracking_not_found",
                suggestion="Read the model's tracking list for current IDs.",
            ) from exc
        if run and result["model_id"] != identity:
            raise ToolRejectedError(
                "This tracked output belongs to another model.", code="forecast_tracking_not_found"
            )
        if not run:
            all_items = result["items"]
            result = {
                **result,
                "total": len(all_items),
                "limit": 20,
                "items": [
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "accepted_at",
                            "status",
                            "observed",
                            "pending",
                            "metrics",
                            "naive",
                            "coverage_pct",
                            "mae_skill_vs_naive_pct",
                        )
                    }
                    for item in all_items[:20]
                ],
            }
        return {"kind": "forecast_outcomes", **result, "url": f"/forecast?tab=models&model={identity}"}

    def forecast_method() -> dict:
        """Explain trained autoregressive forecasts and the separate statistical baseline.

        Use for questions about forecast methodology or whether a model has been
        trained. Returns the implemented assumptions and calibration limitations.
        """
        return {
            "method": "Trained direct autoregressive ridge or a small tanh neural network; the untrained log-return baseline is separate",
            "training": "Separate per-horizon ridge or neural models use frozen daily input, chronological 60/20/20 train/calibration/test partitions and purged boundary-crossing targets.",
            "trained_intervals": "Nominal 90% bands from calibration log errors; held-out coverage is reported and future coverage is not guaranteed.",
            "horizon_days": {"ridge": [1, 30], "small_neural": [1, 14]},
            "baseline_intervals": "Approximate 95% theoretical bands from constant historical drift/volatility, without empirical calibration.",
            "interpretation": "Neither model's bands are probabilities of profitable trades.",
        }

    def trained_models(include_archived: bool = False) -> dict:
        """List saved Chronos model versions, their exact markets, datasets and training settings.

        Use to find a model ID before inspecting its evaluation or a retained forecast.
        Set include_archived to find hidden retained versions. Imported versions carry
        unverified source labels even after local refitting. Returns the local registry only; does not train, fetch prices or select a model for the user.
        """
        rows = services.forecasts.list(include_archived)["items"] if services.forecasts else []
        return {
            "items": [
                {
                    key: row.get(key)
                    for key in (
                        "id",
                        "label",
                        "version",
                        "symbol",
                        "source",
                        "environment",
                        "parameters",
                        "archived",
                        "imported_from",
                    )
                }
                for row in rows[:20]
            ],
            "total": len(rows),
            "limit": 20,
        }

    def model_report(model_id: str | None = None) -> dict:
        """Inspect a trained model's test errors, naive/drift benchmarks and interval coverage.

        Omit model_id to use the Forecasting page selection. Returns dataset/source
        provenance, version, training/calibration/test dates, metrics and interpretation notes.
        """
        identity = selected("forecast_model_id", model_id)
        if not identity or not services.forecasts:
            raise ToolRejectedError(
                "No trained model is selected.",
                code="forecast_model_required",
                suggestion="Use trained_models() for saved versions or guide the user to Forecasting. An empty registry is not a trained forecast.",
            )
        try:
            report = services.forecasts.detail(identity)
        except LookupError as exc:
            raise ToolRejectedError(
                "That trained model version is not retained in this workspace.",
                code="forecast_model_not_found",
                suggestion="Use trained_models() for current model IDs; do not invent a version or substitute the baseline.",
            ) from exc
        return {key: value for key, value in report.items() if key not in {"test_trace", "outputs"}}

    def rolling_evaluation(
        model_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
        evaluation_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
    ) -> dict:
        """Read saved rolling forecast accuracy across successive historical test windows.

        Omit IDs to use the selected model/evaluation. With only a model, list its
        retained reports; supply an evaluation ID to inspect per-fold boundaries,
        errors, naive/drift comparisons, band coverage and input provenance. Each fold
        refits the saved recipe using earlier data; this evaluates the recipe rather
        than the original coefficients. Results are dated research, not live forward
        performance or investment returns. This tool cannot fit, rerun or deploy models.
        """
        identity = selected("forecast_model_id", model_id)
        report_id = evaluation_id or (
            selected("forecast_evaluation_id", None)
            if model_id is None or model_id == selected("forecast_model_id", None)
            else None
        )
        if not services.forecasts or not identity and not report_id:
            raise ToolRejectedError(
                "Choose a saved model or rolling evaluation first.",
                code="forecast_model_required",
                suggestion="Use trained_models() or open Forecasting → Trained models.",
            )
        try:
            if not report_id:
                return {
                    "kind": "rolling_evaluations",
                    "model_id": identity,
                    **services.forecasts.evaluations.list(identity),
                }
            report = services.forecasts.evaluations.detail(report_id)
        except LookupError as exc:
            raise ToolRejectedError(
                "That model or rolling evaluation is no longer retained.",
                code="forecast_evaluation_not_found",
                suggestion="List rolling_evaluation(model_id=...) for retained reports. Never substitute a different evaluation or baseline.",
            ) from exc
        if identity and report["model_id"] != identity:
            raise ToolRejectedError(
                "The evaluation belongs to a different model version.",
                code="forecast_evaluation_not_found",
                suggestion="Choose an evaluation retained for the selected model version.",
            )
        return {
            "kind": "rolling_evaluation",
            "report": {
                **services.forecasts.evaluations.header(report),
                "notes": report["result"]["notes"],
                "folds": [
                    {
                        "index": fold["index"],
                        "partitions": fold["partitions"],
                        "evaluation": {
                            key: value for key, value in fold["evaluation"].items() if key != "trace"
                        },
                    }
                    for fold in report["result"]["folds"]
                ],
            },
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Forecasting controls, input requirements, baseline intervals or model availability.

        Choose a topic for concrete instructions and an in-app link. Use overview for orientation.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-chronos",
        description=DESCRIPTION,
        tools=[
            price_forecast,
            forecast_method,
            page_help,
            trained_models,
            model_report,
            rolling_evaluation,
            forecast_outcomes,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
