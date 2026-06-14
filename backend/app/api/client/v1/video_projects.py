from typing import Dict

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.client.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.client.video import (
    VideoGenerationStartRequest,
    VideoProjectCreateRequest,
    VideoProjectResponse,
    VideoStoryboardGenerateRequest,
    VideoStoryboardUpdateRequest,
)
from app.schemas.response import ApiResponse
from app.services.client.video import VideoProjectService, get_video_project_service

router = APIRouter()


@router.get("", response_model=ApiResponse[Dict])
async def list_video_projects(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """List current user's promotional video projects."""
    result = await video_project_service.list_projects(
        db=db, user_id=current_user.id, page=page, per_page=per_page
    )
    return ApiResponse.success(data=result)


@router.post("", response_model=ApiResponse[VideoProjectResponse])
async def create_video_project(
    request: VideoProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Create a promotional video project."""
    project = await video_project_service.create_project(
        db=db, user_id=current_user.id, request=request
    )
    return ApiResponse.success(data=project)


@router.get("/{project_id}", response_model=ApiResponse[VideoProjectResponse])
async def get_video_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Get a promotional video project."""
    project = await video_project_service.get_project(
        db=db, user_id=current_user.id, project_id=project_id
    )
    return ApiResponse.success(data=project)


@router.post(
    "/{project_id}/storyboard",
    response_model=ApiResponse[VideoProjectResponse],
)
async def generate_video_project_storyboard(
    project_id: int,
    request: VideoStoryboardGenerateRequest = Body(
        default_factory=VideoStoryboardGenerateRequest
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Generate or regenerate a project storyboard."""
    project = await video_project_service.generate_storyboard(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        regenerate=request.regenerate,
    )
    return ApiResponse.success(data=project)


@router.patch(
    "/{project_id}/storyboard",
    response_model=ApiResponse[VideoProjectResponse],
)
async def update_video_project_storyboard(
    project_id: int,
    request: VideoStoryboardUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Replace a project storyboard before generation starts."""
    project = await video_project_service.update_storyboard(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        request=request,
    )
    return ApiResponse.success(data=project)


@router.post(
    "/{project_id}/generate",
    response_model=ApiResponse[VideoProjectResponse],
)
async def start_video_project_generation(
    project_id: int,
    request: VideoGenerationStartRequest = Body(
        default_factory=VideoGenerationStartRequest
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Queue project generation."""
    project = await video_project_service.start_generation(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        force=request.force,
    )
    return ApiResponse.success(data=project)


@router.post(
    "/{project_id}/scenes/{scene_id}/retry",
    response_model=ApiResponse[VideoProjectResponse],
)
async def retry_video_project_scene_generation(
    project_id: int,
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Retry a failed storyboard scene and continue project generation."""
    project = await video_project_service.retry_scene_generation(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        scene_id=scene_id,
    )
    return ApiResponse.success(data=project)


@router.post("/{project_id}/cancel", response_model=ApiResponse[VideoProjectResponse])
async def cancel_video_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    video_project_service: VideoProjectService = Depends(get_video_project_service),
):
    """Cancel queued or running project generation."""
    project = await video_project_service.cancel_project(
        db=db, user_id=current_user.id, project_id=project_id
    )
    return ApiResponse.success(data=project)
