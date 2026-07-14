import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { submitHelpRequest } from "../api/docs";
import { Select, SelectOption } from "../components/Select";

type TabId = "faq" | "bug" | "suggestion" | "contact";

const TABS: { id: TabId; labelKey: string }[] = [
  { id: "faq", labelKey: "help.tabFaq" },
  { id: "bug", labelKey: "help.tabBug" },
  { id: "suggestion", labelKey: "help.tabSuggestion" },
  { id: "contact", labelKey: "help.tabContact" },
];

const FAQ_ITEMS = [
  { qKey: "help.faqQ1", aKey: "help.faqA1" },
  { qKey: "help.faqQ2", aKey: "help.faqA2" },
  { qKey: "help.faqQ3", aKey: "help.faqA3" },
  { qKey: "help.faqQ4", aKey: "help.faqA4" },
];

const BUG_CATEGORIES = [
  { value: "crash", labelKey: "help.bugCrash" },
  { value: "ui", labelKey: "help.bugUi" },
  { value: "render", labelKey: "help.bugRender" },
  { value: "voice", labelKey: "help.bugVoice" },
  { value: "other", labelKey: "help.bugOther" },
];

function SuccessCheck() {
  return (
    <div className="flex h-13 w-13 items-center justify-center rounded-full border border-[var(--vf-c5)]/30 bg-gradient-to-br from-[var(--vf-c5)]/20 to-emerald-500/10">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--vf-c5)" strokeWidth="2.5">
        <polyline points="20,6 9,17 4,12" />
      </svg>
    </div>
  );
}

function SuccessState({
  title,
  message,
  onReset,
}: {
  title: string;
  message: string;
  onReset: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex max-w-[460px] flex-col items-center gap-3.5 px-5 py-14 text-center">
      <SuccessCheck />
      <h3 className="m-0 text-xl font-extrabold tracking-tight text-[var(--vf-text)]">
        {title}
      </h3>
      <p className="m-0 text-sm leading-relaxed text-[var(--vf-muted)]">{message}</p>
      <button
        onClick={onReset}
        className="mt-1 rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-6 py-2 text-xs text-[var(--vf-muted)] transition-colors hover:bg-[rgba(var(--vf-fg-rgb),0.1)] hover:text-[var(--vf-text)]"
      >
        {t("help.back")}
      </button>
    </div>
  );
}

function FaqAccordion() {
  const { t } = useTranslation();
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <div>
      {FAQ_ITEMS.map((item, idx) => {
        const isOpen = openIdx === idx;
        return (
          <div key={item.qKey} className="border-b border-[var(--vf-border)] first:border-t">
            <button
              type="button"
              onClick={() => setOpenIdx(isOpen ? null : idx)}
              className={`flex w-full items-center justify-between gap-4 py-4.5 text-left text-[14.5px] font-semibold transition-colors ${
                isOpen ? "text-[var(--vf-text)]" : "text-[rgba(var(--vf-fg-rgb),0.65)] hover:text-[var(--vf-text)]"
              }`}
            >
              {t(item.qKey)}
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className={`shrink-0 opacity-40 transition-transform duration-200 ${
                  isOpen ? "rotate-180 opacity-80" : ""
                }`}
              >
                <polyline points="6,9 12,15 18,9" />
              </svg>
            </button>
            <div
              className="overflow-hidden transition-[max-height] duration-300 ease-out"
              style={{ maxHeight: isOpen ? "400px" : "0px" }}
            >
              <p className="pb-5 pr-7 text-[13.5px] leading-relaxed text-[var(--vf-muted)]">
                {t(item.aKey)}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BugReportForm() {
  const { t } = useTranslation();
  const [category, setCategory] = useState("crash");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setError("");
    try {
      await submitHelpRequest({
        type: "bug",
        category,
        title,
        description,
      });
      setSent(true);
      setTitle("");
      setDescription("");
      setCategory("crash");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <SuccessState
        title={t("help.bugReportSentTitle")}
        message={t("help.bugReportSentMessage")}
        onReset={() => setSent(false)}
      />
    );
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-[580px]">
      <div className="mb-4.5">
        <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--vf-accent)]/70" />
          {t("help.category")}
        </label>
        <Select
          value={category}
          onChange={(v) => setCategory(v)}
          className="w-full rounded-[10px] border border-[rgba(var(--vf-fg-rgb),0.18)] bg-[rgba(var(--vf-fg-rgb),0.05)] px-4 py-3 text-sm text-[var(--vf-text)] outline-none transition-colors focus:border-[var(--vf-accent)]/50 focus:bg-[var(--vf-accent)]/5"
        >
          {BUG_CATEGORIES.map((c) => (
            <SelectOption key={c.value} value={c.value}>
              {t(c.labelKey)}
            </SelectOption>
          ))}
        </Select>
      </div>
      <div className="mb-4.5">
        <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--vf-accent)]/70" />
          {t("help.bugTitleLabel")}
        </label>
        <input
          type="text"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("help.bugTitlePlaceholder") || ""}
          className="w-full rounded-[10px] border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-4 py-3 text-sm text-[var(--vf-text)] outline-none transition-colors placeholder:text-[rgba(var(--vf-fg-rgb),0.2)] focus:border-[var(--vf-accent)]/50 focus:bg-[var(--vf-accent)]/5"
        />
      </div>
      <div className="mb-4.5">
        <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--vf-accent)]/70" />
          {t("help.description")}
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("help.bugDescriptionPlaceholder") || ""}
          rows={4}
          className="min-h-[112px] w-full resize-y rounded-[10px] border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-4 py-3 text-sm leading-relaxed text-[var(--vf-text)] outline-none transition-colors placeholder:text-[rgba(var(--vf-fg-rgb),0.2)] focus:border-[var(--vf-accent)]/50 focus:bg-[var(--vf-accent)]/5"
        />
      </div>
      {error && <p className="mb-3 text-sm text-[var(--vf-danger)]">{error}</p>}
      <button
        type="submit"
        disabled={sending}
        className="mt-2 w-full rounded-xl bg-gradient-to-br from-[var(--vf-c1)] to-[var(--vf-c2)] py-3.5 text-xs font-bold uppercase tracking-wider text-white shadow-[0_4px_20px_rgba(108,86,255,.35)] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-45"
      >
        {sending ? t("help.sending") : t("help.sendReport")}
      </button>
    </form>
  );
}

function SuggestionForm() {
  const { t } = useTranslation();
  const [suggestion, setSuggestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setError("");
    try {
      const trimmed = suggestion.trim();
      await submitHelpRequest({
        type: "suggestion",
        title: trimmed.slice(0, 50) || t("help.suggestionFallbackTitle"),
        description: suggestion,
      });
      setSent(true);
      setSuggestion("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <SuccessState
        title={t("help.suggestionSentTitle")}
        message={t("help.suggestionSentMessage")}
        onReset={() => setSent(false)}
      />
    );
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-[580px]">
      <div className="mb-4.5">
        <label className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--vf-muted)]">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--vf-accent)]/70" />
          {t("help.yourSuggestion")}
        </label>
        <textarea
          required
          value={suggestion}
          onChange={(e) => setSuggestion(e.target.value)}
          placeholder={t("help.suggestionPlaceholder") || ""}
          rows={4}
          className="min-h-[112px] w-full resize-y rounded-[10px] border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-4 py-3 text-sm leading-relaxed text-[var(--vf-text)] outline-none transition-colors placeholder:text-[rgba(var(--vf-fg-rgb),0.2)] focus:border-[var(--vf-accent)]/50 focus:bg-[var(--vf-accent)]/5"
        />
      </div>
      {error && <p className="mb-3 text-sm text-[var(--vf-danger)]">{error}</p>}
      <button
        type="submit"
        disabled={sending}
        className="mt-2 w-full rounded-xl bg-gradient-to-br from-[var(--vf-c1)] to-[var(--vf-c2)] py-3.5 text-xs font-bold uppercase tracking-wider text-white shadow-[0_4px_20px_rgba(108,86,255,.35)] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-45"
      >
        {sending ? t("help.sending") : t("help.sendSuggestion")}
      </button>
    </form>
  );
}

function ContactTab() {
  const { t } = useTranslation();
  return (
    <div>
      <p className="mb-4 text-sm text-[var(--vf-muted)]">
        {t("help.contactIntro")}
      </p>
      <a
        href="mailto:soporte@videoforge.ai"
        className="text-sm font-medium text-[var(--vf-c2)] hover:underline"
      >
        soporte@videoforge.ai
      </a>
    </div>
  );
}

export default function HelpPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabId>("faq");

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-1 text-[34px] font-bold tracking-tight bg-gradient-to-r from-[var(--vf-text)] to-[var(--vf-c2)] bg-clip-text text-transparent">
        {t("help.title")}
      </h1>
      <p className="mb-8 text-[11.5px] text-[var(--vf-muted)]">
        {t("help.subtitle")}
      </p>

      <div className="mb-9 flex w-fit gap-1 rounded-[14px] border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.03)] p-1">
        {TABS.map((tabItem) => (
          <button
            key={tabItem.id}
            onClick={() => setTab(tabItem.id)}
            className={`whitespace-nowrap rounded-[10px] px-5 py-2 text-xs font-semibold transition-colors ${
              tab === tabItem.id
                ? "bg-[rgba(var(--vf-fg-rgb),0.1)] text-[var(--vf-text)] shadow-[0_1px_4px_rgba(0,0,0,.15)]"
                : "text-[rgba(var(--vf-fg-rgb),0.55)] hover:text-[rgba(var(--vf-fg-rgb),0.85)]"
            }`}
          >
            {t(tabItem.labelKey)}
          </button>
        ))}
      </div>

      {tab === "faq" && <FaqAccordion />}
      {tab === "bug" && <BugReportForm />}
      {tab === "suggestion" && <SuggestionForm />}
      {tab === "contact" && <ContactTab />}
    </div>
  );
}
