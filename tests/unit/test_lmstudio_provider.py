from __future__ import annotations

import json

import httpx

from app.domain.entities import EvaluationSchema, ScoreDimension, Work, WorkEvaluationSample
from app.domain.enums import ScorePolarity
from app.infrastructure.lmstudio import LMStudioEvaluationProvider


class Settings:
    def __init__(self) -> None:
        self.values = {
            "lmstudio_base_url": "http://localhost:1234/v1",
            "lmstudio_model": "gemma-4-26b-local",
            "lmstudio_timeout_seconds": 30,
            "lmstudio_temperature": 0.2,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def test_lmstudio_payload_uses_chat_completions_json_schema(monkeypatch) -> None:
    captured = {}

    def fake_post(self, url, json):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"scores":{"craft":9},"notes_markdown":"Strong.","evidence":{"author":{"name":"example"}}}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    provider = LMStudioEvaluationProvider(Settings())
    result = provider.evaluate_work(
        work=Work(
            work_id="12345",
            ao3_url="https://archiveofourown.org/works/12345",
            title="A Useful Work",
            author_name="example",
        ),
        tags=[],
        schema=EvaluationSchema(
            schema_key="s",
            name="Schema",
            version="1",
            label="Schema",
            description="",
            dimensions=[ScoreDimension("craft", "Craft", polarity=ScorePolarity.POSITIVE)],
        ),
        prompt_template="Custom evaluator prompt.",
    )

    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["json"]["model"] == "gemma-4-26b-local"
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert captured["json"]["response_format"]["json_schema"]["schema"]["properties"]["scores"]["required"] == ["craft"]
    assert "polarity=positive" in captured["json"]["messages"][1]["content"]
    assert json.loads(captured["json"]["messages"][1]["content"].split("Work metadata JSON:\n")[1].split("\n\nTags:")[0])[
        "author_name"
    ] == "example"
    assert result["scores"]["craft"] == 9


def test_lmstudio_payload_explains_negative_polarity(monkeypatch) -> None:
    captured = {}

    def fake_post(self, url, json):
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"scores":{"purple_prose":8},"notes_markdown":"Dense.","evidence":{}}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    provider = LMStudioEvaluationProvider(Settings())
    provider.evaluate_work(
        work=Work(work_id="12345", ao3_url="https://archiveofourown.org/works/12345", title="A Useful Work"),
        tags=[],
        schema=EvaluationSchema(
            schema_key="s",
            name="Schema",
            version="1",
            label="Schema",
            description="",
            dimensions=[ScoreDimension("purple_prose", "Purple Prose", polarity=ScorePolarity.NEGATIVE)],
        ),
        prompt_template="Custom evaluator prompt.",
    )

    prompt = captured["json"]["messages"][1]["content"]
    assert "polarity=negative" in prompt
    assert "Do not invert negative scores yourself" in prompt


def test_lmstudio_native_model_management_uses_v1_api(monkeypatch) -> None:
    captured = {"posts": []}

    def fake_get(self, url):
        captured["get"] = url
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "models": [
                    {
                        "type": "llm",
                        "key": "gemma-local",
                        "display_name": "Gemma Local",
                        "loaded_instances": [{"id": "gemma-loaded"}],
                    }
                ]
            },
        )

    def fake_post(self, url, json):
        captured["posts"].append((url, json))
        if url.endswith("/models/load"):
            return httpx.Response(200, request=httpx.Request("POST", url), json={"instance_id": "gemma-loaded", "status": "loaded"})
        return httpx.Response(200, request=httpx.Request("POST", url), json={"instance_id": json["instance_id"]})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(httpx.Client, "post", fake_post)

    provider = LMStudioEvaluationProvider(Settings())

    assert provider.available_models() == ["gemma-local"]
    assert captured["get"] == "http://localhost:1234/api/v1/models"
    assert provider.loaded_instance_id("gemma-local") == "gemma-loaded"
    assert provider.load_model("gemma-local", 8192)["status"] == "loaded"
    assert provider.unload_model("gemma-loaded")["instance_id"] == "gemma-loaded"
    assert captured["posts"][0] == (
        "http://localhost:1234/api/v1/models/load",
        {"model": "gemma-local", "echo_load_config": True, "context_length": 8192},
    )
    assert captured["posts"][1] == (
        "http://localhost:1234/api/v1/models/unload",
        {"instance_id": "gemma-loaded"},
    )


def test_lmstudio_sampled_payload_contains_contract_and_sample(monkeypatch) -> None:
    captured = {}

    def fake_post(self, url, json):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"scores":{"craft":8},"notes_markdown":"Useful sample.","evidence":{"sample":"chapter 4"}}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    provider = LMStudioEvaluationProvider(Settings())
    sample = WorkEvaluationSample(
        text="Chapter 4 text with enough detail to evaluate.",
        metadata={"work_id": "12345", "title": "A Useful Work"},
        tags=["- fandom: Example"],
        chapter_scope={"actual_start_chapter": 4, "sampled_words": 8},
    )

    result = provider.evaluate_sampled_work(
        work=Work(
            work_id="12345",
            ao3_url="https://archiveofourown.org/works/12345",
            title="A Useful Work",
            author_name="example",
        ),
        tags=[],
        schema=EvaluationSchema(
            schema_key="s",
            name="Schema",
            version="1",
            label="Schema",
            description="",
            dimensions=[ScoreDimension("craft", "Craft", polarity=ScorePolarity.POSITIVE)],
        ),
        prompt_template="Custom evaluator prompt.",
        sample=sample,
    )

    prompt = captured["json"]["messages"][1]["content"]
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert "AO3 Studio JSON contract" in prompt
    assert "Work sample text:" in prompt
    assert "Chapter 4 text" in prompt
    assert '"actual_start_chapter": 4' in prompt
    assert result["scores"]["craft"] == 8
