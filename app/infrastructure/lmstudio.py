from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.domain.entities import EvaluationSchema, Work, WorkEvaluationSample, WorkTag
from app.domain.enums import ScorePolarity
from app.domain.ports import SettingsRepository

DEFAULT_LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
DEFAULT_LMSTUDIO_MODEL = ""


class LMStudioEvaluationProvider:
    """OpenAI-compatible LM Studio adapter for local evaluator prompts."""

    def __init__(self, settings: SettingsRepository) -> None:
        self.settings = settings

    @property
    def base_url(self) -> str:
        value = str(self.settings.get("lmstudio_base_url", DEFAULT_LMSTUDIO_BASE_URL) or DEFAULT_LMSTUDIO_BASE_URL)
        return f"{self._server_root(value)}/v1"

    @property
    def native_base_url(self) -> str:
        value = str(self.settings.get("lmstudio_base_url", DEFAULT_LMSTUDIO_BASE_URL) or DEFAULT_LMSTUDIO_BASE_URL)
        return f"{self._server_root(value)}/api/v1"

    @property
    def model(self) -> str:
        return str(self.settings.get("lmstudio_model", DEFAULT_LMSTUDIO_MODEL) or DEFAULT_LMSTUDIO_MODEL)

    @property
    def timeout(self) -> float:
        try:
            return float(self.settings.get("lmstudio_timeout_seconds", 180))
        except (TypeError, ValueError):
            return 180.0

    @property
    def temperature(self) -> float:
        try:
            return float(self.settings.get("lmstudio_temperature", 0.2))
        except (TypeError, ValueError):
            return 0.2

    def available_models(self) -> list[str]:
        return [
            str(item.get("key") or item.get("id") or item.get("display_name"))
            for item in self.available_model_details()
            if item.get("key") or item.get("id") or item.get("display_name")
        ]

    def available_model_details(self) -> list[dict[str, Any]]:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.native_base_url}/models")
                response.raise_for_status()
                payload = response.json()
            models = payload.get("models")
            if isinstance(models, list):
                return [dict(item) for item in models if isinstance(item, dict)]
        except httpx.HTTPError:
            pass

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{self.base_url}/models")
            response.raise_for_status()
            payload = response.json()
        return [
            {
                "type": "llm",
                "key": str(item.get("id")),
                "display_name": str(item.get("id")),
                "loaded_instances": [],
            }
            for item in payload.get("data", [])
            if item.get("id")
        ]

    def loaded_instance_id(self, model: str) -> str | None:
        clean_model = str(model or "").strip()
        if not clean_model:
            return None
        for item in self.available_model_details():
            key = str(item.get("key") or item.get("id") or "")
            display_name = str(item.get("display_name") or "")
            if clean_model not in {key, display_name}:
                continue
            loaded = item.get("loaded_instances")
            if isinstance(loaded, list) and loaded:
                first = loaded[0]
                if isinstance(first, dict) and first.get("id"):
                    return str(first["id"])
        return None

    def load_model(self, model: str, context_length: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": str(model or "").strip(), "echo_load_config": True}
        if not payload["model"]:
            raise ValueError("Choose an LM Studio model in Settings first.")
        if context_length and int(context_length) > 0:
            payload["context_length"] = int(context_length)
        with httpx.Client(timeout=max(10.0, self.timeout)) as client:
            response = client.post(f"{self.native_base_url}/models/load", json=payload)
            response.raise_for_status()
            return dict(response.json())

    def unload_model(self, instance_id: str) -> dict[str, Any]:
        clean_id = str(instance_id or "").strip()
        if not clean_id:
            raise ValueError("No LM Studio model instance id was provided.")
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self.native_base_url}/models/unload", json={"instance_id": clean_id})
            response.raise_for_status()
            return dict(response.json())

    def evaluate_work(
        self,
        *,
        work: Work,
        tags: list[WorkTag],
        schema: EvaluationSchema,
        prompt_template: str,
    ) -> dict[str, Any]:
        model = self.model
        if not model:
            raise ValueError("Choose an LM Studio model in Settings first.")
        payload = {
            "model": model,
            "messages": self._messages(work, tags, schema, prompt_template),
            "response_format": self._response_format(schema),
            "temperature": self.temperature,
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        result["model_name"] = model
        return result

    def evaluate_sampled_work(
        self,
        *,
        work: Work,
        tags: list[WorkTag],
        schema: EvaluationSchema,
        prompt_template: str,
        sample: WorkEvaluationSample,
    ) -> dict[str, Any]:
        model = self.model
        if not model:
            raise ValueError("Choose an LM Studio model in Settings first.")
        payload = {
            "model": model,
            "messages": self._sampled_messages(work, tags, schema, prompt_template, sample),
            "response_format": self._response_format(schema),
            "temperature": self.temperature,
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        result["model_name"] = model
        return result

    @staticmethod
    def _messages(
        work: Work,
        tags: list[WorkTag],
        schema: EvaluationSchema,
        prompt_template: str,
    ) -> list[dict[str, str]]:
        dimensions = "\n".join(
            LMStudioEvaluationProvider._dimension_instruction(dimension)
            for dimension in schema.dimensions
        )
        tag_lines = "\n".join(f"- {tag.tag_type.value}: {tag.tag_text}" for tag in tags[:120])
        work_context = {
            "work_id": work.work_id,
            "title": work.title,
            "author_name": work.author_name,
            "author_url": work.author_url,
            "rating": work.rating,
            "language": work.language,
            "words": work.words,
            "chapters_current": work.chapters_current,
            "chapters_total": work.chapters_total_text,
            "kudos": work.kudos,
            "bookmarks": work.bookmarks,
            "hits": work.hits,
            "comments": work.comments,
            "summary_text": work.summary_text,
        }
        system = (
            "You are AO3 Studio's private evaluator. Return only valid JSON matching the schema. "
            "Scores are personal reading/evaluation metadata, not public moderation. "
            "Every included dimension must receive an integer score from 1 to 10 unless the supplied schema says otherwise. "
            "Positive dimensions score how well the work succeeds. Negative dimensions score how strongly the flaw is present."
        )
        user = (
            f"{prompt_template.strip() or 'Evaluate this work for the local reading database.'}\n\n"
            f"Schema: {schema.name} v{schema.version}\n"
            f"Score dimensions:\n{dimensions}\n\n"
            f"Work metadata JSON:\n{json.dumps(work_context, ensure_ascii=False, indent=2)}\n\n"
            f"Tags:\n{tag_lines or 'No tags cached.'}\n\n"
            "Return a concise notes_markdown string, evidence object, and scores object keyed exactly by dimension key. "
            "Do not invert negative scores yourself; AO3 Studio handles polarity-aware aggregate math after you return raw scores. "
            "If you include author-level observations, put them under evidence.author."
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    @staticmethod
    def _sampled_messages(
        work: Work,
        tags: list[WorkTag],
        schema: EvaluationSchema,
        prompt_template: str,
        sample: WorkEvaluationSample,
    ) -> list[dict[str, str]]:
        dimensions = "\n".join(
            LMStudioEvaluationProvider._dimension_instruction(dimension)
            for dimension in schema.dimensions
        )
        tag_lines = "\n".join(sample.tags or [f"{tag.tag_type.value}: {tag.tag_text}" for tag in tags[:120]])
        system = (
            "You are AO3 Studio's private evaluator. Return only valid JSON matching the schema. "
            "Scores are personal reading/evaluation metadata, not public moderation. "
            "Every included dimension must receive an integer score from 1 to 10 unless the supplied schema says otherwise. "
            "Positive dimensions score how well the work succeeds. Negative dimensions score how strongly the flaw is present. "
            "Evaluate only from the supplied local sample and metadata; do not invent details outside that context."
        )
        user = (
            f"{prompt_template.strip() or 'Evaluate this AO3 work sample for the local reading database.'}\n\n"
            f"Schema: {schema.name} v{schema.version}\n"
            f"Score dimensions:\n{dimensions}\n\n"
            "AO3 Studio JSON contract: return scores, notes_markdown, evidence, and optional subscores only. "
            "The scores object must be keyed exactly by dimension key. Do not invert negative scores yourself; "
            "AO3 Studio handles polarity-aware aggregate math after you return raw scores.\n\n"
            f"Work metadata JSON:\n{json.dumps(sample.metadata, ensure_ascii=False, indent=2)}\n\n"
            f"Tags:\n{tag_lines or 'Tags intentionally omitted.'}\n\n"
            f"Sample provenance JSON:\n{json.dumps(sample.chapter_scope, ensure_ascii=False, indent=2)}\n\n"
            "Work sample text:\n"
            f"{sample.text.strip()}\n\n"
            "Return concise notes_markdown, evidence object, and scores object."
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    @staticmethod
    def _dimension_instruction(dimension) -> str:
        try:
            polarity = ScorePolarity(str(getattr(dimension, "polarity", ScorePolarity.POSITIVE)))
        except ValueError:
            polarity = ScorePolarity.POSITIVE
        if polarity is ScorePolarity.NEGATIVE:
            framing = "negative framing: 1 means the flaw is absent or minor; 10 means the flaw is strongly present and hurts quality"
        else:
            framing = "positive framing: 1 means poor fit; 10 means this criterion is met extremely well"
        return (
            f"- {dimension.key}: {dimension.label}. polarity={polarity.value}; impact={float(dimension.weight or 1):g}x; "
            f"{framing}. {dimension.description}"
        ).strip()

    @staticmethod
    def _response_format(schema: EvaluationSchema) -> dict[str, Any]:
        score_properties = {
            dimension.key: {
                "type": "integer",
                "minimum": schema.score_range.minimum,
                "maximum": schema.score_range.maximum,
                "description": dimension.label,
            }
            for dimension in schema.dimensions
        }
        required_scores = [dimension.key for dimension in schema.dimensions]
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "ao3_studio_evaluation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "scores": {
                            "type": "object",
                            "properties": score_properties,
                            "required": required_scores,
                            "additionalProperties": False,
                        },
                        "subscores": {"type": "object", "additionalProperties": True},
                        "notes_markdown": {"type": "string"},
                        "evidence": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["scores", "notes_markdown", "evidence"],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _server_root(value: str) -> str:
        clean = str(value or DEFAULT_LMSTUDIO_BASE_URL).strip().rstrip("/")
        parsed = urlparse(clean)
        path = parsed.path.rstrip("/")
        for suffix in ("/api/v1", "/v1"):
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break
        return urlunparse(parsed._replace(path=path, params="", query="", fragment="")).rstrip("/")
