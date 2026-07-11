import { useEffect, useMemo, useState } from "react";
import { listDocs } from "../api/docs";
import type { Doc } from "../api/docs";

function docThumbUrl(doc: Doc): string {
  if (doc.thumbnail_url) return doc.thumbnail_url;
  const marker = "youtube.com/embed/";
  const idx = doc.url ? doc.url.indexOf(marker) : -1;
  if (idx >= 0) {
    const rest = doc.url.slice(idx + marker.length);
    const videoId = rest.split("?")[0];
    return `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
  }
  return "";
}

export default function DocumentacionPage() {
  const [categories, setCategories] = useState<Record<string, Doc[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeDoc, setActiveDoc] = useState<Doc | null>(null);

  useEffect(() => {
    listDocs()
      .then((data) => {
        const cats = data.categories || {};
        setCategories(cats);
        const names = Object.keys(cats);
        setActiveCategory(names.length > 0 ? names[0] : null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const categoryNames = useMemo(() => Object.keys(categories), [categories]);

  const visibleDocs = useMemo(() => {
    const docs = activeCategory ? categories[activeCategory] || [] : [];
    const q = search.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter((d) => {
      const haystack = `${d.title || ""} ${d.description || ""} ${d.tags || ""}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [categories, activeCategory, search]);

  if (activeDoc) {
    return (
      <div className="max-w-3xl">
        <button
          onClick={() => setActiveDoc(null)}
          className="mb-8 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="15,18 9,12 15,6" />
          </svg>
          Volver
        </button>

        <h1 className="mb-2 text-2xl font-bold text-[var(--vf-text)]">{activeDoc.title}</h1>
        {activeDoc.description && (
          <p className="mb-7 text-sm text-[var(--vf-muted)]">{activeDoc.description}</p>
        )}

        {activeDoc.type === "video" && activeDoc.url ? (
          <div
            className="w-full overflow-hidden rounded-2xl border border-[var(--vf-border)] bg-black"
            style={{ aspectRatio: "16/9" }}
          >
            <iframe
              src={activeDoc.url}
              allow="autoplay;fullscreen;encrypted-media"
              allowFullScreen
              className="h-full w-full border-0"
              title={activeDoc.title}
            />
          </div>
        ) : (
          <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-7">
            {activeDoc.content ? (
              activeDoc.content
                .split(/\n{2,}/)
                .map((para, i) => (
                  <p key={i} className="mb-4 text-sm leading-relaxed text-[var(--vf-text)] last:mb-0">
                    {para}
                  </p>
                ))
            ) : (
              <p className="text-sm text-[var(--vf-muted)]">Sin contenido disponible.</p>
            )}
            {activeDoc.url && (
              <a
                href={activeDoc.url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-block text-sm text-[var(--vf-accent)] hover:underline"
              >
                Ver recurso →
              </a>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <h1
        className="mb-2 text-3xl font-extrabold"
        style={{
          background: "linear-gradient(90deg, #eef2ff 30%, rgba(167,139,250,.7))",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          backgroundClip: "text",
        }}
      >
        Documentación
      </h1>
      <p className="mb-7 text-[11.5px] text-[var(--vf-muted)]">
        Tutoriales, guías y recursos para VideoForge
      </p>

      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      {loading ? (
        <p className="text-[var(--vf-muted)]">Cargando…</p>
      ) : categoryNames.length === 0 ? (
        <p className="text-[var(--vf-muted)]">No hay contenidos publicados aún.</p>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-2.5">
            <div className="flex flex-wrap gap-2">
              {categoryNames.map((name) => (
                <button
                  key={name}
                  onClick={() => setActiveCategory(name)}
                  className={`whitespace-nowrap rounded-full border px-4 py-1.5 text-xs font-semibold transition-colors ${
                    activeCategory === name
                      ? "border-[var(--vf-accent)]/35 bg-[var(--vf-accent)]/16 text-[var(--vf-c2)]"
                      : "border-[var(--vf-border)] bg-white/[0.04] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
                  }`}
                >
                  {name}
                  <span className="ml-1.5 text-[9px] opacity-70">{categories[name].length}</span>
                </button>
              ))}
            </div>

            <div className="relative ml-auto">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 opacity-30"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar..."
                className="w-[220px] rounded-xl border border-[var(--vf-border)] bg-white/5 py-2 pl-9 pr-3.5 text-sm text-[var(--vf-text)] outline-none focus:border-[var(--vf-accent)]/45"
              />
            </div>
          </div>

          {visibleDocs.length === 0 ? (
            <p className="py-16 text-center text-[var(--vf-muted)]">
              No hay contenidos en esta categoría.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {visibleDocs.map((doc) => {
                const isVideo = doc.type === "video";
                const thumb = isVideo ? docThumbUrl(doc) : "";
                return (
                  <div
                    key={doc.id}
                    onClick={() => setActiveDoc(doc)}
                    className="group cursor-pointer overflow-hidden rounded-2xl border border-[var(--vf-border)] bg-white/[0.03] transition-all hover:-translate-y-1 hover:border-[var(--vf-accent)]/30 hover:bg-[var(--vf-accent)]/[0.06]"
                  >
                    {isVideo ? (
                      <div className="relative w-full bg-black" style={{ aspectRatio: "16/9" }}>
                        {thumb ? (
                          <img
                            src={thumb}
                            loading="lazy"
                            className="h-full w-full object-cover opacity-75 transition-opacity group-hover:opacity-95"
                          />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[var(--vf-accent)]/10 to-purple-500/5">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(124,106,255,.4)" strokeWidth="1.5">
                              <polygon points="5,3 19,12 5,21" />
                            </svg>
                          </div>
                        )}
                        {doc.duration_label && (
                          <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-white">
                            {doc.duration_label}
                          </span>
                        )}
                      </div>
                    ) : (
                      <div
                        className="flex w-full items-center justify-center border-b border-[var(--vf-c5)]/10 bg-gradient-to-br from-[var(--vf-c5)]/[0.06] to-emerald-500/[0.02]"
                        style={{ aspectRatio: "16/9" }}
                      >
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="rgba(34,211,160,.4)" strokeWidth="1.5">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14 2 14 8 20 8" />
                          <line x1="16" y1="13" x2="8" y2="13" />
                          <line x1="16" y1="17" x2="8" y2="17" />
                        </svg>
                      </div>
                    )}
                    <div className="p-4.5 px-[18px] py-4">
                      <span
                        className={`mb-2.5 inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${
                          isVideo
                            ? "border-[var(--vf-accent)]/20 bg-[var(--vf-accent)]/[0.12] text-[var(--vf-c2)]"
                            : "border-[var(--vf-c5)]/15 bg-[var(--vf-c5)]/[0.08] text-[var(--vf-c5)]"
                        }`}
                      >
                        {isVideo ? "▶ Video" : "☰ Texto"}
                      </span>
                      <p className="mb-1.5 text-sm font-bold leading-snug text-[var(--vf-text)]">
                        {doc.title}
                      </p>
                      {doc.description && (
                        <p className="line-clamp-2 text-[11.5px] leading-relaxed text-[var(--vf-muted)]">
                          {doc.description}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
