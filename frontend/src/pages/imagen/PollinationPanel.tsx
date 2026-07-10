import { useEffect, useState } from "react";
import { pollinationGenerate } from "../../api/whisk";
import { ErrorText, ImageGallery, SectionCard, countPrompts } from "./shared";
import type { GalleryImage } from "./shared";

const RATIOS: Record<string, { width: number; height: number }> = {
  "16:9": { width: 1920, height: 1097 },
  "9:16": { width: 1080, height: 1920 },
};

interface StatusMsg {
  type: "ok" | "error";
  text: string;
}

interface PollinationPanelProps {
  project: string;
  defaultOutputDir: string;
}

export default function PollinationPanel({ defaultOutputDir }: PollinationPanelProps) {
  const [prompts, setPrompts] = useState("");
  const [ratio, setRatio] = useState("16:9");
  const [outputDir, setOutputDir] = useState(defaultOutputDir || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [statusMsg, setStatusMsg] = useState<StatusMsg | null>(null);
  const [images, setImages] = useState<GalleryImage[]>([]);

  useEffect(() => {
    if (defaultOutputDir) setOutputDir(defaultOutputDir);
  }, [defaultOutputDir]);

  async function handleGenerate() {
    setError("");
    setStatusMsg(null);
    if (!prompts.trim()) {
      setError("Escribe al menos un prompt.");
      return;
    }
    setLoading(true);
    try {
      const { width, height } = RATIOS[ratio] || RATIOS["16:9"];
      const data = await pollinationGenerate({
        prompts,
        ratio,
        width,
        height,
        output_dir: outputDir,
      });
      const names = data.images || data.files || [];
      if (names.length) {
        setImages(
          names.map((n) => ({
            key: n,
            name: n,
            // Pollination has no dedicated image-serving endpoint documented;
            // fall back to showing filenames returned by the job if no URL given.
            src: data.urls?.[n] || n,
          })),
        );
      }
      setStatusMsg({ type: "ok", text: `Listo — ${names.length || "lote"} imagen(es) generadas.` });
    } catch (err) {
      setError((err as Error).message);
      setStatusMsg({ type: "error", text: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <p className="mb-4 max-w-xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
        Envía prompts al generador Pollination. Las imágenes se guardan en la carpeta{" "}
        <code className="rounded bg-white/[0.06] px-1.5 py-0.5">imagen/</code> del proyecto —
        la misma ruta que usa Whisk.
      </p>

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3 py-2">
        <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
          Destino:
        </span>
        <input
          value={outputDir}
          onChange={(e) => setOutputDir(e.target.value)}
          placeholder="— selecciona proyecto arriba o escribe una ruta —"
          className="flex-1 bg-transparent font-mono text-[11px] text-[var(--vf-c5)] outline-none"
        />
      </div>

      <div className="mb-4 flex flex-wrap items-start gap-4">
        <div className="min-w-[240px] flex-[2]">
          <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
            Prompts (uno por línea)
          </label>
          <textarea
            value={prompts}
            onChange={(e) => setPrompts(e.target.value)}
            placeholder="Un prompt por línea…"
            className="min-h-[160px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-white/[0.04] p-2.5 font-mono text-[11px] leading-relaxed text-[var(--vf-text)] outline-none"
          />
          <div className="mt-1.5 text-right font-mono text-[10px] text-[var(--vf-c2)]">
            {countPrompts(prompts)} prompts
          </div>
        </div>
        <div className="min-w-[160px] flex-1">
          <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
            Formato
          </label>
          <select
            value={ratio}
            onChange={(e) => setRatio(e.target.value)}
            className="w-full rounded-lg border border-[var(--vf-border)] bg-white/[0.04] px-2.5 py-2.5 font-mono text-xs text-[var(--vf-text)] outline-none"
          >
            <option value="16:9">YouTube (16:9)</option>
            <option value="9:16">TikTok / Reels (9:16)</option>
          </select>
        </div>
      </div>

      {statusMsg && (
        <div
          className="mb-3 rounded-lg border px-3.5 py-2.5 text-center font-mono text-[11px]"
          style={
            statusMsg.type === "error"
              ? { color: "var(--vf-danger)", borderColor: "rgba(239,68,68,.35)", background: "rgba(239,68,68,.06)" }
              : { color: "var(--vf-c5)", borderColor: "rgba(34,211,160,.3)", background: "rgba(34,211,160,.06)" }
          }
        >
          {statusMsg.text}
        </div>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="w-full rounded-lg border-none px-4 py-3 font-mono text-xs font-bold tracking-wide text-white disabled:cursor-not-allowed disabled:opacity-50"
        style={{ background: "linear-gradient(135deg, #8b5cf6, #a855f7)" }}
      >
        {loading ? "Generando…" : "Generar imágenes (Pollination)"}
      </button>
      <ErrorText message={error} />

      {images.length > 0 && (
        <SectionCard title="// Resultado" className="mt-4">
          <ImageGallery images={images} />
        </SectionCard>
      )}
    </div>
  );
}
