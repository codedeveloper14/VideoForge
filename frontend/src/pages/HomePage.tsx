import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getProfile } from "../api/user";
import { listProjects } from "../api/projects";
import type { Project, UserProfile } from "../types";

interface Shortcut {
  to: string;
  icon: string;
  color: string;
  title: string;
  desc: string;
}

const SHORTCUTS: Shortcut[] = [
  {
    to: "/app/idea2video",
    icon: "💡",
    color: "var(--vf-c1)",
    title: "Idea a Video",
    desc: "Pipeline automático de una idea a un video completo.",
  },
  {
    to: "/app/guion",
    icon: "📝",
    color: "var(--vf-c2)",
    title: "Guion",
    desc: "Escribir guion con IA.",
  },
  {
    to: "/app/voz",
    icon: "🎙️",
    color: "var(--vf-c6)",
    title: "Voz",
    desc: "Generar narración con TTS / clonación de voz.",
  },
  {
    to: "/app/imagen",
    icon: "🖼️",
    color: "var(--vf-c3)",
    title: "Imagen",
    desc: "Generar imágenes de escenas.",
  },
  {
    to: "/app/video",
    icon: "🎬",
    color: "var(--vf-c4)",
    title: "Video",
    desc: "Animar imágenes a video con Grok, Qwen o Meta.",
  },
  {
    to: "/app/render",
    icon: "🧩",
    color: "var(--vf-c5)",
    title: "Render",
    desc: "Renderizar el video final.",
  },
  {
    to: "/app/editor",
    icon: "✂️",
    color: "var(--vf-c2)",
    title: "Editor",
    desc: "Editor visual de escenas con overlays.",
  },
  {
    to: "/app/miniaturas",
    icon: "🏷️",
    color: "var(--vf-c3)",
    title: "Miniaturas",
    desc: "Generar miniaturas para YouTube.",
  },
];

interface UsageStatProps {
  label: string;
  value: number;
  limit: number | null;
}

function UsageStat({ label, value, limit }: UsageStatProps) {
  const pct = limit ? Math.min(100, Math.round((value / limit) * 100)) : null;
  return (
    <div className="flex-1">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px]" style={{ fontFamily: "var(--vf-mono)", color: "rgba(255,255,255,.65)" }}>
          {label}
        </span>
        <span className="text-[11px]" style={{ fontFamily: "var(--vf-mono)", color: "var(--vf-m)" }}>
          {value}
          {limit != null ? ` / ${limit}` : ""}
        </span>
      </div>
      <div className="h-[8px] overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: pct != null ? `${pct}%` : "100%",
            background: "linear-gradient(90deg, var(--vf-c1), var(--vf-c3))",
          }}
        />
      </div>
    </div>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getProfile(), listProjects()])
      .then(([profileData, projectsData]) => {
        setProfile(profileData);
        setProjects(Array.isArray(projectsData) ? projectsData : []);
      })
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const recentProjects = [...projects]
    .sort((a, b) => String(b.creado || "").localeCompare(String(a.creado || "")))
    .slice(0, 5);

  return (
    <div className="max-w-5xl">
      <div className="mb-10">
        <div
          className="mb-4 inline-flex items-center gap-2 rounded-full border border-[var(--vf-b)] bg-white/[0.03] px-3 py-1 text-[9.5px] font-medium uppercase tracking-[0.18em] text-[var(--vf-m)]"
          style={{ fontFamily: "var(--vf-mono)" }}
        >
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
          />
          Studio IVR · Pipeline
        </div>
        <h1 className="mb-2 text-[clamp(26px,3vw,38px)] font-extrabold leading-tight tracking-[-1.5px]">
          Hola, <span className="bg-clip-text text-transparent" style={{ backgroundImage: "linear-gradient(110deg, var(--vf-c2), var(--vf-c1), var(--vf-c3))" }}>{user}</span>
        </h1>
        <p className="max-w-md text-[12.5px] leading-relaxed text-[var(--vf-m)]" style={{ fontFamily: "var(--vf-mono)" }}>
          Bienvenido de nuevo. Aquí tienes un resumen de tu cuenta y accesos rápidos a cada herramienta del pipeline.
        </p>
      </div>

      {error && <p className="mb-6 text-sm text-[var(--vf-danger)]">{error}</p>}

      {loading ? (
        <p className="text-[var(--vf-muted)]">Cargando…</p>
      ) : (
        <>
          {/* Usage / plan summary */}
          {profile && (
            <div className="mb-10 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-6">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-lg font-semibold">{profile.username}</p>
                  <p className="text-sm text-[var(--vf-muted)]">{profile.email}</p>
                </div>
                <div
                  className="rounded-full border border-[rgba(124,106,255,0.25)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]"
                  style={{ fontFamily: "var(--vf-mono)", background: "rgba(124,106,255,.14)", color: "var(--vf-c2)" }}
                >
                  Plan {profile.plan_name}
                </div>
              </div>
              <div className="flex flex-col gap-4 sm:flex-row">
                <UsageStat
                  label="Videos"
                  value={profile.usage?.videos ?? 0}
                  limit={profile.limits?.videos_per_month ?? null}
                />
                <UsageStat
                  label="Shorts"
                  value={profile.usage?.shorts ?? 0}
                  limit={profile.limits?.shorts_per_month ?? null}
                />
                <UsageStat
                  label="Caracteres TTS"
                  value={profile.usage?.tts_chars ?? 0}
                  limit={null}
                />
              </div>
            </div>
          )}

          {/* Recent projects */}
          <div className="mb-10">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[var(--vf-muted)]">Proyectos recientes</h2>
              <Link to="/app/proyectos" className="text-xs text-[var(--vf-accent)] hover:underline">
                Ver todos →
              </Link>
            </div>
            {recentProjects.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[var(--vf-b2)] bg-white/[0.02] p-8 text-center">
                <p className="text-sm text-[var(--vf-muted)]">Aún no tienes proyectos. Crea uno en Proyectos.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {recentProjects.map((p) => (
                  <Link
                    key={p.nombre}
                    to={`/app/proyectos/${encodeURIComponent(p.nombre)}`}
                    className="flex flex-col gap-1 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5 transition-colors hover:border-[rgba(124,106,255,0.3)]"
                  >
                    <h3 className="truncate text-base font-semibold">{p.nombre}</h3>
                    <p className="text-xs text-[var(--vf-muted)]">
                      {p.videos ?? 0} videos · {p.audios ?? 0} audios
                    </p>
                    {p.creado && (
                      <p className="mt-1 text-[10px] text-[var(--vf-m2)]" style={{ fontFamily: "var(--vf-mono)" }}>
                        {p.creado}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Pipeline shortcuts */}
          <div>
            <h2 className="mb-4 text-sm font-semibold text-[var(--vf-muted)]">Herramientas del pipeline</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {SHORTCUTS.map((s) => (
                <Link
                  key={s.to}
                  to={s.to}
                  className="group flex flex-col gap-3 rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)] p-5 transition-all hover:-translate-y-0.5 hover:border-[rgba(124,106,255,0.28)]"
                >
                  <div
                    className="flex h-[42px] w-[42px] items-center justify-center rounded-[11px] text-lg"
                    style={{ background: "rgba(124,106,255,.12)" }}
                  >
                    {s.icon}
                  </div>
                  <div>
                    <h3 className="mb-1 text-[14.5px] font-bold tracking-[-0.3px]">{s.title}</h3>
                    <p className="text-[10.5px] leading-relaxed text-[var(--vf-m)]" style={{ fontFamily: "var(--vf-mono)" }}>
                      {s.desc}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
