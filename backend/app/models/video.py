from sqlalchemy import (
    DECIMAL,
    JSON,
    TIMESTAMP,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.user import User

from .base import BaseModel


class VideoProject(BaseModel):
    """Promotional video project owned by a client user."""

    __tablename__ = "video_projects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    prompt = Column(Text, nullable=False)
    expanded_brief = Column(Text, nullable=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    aspect_ratio = Column(String(20), nullable=False, default="9:16")
    resolution = Column(String(20), nullable=False, default="720p")
    target_duration_seconds = Column(Integer, nullable=False, default=24)
    status = Column(String(30), nullable=False, default="draft", index=True)
    progress = Column(Integer, nullable=False, default=0)
    final_video_asset_id = Column(Integer, nullable=True)
    final_video_file_key = Column(String(1024), nullable=True)
    thumbnail_file_key = Column(String(1024), nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    estimated_cost_credits = Column(DECIMAL(12, 4), nullable=True)
    provider_metadata = Column(JSON, nullable=True)
    generation_started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    generation_completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    user = relationship(User, foreign_keys=[user_id])
    assets = relationship(
        "VideoAsset", back_populates="project", cascade="all, delete-orphan"
    )
    scenes = relationship(
        "VideoStoryboardScene",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="VideoStoryboardScene.scene_index",
    )
    tasks = relationship(
        "VideoGenerationTask", back_populates="project", cascade="all, delete-orphan"
    )
    exports = relationship(
        "VideoExport", back_populates="project", cascade="all, delete-orphan"
    )


class VideoAsset(BaseModel):
    """Input or generated media asset for a promotional video project."""

    __tablename__ = "video_assets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(
        Integer, ForeignKey("video_projects.id"), nullable=True, index=True
    )
    asset_type = Column(String(40), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="uploading", index=True)
    file_key = Column(String(1024), nullable=False)
    file_name = Column(String(255), nullable=True)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(DECIMAL(8, 2), nullable=True)
    source_url = Column(String(2048), nullable=True)
    provider = Column(String(50), nullable=True)
    provider_metadata = Column(JSON, nullable=True)

    user = relationship(User, foreign_keys=[user_id])
    project = relationship("VideoProject", back_populates="assets")


class VideoStoryboardScene(BaseModel):
    """Single storyboard scene that maps to a provider generation task."""

    __tablename__ = "video_storyboard_scenes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("video_projects.id"), nullable=False)
    scene_index = Column(Integer, nullable=False)
    scene_role = Column(String(40), nullable=False)
    title = Column(String(255), nullable=False)
    prompt_text = Column(Text, nullable=False)
    narration_text = Column(Text, nullable=True)
    sound_design = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=False, default=8)
    input_asset_ids = Column(JSON, nullable=True)
    output_asset_id = Column(Integer, ForeignKey("video_assets.id"), nullable=True)
    status = Column(String(30), nullable=False, default="draft", index=True)

    project = relationship("VideoProject", back_populates="scenes")


class VideoGenerationTask(BaseModel):
    """Provider task for generating a single video scene."""

    __tablename__ = "video_generation_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("video_projects.id"), nullable=False)
    scene_id = Column(
        Integer, ForeignKey("video_storyboard_scenes.id"), nullable=False, index=True
    )
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    provider_task_id = Column(String(255), nullable=True, index=True)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    failure_code = Column(String(100), nullable=True)
    failure_message = Column(Text, nullable=True)
    output_asset_id = Column(Integer, ForeignKey("video_assets.id"), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    submitted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    project = relationship("VideoProject", back_populates="tasks")
    scene = relationship("VideoStoryboardScene")


class VideoExport(BaseModel):
    """Final video assembly task."""

    __tablename__ = "video_exports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("video_projects.id"), nullable=False)
    status = Column(String(30), nullable=False, default="pending", index=True)
    input_asset_ids = Column(JSON, nullable=True)
    output_asset_id = Column(Integer, ForeignKey("video_assets.id"), nullable=True)
    render_params = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    project = relationship("VideoProject", back_populates="exports")
