import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  createAdminDoc,
  deleteAdminDoc,
  listAdminDocs,
  updateAdminDoc,
  type AdminDoc,
  type AdminDocInput,
} from "../api/adminDocs";
import { Select, SelectOption } from "../components/Select";

const EMPTY_FORM: AdminDocInput = {
  type: "video",
  category: "General",
  title: "",
  description: "",
  url: "",
  content: "",
  thumbnail_url: "",
  duration_label: "",
  tags: "",
  sort_order: 0,
  is_published: true,
};

interface DocFormModalProps {
  initial: AdminDocInput;
  saving: boolean;
  onClose: () => void;
  onSave: (data: AdminDocInput) => void;
}

function DocFormModal({ initial, saving, onClose, onSave }: DocFormModalProps) {
  const { t } = useTranslation();
  const [form, setForm] = useState<AdminDocInput>(initial);

  function set<K extends keyof AdminDocInput>(key: K, value: AdminDocInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSave(form);
  }

  return (
    <div className="fixed inset-0 z-[8100] flex items-center justify-center bg-black/55" onClick={onClose}>
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] w-full max-w-[560px] overflow-y-auto rounded-2xl border border-[rgba(var(--vf-fg-rgb),0.1)] bg-[var(--vf-s)] p-7 shadow-[0_24px_64px_rgba(0,0,0,.5)]"
      >
        <div className="mb-5 text-base font-bold text-[var(--vf-text)]">
          {initial.title ? t("adminDocs.editDocument") : t("adminDocs.newDocument")}
        </div>

        <div className="mb-3 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.type")}
            </label>
            <Select
              value={form.type}
              onChange={(v) => set("type", v)}
              className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            >
              <SelectOption value="video">{t("adminDocs.typeVideo")}</SelectOption>
              <SelectOption value="text">{t("adminDocs.typeText")}</SelectOption>
            </Select>
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.category")}
            </label>
            <input
              type="text"
              value={form.category}
              onChange={(e) => set("category", e.target.value)}
              className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            />
          </div>
        </div>

        <div className="mb-3">
          <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
            {t("adminDocs.titleLabel")}
          </label>
          <input
            type="text"
            required
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
          />
        </div>

        <div className="mb-3">
          <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
            {t("adminDocs.description")}
          </label>
          <textarea
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            rows={2}
            className="w-full resize-y rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
          />
        </div>

        <div className="mb-3">
          <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
            {form.type === "video" ? t("adminDocs.urlYoutube") : t("adminDocs.urlExternalOptional")}
          </label>
          <input
            type="text"
            value={form.url}
            onChange={(e) => set("url", e.target.value)}
            className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
          />
        </div>

        {form.type === "text" && (
          <div className="mb-3">
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.content")}
            </label>
            <textarea
              value={form.content}
              onChange={(e) => set("content", e.target.value)}
              rows={5}
              placeholder={t("adminDocs.contentPlaceholder") || ""}
              className="w-full resize-y rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            />
          </div>
        )}

        <div className="mb-3 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.thumbnailUrl")}
            </label>
            <input
              type="text"
              value={form.thumbnail_url}
              onChange={(e) => set("thumbnail_url", e.target.value)}
              className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.durationExample")}
            </label>
            <input
              type="text"
              value={form.duration_label}
              onChange={(e) => set("duration_label", e.target.value)}
              className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            />
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.tagsCommaSeparated")}
            </label>
            <input
              type="text"
              value={form.tags}
              onChange={(e) => set("tags", e.target.value)}
              className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
              {t("adminDocs.order")}
            </label>
            <input
              type="number"
              value={form.sort_order}
              onChange={(e) => set("sort_order", Number(e.target.value))}
              className="w-full rounded-[9px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-3.5 py-2.5 text-sm text-[var(--vf-text)] outline-none"
            />
          </div>
        </div>

        <label className="mb-5 flex items-center gap-2 text-sm text-[var(--vf-text)]">
          <input
            type="checkbox"
            checked={form.is_published}
            onChange={(e) => set("is_published", e.target.checked)}
            className="accent-[var(--vf-c1)]"
          />
          {t("adminDocs.published")}
        </label>

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={saving}
            className="flex-1 rounded-[9px] border-none bg-gradient-to-br from-[#7c6aff] to-[#5b42f3] py-2.5 text-[13px] font-bold text-white transition-transform hover:-translate-y-0.5 disabled:opacity-50"
          >
            {saving ? t("adminDocs.saving") : t("adminDocs.save")}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-[9px] border border-[var(--vf-border)] px-5 py-2.5 text-[13px] font-medium text-[var(--vf-text)] hover:bg-[var(--vf-surface-2)]"
          >
            {t("adminDocs.cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function AdminDocsPage() {
  const { t } = useTranslation();
  const [docs, setDocs] = useState<AdminDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<AdminDoc | null>(null);
  const [creating, setCreating] = useState(false);

  function load() {
    setLoading(true);
    setError("");
    listAdminDocs()
      .then(setDocs)
      .catch((err: Error) => setError(err.message || t("adminDocs.noPermission")))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleSave(data: AdminDocInput) {
    setSaving(true);
    try {
      if (editing) {
        await updateAdminDoc(editing.id, data);
      } else {
        await createAdminDoc(data);
      }
      setEditing(null);
      setCreating(false);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(doc: AdminDoc) {
    if (!confirm(t("adminDocs.confirmDelete", { title: doc.title }))) return;
    try {
      await deleteAdminDoc(doc.id);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--vf-text)]">{t("adminDocs.title")}</h1>
          <p className="mt-1 text-sm text-[var(--vf-muted)]">
            {t("adminDocs.subtitle")}
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="rounded-lg bg-[var(--vf-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--vf-accent-hover)]"
        >
          {t("adminDocs.newDoc")}
        </button>
      </div>

      {loading ? (
        <p className="text-[var(--vf-muted)]">{t("adminDocs.loading")}</p>
      ) : error ? (
        <p className="text-sm text-[var(--vf-danger)]">{error}</p>
      ) : docs.length === 0 ? (
        <p className="text-[var(--vf-muted)]">{t("adminDocs.noDocsYet")}</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)]">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--vf-border)] text-[11px] uppercase tracking-wider text-[var(--vf-muted)]">
                <th className="px-4 py-2.5">{t("adminDocs.colTitle")}</th>
                <th className="px-4 py-2.5">{t("adminDocs.colCategory")}</th>
                <th className="px-4 py-2.5">{t("adminDocs.colType")}</th>
                <th className="px-4 py-2.5">{t("adminDocs.colStatus")}</th>
                <th className="px-4 py-2.5">{t("adminDocs.colCreatedBy")}</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id} className="border-b border-[var(--vf-border)] last:border-0">
                  <td className="max-w-[220px] truncate px-4 py-2.5">{doc.title}</td>
                  <td className="px-4 py-2.5 text-[var(--vf-muted)]">{doc.category}</td>
                  <td className="px-4 py-2.5 text-[var(--vf-muted)]">{doc.type}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                        doc.is_published
                          ? "bg-[var(--vf-success)]/15 text-[var(--vf-success)]"
                          : "bg-[rgba(var(--vf-fg-rgb),0.08)] text-[var(--vf-muted)]"
                      }`}
                    >
                      {doc.is_published ? t("adminDocs.published_status") : t("adminDocs.draft")}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-[var(--vf-muted)]">{doc.created_by}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => setEditing(doc)}
                      className="mr-3 text-[var(--vf-accent)] hover:underline"
                    >
                      {t("adminDocs.edit")}
                    </button>
                    <button
                      onClick={() => handleDelete(doc)}
                      className="text-[var(--vf-danger)] hover:underline"
                    >
                      {t("adminDocs.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && (
        <DocFormModal
          initial={EMPTY_FORM}
          saving={saving}
          onClose={() => setCreating(false)}
          onSave={handleSave}
        />
      )}
      {editing && (
        <DocFormModal
          initial={{
            type: editing.type,
            category: editing.category,
            title: editing.title,
            description: editing.description,
            url: editing.url,
            content: editing.content,
            thumbnail_url: editing.thumbnail_url,
            duration_label: editing.duration_label,
            tags: editing.tags,
            sort_order: editing.sort_order,
            is_published: editing.is_published,
          }}
          saving={saving}
          onClose={() => setEditing(null)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
