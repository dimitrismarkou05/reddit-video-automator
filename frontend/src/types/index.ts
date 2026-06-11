export interface Story {
  id: number;
  reddit_id: string;
  title: string;
  author: string;
  subreddit: string;
  score: number;
  body: string | null;
  url: string;
  permalink: string;
  created_utc: string;
  fetched_at: string;
  status: string;
  is_update: boolean;
  update_reason: string | null;
  parent_story_id: number | null;
  updates?: Story[];
  generated_video?: GeneratedVideo | null;
}

export interface GeneratedVideo {
  id: number;
  story_id: number;
  video_path: string | null;
  thumbnail_path: string | null;
  audio_path: string | null;
  subtitle_path: string | null;
  format: string;
  duration_seconds: number | null;
  file_size_bytes: number | null;
  status: string;
  progress_percent: number;
  current_step: string;
  step_progress: number;
  retry_count: number;
  error_message: string | null;
  error_type: string | null;
  error_step: string | null;
  queue_position: number | null;
  is_paused: boolean;
  paused_at: string | null;
  tts_audio_path: string | null;
  subtitle_ass_path: string | null;
  selected_background_video: string | null;
  background_source: string | null;
  subtitle_style: Record<string, any> | null;
  youtube_upload_status: string;
  youtube_video_id: string | null;
  youtube_analytics: Record<string, any> | null;
  created_at: string;
  completed_at: string | null;
  story?: Story;
}

export interface Subreddit {
  id: number;
  name: string;
  display_name: string;
  is_active: boolean;
  fetch_settings: Record<string, any>;
  added_at: string;
}

export interface Notification {
  id: number;
  type: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
  details: Record<string, any> | null;
  is_read: boolean;
  created_at: string;
}

export interface YouTubeAuthStatus {
  is_configured: boolean;
  is_authenticated: boolean;
  user_info: {
    name?: string;
    email?: string;
    picture?: string;
  } | null;
}

export interface VideoStats {
  video_id: string;
  title: string;
  description: string;
  tags: string[];
  views: number;
  likes: number;
  comments: number;
  duration: string;
  thumbnail_url: string;
  privacy_status: string;
  upload_date: string;
  category_id: string;
}

export interface AutomationTemplate {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  status: string;
  subreddit_names: string[];
  fetch_settings: Record<string, any>;
  background_source: string;
  video_format: string;
  subtitle_style: Record<string, any>;
  include_updates: boolean;
  generate_hashtags: boolean;
  voice_id: string;
  youtube_title_template: string;
  youtube_description_template: string;
  youtube_tags: string[];
  youtube_privacy: string;
  youtube_category: string;
  auto_upload: boolean;
  schedule_type: string;
  schedule_config: Record<string, any>;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubtitleStyle {
  position: "center" | "bottom" | "top";
  font_size: number;
  font_color: string;
  outline_color: string;
  outline_width: number;
  max_width_percent: number;
}

export interface VideoProgressEvent {
  video_id: number;
  status: string;
  progress_percent: number;
  current_step: string;
  step_progress: number;
  error_message: string | null;
  error_type: string | null;
  error_step: string | null;
  queue_position: number | null;
  is_paused: boolean;
  thumbnail_path?: string;
  video_path?: string;
}

export interface FfmpegStatus {
  ffmpeg_installed: boolean;
  ffprobe_installed: boolean;
  ffmpeg_path: string | null;
  ffprobe_path: string | null;
  ffmpeg_version: string | null;
  ffprobe_version: string | null;
  can_generate_videos: boolean;
  ffmpeg_in_path: boolean;
}

export interface FfmpegInstallProgress {
  event_type: string;
  progress_percent: number;
  step: string;
  mirror: string | null;
  retry_count: number;
  error: string | null;
}

export interface VoiceInfo {
  id: string;
  name: string;
  model_name: string;
  language: string;
  speaker_count: number;
  description: string;
  installed: boolean;
  path: string | null;
}

export interface TtsStatus {
  installed: boolean;
  tts_package_installed: boolean;
  voices: VoiceInfo[];
  models_dir: string;
  auto_download: boolean;
  message: string;
}

export interface TtsInstallProgress {
  event_type: string;
  progress_percent: number;
  step: string;
  mirror: string | null;
  retry_count: number;
  error: string | null;
}
