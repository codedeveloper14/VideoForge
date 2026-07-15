// Decorative animated illustration reused across pipeline page headers
// (Guión, Imagen/Flow, Voz, Video) — ported from the legacy app's shared
// hero artwork. Render is the only pipeline page that omits it.
export function HeaderArt() {
  return (
    <svg
      viewBox="0 0 165 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="hidden h-[110px] w-[130px] flex-shrink-0 sm:block"
    >
      <defs>
        <linearGradient id="hdrArtG" x1="22" y1="0" x2="140" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7c6aff" stopOpacity="0.85" />
          <stop offset="1" stopColor="#c026d3" stopOpacity="0.5" />
        </linearGradient>
      </defs>
      <rect x="20" y="46" width="92" height="74" rx="10" fill="rgba(13,16,34,0.97)" stroke="rgba(124,106,255,0.22)" />
      <rect x="40" y="30" width="92" height="74" rx="10" fill="rgba(13,16,34,0.97)" stroke="rgba(124,106,255,0.28)" />
      <rect x="40" y="30" width="92" height="5" rx="10" fill="url(#hdrArtG)" className="animate-pulse" />
      <circle cx="58" cy="52" r="7" fill="rgba(124,106,255,0.5)" />
      <path d="M46 92l16-18 14 12 12-15 22 21v8a4 4 0 01-4 4H50a4 4 0 01-4-4z" fill="rgba(167,139,250,0.28)" />
      <circle cx="24" cy="20" r="16" fill="rgba(6,182,212,0.92)" className="animate-pulse" style={{ animationDuration: "3s" }} />
      <path
        d="M17 14h14a2.5 2.5 0 012.5 2.5v7a2.5 2.5 0 01-2.5 2.5h-5l-3 3.5V26h-6a2.5 2.5 0 01-2.5-2.5v-7A2.5 2.5 0 0117 14z"
        fill="white"
      />
      <circle cx="141" cy="30" r="16" fill="rgba(124,106,255,0.92)" className="animate-pulse" style={{ animationDuration: "2.4s" }} />
      <circle cx="141" cy="30" r="6.5" stroke="white" strokeWidth="2" fill="none" />
      <circle cx="141" cy="30" r="2.5" fill="white" />
      <circle cx="13" cy="72" r="3" fill="rgba(124,106,255,0.4)" />
      <circle cx="153" cy="96" r="2.5" fill="rgba(192,38,211,0.4)" />
    </svg>
  );
}
