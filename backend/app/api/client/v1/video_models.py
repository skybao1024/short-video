from typing import List

from fastapi import APIRouter, Depends

from app.api.client.deps import get_current_user
from app.models.user import User
from app.schemas.client.video import VideoModelCapabilityResponse
from app.schemas.response import ApiResponse
from app.services.client.video_model_registry import (
    VideoModelRegistry,
    get_video_model_registry,
)

router = APIRouter()


@router.get("", response_model=ApiResponse[List[VideoModelCapabilityResponse]])
async def list_video_models(
    _current_user: User = Depends(get_current_user),
    registry: VideoModelRegistry = Depends(get_video_model_registry),
):
    """List available video generation models."""
    return ApiResponse.success(data=registry.list_models())
