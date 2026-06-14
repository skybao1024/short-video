from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.client.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.client.video import (
    VideoAssetUploadUrlRequest,
    VideoAssetUploadUrlResponse,
)
from app.schemas.response import ApiResponse
from app.services.client.video import VideoAssetService, get_video_asset_service

router = APIRouter()


@router.post(
    "/presigned-upload-url",
    response_model=ApiResponse[VideoAssetUploadUrlResponse],
)
async def create_video_asset_upload_url(
    request: VideoAssetUploadUrlRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_asset_service: VideoAssetService = Depends(get_video_asset_service),
):
    """Create a presigned upload URL for an input image."""
    result = await video_asset_service.create_input_image_upload_url(
        db=db,
        user_id=current_user.id,
        file_name=request.file_name,
        file_type=request.file_type,
        file_size=request.file_size,
    )
    return ApiResponse.success(data=result)
