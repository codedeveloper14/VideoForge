import { useState } from "react";
import { buscarImagen, proxyImagen } from "../../api/editor";

export interface ImageSearchPick {
  url: string;
  b64?: string;
}

export interface ImageSearchModalProps {
  sceneIndex: number;
  initialQuery: string;
  onClose: () => void;
  onPick: (sceneIndex: number, pick: ImageSearchPick) => void;
}

export default function ImageSearchModal({
  sceneIndex,
  initialQuery,
  onClose,
  onPick,
}: ImageSearchModalProps) {
  const [query, setQuery] = useState(initialQuery || "");
  const [urls, setUrls] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [pickingUrl, setPickingUrl] = useState("");
  const [error, setError] = useState("");

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await buscarImagen({ query: query.trim(), n: 8 });
      setUrls(data.urls || []);
      if (!data.urls?.length) setError("Sin resultados para esa búsqueda.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handlePick(url: string) {
    setPickingUrl(url);
    setError("");
    try {
      const data = await proxyImagen(url);
      if (data.error) throw new Error(data.error);
      onPick(sceneIndex, { url, b64: data.b64 });
    } catch (err) {
      setError(`No se pudo cargar esa imagen: ${(err as Error).message}`);
    } finally {
      setPickingUrl("");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--vf-b)] bg-[var(--vf-s)] p-5"
      >
        <div className="mb-3.5 flex items-center justify-between">
          <h3 className="font-mono text-[11px] font-semibold uppercase tracking-[.09em] text-[var(--vf-c2)]">
            Buscar imagen — Escena {sceneIndex + 1}
          </h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[var(--vf-m2)] transition-colors hover:text-[var(--vf-text)]"
          >
            ✕
          </button>
        </div>

        <div className="mb-3.5 flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Query de búsqueda…"
            className="flex-1 rounded-[9px] border border-[var(--vf-b)] bg-white/[0.05] px-3 py-2.5 text-[12.5px] text-[var(--vf-text)] outline-none focus:border-[var(--vf-c5)]/50"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border-none px-4 py-2.5 font-mono text-xs font-bold text-white transition-all disabled:opacity-50"
            style={{
              background: "linear-gradient(135deg, var(--vf-c5), var(--vf-c1))",
              boxShadow: "0 6px 22px rgba(34,211,160,.3)",
            }}
          >
            <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            {loading ? "Buscando…" : "Buscar"}
          </button>
        </div>

        {error && (
          <p className="mb-2 rounded-lg border border-[var(--vf-danger)]/30 bg-[var(--vf-danger)]/10 px-3 py-2 text-xs text-[var(--vf-danger)]">
            {error}
          </p>
        )}

        {urls.length > 0 && (
          <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
            {urls.map((url) => (
              <button
                key={url}
                onClick={() => handlePick(url)}
                disabled={pickingUrl === url}
                className="group relative aspect-video overflow-hidden rounded-lg border-2 border-transparent bg-black/30 transition-colors hover:border-[var(--vf-c5)] disabled:opacity-50"
              >
                <img src={url} alt="" loading="lazy" className="h-full w-full object-cover" />
                <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                  <span className="font-mono text-[10px] font-bold text-white">
                    {pickingUrl === url ? "Cargando…" : "Usar esta"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}

        {!loading && urls.length === 0 && !error && (
          <p className="py-8 text-center font-mono text-xs text-[var(--vf-m2)]">
            Escribe una búsqueda y presiona Buscar.
          </p>
        )}
      </div>
    </div>
  );
}
