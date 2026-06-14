import asyncio
import logging
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.base import create_scheduler_engine, create_scheduler_session_factory
from app.models.video import (
    VideoAsset,
    VideoExport,
    VideoGenerationTask,
    VideoProject,
    VideoStoryboardScene,
)
from app.services.client.video_providers import (
    ProviderInputImage,
    VideoProviderError,
    VideoProviderFactory,
    VideoProviderRequest,
    VideoProviderTask,
    encode_image_bytes,
    normalize_veo_duration_seconds,
)
from app.services.common.s3_service import S3Service

logger = logging.getLogger(__name__)


@celery_app.task(name="app.schedule.jobs.video_generation.generate_video_project")
def generate_video_project(project_id: int):
    """Generate all scenes for a video project and export the final video."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_generate_video_project(project_id))
    finally:
        loop.close()


@celery_app.task(name="app.schedule.jobs.video_generation.retry_video_project_scene")
def retry_video_project_scene(project_id: int, scene_id: int):
    """Retry one failed scene, then continue the project if possible."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _generate_video_project(project_id, retry_scene_id=scene_id)
        )
    finally:
        loop.close()


async def _generate_video_project(project_id: int, retry_scene_id: int = None) -> Dict:
    scheduler_engine = create_scheduler_engine()
    SchedulerSessionLocal = create_scheduler_session_factory(scheduler_engine)
    try:
        async with SchedulerSessionLocal() as db:
            await _run_generation(db, project_id, retry_scene_id=retry_scene_id)
        return {
            "status": "success",
            "project_id": project_id,
            "retry_scene_id": retry_scene_id,
        }
    except VideoProviderError as exc:
        logger.error(
            "Video provider flow failed for project %s: %s",
            project_id,
            exc.code,
            exc_info=True,
        )
        if exc.code == "PROVIDER_CANCELED":
            return {"status": "canceled", "project_id": project_id}
        async with SchedulerSessionLocal() as db:
            await _fail_project(db, project_id, exc.code, exc.message)
        return {
            "status": "failed",
            "project_id": project_id,
            "error_code": exc.code,
        }
    except Exception as exc:
        logger.error(
            "Video generation failed for project %s", project_id, exc_info=True
        )
        async with SchedulerSessionLocal() as db:
            await _fail_project(db, project_id, "WORKER_ERROR", str(exc))
        raise
    finally:
        await scheduler_engine.dispose()


async def _run_generation(
    db: AsyncSession, project_id: int, retry_scene_id: int = None
):
    project = await _load_project(db, project_id)
    if project.status == "canceled":
        return
    project.status = "generating"
    project.progress = max(project.progress, 25)
    project.error_code = None
    project.error_message = None
    project.generation_started_at = datetime.now(UTC)
    await db.commit()

    s3_service = S3Service()
    provider_factory = VideoProviderFactory()
    scenes = sorted(project.scenes, key=lambda scene: scene.scene_index)
    for index, scene in enumerate(scenes, start=1):
        project = await _load_project(db, project_id)
        if project.status == "canceled":
            return
        scene = next(item for item in project.scenes if item.id == scene.id)
        if scene.status == "completed" and scene.output_asset_id:
            clip_asset = None
        else:
            clip_asset = await _generate_scene(
                db=db,
                project=project,
                scene=scene,
                s3_service=s3_service,
                provider_factory=provider_factory,
            )
        project = await _load_project(db, project_id)
        completed_count = _completed_scene_count(project)
        if clip_asset or scene.status == "completed":
            project.progress = min(85, 25 + round(completed_count / len(scenes) * 55))
        await db.commit()

    project = await _load_project(db, project_id)
    if project.status == "canceled":
        return
    clip_asset_ids = _completed_clip_asset_ids(project)
    final_asset = await _export_project_video(
        db=db,
        project=project,
        clip_asset_ids=clip_asset_ids,
        s3_service=s3_service,
    )
    project.status = "completed"
    project.progress = 100
    project.final_video_asset_id = final_asset.id
    project.final_video_file_key = final_asset.file_key
    project.generation_completed_at = datetime.now(UTC)
    await db.commit()


async def _generate_scene(
    db: AsyncSession,
    project: VideoProject,
    scene: VideoStoryboardScene,
    s3_service: S3Service,
    provider_factory: VideoProviderFactory,
) -> VideoAsset:
    provider_request = _build_provider_request(project, scene, s3_service)
    task = VideoGenerationTask(
        project_id=project.id,
        scene_id=scene.id,
        provider=project.provider,
        model=project.model,
        status="pending",
        request_payload=_sanitize_provider_request(provider_request),
    )
    db.add(task)
    scene.status = "generating"
    await db.flush()

    client = provider_factory.get_client(project.provider)
    try:
        provider_task = await _submit_provider_task_with_retry(
            client=client,
            provider_request=provider_request,
            task=task,
            db=db,
        )
        task.provider_task_id = provider_task.provider_task_id
        task.response_payload = provider_task.raw_response
        task.status = "submitted"
        task.failure_code = None
        task.failure_message = None
        task.submitted_at = datetime.now(UTC)
        await db.commit()

        provider_status = await _poll_until_finished(client, task.provider_task_id)
        task.response_payload = provider_status.raw_response
        if provider_status.status == "canceled":
            task.status = "canceled"
            task.completed_at = datetime.now(UTC)
            scene.status = "canceled"
            project.status = "canceled"
            await db.commit()
            raise VideoProviderError(
                provider_status.failure_code or "PROVIDER_CANCELED",
                provider_status.failure_message or "Provider task was canceled",
            )
        if provider_status.status == "failed":
            task.status = "failed"
            task.failure_code = provider_status.failure_code
            task.failure_message = provider_status.failure_message
            task.completed_at = datetime.now(UTC)
            scene.status = "failed"
            await _fail_project(
                db,
                project.id,
                provider_status.failure_code or "PROVIDER_FAILED",
                provider_status.failure_message or "Video generation failed",
                commit=False,
            )
            await db.commit()
            raise VideoProviderError(
                provider_status.failure_code or "PROVIDER_FAILED",
                provider_status.failure_message or "Video generation failed",
            )
        if not provider_status.output_ref:
            raise VideoProviderError(
                "PROVIDER_EMPTY_OUTPUT", "Provider did not return a video output"
            )

        output_bytes = await client.download_output(provider_status.output_ref)
        file_key = s3_service.generate_file_key(
            user_id=project.user_id,
            file_name=f"scene-{scene.scene_index}.mp4",
            module="video-projects",
            module_id=project.id,
            sub_path="generated-clips",
        )
        s3_service.upload_bytes(
            file_key=file_key,
            data=output_bytes,
            content_type="video/mp4",
            metadata={"project_id": project.id, "scene_id": scene.id},
        )
        asset = VideoAsset(
            user_id=project.user_id,
            project_id=project.id,
            asset_type="generated_clip",
            status="ready",
            file_key=file_key,
            file_name=f"scene-{scene.scene_index}.mp4",
            mime_type="video/mp4",
            file_size=len(output_bytes),
            duration_seconds=provider_request.duration_seconds,
            provider=project.provider,
            provider_metadata={"provider_task_id": task.provider_task_id},
        )
        db.add(asset)
        await db.flush()
        task.status = "succeeded"
        task.output_asset_id = asset.id
        task.completed_at = datetime.now(UTC)
        scene.status = "completed"
        scene.output_asset_id = asset.id
        await db.commit()
        return asset
    except VideoProviderError as exc:
        if exc.code == "PROVIDER_CANCELED":
            raise
        task.status = "failed"
        task.failure_code = exc.code
        task.failure_message = exc.message
        task.completed_at = datetime.now(UTC)
        scene.status = "failed"
        await _fail_project(db, project.id, exc.code, exc.message, commit=False)
        await db.commit()
        raise


def _completed_scene_count(project: VideoProject) -> int:
    """Count scenes with completed output clips."""
    return sum(
        1
        for scene in project.scenes
        if scene.status == "completed" and scene.output_asset_id
    )


def _completed_clip_asset_ids(project: VideoProject) -> List[int]:
    """Return completed clip asset ids or block final export."""
    scenes = sorted(project.scenes, key=lambda scene: scene.scene_index)
    missing_scene_indexes = [
        scene.scene_index
        for scene in scenes
        if scene.status != "completed" or not scene.output_asset_id
    ]
    if missing_scene_indexes:
        missing_text = ", ".join(str(index) for index in missing_scene_indexes)
        raise VideoProviderError(
            "EXPORT_INCOMPLETE_SCENES",
            f"Final export requires every scene to complete first: {missing_text}",
        )
    return [scene.output_asset_id for scene in scenes]


async def _submit_provider_task_with_retry(
    client,
    provider_request: VideoProviderRequest,
    task: VideoGenerationTask,
    db: AsyncSession,
) -> VideoProviderTask:
    """Submit a provider task with bounded retries for transient HTTP errors."""
    max_retries = max(0, int(settings.VIDEO_PROVIDER_SUBMIT_MAX_RETRIES))
    attempt = 0

    while True:
        try:
            return await client.submit(provider_request)
        except VideoProviderError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise

            attempt += 1
            task.retry_count = attempt
            task.status = "retrying"
            task.failure_code = exc.code
            task.failure_message = exc.message
            await db.commit()

            delay_seconds = min(
                settings.VIDEO_PROVIDER_SUBMIT_RETRY_BACKOFF_SECONDS * attempt,
                settings.VIDEO_PROVIDER_SUBMIT_RETRY_MAX_BACKOFF_SECONDS,
            )
            logger.warning(
                "Provider submit failed for project %s scene %s with %s; "
                "retrying attempt %s/%s in %s seconds",
                task.project_id,
                task.scene_id,
                exc.code,
                attempt,
                max_retries,
                delay_seconds,
            )
            await asyncio.sleep(delay_seconds)


async def _poll_until_finished(client, provider_task_id: str):
    elapsed = 0
    while elapsed <= settings.VIDEO_PROVIDER_MAX_POLL_SECONDS:
        status = await client.poll(provider_task_id)
        if status.status in {"succeeded", "failed", "canceled"}:
            return status
        await asyncio.sleep(settings.VIDEO_PROVIDER_POLL_INTERVAL_SECONDS)
        elapsed += settings.VIDEO_PROVIDER_POLL_INTERVAL_SECONDS
    raise VideoProviderError(
        "PROVIDER_TIMEOUT",
        "Video generation timed out before the provider returned output",
        retryable=True,
    )


async def _export_project_video(
    db: AsyncSession,
    project: VideoProject,
    clip_asset_ids: List[int],
    s3_service: S3Service,
) -> VideoAsset:
    export = VideoExport(
        project_id=project.id,
        status="running",
        input_asset_ids=clip_asset_ids,
        render_params={
            "aspect_ratio": project.aspect_ratio,
            "resolution": project.resolution,
            "engine": "ffmpeg",
        },
        started_at=datetime.now(UTC),
    )
    db.add(export)
    await db.flush()

    try:
        clip_assets = await _load_assets(db, project.id, clip_asset_ids)
        if not clip_assets:
            raise VideoProviderError("EXPORT_NO_CLIPS", "No generated clips to export")
        output_bytes = _combine_clips_with_ffmpeg(clip_assets, s3_service)
        final_key = s3_service.generate_file_key(
            user_id=project.user_id,
            file_name="final-video.mp4",
            module="video-projects",
            module_id=project.id,
            sub_path="exports",
        )
        s3_service.upload_bytes(
            file_key=final_key,
            data=output_bytes,
            content_type="video/mp4",
            metadata={"project_id": project.id, "asset_type": "final_video"},
        )
        final_asset = VideoAsset(
            user_id=project.user_id,
            project_id=project.id,
            asset_type="final_video",
            status="ready",
            file_key=final_key,
            file_name="final-video.mp4",
            mime_type="video/mp4",
            file_size=len(output_bytes),
            duration_seconds=sum(asset.duration_seconds or 0 for asset in clip_assets),
            provider=project.provider,
        )
        db.add(final_asset)
        await db.flush()
        export.status = "completed"
        export.output_asset_id = final_asset.id
        export.completed_at = datetime.now(UTC)
        await db.commit()
        return final_asset
    except VideoProviderError as exc:
        export.status = "failed"
        export.error_message = exc.message
        export.completed_at = datetime.now(UTC)
        await _fail_project(db, project.id, exc.code, exc.message, commit=False)
        await db.commit()
        raise


def _combine_clips_with_ffmpeg(
    clip_assets: List[VideoAsset], s3_service: S3Service
) -> bytes:
    if len(clip_assets) == 1:
        return s3_service.download_bytes(clip_assets[0].file_key)
    if not shutil.which("ffmpeg"):
        raise VideoProviderError("FFMPEG_MISSING", "FFmpeg is not installed")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        concat_lines = []
        for index, asset in enumerate(clip_assets, start=1):
            clip_path = temp_path / f"clip-{index}.mp4"
            clip_path.write_bytes(s3_service.download_bytes(asset.file_key))
            escaped_path = str(clip_path).replace("'", "'\\''")
            concat_lines.append(f"file '{escaped_path}'")
        concat_path = temp_path / "concat.txt"
        concat_path.write_text("\n".join(concat_lines), encoding="utf-8")
        output_path = temp_path / "final-video.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if completed.returncode != 0:
            raise VideoProviderError("FFMPEG_FAILED", "Final video export failed")
        return output_path.read_bytes()


def _build_provider_request(
    project: VideoProject,
    scene: VideoStoryboardScene,
    s3_service: S3Service,
) -> VideoProviderRequest:
    input_assets = _scene_input_assets(project, scene)
    input_images = []
    for asset in input_assets[:3]:
        image = ProviderInputImage(
            url=s3_service.generate_presigned_download_url(
                asset.file_key, expires_in=3600
            ),
            mime_type=asset.mime_type,
        )
        if project.provider == "google_veo":
            image.data_base64 = encode_image_bytes(
                s3_service.download_bytes(asset.file_key)
            )
        input_images.append(image)
    prompt = (
        f"{scene.prompt_text}\n\n"
        f"Narration intent: {scene.narration_text or ''}\n"
        f"Sound direction: {scene.sound_design or ''}"
    )
    return VideoProviderRequest(
        prompt_text=prompt,
        model=project.model,
        input_images=input_images,
        aspect_ratio=project.aspect_ratio,
        duration_seconds=_provider_scene_duration_seconds(
            project=project,
            scene=scene,
            has_images=bool(input_images),
        ),
        resolution=project.resolution,
        audio_mode="auto",
    )


def _scene_input_assets(
    project: VideoProject, scene: VideoStoryboardScene
) -> List[VideoAsset]:
    input_ids = set(scene.input_asset_ids or [])
    return [
        asset
        for asset in project.assets
        if asset.asset_type == "input_image"
        and (not input_ids or asset.id in input_ids)
    ]


def _provider_scene_duration_seconds(
    project: VideoProject,
    scene: VideoStoryboardScene,
    has_images: bool,
) -> int:
    if project.provider == "google_veo":
        return normalize_veo_duration_seconds(
            scene.duration_seconds,
            project.resolution,
            has_images=has_images,
        )
    return scene.duration_seconds


def _sanitize_provider_request(request: VideoProviderRequest) -> Dict:
    return {
        "prompt_text": request.prompt_text,
        "model": request.model,
        "input_image_count": len(request.input_images),
        "aspect_ratio": request.aspect_ratio,
        "duration_seconds": request.duration_seconds,
        "resolution": request.resolution,
        "seed": request.seed,
        "audio_mode": request.audio_mode,
        "provider_params": request.provider_params,
    }


async def _load_project(db: AsyncSession, project_id: int) -> VideoProject:
    result = await db.execute(
        select(VideoProject)
        .options(
            selectinload(VideoProject.assets),
            selectinload(VideoProject.scenes),
            selectinload(VideoProject.tasks),
            selectinload(VideoProject.exports),
        )
        .where(VideoProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise VideoProviderError("PROJECT_NOT_FOUND", "Video project not found")
    return project


async def _load_assets(
    db: AsyncSession, project_id: int, asset_ids: List[int]
) -> List[VideoAsset]:
    result = await db.execute(
        select(VideoAsset).where(
            VideoAsset.project_id == project_id,
            VideoAsset.id.in_(asset_ids),
        )
    )
    assets = result.scalars().all()
    asset_by_id = {asset.id: asset for asset in assets}
    return [asset_by_id[asset_id] for asset_id in asset_ids if asset_id in asset_by_id]


async def _fail_project(
    db: AsyncSession,
    project_id: int,
    error_code: str,
    error_message: str,
    commit: bool = True,
):
    result = await db.execute(select(VideoProject).where(VideoProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        return
    project.status = "failed"
    project.error_code = error_code
    project.error_message = error_message[:2000] if error_message else None
    project.generation_completed_at = datetime.now(UTC)
    if commit:
        await db.commit()
