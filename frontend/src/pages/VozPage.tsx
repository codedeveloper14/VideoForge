import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import WaveSurfer from "wavesurfer.js";
import { listProjects } from "../api/projects";
import { audioFileUrl, loadAudio, loadScript } from "../api/script";
import type { LoadAudioResult } from "../api/script";
import { cloneVoice, generateVoice, listVoices, mergeAudio } from "../api/voice";
import { Select, SelectOption } from "../components/Select";
import type { MergeAudioResult, Voice, VoiceFragment } from "../api/voice";
import type { Project } from "../types";

function WaveformPlayer({ src }: { src?: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !src) return;
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "#5a5a75",
      progressColor: "#7c6aff",
      height: 48,
      cursorWidth: 1,
      barWidth: 2,
      barGap: 1,
      url: src,
    });
    wsRef.current = ws;
    ws.on("finish", () => setPlaying(false));
    return () => {
      ws.destroy();
      wsRef.current = null;
    };
  }, [src]);

  function toggle() {
    if (!wsRef.current) return;
    wsRef.current.playPause();
    setPlaying(wsRef.current.isPlaying());
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={toggle}
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--vf-accent)] text-white"
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}

type Tab = "estudio" | "clonar";

export default function VozPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState(searchParams.get("project") || "");

  const [tab, setTab] = useState<Tab>("estudio");

  // Estudio state
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voicesLoading, setVoicesLoading] = useState(true);
  const [voiceId, setVoiceId] = useState("");
  const [text, setText] = useState("");
  const [useProjectScript, setUseProjectScript] = useState(false);
  const [fragments, setFragments] = useState<VoiceFragment[] | null>(null);
  const [master, setMaster] = useState<MergeAudioResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [merging, setMerging] = useState(false);
  const [error, setError] = useState("");

  // Existing audio for project
  const [existingAudio, setExistingAudio] = useState<LoadAudioResult | null>(null);

  // Clonar state
  const [cloneName, setCloneName] = useState("");
  const [cloneFile, setCloneFile] = useState<File | null>(null);
  const [cloneLang, setCloneLang] = useState("AUTO");
  const [cloneText, setCloneText] = useState("");
  const [cloning, setCloning] = useState(false);
  const [cloneMsg, setCloneMsg] = useState("");
  const [cloneError, setCloneError] = useState("");

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (project) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("project", project);
        return next;
      });
    }
  }, [project]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setVoicesLoading(true);
    listVoices()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setVoices(list);
        if (list.length > 0) {
          const first = list[0];
          setVoiceId(first["ID Voz"] || first.id || first.voice_id || "");
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setVoicesLoading(false));
  }, []);

  useEffect(() => {
    if (!project) {
      setExistingAudio(null);
      return;
    }
    loadAudio(project)
      .then(setExistingAudio)
      .catch(() => setExistingAudio(null));
  }, [project]);

  function handleToggleUseScript(checked: boolean) {
    setUseProjectScript(checked);
    if (checked && project) {
      loadScript(project)
        .then((data) => {
          if (data?.existe) setText(data.texto || "");
        })
        .catch((err: Error) => setError(err.message));
    }
  }

  async function handleGenerate() {
    if (!text.trim()) {
      setError(t("vozTool.writeOrLoadScript"));
      return;
    }
    setGenerating(true);
    setError("");
    setMaster(null);
    try {
      const data = await generateVoice({ projectName: project, voiceId, data: text });
      if (data.error) {
        setError(data.error);
      } else {
        setFragments(data.fragments || []);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleMerge() {
    if (!fragments || fragments.length === 0) return;
    setMerging(true);
    setError("");
    try {
      const data = await mergeAudio(project, { fragments });
      setMaster(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setMerging(false);
    }
  }

  function handleReset() {
    setFragments(null);
    setMaster(null);
    setText("");
    setUseProjectScript(false);
  }

  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function handleClone(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!cloneName.trim() || !cloneFile) {
      setCloneError(t("vozTool.cloneNameFileRequired"));
      return;
    }
    setCloning(true);
    setCloneError("");
    setCloneMsg("");
    try {
      const audio_base64 = await fileToBase64(cloneFile);
      const data = await cloneVoice({
        name: cloneName,
        audio_base64,
        mime_type: cloneFile.type || "audio/mpeg",
        lang: cloneLang,
        text: cloneText,
      });
      if (data.error) {
        setCloneError(data.error);
      } else {
        setCloneMsg(t("vozTool.voiceCloned"));
      }
    } catch (err) {
      setCloneError((err as Error).message);
    } finally {
      setCloning(false);
    }
  }

  return (
    <div>
      {/* Project selector topbar */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
          {t("tools.project")}
        </span>
        <Select
          value={project}
          onChange={(v) => setProject(v)}
          className="min-w-[200px] rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--vf-accent)]"
        >
          <SelectOption value="">{t("tools.noProjectSelected")}</SelectOption>
          {projects.map((p) => (
            <SelectOption key={p.nombre} value={p.nombre}>
              {p.nombre}
            </SelectOption>
          ))}
        </Select>
      </div>

      <div className="mb-9 max-w-2xl">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.03)] px-3 py-1 font-mono text-[9.5px] uppercase tracking-widest text-[var(--vf-muted)]">
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ background: "var(--vf-c5)", boxShadow: "0 0 6px var(--vf-c5)" }}
          />
          {t("vozTool.moduleLabel")}
        </div>
        <h1 className="mb-3 text-3xl font-bold tracking-tight sm:text-4xl">
          {t("vozTool.titlePart1")}{" "}
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(110deg, var(--vf-c2) 0%, var(--vf-c1) 40%, var(--vf-c3) 85%)",
            }}
          >
            {t("vozTool.titlePart2")}
          </span>
        </h1>
        <p className="font-mono text-[12.5px] leading-relaxed text-[var(--vf-muted)]">
          {t("vozTool.subtitle")}
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-2 border-b border-[var(--vf-border)] pb-3">
        <button
          type="button"
          onClick={() => setTab("estudio")}
          className={`rounded-lg px-4 py-1.5 font-mono text-[11px] font-semibold ${
            tab === "estudio"
              ? "bg-[var(--vf-accent)] text-white"
              : "border border-[var(--vf-border)] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
          }`}
        >
          {t("vozTool.tabStudio")}
        </button>
        <button
          type="button"
          onClick={() => setTab("clonar")}
          className={`rounded-lg px-4 py-1.5 font-mono text-[11px] font-semibold ${
            tab === "clonar"
              ? "bg-[var(--vf-accent)] text-white"
              : "border border-[var(--vf-border)] text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
          }`}
        >
          {t("vozTool.tabClone")}
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-[var(--vf-danger)]">{error}</p>}

      {tab === "estudio" && (
        <div className="max-w-2xl">
          {existingAudio?.existe && (
            <div className="mb-5 rounded-xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-4">
              <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                {t("vozTool.existingAudio")}
              </div>
              <ul className="space-y-2">
                {(existingAudio.archivos || []).map((f) => (
                  <li key={f}>
                    <div className="mb-1 truncate font-mono text-[11px] text-[var(--vf-muted)]">
                      {f}
                      {existingAudio.principal === f && (
                        <span className="ml-2 text-[var(--vf-success)]">{t("vozTool.principal")}</span>
                      )}
                    </div>
                    <WaveformPlayer src={audioFileUrl(project, f)} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!master && !fragments && (
            <div className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
              <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                {t("vozTool.configuration")}
              </div>

              <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                {t("vozTool.voice")}
              </label>
              <Select
                value={voiceId}
                onChange={(v) => setVoiceId(v)}
                disabled={voicesLoading}
                className="mb-3 w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
              >
                {voicesLoading && <SelectOption value="">{t("vozTool.loadingVoices")}</SelectOption>}
                {!voicesLoading && voices.length === 0 && <SelectOption value="">{t("vozTool.noVoicesAvailable")}</SelectOption>}
                {voices.map((v) => {
                  const id = v["ID Voz"] || v.id || v.voice_id;
                  const name = v["Nombre Voz"] || v.name || id;
                  return (
                    <SelectOption key={id} value={id || ""}>
                      {name}
                    </SelectOption>
                  );
                })}
              </Select>

              <div className="mb-1 flex items-center justify-between">
                <label className="font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("vozTool.script")}
                </label>
                <label className="flex cursor-pointer items-center gap-1.5 font-mono text-[9px] text-[var(--vf-muted)]">
                  <input
                    type="checkbox"
                    checked={useProjectScript}
                    onChange={(e) => handleToggleUseScript(e.target.checked)}
                    className="h-3 w-3 accent-[var(--vf-accent)]"
                  />
                  {t("vozTool.useProjectScript")}
                </label>
              </div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={t("vozTool.scriptPlaceholder") || ""}
                className="mb-3 min-h-[130px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 font-mono text-[12px] outline-none focus:border-[var(--vf-accent)]"
              />

              <button
                type="button"
                onClick={handleGenerate}
                disabled={generating}
                className="w-full rounded-lg bg-[var(--vf-accent)] py-2.5 text-sm font-semibold text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
              >
                {generating ? t("vozTool.processing") : t("vozTool.processSpeech")}
              </button>
            </div>
          )}

          {fragments && !master && (
            <div>
              <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
                <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("vozTool.generatedFragments")}
                </div>
                <div className="flex flex-col gap-3">
                  {fragments.map((frag, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] p-3"
                    >
                      <div className="mb-2 truncate font-mono text-[10px] text-[var(--vf-muted)]">
                        {frag.chunkText?.slice(0, 80) || t("vozTool.fragmentFallback", { n: i + 1 })}
                      </div>
                      {frag.audio || frag.url || frag.audioUrl ? (
                        <WaveformPlayer src={frag.audio || frag.url || frag.audioUrl} />
                      ) : (
                        <span className="font-mono text-[10px] text-[var(--vf-muted)]">
                          {t("vozTool.noPreviewAvailable")}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              <button
                type="button"
                onClick={handleMerge}
                disabled={merging}
                className="w-full rounded-lg py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: "linear-gradient(135deg, var(--vf-c5), var(--vf-c6))" }}
              >
                {merging ? t("vozTool.merging") : t("vozTool.mergeAll")}
              </button>
            </div>
          )}

          {master && (
            <div>
              <div className="mb-4 rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5">
                <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
                  {t("vozTool.masterTrack")}
                </div>
                {master.finalAudio ? (
                  <WaveformPlayer src={master.finalAudio} />
                ) : (
                  <pre className="whitespace-pre-wrap font-mono text-[11px] text-[var(--vf-muted)]">
                    {JSON.stringify(master, null, 2)}
                  </pre>
                )}
                {project && (
                  <p className="mt-3 font-mono text-[10px] text-[var(--vf-success)]">
                    {t("vozTool.savedInProject", { project })}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={handleReset}
                className="w-full rounded-lg border border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.04)] py-2.5 text-sm font-medium text-[var(--vf-muted)] hover:text-[var(--vf-text)]"
              >
                {t("vozTool.generateAnother")}
              </button>
            </div>
          )}
        </div>
      )}

      {tab === "clonar" && (
        <div className="max-w-2xl">
          {cloneMsg && <p className="mb-3 text-sm text-[var(--vf-success)]">{cloneMsg}</p>}
          {cloneError && <p className="mb-3 text-sm text-[var(--vf-danger)]">{cloneError}</p>}

          <form
            onSubmit={handleClone}
            className="rounded-2xl border border-[var(--vf-border)] bg-[var(--vf-surface)] p-5"
          >
            <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("vozTool.cloneNewVoice")}
            </div>

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("vozTool.name")}
            </label>
            <input
              type="text"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              placeholder={t("vozTool.cloneNamePlaceholder") || ""}
              className="mb-3 w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
            />

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("vozTool.audioSample")}
            </label>
            <div className="relative mb-3 rounded-lg border border-dashed border-[var(--vf-border)] bg-[rgba(var(--vf-fg-rgb),0.015)] p-5 text-center">
              <input
                type="file"
                accept="audio/*"
                onChange={(e) => setCloneFile(e.target.files?.[0] || null)}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              />
              <div className="mb-1 text-xl">🎵</div>
              <div className="font-mono text-[11px] text-[var(--vf-muted)]">
                <strong>{t("vozTool.clickOrDrag")}</strong> {t("vozTool.yourAudio")}
              </div>
              {cloneFile && (
                <div className="mt-1 font-mono text-[10px] text-[var(--vf-success)]">
                  {cloneFile.name}
                </div>
              )}
            </div>

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("vozTool.language")}
            </label>
            <Select
              value={cloneLang}
              onChange={(v) => setCloneLang(v)}
              className="mb-3 w-full rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--vf-accent)]"
            >
              <SelectOption value="AUTO">{t("vozTool.autoDetect")}</SelectOption>
              <SelectOption value="ES_ES">{t("vozTool.spanish")}</SelectOption>
              <SelectOption value="EN_US">{t("vozTool.english")}</SelectOption>
              <SelectOption value="PT_BR">{t("vozTool.portuguese")}</SelectOption>
              <SelectOption value="FR_FR">{t("vozTool.french")}</SelectOption>
              <SelectOption value="DE_DE">{t("vozTool.german")}</SelectOption>
            </Select>

            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[var(--vf-muted)]">
              {t("vozTool.transcription")}
            </label>
            <textarea
              value={cloneText}
              onChange={(e) => setCloneText(e.target.value)}
              placeholder={t("vozTool.transcriptionPlaceholder") || ""}
              className="mb-3 min-h-[100px] w-full resize-y rounded-lg border border-[var(--vf-border)] bg-[var(--vf-surface-2)] px-3 py-2 font-mono text-[12px] outline-none focus:border-[var(--vf-accent)]"
            />

            <button
              type="submit"
              disabled={cloning}
              className="w-full rounded-lg bg-[var(--vf-accent)] py-2.5 text-sm font-semibold text-white hover:bg-[var(--vf-accent-hover)] disabled:opacity-50"
            >
              {cloning ? t("vozTool.processing") : t("vozTool.cloneAndSave")}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
