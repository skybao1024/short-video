"""add_video_generation_tables

Revision ID: 20260613_video_generation
Revises: 9284e3bc3574
Create Date: 2026-06-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_video_generation"
down_revision: Union[str, None] = "9284e3bc3574"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "video_projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("expanded_brief", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=20), nullable=False),
        sa.Column("resolution", sa.String(length=20), nullable=False),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("final_video_asset_id", sa.Integer(), nullable=True),
        sa.Column("final_video_file_key", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_file_key", sa.String(length=1024), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("estimated_cost_credits", sa.DECIMAL(12, 4), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
        sa.Column("generation_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "generation_completed_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_video_projects_id"), "video_projects", ["id"])
    op.create_index(op.f("ix_video_projects_user_id"), "video_projects", ["user_id"])
    op.create_index(op.f("ix_video_projects_status"), "video_projects", ["status"])

    op.create_table(
        "video_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("file_key", sa.String(length=1024), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.DECIMAL(8, 2), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_video_assets_id"), "video_assets", ["id"])
    op.create_index(op.f("ix_video_assets_user_id"), "video_assets", ["user_id"])
    op.create_index(op.f("ix_video_assets_project_id"), "video_assets", ["project_id"])
    op.create_index(op.f("ix_video_assets_asset_type"), "video_assets", ["asset_type"])
    op.create_index(op.f("ix_video_assets_status"), "video_assets", ["status"])

    op.create_table(
        "video_storyboard_scenes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("scene_role", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("narration_text", sa.Text(), nullable=True),
        sa.Column("sound_design", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("input_asset_ids", sa.JSON(), nullable=True),
        sa.Column("output_asset_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["output_asset_id"], ["video_assets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_video_storyboard_scenes_id"), "video_storyboard_scenes", ["id"]
    )
    op.create_index(
        op.f("ix_video_storyboard_scenes_status"),
        "video_storyboard_scenes",
        ["status"],
    )

    op.create_table(
        "video_generation_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("provider_task_id", sa.String(length=255), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("output_asset_id", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["output_asset_id"], ["video_assets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["video_storyboard_scenes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_video_generation_tasks_id"), "video_generation_tasks", ["id"]
    )
    op.create_index(
        op.f("ix_video_generation_tasks_scene_id"),
        "video_generation_tasks",
        ["scene_id"],
    )
    op.create_index(
        op.f("ix_video_generation_tasks_provider_task_id"),
        "video_generation_tasks",
        ["provider_task_id"],
    )
    op.create_index(
        op.f("ix_video_generation_tasks_status"),
        "video_generation_tasks",
        ["status"],
    )

    op.create_table(
        "video_exports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_asset_ids", sa.JSON(), nullable=True),
        sa.Column("output_asset_id", sa.Integer(), nullable=True),
        sa.Column("render_params", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["output_asset_id"], ["video_assets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_video_exports_id"), "video_exports", ["id"])
    op.create_index(op.f("ix_video_exports_status"), "video_exports", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_video_exports_status"), table_name="video_exports")
    op.drop_index(op.f("ix_video_exports_id"), table_name="video_exports")
    op.drop_table("video_exports")
    op.drop_index(
        op.f("ix_video_generation_tasks_status"), table_name="video_generation_tasks"
    )
    op.drop_index(
        op.f("ix_video_generation_tasks_provider_task_id"),
        table_name="video_generation_tasks",
    )
    op.drop_index(
        op.f("ix_video_generation_tasks_scene_id"),
        table_name="video_generation_tasks",
    )
    op.drop_index(
        op.f("ix_video_generation_tasks_id"), table_name="video_generation_tasks"
    )
    op.drop_table("video_generation_tasks")
    op.drop_index(
        op.f("ix_video_storyboard_scenes_status"),
        table_name="video_storyboard_scenes",
    )
    op.drop_index(
        op.f("ix_video_storyboard_scenes_id"),
        table_name="video_storyboard_scenes",
    )
    op.drop_table("video_storyboard_scenes")
    op.drop_index(op.f("ix_video_assets_status"), table_name="video_assets")
    op.drop_index(op.f("ix_video_assets_asset_type"), table_name="video_assets")
    op.drop_index(op.f("ix_video_assets_project_id"), table_name="video_assets")
    op.drop_index(op.f("ix_video_assets_user_id"), table_name="video_assets")
    op.drop_index(op.f("ix_video_assets_id"), table_name="video_assets")
    op.drop_table("video_assets")
    op.drop_index(op.f("ix_video_projects_status"), table_name="video_projects")
    op.drop_index(op.f("ix_video_projects_user_id"), table_name="video_projects")
    op.drop_index(op.f("ix_video_projects_id"), table_name="video_projects")
    op.drop_table("video_projects")
