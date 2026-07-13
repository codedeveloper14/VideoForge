export interface Project {
  nombre: string;
  ruta: string;
  videos: number;
  audios: number;
  creado: number;
}

export interface Plan {
  id: string;
  name: string;
  emoji: string;
  price_usd: number;
  videos_per_day: number | null;
  videos_per_month: number | null;
  audio_hours_per_month: number | null;
  shorts_per_month: number | null;
  tts_mins_per_day: number | null;
  max_video_minutes: number | null;
  highlight: boolean;
}

export interface UserUsage {
  videos: number;
  tts_chars: number;
  shorts: number;
}

export interface UserLimits {
  videos_per_month: number | null;
  tts_chars_per_month: number | null;
  audio_hours_per_month: number | null;
  shorts_per_month: number | null;
  max_video_minutes: number | null;
  videos_per_day: number | null;
  tts_chars_per_day: number | null;
}

export interface UserProfile {
  username: string;
  email: string;
  plan: string;
  plan_name: string;
  subscription_date: string | null;
  theme: "light" | "dark";
  usage: UserUsage;
  limits: UserLimits;
  payment: {
    activated_at: string;
    expires_at: string;
  };
}

export interface Payment {
  plan: string;
  amount_usd: number;
  paid_at: string;
  session_id: string | null;
}
