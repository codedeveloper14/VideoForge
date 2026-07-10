// Small shared UI bits reused across the Imagen sub-panels (Whisk/Pollination/Flow/Gentube).
import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface GalleryImage {
  key?: string;
  name?: string;
  src: string;
}

interface SectionCardProps {
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

interface StatBoxProps {
  value: ReactNode;
  label: string;
  color?: string;
}

export function StatBox({ value, label, color }: StatBoxProps) {
  return (
    <div className="rounded-lg border border-[var(--vf-border)] bg-white/[0.03] p-2 text-center">
      <div
        className="font-mono text-lg font-bold"
        style={{ color: color || "var(--vf-text)" }}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[9px] uppercase tracking-wider text-[var(--vf-m2)]">
        {label}
      </div>
    </div>
  );
}

interface ProgressBarProps {
  pct: number;
}

export function ProgressBar({ pct }: ProgressBarProps) {
  return (
    <div className="mb-1.5 h-[3px] overflow-hidden rounded-full bg-white/5">
      <div
        className="h-full rounded-full transition-all"
        style={{
          width: `${Math.max(0, Math.min(100, pct || 0))}%`,
          background: "linear-gradient(90deg, var(--vf-c1), var(--vf-c5))",
        }}
      />
    </div>
  );
}

interface ImageGalleryProps {
  images: GalleryImage[];
  emptyLabel?: string;
  renderOverlay?: (img: GalleryImage) => ReactNode;
}

export function ImageGallery({
  images,
  emptyLabel = "Sin imágenes todavía",
  renderOverlay,
}: ImageGalleryProps) {
  if (!images || images.length === 0) {
    return (
      <div className="py-10 text-center font-mono text-xs text-[var(--vf-m2)]">
        {emptyLabel}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-1.5">
      {images.map((img, i) => (
        <div
          key={img.key || img.src || i}
          className="group relative aspect-square overflow-hidden rounded-lg border border-[var(--vf-border)] bg-black/40"
        >
          <img
            src={img.src}
            alt={img.name || ""}
            loading="lazy"
            className="h-full w-full object-cover"
          />
          {renderOverlay && (
            <div className="absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-gradient-to-t from-black/80 to-transparent p-1 opacity-0 transition-opacity group-hover:opacity-100">
              {renderOverlay(img)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

interface LogConsoleProps {
  lines: string[];
}

export function LogConsole({ lines }: LogConsoleProps) {
  return (
    <div className="h-[240px] overflow-y-auto rounded-lg bg-black/20 p-3 font-mono text-[11px] leading-relaxed text-[var(--vf-muted)]">
      {lines.length === 0 ? (
        <span className="text-[var(--vf-m2)]">Esperando inicio…</span>
      ) : (
        lines.map((l, i) => <div key={i}>{l}</div>)
      )}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function PrimaryButton({ children, className = "", ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={
        "flex-1 rounded-lg border-none px-4 py-3 font-mono text-xs font-bold tracking-wide text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50 " +
        className
      }
      style={{ background: "linear-gradient(135deg, var(--vf-c1), #9f7aea)" }}
    >
      {children}
    </button>
  );
}

export function StopButton({ children = "Detener", className = "", ...props }: ButtonProps) {
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

export function GhostButton({ children, className = "", ...props }: ButtonProps) {
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

interface ErrorTextProps {
  message?: string;
}

export function ErrorText({ message }: ErrorTextProps) {
  if (!message) return null;
  return <p className="mt-2 text-xs text-[var(--vf-danger)]">{message}</p>;
}

export function countPrompts(text: string) {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean).length;
}
