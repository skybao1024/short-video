import json
import logging
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Dict, List

import httpx

from app.core.config import settings
from app.services.client.video_providers import (
    VEO_ALLOWED_DURATION_SECONDS,
    normalize_veo_duration_seconds,
)

logger = logging.getLogger(__name__)

MIN_SCENE_DURATION_SECONDS = 3
MAX_SCENE_DURATION_SECONDS = 15
DEFAULT_SCENE_COUNT = 3
MAX_SCENE_COUNT = 10
OPENAI_STORYBOARD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["expanded_brief", "scenes"],
    "properties": {
        "expanded_brief": {
            "type": "string",
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "scene_index",
                    "scene_role",
                    "title",
                    "prompt_text",
                    "narration_text",
                    "sound_design",
                    "duration_seconds",
                    "input_asset_ids",
                ],
                "properties": {
                    "scene_index": {"type": "integer"},
                    "scene_role": {"type": "string"},
                    "title": {"type": "string"},
                    "prompt_text": {
                        "type": "string",
                    },
                    "narration_text": {"type": "string"},
                    "sound_design": {"type": "string"},
                    "duration_seconds": {"type": "integer"},
                    "input_asset_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
    },
}


@dataclass
class PlannedVideoScene:
    """Template-planned storyboard scene."""

    scene_index: int
    scene_role: str
    title: str
    prompt_text: str
    narration_text: str
    sound_design: str
    duration_seconds: int
    input_asset_ids: List[int] = field(default_factory=list)


@dataclass
class PlannedVideoStoryboard:
    """Template-planned storyboard."""

    expanded_brief: str
    scenes: List[PlannedVideoScene]


class StoryboardPlanningError(Exception):
    """Raised when AI storyboard planning cannot produce a valid plan."""


class OpenAIStoryboardPlanningClient:
    """Generate storyboard plans with the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        timeout_seconds: int = None,
        transport: Any = None,
    ):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.base_url = (base_url or settings.OPENAI_API_BASE_URL).rstrip("/")
        self.model = model or settings.OPENAI_STORYBOARD_MODEL
        self.timeout_seconds = (
            timeout_seconds or settings.OPENAI_STORYBOARD_TIMEOUT_SECONDS
        )
        self.transport = transport

    def is_configured(self) -> bool:
        """Return whether OpenAI storyboard planning can be attempted."""
        return bool(self.api_key and self.model and self.base_url)

    async def plan_storyboard(
        self,
        prompt: str,
        target_duration_seconds: int,
        aspect_ratio: str,
        has_images: bool,
        duration_plan_seconds: List[int],
        provider: str = None,
        model: str = None,
        resolution: str = "720p",
        image_assets: List[Dict[str, Any]] = None,
    ) -> PlannedVideoStoryboard:
        """Create a structured storyboard plan through OpenAI."""
        if not self.is_configured():
            raise StoryboardPlanningError(
                "OpenAI storyboard planning is not configured"
            )

        payload = self._build_request_payload(
            prompt=prompt,
            target_duration_seconds=target_duration_seconds,
            aspect_ratio=aspect_ratio,
            has_images=has_images,
            duration_plan_seconds=duration_plan_seconds,
            provider=provider,
            model=model,
            resolution=resolution,
            image_assets=image_assets or [],
        )
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers=self._headers(),
                json=payload,
            )
        if response.status_code >= 400:
            raise StoryboardPlanningError(self._safe_error_message(response))

        response_text = self._extract_response_text(response.json())
        raw_plan = self._decode_response_text(response_text)
        return self._build_storyboard_from_response(
            raw_plan=raw_plan,
            fallback_prompt=prompt,
            fallback_duration_plan=duration_plan_seconds,
            available_asset_ids=[
                int(asset["asset_id"])
                for asset in image_assets or []
                if isinstance(asset, dict) and asset.get("asset_id") is not None
            ],
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_request_payload(
        self,
        prompt: str,
        target_duration_seconds: int,
        aspect_ratio: str,
        has_images: bool,
        duration_plan_seconds: List[int],
        provider: str = None,
        model: str = None,
        resolution: str = "720p",
        image_assets: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        system_prompt = (
            "You are a senior short-form commercial video director. "
            "Create practical storyboards for AI video generation providers. "
            "Each scene must be visually concrete, commercially usable, and "
            "safe for provider generation. Avoid readable text overlays, "
            "watermarks, UI text, and unsupported claims. Keep prompt_text in "
            "English. Keep narration_text in the same language as the user "
            "brief. Return only the structured output."
        )
        user_payload = {
            "campaign_prompt": prompt,
            "target_duration_seconds": target_duration_seconds,
            "provider": provider,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "has_input_images": has_images,
            "image_assets": image_assets or [],
            "scene_count": len(duration_plan_seconds),
            "duration_plan_seconds": duration_plan_seconds,
            "scene_duration_limits_seconds": {
                "min": MIN_SCENE_DURATION_SECONDS,
                "max": MAX_SCENE_DURATION_SECONDS,
            },
            "requirements": [
                "Use one scene per duration in duration_plan_seconds.",
                "Treat duration_plan_seconds as authoritative and do not invent other scene durations.",
                "Make scene_index start at 1 and increase sequentially.",
                "Use concise scene_role labels such as hook, value, proof, cta.",
                "If images are present, treat them as the main product or brand reference.",
                "If image_assets is non-empty, choose 1 to 3 input_asset_ids per scene from those asset IDs.",
                "Choose image references that best match the visual content and scene role; do not always reuse the same images.",
                "Make each prompt_text strong enough to send directly to Runway or Veo.",
                "Design clear continuity from opening hook to final action.",
            ],
        }
        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(user_payload, ensure_ascii=False),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "video_storyboard_plan",
                    "strict": True,
                    "schema": OPENAI_STORYBOARD_SCHEMA,
                },
                "verbosity": "low",
            },
        }

    def _extract_response_text(self, response_data: Dict[str, Any]) -> str:
        output_text = response_data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        for output_item in response_data.get("output") or []:
            if not isinstance(output_item, dict):
                continue
            for content_item in output_item.get("content") or []:
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") not in {"output_text", "text"}:
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text.strip():
                    return text

        raise StoryboardPlanningError("OpenAI response did not include output text")

    def _decode_response_text(self, response_text: str) -> Dict[str, Any]:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise StoryboardPlanningError(
                "OpenAI storyboard response was not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise StoryboardPlanningError(
                "OpenAI storyboard response must be a JSON object"
            )
        return data

    def _build_storyboard_from_response(
        self,
        raw_plan: Dict[str, Any],
        fallback_prompt: str,
        fallback_duration_plan: List[int],
        available_asset_ids: List[int] = None,
    ) -> PlannedVideoStoryboard:
        raw_scenes = raw_plan.get("scenes")
        if not isinstance(raw_scenes, list) or not raw_scenes:
            raise StoryboardPlanningError("OpenAI storyboard response has no scenes")

        duration_plan = fallback_duration_plan[:MAX_SCENE_COUNT]
        available_asset_ids = list(dict.fromkeys(available_asset_ids or []))
        raw_scenes = raw_scenes[: len(duration_plan)]
        if len(raw_scenes) != len(duration_plan):
            raise StoryboardPlanningError(
                "OpenAI storyboard scene count did not match duration plan"
            )

        scenes = [
            self._build_scene_from_response(
                scene_data=scene_data,
                scene_index=index,
                duration_seconds=duration,
                fallback_prompt=fallback_prompt,
                available_asset_ids=available_asset_ids,
            )
            for index, (scene_data, duration) in enumerate(
                zip(raw_scenes, duration_plan), start=1
            )
        ]
        expanded_brief = self._clean_text(
            raw_plan.get("expanded_brief"),
            fallback=(
                "Create a concise promotional short video for: " f"{fallback_prompt}."
            ),
            max_length=4000,
        )
        return PlannedVideoStoryboard(expanded_brief=expanded_brief, scenes=scenes)

    def _build_scene_from_response(
        self,
        scene_data: Any,
        scene_index: int,
        duration_seconds: int,
        fallback_prompt: str,
        available_asset_ids: List[int] = None,
    ) -> PlannedVideoScene:
        if not isinstance(scene_data, dict):
            raise StoryboardPlanningError("OpenAI storyboard scene must be an object")

        scene_role = self._clean_text(
            scene_data.get("scene_role"), fallback="scene", max_length=40
        )
        title = self._clean_text(
            scene_data.get("title"),
            fallback=f"Scene {scene_index}",
            max_length=255,
        )
        prompt_text = self._clean_text(
            scene_data.get("prompt_text"),
            fallback=f"Create a polished commercial shot for: {fallback_prompt}.",
            max_length=4000,
        )
        if len(prompt_text) < 8:
            raise StoryboardPlanningError("OpenAI storyboard scene prompt is too short")
        input_asset_ids = self._clean_asset_ids(
            scene_data.get("input_asset_ids"),
            available_asset_ids=available_asset_ids or [],
        )

        return PlannedVideoScene(
            scene_index=scene_index,
            scene_role=scene_role,
            title=title,
            prompt_text=prompt_text,
            narration_text=self._clean_text(
                scene_data.get("narration_text"), fallback="", max_length=2000
            ),
            sound_design=self._clean_text(
                scene_data.get("sound_design"), fallback="", max_length=1000
            ),
            duration_seconds=max(
                MIN_SCENE_DURATION_SECONDS,
                min(int(duration_seconds), MAX_SCENE_DURATION_SECONDS),
            ),
            input_asset_ids=input_asset_ids,
        )

    def _clean_asset_ids(
        self, value: Any, available_asset_ids: List[int], max_items: int = 3
    ) -> List[int]:
        if not available_asset_ids:
            return []
        available = set(available_asset_ids)
        result = []
        if isinstance(value, list):
            for item in value:
                try:
                    asset_id = int(item)
                except (TypeError, ValueError):
                    continue
                if asset_id not in available or asset_id in result:
                    continue
                result.append(asset_id)
                if len(result) >= max_items:
                    break
        return result or available_asset_ids[:max_items]

    def _clean_text(self, value: Any, fallback: str, max_length: int) -> str:
        text = value if isinstance(value, str) else fallback
        normalized = " ".join(text.split())
        if not normalized:
            normalized = fallback
        return normalized[:max_length]

    def _safe_error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return "OpenAI storyboard request failed"
        error = data.get("error") or {}
        if isinstance(error, dict):
            return error.get("message") or "OpenAI storyboard request failed"
        if isinstance(error, str):
            return error
        return data.get("message") or "OpenAI storyboard request failed"


class PromptPlanningService:
    """Plan a short promotional video storyboard from a user brief."""

    def __init__(self, ai_planning_client: OpenAIStoryboardPlanningClient = None):
        self.ai_planning_client = (
            ai_planning_client or get_openai_storyboard_planning_client()
        )

    async def plan_storyboard(
        self,
        prompt: str,
        target_duration_seconds: int = 24,
        aspect_ratio: str = "9:16",
        has_images: bool = False,
        provider: str = None,
        model: str = None,
        resolution: str = "720p",
        image_assets: List[Dict[str, Any]] = None,
    ) -> PlannedVideoStoryboard:
        """Create a provider-safe promotional storyboard."""
        fallback_storyboard = self.plan_template_storyboard(
            prompt=prompt,
            target_duration_seconds=target_duration_seconds,
            aspect_ratio=aspect_ratio,
            has_images=has_images,
            provider=provider,
            resolution=resolution,
        )
        if not self.ai_planning_client.is_configured():
            raise StoryboardPlanningError(
                "OpenAI storyboard planning is not configured. "
                "Set OPENAI_API_KEY for the backend service."
            )

        try:
            return await self.ai_planning_client.plan_storyboard(
                prompt=prompt,
                target_duration_seconds=target_duration_seconds,
                aspect_ratio=aspect_ratio,
                has_images=has_images,
                duration_plan_seconds=[
                    scene.duration_seconds for scene in fallback_storyboard.scenes
                ],
                provider=provider,
                model=model,
                resolution=resolution,
                image_assets=image_assets or [],
            )
        except StoryboardPlanningError:
            logger.exception("OpenAI storyboard planning failed")
            raise
        except httpx.HTTPError as exc:
            logger.exception("OpenAI storyboard planning request failed")
            raise StoryboardPlanningError(
                "OpenAI storyboard planning request failed"
            ) from exc

    def plan_template_storyboard(
        self,
        prompt: str,
        target_duration_seconds: int = 24,
        aspect_ratio: str = "9:16",
        has_images: bool = False,
        provider: str = None,
        resolution: str = "720p",
    ) -> PlannedVideoStoryboard:
        """Create a provider-safe promotional storyboard from local templates."""
        visual_anchor = (
            "Use the provided product or brand image as the main visual reference."
            if has_images
            else "Create original commercial visuals that match the product brief."
        )
        expanded_brief = (
            f"Create a concise promotional short video for: {prompt}. "
            f"The video should feel premium, trustworthy, and conversion-oriented. "
            f"Use a vertical-first composition when aspect ratio is {aspect_ratio}. "
            f"{visual_anchor}"
        )

        durations = self._duration_plan(
            target_duration_seconds=target_duration_seconds,
            provider=provider,
            resolution=resolution,
            has_images=has_images,
        )
        scene_templates = self._scene_templates(prompt, visual_anchor, len(durations))
        scenes = [
            PlannedVideoScene(
                scene_index=index,
                scene_role=template["scene_role"],
                title=template["title"],
                prompt_text=template["prompt_text"],
                narration_text=template["narration_text"],
                sound_design=template["sound_design"],
                duration_seconds=duration,
            )
            for index, (template, duration) in enumerate(
                zip(scene_templates, durations), start=1
            )
        ]
        return PlannedVideoStoryboard(expanded_brief=expanded_brief, scenes=scenes)

    def _duration_plan(
        self,
        target_duration_seconds: int,
        provider: str = None,
        resolution: str = "720p",
        has_images: bool = False,
    ) -> List[int]:
        if provider == "google_veo":
            return self._veo_duration_plan(
                target_duration_seconds=target_duration_seconds,
                resolution=resolution,
                has_images=has_images,
            )

        target = max(
            MIN_SCENE_DURATION_SECONDS,
            min(target_duration_seconds, MAX_SCENE_DURATION_SECONDS * MAX_SCENE_COUNT),
        )
        required_count = ceil(target / MAX_SCENE_DURATION_SECONDS)
        preferred_count = max(self._preferred_scene_count(target), required_count)
        max_count_for_target = max(1, target // MIN_SCENE_DURATION_SECONDS)
        scene_count = min(preferred_count, max_count_for_target, MAX_SCENE_COUNT)
        base_duration = target // scene_count
        remainder = target % scene_count
        return [
            base_duration + (1 if index < remainder else 0)
            for index in range(scene_count)
        ]

    def _veo_duration_plan(
        self,
        target_duration_seconds: int,
        resolution: str,
        has_images: bool,
    ) -> List[int]:
        target = max(
            min(VEO_ALLOWED_DURATION_SECONDS),
            min(
                target_duration_seconds,
                max(VEO_ALLOWED_DURATION_SECONDS) * MAX_SCENE_COUNT,
            ),
        )
        if has_images or resolution in {"1080p", "4k"}:
            duration = normalize_veo_duration_seconds(
                target, resolution, has_images=has_images
            )
            scene_count = min(MAX_SCENE_COUNT, max(1, ceil(target / duration)))
            return [duration for _ in range(scene_count)]

        best_plan = None
        best_score = None
        for scene_count in range(1, MAX_SCENE_COUNT + 1):
            candidates = self._veo_duration_candidates(scene_count)
            for candidate in candidates:
                total = sum(candidate)
                score = (
                    abs(total - target),
                    0 if total >= target else 1,
                    len(candidate),
                )
                if best_score is None or score < best_score:
                    best_plan = candidate
                    best_score = score
        return best_plan or [max(VEO_ALLOWED_DURATION_SECONDS)]

    def _veo_duration_candidates(self, scene_count: int) -> List[List[int]]:
        if scene_count <= 0:
            return []
        if scene_count == 1:
            return [[duration] for duration in VEO_ALLOWED_DURATION_SECONDS]
        candidates = []
        for duration in VEO_ALLOWED_DURATION_SECONDS:
            for tail in self._veo_duration_candidates(scene_count - 1):
                candidates.append([duration, *tail])
        return candidates

    def _preferred_scene_count(self, target_duration_seconds: int) -> int:
        if target_duration_seconds <= 16:
            return 2
        if target_duration_seconds <= 45:
            return DEFAULT_SCENE_COUNT
        return 4

    def _scene_templates(
        self, prompt: str, visual_anchor: str, scene_count: int
    ) -> List[dict]:
        hook_scene = {
            "scene_role": "hook",
            "title": "Opening Hook",
            "prompt_text": (
                f"{visual_anchor} Start with an attention-grabbing commercial "
                f"shot for this offer: {prompt}. Use dynamic camera movement, "
                "clear subject focus, polished lighting, and a modern brand tone. "
                "Avoid readable text overlays or watermarks."
            ),
            "narration_text": "用一个直接的痛点或机会开场，让观众立刻知道为什么要继续看。",
            "sound_design": "Upbeat cinematic intro, clean impact accent, subtle ambience.",
        }
        value_scene = {
            "scene_role": "value",
            "title": "Core Value",
            "prompt_text": (
                f"Show the strongest selling points for: {prompt}. Build a "
                "smooth product-focused sequence with premium details, real-world "
                "usage context, and confident pacing. Keep the visuals realistic "
                "and commercially usable."
            ),
            "narration_text": "突出核心卖点、使用场景和可信赖感，语言短促有力。",
            "sound_design": "Steady branded rhythm, warm movement, light product accents.",
        }
        proof_scene = {
            "scene_role": "proof",
            "title": "Proof Moment",
            "prompt_text": (
                f"Show why the audience should trust this offer: {prompt}. Use "
                "credible usage details, calm pacing, polished brand visuals, and "
                "a confident transition toward the final action."
            ),
            "narration_text": "补充可信证据、关键场景或前后对比，让卖点更具体。",
            "sound_design": "Measured branded rhythm, subtle confirmation accents.",
        }
        cta_scene = {
            "scene_role": "cta",
            "title": "CTA Close",
            "prompt_text": (
                f"End with a memorable call-to-action feeling for: {prompt}. "
                "Show a polished final product moment, aspirational lifestyle "
                "context, and a clean ending beat. Leave space for the app to add "
                "localized captions later."
            ),
            "narration_text": "用一句行动号召收尾，引导咨询、购买或预约。",
            "sound_design": "Resolved musical lift, soft logo-style ending cue.",
        }
        if scene_count <= 2:
            return [hook_scene, cta_scene]
        middle_scenes = [
            value_scene,
            proof_scene,
            {
                "scene_role": "demo",
                "title": "Product Flow",
                "prompt_text": (
                    f"Show a clear product or service workflow for: {prompt}. "
                    "Use smooth step-by-step motion, realistic UI-adjacent visuals "
                    "without readable text, and a confident commercial rhythm."
                ),
                "narration_text": "展示从需求到结果的关键过程，让观众快速理解产品如何工作。",
                "sound_design": "Smooth interface motion, gentle clicks, clean transition pulse.",
            },
            {
                "scene_role": "benefit",
                "title": "Benefit Detail",
                "prompt_text": (
                    f"Focus on a concrete audience benefit for: {prompt}. Show "
                    "realistic business context, human decision-making, and a "
                    "polished visual metaphor for progress without text overlays."
                ),
                "narration_text": "把收益讲得更具体，强调效率、清晰度或增长结果。",
                "sound_design": "Warm forward momentum, restrained branded accents.",
            },
            {
                "scene_role": "trust",
                "title": "Trust Builder",
                "prompt_text": (
                    f"Build trust for: {prompt}. Use calm premium lighting, "
                    "credible work scenes, thoughtful pacing, and visual cues of "
                    "quality, reliability, and control."
                ),
                "narration_text": "补充可信感，降低观众疑虑，让产品更像可以马上使用的方案。",
                "sound_design": "Measured ambience, soft confirmation tones.",
            },
            {
                "scene_role": "momentum",
                "title": "Momentum Shift",
                "prompt_text": (
                    f"Create a momentum-building transition for: {prompt}. Show "
                    "the audience moving from uncertainty to clarity with elegant "
                    "camera motion, realistic props, and premium commercial energy."
                ),
                "narration_text": "推进情绪，从发现价值过渡到准备行动。",
                "sound_design": "Rising pulse, subtle sweep, clean impact.",
            },
            {
                "scene_role": "offer",
                "title": "Offer Focus",
                "prompt_text": (
                    f"Show the offer at its most compelling for: {prompt}. Use a "
                    "focused hero shot, confident pacing, and a polished setup that "
                    "naturally leads into the final call to action."
                ),
                "narration_text": "聚焦最值得行动的一点，为结尾转化做铺垫。",
                "sound_design": "Focused musical lift, crisp accent, restrained finish.",
            },
            {
                "scene_role": "recap",
                "title": "Value Recap",
                "prompt_text": (
                    f"Recap the main value of: {prompt} through a short cinematic "
                    "sequence. Keep the same visual world, subject continuity, and "
                    "premium tone while preparing for the final action."
                ),
                "narration_text": "快速回收核心价值，让观众记住为什么现在值得行动。",
                "sound_design": "Clean recap rhythm, soft rise, final transition cue.",
            },
        ]
        return [hook_scene, *middle_scenes[: scene_count - 2], cta_scene]


def get_openai_storyboard_planning_client() -> OpenAIStoryboardPlanningClient:
    """Get OpenAIStoryboardPlanningClient instance."""
    return OpenAIStoryboardPlanningClient()


def get_prompt_planning_service() -> PromptPlanningService:
    """Get PromptPlanningService instance."""
    ai_planning_client = get_openai_storyboard_planning_client()
    return PromptPlanningService(ai_planning_client=ai_planning_client)
