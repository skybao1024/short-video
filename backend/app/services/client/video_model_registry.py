from dataclasses import asdict, dataclass
from typing import Dict, List

from app.exceptions.http_exceptions import APIException


@dataclass(frozen=True)
class VideoModelCapability:
    """Provider model capability used by API validation and UI display."""

    provider: str
    provider_label: str
    model: str
    model_label: str
    supports_text: bool
    supports_image: bool
    supports_audio: bool
    supported_aspect_ratios: List[str]
    supported_resolutions: List[str]
    default_duration_seconds: int
    max_prompt_tokens: int
    cost_hint: str
    is_default: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


VIDEO_MODEL_CAPABILITIES = [
    VideoModelCapability(
        provider="runway",
        provider_label="Runway",
        model="gen4.5",
        model_label="Gen-4.5",
        supports_text=True,
        supports_image=True,
        supports_audio=False,
        supported_aspect_ratios=["9:16", "16:9", "1:1"],
        supported_resolutions=["720p", "1080p"],
        default_duration_seconds=8,
        max_prompt_tokens=1000,
        cost_hint="Balanced quality and speed for commercial clips",
        is_default=True,
    ),
    VideoModelCapability(
        provider="google_veo",
        provider_label="Google Veo",
        model="veo-3.0-generate-001",
        model_label="Veo 3",
        supports_text=True,
        supports_image=True,
        supports_audio=True,
        supported_aspect_ratios=["9:16", "16:9"],
        supported_resolutions=["720p", "1080p"],
        default_duration_seconds=8,
        max_prompt_tokens=1024,
        cost_hint="High realism with native audio generation",
    ),
    VideoModelCapability(
        provider="google_veo",
        provider_label="Google Veo",
        model="veo-3.0-fast-generate-001",
        model_label="Veo 3 Fast",
        supports_text=True,
        supports_image=True,
        supports_audio=True,
        supported_aspect_ratios=["9:16", "16:9"],
        supported_resolutions=["720p", "1080p"],
        default_duration_seconds=8,
        max_prompt_tokens=1024,
        cost_hint="Faster and cheaper Veo variant",
    ),
    VideoModelCapability(
        provider="google_veo",
        provider_label="Google Veo",
        model="veo-3.1-generate-preview",
        model_label="Veo 3.1 Preview",
        supports_text=True,
        supports_image=True,
        supports_audio=True,
        supported_aspect_ratios=["9:16", "16:9"],
        supported_resolutions=["720p", "1080p", "4k"],
        default_duration_seconds=8,
        max_prompt_tokens=1024,
        cost_hint="Preview model with stronger image guidance",
    ),
    VideoModelCapability(
        provider="google_veo",
        provider_label="Google Veo",
        model="veo-3.1-fast-generate-preview",
        model_label="Veo 3.1 Fast Preview",
        supports_text=True,
        supports_image=True,
        supports_audio=True,
        supported_aspect_ratios=["9:16", "16:9"],
        supported_resolutions=["720p", "1080p"],
        default_duration_seconds=8,
        max_prompt_tokens=1024,
        cost_hint="Preview model optimized for speed",
    ),
]


class VideoModelRegistry:
    """Central model registry for provider-specific capabilities."""

    def __init__(self, capabilities: List[VideoModelCapability] = None):
        self.capabilities = capabilities or VIDEO_MODEL_CAPABILITIES

    def list_models(self) -> List[Dict]:
        """List all public model capabilities."""
        return [capability.to_dict() for capability in self.capabilities]

    def get_model(self, provider: str, model: str) -> VideoModelCapability:
        """Get a capability by provider and model."""
        for capability in self.capabilities:
            if capability.provider == provider and capability.model == model:
                return capability
        raise APIException(status_code=400, message="Unsupported video model")

    def validate_generation_options(
        self,
        provider: str,
        model: str,
        aspect_ratio: str,
        resolution: str,
        has_images: bool,
    ) -> VideoModelCapability:
        """Validate user-selected generation options."""
        capability = self.get_model(provider, model)
        if aspect_ratio not in capability.supported_aspect_ratios:
            raise APIException(
                status_code=400,
                message=f"Aspect ratio {aspect_ratio} is not supported by {model}",
            )
        if resolution not in capability.supported_resolutions:
            raise APIException(
                status_code=400,
                message=f"Resolution {resolution} is not supported by {model}",
            )
        if has_images and not capability.supports_image:
            raise APIException(
                status_code=400,
                message=f"Image input is not supported by {model}",
            )
        return capability


def get_video_model_registry() -> VideoModelRegistry:
    """Get VideoModelRegistry instance."""
    return VideoModelRegistry()
