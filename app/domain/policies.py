from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.entities import EvaluationSchema, RemoteIdentity
from app.domain.enums import AuthState, OverlayVisibility, RemoteRole, RuntimeMode, ScorePolarity


@dataclass(frozen=True, slots=True)
class ScoreValidationResult:
    valid: bool
    errors: list[str]


class ModePolicy:
    @staticmethod
    def status_badge(mode: RuntimeMode) -> str:
        return "LOCAL + SHARED" if mode is RuntimeMode.SHARED else "LOCAL ONLY"

    @staticmethod
    def shared_widgets_visible(mode: RuntimeMode) -> bool:
        return mode is RuntimeMode.SHARED

    @staticmethod
    def admin_widgets_visible(mode: RuntimeMode, remote_identity: RemoteIdentity) -> bool:
        return (
            mode is RuntimeMode.SHARED
            and remote_identity.remote_role is RemoteRole.ADMIN
            and remote_identity.auth_state is AuthState.AUTHENTICATED
        )


class SchemaPolicy:
    @staticmethod
    def is_locked(schema: EvaluationSchema) -> bool:
        return schema.is_official_shared_compatible

    @staticmethod
    def can_publish_to_shared(schema: EvaluationSchema) -> bool:
        return schema.is_official_shared_compatible and bool(schema.shared_compatibility.get("official", True))

    @staticmethod
    def validate_scores(schema: EvaluationSchema, scores: dict[str, Any]) -> ScoreValidationResult:
        errors: list[str] = []
        dimension_keys = {dimension.key for dimension in schema.dimensions}
        for dimension in schema.dimensions:
            if dimension.key not in scores:
                errors.append(f"{dimension.label} is required.")
                continue
            value = scores[dimension.key]
            if not isinstance(value, int | float):
                errors.append(f"{dimension.label} must be numeric.")
                continue
            if value < schema.score_range.minimum or value > schema.score_range.maximum:
                errors.append(
                    f"{dimension.label} must be between {schema.score_range.minimum} and {schema.score_range.maximum}."
                )
        for key in scores:
            if key not in dimension_keys:
                errors.append(f"Unknown score dimension: {key}.")
        return ScoreValidationResult(valid=not errors, errors=errors)

    @staticmethod
    def score_contributions(schema: EvaluationSchema, scores: dict[str, Any]) -> dict[str, float]:
        contributions: dict[str, float] = {}
        lower = schema.score_range.minimum
        upper = schema.score_range.maximum
        for dimension in schema.dimensions:
            value = scores.get(dimension.key)
            if not isinstance(value, int | float):
                continue
            polarity = getattr(dimension, "polarity", ScorePolarity.POSITIVE)
            if str(polarity) == ScorePolarity.NEGATIVE:
                contributions[dimension.key] = float(lower + upper - value)
            else:
                contributions[dimension.key] = float(value)
        return contributions

    @staticmethod
    def aggregate_quality_score(schema: EvaluationSchema, scores: dict[str, Any]) -> float | None:
        contributions = SchemaPolicy.score_contributions(schema, scores)
        total_weight = 0.0
        weighted_total = 0.0
        for dimension in schema.dimensions:
            if dimension.key not in contributions:
                continue
            weight = max(0.0, float(dimension.weight or 0))
            total_weight += weight
            weighted_total += contributions[dimension.key] * weight
        if total_weight <= 0:
            return None
        return round(weighted_total / total_weight, 2)

    @staticmethod
    def score_breakdown(schema: EvaluationSchema, scores: dict[str, Any]) -> dict[str, Any]:
        contributions = SchemaPolicy.score_contributions(schema, scores)
        return {
            "quality_score": SchemaPolicy.aggregate_quality_score(schema, scores),
            "contributions": contributions,
            "weights": {dimension.key: float(dimension.weight or 0) for dimension in schema.dimensions},
            "polarity": {dimension.key: str(getattr(dimension, "polarity", ScorePolarity.POSITIVE)) for dimension in schema.dimensions},
        }


class MergePolicy:
    @staticmethod
    def overlay_allowed(mode: RuntimeMode, visibility: OverlayVisibility) -> bool:
        return mode is RuntimeMode.SHARED and visibility is not OverlayVisibility.LOCAL_ONLY
