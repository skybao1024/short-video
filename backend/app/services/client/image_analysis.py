import base64
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.video import VideoAsset
from app.services.common.s3_service import S3Service, get_s3_service


OPENAI_IMAGE_ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assets"],
    "properties": {
        "assets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "asset_id",
                    "caption",
                    "asset_type",
                    "visual_tags",
                    "best_for_scene_roles",
                    "avoid_for_scene_roles",
                ],
                "properties": {
                    "asset_id": {"type": "integer"},
                    "caption": {"type": "string"},
                    "asset_type": {"type": "string"},
                    "visual_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "best_for_scene_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "avoid_for_scene_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


@dataclass
class ImageAssetInput:
    """Image asset payload sent to the analysis model."""

    asset_id: int
    file_name: str
    mime_type: str
    data_base64: str


@dataclass
class ImageAssetAnalysis:
    """Structured image understanding used by storyboard planning."""

    asset_id: int
    caption: str
    asset_type: str
    visual_tags: List[str] = field(default_factory=list)
    best_for_scene_roles: List[str] = field(default_factory=list)
    avoid_for_scene_roles: List[str] = field(default_factory=list)

    def to_storyboard_context(self) -> Dict[str, Any]:
        """Return compact metadata safe to include in storyboard prompts."""
        return asdict(self)


class ImageAnalysisError(Exception):
    """Raised when image analysis cannot produce usable metadata."""


class OpenAIImageAnalysisClient:
    """Analyze project reference images with the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        detail: str = None,
        timeout_seconds: int = None,
        transport: Any = None,
    ):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.base_url = (base_url or settings.OPENAI_API_BASE_URL).rstrip("/")
        self.model = model or settings.OPENAI_IMAGE_ANALYSIS_MODEL
        self.detail = detail or settings.OPENAI_IMAGE_ANALYSIS_DETAIL
        self.timeout_seconds = (
            timeout_seconds or settings.OPENAI_IMAGE_ANALYSIS_TIMEOUT_SECONDS
        )
        self.transport = transport

    def is_configured(self) -> bool:
        """Return whether image analysis can be attempted."""
        return bool(self.api_key and self.base_url and self.model)

    async def analyze_assets(
        self, assets: List[ImageAssetInput]
    ) -> List[ImageAssetAnalysis]:
        """Analyze image assets and return storyboard-ready metadata."""
        if not assets:
            return []
        if not self.is_configured():
            raise ImageAnalysisError("OpenAI image analysis is not configured")

        payload = self._build_request_payload(assets)
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
            raise ImageAnalysisError(self._safe_error_message(response))

        response_text = self._extract_response_text(response.json())
        data = self._decode_response_text(response_text)
        return self._build_analyses(
            data, expected_asset_ids={asset.asset_id for asset in assets}
        )

    def _build_request_payload(self, assets: List[ImageAssetInput]) -> Dict[str, Any]:
        system_prompt = (
            "You are a commercial video art director and product UI analyst. "
            "Describe each reference image so another AI can choose the right "
            "assets for storyboard scenes. Focus on product UI, brand style, "
            "objects, composition, color, and which scene roles the image fits. "
            "Return concise English structured output only."
        )
        user_content = [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "task": "Analyze these uploaded video reference assets.",
                        "assets": [
                            {
                                "asset_id": asset.asset_id,
                                "file_name": asset.file_name,
                                "mime_type": asset.mime_type,
                            }
                            for asset in assets
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        for asset in assets:
            user_content.extend(
                [
                    {
                        "type": "input_text",
                        "text": f"Asset {asset.asset_id}: {asset.file_name}",
                    },
                    {
                        "type": "input_image",
                        "image_url": (
                            f"data:{asset.mime_type};base64,{asset.data_base64}"
                        ),
                        "detail": self.detail,
                    },
                ]
            )

        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {"role": "user", "content": user_content},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "video_reference_image_analysis",
                    "strict": True,
                    "schema": OPENAI_IMAGE_ANALYSIS_SCHEMA,
                },
                "verbosity": "low",
            },
        }

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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

        raise ImageAnalysisError("OpenAI image analysis returned no output text")

    def _decode_response_text(self, response_text: str) -> Dict[str, Any]:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ImageAnalysisError(
                "OpenAI image analysis returned invalid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise ImageAnalysisError("OpenAI image analysis must return an object")
        return data

    def _build_analyses(
        self, data: Dict[str, Any], expected_asset_ids: set[int]
    ) -> List[ImageAssetAnalysis]:
        raw_assets = data.get("assets")
        if not isinstance(raw_assets, list):
            raise ImageAnalysisError("OpenAI image analysis returned no assets")

        analyses = []
        seen_asset_ids = set()
        for item in raw_assets:
            if not isinstance(item, dict):
                continue
            try:
                asset_id = int(item.get("asset_id"))
            except (TypeError, ValueError):
                continue
            if asset_id not in expected_asset_ids or asset_id in seen_asset_ids:
                continue
            seen_asset_ids.add(asset_id)
            analyses.append(
                ImageAssetAnalysis(
                    asset_id=asset_id,
                    caption=self._clean_text(item.get("caption"), 600),
                    asset_type=self._clean_text(item.get("asset_type"), 80),
                    visual_tags=self._clean_list(item.get("visual_tags"), 12, 40),
                    best_for_scene_roles=self._clean_list(
                        item.get("best_for_scene_roles"), 8, 40
                    ),
                    avoid_for_scene_roles=self._clean_list(
                        item.get("avoid_for_scene_roles"), 8, 40
                    ),
                )
            )

        missing_asset_ids = expected_asset_ids - seen_asset_ids
        if missing_asset_ids:
            missing = ", ".join(str(asset_id) for asset_id in sorted(missing_asset_ids))
            raise ImageAnalysisError(f"OpenAI image analysis missed assets: {missing}")
        return analyses

    def _clean_text(self, value: Any, max_length: int) -> str:
        text = value if isinstance(value, str) else ""
        return " ".join(text.split())[:max_length]

    def _clean_list(self, value: Any, max_items: int, max_length: int) -> List[str]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            if not isinstance(item, str):
                continue
            normalized = " ".join(item.split())[:max_length]
            if normalized and normalized not in result:
                result.append(normalized)
            if len(result) >= max_items:
                break
        return result

    def _safe_error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return "OpenAI image analysis request failed"
        error = data.get("error") or {}
        if isinstance(error, dict):
            return error.get("message") or "OpenAI image analysis request failed"
        if isinstance(error, str):
            return error
        return data.get("message") or "OpenAI image analysis request failed"


class ImageAssetAnalysisService:
    """Persist image analysis metadata for video project assets."""

    def __init__(
        self,
        analysis_client: OpenAIImageAnalysisClient = None,
        s3_service: S3Service = None,
    ):
        self.analysis_client = analysis_client or get_openai_image_analysis_client()
        self.s3_service = s3_service or get_s3_service()

    async def analyze_assets(
        self, db: AsyncSession, assets: List[VideoAsset]
    ) -> List[Dict[str, Any]]:
        """Analyze missing image metadata and return storyboard context."""
        image_assets = [asset for asset in assets if asset.asset_type == "input_image"]
        missing_assets = [
            asset for asset in image_assets if not self._get_image_analysis(asset)
        ]

        if missing_assets:
            inputs = [
                ImageAssetInput(
                    asset_id=asset.id,
                    file_name=asset.file_name or f"asset-{asset.id}",
                    mime_type=asset.mime_type,
                    data_base64=base64.b64encode(
                        self.s3_service.download_bytes(asset.file_key)
                    ).decode("utf-8"),
                )
                for asset in missing_assets
            ]
            analyses = await self.analysis_client.analyze_assets(inputs)
            analyses_by_id = {analysis.asset_id: analysis for analysis in analyses}

            for asset in missing_assets:
                analysis = analyses_by_id.get(asset.id)
                if not analysis:
                    continue
                metadata = dict(asset.provider_metadata or {})
                metadata["image_analysis"] = {
                    **analysis.to_storyboard_context(),
                    "model": self.analysis_client.model,
                    "analyzed_at": datetime.now(UTC).isoformat(),
                }
                asset.provider_metadata = metadata
            await db.flush()

        return [
            self._get_image_analysis(asset)
            for asset in image_assets
            if self._get_image_analysis(asset)
        ]

    def _get_image_analysis(self, asset: VideoAsset) -> Dict[str, Any] | None:
        metadata = asset.provider_metadata or {}
        analysis = metadata.get("image_analysis")
        if not isinstance(analysis, dict):
            return None
        return {
            "asset_id": asset.id,
            "file_name": asset.file_name,
            "caption": analysis.get("caption") or "",
            "asset_type": analysis.get("asset_type") or "",
            "visual_tags": analysis.get("visual_tags") or [],
            "best_for_scene_roles": analysis.get("best_for_scene_roles") or [],
            "avoid_for_scene_roles": analysis.get("avoid_for_scene_roles") or [],
        }


def get_openai_image_analysis_client() -> OpenAIImageAnalysisClient:
    """Get OpenAIImageAnalysisClient instance."""
    return OpenAIImageAnalysisClient()


def get_image_asset_analysis_service() -> ImageAssetAnalysisService:
    """Get ImageAssetAnalysisService instance."""
    return ImageAssetAnalysisService()
