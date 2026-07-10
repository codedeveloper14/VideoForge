import { useEffect, useState, type FormEvent } from "react";
import { listDocs, submitHelpRequest } from "../api/docs";
import type { Doc, HelpSubmitPayload } from "../api/docs";

const emptyForm: HelpSubmitPayload = { title: "", description: "", category: "", type: "" };

export default function HelpPage() {
  const [categories, setCategories] = useState<Record<string, Doc[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState<HelpSubmitPayload>(emptyForm);
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    listDocs()
      .then((data) => setCategories(data.categories || {}))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setError("");
    try {
      await submitHelpRequest(form);
      setSent(true);
      setForm(emptyForm);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="mb-6 text-2xl font-semibold">Ayuda</h1>

      {loading ? (
        <p className="text-[var(--vf-muted)]">Cargando…</p>
      ) : Object.keys(categories).length === 0 ? (
        <p className="mb-8 text-[var(--vf-muted)]">Aún no hay artículos publicados.</p>
      ) : (
        <div className="mb-8 space-y-6">
          {Object.entries(categories).map(([category, docs]) => (
            <div key={category}>
              <h2 className="mb-2 text-sm font-semibold text-[var(--vf-muted)]">{category}</h2>
              <div className="space-y-2">
                {docs.map((doc) => (
                  <div
                    key={doc.id}
                    className="rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4"
                  >
                    <p className="font-medium">{doc.title}</p>
                    {doc.description && (
                      <p className="mt-1 text-sm text-[var(--vf-muted)]">{doc.description}</p>
                    )}
                    {doc.url && (
                      <a
                        href={doc.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-block text-sm text-[var(--vf-accent)] hover:underline"
                      >
                        Ver más →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-6">
        <h2 className="mb-4 text-lg font-semibold">¿Necesitas ayuda?</h2>
        {sent ? (
          <p className="text-sm text-[var(--vf-success)]">
            Gracias, recibimos tu mensaje y te responderemos pronto.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Asunto"
              required
              className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
            />
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Cuéntanos qué necesitas"
              rows={4}
              className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
            />
            {error && <p className="text-sm text-[var(--vf-danger)]">{error}</p>}
            <button
              type="submit"
              disabled={sending}
              className="self-start rounded-lg bg-[var(--vf-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
            >
              {sending ? "Enviando…" : "Enviar"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
