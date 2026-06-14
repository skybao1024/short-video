import logging
from typing import Dict, List

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import transaction
from app.exceptions.http_exceptions import APIException
from app.models.video import VideoAsset, VideoProject, VideoStoryboardScene
from app.schemas.client.video import (
    VideoProjectCreateRequest,
    VideoProjectListItemResponse,
    VideoProjectResponse,
    VideoStoryboardSceneUpdate,
    VideoStoryboardUpdateRequest,
)
from app.services.client.image_analysis import (
    ImageAnalysisError,
    ImageAssetAnalysisService,
    get_image_asset_analysis_service,
)
from app.services.client.prompt_planning import (
    PromptPlanningService,
    StoryboardPlanningError,
    get_prompt_planning_service,
)
from app.services.client.video_model_registry import (
    VideoModelRegistry,
    get_video_model_registry,
)
from app.services.client.video_providers import (
    VideoProviderFactory,
    get_video_provider_factory,
)
from app.services.common.s3_service import S3Service, get_s3_service

logger = logging.getLogger(__name__)


class VideoAssetService:
    """Manage video project assets."""

    IMAGE_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
    IMAGE_ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]
    MAX_IMAGE_SIZE = 16 * 1024 * 1024

    def __init__(self, s3_service: S3Service = None):
        self.s3_service = s3_service or get_s3_service()

    async def create_input_image_upload_url(
        self,
        db: AsyncSession,
        user_id: int,
        file_name: str,
        file_type: str,
        file_size: int,
    ) -> Dict:
        """Create an input image asset and upload URL."""
        self._validate_input_image(file_name, file_type, file_size)
        file_key = self.s3_service.generate_file_key(
            user_id=user_id,
            file_name=file_name,
            module="video-projects",
            sub_path="input-images",
        )
        async with transaction(db):
            asset = VideoAsset(
                user_id=user_id,
                asset_type="input_image",
                status="uploading",
                file_key=file_key,
                file_name=file_name,
                mime_type=file_type,
                file_size=file_size,
            )
            db.add(asset)
            await db.flush()
            upload = self.s3_service.generate_presigned_upload_url(
                file_key=file_key,
                file_type=file_type,
                expires_in=900,
                max_file_size=self.MAX_IMAGE_SIZE,
            )
            return {
                "asset_id": asset.id,
                "presigned_url": upload["presigned_url"],
                "file_key": file_key,
                "expires_in": upload["expires_in"],
                "max_file_size": upload["max_file_size"],
            }

    def _validate_input_image(self, file_name: str, file_type: str, file_size: int):
        if file_size > self.MAX_IMAGE_SIZE:
            raise APIException(status_code=400, message="Image size exceeds 16MB")
        if file_type not in self.IMAGE_ALLOWED_MIME_TYPES:
            raise APIException(status_code=400, message="Unsupported image MIME type")
        if not self.s3_service.validate_file_type(
            file_name, self.IMAGE_ALLOWED_EXTENSIONS
        ):
            raise APIException(status_code=400, message="Unsupported image file type")


class VideoProjectService:
    """Manage promotional video projects and generation flow."""

    EDITABLE_STATUSES = {"draft", "storyboard_ready", "failed"}
    GENERATION_STATUSES = {"queued", "generating"}

    def __init__(
        self,
        planning_service: PromptPlanningService = None,
        image_analysis_service: ImageAssetAnalysisService = None,
        registry: VideoModelRegistry = None,
        provider_factory: VideoProviderFactory = None,
    ):
        self.planning_service = planning_service or get_prompt_planning_service()
        self.image_analysis_service = (
            image_analysis_service or get_image_asset_analysis_service()
        )
        self.registry = registry or get_video_model_registry()
        self.provider_factory = provider_factory or get_video_provider_factory()

    async def list_projects(
        self, db: AsyncSession, user_id: int, page: int = 1, per_page: int = 12
    ) -> Dict:
        """List current user's video projects."""
        page = max(1, page)
        per_page = min(50, max(1, per_page))
        total_query = (
            select(func.count())
            .select_from(VideoProject)
            .where(VideoProject.user_id == user_id)
        )
        total = await db.scalar(total_query)
        query = (
            select(VideoProject)
            .where(VideoProject.user_id == user_id)
            .order_by(desc(VideoProject.created_at))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await db.execute(query)
        projects = result.scalars().all()
        return {
            "items": [
                VideoProjectListItemResponse.model_validate(project)
                for project in projects
            ],
            "total": total or 0,
            "per_page": per_page,
            "current_page": page,
            "last_page": ((total or 0) + per_page - 1) // per_page,
            "has_more": page * per_page < (total or 0),
        }

    async def get_project(
        self, db: AsyncSession, user_id: int, project_id: int
    ) -> VideoProjectResponse:
        """Get a project with all related generation data."""
        project = await self._get_project_model(db, user_id, project_id)
        return VideoProjectResponse.model_validate(project)

    async def create_project(
        self, db: AsyncSession, user_id: int, request: VideoProjectCreateRequest
    ) -> VideoProjectResponse:
        """Create a promotional video project."""
        has_images = bool(request.asset_ids)
        self.registry.validate_generation_options(
            provider=request.provider,
            model=request.model,
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
            has_images=has_images,
        )
        async with transaction(db):
            assets = await self._get_user_assets(db, user_id, request.asset_ids)
            title = request.title or self._derive_title(request.prompt)
            project = VideoProject(
                user_id=user_id,
                title=title,
                prompt=request.prompt,
                provider=request.provider,
                model=request.model,
                aspect_ratio=request.aspect_ratio,
                resolution=request.resolution,
                target_duration_seconds=request.target_duration_seconds,
                status="draft",
                progress=0,
            )
            db.add(project)
            await db.flush()
            for asset in assets:
                asset.project_id = project.id
                asset.status = "ready"
            await db.flush()
            project_id = project.id
        return await self.get_project(db, user_id, project_id)

    async def generate_storyboard(
        self,
        db: AsyncSession,
        user_id: int,
        project_id: int,
        regenerate: bool = False,
    ) -> VideoProjectResponse:
        """Generate or regenerate a storyboard for a project."""
        async with transaction(db):
            project = await self._get_project_model(db, user_id, project_id)
            if project.status not in self.EDITABLE_STATUSES:
                raise APIException(
                    status_code=400,
                    message="Storyboard cannot be changed after generation starts",
                )
            if project.scenes and not regenerate:
                return VideoProjectResponse.model_validate(project)
            for scene in list(project.scenes):
                await db.delete(scene)
            input_assets = [
                asset for asset in project.assets if asset.asset_type == "input_image"
            ]
            image_asset_context = []
            if input_assets:
                try:
                    image_asset_context = (
                        await self.image_analysis_service.analyze_assets(
                            db=db,
                            assets=input_assets,
                        )
                    )
                except ImageAnalysisError as exc:
                    raise APIException(
                        status_code=400,
                        message=str(exc) or "Failed to analyze input images",
                    ) from exc
            try:
                planned = await self.planning_service.plan_storyboard(
                    prompt=project.prompt,
                    target_duration_seconds=project.target_duration_seconds,
                    aspect_ratio=project.aspect_ratio,
                    has_images=bool(input_assets),
                    provider=project.provider,
                    model=project.model,
                    resolution=project.resolution,
                    image_assets=image_asset_context,
                )
            except StoryboardPlanningError as exc:
                raise APIException(
                    status_code=400,
                    message=str(exc) or "Failed to plan storyboard with OpenAI",
                ) from exc
            project.expanded_brief = planned.expanded_brief
            project.status = "storyboard_ready"
            project.progress = 15
            fallback_input_asset_ids = [asset.id for asset in input_assets[:3]]
            for planned_scene in planned.scenes:
                db.add(
                    VideoStoryboardScene(
                        project_id=project.id,
                        scene_index=planned_scene.scene_index,
                        scene_role=planned_scene.scene_role,
                        title=planned_scene.title,
                        prompt_text=planned_scene.prompt_text,
                        narration_text=planned_scene.narration_text,
                        sound_design=planned_scene.sound_design,
                        duration_seconds=planned_scene.duration_seconds,
                        input_asset_ids=(
                            planned_scene.input_asset_ids or fallback_input_asset_ids
                        ),
                        status="draft",
                    )
                )
            await db.flush()
            project_id = project.id
        return await self.get_project(db, user_id, project_id)

    async def update_storyboard(
        self,
        db: AsyncSession,
        user_id: int,
        project_id: int,
        request: VideoStoryboardUpdateRequest,
    ) -> VideoProjectResponse:
        """Replace the storyboard for an editable project."""
        async with transaction(db):
            project = await self._get_project_model(db, user_id, project_id)
            if project.status not in self.EDITABLE_STATUSES:
                raise APIException(
                    status_code=400,
                    message="Storyboard cannot be changed after generation starts",
                )
            asset_ids = {
                asset.id
                for asset in project.assets
                if asset.asset_type == "input_image"
            }
            for scene_request in request.scenes:
                unknown_assets = set(scene_request.input_asset_ids) - asset_ids
                if unknown_assets:
                    raise APIException(
                        status_code=400,
                        message="Storyboard references assets outside this project",
                    )
            task_scene_ids = {
                task.scene_id for task in project.tasks if task.scene_id is not None
            }
            requested_scene_indexes = {scene.scene_index for scene in request.scenes}
            existing_scenes_by_index = {
                scene.scene_index: scene for scene in project.scenes
            }

            for scene in list(project.scenes):
                if scene.scene_index in requested_scene_indexes:
                    continue
                if scene.id in task_scene_ids:
                    raise APIException(
                        status_code=400,
                        message=(
                            "Storyboard scenes with generation history cannot be "
                            "removed"
                        ),
                    )
                await db.delete(scene)

            for scene_request in sorted(
                request.scenes, key=lambda scene: scene.scene_index
            ):
                existing_scene = existing_scenes_by_index.get(scene_request.scene_index)
                if existing_scene:
                    self._apply_scene_update(existing_scene, scene_request)
                else:
                    db.add(self._build_scene(project.id, scene_request))
            project.status = "storyboard_ready"
            project.progress = 15
            project.error_code = None
            project.error_message = None
            await db.flush()
            project_id = project.id
        return await self.get_project(db, user_id, project_id)

    async def start_generation(
        self,
        db: AsyncSession,
        user_id: int,
        project_id: int,
        force: bool = False,
    ) -> VideoProjectResponse:
        """Queue a storyboard for provider generation."""
        async with transaction(db):
            project = await self._get_project_model(db, user_id, project_id)
            if project.status in self.GENERATION_STATUSES and not force:
                raise APIException(
                    status_code=400, message="Generation already started"
                )
            if project.status == "completed" and not force:
                raise APIException(
                    status_code=400, message="Project is already completed"
                )
            if not project.scenes:
                raise APIException(
                    status_code=400, message="Generate a storyboard first"
                )
            self.registry.validate_generation_options(
                provider=project.provider,
                model=project.model,
                aspect_ratio=project.aspect_ratio,
                resolution=project.resolution,
                has_images=any(
                    asset.asset_type == "input_image" for asset in project.assets
                ),
            )
            project.status = "queued"
            project.progress = 20
            project.error_code = None
            project.error_message = None
            await db.flush()

        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "app.schedule.jobs.video_generation.generate_video_project",
                args=[project_id],
                queue="video_generation",
            )
        except Exception as exc:
            logger.exception("Failed to enqueue video generation task")
            async with transaction(db):
                project = await self._get_project_model(db, user_id, project_id)
                project.status = "failed"
                project.error_code = "QUEUE_UNAVAILABLE"
                project.error_message = "Failed to enqueue video generation task"
                await db.flush()
            raise APIException(
                status_code=500,
                message="Failed to enqueue video generation task",
            ) from exc

        return await self.get_project(db, user_id, project_id)

    async def retry_scene_generation(
        self,
        db: AsyncSession,
        user_id: int,
        project_id: int,
        scene_id: int,
    ) -> VideoProjectResponse:
        """Queue one failed scene for retry and continue project generation."""
        async with transaction(db):
            project = await self._get_project_model(db, user_id, project_id)
            if project.status in self.GENERATION_STATUSES:
                raise APIException(
                    status_code=400, message="Generation already started"
                )
            if project.status == "completed":
                raise APIException(
                    status_code=400, message="Project is already completed"
                )

            scene = next(
                (item for item in project.scenes if item.id == scene_id),
                None,
            )
            if not scene:
                raise APIException(
                    status_code=404, message="Storyboard scene not found"
                )
            if scene.status != "failed":
                raise APIException(
                    status_code=400, message="Only failed scenes can be retried"
                )

            self.registry.validate_generation_options(
                provider=project.provider,
                model=project.model,
                aspect_ratio=project.aspect_ratio,
                resolution=project.resolution,
                has_images=any(
                    asset.asset_type == "input_image" for asset in project.assets
                ),
            )
            project.status = "queued"
            project.progress = max(project.progress, 20)
            project.error_code = None
            project.error_message = None
            scene.status = "queued"
            scene.output_asset_id = None
            await db.flush()

        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "app.schedule.jobs.video_generation.retry_video_project_scene",
                args=[project_id, scene_id],
                queue="video_generation",
            )
        except Exception as exc:
            logger.exception("Failed to enqueue video scene retry task")
            async with transaction(db):
                project = await self._get_project_model(db, user_id, project_id)
                scene = next(
                    (item for item in project.scenes if item.id == scene_id),
                    None,
                )
                project.status = "failed"
                project.error_code = "QUEUE_UNAVAILABLE"
                project.error_message = "Failed to enqueue video scene retry task"
                if scene:
                    scene.status = "failed"
                await db.flush()
            raise APIException(
                status_code=500,
                message="Failed to enqueue video scene retry task",
            ) from exc

        return await self.get_project(db, user_id, project_id)

    async def cancel_project(
        self, db: AsyncSession, user_id: int, project_id: int
    ) -> VideoProjectResponse:
        """Cancel a queued or running project."""
        project = await self._get_project_model(db, user_id, project_id)
        if project.status in {"completed", "canceled"}:
            return VideoProjectResponse.model_validate(project)

        for task in project.tasks:
            if task.provider_task_id and task.status in {"submitted", "running"}:
                try:
                    client = self.provider_factory.get_client(task.provider)
                    await client.cancel(task.provider_task_id)
                except Exception:
                    pass

        async with transaction(db):
            project = await self._get_project_model(db, user_id, project_id)
            project.status = "canceled"
            project.progress = min(project.progress, 95)
            for task in project.tasks:
                if task.status not in {"succeeded", "failed"}:
                    task.status = "canceled"
            await db.flush()
        return await self.get_project(db, user_id, project_id)

    async def _get_project_model(
        self, db: AsyncSession, user_id: int, project_id: int
    ) -> VideoProject:
        query = (
            select(VideoProject)
            .options(
                selectinload(VideoProject.assets),
                selectinload(VideoProject.scenes),
                selectinload(VideoProject.tasks),
                selectinload(VideoProject.exports),
            )
            .where(VideoProject.id == project_id, VideoProject.user_id == user_id)
        )
        result = await db.execute(query)
        project = result.scalar_one_or_none()
        if not project:
            raise APIException(status_code=404, message="Video project not found")
        return project

    async def _get_user_assets(
        self, db: AsyncSession, user_id: int, asset_ids: List[int]
    ) -> List[VideoAsset]:
        if not asset_ids:
            return []
        result = await db.execute(
            select(VideoAsset).where(
                VideoAsset.user_id == user_id,
                VideoAsset.id.in_(asset_ids),
                VideoAsset.asset_type == "input_image",
            )
        )
        assets = result.scalars().all()
        if len(assets) != len(set(asset_ids)):
            raise APIException(status_code=400, message="Invalid video asset ids")
        return assets

    def _derive_title(self, prompt: str) -> str:
        normalized = " ".join(prompt.split())
        return normalized[:60] or "Untitled video"

    def _build_scene(
        self, project_id: int, scene_request: VideoStoryboardSceneUpdate
    ) -> VideoStoryboardScene:
        return VideoStoryboardScene(
            project_id=project_id,
            scene_index=scene_request.scene_index,
            scene_role=scene_request.scene_role,
            title=scene_request.title,
            prompt_text=scene_request.prompt_text,
            narration_text=scene_request.narration_text,
            sound_design=scene_request.sound_design,
            duration_seconds=scene_request.duration_seconds,
            input_asset_ids=scene_request.input_asset_ids,
            status="draft",
        )

    def _apply_scene_update(
        self,
        scene: VideoStoryboardScene,
        scene_request: VideoStoryboardSceneUpdate,
    ):
        scene.scene_role = scene_request.scene_role
        scene.title = scene_request.title
        scene.prompt_text = scene_request.prompt_text
        scene.narration_text = scene_request.narration_text
        scene.sound_design = scene_request.sound_design
        scene.duration_seconds = scene_request.duration_seconds
        scene.input_asset_ids = scene_request.input_asset_ids
        scene.output_asset_id = None
        scene.status = "draft"


def get_video_asset_service() -> VideoAssetService:
    """Get VideoAssetService instance."""
    return VideoAssetService()


def get_video_project_service() -> VideoProjectService:
    """Get VideoProjectService instance."""
    return VideoProjectService()
