// Guión page's own hero illustration (distinct from the shared HeaderArt used
// on Voz/Imagen/Video) — ported verbatim from launcher.py's vf-guion-redesign _ART_SVG.
export function GuionHeaderArt() {
  return (
    <svg
      viewBox="0 0 165 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
      className="hidden h-[148px] w-[190px] flex-shrink-0 opacity-[.92] sm:block"
    >
      <defs>
        <linearGradient id="gsIllG" x1="30" y1="0" x2="130" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7c6aff" stopOpacity="0.8" />
          <stop offset="1" stopColor="#c026d3" stopOpacity="0.45" />
        </linearGradient>
      </defs>
      <ellipse cx="80" cy="70" rx="62" ry="56" fill="rgba(124,106,255,0.05)" />
      <rect x="30" y="8" width="102" height="126" rx="12" fill="rgba(13,16,34,0.97)" stroke="rgba(124,106,255,0.28)" strokeWidth="1" />
      <rect x="30" y="8" width="102" height="5" rx="12" fill="url(#gsIllG)" className="animate-pulse" />
      <rect x="44" y="26" width="74" height="5" rx="2.5" fill="rgba(124,106,255,0.55)" />
      <rect x="44" y="40" width="58" height="3.5" rx="1.75" fill="rgba(255,255,255,0.13)" />
      <rect x="44" y="51" width="68" height="3.5" rx="1.75" fill="rgba(255,255,255,0.09)" />
      <rect x="44" y="62" width="50" height="3.5" rx="1.75" fill="rgba(255,255,255,0.09)" />
      <rect x="44" y="73" width="62" height="3.5" rx="1.75" fill="rgba(255,255,255,0.07)" />
      <rect x="44" y="84" width="42" height="3.5" rx="1.75" fill="rgba(255,255,255,0.07)" />
      <rect x="44" y="95" width="55" height="3.5" rx="1.75" fill="rgba(255,255,255,0.05)" />
      <rect x="44" y="106" width="36" height="3.5" rx="1.75" fill="rgba(255,255,255,0.04)" />
      <circle cx="24" cy="18" r="16" fill="rgba(6,182,212,0.92)" className="animate-pulse" style={{ animationDuration: "3s" }} />
      <path d="M17 12h14a2.5 2.5 0 012.5 2.5v7a2.5 2.5 0 01-2.5 2.5h-5l-3 3.5V24h-6a2.5 2.5 0 01-2.5-2.5v-7A2.5 2.5 0 0117 12z" fill="white" />
      <circle cx="141" cy="28" r="16" fill="rgba(124,106,255,0.92)" className="animate-pulse" style={{ animationDuration: "2.4s" }} />
      <circle cx="141" cy="28" r="6.5" stroke="white" strokeWidth="2" fill="none" />
      <circle cx="141" cy="28" r="2.5" fill="white" />
      <circle cx="13" cy="70" r="3" fill="rgba(124,106,255,0.4)" />
      <circle cx="153" cy="92" r="2.5" fill="rgba(192,38,211,0.4)" />
      <circle cx="15" cy="108" r="2" fill="rgba(124,106,255,0.25)" />
      <circle cx="155" cy="116" r="2" fill="rgba(124,106,255,0.2)" />
    </svg>
  );
}
