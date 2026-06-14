import json

import httpx
import pytest

from app.core.celery_app import celery_app
from app.exceptions.http_exceptions import APIException
from app.models.video import VideoProject, VideoStoryboardScene
from app.schedule.jobs.video_generation import (
    _completed_clip_asset_ids,
    _sanitize_provider_request,
    generate_video_project,
    retry_video_project_scene,
)
from app.schemas.client.video import VideoProjectCreateRequest
from app.services.client.prompt_planning import (
    OpenAIStoryboardPlanningClient,
    PlannedVideoScene,
    PlannedVideoStoryboard,
    PromptPlanningService,
    StoryboardPlanningError,
)
from app.services.client.image_analysis import (
    ImageAssetInput,
    OpenAIImageAnalysisClient,
)
from app.services.client.video import VideoAssetService
from app.services.client.video_model_registry import VideoModelRegistry
from app.services.client.video_providers import (
    GoogleVeoProviderClient,
    ProviderInputImage,
    RunwayVideoProviderClient,
    VideoProviderError,
    VideoProviderRequest,
    normalize_veo_duration_seconds,
)
from app.services.common.s3_service import S3Service


class FakeS3Service:
    def validate_file_type(self, file_name: str, allowed_types: list) -> bool:
        file_ext = file_name.split(".")[-1].lower()
        return file_ext in allowed_types


class FakeOpenAIStoryboardPlanningClient:
    def __init__(
        self,
        storyboard: PlannedVideoStoryboard = None,
        should_fail=False,
        configured=True,
    ):
        self.storyboard = storyboard
        self.should_fail = should_fail
        self.configured = configured
        self.calls = []

    def is_configured(self) -> bool:
        return self.configured

    async def plan_storyboard(
        self,
        prompt: str,
        target_duration_seconds: int,
        aspect_ratio: str,
        has_images: bool,
        duration_plan_seconds: list,
        provider: str = None,
        model: str = None,
        resolution: str = "720p",
        image_assets: list = None,
    ) -> PlannedVideoStoryboard:
        self.calls.append(
            {
                "prompt": prompt,
                "target_duration_seconds": target_duration_seconds,
                "aspect_ratio": aspect_ratio,
                "has_images": has_images,
                "duration_plan_seconds": duration_plan_seconds,
                "provider": provider,
                "model": model,
                "resolution": resolution,
                "image_assets": image_assets or [],
            }
        )
        if self.should_fail:
            raise StoryboardPlanningError("OpenAI test failure")
        return self.storyboard


def test_video_model_registry_validates_supported_model():
    registry = VideoModelRegistry()

    capability = registry.validate_generation_options(
        provider="runway",
        model="gen4.5",
        aspect_ratio="9:16",
        resolution="720p",
        has_images=True,
    )

    assert capability.provider == "runway"
    assert capability.model == "gen4.5"


def test_video_model_registry_rejects_unsupported_resolution():
    registry = VideoModelRegistry()

    with pytest.raises(APIException) as exc_info:
        registry.validate_generation_options(
            provider="runway",
            model="gen4.5",
            aspect_ratio="9:16",
            resolution="4k",
            has_images=False,
        )

    assert exc_info.value.status_code == 400


def test_video_project_prompt_allows_8000_characters():
    request = VideoProjectCreateRequest(
        prompt="A" * 8000,
        provider="google_veo",
        model="veo-3.1-generate-preview",
    )

    assert len(request.prompt) == 8000


def test_video_project_prompt_rejects_more_than_8000_characters():
    with pytest.raises(ValueError):
        VideoProjectCreateRequest(
            prompt="A" * 8001,
            provider="google_veo",
            model="veo-3.1-generate-preview",
        )


def test_prompt_planning_generates_three_scene_storyboard():
    planner = PromptPlanningService()

    storyboard = planner.plan_template_storyboard(
        prompt="A premium AI product for enterprise marketing teams",
        target_duration_seconds=24,
        aspect_ratio="9:16",
        has_images=True,
    )

    assert len(storyboard.scenes) == 3
    assert [scene.scene_role for scene in storyboard.scenes] == [
        "hook",
        "value",
        "cta",
    ]
    assert sum(scene.duration_seconds for scene in storyboard.scenes) == 24


@pytest.mark.parametrize(
    ("target_duration", "expected_scene_count"),
    [(8, 2), (45, 3), (60, 4)],
)
def test_prompt_planning_keeps_scene_durations_within_provider_limits(
    target_duration: int, expected_scene_count: int
):
    planner = PromptPlanningService()

    storyboard = planner.plan_template_storyboard(
        prompt="AI project scope assistant for software teams",
        target_duration_seconds=target_duration,
        aspect_ratio="9:16",
        has_images=False,
    )

    durations = [scene.duration_seconds for scene in storyboard.scenes]
    assert len(storyboard.scenes) == expected_scene_count
    assert sum(durations) == target_duration
    assert min(durations) >= 3
    assert max(durations) <= 15


def test_prompt_planning_uses_veo_compatible_duration_plan():
    planner = PromptPlanningService()

    storyboard = planner.plan_template_storyboard(
        prompt="AI project scope assistant for software teams",
        target_duration_seconds=45,
        aspect_ratio="9:16",
        has_images=True,
        provider="google_veo",
        resolution="1080p",
    )

    durations = [scene.duration_seconds for scene in storyboard.scenes]
    assert durations == [8, 8, 8, 8, 8, 8]
    assert storyboard.scenes[0].scene_role == "hook"
    assert storyboard.scenes[-1].scene_role == "cta"


@pytest.mark.asyncio
async def test_prompt_planning_uses_openai_storyboard_when_configured():
    ai_storyboard = PlannedVideoStoryboard(
        expanded_brief="AI generated campaign brief",
        scenes=[
            PlannedVideoScene(
                scene_index=1,
                scene_role="hook",
                title="AI Hook",
                prompt_text="Premium cinematic product reveal with clean motion.",
                narration_text="Open with the core promise.",
                sound_design="Bright intro hit.",
                duration_seconds=8,
            ),
            PlannedVideoScene(
                scene_index=2,
                scene_role="value",
                title="AI Value",
                prompt_text="Show practical customer use with polished lighting.",
                narration_text="Explain the strongest benefit.",
                sound_design="Steady branded pulse.",
                duration_seconds=8,
            ),
        ],
    )
    ai_client = FakeOpenAIStoryboardPlanningClient(storyboard=ai_storyboard)
    planner = PromptPlanningService(ai_planning_client=ai_client)

    storyboard = await planner.plan_storyboard(
        prompt="A premium AI product for enterprise marketing teams",
        target_duration_seconds=16,
        aspect_ratio="9:16",
        has_images=False,
    )

    assert storyboard.expanded_brief == "AI generated campaign brief"
    assert [scene.title for scene in storyboard.scenes] == ["AI Hook", "AI Value"]
    assert ai_client.calls[0]["duration_plan_seconds"] == [8, 8]


@pytest.mark.asyncio
async def test_prompt_planning_sends_veo_duration_plan_to_openai():
    ai_client = FakeOpenAIStoryboardPlanningClient(
        storyboard=PlannedVideoStoryboard(
            expanded_brief="AI generated Veo campaign brief",
            scenes=[
                PlannedVideoScene(
                    scene_index=1,
                    scene_role="hook",
                    title="AI Hook",
                    prompt_text="Premium cinematic product reveal with clean motion.",
                    narration_text="Open with the core promise.",
                    sound_design="Bright intro hit.",
                    duration_seconds=8,
                )
            ],
        )
    )
    planner = PromptPlanningService(ai_planning_client=ai_client)

    await planner.plan_storyboard(
        prompt="A premium AI product for enterprise marketing teams",
        target_duration_seconds=45,
        aspect_ratio="9:16",
        has_images=True,
        provider="google_veo",
        model="veo-3.1-generate-preview",
        resolution="1080p",
    )

    assert ai_client.calls[0]["duration_plan_seconds"] == [8, 8, 8, 8, 8, 8]
    assert ai_client.calls[0]["provider"] == "google_veo"
    assert ai_client.calls[0]["model"] == "veo-3.1-generate-preview"
    assert ai_client.calls[0]["resolution"] == "1080p"


@pytest.mark.asyncio
async def test_prompt_planning_raises_when_openai_planning_fails():
    ai_client = FakeOpenAIStoryboardPlanningClient(should_fail=True)
    planner = PromptPlanningService(ai_planning_client=ai_client)

    with pytest.raises(StoryboardPlanningError, match="OpenAI test failure"):
        await planner.plan_storyboard(
            prompt="A premium AI product for enterprise marketing teams",
            target_duration_seconds=24,
            aspect_ratio="9:16",
            has_images=True,
        )


@pytest.mark.asyncio
async def test_prompt_planning_requires_openai_configuration():
    ai_client = FakeOpenAIStoryboardPlanningClient(configured=False)
    planner = PromptPlanningService(ai_planning_client=ai_client)

    with pytest.raises(StoryboardPlanningError, match="OPENAI_API_KEY"):
        await planner.plan_storyboard(
            prompt="A premium AI product for enterprise marketing teams",
            target_duration_seconds=24,
            aspect_ratio="9:16",
            has_images=True,
        )


@pytest.mark.asyncio
async def test_openai_storyboard_client_uses_responses_structured_output():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        response_payload = {
            "expanded_brief": "Create a premium launch video.",
            "scenes": [
                {
                    "scene_index": 1,
                    "scene_role": "hook",
                    "title": "Launch Hook",
                    "prompt_text": "Cinematic product reveal in a premium studio.",
                    "narration_text": "Meet the launch moment.",
                    "sound_design": "Clean impact accent.",
                    "duration_seconds": 8,
                    "input_asset_ids": [101, 102],
                },
                {
                    "scene_index": 2,
                    "scene_role": "cta",
                    "title": "Action Close",
                    "prompt_text": "Confident final product moment with warm light.",
                    "narration_text": "Invite the viewer to act.",
                    "sound_design": "Resolved branded lift.",
                    "duration_seconds": 8,
                    "input_asset_ids": [102],
                },
            ],
        }

        assert request.url.path == "/v1/responses"
        assert payload["model"] == "gpt-test"
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        user_payload = json.loads(payload["input"][1]["content"][0]["text"])
        assert user_payload["image_assets"][0]["asset_id"] == 101
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(response_payload),
                            }
                        ],
                    }
                ]
            },
        )

    client = OpenAIStoryboardPlanningClient(
        api_key="test-key",
        base_url="https://api.openai.test/v1",
        model="gpt-test",
        transport=httpx.MockTransport(handler),
    )

    storyboard = await client.plan_storyboard(
        prompt="Launch a premium productivity app",
        target_duration_seconds=16,
        aspect_ratio="9:16",
        has_images=False,
        duration_plan_seconds=[8, 8],
        image_assets=[
            {
                "asset_id": 101,
                "caption": "Dark product dashboard",
                "asset_type": "product_ui",
                "visual_tags": ["dashboard"],
                "best_for_scene_roles": ["value"],
                "avoid_for_scene_roles": [],
            },
            {
                "asset_id": 102,
                "caption": "Mobile assessment screen",
                "asset_type": "mobile_ui",
                "visual_tags": ["mobile"],
                "best_for_scene_roles": ["cta"],
                "avoid_for_scene_roles": [],
            },
        ],
    )

    assert storyboard.expanded_brief == "Create a premium launch video."
    assert [scene.scene_index for scene in storyboard.scenes] == [1, 2]
    assert [scene.duration_seconds for scene in storyboard.scenes] == [8, 8]
    assert [scene.input_asset_ids for scene in storyboard.scenes] == [
        [101, 102],
        [102],
    ]


def test_video_asset_validation_rejects_non_image_file():
    service = VideoAssetService(s3_service=FakeS3Service())

    with pytest.raises(APIException) as exc_info:
        service._validate_input_image(
            file_name="brief.pdf",
            file_type="application/pdf",
            file_size=1024,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_openai_image_analysis_client_uses_multimodal_responses_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        user_content = payload["input"][1]["content"]

        assert request.url.path == "/v1/responses"
        assert payload["model"] == "gpt-vision-test"
        assert payload["text"]["format"]["name"] == "video_reference_image_analysis"
        assert user_content[1]["text"] == "Asset 77: product.png"
        assert user_content[2]["type"] == "input_image"
        assert user_content[2]["detail"] == "original"
        assert user_content[2]["image_url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "assets": [
                                            {
                                                "asset_id": 77,
                                                "caption": "Dark product UI dashboard.",
                                                "asset_type": "product_ui",
                                                "visual_tags": [
                                                    "dark mode",
                                                    "dashboard",
                                                ],
                                                "best_for_scene_roles": ["value"],
                                                "avoid_for_scene_roles": [
                                                    "human close-up"
                                                ],
                                            }
                                        ]
                                    }
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    client = OpenAIImageAnalysisClient(
        api_key="test-key",
        base_url="https://api.openai.test/v1",
        model="gpt-vision-test",
        detail="original",
        transport=httpx.MockTransport(handler),
    )

    analyses = await client.analyze_assets(
        [
            ImageAssetInput(
                asset_id=77,
                file_name="product.png",
                mime_type="image/png",
                data_base64="base64-image",
            )
        ]
    )

    assert analyses[0].asset_id == 77
    assert analyses[0].caption == "Dark product UI dashboard."
    assert analyses[0].best_for_scene_roles == ["value"]


def test_runway_ratio_mapping_uses_provider_dimensions():
    assert RunwayVideoProviderClient._ratio_to_runway_size("9:16") == "720:1280"
    assert RunwayVideoProviderClient._ratio_to_runway_size("16:9") == "1280:720"


def test_veo_output_ref_extraction_supports_rest_response_shape():
    data = {
        "response": {
            "generateVideoResponse": {
                "generatedSamples": [{"video": {"uri": "https://example.com/out.mp4"}}]
            }
        }
    }

    assert (
        GoogleVeoProviderClient._extract_output_ref(data)
        == "https://example.com/out.mp4"
    )


def test_veo_duration_normalization_matches_provider_limits():
    assert normalize_veo_duration_seconds(3) == 4
    assert normalize_veo_duration_seconds(5) == 6
    assert normalize_veo_duration_seconds(15) == 8
    assert normalize_veo_duration_seconds(6, resolution="1080p") == 8
    assert normalize_veo_duration_seconds(6, has_images=True) == 8


def test_veo_payload_uses_reference_images_for_multiple_inputs():
    client = GoogleVeoProviderClient(api_key="test-key")
    request = VideoProviderRequest(
        prompt_text="Create a premium product promotion clip",
        model="veo-3.1-generate-preview",
        input_images=[
            ProviderInputImage(data_base64="image-one", mime_type="image/png"),
            ProviderInputImage(data_base64="image-two", mime_type="image/png"),
        ],
        duration_seconds=15,
        resolution="720p",
    )

    payload = client._build_payload(request)

    assert payload["parameters"]["durationSeconds"] == 8
    assert payload["parameters"]["personGeneration"] == "allow_adult"
    assert "image" not in payload["instances"][0]
    assert payload["instances"][0]["referenceImages"] == [
        {
            "image": {
                "inlineData": {
                    "data": "image-one",
                    "mimeType": "image/png",
                }
            },
            "referenceType": "asset",
        },
        {
            "image": {
                "inlineData": {
                    "data": "image-two",
                    "mimeType": "image/png",
                }
            },
            "referenceType": "asset",
        },
    ]
    assert "imageBytes" not in str(payload)


def test_veo_payload_uses_reference_images_for_single_input_image():
    client = GoogleVeoProviderClient(api_key="test-key")
    request = VideoProviderRequest(
        prompt_text="Animate the product image as a vertical promo",
        model="veo-3.1-generate-preview",
        input_images=[
            ProviderInputImage(data_base64="single-image", mime_type="image/webp"),
        ],
        duration_seconds=6,
        resolution="720p",
    )

    payload = client._build_payload(request)

    assert "image" not in payload["instances"][0]
    assert payload["instances"][0]["referenceImages"] == [
        {
            "image": {
                "inlineData": {
                    "data": "single-image",
                    "mimeType": "image/webp",
                }
            },
            "referenceType": "asset",
        }
    ]
    assert payload["parameters"]["durationSeconds"] == 8
    assert "imageBytes" not in str(payload)


def test_veo_payload_can_build_text_only_request_when_images_are_excluded():
    client = GoogleVeoProviderClient(api_key="test-key")
    request = VideoProviderRequest(
        prompt_text="Create a text-only promo",
        model="veo-3.1-generate-preview",
        input_images=[
            ProviderInputImage(data_base64="single-image", mime_type="image/png"),
        ],
        duration_seconds=6,
        resolution="720p",
    )

    payload = client._build_payload(request, include_images=False)

    assert payload["instances"][0] == {"prompt": request.prompt_text}
    assert "personGeneration" not in payload["parameters"]
    assert payload["parameters"]["durationSeconds"] == 6


@pytest.mark.asyncio
async def test_veo_submit_falls_back_to_text_only_when_images_are_rejected():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))
        if len(requests) == 2:
            return httpx.Response(200, json={"name": "operations/fallback-task"})
        return httpx.Response(
            status_code=400,
            json={"error": {"message": "`inlineData` isn't supported by this model."}},
        )

    client = GoogleVeoProviderClient(
        api_key="test-key",
        base_url="https://gemini.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    request = VideoProviderRequest(
        prompt_text="Create a premium product promotion clip",
        model="veo-3.1-generate-preview",
        input_images=[
            ProviderInputImage(data_base64="image-one", mime_type="image/png"),
        ],
        duration_seconds=8,
        resolution="720p",
    )

    task = await client.submit(request)

    assert task.provider_task_id == "operations/fallback-task"
    assert task.raw_response["_local_fallback"]["reason"] == "image_input_rejected"
    assert len(requests) == 2
    assert (
        requests[0]["instances"][0]["referenceImages"][0]["image"]["inlineData"][
            "data"
        ]
        == "image-one"
    )
    assert requests[1]["instances"][0] == {
        "prompt": "Create a premium product promotion clip"
    }
    assert "personGeneration" not in requests[1]["parameters"]


@pytest.mark.asyncio
async def test_veo_submit_wraps_read_timeout_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timed out", request=request)

    client = GoogleVeoProviderClient(
        api_key="test-key",
        base_url="https://gemini.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    request = VideoProviderRequest(
        prompt_text="Create a premium product promotion clip",
        model="veo-3.1-generate-preview",
        duration_seconds=8,
        resolution="720p",
    )

    with pytest.raises(VideoProviderError) as exc_info:
        await client.submit(request)

    assert exc_info.value.code == "VEO_TIMEOUT"
    assert exc_info.value.retryable is True


def test_sanitized_provider_request_does_not_persist_image_bytes():
    request = VideoProviderRequest(
        prompt_text="Create a product launch clip",
        model="veo-3.0-generate-001",
        input_images=[
            ProviderInputImage(
                data_base64="sensitive-base64-image", mime_type="image/png"
            )
        ],
    )

    sanitized = _sanitize_provider_request(request)

    assert sanitized["input_image_count"] == 1
    assert "sensitive-base64-image" not in str(sanitized)


def test_completed_clip_asset_ids_requires_every_scene_complete():
    project = VideoProject(
        scenes=[
            VideoStoryboardScene(
                scene_index=1,
                scene_role="hook",
                title="Hook",
                prompt_text="Completed opening scene",
                duration_seconds=8,
                status="completed",
                output_asset_id=10,
            ),
            VideoStoryboardScene(
                scene_index=2,
                scene_role="value",
                title="Value",
                prompt_text="Failed value scene",
                duration_seconds=8,
                status="failed",
            ),
        ]
    )

    with pytest.raises(VideoProviderError) as exc_info:
        _completed_clip_asset_ids(project)

    assert exc_info.value.code == "EXPORT_INCOMPLETE_SCENES"
    assert "2" in exc_info.value.message


def test_completed_clip_asset_ids_preserves_scene_order():
    project = VideoProject(
        scenes=[
            VideoStoryboardScene(
                scene_index=2,
                scene_role="cta",
                title="Close",
                prompt_text="Completed closing scene",
                duration_seconds=8,
                status="completed",
                output_asset_id=20,
            ),
            VideoStoryboardScene(
                scene_index=1,
                scene_role="hook",
                title="Hook",
                prompt_text="Completed opening scene",
                duration_seconds=8,
                status="completed",
                output_asset_id=10,
            ),
        ]
    )

    assert _completed_clip_asset_ids(project) == [10, 20]


def test_video_generation_task_uses_project_celery_app():
    assert generate_video_project.app is celery_app
    assert retry_video_project_scene.app is celery_app
    assert "video_generation" in celery_app.conf.task_queues


def test_video_models_register_user_table_for_worker_flushes():
    assert "users" in VideoProject.metadata.tables


@pytest.mark.parametrize(
    ("endpoint_url", "expected"),
    [
        ("http://minio:9010", "http://minio:9000"),
        ("http://minio:90000", "http://minio:9000"),
        ("http://remote-minio:9010", "http://remote-minio:9010"),
        ("https://s3.amazonaws.com", "https://s3.amazonaws.com"),
    ],
)
def test_s3_service_normalizes_docker_minio_internal_endpoint(
    endpoint_url: str, expected: str
):
    service = object.__new__(S3Service)

    assert service._resolve_internal_endpoint(endpoint_url) == expected
