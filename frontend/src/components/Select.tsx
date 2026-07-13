import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface SelectOptionProps {
  value: string | number;
  disabled?: boolean;
  children: ReactNode;
}

/** Marker component: never rendered directly, only introspected by <Select>. */
export function SelectOption(_props: SelectOptionProps) {
  return null;
}

interface OptionMeta {
  value: string;
  label: ReactNode;
  disabled: boolean;
}

function collectOptions(children: ReactNode): OptionMeta[] {
  const out: OptionMeta[] = [];
  const walk = (node: ReactNode) => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (!node || typeof node !== "object") return;
    const el = node as { type: unknown; props?: { value?: string | number; children?: ReactNode; disabled?: boolean } };
    if (el.type === SelectOption && el.props) {
      out.push({
        value: String(el.props.value),
        label: el.props.children,
        disabled: !!el.props.disabled,
      });
      return;
    }
    if (el.props?.children) walk(el.props.children);
  };
  walk(children);
  return out;
}

interface SelectProps {
  value: string | number;
  onChange: (value: string) => void;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  disabled?: boolean;
  id?: string;
}

export function Select({ value, onChange, children, className = "", style, disabled, id }: SelectProps) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<{ top: number; bottom: number; left: number; width: number; openUp: boolean } | null>(null);
  const [highlighted, setHighlighted] = useState(0);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  const options = collectOptions(children);
  const current = options.find((o) => o.value === String(value));

  useEffect(() => {
    if (!open) return;
    const idx = options.findIndex((o) => o.value === String(value));
    setHighlighted(idx >= 0 ? idx : 0);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (popupRef.current?.contains(target)) return;
      setOpen(false);
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setHighlighted((h) => {
          const dir = e.key === "ArrowDown" ? 1 : -1;
          let next = h;
          for (let i = 0; i < options.length; i++) {
            next = (next + dir + options.length) % options.length;
            if (!options[next]?.disabled) break;
          }
          return next;
        });
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const opt = options[highlighted];
        if (opt && !opt.disabled) {
          onChange(opt.value);
          setOpen(false);
        }
      }
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, options, highlighted, onChange]);

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect();
      const spaceBelow = window.innerHeight - r.bottom;
      const openUp = spaceBelow < 260 && r.top > spaceBelow;
      setRect({ top: r.top, bottom: r.bottom, left: r.left, width: r.width, openUp });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={`flex cursor-pointer items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
        style={style}
      >
        <span className="min-w-0 flex-1 truncate">{current ? current.label : ""}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="flex-shrink-0 opacity-50 transition-transform"
          style={{ transform: open ? "rotate(180deg)" : undefined }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={popupRef}
            className="fixed z-[9500] max-h-[280px] overflow-y-auto rounded-xl py-1"
            style={{
              top: rect.openUp ? undefined : rect.bottom + 4,
              bottom: rect.openUp ? window.innerHeight - rect.top + 4 : undefined,
              left: rect.left,
              minWidth: Math.max(rect.width, 140),
              width: rect.width,
              background: "var(--vf-p)",
              border: "1px solid rgba(var(--vf-fg-rgb),.08)",
              boxShadow: "0 12px 36px rgba(0,0,0,.6)",
            }}
          >
            {options.map((o, i) => (
              <button
                key={o.value}
                type="button"
                disabled={o.disabled}
                onMouseEnter={() => setHighlighted(i)}
                onClick={() => {
                  if (o.disabled) return;
                  onChange(o.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between gap-2 px-3.5 py-2 text-left text-[13px] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                  o.value === String(value)
                    ? "bg-[rgba(124,106,255,.14)] text-[var(--vf-c1)]"
                    : i === highlighted
                      ? "bg-[rgba(var(--vf-fg-rgb),0.06)] text-[var(--vf-text)]"
                      : "text-[var(--vf-text)]"
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {o.value === String(value) && (
                  <svg
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="flex-shrink-0"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
