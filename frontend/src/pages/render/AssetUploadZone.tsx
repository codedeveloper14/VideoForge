// Dropzone con validacion real de tipo en el drag-and-drop -- el <input type=file>
// nativo solo filtra por `accept` en el dialogo del explorador, NO en un drop real
// (el navegador deja soltar cualquier archivo). Aca se valida la extension real de
// cada archivo soltado y se muestra un error claro si no corresponde a la zona.
import { useState, type DragEvent } from "react";

interface AssetUploadZoneProps {
  icon: string;
  label: React.ReactNode;
  hint: string;
  accept: string[];
  wrongTypeMessage: string;
  multiple?: boolean;
  uploading?: boolean;
  onFiles: (files: File[]) => void;
}

function extOf(file: File): string {
  const m = /\.([a-z0-9]+)$/i.exec(file.name);
  return m ? m[1].toLowerCase() : "";
}

export function AssetUploadZone({
  icon,
  label,
  hint,
  accept,
  wrongTypeMessage,
  multiple,
  uploading,
  onFiles,
}: AssetUploadZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const [typeError, setTypeError] = useState("");

  function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    const valid = files.filter((f) => accept.includes(extOf(f)));
    if (valid.length < files.length) {
      setTypeError(wrongTypeMessage);
      window.setTimeout(() => setTypeError(""), 4000);
    } else {
      setTypeError("");
    }
    if (valid.length) onFiles(multiple ? valid : [valid[0]]);
  }

  return (
    <div>
      <label
        onDragOver={(e: DragEvent) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e: DragEvent) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`relative block cursor-pointer rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors ${
          dragOver
            ? "border-[var(--vf-accent)] bg-[var(--vf-accent)]/[0.08]"
            : "border-[var(--vf-b2)] hover:border-[var(--vf-accent)] hover:bg-[var(--vf-accent)]/[0.04]"
        }`}
      >
        <input
          type="file"
          accept={accept.map((e) => `.${e}`).join(",")}
          multiple={multiple}
          onChange={(e) => {
            const files = e.target.files;
            if (files && files.length) handleFiles(files);
            e.target.value = "";
          }}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        />
        <div className="mb-1.5 text-[26px]">{uploading ? "⏳" : icon}</div>
        <div className="text-[13px] text-[var(--vf-muted)]">{label}</div>
        <div className="mt-1 font-mono text-[11px] text-[var(--vf-m2)]">{hint}</div>
      </label>
      {typeError && (
        <p className="mt-1.5 rounded-lg border border-[var(--vf-danger)]/40 bg-[var(--vf-danger)]/10 px-3 py-1.5 text-center text-xs font-semibold text-[var(--vf-danger)]">
          {typeError}
        </p>
      )}
    </div>
  );
}
