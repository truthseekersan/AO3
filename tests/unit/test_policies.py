from __future__ import annotations

from app.domain.entities import EvaluationSchema, RemoteIdentity, ScoreDimension
from app.domain.enums import AuthState, RemoteRole, RuntimeMode, ScorePolarity
from app.domain.policies import ModePolicy, SchemaPolicy


def test_mode_policy_gates_admin_to_shared_authenticated_admin() -> None:
    remote = RemoteIdentity(remote_role=RemoteRole.ADMIN, auth_state=AuthState.AUTHENTICATED)

    assert ModePolicy.admin_widgets_visible(RuntimeMode.SHARED, remote)
    assert not ModePolicy.admin_widgets_visible(RuntimeMode.LOCAL, remote)


def test_schema_policy_validates_one_to_ten_scores() -> None:
    schema = EvaluationSchema(
        schema_key="s",
        name="S",
        version="1",
        label="S",
        description="",
        dimensions=[ScoreDimension("craft", "Craft")],
    )

    assert SchemaPolicy.validate_scores(schema, {"craft": 8}).valid
    result = SchemaPolicy.validate_scores(schema, {"craft": 11})
    assert not result.valid
    assert "Craft" in result.errors[0]


def test_schema_policy_inverts_negative_polarity_for_quality_score() -> None:
    schema = EvaluationSchema(
        schema_key="s",
        name="S",
        version="1",
        label="S",
        description="",
        dimensions=[
            ScoreDimension("meaningful_moments", "Meaningful Moments", weight=1.0, polarity=ScorePolarity.POSITIVE),
            ScoreDimension("purple_prose", "Purple Prose", weight=1.0, polarity=ScorePolarity.NEGATIVE),
        ],
    )

    assert SchemaPolicy.score_contributions(schema, {"meaningful_moments": 9, "purple_prose": 8}) == {
        "meaningful_moments": 9.0,
        "purple_prose": 3.0,
    }
    assert SchemaPolicy.aggregate_quality_score(schema, {"meaningful_moments": 9, "purple_prose": 8}) == 6.0


def test_schema_policy_uses_weighted_quality_average() -> None:
    schema = EvaluationSchema(
        schema_key="s",
        name="S",
        version="1",
        label="S",
        description="",
        dimensions=[
            ScoreDimension("craft", "Craft", weight=2.0, polarity=ScorePolarity.POSITIVE),
            ScoreDimension("purple_prose", "Purple Prose", weight=1.0, polarity=ScorePolarity.NEGATIVE),
        ],
    )

    assert SchemaPolicy.aggregate_quality_score(schema, {"craft": 10, "purple_prose": 10}) == 7.0
