// Small shared UI bits reused across the Video sub-panels (Grok/Qwen/Meta).
// Mirrors the pattern established in pages/imagen/shared.jsx for visual consistency.

import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface SectionCardProps {
  title?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function SectionCard({ title, right, children, className = "" }: SectionCardProps) {
  return (
    <div
      className={
        "overflow-hidden rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] " +
        className
      }
    >
      {(title || right) && (
        <div className="flex items-center justify-between border-b border-[var(--vf-border)] px-3 py-2">
          <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
            {title}
          </span>
          {right}
        </div>
      )}
      <div className="p-3">{children}</div>
    </div>
  );
}

export interface ProgressBarProps {
  pct: number;
}

export function ProgressBar({ pct }: ProgressBarProps) {
  return (
    <div className="mb-1.5 h-[4px] overflow-hidden rounded-full bg-[rgba(var(--vf-fg-rgb),0.05)]">
      <div
        className="h-full rounded-full transition-all"
        style={{
          width: `${Math.max(0, Math.min(100, pct || 0))}%`,
          background: "linear-gradient(90deg, var(--vf-c1), var(--vf-c2))",
        }}
      />
    </div>
  );
}

export interface LogConsoleProps {
  lines: string[];
}

export function LogConsole({ lines }: LogConsoleProps) {
  return (
    <div className="h-[260px] overflow-y-auto rounded-lg bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-[var(--vf-muted)]">
      {lines.length === 0 ? (
        <span className="text-[var(--vf-m2)]">Esperando inicio...</span>
      ) : (
        lines.map((l, i) => {
          const isErr = /❌|\[ERROR\]/.test(l);
          const isWarn = /\[WARNING\]/.test(l);
          const isOk = /✅|✓/.test(l);
          return (
            <div
              key={i}
              style={{
                color: isErr
                  ? "var(--vf-danger)"
                  : isWarn
                    ? "var(--vf-c4)"
                    : isOk
                      ? "var(--vf-success)"
                      : undefined,
              }}
            >
              {l}
            </div>
          );
        })
      )}
    </div>
  );
}

export function PrimaryButton({
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        "rounded-lg border-none px-4 py-3 font-mono text-xs font-bold tracking-wide text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50 " +
        className
      }
      style={{ background: "linear-gradient(135deg, var(--vf-c1), var(--vf-c2))" }}
    >
      {children}
    </button>
  );
}

export function StopButton({
  children = "Detener",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        "rounded-lg border px-5 py-3 font-mono text-xs font-semibold transition-opacity disabled:cursor-not-allowed disabled:opacity-40 " +
        className
      }
      style={{
        background: "rgba(239,68,68,.08)",
        borderColor: "rgba(239,68,68,.35)",
        color: "#ef4444",
      }}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        "rounded-lg border border-[var(--vf-b2)] bg-transparent px-3 py-2 font-mono text-[11px] text-[var(--vf-muted)] hover:text-[var(--vf-text)] disabled:cursor-not-allowed disabled:opacity-40 " +
        className
      }
    >
      {children}
    </button>
  );
}

export interface ErrorTextProps {
  message?: string;
}

export function ErrorText({ message }: ErrorTextProps) {
  if (!message) return null;
  return <p className="mt-2 text-xs text-[var(--vf-danger)]">{message}</p>;
}

// ── Image slot uploader — ordered list of files, drag/drop + file input ──
export interface ImageSlotsProps {
  files: File[];
  onChange: (files: File[]) => void;
}

export function ImageSlots({ files, onChange }: ImageSlotsProps) {
  function handleFiles(fileList: FileList) {
    const imgs = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (imgs.length) onChange([...files, ...imgs]);
  }

  function removeAt(idx: number) {
    onChange(files.filter((_, i) => i !== idx));
  }

  function clearAll() {
    onChange([]);
  }

  return (
    <div>
      <label className="block cursor-pointer rounded-lg border border-dashed border-[var(--vf-b2)] p-5 text-center transition-colors hover:border-[var(--vf-c1)]">
        <input
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.webp,.gif,.bmp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length) handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="mb-1 text-2xl">🖼️</div>
        <div className="font-mono text-xs text-[var(--vf-text)]">
          <strong>Clic o arrastra</strong> las imágenes
        </div>
        <div className="mt-1 font-mono text-[10px] text-[var(--vf-m2)]">
          JPG · PNG · WEBP · múltiples a la vez · se numeran en orden de subida
        </div>
      </label>

      {files.length > 0 && (
        <>
          <div className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(80px,1fr))] gap-2">
            {files.map((f, i) => (
              <div
                key={i}
                className="group relative aspect-square overflow-hidden rounded-lg border border-[var(--vf-border)] bg-black/40"
              >
                <img
                  src={URL.createObjectURL(f)}
                  alt=""
                  className="h-full w-full object-cover"
                />
                <span className="absolute left-1 top-1 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] text-white">
                  {i + 1}
                </span>
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  className="absolute right-1 top-1 hidden rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] text-white group-hover:block"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-center gap-3">
            <span className="font-mono text-[10px] text-[var(--vf-success)]">
              ✓ {files.length} imagen{files.length !== 1 ? "es" : ""} cargada
              {files.length !== 1 ? "s" : ""}
            </span>
            <button
              type="button"
              onClick={clearAll}
              className="font-mono text-[10px] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
            >
              ✕ Limpiar
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Account/session manager — list, login, delete ──
export interface AccountSessionInfo {
  name: string;
  active: boolean;
  user?: string;
}

export interface AccountSessionsProps {
  accounts: AccountSessionInfo[];
  loading: boolean;
  error: string;
  onLogin: (name: string) => void;
  onDelete: (name: string) => void;
  onRefresh: () => void;
}

export function AccountSessions({
  accounts,
  loading,
  error,
  onLogin,
  onDelete,
  onRefresh,
}: AccountSessionsProps) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
          Cuentas
        </span>
        <button
          onClick={onRefresh}
          className="rounded-md border border-[var(--vf-b2)] px-2 py-0.5 font-mono text-[9px] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
        >
          ↺ Verificar
        </button>
      </div>
      <div className="flex flex-col gap-1.5">
        {loading && (
          <div className="font-mono text-[10px] text-[var(--vf-m2)]">Cargando cuentas...</div>
        )}
        {!loading && error && (
          <div className="font-mono text-[10px] text-[var(--vf-danger)]">{error}</div>
        )}
        {!loading && !error && accounts.length === 0 && (
          <div className="font-mono text-[10px] text-[var(--vf-m2)]">
            No hay carpetas en accounts/
          </div>
        )}
        {!loading &&
          accounts.map((a) => (
            <div
              key={a.name}
              className="flex items-center justify-between rounded-md border border-[var(--vf-border)] bg-[var(--vf-p)] px-2 py-1.5"
            >
              <span
                className="font-mono text-[10px]"
                style={{ color: a.active ? "var(--vf-success)" : "var(--vf-m2)" }}
              >
                {a.active ? "✓ " : "○ "}
                {a.name}
                {a.user ? ` (${a.user})` : ""}
              </span>
              <div className="flex gap-1.5">
                {a.active && (
                  <button
                    onClick={() => onDelete(a.name)}
                    className="rounded-md border border-[rgba(239,68,68,.3)] bg-[rgba(239,68,68,.1)] px-1.5 py-0.5 font-mono text-[9px] text-[#ef4444]"
                  >
                    ✕
                  </button>
                )}
                <button
                  onClick={() => onLogin(a.name)}
                  className="rounded-md border border-[var(--vf-b2)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--vf-muted)]"
                >
                  🔑 Login
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

// ── Slot count picker (1..12 buttons) ──
export interface SlotPickerProps {
  value: number;
  onChange: (n: number) => void;
  max?: number;
}

export function SlotPicker({ value, onChange, max = 12 }: SlotPickerProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={
            "h-7 w-7 rounded-md border font-mono text-[11px] transition-colors " +
            (n === value
              ? "border-[var(--vf-c1)] bg-[var(--vf-c1)] text-white"
              : "border-[var(--vf-b2)] text-[var(--vf-muted)] hover:border-[var(--vf-c1)]")
          }
        >
          {n}
        </button>
      ))}
    </div>
  );
}

// ── Video gallery grid ──
export interface VideoGalleryProps {
  videos: string[];
  project: string;
  videoUrl: (project: string, file: string, dl?: number) => string;
  onRegenerate?: (videoName: string) => void;
}

export function VideoGallery({ videos, project, videoUrl, onRegenerate }: VideoGalleryProps) {
  if (!videos || videos.length === 0) {
    return (
      <div className="py-10 text-center font-mono text-xs text-[var(--vf-m2)]">
        Aún no hay videos generados para este proyecto.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
      {videos.map((v) => (
        <div
          key={v}
          className="overflow-hidden rounded-lg border border-[var(--vf-border)] bg-[var(--vf-p)] transition-transform hover:-translate-y-0.5"
        >
          <video
            src={videoUrl(project, v)}
            className="h-[110px] w-full object-cover"
            muted
            loop
            playsInline
            controls
            preload="metadata"
          />
          <div
            className="truncate px-2 py-1.5 font-mono text-[9px] text-[var(--vf-muted)]"
            title={v}
          >
            {v}
          </div>
          <div className="flex gap-1.5 px-2 pb-2">
            <a
              href={videoUrl(project, v, 1)}
              download={v}
              className="flex-1 rounded-md px-2 py-1 text-center font-mono text-[9px] text-white"
              style={{ background: "linear-gradient(135deg, var(--vf-c1), var(--vf-c2))" }}
            >
              ⬇ Descargar
            </a>
            {onRegenerate && (
              <button
                onClick={() => onRegenerate(v)}
                className="rounded-md border px-2 py-1 font-mono text-[9px]"
                style={{
                  background: "rgba(251,191,36,.1)",
                  borderColor: "rgba(251,191,36,.2)",
                  color: "var(--vf-c4)",
                }}
              >
                ↺ Regen
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
