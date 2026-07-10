import { useState } from "react";
import { generarMiniaturas, miniaturaImageUrl } from "../api/miniaturas";

interface Template {
  label: string;
  prompt: string;
}

const TEMPLATES: Template[] = [
  {
    label: "MrBeast llamativo",
    prompt:
      "YouTube thumbnail, MrBeast style, hyper expressive shocked face, bold saturated colors, huge bright yellow bold text, high contrast, dramatic lighting, high CTR, 16:9",
  },
  {
    label: "Minimalista texto grande",
    prompt:
      "Minimalist YouTube thumbnail, clean flat background, one large bold sans-serif word, simple centered subject, plenty of negative space, modern high-CTR design, 16:9",
  },
  {
    label: "Documental / cinematico",
    prompt:
      "Cinematic YouTube thumbnail, dramatic moody lighting, film grain, high detail, subtle text overlay, dark vignette, epic documentary style, 16:9",
  },
];

interface RatioOption {
  width: number;
  height: number;
  label: string;
}

const RATIOS: Record<string, RatioOption> = {
  "16:9": { width: 1920, height: 1097, label: "YouTube (16:9)" },
  "9:16": { width: 1080, height: 1920, label: "Shorts / Reels (9:16)" },
  "1:1": { width: 1080, height: 1080, label: "Cuadrado (1:1)" },
};

interface GeneratedImage {
  name: string;
  src: string;
}

export default function MiniaturasPage() {
  const [prompt, setPrompt] = useState("");
  const [ratio, setRatio] = useState("16:9");
  const [count, setCount] = useState(4);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [images, setImages] = useState<GeneratedImage[]>([]);

  async function handleGenerate() {
    setError("");
    if (!prompt.trim()) {
      setError("Escribe un prompt para la miniatura.");
      return;
    }
    setLoading(true);
    setImages([]);
    try {
      const { width, height } = RATIOS[ratio] || RATIOS["16:9"];
      const n = Math.max(1, Math.min(8, Number(count) || 1));
      const prompts = Array.from({ length: n }, () => prompt.trim());
      const data = await generarMiniaturas({ prompts, ratio, width, height });
      const files = data.images || [];
      setImages(files.map((name) => ({ name, src: miniaturaImageUrl(name) + `?t=${Date.now()}` })));
      if (!files.length) setError("No se generaron imágenes.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-5">
        <div className="mb-1.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-c5)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--vf-c5)]" />
          Generador de Miniaturas
        </div>
        <h1 className="text-2xl font-bold text-[var(--vf-text)]">
          Miniaturas <span className="text-[var(--vf-c1)]">de alto CTR</span>
        </h1>
        <p className="mt-1.5 max-w-2xl font-mono text-xs leading-relaxed text-[var(--vf-muted)]">
          Escribe un prompt (o usa una plantilla), elige el formato y genera variantes con
          Pollination.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {TEMPLATES.map((t) => (
          <button
            key={t.label}
            onClick={() => setPrompt(t.prompt)}
            className="rounded-full border border-[var(--vf-border)] bg-[var(--vf-surface)] px-3.5 py-1.5 font-mono text-[11px] text-[var(--vf-muted)] transition-colors hover:border-[var(--vf-c1)] hover:text-[var(--vf-text)]"
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mb-4 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
        <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
          Prompt
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe la miniatura que quieres generar…"
          className="min-h-[110px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-white/[0.04] p-3 font-mono text-[12px] leading-relaxed text-[var(--vf-text)] outline-none"
        />

        <div className="mt-3 flex flex-wrap items-end gap-4">
          <div className="min-w-[180px]">
            <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              Formato
            </label>
            <select
              value={ratio}
              onChange={(e) => setRatio(e.target.value)}
              className="w-full rounded-lg border border-[var(--vf-border)] bg-white/[0.04] px-2.5 py-2 font-mono text-xs text-[var(--vf-text)] outline-none"
            >
              {Object.entries(RATIOS).map(([key, r]) => (
                <option key={key} value={key}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div className="w-[100px]">
            <label className="mb-1.5 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              Variantes
            </label>
            <input
              type="number"
              min={1}
              max={8}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="w-full rounded-lg border border-[var(--vf-border)] bg-white/[0.04] px-2.5 py-2 text-center font-mono text-xs text-[var(--vf-text)] outline-none"
            />
          </div>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="ml-auto rounded-lg border-none px-6 py-2.5 font-mono text-xs font-bold tracking-wide text-white disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "linear-gradient(135deg, var(--vf-c1), var(--vf-c3))" }}
          >
            {loading ? "Generando…" : "Generar miniaturas"}
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-[var(--vf-danger)]">{error}</p>}
      </div>

      <div className="rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
        <div className="mb-3 font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
          Resultado
        </div>
        {images.length === 0 ? (
          <div className="py-14 text-center font-mono text-xs text-[var(--vf-muted)]">
            {loading ? "Generando miniaturas…" : "Las miniaturas generadas aparecerán aquí."}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {images.map((img) => (
              <div
                key={img.name}
                className="group relative aspect-video overflow-hidden rounded-lg border border-[var(--vf-border)] bg-black/30"
              >
                <img src={img.src} alt={img.name} loading="lazy" className="h-full w-full object-cover" />
                <a
                  href={img.src}
                  download={img.name}
                  className="absolute bottom-1.5 right-1.5 rounded-md bg-black/70 px-2 py-1 font-mono text-[9px] text-white opacity-0 transition-opacity group-hover:opacity-100"
                >
                  Descargar
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
