from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProviderName = Literal["google_veo", "runway"]
AspectRatio = Literal["9:16", "16:9", "1:1"]
Resolution = Literal["720p", "1080p", "4k"]


class VideoModelCapabilityResponse(BaseModel):
    """Public model capability shown in the client model picker."""

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


class VideoAssetUploadUrlRequest(BaseModel):
    """Request schema for uploading video project input images."""

    file_name: str = Field(..., description="Image file name with extension")
    file_type: str = Field(..., description="Image MIME type")
    file_size: int = Field(..., description="File size in bytes", gt=0)


class VideoAssetUploadUrlResponse(BaseModel):
    """Response schema for an input image upload URL."""

    asset_id: int
    presigned_url: str
    file_key: str
    expires_in: int
    max_file_size: int


class VideoProjectCreateRequest(BaseModel):
    """Create a promotional video project."""

    prompt: str = Field(..., min_length=8, max_length=8000)
    asset_ids: List[int] = Field(default_factory=list)
    provider: ProviderName = "runway"
    model: str = "gen4.5"
    aspect_ratio: AspectRatio = "9:16"
    resolution: Resolution = "720p"
    target_duration_seconds: int = Field(24, ge=8, le=60)
    title: Optional[str] = Field(None, max_length=255)


class VideoStoryboardGenerateRequest(BaseModel):
    """Request schema for storyboard generation."""

    regenerate: bool = False


class VideoStoryboardSceneUpdate(BaseModel):
    """Editable storyboard scene submitted by the client."""

    scene_index: int = Field(..., ge=1, le=20)
    scene_role: str = Field(..., min_length=1, max_length=40)
    title: str = Field(..., min_length=1, max_length=255)
    prompt_text: str = Field(..., min_length=8, max_length=4000)
    narration_text: Optional[str] = Field(None, max_length=2000)
    sound_design: Optional[str] = Field(None, max_length=1000)
    duration_seconds: int = Field(..., ge=3, le=15)
    input_asset_ids: List[int] = Field(default_factory=list)


class VideoStoryboardUpdateRequest(BaseModel):
    """Replace the editable storyboard for a project."""

    scenes: List[VideoStoryboardSceneUpdate] = Field(..., min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_scene_indexes(self):
        indexes = [scene.scene_index for scene in self.scenes]
        if len(indexes) != len(set(indexes)):
            raise ValueError("Scene indexes must be unique")
        return self


class VideoGenerationStartRequest(BaseModel):
    """Start generation after storyboard confirmation."""

    force: bool = False


class VideoAssetResponse(BaseModel):
    """Video asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: Optional[int] = None
    asset_type: str
    status: str
    file_key: str
    file_name: Optional[str] = None
    mime_type: str
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[Decimal] = None
    source_url: Optional[str] = None
    provider: Optional[str] = None
    provider_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class VideoStoryboardSceneResponse(BaseModel):
    """Storyboard scene response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    scene_index: int
    scene_role: str
    title: str
    prompt_text: str
    narration_text: Optional[str] = None
    sound_design: Optional[str] = None
    duration_seconds: int
    input_asset_ids: Optional[List[int]] = None
    output_asset_id: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime


class VideoGenerationTaskResponse(BaseModel):
    """Provider generation task response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    scene_id: int
    provider: str
    model: str
    provider_task_id: Optional[str] = None
    status: str
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    output_asset_id: Optional[int] = None
    retry_count: int
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class VideoExportResponse(BaseModel):
    """Final export response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    input_asset_ids: Optional[List[int]] = None
    output_asset_id: Optional[int] = None
    render_params: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class VideoProjectResponse(BaseModel):
    """Promotional video project response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: Optional[str] = None
    prompt: str
    expanded_brief: Optional[str] = None
    provider: str
    model: str
    aspect_ratio: str
    resolution: str
    target_duration_seconds: int
    status: str
    progress: int
    final_video_asset_id: Optional[int] = None
    final_video_file_key: Optional[str] = None
    thumbnail_file_key: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    estimated_cost_credits: Optional[Decimal] = None
    provider_metadata: Optional[Dict[str, Any]] = None
    generation_started_at: Optional[datetime] = None
    generation_completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    assets: List[VideoAssetResponse] = Field(default_factory=list)
    scenes: List[VideoStoryboardSceneResponse] = Field(default_factory=list)
    tasks: List[VideoGenerationTaskResponse] = Field(default_factory=list)
    exports: List[VideoExportResponse] = Field(default_factory=list)


class VideoProjectListItemResponse(BaseModel):
    """Compact project response for lists."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: Optional[str] = None
    prompt: str
    provider: str
    model: str
    aspect_ratio: str
    resolution: str
    target_duration_seconds: int
    status: str
    progress: int
    final_video_file_key: Optional[str] = None
    thumbnail_file_key: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
