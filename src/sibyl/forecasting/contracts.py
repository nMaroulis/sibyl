"""Bounded requests for explicit Chronos research; no training runs at startup."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from sibyl.models import Request


class TrainForecast(Request):
    """Fit one reproducible daily model from a frozen dataset or one current feed page."""

    label: str = Field(default="Daily autoregression", min_length=1, max_length=80)
    input_kind: Literal["current_feed", "saved_dataset", "demo"] = "current_feed"
    dataset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    symbol: str = Field(default="BTC/USDT", pattern=r"^[A-Z0-9]{1,12}/[A-Z0-9]{1,12}$")
    candles: int = Field(default=720, ge=360, le=5000, strict=True)
    lags: Literal[5, 14, 30] = 14
    feature_set: Literal["returns", "returns_context"] = "returns"
    max_horizon: int = Field(default=30, ge=1, le=30, strict=True)
    alpha: float = Field(default=1.0, ge=0.01, le=1000, strict=True)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value):
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a non-empty model label without control characters.")
        return value.strip()

    @model_validator(mode="after")
    def input_selection(self):
        if (self.input_kind == "saved_dataset") != (self.dataset_id is not None):
            raise ValueError("Provide a dataset ID only for saved-dataset training.")
        if self.input_kind != "saved_dataset" and self.candles > 720:
            raise ValueError(
                "Current and Demo pages support at most 720 candles. Use a saved dataset for more."
            )
        return self


class ForecastRequest(Request):
    """Produce and retain a forecast without refitting its immutable model."""

    input_kind: Literal["saved_input", "current_feed"] = "saved_input"
    horizon: int = Field(default=14, ge=1, le=30, strict=True)


class RollingEvaluationRequest(Request):
    """Refit a fixed saved recipe across bounded successive historical test blocks."""

    horizon: int = Field(default=7, ge=1, le=30, strict=True)
    folds: int = Field(default=2, ge=2, le=8, strict=True)
    test_days: int = Field(default=60, ge=21, le=180, strict=True)
    calibration_days: int = Field(default=60, ge=21, le=365, strict=True)
    window: Literal["expanding", "rolling"] = "expanding"
    training_days: int | None = Field(default=None, ge=120, le=2000, strict=True)

    @model_validator(mode="after")
    def fixed_window(self):
        if (self.window == "rolling") != (self.training_days is not None):
            raise ValueError("Supply training_days only for a fixed rolling window.")
        return self


class ArchiveModel(Request):
    """Organize the registry; retained outputs and outcome monitors remain separate."""

    archived: bool
    revision: int = Field(default=0, ge=0, strict=True)
