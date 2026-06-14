import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  FileImageOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  ScissorOutlined,
  StopOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Empty, Input, InputNumber, Progress, Segmented, Select, Space, Spin, Tag, Tooltip, Upload } from 'antd';
import type { UploadProps } from 'antd';
import {
  cancelVideoProject,
  createVideoAssetUploadUrl,
  createVideoProject,
  generateVideoStoryboard,
  getPresignedDownloadUrl,
  getVideoProject,
  listVideoModels,
  listVideoProjects,
  retryVideoSceneGeneration,
  startVideoGeneration,
  updateVideoStoryboard,
} from '@/apis/video';
import type { VideoAsset, VideoModelCapability, VideoProject, VideoProjectListItem, VideoStoryboardSceneUpdate } from '@/apis/video';
import { getMessageApi } from '@/utils/messageClient';
import { showRequestError } from '@/utils/requestError';
import styles from './index.module.scss';

interface UploadedAsset {
  assetId: number;
  fileName: string;
}

interface ActivePreview {
  title: string;
  url: string;
}

interface ImageAssetAnalysis {
  caption?: string;
  asset_type?: string;
  visual_tags?: string[];
  best_for_scene_roles?: string[];
  avoid_for_scene_roles?: string[];
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  storyboard_ready: 'Storyboard',
  queued: 'Queued',
  generating: 'Generating',
  completed: 'Completed',
  failed: 'Failed',
  canceled: 'Canceled',
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'default',
  storyboard_ready: 'processing',
  queued: 'warning',
  generating: 'blue',
  completed: 'success',
  failed: 'error',
  canceled: 'default',
};

const SCENE_DURATION_MIN = 3;
const SCENE_DURATION_MAX = 15;

const notifySuccess = (content: string): void => {
  const messageApi = getMessageApi();
  if (messageApi) {
    messageApi.success(content);
  }
};

const notifyError = (content: string): void => {
  const messageApi = getMessageApi();
  if (messageApi) {
    messageApi.error(content);
  }
};

const getImageAssetAnalysis = (asset: VideoAsset): ImageAssetAnalysis | null => {
  const metadata = asset.provider_metadata;
  if (!metadata || typeof metadata !== 'object') return null;
  const analysis = (metadata as Record<string, unknown>).image_analysis;
  if (!analysis || typeof analysis !== 'object') return null;
  return analysis as ImageAssetAnalysis;
};

const sceneReferenceIds = (scene: { input_asset_ids?: number[] | null }): number[] => {
  return (scene.input_asset_ids ?? []).slice(0, 3);
};

const Home: FC = () => {
  const [models, setModels] = useState<VideoModelCapability[]>([]);
  const [projects, setProjects] = useState<VideoProjectListItem[]>([]);
  const [selectedModelKey, setSelectedModelKey] = useState<string>('');
  const [prompt, setPrompt] = useState<string>('');
  const [aspectRatio, setAspectRatio] = useState<string>('9:16');
  const [resolution, setResolution] = useState<string>('720p');
  const [targetDuration, setTargetDuration] = useState<number>(24);
  const [uploadedAssets, setUploadedAssets] = useState<UploadedAsset[]>([]);
  const [selectedProject, setSelectedProject] = useState<VideoProject | null>(null);
  const [finalPreviewUrl, setFinalPreviewUrl] = useState<string | null>(null);
  const [activePreview, setActivePreview] = useState<ActivePreview | null>(null);
  const [scenePreviewUrls, setScenePreviewUrls] = useState<Record<number, string>>({});
  const [assetPreviewUrls, setAssetPreviewUrls] = useState<Record<number, string>>({});
  const [retryingSceneId, setRetryingSceneId] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);

  const selectedModel = useMemo(() => {
    return models.find((model) => `${model.provider}:${model.model}` === selectedModelKey);
  }, [models, selectedModelKey]);

  const selectedProjectIsActive = selectedProject?.status === 'queued' || selectedProject?.status === 'generating';

  const inputAssets = useMemo(() => {
    return selectedProject?.assets.filter((asset) => asset.asset_type === 'input_image') ?? [];
  }, [selectedProject?.assets]);

  const inputAssetsById = useMemo(() => {
    return new Map(inputAssets.map((asset) => [asset.id, asset]));
  }, [inputAssets]);

  const displayedPreview = useMemo(() => {
    if (activePreview) return activePreview;
    if (finalPreviewUrl) {
      return {
        title: 'Final export',
        url: finalPreviewUrl,
      };
    }
    return null;
  }, [activePreview, finalPreviewUrl]);

  const loadModels = useCallback(async (): Promise<void> => {
    const response = await listVideoModels();
    const items = response.data.data;
    setModels(items);
    const defaultModel = items.find((item) => item.is_default) ?? items[0];
    if (defaultModel) {
      setSelectedModelKey(`${defaultModel.provider}:${defaultModel.model}`);
    }
  }, []);

  const loadProjects = useCallback(async (): Promise<void> => {
    try {
      const response = await listVideoProjects(1, 12);
      setProjects(response.data.data.items);
    } catch {
      setProjects([]);
    }
  }, []);

  const refreshSelectedProject = useCallback(
    async (projectId: number): Promise<VideoProject> => {
      const response = await getVideoProject(projectId);
      const project = response.data.data;
      setSelectedProject(project);
      await loadProjects();
      return project;
    },
    [loadProjects]
  );

  useEffect(() => {
    void Promise.allSettled([loadModels(), loadProjects()]);
  }, [loadModels, loadProjects]);

  useEffect(() => {
    if (!selectedModel) return;
    const nextAspectRatio = selectedModel.supported_aspect_ratios[0];
    const nextResolution = selectedModel.supported_resolutions[0];
    if (nextAspectRatio && !selectedModel.supported_aspect_ratios.includes(aspectRatio)) {
      setAspectRatio(nextAspectRatio);
    }
    if (nextResolution && !selectedModel.supported_resolutions.includes(resolution)) {
      setResolution(nextResolution);
    }
  }, [aspectRatio, resolution, selectedModel]);

  useEffect(() => {
    if (!selectedProjectIsActive || !selectedProject) return undefined;
    const interval = window.setInterval(() => {
      void refreshSelectedProject(selectedProject.id);
    }, 5000);
    return () => window.clearInterval(interval);
  }, [refreshSelectedProject, selectedProject, selectedProjectIsActive]);

  useEffect(() => {
    const fileKey = selectedProject?.final_video_file_key;
    setFinalPreviewUrl(null);
    if (!fileKey) return;
    void getPresignedDownloadUrl(fileKey).then((response) => {
      setFinalPreviewUrl(response.data.data.download_url);
    });
  }, [selectedProject?.final_video_file_key]);

  useEffect(() => {
    setActivePreview(null);
  }, [selectedProject?.id]);

  useEffect(() => {
    let canceled = false;
    setScenePreviewUrls({});
    if (!selectedProject) {
      return () => {
        canceled = true;
      };
    }

    const assetsById = new Map(selectedProject.assets.map((asset) => [asset.id, asset]));
    const scenesWithOutputs = selectedProject.scenes.filter((scene) => {
      if (!scene.output_asset_id) return false;
      return Boolean(assetsById.get(scene.output_asset_id)?.file_key);
    });

    if (scenesWithOutputs.length === 0) {
      return () => {
        canceled = true;
      };
    }

    void Promise.all(
      scenesWithOutputs.map(async (scene) => {
        const asset = assetsById.get(scene.output_asset_id as number);
        if (!asset) return null;
        try {
          const response = await getPresignedDownloadUrl(asset.file_key);
          return [scene.id, response.data.data.download_url] as const;
        } catch {
          return null;
        }
      })
    ).then((entries) => {
      if (canceled) return;
      const validEntries = entries.filter((entry): entry is readonly [number, string] => entry !== null);
      setScenePreviewUrls(Object.fromEntries(validEntries));
    });

    return () => {
      canceled = true;
    };
  }, [selectedProject]);

  useEffect(() => {
    let canceled = false;
    setAssetPreviewUrls({});
    if (inputAssets.length === 0) {
      return () => {
        canceled = true;
      };
    }

    void Promise.all(
      inputAssets.map(async (asset) => {
        try {
          const response = await getPresignedDownloadUrl(asset.file_key);
          return [asset.id, response.data.data.download_url] as const;
        } catch {
          return null;
        }
      })
    ).then((entries) => {
      if (canceled) return;
      const validEntries = entries.filter((entry): entry is readonly [number, string] => entry !== null);
      setAssetPreviewUrls(Object.fromEntries(validEntries));
    });

    return () => {
      canceled = true;
    };
  }, [inputAssets]);

  const handleUploadImage = async (file: File): Promise<void> => {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      notifyError('Unsupported image type');
      return;
    }
    setUploading(true);
    try {
      const uploadResponse = await createVideoAssetUploadUrl({
        file_name: file.name,
        file_type: file.type,
        file_size: file.size,
      });
      const uploadData = uploadResponse.data.data;
      await axios.put(uploadData.presigned_url, file, {
        headers: { 'Content-Type': file.type },
      });
      setUploadedAssets((current) => [...current, { assetId: uploadData.asset_id, fileName: file.name }]);
      notifySuccess('Image uploaded');
    } catch (error) {
      showRequestError(error, 'Failed to upload image');
    } finally {
      setUploading(false);
    }
  };

  const beforeUpload: UploadProps['beforeUpload'] = (file) => {
    void handleUploadImage(file);
    return Upload.LIST_IGNORE;
  };

  const handleCreateStoryboard = async (): Promise<void> => {
    if (!selectedModel) {
      notifyError('Select a model first');
      return;
    }
    if (!prompt.trim()) {
      notifyError('Enter a campaign prompt');
      return;
    }
    setLoading(true);
    try {
      const createResponse = await createVideoProject({
        prompt: prompt.trim(),
        asset_ids: uploadedAssets.map((asset) => asset.assetId),
        provider: selectedModel.provider,
        model: selectedModel.model,
        aspect_ratio: aspectRatio,
        resolution,
        target_duration_seconds: targetDuration,
      });
      const project = createResponse.data.data;
      const storyboardResponse = await generateVideoStoryboard(project.id, false);
      setSelectedProject(storyboardResponse.data.data);
      await loadProjects();
      notifySuccess('Storyboard ready');
    } catch (error) {
      showRequestError(error, 'Failed to create storyboard');
    } finally {
      setLoading(false);
    }
  };

  const sceneUpdates = (project: VideoProject): VideoStoryboardSceneUpdate[] => {
    return project.scenes.map((scene) => ({
      scene_index: scene.scene_index,
      scene_role: scene.scene_role,
      title: scene.title,
      prompt_text: scene.prompt_text,
      narration_text: scene.narration_text,
      sound_design: scene.sound_design,
      duration_seconds: scene.duration_seconds,
      input_asset_ids: sceneReferenceIds(scene),
    }));
  };

  const hasInvalidSceneDurations = (project: VideoProject): boolean => {
    return project.scenes.some((scene) => scene.duration_seconds < SCENE_DURATION_MIN || scene.duration_seconds > SCENE_DURATION_MAX);
  };

  const saveStoryboard = async (showMessage = true, projectToSave = selectedProject): Promise<VideoProject | null> => {
    if (!projectToSave) return null;
    if (projectToSave.scenes.length === 0) {
      if (showMessage) {
        notifyError('No storyboard scenes to save');
      }
      return null;
    }
    if (hasInvalidSceneDurations(projectToSave)) {
      if (showMessage) {
        notifyError(`Scene durations must be between ${SCENE_DURATION_MIN} and ${SCENE_DURATION_MAX} seconds`);
      }
      return null;
    }
    if (showMessage) {
      setLoading(true);
    }
    try {
      const response = await updateVideoStoryboard(projectToSave.id, sceneUpdates(projectToSave));
      const project = response.data.data;
      setSelectedProject(project);
      await loadProjects();
      if (showMessage) {
        notifySuccess('Storyboard saved');
      }
      return project;
    } catch (error) {
      showRequestError(error, 'Failed to save storyboard');
      return null;
    } finally {
      if (showMessage) {
        setLoading(false);
      }
    }
  };

  const ensureStoryboardScenes = async (project: VideoProject): Promise<VideoProject | null> => {
    if (project.scenes.length > 0 && !hasInvalidSceneDurations(project)) return project;

    let latestProject = await refreshSelectedProject(project.id);
    if (latestProject.scenes.length > 0 && !hasInvalidSceneDurations(latestProject)) return latestProject;

    const storyboardResponse = await generateVideoStoryboard(latestProject.id, latestProject.scenes.length > 0);
    latestProject = storyboardResponse.data.data;
    setSelectedProject(latestProject);
    await loadProjects();

    if (latestProject.scenes.length === 0) {
      notifyError('No storyboard scenes found');
      return null;
    }
    if (hasInvalidSceneDurations(latestProject)) {
      notifyError(`Scene durations must be between ${SCENE_DURATION_MIN} and ${SCENE_DURATION_MAX} seconds`);
      return null;
    }
    return latestProject;
  };

  const handleStartGeneration = async (): Promise<void> => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const projectWithScenes = await ensureStoryboardScenes(selectedProject);
      if (!projectWithScenes) return;
      const savedProject = await saveStoryboard(false, projectWithScenes);
      if (!savedProject) return;
      const response = await startVideoGeneration(savedProject.id);
      setSelectedProject(response.data.data);
      await loadProjects();
      notifySuccess('Generation queued');
    } catch (error) {
      showRequestError(error, 'Failed to start generation');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (): Promise<void> => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const response = await cancelVideoProject(selectedProject.id);
      setSelectedProject(response.data.data);
      await loadProjects();
    } catch (error) {
      showRequestError(error, 'Failed to cancel generation');
    } finally {
      setLoading(false);
    }
  };

  const handleRetryScene = async (sceneId: number): Promise<void> => {
    if (!selectedProject) return;
    setRetryingSceneId(sceneId);
    try {
      const response = await retryVideoSceneGeneration(selectedProject.id, sceneId);
      setSelectedProject(response.data.data);
      await loadProjects();
      notifySuccess('Scene retry queued');
    } catch (error) {
      showRequestError(error, 'Failed to retry scene');
    } finally {
      setRetryingSceneId(null);
    }
  };

  const handleSelectProject = async (projectId: number): Promise<void> => {
    setLoading(true);
    try {
      await refreshSelectedProject(projectId);
    } catch (error) {
      showRequestError(error, 'Failed to load project');
    } finally {
      setLoading(false);
    }
  };

  const updateScene = <K extends keyof VideoStoryboardSceneUpdate>(sceneIndex: number, field: K, value: VideoStoryboardSceneUpdate[K]): void => {
    setSelectedProject((current) => {
      if (!current) return current;
      return {
        ...current,
        scenes: current.scenes.map((scene) => (scene.scene_index === sceneIndex ? { ...scene, [field]: value } : scene)),
      };
    });
  };

  const toggleSceneAsset = (sceneIndex: number, assetId: number): void => {
    if (!selectedProject) return;
    const scene = selectedProject.scenes.find((item) => item.scene_index === sceneIndex);
    if (!scene) return;
    const currentIds = sceneReferenceIds(scene);
    const nextIds = currentIds.includes(assetId) ? currentIds.filter((id) => id !== assetId) : [...currentIds, assetId];
    if (nextIds.length > 3) {
      notifyError('Each scene can use up to 3 reference images');
      return;
    }
    updateScene(sceneIndex, 'input_asset_ids', nextIds);
  };

  const handleDownload = (): void => {
    if (!displayedPreview) return;
    window.open(displayedPreview.url, '_blank', 'noopener,noreferrer');
  };

  const handleSceneDownload = (scenePreviewUrl?: string): void => {
    if (!scenePreviewUrl) return;
    window.open(scenePreviewUrl, '_blank', 'noopener,noreferrer');
  };

  const handlePlayScene = (sceneIndex: number, scenePreviewUrl?: string): void => {
    if (!scenePreviewUrl) return;
    setActivePreview({
      title: `Scene ${sceneIndex} clip`,
      url: scenePreviewUrl,
    });
  };

  const handlePlayFinalExport = (): void => {
    setActivePreview(null);
  };

  return (
    <div className={styles.videoStudio}>
      <section className={styles.headerBand}>
        <div>
          <h1>Video Studio</h1>
          <p>Promotion projects, storyboards, model runs, and exports.</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadProjects()}>
          Refresh
        </Button>
      </section>

      <div className={styles.workspace}>
        <section className={styles.creationPanel}>
          <div className={styles.panelHeader}>
            <VideoCameraOutlined />
            <span>New campaign</span>
          </div>
          <Input.TextArea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe the product, audience, selling points, and desired tone."
            autoSize={{ minRows: 5, maxRows: 8 }}
            maxLength={8000}
            showCount
          />

          <div className={styles.fieldGrid}>
            <label>
              <span>Model</span>
              <Select
                value={selectedModelKey || undefined}
                onChange={setSelectedModelKey}
                options={models.map((model) => ({
                  value: `${model.provider}:${model.model}`,
                  label: `${model.provider_label} · ${model.model_label}`,
                }))}
                placeholder="Select model"
              />
            </label>
            <label>
              <span>Duration</span>
              <Space.Compact className={styles.compactNumber}>
                <InputNumber min={8} max={60} value={targetDuration} onChange={(value) => setTargetDuration(value ?? 24)} />
                <span className={styles.inputAddon}>s</span>
              </Space.Compact>
            </label>
          </div>

          <div className={styles.controlRow}>
            <Segmented value={aspectRatio} onChange={(value) => setAspectRatio(String(value))} options={selectedModel?.supported_aspect_ratios ?? ['9:16']} />
            <Segmented value={resolution} onChange={(value) => setResolution(String(value))} options={selectedModel?.supported_resolutions ?? ['720p']} />
          </div>

          <div className={styles.uploadCard}>
            <div className={styles.uploadCardHeader}>
              <span>
                <PictureOutlined />
                Reference images
              </span>
              <span className={styles.uploadCount}>{uploadedAssets.length} uploaded</span>
            </div>
            <div className={styles.uploadBody}>
              <Upload beforeUpload={beforeUpload} showUploadList={false} accept="image/png,image/jpeg,image/webp" disabled={uploading}>
                <button className={styles.uploadButton} type="button" disabled={uploading}>
                  <span className={styles.uploadIcon}>
                    <CloudUploadOutlined />
                  </span>
                  <span className={styles.uploadText}>
                    <strong>{uploading ? 'Uploading' : 'Upload image'}</strong>
                    <small>PNG, JPG, WebP</small>
                  </span>
                </button>
              </Upload>
              <div className={styles.assetChips} aria-live="polite">
                {uploadedAssets.length === 0 ? (
                  <span className={styles.assetEmpty}>No images selected</span>
                ) : (
                  uploadedAssets.map((asset) => (
                    <span className={styles.assetChip} key={asset.assetId} title={asset.fileName}>
                      <FileImageOutlined />
                      <span>{asset.fileName}</span>
                      <button
                        type="button"
                        aria-label={`Remove ${asset.fileName}`}
                        onClick={() => setUploadedAssets((current) => current.filter((item) => item.assetId !== asset.assetId))}
                      >
                        <CloseCircleOutlined />
                      </button>
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          {selectedModel && <div className={styles.modelHint}>{selectedModel.cost_hint}</div>}

          <Button type="primary" icon={<ScissorOutlined />} loading={loading} onClick={() => void handleCreateStoryboard()}>
            Create storyboard
          </Button>
        </section>

        <section className={styles.storyboardPanel}>
          <div className={styles.panelHeader}>
            <ScissorOutlined />
            <span>Storyboard</span>
          </div>

          {!selectedProject ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No project selected" />
          ) : (
            <Spin spinning={loading}>
              <div className={styles.projectStatus}>
                <div>
                  <h2>{selectedProject.title ?? `Project ${selectedProject.id}`}</h2>
                  <Space size={8} wrap>
                    <Tag color={STATUS_COLORS[selectedProject.status] ?? 'default'}>{STATUS_LABELS[selectedProject.status] ?? selectedProject.status}</Tag>
                    <Tag>{selectedProject.provider}</Tag>
                    <Tag>{selectedProject.model}</Tag>
                  </Space>
                </div>
                <Progress type="circle" percent={selectedProject.progress} size={64} />
              </div>

              {selectedProject.error_message && <div className={styles.errorBox}>{selectedProject.error_message}</div>}

              <div className={styles.sceneList}>
                {selectedProject.scenes.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No storyboard scenes" />}
                {selectedProject.scenes.map((scene) => {
                  const scenePreviewUrl = scenePreviewUrls[scene.id];
                  const canRetryScene = scene.status === 'failed' && !selectedProjectIsActive;
                  const referenceIds = sceneReferenceIds(scene).filter((assetId) => inputAssetsById.has(assetId));
                  return (
                    <article className={styles.sceneItem} key={scene.id}>
                      <div className={styles.sceneTopline}>
                        <Tag color="geekblue">Scene {scene.scene_index}</Tag>
                        <Tag>{scene.scene_role}</Tag>
                        <Tag color={STATUS_COLORS[scene.status] ?? 'default'}>{scene.status}</Tag>
                        {canRetryScene && (
                          <Tooltip title="Retry this failed scene">
                            <Button size="small" icon={<ReloadOutlined />} loading={retryingSceneId === scene.id} onClick={() => void handleRetryScene(scene.id)}>
                              Retry
                            </Button>
                          </Tooltip>
                        )}
                      </div>
                      <Input value={scene.title} onChange={(event) => updateScene(scene.scene_index, 'title', event.target.value)} />
                      <Input.TextArea
                        value={scene.prompt_text}
                        onChange={(event) => updateScene(scene.scene_index, 'prompt_text', event.target.value)}
                        autoSize={{ minRows: 3, maxRows: 6 }}
                      />
                      {inputAssets.length > 0 && (
                        <div className={styles.sceneReferenceBlock}>
                          <div className={styles.sceneReferenceHeader}>
                            <span>
                              <PictureOutlined />
                              References
                            </span>
                            <Tag>{referenceIds.length}/3</Tag>
                          </div>
                          <div className={styles.sceneReferenceRail}>
                            {inputAssets.map((asset) => {
                              const previewUrl = assetPreviewUrls[asset.id];
                              const selected = referenceIds.includes(asset.id);
                              const analysis = getImageAssetAnalysis(asset);
                              const tooltipTitle = (
                                <div className={styles.assetTooltip}>
                                  <strong>{analysis?.asset_type || asset.file_name || `Asset ${asset.id}`}</strong>
                                  {analysis?.caption && <span>{analysis.caption}</span>}
                                  {analysis?.visual_tags && analysis.visual_tags.length > 0 && <small>{analysis.visual_tags.slice(0, 5).join(' · ')}</small>}
                                </div>
                              );

                              return (
                                <Tooltip title={tooltipTitle} key={asset.id}>
                                  <button
                                    type="button"
                                    className={`${styles.referenceThumb} ${selected ? styles.selectedReferenceThumb : ''}`}
                                    aria-pressed={selected}
                                    aria-label={asset.file_name ?? `Reference image ${asset.id}`}
                                    onClick={() => toggleSceneAsset(scene.scene_index, asset.id)}
                                  >
                                    {previewUrl ? <img src={previewUrl} alt={asset.file_name ?? `Reference ${asset.id}`} /> : <Spin size="small" />}
                                    {selected && (
                                      <span className={styles.referenceCheck}>
                                        <CheckCircleOutlined />
                                      </span>
                                    )}
                                  </button>
                                </Tooltip>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      <div className={styles.sceneMetaGrid}>
                        <Input.TextArea
                          value={scene.narration_text ?? ''}
                          onChange={(event) => updateScene(scene.scene_index, 'narration_text', event.target.value)}
                          autoSize={{ minRows: 2, maxRows: 4 }}
                        />
                        <Input.TextArea
                          value={scene.sound_design ?? ''}
                          onChange={(event) => updateScene(scene.scene_index, 'sound_design', event.target.value)}
                          autoSize={{ minRows: 2, maxRows: 4 }}
                        />
                        <Space.Compact className={styles.compactNumber}>
                          <InputNumber
                            min={SCENE_DURATION_MIN}
                            max={SCENE_DURATION_MAX}
                            value={scene.duration_seconds}
                            onChange={(value) => updateScene(scene.scene_index, 'duration_seconds', value ?? 8)}
                          />
                          <span className={styles.inputAddon}>s</span>
                        </Space.Compact>
                      </div>
                      {scene.output_asset_id && (
                        <div className={styles.scenePreview}>
                          {!scenePreviewUrl && <Spin size="small" />}
                          <Button
                            size="small"
                            type="primary"
                            icon={<PlayCircleOutlined />}
                            disabled={!scenePreviewUrl}
                            onClick={() => handlePlayScene(scene.scene_index, scenePreviewUrl)}
                          >
                            Play clip
                          </Button>
                          <Button size="small" icon={<DownloadOutlined />} disabled={!scenePreviewUrl} onClick={() => handleSceneDownload(scenePreviewUrl)}>
                            Download
                          </Button>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>

              <div className={styles.actionBar}>
                <Button icon={<SaveOutlined />} loading={loading} onClick={() => void saveStoryboard()}>
                  Save
                </Button>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={loading}
                  disabled={selectedProjectIsActive || selectedProject.status === 'completed'}
                  onClick={() => void handleStartGeneration()}
                >
                  Generate
                </Button>
                {selectedProject.final_video_file_key && (
                  <Button icon={<PlayCircleOutlined />} disabled={!finalPreviewUrl} onClick={handlePlayFinalExport}>
                    View final
                  </Button>
                )}
                <Tooltip title="Cancel queued or running generation">
                  <Button danger icon={<StopOutlined />} disabled={!selectedProjectIsActive} onClick={() => void handleCancel()} />
                </Tooltip>
              </div>
            </Spin>
          )}
        </section>

        <aside className={styles.sidePanel}>
          <section className={styles.previewPanel}>
            <div className={styles.panelHeader}>
              <PlayCircleOutlined />
              <span>{displayedPreview?.title ?? 'Preview'}</span>
            </div>
            {displayedPreview ? (
              <>
                <video className={styles.videoPreview} controls src={displayedPreview.url} />
                <Button icon={<DownloadOutlined />} onClick={handleDownload}>
                  Download
                </Button>
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No export yet" />
            )}
          </section>

          <section className={styles.projectListPanel}>
            <div className={styles.panelHeader}>
              <VideoCameraOutlined />
              <span>Projects</span>
            </div>
            <div className={styles.projectList}>
              {projects.map((project) => (
                <button
                  type="button"
                  className={`${styles.projectListItem} ${selectedProject?.id === project.id ? styles.activeProject : ''}`}
                  key={project.id}
                  onClick={() => void handleSelectProject(project.id)}
                >
                  <span>{project.title ?? `Project ${project.id}`}</span>
                  <Tag color={STATUS_COLORS[project.status] ?? 'default'}>{STATUS_LABELS[project.status] ?? project.status}</Tag>
                </button>
              ))}
              {projects.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No projects" />}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
};

export default Home;
