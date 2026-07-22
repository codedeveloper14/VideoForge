// Small shared UI bits reused across the Video sub-panels (Grok/Qwen/Meta).
// Mirrors the pattern established in pages/imagen/shared.jsx for visual consistency.

import { useEffect, useState } from "react";
import type { ButtonHTMLAttributes, DragEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { getProjectContent, imagenFileUrl } from "../../api/projects";

export interface SectionCardProps {
  title?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
}

// Mirrors the legacy `.gk-card` treatment: 16px radius, subtle border,
// a 1px gradient hairline along the top edge, and an uppercase mono title.
export function SectionCard({ title, right, children, className = "" }: SectionCardProps) {
  return (
    <div
      className={
        "overflow-hidden rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] transition-colors focus-within:border-[color-mix(in_srgb,var(--vf-c1)_35%,transparent)] " +
        className
      }
    >
      <div
        className="h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(124,106,255,.2), transparent)",
        }}
      />
      {(title || right) && (
        <div className="flex items-center justify-between px-[18px] pb-2.5 pt-3.5">
          <span className="font-mono text-[10px] font-medium uppercase tracking-[.14em] text-[var(--vf-muted)]">
            {title}
          </span>
          {right}
        </div>
      )}
      <div className="px-[18px] pb-4 pt-1">{children}</div>
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

// Green-on-black terminal text, mirroring the legacy `#gk-log` palette
// (log-info #a0e8b0 / log-warn #fbbf24 / log-error #ff5566 / log-done #22d3a0).
export function LogConsole({ lines }: LogConsoleProps) {
  const { t } = useTranslation();
  return (
    <div className="max-h-[320px] min-h-[160px] overflow-y-auto px-4 py-3.5 font-mono text-[11px] leading-[1.7] break-all whitespace-pre-wrap text-[#a0e8b0]">
      {lines.length === 0 ? (
        <span className="text-[rgba(255,255,255,.25)]">{t("videoShared.waitingToStart")}</span>
      ) : (
        lines.map((l, i) => {
          const isErr = /❌|\[ERROR\]/.test(l);
          const isWarn = /\[WARNING\]/.test(l);
          const isOk = /✅|✓|completado/i.test(l);
          return (
            <div
              key={i}
              style={{
                color: isErr
                  ? "#ff5566"
                  : isWarn
                    ? "#fbbf24"
                    : isOk
                      ? "var(--vf-c5)"
                      : undefined,
                fontWeight: isOk ? 700 : undefined,
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

// Terminal card: black background, gradient hairline, traffic-light dots
// header with a centered title and a "limpiar" clear button — mirrors
// `.gk-terminal` / `.gk-term-header` from the legacy reference.
export interface TerminalCardProps {
  title: string;
  onClear?: () => void;
  children?: ReactNode;
}

export function TerminalCard({ title, onClear, children }: TerminalCardProps) {
  const { t } = useTranslation();
  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-[rgba(124,106,255,.15)] bg-[#0a0a0f]">
      <div
        className="h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(124,106,255,.3), transparent)",
        }}
      />
      <div className="flex items-center gap-2 border-b border-white/[0.04] px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        <span className="ml-1 flex-1 text-center font-mono text-[10px] tracking-[.08em] text-white/30">
          {title}
        </span>
        {onClear && (
          <button
            onClick={onClear}
            className="rounded px-1.5 py-0.5 font-mono text-[9px] text-white/25 hover:text-white/50"
          >
            {t("videoShared.clearLower")}
          </button>
        )}
      </div>
      {children}
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
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  const { t } = useTranslation();
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
      {children ?? t("videoShared.stop")}
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
  const { t } = useTranslation();
  const [dragOver, setDragOver] = useState(false);

  function handleFiles(fileList: FileList | File[]) {
    const imgs = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (imgs.length) onChange([...files, ...imgs]);
  }

  // Assets dragged from a project gallery (ProjectImagePicker, AssetGallery) arrive
  // as a URL via dataTransfer, not as a native File -- fetch() reconstructs a real
  // File so it flows through the same handleFiles() path as a manual drop.
  async function handleDraggedAsset(uri: string, filenameHint: string) {
    try {
      const resp = await fetch(uri);
      if (!resp.ok) return;
      const blob = await resp.blob();
      const name = filenameHint || decodeURIComponent(uri.split("/").pop() || "imagen");
      handleFiles([new File([blob], name, { type: blob.type || "image/png" })]);
    } catch {
      // dropped item wasn't a recognizable image asset -- ignore silently
    }
  }

  function removeAt(idx: number) {
    onChange(files.filter((_, i) => i !== idx));
  }

  function clearAll() {
    onChange([]);
  }

  return (
    <div>
      <label
        onDragOver={(e: DragEvent<HTMLLabelElement>) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e: DragEvent<HTMLLabelElement>) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files && e.dataTransfer.files.length) {
            handleFiles(e.dataTransfer.files);
            return;
          }
          const uri = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
          if (uri) {
            const filenameHint = e.dataTransfer.getData("application/x-vf-filename");
            void handleDraggedAsset(uri, filenameHint);
          }
        }}
        className={
          "relative block cursor-pointer rounded-xl border-[1.5px] border-dashed p-7 text-center transition-all " +
          (dragOver
            ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/[0.08]"
            : "border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.015)] hover:border-[color-mix(in_srgb,var(--vf-c1)_50%,transparent)] hover:bg-[color-mix(in_srgb,var(--vf-c1)_5%,transparent)]")
        }
      >
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
        <div className="mb-1.5 text-[28px]">🖼️</div>
        <div className="font-mono text-xs text-[var(--vf-text)]">
          <strong>{t("videoShared.clickOrDrag")}</strong> {t("videoShared.images")}
        </div>
        <div className="mt-1 font-mono text-[10px] text-[var(--vf-m2)]">
          {t("videoShared.imageFormatsHint")}
        </div>
      </label>

      {files.length > 0 && (
        <>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {files.map((f, i) => (
              <div
                key={i}
                className="group relative h-[52px] w-[52px] flex-shrink-0 overflow-hidden rounded-[7px] border border-[var(--vf-border)]"
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
            <span className="font-mono text-[10px] text-[var(--vf-c5)]">
              {t("videoShared.imageLoadedCount", { count: files.length })}
            </span>
            <button
              type="button"
              onClick={clearAll}
              className="font-mono text-[10px] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
            >
              {t("videoShared.clear")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Project image picker — pulls images already generated in Paso 2 (Flow/
// GenTube, saved under jobs/<project>/imagen) so they can be used as the
// animation source without the user manually re-downloading and re-uploading
// them. Fetched files are handed back as File objects so they flow through
// the exact same multipart-upload path as a manual drag/drop. ──
export interface ProjectImagePickerProps {
  project: string;
  selected: File[];
  onAdd: (files: File[]) => void;
}

export function ProjectImagePicker({ project, selected, onAdd }: ProjectImagePickerProps) {
  const { t } = useTranslation();
  const [sceneImages, setSceneImages] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetchingName, setFetchingName] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!project) {
      setSceneImages([]);
      return;
    }
    setLoading(true);
    setError("");
    getProjectContent(project)
      .then((data) => {
        const names = (data.scenes || [])
          .map((s) => s.image)
          .filter((img): img is string => Boolean(img));
        setSceneImages(names);
      })
      .catch(() => setSceneImages([]))
      .finally(() => setLoading(false));
  }, [project]);

  const selectedNames = new Set(selected.map((f) => f.name));

  async function addImage(name: string) {
    if (selectedNames.has(name)) return;
    setFetchingName(name);
    setError("");
    try {
      const res = await fetch(imagenFileUrl(project, name));
      if (!res.ok) throw new Error(t("videoShared.couldNotLoadImage") || "");
      const blob = await res.blob();
      const file = new File([blob], name, { type: blob.type || "image/png" });
      onAdd([file]);
    } catch {
      setError(t("videoShared.couldNotLoadImage") || "");
    } finally {
      setFetchingName(null);
    }
  }

  if (!project || (!loading && sceneImages.length === 0)) return null;

  return (
    <div className="mb-3 rounded-xl border border-[var(--vf-b2)] bg-[rgba(var(--vf-fg-rgb),.015)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
          {t("videoShared.fromProjectImages")}
        </span>
        {loading && <span className="font-mono text-[9px] text-[var(--vf-m2)]">{t("videoShared.loadingAccounts")}</span>}
      </div>
      {sceneImages.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {sceneImages.map((name) => {
            const isSelected = selectedNames.has(name);
            return (
              <button
                key={name}
                type="button"
                disabled={isSelected || fetchingName === name}
                onClick={() => addImage(name)}
                draggable={!isSelected}
                onDragStart={(e) => {
                  const url = imagenFileUrl(project, name);
                  e.dataTransfer.setData("text/uri-list", url);
                  e.dataTransfer.setData("text/plain", url);
                  e.dataTransfer.setData("application/x-vf-filename", name);
                  e.dataTransfer.effectAllowed = "copy";
                }}
                title={name}
                className={
                  "group relative h-[52px] w-[52px] flex-shrink-0 overflow-hidden rounded-[7px] border transition-opacity " +
                  (isSelected ? "border-[var(--vf-c5)] opacity-50" : "cursor-grab border-[var(--vf-border)] hover:border-[color-mix(in_srgb,var(--vf-c1)_50%,transparent)] active:cursor-grabbing")
                }
              >
                <img src={imagenFileUrl(project, name)} alt="" className="h-full w-full object-cover" draggable={false} />
                {isSelected && (
                  <span className="absolute inset-0 flex items-center justify-center bg-black/40 text-[13px] text-white">✓</span>
                )}
                {fetchingName === name && (
                  <span className="absolute inset-0 flex items-center justify-center bg-black/40 text-[9px] text-white">…</span>
                )}
              </button>
            );
          })}
        </div>
      )}
      <ErrorText message={error} />
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
  const { t } = useTranslation();
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[9.5px] uppercase tracking-wider text-[var(--vf-muted)]">
          {t("videoShared.accounts")}
        </span>
        <button
          onClick={onRefresh}
          className="rounded-md border border-[var(--vf-b2)] px-2 py-0.5 font-mono text-[9px] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
        >
          {t("videoShared.verify")}
        </button>
      </div>
      <div className="flex flex-col gap-1.5">
        {loading && (
          <div className="font-mono text-[10px] text-[var(--vf-m2)]">{t("videoShared.loadingAccounts")}</div>
        )}
        {!loading && error && (
          <div className="font-mono text-[10px] text-[var(--vf-danger)]">{error}</div>
        )}
        {!loading && !error && accounts.length === 0 && (
          <div className="font-mono text-[10px] text-[var(--vf-m2)]">
            {t("videoShared.noAccountFolders")}
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
                  {t("videoShared.login")}
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
    <div className="mt-1 flex flex-wrap gap-1.5">
      {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={
            "flex h-9 w-9 items-center justify-center rounded-lg border font-mono text-xs transition-all " +
            (n === value
              ? "border-[color-mix(in_srgb,var(--vf-c1)_50%,transparent)] bg-[color-mix(in_srgb,var(--vf-c1)_15%,transparent)] text-[var(--vf-c2)] shadow-[0_0_10px_rgba(124,106,255,.2)]"
              : "border-[var(--vf-b2)] text-[var(--vf-muted)] hover:border-[color-mix(in_srgb,var(--vf-c1)_40%,transparent)] hover:text-[var(--vf-text)]")
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
  const { t } = useTranslation();
  if (!videos || videos.length === 0) {
    return (
      <div className="py-10 text-center font-mono text-xs text-[var(--vf-m2)]">
        {t("videoShared.noVideosYetForProject")}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
      {videos.map((v) => (
        <div
          key={v}
          className="overflow-hidden rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] transition-all hover:-translate-y-0.5 hover:border-[color-mix(in_srgb,var(--vf-c1)_30%,transparent)]"
        >
          <video
            src={videoUrl(project, v)}
            className="block aspect-[2/3] w-full bg-[#111] object-cover"
            muted
            loop
            playsInline
            controls
            preload="metadata"
          />
          <div className="px-2.5 py-2">
            <div
              className="truncate font-mono text-[9px] text-[var(--vf-muted)]"
              title={v}
            >
              {v}
            </div>
            <a
              href={videoUrl(project, v, 1)}
              download={v}
              className="mt-1.5 block rounded-[5px] bg-[rgba(124,106,255,.08)] py-1 text-center font-mono text-[9.5px] text-[var(--vf-c2)] transition-colors hover:bg-[rgba(124,106,255,.18)]"
            >
              {t("videoShared.download")}
            </a>
            {onRegenerate && (
              <button
                onClick={() => onRegenerate(v)}
                className="mt-1.5 block w-full rounded-[5px] border py-1 text-center font-mono text-[9.5px]"
                style={{
                  background: "rgba(251,191,36,.1)",
                  borderColor: "rgba(251,191,36,.2)",
                  color: "var(--vf-c4)",
                }}
              >
                {t("videoShared.regen")}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
