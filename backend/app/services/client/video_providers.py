import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.exceptions.http_exceptions import APIException

VEO_ALLOWED_DURATION_SECONDS = (4, 6, 8)


@dataclass
class ProviderInputImage:
    """Image input prepared for a provider request."""

    url: Optional[str] = None
    data_base64: Optional[str] = None
    mime_type: str = "image/png"


@dataclass
class VideoProviderRequest:
    """Provider-neutral video generation request."""

    prompt_text: str
    model: str
    input_images: List[ProviderInputImage] = field(default_factory=list)
    aspect_ratio: str = "9:16"
    duration_seconds: int = 8
    resolution: str = "720p"
    seed: Optional[int] = None
    audio_mode: str = "auto"
    provider_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoProviderTask:
    """Provider task returned after submission."""

    provider_task_id: str
    raw_response: Dict[str, Any]


@dataclass
class VideoProviderStatus:
    """Provider-neutral status from a poll operation."""

    status: str
    output_ref: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


class VideoProviderError(Exception):
    """Provider-level error with a stable code."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def normalize_veo_duration_seconds(
    duration_seconds: int,
    resolution: str = "720p",
    has_images: bool = False,
) -> int:
    """Normalize requested scene duration to Veo's supported duration values."""
    if has_images or resolution in {"1080p", "4k"}:
        return 8

    requested_duration = max(1, int(duration_seconds or 8))
    for allowed_duration in VEO_ALLOWED_DURATION_SECONDS:
        if requested_duration <= allowed_duration:
            return allowed_duration
    return VEO_ALLOWED_DURATION_SECONDS[-1]


def _provider_http_error(
    code_prefix: str,
    provider_name: str,
    action: str,
    exc: httpx.HTTPError,
) -> VideoProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return VideoProviderError(
            code=f"{code_prefix}_TIMEOUT",
            message=f"{provider_name} request timed out while {action}",
            retryable=True,
        )
    return VideoProviderError(
        code=f"{code_prefix}_REQUEST_FAILED",
        message=f"{provider_name} request failed while {action}",
        retryable=True,
    )


class BaseVideoProviderClient:
    """Base provider client interface."""

    async def submit(self, request: VideoProviderRequest) -> VideoProviderTask:
        raise NotImplementedError

    async def poll(self, provider_task_id: str) -> VideoProviderStatus:
        raise NotImplementedError

    async def download_output(self, output_ref: str) -> bytes:
        raise NotImplementedError

    async def cancel(self, provider_task_id: str) -> bool:
        raise NotImplementedError


class RunwayVideoProviderClient(BaseVideoProviderClient):
    """Runway REST API client."""

    def __init__(
        self,
        api_secret: str = None,
        base_url: str = None,
        api_version: str = None,
        timeout_seconds: int = None,
        transport: Any = None,
    ):
        self.api_secret = api_secret or settings.RUNWAYML_API_SECRET
        self.base_url = (base_url or settings.RUNWAY_API_BASE_URL).rstrip("/")
        self.api_version = api_version or settings.RUNWAY_API_VERSION
        self.timeout_seconds = (
            timeout_seconds or settings.VIDEO_PROVIDER_TIMEOUT_SECONDS
        )
        self.transport = transport

    async def submit(self, request: VideoProviderRequest) -> VideoProviderTask:
        self._ensure_credentials()
        payload = {
            "model": request.model,
            "promptText": request.prompt_text,
            "ratio": self._ratio_to_runway_size(request.aspect_ratio),
            "duration": request.duration_seconds,
        }
        if request.input_images:
            first_image = request.input_images[0]
            payload["promptImage"] = (
                first_image.url
                or f"data:{first_image.mime_type};base64,{first_image.data_base64}"
            )
        payload.update(request.provider_params or {})

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/image_to_video",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _provider_http_error(
                "RUNWAY", "Runway", "submitting the generation request", exc
            ) from exc
        self._raise_for_response(response)
        data = response.json()
        provider_task_id = data.get("id")
        if not provider_task_id:
            raise VideoProviderError(
                "RUNWAY_EMPTY_TASK_ID", "Runway did not return a task id"
            )
        return VideoProviderTask(provider_task_id=provider_task_id, raw_response=data)

    async def poll(self, provider_task_id: str) -> VideoProviderStatus:
        self._ensure_credentials()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.base_url}/tasks/{provider_task_id}",
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise _provider_http_error(
                "RUNWAY", "Runway", "polling the generation task", exc
            ) from exc
        self._raise_for_response(response)
        data = response.json()
        provider_status = str(data.get("status", "")).upper()
        if provider_status == "SUCCEEDED":
            output = data.get("output") or []
            return VideoProviderStatus(
                status="succeeded",
                output_ref=output[0] if output else None,
                raw_response=data,
            )
        if provider_status in {"FAILED", "CANCELLED", "CANCELED"}:
            failure_code = data.get("failureCode") or provider_status
            return VideoProviderStatus(
                status=(
                    "canceled"
                    if provider_status in {"CANCELLED", "CANCELED"}
                    else "failed"
                ),
                failure_code=failure_code,
                failure_message=data.get("failure") or data.get("failureMessage"),
                raw_response=data,
            )
        return VideoProviderStatus(status="running", raw_response=data)

    async def download_output(self, output_ref: str) -> bytes:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(output_ref, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise _provider_http_error(
                "RUNWAY", "Runway", "downloading the generated video", exc
            ) from exc
        self._raise_for_response(response)
        return response.content

    async def cancel(self, provider_task_id: str) -> bool:
        self._ensure_credentials()
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.delete(
                f"{self.base_url}/tasks/{provider_task_id}",
                headers=self._headers(),
            )
        return response.status_code in {200, 202, 204, 404}

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_secret}",
            "Content-Type": "application/json",
            "X-Runway-Version": self.api_version,
        }

    def _ensure_credentials(self):
        if not self.api_secret:
            raise VideoProviderError(
                "RUNWAY_CREDENTIALS_MISSING",
                "Runway API credentials are not configured",
            )

    def _raise_for_response(self, response: httpx.Response):
        if response.status_code < 400:
            return
        raise VideoProviderError(
            code=f"RUNWAY_HTTP_{response.status_code}",
            message=self._safe_error_message(response),
            retryable=response.status_code >= 500 or response.status_code == 429,
        )

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
            return data.get("message") or data.get("error") or "Runway request failed"
        except ValueError:
            return "Runway request failed"

    @staticmethod
    def _ratio_to_runway_size(aspect_ratio: str) -> str:
        return {
            "9:16": "720:1280",
            "16:9": "1280:720",
            "1:1": "960:960",
        }.get(aspect_ratio, "720:1280")


class GoogleVeoProviderClient(BaseVideoProviderClient):
    """Google Veo client using the Gemini REST API."""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        timeout_seconds: int = None,
        transport: Any = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = (base_url or settings.GEMINI_API_BASE_URL).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds or settings.VIDEO_PROVIDER_TIMEOUT_SECONDS
        )
        self.transport = transport

    async def submit(self, request: VideoProviderRequest) -> VideoProviderTask:
        self._ensure_credentials()
        try:
            data = await self._submit_payload(request, include_images=True)
        except VideoProviderError as exc:
            if not self._should_retry_without_images(exc, request):
                raise
            data = await self._submit_payload(request, include_images=False)
            data["_local_fallback"] = {
                "reason": "image_input_rejected",
                "original_error_code": exc.code,
                "original_error_message": exc.message,
            }
        operation_name = data.get("name")
        if not operation_name:
            raise VideoProviderError(
                "VEO_EMPTY_OPERATION", "Veo did not return an operation name"
            )
        return VideoProviderTask(provider_task_id=operation_name, raw_response=data)

    async def _submit_payload(
        self, request: VideoProviderRequest, include_images: bool
    ) -> Dict[str, Any]:
        payload = self._build_payload(request, include_images=include_images)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/models/{request.model}:predictLongRunning",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _provider_http_error(
                "VEO", "Veo", "submitting the generation request", exc
            ) from exc
        self._raise_for_response(response)
        return response.json()

    async def poll(self, provider_task_id: str) -> VideoProviderStatus:
        self._ensure_credentials()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.base_url}/{provider_task_id}",
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise _provider_http_error(
                "VEO", "Veo", "polling the generation task", exc
            ) from exc
        self._raise_for_response(response)
        data = response.json()
        if not data.get("done"):
            return VideoProviderStatus(status="running", raw_response=data)
        if data.get("error"):
            error = data["error"]
            return VideoProviderStatus(
                status="failed",
                failure_code=str(error.get("code") or "VEO_ERROR"),
                failure_message=error.get("message"),
                raw_response=data,
            )
        output_ref = self._extract_output_ref(data)
        return VideoProviderStatus(
            status="succeeded",
            output_ref=output_ref,
            raw_response=data,
        )

    async def download_output(self, output_ref: str) -> bytes:
        self._ensure_credentials()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    output_ref,
                    headers={"x-goog-api-key": self.api_key},
                    follow_redirects=True,
                )
        except httpx.HTTPError as exc:
            raise _provider_http_error(
                "VEO", "Veo", "downloading the generated video", exc
            ) from exc
        self._raise_for_response(response)
        return response.content

    async def cancel(self, provider_task_id: str) -> bool:
        return False

    def _build_payload(
        self, request: VideoProviderRequest, include_images: bool = True
    ) -> Dict[str, Any]:
        instance: Dict[str, Any] = {"prompt": request.prompt_text}
        inline_images = [
            image
            for image in (request.input_images if include_images else [])
            if image.data_base64
        ]
        has_images = bool(inline_images)
        if inline_images:
            instance["referenceImages"] = [
                {
                    "image": self._inline_image(image),
                    "referenceType": "asset",
                }
                for image in inline_images[:3]
            ]

        parameters = {
            "aspectRatio": request.aspect_ratio,
            "durationSeconds": normalize_veo_duration_seconds(
                request.duration_seconds,
                request.resolution,
                has_images=has_images,
            ),
            "resolution": request.resolution,
        }
        if has_images:
            parameters["personGeneration"] = "allow_adult"
        parameters.update(request.provider_params or {})
        return {"instances": [instance], "parameters": parameters}

    @staticmethod
    def _inline_image(image: ProviderInputImage) -> Dict[str, Dict[str, str]]:
        return {
            "inlineData": {
                "mimeType": image.mime_type,
                "data": image.data_base64 or "",
            }
        }

    def _headers(self) -> Dict[str, str]:
        return {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _ensure_credentials(self):
        if not self.api_key:
            raise VideoProviderError(
                "VEO_CREDENTIALS_MISSING",
                "Gemini API credentials are not configured",
            )

    def _raise_for_response(self, response: httpx.Response):
        if response.status_code < 400:
            return
        raise VideoProviderError(
            code=f"VEO_HTTP_{response.status_code}",
            message=self._safe_error_message(response),
            retryable=response.status_code >= 500 or response.status_code == 429,
        )

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
            error = data.get("error") or {}
            return error.get("message") or data.get("message") or "Veo request failed"
        except ValueError:
            return "Veo request failed"

    @staticmethod
    def _should_retry_without_images(
        exc: VideoProviderError, request: VideoProviderRequest
    ) -> bool:
        if exc.code != "VEO_HTTP_400" or not request.input_images:
            return False
        message = (exc.message or "").lower()
        mentions_image_payload = any(
            marker in message
            for marker in ("inlinedata", "imagebytes", "referenceimages")
        )
        return mentions_image_payload and (
            "not supported" in message or "isn't supported" in message
        )

    @staticmethod
    def _extract_output_ref(data: Dict[str, Any]) -> Optional[str]:
        response = data.get("response") or {}
        generate_response = response.get("generateVideoResponse") or {}
        samples = generate_response.get("generatedSamples") or []
        if samples:
            return (samples[0].get("video") or {}).get("uri")
        videos = response.get("generatedVideos") or []
        if videos:
            return (videos[0].get("video") or {}).get("uri")
        return None


class VideoProviderFactory:
    """Create provider clients by provider key."""

    def __init__(
        self,
        runway_client: RunwayVideoProviderClient = None,
        veo_client: GoogleVeoProviderClient = None,
    ):
        self.runway_client = runway_client or RunwayVideoProviderClient()
        self.veo_client = veo_client or GoogleVeoProviderClient()

    def get_client(self, provider: str) -> BaseVideoProviderClient:
        """Get provider client by provider key."""
        if provider == "runway":
            return self.runway_client
        if provider == "google_veo":
            return self.veo_client
        raise APIException(status_code=400, message="Unsupported video provider")


def encode_image_bytes(data: bytes) -> str:
    """Encode image bytes for providers that require inline data."""
    return base64.b64encode(data).decode("utf-8")


def get_video_provider_factory() -> VideoProviderFactory:
    """Get VideoProviderFactory instance."""
    return VideoProviderFactory()
