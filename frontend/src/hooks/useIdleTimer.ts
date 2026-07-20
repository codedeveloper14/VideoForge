import { useEffect, useRef } from "react";

const IDLE_MS = 40 * 60 * 1000;
const WARN_MS = 35 * 60 * 1000;
const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "scroll", "touchstart", "click"] as const;

interface UseIdleTimerOptions {
  enabled: boolean;
  onWarn: () => void;
  onExpire: () => void;
}

// Cierra la sesion tras IDLE_MS de inactividad, avisando WARN_MS antes. Los
// listeners van en `document` (no en un componente puntual) para que cualquier
// tecleo -- incluido escribir en el guion de GuionPage -- burbujee y resetee el
// timer sin necesitar logica especial por pagina.
export function useIdleTimer({ enabled, onWarn, onExpire }: UseIdleTimerOptions) {
  const warnTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expireTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onWarnRef = useRef(onWarn);
  const onExpireRef = useRef(onExpire);
  onWarnRef.current = onWarn;
  onExpireRef.current = onExpire;

  useEffect(() => {
    if (!enabled) return;

    function reset() {
      if (warnTimer.current) clearTimeout(warnTimer.current);
      if (expireTimer.current) clearTimeout(expireTimer.current);
      warnTimer.current = setTimeout(() => onWarnRef.current(), WARN_MS);
      expireTimer.current = setTimeout(() => onExpireRef.current(), IDLE_MS);
    }

    reset();
    ACTIVITY_EVENTS.forEach((ev) => document.addEventListener(ev, reset, { passive: true }));

    return () => {
      ACTIVITY_EVENTS.forEach((ev) => document.removeEventListener(ev, reset));
      if (warnTimer.current) clearTimeout(warnTimer.current);
      if (expireTimer.current) clearTimeout(expireTimer.current);
    };
  }, [enabled]);
}
