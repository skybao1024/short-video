import service from '@/utils/https';

const STORYBOARD_REQUEST_TIMEOUT_MS = 60 * 1000;

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface VideoModelCapability {
  provider: string;
  provider_label: string;
  model: string;
  model_label: string;
  supports_text: boolean;
  supports_image: boolean;
  supports_audio: boolean;
  supported_aspect_ratios: string[];
  supported_resolutions: string[];
  default_duration_seconds: number;
  max_prompt_tokens: number;
  cost_hint: string;
  is_default: boolean;
}

export interface VideoAssetUploadUrlResponse {
  asset_id: number;
  presigned_url: string;
  file_key: string;
  expires_in: number;
  max_file_size: number;
}

export interface VideoAssetUploadUrlRequest {
  file_name: string;
  file_type: string;
  file_size: number;
}

export interface VideoAsset {
  id: number;
  project_id?: number | null;
  asset_type: string;
  status: string;
  file_key: string;
  file_name?: string | null;
  mime_type: string;
  file_size?: number | null;
  duration_seconds?: string | null;
  provider?: string | null;
  provider_metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface VideoStoryboardScene {
  id: number;
  project_id: number;
  scene_index: number;
  scene_role: string;
  title: string;
  prompt_text: string;
  narration_text?: string | null;
  sound_design?: string | null;
  duration_seconds: number;
  input_asset_ids?: number[] | null;
  output_asset_id?: number | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface VideoGenerationTask {
  id: number;
  project_id: number;
  scene_id: number;
  provider: string;
  model: string;
  provider_task_id?: string | null;
  status: string;
  failure_code?: string | null;
  failure_message?: string | null;
  output_asset_id?: number | null;
  retry_count: number;
  submitted_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VideoProject {
  id: number;
  title?: string | null;
  prompt: string;
  expanded_brief?: string | null;
  provider: string;
  model: string;
  aspect_ratio: string;
  resolution: string;
  target_duration_seconds: number;
  status: string;
  progress: number;
  final_video_asset_id?: number | null;
  final_video_file_key?: string | null;
  thumbnail_file_key?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  assets: VideoAsset[];
  scenes: VideoStoryboardScene[];
  tasks: VideoGenerationTask[];
}

export interface VideoProjectListItem {
  id: number;
  title?: string | null;
  prompt: string;
  provider: string;
  model: string;
  aspect_ratio: string;
  resolution: string;
  target_duration_seconds: number;
  status: string;
  progress: number;
  final_video_file_key?: string | null;
  thumbnail_file_key?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VideoProjectListData {
  items: VideoProjectListItem[];
  total: number;
  per_page: number;
  current_page: number;
  last_page: number;
  has_more: boolean;
}

export interface VideoProjectCreateRequest {
  prompt: string;
  asset_ids: number[];
  provider: string;
  model: string;
  aspect_ratio: string;
  resolution: string;
  target_duration_seconds: number;
  title?: string;
}

export interface VideoStoryboardSceneUpdate {
  scene_index: number;
  scene_role: string;
  title: string;
  prompt_text: string;
  narration_text?: string | null;
  sound_design?: string | null;
  duration_seconds: number;
  input_asset_ids: number[];
}

export interface PresignedDownloadUrlResponse {
  download_url: string;
  file_key: string;
  expires_in: number;
}

export const listVideoModels = () => {
  return service.get<ApiResponse<VideoModelCapability[]>>('/v1/video-models');
};

export const createVideoAssetUploadUrl = (data: VideoAssetUploadUrlRequest) => {
  return service.post<ApiResponse<VideoAssetUploadUrlResponse>>('/v1/video-assets/presigned-upload-url', data);
};

export const createVideoProject = (data: VideoProjectCreateRequest) => {
  return service.post<ApiResponse<VideoProject>>('/v1/video-projects', data);
};

export const listVideoProjects = (page = 1, perPage = 12) => {
  return service.get<ApiResponse<VideoProjectListData>>('/v1/video-projects', {
    params: { page, per_page: perPage },
  });
};

export const getVideoProject = (projectId: number) => {
  return service.get<ApiResponse<VideoProject>>(`/v1/video-projects/${projectId}`);
};

export const generateVideoStoryboard = (projectId: number, regenerate = false) => {
  return service.post<ApiResponse<VideoProject>>(
    `/v1/video-projects/${projectId}/storyboard`,
    {
      regenerate,
    },
    {
      timeout: STORYBOARD_REQUEST_TIMEOUT_MS,
    }
  );
};

export const updateVideoStoryboard = (projectId: number, scenes: VideoStoryboardSceneUpdate[]) => {
  return service.patch<ApiResponse<VideoProject>>(`/v1/video-projects/${projectId}/storyboard`, {
    scenes,
  });
};

export const startVideoGeneration = (projectId: number) => {
  return service.post<ApiResponse<VideoProject>>(`/v1/video-projects/${projectId}/generate`, {
    force: false,
  });
};

export const retryVideoSceneGeneration = (projectId: number, sceneId: number) => {
  return service.post<ApiResponse<VideoProject>>(`/v1/video-projects/${projectId}/scenes/${sceneId}/retry`);
};

export const cancelVideoProject = (projectId: number) => {
  return service.post<ApiResponse<VideoProject>>(`/v1/video-projects/${projectId}/cancel`);
};

export const getPresignedDownloadUrl = (fileKey: string) => {
  return service.get<ApiResponse<PresignedDownloadUrlResponse>>('/v1/aws/presigned-download-url', {
    params: { file_key: fileKey },
  });
};
