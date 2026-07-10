import type { InputHTMLAttributes, ReactNode } from "react";

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: ReactNode;
}

export default function FormField({ label, ...inputProps }: FormFieldProps) {
  return (
    <label className="flex flex-col gap-1.5 text-sm text-[var(--vf-muted)]">
      {label}
      <input
        {...inputProps}
        className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-[var(--vf-text)] outline-none focus:border-[var(--vf-accent)]"
      />
    </label>
  );
}
