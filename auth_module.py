"""
Studio IVR — Módulo de Autenticación  v3.0
==========================================
Cambios en esta versión:
  [OK]  SESSION_MINUTES = 40   — sesión deslizante (se renueva con cada request)
  [OK]  _SERVER_BOOT           — invalida TODAS las sesiones al reiniciar el servidor
  [OK]  Botón "Cerrar sesión"  — inyectado automáticamente en la barra lateral
  [OK]  Toast de advertencia   — aparece 5 min antes de expirar por inactividad
  [OK]  Sistema de planes: Starter / Pro / Ultra
  [OK]  Límites diarios: videos, caracteres TTS, duración máxima de video
  [OK]  UI de Configuración y Upgrade en la barra lateral
  [OK]  Popup de límite alcanzado con opción de upgrade

Dependencias:
    pip install pymysql bcrypt flask

Integración en launcher.py:
    from auth_module import init_auth, check_limit, check_video_duration, record_usage
    init_auth(app)
"""

import os
import time
import hashlib
import hmac
import json
import threading
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────
# PLANES — límites diarios por plan
#   tts_chars_per_day: ~900 chars/min   (30-->27k | 60-->54k | 150-->135k)
#   max_video_minutes: None = ilimitado
# ─────────────────────────────────────────────────────────────────
PLANS = {
    "free": {
        "name": "Free",          "emoji": "🆓",
        "videos_per_month":  3,  "shorts_per_month":  0,
        "audio_hours_per_month": 0,
        "tts_chars_per_month":  18_000,    # 20min × 900chars/min
        "tts_chars_per_day":    3_000,
        "max_video_minutes": None, "price_usd": 0,
        "color": "#64748b",      "highlight": False,
    },
    "basico": {
        "name": "Básico",        "emoji": "🌱",
        "videos_per_month": 45,  "shorts_per_month": 15,
        "audio_hours_per_month": 30,
        "tts_chars_per_month":  1_620_000,  # 30h × 60 × 900
        "tts_chars_per_day":    54_000,
        "max_video_minutes": None, "price_usd": 75,
        "color": "#22d3a0",      "highlight": False,
    },
    "pro": {
        "name": "Pro",           "emoji": "⚡",
        "videos_per_month": 60,  "shorts_per_month": 25,
        "audio_hours_per_month": 45,
        "tts_chars_per_month":  2_430_000,  # 45h × 60 × 900
        "tts_chars_per_day":    81_000,
        "max_video_minutes": None, "price_usd": 105,
        "color": "#7c6aff",      "highlight": True,
    },
    "ultra": {
        "name": "Ultra",         "emoji": "🔥",
        "videos_per_month": 75,  "shorts_per_month": 35,
        "audio_hours_per_month": 60,
        "tts_chars_per_month":  3_240_000,  # 60h × 60 × 900
        "tts_chars_per_day":    108_000,
        "max_video_minutes": None, "price_usd": 145,
        "color": "#fbbf24",      "highlight": False,
    },
    "unlimited": {
        "name": "Ilimitado",     "emoji": "♾️",
        "videos_per_month": None, "shorts_per_month": None,
        "audio_hours_per_month": None,
        "tts_chars_per_month":  None,
        "tts_chars_per_day":    None,
        "max_video_minutes": None, "price_usd": 350,
        "color": "#c084fc",      "highlight": False,
    },
}

# Alias de nombres de plan alternativos en la BD --> clave canónica
PLAN_ALIASES = {
    "starter":     "basico",
    "basic":       "basico",
    "basico":      "basico",
    "free":        "free",
    "standard":    "pro",
    "premium":     "pro",
    "advanced":    "pro",
    "enterprise": "unlimited",
    "business":   "ultra",
    "ilimitado":  "unlimited",
    "unlimited":  "unlimited",
}

def normalize_plan_key(raw: str) -> str:
    """Convierte cualquier nombre de plan de la BD al key canónico (basico/pro/ultra/unlimited)."""
    key = str(raw or "basico").lower().strip()
    key = PLAN_ALIASES.get(key, key)          # resolver alias
    return key if key in PLANS else "basico"  # validar contra PLANS

# Cargar Stripe Key desde variables de entorno
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

# Precios en centavos por plan (para crear Checkout Sessions)
STRIPE_PRICES = {
    "basico":    {"amount": 7500,  "name": "Studio IVR Básico",    "product_id": None},
    "pro":       {"amount": 10500, "name": "Studio IVR Pro",       "product_id": None},
    "ultra":     {"amount": 14500, "name": "Studio IVR Ultra",     "product_id": None},
    "unlimited": {"amount": 35000, "name": "Studio IVR Ilimitado", "product_id": None},
}

# Payment Links de respaldo (se usan si falla la creación de sesión)
STRIPE_PAYMENT_LINKS = {
    "basico":    "https://buy.stripe.com/6oU3cx2S10sr24c4v93cc0b",
    "pro":       "https://buy.stripe.com/9B614p78h0sr7ow1iX3cc0c",
    "ultra":     "https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d",
    "unlimited": "https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e",
}

STRIPE_URLS = {
    ("basico", "pro"):       "https://buy.stripe.com/9B614p78h0sr7ow1iX3cc0c",
    ("basico", "ultra"):     "https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d",
    ("basico", "unlimited"): "https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e",
    ("pro",    "ultra"):     "https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d",
    ("pro",    "unlimited"): "https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e",
    ("ultra",  "unlimited"): "https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e",
}

def _chars_to_min(chars: int) -> str:
    """Convierte caracteres a string legible de minutos."""
    m = chars / 900
    if m < 1:
        return f"{int(m*60)}s"
    return f"{m:.0f} min"

# ─────────────────────────────────────────────────────────────────
# CONFIGURACIÓN  ← Cargada de forma segura
# ─────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":            os.getenv("DB_HOST"),
    "user":            os.getenv("DB_USER"),
    "password":        os.getenv("DB_PASSWORD"),
    "database":        os.getenv("DB_NAME"),
    "port":            3306,
    "connect_timeout": 10,
    "charset":         "utf8mb4"
}

APP_SECRET_KEY      = os.getenv("APP_SECRET_KEY")
SESSION_MINUTES     = 40          # ← inactividad máxima (minutos)
PUBLIC_ROUTES       = {"/api/login", "/login", "/api/change-password", "/favicon.ico", "/api/logout", "/shell", "/api/register", "/stripe-success"}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS     = 300

def _chars_to_min(chars: int) -> str:
    """Convierte caracteres a string legible de minutos."""
    m = chars / 900
    if m < 1:
        return f"{int(m*60)}s"
    return f"{m:.0f} min"

# ─────────────────────────────────────────────────────────────────
# CONFIGURACIÓN  ← Editar aquí con tus datos de Hostinger
# ─────────────────────────────────────────────────────────────────

DB_CONFIG = {
    # Contabo VPS
    "host": "vmi3378735.contaboserver.net",
    "user":     "admin",
    "password": "Videoforge2026*",
    "database": "u330524705_VideoForge",
    "port":     3306,
    "connect_timeout": 10,
    "charset":  "utf8mb4",
}

APP_SECRET_KEY      = "Videoforgepassa34432fsdsdfs"
SESSION_MINUTES     = 40          # ← inactividad máxima (minutos)
PUBLIC_ROUTES       = {"/api/login", "/login", "/api/change-password", "/favicon.ico", "/api/logout", "/shell", "/api/register", "/stripe-success"}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS     = 300

# ─────────────────────────────────────────────────────────────────
# BOOT EPOCH  — invalida TODAS las sesiones previas al reiniciar
# ─────────────────────────────────────────────────────────────────
import tempfile as _tmplib, os as _oslib
_BOOT_FILE = _oslib.path.join(_tmplib.gettempdir(), "vf_server_boot.epoch")
try:
    with open(_BOOT_FILE, "r") as _bf:
        _stored = _bf.read().strip().split(":")
        _epoch_val = int(_stored[0])
        _epoch_ts  = float(_stored[1]) if len(_stored) > 1 else 0
        # Reutilizar boot epoch si el servidor se reinició dentro de la ventana de sesión
        if time.time() - _epoch_ts < SESSION_MINUTES * 60:
            _SERVER_BOOT = _epoch_val
        else:
            raise ValueError("epoch expirado")
except Exception:
    _SERVER_BOOT = int(time.time())
    try:
        with open(_BOOT_FILE, "w") as _bf:
            _bf.write(f"{_SERVER_BOOT}:{time.time()}")
    except Exception:
        pass
print(f"[AUTH] 🔑 SERVER_BOOT={_SERVER_BOOT}  (sesiones preservadas en reinicios cortos).")


# ─────────────────────────────────────────────────────────────────
# HTML DE LOGIN — diseño premium Studio IVR
# ─────────────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Studio IVR — Acceso</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--c1:#7c6aff;--c2:#a78bfa;--c5:#22d3a0;--bg:#08080f;--t:#ebebf5;--mono:'JetBrains Mono',monospace}
html,body{height:100%}
body{background:var(--bg);color:var(--t);font-family:'Syne',sans-serif;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(ellipse 55% 55% at 15% 15%, rgba(99,80,255,.18) 0%, transparent 55%),
    radial-gradient(ellipse 45% 45% at 85% 80%, rgba(124,106,255,.12) 0%, transparent 50%),
    radial-gradient(ellipse 35% 35% at 75% 8%,  rgba(167,139,250,.08) 0%, transparent 45%),
    radial-gradient(ellipse 30% 30% at 5%  90%, rgba(80,60,200,.07)  0%, transparent 45%)}
body::after{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity:.025}
.wrap{display:flex;width:min(1080px,96vw);height:min(660px,88vh);border-radius:18px;overflow:hidden;border:1px solid rgba(255,255,255,.09);box-shadow:0 40px 120px rgba(0,0,0,.8),0 0 80px rgba(99,80,255,.08);animation:up .45s cubic-bezier(.16,1,.3,1) both;position:relative;z-index:1}
.wrap::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent 0%,rgba(255,255,255,.08) 25%,rgba(124,106,255,.35) 50%,rgba(255,255,255,.08) 75%,transparent 100%);z-index:10;pointer-events:none}
@keyframes up{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
.lp{flex:1;background:rgba(12,12,24,.82);backdrop-filter:blur(0px);display:flex;flex-direction:column;padding:40px 48px;position:relative;overflow:hidden}
.lp-bg{position:absolute;inset:0;background:radial-gradient(ellipse 90% 70% at -10% -10%,rgba(124,106,255,.13) 0%,transparent 55%),radial-gradient(ellipse 60% 40% at 110% 110%,rgba(99,80,255,.07) 0%,transparent 50%);pointer-events:none}
.rp{width:400px;flex-shrink:0;background:rgba(14,14,28,.90);border-left:1px solid rgba(255,255,255,.06);display:flex;align-items:center;justify-content:center;padding:44px 44px}
.logo{display:flex;align-items:center;gap:12px;position:relative;z-index:1}
.logo-icon{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#6f5eff 0%,#9b68ff 100%);display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 0 22px rgba(124,106,255,.38)}
.logo-icon svg{width:18px;height:18px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.logo-text{display:flex;flex-direction:column;gap:2px}
.logo-name{font-size:15px;font-weight:800;letter-spacing:-.3px}
.logo-sub{font-family:var(--mono);font-size:7.5px;color:rgba(167,139,250,.5);letter-spacing:.2em;text-transform:uppercase}
.hero{flex:1;display:flex;flex-direction:column;justify-content:center;position:relative;z-index:1}
.hero h1{font-size:clamp(32px,3.5vw,50px);font-weight:800;letter-spacing:-1.8px;line-height:1.06;color:#eeeef8;margin-bottom:16px}
.hero h1 span{color:var(--c1)}
.hero p{font-size:13px;color:rgba(255,255,255,.38);line-height:1.7;max-width:360px;font-family:var(--mono)}
.features{display:flex;flex-direction:column;gap:16px;position:relative;z-index:1}
.feat{display:flex;align-items:flex-start;gap:14px}
.feat-icon{width:36px;height:36px;border-radius:9px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.feat-icon svg{width:16px;height:16px;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.feat-body{}
.feat-title{font-size:13px;font-weight:700;color:rgba(255,255,255,.8);margin-bottom:2px}
.feat-desc{font-size:11.5px;color:rgba(255,255,255,.3);font-family:var(--mono);line-height:1.4}
.lp-foot{font-family:var(--mono);font-size:8.5px;color:rgba(255,255,255,.18);position:relative;z-index:1}
.fw{width:100%;max-width:320px}
.fw-title{font-size:20px;font-weight:800;letter-spacing:-.4px;margin-bottom:5px;white-space:nowrap}
.fw-sub{font-size:12.5px;color:rgba(255,255,255,.38);margin-bottom:24px;line-height:1.55}
.msg{display:none;padding:9px 12px;border-radius:9px;font-family:var(--mono);font-size:10.5px;margin-bottom:12px;line-height:1.5}
.msg.err{background:rgba(255,60,80,.06);border:1px solid rgba(255,60,80,.15);color:#ff6677}
.msg.warn{background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.15);color:#fbbf24}
.msg.show{display:block}
.field{margin-bottom:12px}
.field-label{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.field-label span{font-size:12px;font-weight:600;color:rgba(255,255,255,.62)}
.field-label a{font-size:11px;color:rgba(124,106,255,.6);text-decoration:none;font-family:var(--mono);transition:color .15s}
.field-label a:hover{color:var(--c2)}
.inp-wrap{position:relative}
.inp-ico{position:absolute;left:13px;top:50%;transform:translateY(-50%);width:14px;height:14px;color:rgba(255,255,255,.22);pointer-events:none}
.fin{width:100%;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:12px 40px 12px 38px;color:var(--t);font-family:'Syne',sans-serif;font-size:13.5px;font-weight:500;outline:none;transition:border-color .2s,background .2s,box-shadow .2s}
.fin:focus{border-color:rgba(124,106,255,.5);background:rgba(124,106,255,.05);box-shadow:0 0 0 3px rgba(124,106,255,.1)}
.fin::placeholder{color:rgba(255,255,255,.15);font-weight:400}
.pw-btn{position:absolute;right:11px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:rgba(255,255,255,.25);padding:4px;line-height:1;font-size:13px;transition:color .15s}
.pw-btn:hover{color:rgba(255,255,255,.6)}
.check-row{display:flex;align-items:center;justify-content:space-between;margin:12px 0 18px}
.remember{display:flex;align-items:center;gap:8px;font-size:12px;color:rgba(255,255,255,.45);cursor:pointer;user-select:none}
.remember input[type=checkbox]{display:none}
.chk{width:15px;height:15px;border-radius:4px;border:1.5px solid rgba(255,255,255,.18);background:rgba(255,255,255,.03);display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
.chk::after{content:'';width:8px;height:5px;border-left:1.5px solid #fff;border-bottom:1.5px solid #fff;transform:rotate(-45deg) scale(0) translate(0,-1px);transition:transform .12s ease;display:block}
.remember input[type=checkbox]:checked + .chk{background:var(--c1);border-color:var(--c1)}
.remember input[type=checkbox]:checked + .chk::after{transform:rotate(-45deg) scale(1) translate(0,-1px)}
.btn{width:100%;padding:13.5px;border-radius:10px;border:none;cursor:pointer;background:linear-gradient(135deg,#6f5eff 0%,#9b68ff 100%);color:#fff;font-family:'Syne',sans-serif;font-size:14.5px;font-weight:700;letter-spacing:-.1px;transition:box-shadow .2s,transform .15s,opacity .15s;position:relative;overflow:hidden;margin-bottom:18px;box-shadow:0 4px 18px rgba(112,90,255,.3)}
.btn:hover{transform:translateY(-1.5px);box-shadow:0 8px 32px rgba(112,90,255,.5)}
.btn:active{transform:none;box-shadow:0 2px 8px rgba(112,90,255,.25)}
.btn:disabled{opacity:.35;cursor:not-allowed;transform:none;box-shadow:none}
.ldots{display:none;gap:5px;align-items:center;justify-content:center}
.ldots.show{display:flex}
.ld{width:4px;height:4px;border-radius:50%;background:#fff;animation:ld .85s ease-in-out infinite}
.ld:nth-child(2){animation-delay:.14s}
.ld:nth-child(3){animation-delay:.28s}
@keyframes ld{0%,80%,100%{transform:scale(.3);opacity:.3}40%{transform:scale(1);opacity:1}}
.divider{display:flex;align-items:center;gap:10px;margin-bottom:14px;color:rgba(255,255,255,.18);font-size:11px;font-family:var(--mono)}
.divider::before,.divider::after{content:'';flex:1;height:1px;background:rgba(255,255,255,.07)}
.soc-row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
.soc-btn{padding:11px 8px;border-radius:9px;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.03);color:rgba(255,255,255,.65);font-family:'Syne',sans-serif;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:7px;transition:background .15s,border-color .15s,color .15s,box-shadow .15s;white-space:nowrap}
.soc-btn:hover{background:rgba(255,255,255,.055);border-color:rgba(255,255,255,.16);color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.3)}
.reg-link{text-align:center;font-size:12px;color:rgba(255,255,255,.28);font-family:var(--mono)}
.reg-link a{color:var(--c2);text-decoration:none;font-weight:700;margin-left:4px;transition:color .15s}
.reg-link a:hover{color:var(--t)}
.mhint{font-family:var(--mono);font-size:9.5px;margin-top:5px;transition:color .2s;color:rgba(255,255,255,.22)}
.mhint.ok{color:var(--c5)}
.mhint.bad{color:#ff5566}
.reg-ov{display:none;position:fixed;inset:0;z-index:900;background:rgba(0,0,0,.86);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);align-items:center;justify-content:center;padding:20px}
.reg-ov.show{display:flex;animation:up .25s ease}
.reg-card{width:100%;max-width:640px;max-height:88vh;background:#0d0d1e;border:1px solid rgba(124,106,255,.15);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 40px 100px rgba(0,0,0,.9)}
.reg-head{display:flex;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid rgba(255,255,255,.05);flex-shrink:0}
.reg-htxt .rht{font-size:14px;font-weight:700}
.reg-htxt .rhs{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,.28);margin-top:2px}
.reg-close{width:26px;height:26px;border-radius:7px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:rgba(255,255,255,.4);cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;transition:background .15s,color .15s}
.reg-close:hover{background:rgba(255,60,80,.1);color:#ff6677}
.reg-card iframe{width:100%;flex:1;min-height:480px;border:none;background:#fff}
.overlay{display:none;position:fixed;inset:0;z-index:800;background:rgba(0,0,0,.8);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);align-items:center;justify-content:center;padding:20px}
.overlay.show{display:flex}
.modal{width:100%;max-width:370px;background:#0e0e1e;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:32px 28px;box-shadow:0 40px 100px rgba(0,0,0,.88);animation:up .3s cubic-bezier(.16,1,.3,1);position:relative}
.modal::before{content:'';position:absolute;top:0;left:20%;right:20%;height:1px;background:linear-gradient(90deg,transparent,rgba(251,191,36,.4),transparent)}
.modal-icon{width:50px;height:50px;border-radius:13px;background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.16);display:flex;align-items:center;justify-content:center;font-size:20px;margin:0 auto 16px}
.modal-title{font-size:18px;font-weight:800;letter-spacing:-.35px;text-align:center;margin-bottom:4px}
.modal-sub{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,.28);text-align:center;margin-bottom:18px;line-height:1.6}
.req{display:flex;flex-direction:column;gap:5px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);border-radius:9px;padding:10px 12px;margin-bottom:12px}
.req-item{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:9.5px;color:rgba(255,255,255,.26);transition:color .2s}
.req-item.ok{color:var(--c5)}
.ricon{font-size:10px;width:12px;text-align:center}
.btn-gold{width:100%;padding:12px;border-radius:9px;border:none;cursor:pointer;background:#fbbf24;color:#000;font-family:var(--mono);font-size:11.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;transition:opacity .15s,transform .15s;margin-top:4px}
.btn-gold:hover{opacity:.87;transform:translateY(-1px)}
.btn-gold:disabled{opacity:.35;cursor:not-allowed;transform:none}
</style>
</head>
<body>

<div class="wrap">
  <!-- LEFT PANEL -->
  <div class="lp">
    <div class="lp-bg"></div>

    <div class="logo">
      <div class="logo-icon">
        <svg viewBox="0 0 24 24"><rect x="2" y="4" width="4" height="16" rx="1" fill="rgba(255,255,255,.25)"/><rect x="2.5" y="6" width="3" height="2" rx=".5" fill="rgba(255,255,255,.65)"/><rect x="2.5" y="11" width="3" height="2" rx=".5" fill="rgba(255,255,255,.65)"/><rect x="2.5" y="16" width="3" height="2" rx=".5" fill="rgba(255,255,255,.65)"/><path d="M9 8.5L18.5 12 9 15.5V8.5Z" fill="white"/></svg>
      </div>
      <div class="logo-text">
        <span class="logo-name">Studio IVR</span>
        <span class="logo-sub">AI Pipeline</span>
      </div>
    </div>

    <div class="hero">
      <h1>Crea. Automatiza.<br><span>Produce.</span></h1>
      <p>La plataforma completa para producción audiovisual con IA. Guión, voz, video y renderizado en un solo flujo.</p>
    </div>

    <div class="features">
      <div class="feat">
        <div class="feat-icon" style="background:rgba(251,191,36,.12)">
          <svg viewBox="0 0 24 24" stroke="#fbbf24"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        </div>
        <div class="feat-body">
          <div class="feat-title">Pipeline inteligente</div>
          <div class="feat-desc">Automatiza cada etapa de tu producción.</div>
        </div>
      </div>
      <div class="feat">
        <div class="feat-icon" style="background:rgba(124,106,255,.12)">
          <svg viewBox="0 0 24 24" stroke="#a78bfa"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        </div>
        <div class="feat-body">
          <div class="feat-title">Colaboración en equipo</div>
          <div class="feat-desc">Trabaja junto a tu equipo en tiempo real.</div>
        </div>
      </div>
      <div class="feat">
        <div class="feat-icon" style="background:rgba(34,211,160,.1)">
          <svg viewBox="0 0 24 24" stroke="#22d3a0"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        </div>
        <div class="feat-body">
          <div class="feat-title">Seguro y confiable</div>
          <div class="feat-desc">Tus proyectos están siempre protegidos.</div>
        </div>
      </div>
    </div>

    <div class="lp-foot" style="margin-top:24px">© 2026 Studio IVR. Todos los derechos reservados.</div>
  </div>

  <!-- RIGHT PANEL -->
  <div class="rp">
    <div class="fw">
      <div class="fw-title">Bienvenido de nuevo</div>
      <div class="fw-sub">Inicia sesión para continuar con tus proyectos.</div>

      <div class="msg err" id="errMsg"></div>
      <div class="msg warn" id="warnMsg"></div>

      <div class="field">
        <div class="field-label"><span>Correo electrónico o usuario</span></div>
        <div class="inp-wrap">
          <svg class="inp-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          <input class="fin" type="text" id="uInput" placeholder="tu_usuario" autocomplete="username" autocapitalize="off" spellcheck="false">
        </div>
      </div>

      <div class="field">
        <div class="field-label">
          <span>Contraseña</span>
          <a href="#" tabindex="-1" style="pointer-events:none;opacity:.38">¿Olvidaste tu contraseña?</a>
        </div>
        <div class="inp-wrap">
          <svg class="inp-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <input class="fin" type="password" id="pInput" placeholder="••••••••" autocomplete="current-password">
          <button class="pw-btn" onclick="togglePw('pInput',this)" type="button">👁</button>
        </div>
      </div>

      <div class="check-row">
        <label class="remember"><input type="checkbox" id="rememberMe"><span class="chk"></span> Recordarme</label>
      </div>

      <button class="btn" id="loginBtn" onclick="doLogin()">
        <span id="btnTxt">Iniciar sesión --></span>
        <span class="ldots" id="ldots"><span class="ld"></span><span class="ld"></span><span class="ld"></span></span>
      </button>

      <div class="divider"><span>O continúa con</span></div>

      <div class="soc-row">
        <button class="soc-btn" onclick="alert('Próximamente.')">
          <svg width="14" height="14" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
          Continuar con Google
        </button>
        <button class="soc-btn" onclick="alert('Próximamente.')">
          <svg width="12" height="14" viewBox="0 0 814 1000" fill="currentColor"><path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105-36.8-162.8-106.3C180.9 742.2 139 649 139 603c0-188.1 130.9-314.3 260.2-314.3 73.9 0 135.4 48.4 179.9 48.4 42.6 0 113.5-50.7 196.7-50.7z"/><path d="M555.5 0c-58.1 0-115.8 38.4-153.1 97.8-33.1 53.2-60.3 131.2-60.3 209.5 0 4.7.5 9.4.5 14.1 3.7.2 7.5.3 11.2.3 55.1 0 113.9-37.1 149.7-95.7 37.7-62.4 62.3-140.6 62.3-218.8 0-2.6-.1-5.2-.2-7.8z"/></svg>
          Continuar con Apple
        </button>
      </div>

      <div class="reg-link">¿No tienes cuenta?<a href="#" onclick="openReg();return false;">Registrarse</a></div>
    </div>
  </div>
</div>

<!-- REGISTRATION MODAL -->
<div class="reg-ov" id="regOv" onclick="if(event.target===this)closeReg()">
  <div class="reg-card">
    <div class="reg-head">
      <div class="reg-htxt"><div class="rht">Crear cuenta</div><div class="rhs">Completa el formulario para acceder a Studio IVR</div></div>
      <button class="reg-close" onclick="closeReg()">✕</button>
    </div>
    <iframe id="regFr" src="" allow="fullscreen" loading="lazy"></iframe>
  </div>
</div>

<!-- CHANGE PASSWORD MODAL -->
<div class="overlay" id="cpOverlay">
  <div class="modal">
    <div class="modal-icon">🔐</div>
    <div class="modal-title">Cambia tu contraseña</div>
    <p class="modal-sub">Es tu primer acceso. Por seguridad<br>debes establecer una nueva contraseña.</p>
    <div class="msg err" id="cpErr"></div>
    <div class="msg ok" id="cpOk"></div>
    <div class="req">
      <div class="req-item" id="req-len"><span class="ricon">○</span> Mínimo 8 caracteres</div>
      <div class="req-item" id="req-num"><span class="ricon">○</span> Al menos un número</div>
      <div class="req-item" id="req-up"><span class="ricon">○</span> Al menos una mayúscula</div>
    </div>
    <div class="field">
      <div class="field-label"><span>Nueva contraseña</span></div>
      <div class="inp-wrap"><input class="fin" type="password" id="np1" placeholder="Nueva contraseña" oninput="checkReqs()" autocomplete="new-password" style="padding-left:14px"><button class="pw-btn" onclick="togglePw('np1',this)" type="button">👁</button></div>
    </div>
    <div class="field">
      <div class="field-label"><span>Confirmar contraseña</span></div>
      <div class="inp-wrap"><input class="fin" type="password" id="np2" placeholder="Repite la contraseña" oninput="checkMatch()" autocomplete="new-password" style="padding-left:14px"><button class="pw-btn" onclick="togglePw('np2',this)" type="button">👁</button></div>
      <div class="mhint" id="mhint"></div>
    </div>
    <button class="btn-gold" id="cpBtn" onclick="doChange()" disabled>
      <span id="cpTxt">Guardar contraseña --></span>
      <span class="ldots" id="cpLd"><span class="ld"></span><span class="ld"></span><span class="ld"></span></span>
    </button>
  </div>
</div>

<script>
var _pu=null;
function togglePw(id,b){var i=document.getElementById(id);i.type=i.type==='password'?'text':'password';b.textContent=i.type==='password'?'👁':'🙈';}
function showMsg(id,t,tx){var e=document.getElementById(id);e.textContent=(t==='err'?'⚠ ':t==='warn'?'⏱ ':'✓ ')+tx;e.className='msg '+t+' show';}
function hideMsg(id){var e=document.getElementById(id);if(e)e.className='msg';}
function setLoad(b,l,t,on){document.getElementById(b).disabled=on;document.getElementById(l).className='ldots'+(on?' show':'');document.getElementById(t).style.display=on?'none':'';}
function openReg(){var fr=document.getElementById('regFr');if(!fr.src||fr.src==='about:blank'||fr.src===window.location.href)fr.src='https://n8n-n8n.y9c1cn.easypanel.host/form/cf9a827e-e8ac-499a-9fbc-39abd2334490';document.getElementById('regOv').classList.add('show');}
function closeReg(){document.getElementById('regOv').classList.remove('show');}
async function doLogin(){
  hideMsg('errMsg');hideMsg('warnMsg');
  var u=document.getElementById('uInput').value.trim(),p=document.getElementById('pInput').value;
  if(!u||!p){showMsg('errMsg','err','Completa usuario y contraseña.');return;}
  setLoad('loginBtn','ldots','btnTxt',true);
  try{
    var r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    var d=await r.json();
    if(d.ok&&d.must_change_password){_pu=u;document.getElementById('cpOverlay').classList.add('show');setLoad('loginBtn','ldots','btnTxt',false);}
    else if(d.ok){try{window.parent.postMessage({__vf:true,type:'session',loggedIn:true},'*');}catch(e){}document.body.style.transition='opacity .35s';document.body.style.opacity='0';setTimeout(function(){window.location.replace('/');},360);}
    else if(d.lockout){showMsg('warnMsg','warn',d.error);setLoad('loginBtn','ldots','btnTxt',false);}
    else{showMsg('errMsg','err',d.error||'Credenciales incorrectas.');setLoad('loginBtn','ldots','btnTxt',false);}
  }catch(e){showMsg('errMsg','err','Error de conexión.');setLoad('loginBtn','ldots','btnTxt',false);}
}
function setReq(id,ok){var e=document.getElementById(id);e.className='req-item'+(ok?' ok':'');e.querySelector('.ricon').textContent=ok?'✓':'○';}
function checkReqs(){var v=document.getElementById('np1').value;setReq('req-len',v.length>=8);setReq('req-num',/[0-9]/.test(v));setReq('req-up',/[A-Z]/.test(v));checkMatch();}
function checkMatch(){
  var v1=document.getElementById('np1').value,v2=document.getElementById('np2').value,h=document.getElementById('mhint');
  if(!v2){h.textContent='';h.className='mhint';return;}
  h.textContent=v1===v2?'✓ Coinciden':'✗ No coinciden';
  h.className='mhint '+(v1===v2?'ok':'bad');
  document.getElementById('cpBtn').disabled=!(v1.length>=8&&/[0-9]/.test(v1)&&/[A-Z]/.test(v1)&&v1===v2);
}
async function doChange(){
  hideMsg('cpErr');hideMsg('cpOk');
  var np=document.getElementById('np1').value,nc=document.getElementById('np2').value;
  if(np!==nc){showMsg('cpErr','err','Las contraseñas no coinciden.');return;}
  setLoad('cpBtn','cpLd','cpTxt',true);
  try{
    var r=await fetch('/api/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:_pu,new_password:np})});
    var d=await r.json();
    if(d.ok){showMsg('cpOk','ok','¡Contraseña guardada! Ingresando…');setTimeout(function(){window.location.replace('/');},1200);}
    else{showMsg('cpErr','err',d.error||'Error al guardar.');setLoad('cpBtn','cpLd','cpTxt',false);}
  }catch(e){showMsg('cpErr','err','Error de conexión.');setLoad('cpBtn','cpLd','cpTxt',false);}
}
document.addEventListener('keydown',function(e){
  if(e.key!=='Enter')return;
  if(document.getElementById('cpOverlay').classList.contains('show')){if(!document.getElementById('cpBtn').disabled)doChange();}
  else if(!document.getElementById('regOv').classList.contains('show')){doLogin();}
});
if(window.location.search.indexOf('expired=1')>=0)showMsg('warnMsg','warn','Sesión expirada. Ingresa nuevamente.');
document.getElementById('uInput').focus();
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────────────────
# ESTADO EN MEMORIA (anti-brute force)
# ─────────────────────────────────────────────────────────────────

_failed_attempts = {}
_lock = threading.Lock()


def _get_client_ip(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _is_locked_out(ip):
    with _lock:
        data = _failed_attempts.get(ip)
        if not data:
            return False, 0
        if time.time() < data.get("until", 0):
            secs = int(data["until"] - time.time())
            return True, secs
        _failed_attempts.pop(ip, None)
        return False, 0


def _register_fail(ip):
    with _lock:
        data = _failed_attempts.setdefault(ip, {"count": 0, "until": 0})
        data["count"] += 1
        if data["count"] >= MAX_FAILED_ATTEMPTS:
            data["until"] = time.time() + LOCKOUT_SECONDS
            data["count"] = 0


def _clear_fails(ip):
    with _lock:
        _failed_attempts.pop(ip, None)


# ─────────────────────────────────────────────────────────────────
# PLANES — helpers de base de datos
# ─────────────────────────────────────────────────────────────────

def _get_user_full(username: str) -> dict | None:
    """Devuelve {id, username, plan, email} del usuario, o None.
    Usa SELECT * para ser robusto ante distintos nombres de columna en la BD."""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM vf_users WHERE username=%s LIMIT 1",
                (username,),
            )
            cols = [d[0].lower() for d in (cur.description or [])]
            row  = cur.fetchone()
        conn.close()
        if not row:
            print(f"[AUTH] _get_user_full: usuario '{username}' NO encontrado en BD")
            return None
        r = dict(zip(cols, row))

        # ── DEBUG: mostrar TODAS las columnas para diagnosticar ──────
        import sys as _sys
        print(f"[AUTH] DB columnas: {cols}", flush=True)
        print(f"[AUTH] DB valores:  {dict((k, v) for k, v in r.items() if k not in ('password_hash','password','passwd','pwd'))}", flush=True)
        # ─────────────────────────────────────────────────────────────

        # Buscar el campo plan: primero nombres conocidos, luego buscar
        # en TODOS los valores de la fila por un valor de plan válido
        _known_plan_values = set(PLANS.keys()) | set(PLAN_ALIASES.keys())
        plan_raw = (
            r.get("plan") or r.get("plan_type") or
            r.get("subscription") or r.get("membership") or
            r.get("tier") or r.get("user_plan") or
            r.get("user_tier") or r.get("account_type") or
            r.get("level") or r.get("package") or
            r.get("user_type") or r.get("service")
        )
        # Si ninguna columna conocida tiene el plan, buscar en todos los valores
        if not plan_raw or str(plan_raw).lower().strip() not in _known_plan_values:
            for col_name, col_val in r.items():
                if (isinstance(col_val, str)
                        and col_val.lower().strip() in _known_plan_values
                        and col_name not in ('role', 'status', 'username', 'user_mail', 'email')):
                    print(f"[AUTH] plan encontrado en columna '{col_name}' = '{col_val}'")
                    plan_raw = col_val
                    break

        # Buscar el correo con varios nombres posibles
        email_val = (
            r.get("user_mail") or r.get("email") or
            r.get("user_email") or r.get("correo") or ""
        )
        # Si no se encontró, buscar cualquier valor con "@"
        if not email_val:
            for col_val in r.values():
                if isinstance(col_val, str) and "@" in col_val:
                    email_val = col_val
                    break

        # Buscar fecha de expiración del plan y fecha de registro
        _expires = (r.get("plan_expires_at") or r.get("expires_at")
                    or r.get("plan_expiry") or r.get("subscription_end"))
        _created = (r.get("created_at") or r.get("registered_at")
                    or r.get("reg_date") or r.get("date_created"))
        result = {
            "id":             r.get("id") or 0,
            "username":       r.get("username") or username,
            "plan":           str(plan_raw) if plan_raw else "basico",
            "email":          str(email_val) if email_val else "",
            "plan_expires_at": str(_expires) if _expires else None,
            "created_at":     str(_created) if _created else None,
        }
        print(f"[AUTH] _get_user_full result: username={result['username']}, plan={result['plan']}, email={result['email']}", flush=True)
        return result
    except Exception as e:
        print(f"[AUTH] _get_user_full error: {e}", flush=True)
        return None


def _ensure_tables():
    """Crea las tablas de uso si no existen (se llama al arrancar init_auth)."""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vf_usage (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    user_id          INT  NOT NULL,
                    usage_date       DATE NOT NULL,
                    videos_generated INT DEFAULT 0,
                    tts_chars_used   INT DEFAULT 0,
                    shorts_generated INT DEFAULT 0,
                    UNIQUE KEY uq_user_date (user_id, usage_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Agregar columnas si la tabla ya existía sin ellas
            for col, ddl in [
                ("shorts_generated", "INT DEFAULT 0 NOT NULL"),
            ]:
                try:
                    cur.execute(f"ALTER TABLE vf_usage ADD COLUMN {col} {ddl}")
                except Exception:
                    pass  # ya existe
            # Agregar subscription_date a vf_users si no existe
            try:
                cur.execute("ALTER TABLE vf_users ADD COLUMN subscription_date DATE DEFAULT NULL")
            except Exception:
                pass
        conn.commit()
        conn.close()
        print("[AUTH] Tabla vf_usage OK.", flush=True)
    except Exception as e:
        print(f"[AUTH] _ensure_tables error: {e}", flush=True)
    _ensure_stripe_table()


def get_today_usage(user_id: int) -> dict:
    """Devuelve {videos, tts_chars, shorts} para hoy (UTC)."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT videos_generated, tts_chars_used, "
                "COALESCE(shorts_generated,0) "
                "FROM vf_usage WHERE user_id=%s AND usage_date=%s LIMIT 1",
                (user_id, today),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return {"videos": int(row[0]), "tts_chars": int(row[1]), "shorts": int(row[2])}
    except Exception as e:
        print(f"[AUTH] get_today_usage error: {e}")
    return {"videos": 0, "tts_chars": 0, "shorts": 0}


def get_month_usage(user_id: int) -> dict:
    """Suma uso del mes calendario actual. Devuelve {videos, tts_chars, shorts}."""
    now = datetime.utcnow()
    month_start = now.strftime("%Y-%m-01")
    tomorrow    = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(videos_generated),0), "
                "       COALESCE(SUM(tts_chars_used),0), "
                "       COALESCE(SUM(COALESCE(shorts_generated,0)),0) "
                "FROM vf_usage "
                "WHERE user_id=%s AND usage_date >= %s AND usage_date < %s",
                (user_id, month_start, tomorrow),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return {"videos": int(row[0]), "tts_chars": int(row[1]), "shorts": int(row[2])}
    except Exception as e:
        print(f"[AUTH] get_month_usage error: {e}")
    return {"videos": 0, "tts_chars": 0, "shorts": 0}


def record_usage(user_id: int, videos: int = 0, tts_chars: int = 0, shorts: int = 0) -> bool:
    """Incrementa atómicamente los contadores del día actual."""
    if videos == 0 and tts_chars == 0 and shorts == 0:
        return True
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vf_usage "
                "(user_id, usage_date, videos_generated, tts_chars_used, shorts_generated) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "videos_generated = videos_generated + VALUES(videos_generated), "
                "tts_chars_used   = tts_chars_used   + VALUES(tts_chars_used), "
                "shorts_generated = COALESCE(shorts_generated,0) + VALUES(shorts_generated)",
                (user_id, today, videos, tts_chars, shorts),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[AUTH] record_usage error: {e}")
        return False


def check_limit(username: str, check_type: str, amount: int = 1):
    """
    Verifica si el usuario puede realizar la acción.
    check_type : 'video' | 'tts' | 'short'
    amount     : para 'tts', nº de caracteres; para 'video'/'short', siempre 1
    Devuelve   : (allowed: bool, message: str, extra: dict)
    Los límites de video y shorts son mensuales; TTS también es mensual.
    """
    user = _get_user_full(username)
    if not user:
        return False, "Usuario no encontrado", {}

    plan_key = normalize_plan_key(user["plan"])
    plan     = PLANS[plan_key]
    usage    = get_month_usage(user["id"])   # totales del mes actual

    if check_type == "video":
        limit = plan["videos_per_month"]
        used  = usage["videos"]
        if limit is None:
            return True, "", {"used": used, "limit": None, "remaining": None}
        if used >= limit:
            return (
                False,
                f"Has alcanzado el límite de {limit} videos/mes de tu plan {plan['name']}. "
                f"Haz upgrade para continuar.",
                {"used": used, "limit": limit, "remaining": 0,
                 "type": "video", "plan": plan_key},
            )
        return True, "", {"used": used, "limit": limit, "remaining": limit - used}

    if check_type == "short":
        limit = plan["shorts_per_month"]
        used  = usage["shorts"]
        if limit is None:
            return True, "", {"used": used, "limit": None, "remaining": None}
        if used >= limit:
            return (
                False,
                f"Has alcanzado el límite de {limit} shorts/mes de tu plan {plan['name']}. "
                f"Haz upgrade para continuar.",
                {"used": used, "limit": limit, "remaining": 0,
                 "type": "short", "plan": plan_key},
            )
        return True, "", {"used": used, "limit": limit, "remaining": limit - used}

    if check_type == "tts":
        limit = plan["tts_chars_per_month"]
        used  = usage["tts_chars"]
        if limit is None:
            return True, "", {"used": used, "limit": None, "remaining": None}
        remaining = max(0, limit - used)
        if used + amount > limit:
            return (
                False,
                f"Límite de audio alcanzado: {plan['audio_hours_per_month']}h/mes (plan {plan['name']}). "
                f"Disponible: {_chars_to_min(remaining)}. Haz upgrade para más.",
                {"used": used, "limit": limit, "remaining": remaining,
                 "type": "tts", "plan": plan_key},
            )
        return True, "", {"used": used, "limit": limit, "remaining": remaining - amount}

    return True, "", {}


def check_video_duration(username: str, duration_seconds: float):
    """
    Verifica si la duración del video está dentro del límite del plan.
    Devuelve (allowed: bool, message: str)
    """
    user = _get_user_full(username)
    if not user:
        return False, "Usuario no encontrado"

    plan_key  = normalize_plan_key(user["plan"])
    plan      = PLANS[plan_key]
    max_min   = plan.get("max_video_minutes")

    if max_min is None:       # Ultra: ilimitado
        return True, ""

    if duration_seconds > max_min * 60:
        dur_min = duration_seconds / 60
        return (
            False,
            f"El audio ({dur_min:.1f} min) supera el límite de {max_min} min/video "
            f"de tu plan {plan['name']}. Haz upgrade para videos más largos.",
        )
    return True, ""


# ─────────────────────────────────────────────────────────────────
# STRIPE — actualización de plan y log de pagos
# ─────────────────────────────────────────────────────────────────

def _ensure_stripe_table():
    """Crea la tabla de pagos Stripe si no existe."""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vf_stripe_payments (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    username         VARCHAR(120) NOT NULL,
                    plan             VARCHAR(40)  NOT NULL,
                    amount_usd       DECIMAL(10,2) DEFAULT 0,
                    stripe_session_id VARCHAR(255),
                    paid_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_session (stripe_session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # compatibilidad: añadir columnas nuevas si la tabla ya existía
            for col, ddl in [
                ("amount_usd",        "DECIMAL(10,2) DEFAULT 0"),
                ("paid_at",           "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("stripe_session_id", "VARCHAR(255)"),
                ("plan",              "VARCHAR(40) NOT NULL DEFAULT 'unknown'"),
            ]:
                try:
                    cur.execute(f"ALTER TABLE vf_stripe_payments ADD COLUMN {col} {ddl}")
                except Exception:
                    pass
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[STRIPE] _ensure_stripe_table: {e}")


def _update_user_plan(username: str, new_plan: str, stripe_session_id: str = None) -> bool:
    """
    Actualiza el plan del usuario en la BD.
    Retorna True si se actualizó correctamente.
    """
    try:
        conn = _get_db_connection()
        plan_obj = PLANS.get(new_plan, {})
        amount   = plan_obj.get("price_usd", 0)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vf_users SET plan=%s, subscription_date=CURDATE() WHERE username=%s",
                (new_plan, username)
            )
            updated = cur.rowcount > 0
        conn.commit()
        # Registrar pago
        if updated and stripe_session_id:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT IGNORE INTO vf_stripe_payments "
                        "(username, plan, amount_usd, stripe_session_id) "
                        "VALUES (%s, %s, %s, %s)",
                        (username, new_plan, amount, stripe_session_id)
                    )
                conn.commit()
            except Exception:
                pass
        conn.close()
        if updated:
            print(f"[STRIPE] Plan actualizado: {username} --> {new_plan}")
        return updated
    except Exception as e:
        print(f"[STRIPE] _update_user_plan error: {e}")
        return False


def _verify_stripe_session(session_id: str) -> dict | None:
    """
    Verifica una sesión de Stripe y retorna {paid: bool, plan: str|None, customer_email: str|None}.
    Retorna None si hay error.
    """
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET_KEY
        session = _stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
        paid = (
            session.payment_status in ("paid", "no_payment_required")
            or session.status == "complete"
        )
        meta_plan = None
        if session.metadata:
            meta_plan = session.metadata.get("plan") or session.metadata.get("plan_key")
        return {
            "paid":           paid,
            "plan":           meta_plan,
            "customer_email": session.customer_details.email if session.customer_details else None,
            "session_id":     session_id,
        }
    except Exception as e:
        print(f"[STRIPE] _verify_stripe_session error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# SESIONES  — token deslizante + validación de boot epoch
# ─────────────────────────────────────────────────────────────────

SESSION_COOKIE = "vf_session"


def _sign(payload, secret):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(username, secret):
    """Crea un token firmado con HMAC-SHA256.
    Contiene 'boot' para invalidar tokens de arranques anteriores del servidor."""
    import base64
    expires = int(time.time() + SESSION_MINUTES * 60)
    payload = json.dumps({"u": username, "exp": expires, "boot": _SERVER_BOOT})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{encoded}.{_sign(encoded, secret)}"


def _verify_token(token, secret):
    """Verifica firma y que el boot epoch coincida con el arranque actual.
    La sesión no expira por inactividad — dura hasta que la app se cierre/reinicie."""
    try:
        import base64
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        encoded, sig = parts
        if not hmac.compare_digest(sig, _sign(encoded, secret)):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode())
        # Rechaza tokens de sesiones de un arranque anterior del servidor
        if payload.get("boot") != _SERVER_BOOT:
            return None
        # Validar expiración del token
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("u")
    except Exception:
        return None


def _get_current_user(request, secret):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return _verify_token(token, secret)


def _is_public(path):
    if path in PUBLIC_ROUTES or path.startswith("/static/"):
        return True
    # Prefix-based public routes (e.g. /api/admin/docs/123)
    _PUBLIC_PREFIXES = ("/api/admin/docs", "/admin/docs", "/api/docs")
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


# ─────────────────────────────────────────────────────────────────
# UI INYECTADA — sidebar (Upgrade + Config + Logout) + overlays + popup
# ─────────────────────────────────────────────────────────────────

_INJECT_HTML = """
<style>
/* ── Sidebar buttons ────────────────────────────────────── */
.vf-sb-btn{
  display:flex;align-items:center;gap:8px;width:calc(100% - 20px);
  margin:0 10px 2px;padding:9px 10px;
  background:none;border:none;cursor:pointer;
  font-family:var(--mono,'JetBrains Mono',monospace);
  font-size:11px;font-weight:400;letter-spacing:.01em;border-radius:9px;
  transition:color .15s,background .15s;text-align:left;
}
#vf-logout-btn{color:rgba(255,80,80,.65)}
#vf-logout-btn:hover{color:#ff5566;background:rgba(255,50,50,.07)}
#vf-config-btn{color:rgba(180,180,220,.7)}
#vf-config-btn:hover{color:#eef2ff;background:rgba(124,106,255,.1)}
#vf-upgrade-btn{
  width:calc(100% - 20px);margin:0 10px 4px;padding:9px 12px;
  background:linear-gradient(135deg,rgba(124,106,255,.22),rgba(244,114,182,.18));
  border:1px solid rgba(167,139,250,.35);border-radius:10px;cursor:pointer;
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px;font-weight:600;
  color:#c4b5fd;letter-spacing:.03em;display:flex;align-items:center;gap:8px;
  transition:background .2s,border-color .2s,color .2s;text-align:left;
}
#vf-upgrade-btn:hover{
  background:linear-gradient(135deg,rgba(124,106,255,.38),rgba(244,114,182,.28));
  border-color:rgba(167,139,250,.6);color:#ddd6fe;
}
/* ── Session warning toast ──────────────────────────────── */
#vf-session-warn{
  position:fixed;bottom:22px;right:22px;z-index:2147483645;
  background:rgba(15,15,28,.97);border:1px solid rgba(251,191,36,.35);
  border-radius:14px;padding:14px 18px;font-family:'JetBrains Mono',monospace;
  font-size:12px;color:#fbbf24;box-shadow:0 8px 36px rgba(0,0,0,.6);
  display:none;flex-direction:row;gap:14px;align-items:center;
}
#vf-session-warn button{
  background:rgba(251,191,36,.14);border:1px solid rgba(251,191,36,.3);
  border-radius:7px;padding:4px 11px;color:#fbbf24;cursor:pointer;
  font-family:inherit;font-size:11px;white-space:nowrap;
}
/* ── Limit popup ────────────────────────────────────────── */
#vf-limit-popup{
  position:fixed;bottom:24px;right:24px;z-index:2147483644;
  max-width:340px;background:rgba(10,10,22,.97);
  border:1px solid rgba(124,106,255,.35);border-radius:18px;
  padding:20px 22px;box-shadow:0 16px 48px rgba(0,0,0,.75),0 0 0 1px rgba(124,106,255,.12);
  display:none;flex-direction:column;gap:12px;
  animation:vfPopIn .3s cubic-bezier(.22,1,.36,1);
}
@keyframes vfPopIn{from{opacity:0;transform:translateY(20px) scale(.95)}to{opacity:1;transform:none}}
#vf-limit-popup .vflp-head{display:flex;align-items:center;gap:10px}
#vf-limit-popup .vflp-icon{font-size:22px;line-height:1}
#vf-limit-popup .vflp-title{font-family:var(--mono,'JetBrains Mono',monospace);font-size:12px;
  font-weight:700;color:#eef2ff;letter-spacing:.02em}
#vf-limit-popup .vflp-msg{font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px;
  color:rgba(255,255,255,.55);line-height:1.55}
#vf-limit-popup .vflp-bar-wrap{background:rgba(255,255,255,.06);border-radius:6px;height:6px;overflow:hidden}
#vf-limit-popup .vflp-bar{height:100%;border-radius:6px;
  background:linear-gradient(90deg,#7c6aff,#f472b6);transition:width .4s}
#vf-limit-popup .vflp-btns{display:flex;gap:8px;margin-top:4px}
#vf-limit-popup .vflp-upgrade{
  flex:1;padding:9px;border-radius:9px;border:none;cursor:pointer;
  background:linear-gradient(135deg,#6c56ff,#a855f7);
  color:#fff;font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px;
  font-weight:700;letter-spacing:.04em;transition:opacity .15s;
}
#vf-limit-popup .vflp-upgrade:hover{opacity:.85}
#vf-limit-popup .vflp-close{
  padding:9px 12px;border-radius:9px;border:1px solid rgba(255,255,255,.1);
  background:none;color:rgba(255,255,255,.4);cursor:pointer;
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px;
  transition:color .15s,border-color .15s;
}
#vf-limit-popup .vflp-close:hover{color:#eef2ff;border-color:rgba(255,255,255,.25)}
/* Clase de fuerza para cerrar overlays (respaldo al inline style) */
.vf-overlay-closed{display:none!important;animation:none!important;}
/* ── Full-screen overlays ───────────────────────────────── */
.vf-overlay{
  position:fixed;inset:0;z-index:2147483640;overflow-y:auto;
  background:#06060e;
  background-image:radial-gradient(ellipse 140% 80% at 50% -5%,rgba(108,86,255,.24) 0%,transparent 52%);
  display:none;
  animation:vfOverlayIn .32s cubic-bezier(.22,1,.36,1);
}
@keyframes vfOverlayIn{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
.vf-overlay-inner{max-width:1280px;margin:0 auto;padding:36px 36px 80px}
.vf-ov-back{
  display:inline-flex;align-items:center;gap:8px;margin-bottom:36px;
  background:none;border:none;cursor:pointer;color:rgba(255,255,255,.38);
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:10px;
  letter-spacing:.1em;text-transform:uppercase;padding:0;
  transition:color .18s;
}
.vf-ov-back:hover{color:rgba(255,255,255,.8)}
.vf-ov-title{
  font-size:34px;font-weight:800;letter-spacing:-.8px;margin-bottom:8px;
  background:linear-gradient(90deg,#eef2ff 30%,rgba(167,139,250,.7));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.vf-ov-sub{
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:11.5px;
  color:rgba(255,255,255,.32);margin-bottom:44px;letter-spacing:.01em;
}
/* Settings: avatar + profile card */
.vf-profile-card{
  background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);
  border-radius:20px;padding:28px;display:flex;align-items:center;gap:22px;
  margin-bottom:24px;
}
.vf-avatar{
  width:64px;height:64px;border-radius:50%;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;
  font-size:26px;font-weight:800;color:#fff;letter-spacing:-.5px;
  box-shadow:0 0 0 3px rgba(124,106,255,.3),0 6px 24px rgba(0,0,0,.5);
}
.vf-profile-info{flex:1;min-width:0}
.vf-profile-name{font-size:20px;font-weight:800;letter-spacing:-.4px;color:#eef2ff;margin-bottom:3px}
.vf-profile-email{font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px;
  color:rgba(255,255,255,.35);margin-bottom:10px;word-break:break-all}
.vf-plan-badge{
  display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:10px;font-weight:700;
  letter-spacing:.08em;text-transform:uppercase;
}
/* Usage section */
.vf-usage-card{
  background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);
  border-radius:20px;padding:24px;margin-bottom:24px;
}
.vf-usage-title{font-family:var(--mono,'JetBrains Mono',monospace);font-size:9px;
  color:rgba(255,255,255,.3);letter-spacing:.14em;text-transform:uppercase;margin-bottom:18px}
.vf-usage-row{margin-bottom:16px}
.vf-usage-row:last-child{margin-bottom:0}
.vf-usage-label{display:flex;justify-content:space-between;margin-bottom:7px;
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px}
.vf-usage-label span:first-child{color:rgba(255,255,255,.65)}
.vf-usage-label span:last-child{color:rgba(255,255,255,.3)}
.vf-usage-track{background:rgba(255,255,255,.06);border-radius:8px;height:8px;overflow:hidden}
.vf-usage-fill{height:100%;border-radius:8px;transition:width .5s cubic-bezier(.22,1,.36,1)}
.vf-upgrade-cta{
  width:100%;padding:14px;border-radius:14px;border:none;cursor:pointer;
  background:linear-gradient(135deg,#6c56ff 0%,#a855f7 100%);
  color:#fff;font-family:var(--mono,'JetBrains Mono',monospace);font-size:12px;
  font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  box-shadow:0 4px 20px rgba(124,106,255,.4);transition:all .22s;
}
.vf-upgrade-cta:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(124,106,255,.55)}
/* Plans grid ─ upgrade overlay */
/* ── Plans grid — 5 cols ──────────────────────────────────── */
.vf-plans-grid{
  display:grid;
  grid-template-columns:repeat(5,minmax(0,1fr));
  gap:18px;margin-bottom:40px;align-items:stretch;
}
@media(max-width:1100px){.vf-plans-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}
@media(max-width:700px) {.vf-plans-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
@media(max-width:460px) {.vf-plans-grid{grid-template-columns:1fr;gap:12px}}

/* Card base */
.vf-plan-card{
  position:relative;border-radius:22px;padding:0;
  display:flex;flex-direction:column;overflow:hidden;
  background:rgba(255,255,255,.038);
  border:1px solid rgba(255,255,255,.09);
  color:#eef2ff;
  transition:transform .3s cubic-bezier(.22,1,.36,1),
             box-shadow .3s,border-color .3s;
}
.vf-plan-card:not(.vf-plan-card-free):hover{
  transform:translateY(-6px);
  border-color:rgba(255,255,255,.18);
  box-shadow:0 24px 60px rgba(0,0,0,.45);
}

/* Free plan — muted */
.vf-plan-card-free{
  background:rgba(255,255,255,.018);
  border-color:rgba(255,255,255,.055);
  opacity:.75;
}
.vf-plan-card-free:hover{opacity:.95;border-color:rgba(255,255,255,.1)}

/* Inner wrapper */
.vf-plan-card-inner{
  padding:26px 22px 22px;
  display:flex;flex-direction:column;flex:1;
}
/* Colored accent bar at top */
.vf-plan-accent{height:4px;width:100%;flex-shrink:0}

/* Pro — highlighted */
.vf-plan-card.highlight{
  background:linear-gradient(155deg,rgba(108,86,255,.16) 0%,rgba(168,85,247,.05) 100%);
  border-color:rgba(108,86,255,.42);
  transform:translateY(-10px);
  box-shadow:0 0 0 1px rgba(108,86,255,.22),
             0 24px 70px rgba(108,86,255,.22),
             0 8px 24px rgba(0,0,0,.45);
}
.vf-plan-card.highlight:hover{
  transform:translateY(-16px);
  box-shadow:0 0 0 1px rgba(168,85,247,.55),
             0 36px 90px rgba(108,86,255,.32),
             0 12px 32px rgba(0,0,0,.55);
}
@keyframes vfGlow{
  0%,100%{box-shadow:0 0 0 1px rgba(108,86,255,.22),0 24px 70px rgba(108,86,255,.22),0 8px 24px rgba(0,0,0,.45)}
  50%    {box-shadow:0 0 0 1px rgba(168,85,247,.4), 0 24px 70px rgba(108,86,255,.34),0 8px 24px rgba(0,0,0,.45)}
}
.vf-plan-card.highlight{animation:vfGlow 3.2s ease-in-out infinite}

/* Current plan */
.vf-plan-card.current{
  border-color:rgba(34,211,160,.42)!important;
  box-shadow:0 0 0 1px rgba(34,211,160,.14),0 8px 32px rgba(34,211,160,.07)!important;
}

/* Ribbon badge */
.vf-plan-ribbon{
  display:inline-flex;align-items:center;gap:5px;align-self:flex-start;
  margin-bottom:16px;padding:5px 13px;border-radius:99px;
  background:linear-gradient(135deg,#6c56ff,#a855f7);
  color:#fff;font-family:var(--mono,'JetBrains Mono',monospace);
  font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  box-shadow:0 3px 14px rgba(108,86,255,.45);
}
/* Plan name row */
.vf-plan-name-row{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.vf-plan-icon-badge{
  width:42px;height:42px;border-radius:13px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
}
/* Plan name */
.vf-plan-name{font-size:22px;font-weight:800;letter-spacing:-.5px}
/* Tagline */
.vf-plan-tagline{
  font-family:var(--mono,'JetBrains Mono',monospace);
  font-size:10px;color:rgba(255,255,255,.33);margin-bottom:20px;
}
/* Price */
.vf-plan-price{
  display:flex;align-items:flex-end;gap:5px;
  margin-bottom:22px;line-height:1;
}
.vf-plan-price .amt{font-size:46px;font-weight:800;letter-spacing:-2.5px;line-height:.88}
.vf-plan-price .per{font-size:12px;color:rgba(255,255,255,.28);margin-bottom:5px}
/* Separator */
.vf-plan-sep{height:1px;background:rgba(255,255,255,.07);margin:0 0 20px}
/* Features */
.vf-plan-features{
  list-style:none;padding:0;margin:0 0 24px;
  display:flex;flex-direction:column;gap:11px;flex:1;
}
.vf-plan-features li{
  display:flex;align-items:flex-start;gap:9px;
  font-size:12.5px;color:rgba(255,255,255,.68);line-height:1.4;
}
.vf-plan-features li.vf-feat-no{color:rgba(255,255,255,.26)}
.vf-plan-features li .vfck{
  width:20px;height:20px;border-radius:50%;flex-shrink:0;margin-top:1px;
  display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:800;
}
/* Buttons */
.vf-plan-btn{
  width:100%;padding:14px;border-radius:13px;border:none;cursor:pointer;
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:11px;
  font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  transition:all .26s cubic-bezier(.22,1,.36,1);
}
.vf-plan-btn.current-plan{
  background:rgba(255,255,255,.05);border:1.5px solid rgba(255,255,255,.1);
  color:rgba(255,255,255,.3);cursor:default;
}
.vf-plan-btn.free-btn{
  color:rgba(255,255,255,.35);background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.07);cursor:default;font-size:10px;
}
.vf-plan-btn.starter-btn{
  color:#052e1c;background:linear-gradient(135deg,#22d3a0,#10b981);
  box-shadow:0 4px 18px rgba(34,211,160,.32);
}
.vf-plan-btn.starter-btn:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(34,211,160,.5)}
.vf-plan-btn.pro-btn{
  color:#fff;background:linear-gradient(135deg,#6c56ff,#a855f7);
  box-shadow:0 4px 22px rgba(108,86,255,.45);
}
.vf-plan-btn.pro-btn:hover{transform:translateY(-2px);box-shadow:0 10px 34px rgba(108,86,255,.65)}
.vf-plan-btn.ultra-btn{
  color:#2d1a00;background:linear-gradient(135deg,#fbbf24,#f59e0b);
  box-shadow:0 4px 18px rgba(251,191,36,.32);
}
.vf-plan-btn.ultra-btn:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(251,191,36,.5)}
.vf-plan-btn.unlimited-btn{
  color:#fff;background:linear-gradient(135deg,#9333ea,#c084fc,#e879f9);
  box-shadow:0 4px 22px rgba(192,132,252,.45);
}
.vf-plan-btn.unlimited-btn:hover{transform:translateY(-2px);box-shadow:0 10px 34px rgba(192,132,252,.65)}
/* ── Pay-waiting & pay-ok banners ───────────────────────── */
#vf-pay-waiting,#vf-pay-ok{
  position:fixed;bottom:28px;left:50%;transform:translateX(-50%);
  z-index:2147483646;display:none;align-items:center;gap:14px;
  background:rgba(10,10,22,.98);border-radius:18px;padding:18px 26px;
  box-shadow:0 20px 60px rgba(0,0,0,.7),0 0 0 1px rgba(124,106,255,.25);
  font-family:var(--mono,'JetBrains Mono',monospace);
  animation:vfPopIn .3s cubic-bezier(.22,1,.36,1);
  max-width:calc(100vw - 40px);white-space:nowrap;
}
#vf-pay-waiting{border:1px solid rgba(124,106,255,.35)}
#vf-pay-ok    {border:1px solid rgba(34,211,160,.45)}
.vf-pw-spin{
  width:20px;height:20px;border-radius:50%;flex-shrink:0;
  border:2.5px solid rgba(124,106,255,.25);
  border-top-color:#a78bfa;
  animation:vfSpin 0.85s linear infinite;
}
@keyframes vfSpin{to{transform:rotate(360deg)}}
.vf-pw-text{font-size:12px;font-weight:600;color:#c4b5fd;letter-spacing:.02em}
.vf-pw-sub {font-size:10px;color:rgba(255,255,255,.32);margin-top:3px}
.vf-pw-plan{color:#a78bfa;font-weight:700}
.vf-pw-cancel{
  margin-left:8px;padding:5px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.1);
  background:none;color:rgba(255,255,255,.35);cursor:pointer;
  font-family:inherit;font-size:10px;transition:color .15s,border-color .15s;
}
.vf-pw-cancel:hover{color:#eef2ff;border-color:rgba(255,255,255,.3)}
.vf-pk-icon{font-size:22px;line-height:1;flex-shrink:0}
.vf-pk-text{font-size:12px;font-weight:700;color:#22d3a0;letter-spacing:.02em}
.vf-pk-sub {font-size:10px;color:rgba(255,255,255,.4);margin-top:3px}
.vf-pk-plan{color:#22d3a0;font-weight:700}
/* Payment record card */
.vf-payment-card{
  background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.07);
  border-radius:20px;padding:20px 24px;margin-bottom:24px;
}
.vf-payment-title{
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:9px;
  color:rgba(255,255,255,.3);letter-spacing:.14em;text-transform:uppercase;
  margin-bottom:14px;
}
.vf-payment-row{
  display:flex;justify-content:space-between;align-items:center;
  padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);
}
.vf-payment-row:last-child{border-bottom:none;padding-bottom:0}
.vf-payment-label{
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:10.5px;
  color:rgba(255,255,255,.42);
}
.vf-payment-value{
  font-family:var(--mono,'JetBrains Mono',monospace);font-size:10.5px;
  color:rgba(255,255,255,.82);font-weight:600;
}
</style>

<!-- Session expiry warning -->
<div id="vf-session-warn">
  <span>&#9201; Sesi&oacute;n expira en 5&nbsp;min</span>
  <button onclick="window._vfResetIdle()">Mantener sesi&oacute;n</button>
</div>

<!-- Limit reached popup -->
<div id="vf-limit-popup">
  <div class="vflp-head">
    <span class="vflp-icon">⚡</span>
    <span class="vflp-title" id="vflp-title">L&iacute;mite alcanzado</span>
  </div>
  <div class="vflp-msg" id="vflp-msg"></div>
  <div class="vflp-bar-wrap"><div class="vflp-bar" id="vflp-bar" style="width:100%"></div></div>
  <div class="vflp-btns">
    <button class="vflp-upgrade" id="vflp-upgrade-btn" onclick="window.vfOpenUpgrade()">
      &#8599; Ver planes
    </button>
    <button class="vflp-close" onclick="document.getElementById('vf-limit-popup').style.display='none'">
      Cerrar
    </button>
  </div>
</div>

<!-- Pay waiting banner -->
<div id="vf-pay-waiting">
  <div class="vf-pw-spin"></div>
  <div>
    <div class="vf-pw-text">Esperando confirmaci&oacute;n de pago &mdash; <span class="vf-pw-plan"></span></div>
    <div class="vf-pw-sub">Completa el pago en la pesta&ntilde;a de Stripe. El plan se activar&aacute; autom&aacute;ticamente.</div>
  </div>
  <button class="vf-pw-cancel" onclick="window._vfCancelPoll()">Cancelar</button>
</div>

<!-- Pay ok banner -->
<div id="vf-pay-ok">
  <div class="vf-pk-icon">&#10003;</div>
  <div>
    <div class="vf-pk-text">&#161;Plan <span class="vf-pk-plan"></span> activado!</div>
    <div class="vf-pk-sub">Tu cuenta se ha actualizado correctamente.</div>
  </div>
</div>

<!-- Settings overlay -->
<div id="vf-overlay-settings" class="vf-overlay">
  <div class="vf-overlay-inner">
    <button class="vf-ov-back" onclick="window.vfCloseOverlay('settings')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15,18 9,12 15,6"/></svg>
      Volver
    </button>
    <div class="vf-ov-title">Configuraci&oacute;n</div>
    <div class="vf-ov-sub" id="vf-settings-sub">Cargando perfil&hellip;</div>

    <div class="vf-profile-card" id="vf-profile-card">
      <div class="vf-avatar" id="vf-avatar" style="background:linear-gradient(135deg,#6c56ff,#a855f7)">?</div>
      <div class="vf-profile-info">
        <div class="vf-profile-name" id="vf-profile-name">&mdash;</div>
        <div class="vf-profile-email" id="vf-profile-email">&mdash;</div>
        <span class="vf-plan-badge" id="vf-plan-badge" style="background:rgba(34,211,160,.12);color:#22d3a0;border:1px solid rgba(34,211,160,.25)">
          Starter
        </span>
      </div>
    </div>

    <div class="vf-usage-card">
      <div class="vf-usage-title">Uso este mes</div>
      <div class="vf-usage-row">
        <div class="vf-usage-label">
          <span>Videos generados</span>
          <span id="vf-usage-videos-label">0 / —</span>
        </div>
        <div class="vf-usage-track">
          <div class="vf-usage-fill" id="vf-usage-videos-bar"
               style="width:0%;background:linear-gradient(90deg,#7c6aff,#a855f7)"></div>
        </div>
      </div>
      <div class="vf-usage-row">
        <div class="vf-usage-label">
          <span>Shorts generados</span>
          <span id="vf-usage-shorts-label">0 / —</span>
        </div>
        <div class="vf-usage-track">
          <div class="vf-usage-fill" id="vf-usage-shorts-bar"
               style="width:0%;background:linear-gradient(90deg,#fbbf24,#f59e0b)"></div>
        </div>
      </div>
      <div class="vf-usage-row">
        <div class="vf-usage-label">
          <span>Generaci&oacute;n de voz</span>
          <span id="vf-usage-tts-label">0 / — h</span>
        </div>
        <div class="vf-usage-track">
          <div class="vf-usage-fill" id="vf-usage-tts-bar"
               style="width:0%;background:linear-gradient(90deg,#22d3a0,#7c6aff)"></div>
        </div>
      </div>
    </div>

    <div class="vf-payment-card" id="vf-payment-card">
      <div class="vf-payment-title">&#128179;&nbsp; Suscripci&oacute;n</div>
      <div class="vf-payment-row">
        <span class="vf-payment-label">Fecha de suscripci&oacute;n</span>
        <span class="vf-payment-value" id="vf-payment-subdate">&mdash;</span>
      </div>
      <div class="vf-payment-row">
        <span class="vf-payment-label">Plan activado</span>
        <span class="vf-payment-value" id="vf-payment-activated">&mdash;</span>
      </div>
      <div class="vf-payment-row" id="vf-payment-renewal-row">
        <span class="vf-payment-label">Pr&oacute;xima renovaci&oacute;n</span>
        <span class="vf-payment-value" id="vf-payment-renewal">&mdash;</span>
      </div>
    </div>

    <div class="vf-payment-card" id="vf-history-card" style="display:none">
      <div class="vf-payment-title">&#128200;&nbsp; Historial de pagos</div>
      <div id="vf-history-list" style="display:flex;flex-direction:column;gap:6px;margin-top:4px"></div>
    </div>

    <div id="vf-settings-upgrade-wrap" style="display:none">
      <button class="vf-upgrade-cta" onclick="window.vfOpenUpgrade()">
        &#8599;&nbsp; Ver planes y hacer upgrade
      </button>
    </div>
  </div>
</div>

<!-- Upgrade / Plans overlay -->
<div id="vf-overlay-upgrade" class="vf-overlay">
  <div class="vf-overlay-inner">
    <button class="vf-ov-back" onclick="window.vfCloseOverlay('upgrade')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15,18 9,12 15,6"/></svg>
      Volver
    </button>
    <div class="vf-ov-title">Elige tu plan</div>
    <div class="vf-ov-sub" style="max-width:520px;margin-bottom:36px">
      Escala tu producci&oacute;n. Cancela cuando quieras.
    </div>

    <div class="vf-plans-grid" id="vf-plans-grid">

      <!-- ── Free ──────────────────────────────────── -->
      <div class="vf-plan-card vf-plan-card-free" id="vf-card-free">
        <div class="vf-plan-accent" style="background:linear-gradient(90deg,#475569,#64748b)"></div>
        <div class="vf-plan-card-inner">
          <div class="vf-plan-name-row">
            <span class="vf-plan-icon-badge" style="background:rgba(100,116,139,.12);color:#94a3b8;border:1px solid rgba(100,116,139,.2)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
            </span>
            <span class="vf-plan-name" style="color:#94a3b8">Free</span>
          </div>
          <div class="vf-plan-tagline">Prueba la plataforma</div>
          <div class="vf-plan-price">
            <span class="amt" style="color:#94a3b8">$0</span>
            <span class="per">/mes</span>
          </div>
          <div class="vf-plan-sep"></div>
          <ul class="vf-plan-features">
            <li><span class="vfck" style="background:#64748b20;color:#94a3b8">&#10003;</span>3 videos al mes</li>
            <li><span class="vfck" style="background:#64748b20;color:#94a3b8">&#10003;</span>20 min de voz al mes</li>
            <li class="vf-feat-no"><span class="vfck" style="background:rgba(255,255,255,.05);color:rgba(255,255,255,.2)">&#10005;</span>Sin shorts</li>
            <li class="vf-feat-no"><span class="vfck" style="background:rgba(255,255,255,.05);color:rgba(255,255,255,.2)">&#10005;</span>Sin imagen a video</li>
            <li class="vf-feat-no"><span class="vfck" style="background:rgba(255,255,255,.05);color:rgba(255,255,255,.2)">&#10005;</span>Sin renderizado</li>
          </ul>
          <button class="vf-plan-btn free-btn" id="vf-btn-free">Plan actual</button>
        </div>
      </div>

      <!-- ── Básico ─────────────────────────────── -->
      <div class="vf-plan-card" id="vf-card-basico">
        <div class="vf-plan-accent" style="background:linear-gradient(90deg,#22d3a0,#0ea5e9)"></div>
        <div class="vf-plan-card-inner">
          <div class="vf-plan-name-row">
            <span class="vf-plan-icon-badge" style="background:rgba(34,211,160,.12);color:#22d3a0;border:1px solid rgba(34,211,160,.2)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
            </span>
            <span class="vf-plan-name" style="color:#22d3a0">B&aacute;sico</span>
          </div>
          <div class="vf-plan-tagline">Para comenzar a producir</div>
          <div class="vf-plan-price">
            <span class="amt" style="color:#22d3a0">$75</span>
            <span class="per">/mes</span>
          </div>
          <div class="vf-plan-sep"></div>
          <ul class="vf-plan-features">
            <li><span class="vfck" style="background:#22d3a020;color:#22d3a0">&#10003;</span>45 videos al mes</li>
            <li><span class="vfck" style="background:#22d3a020;color:#22d3a0">&#10003;</span>15 shorts al mes</li>
            <li><span class="vfck" style="background:#22d3a020;color:#22d3a0">&#10003;</span>30 h audio al mes</li>
            <li><span class="vfck" style="background:#22d3a020;color:#22d3a0">&#10003;</span>Imagen a video</li>
            <li><span class="vfck" style="background:#22d3a020;color:#22d3a0">&#10003;</span>Renderizado</li>
            <li><span class="vfck" style="background:#22d3a020;color:#22d3a0">&#10003;</span>Miniaturas</li>
          </ul>
          <button class="vf-plan-btn starter-btn" id="vf-btn-basico" onclick="window._vfGoCheckout&&window._vfGoCheckout('basico')||window.open('https://buy.stripe.com/6oU3cx2S10sr24c4v93cc0b','_blank')">&#8599; Elegir B&aacute;sico</button>
        </div>
      </div>

      <!-- ── Pro ─────────────────────────────────── -->
      <div class="vf-plan-card highlight" id="vf-card-pro">
        <div class="vf-plan-accent" style="background:linear-gradient(90deg,#6c56ff,#a855f7,#ec4899)"></div>
        <div class="vf-plan-card-inner">
          <div class="vf-plan-ribbon">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            M&aacute;s popular
          </div>
          <div class="vf-plan-name-row">
            <span class="vf-plan-icon-badge" style="background:rgba(124,106,255,.15);color:#a78bfa;border:1px solid rgba(167,139,250,.22)">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            </span>
            <span class="vf-plan-name" style="color:#a78bfa">Pro</span>
          </div>
          <div class="vf-plan-tagline">El favorito de los creadores</div>
          <div class="vf-plan-price">
            <span class="amt" style="color:#a78bfa">$105</span>
            <span class="per">/mes</span>
          </div>
          <div class="vf-plan-sep"></div>
          <ul class="vf-plan-features">
            <li><span class="vfck" style="background:#7c6aff20;color:#a78bfa">&#10003;</span>60 videos al mes</li>
            <li><span class="vfck" style="background:#7c6aff20;color:#a78bfa">&#10003;</span>25 shorts al mes</li>
            <li><span class="vfck" style="background:#7c6aff20;color:#a78bfa">&#10003;</span>45 h audio al mes</li>
            <li><span class="vfck" style="background:#7c6aff20;color:#a78bfa">&#10003;</span>Modelado video (YouTube)</li>
            <li><span class="vfck" style="background:#7c6aff20;color:#a78bfa">&#10003;</span>Gui&oacute;n a video (1 clic)</li>
            <li><span class="vfck" style="background:#7c6aff20;color:#a78bfa">&#10003;</span>Renderizado + Miniaturas</li>
          </ul>
          <button class="vf-plan-btn pro-btn" id="vf-btn-pro" onclick="window._vfGoCheckout&&window._vfGoCheckout('pro')||window.open('https://buy.stripe.com/9B614p78h0sr7ow1iX3cc0c','_blank')">&#8599; Elegir Pro</button>
        </div>
      </div>

      <!-- ── Ultra ────────────────────────────────── -->
      <div class="vf-plan-card" id="vf-card-ultra">
        <div class="vf-plan-accent" style="background:linear-gradient(90deg,#fbbf24,#f97316)"></div>
        <div class="vf-plan-card-inner">
          <div class="vf-plan-name-row">
            <span class="vf-plan-icon-badge" style="background:rgba(251,191,36,.12);color:#fbbf24;border:1px solid rgba(251,191,36,.2)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            </span>
            <span class="vf-plan-name" style="color:#fbbf24">Ultra</span>
          </div>
          <div class="vf-plan-tagline">Producci&oacute;n profesional total</div>
          <div class="vf-plan-price">
            <span class="amt" style="color:#fbbf24">$145</span>
            <span class="per">/mes</span>
          </div>
          <div class="vf-plan-sep"></div>
          <ul class="vf-plan-features">
            <li><span class="vfck" style="background:#fbbf2420;color:#fbbf24">&#10003;</span>75 videos al mes</li>
            <li><span class="vfck" style="background:#fbbf2420;color:#fbbf24">&#10003;</span>35 shorts al mes</li>
            <li><span class="vfck" style="background:#fbbf2420;color:#fbbf24">&#10003;</span>60 h audio al mes</li>
            <li><span class="vfck" style="background:#fbbf2420;color:#fbbf24">&#10003;</span>Editor din&aacute;mico</li>
            <li><span class="vfck" style="background:#fbbf2420;color:#fbbf24">&#10003;</span>Modelado video (YouTube)</li>
            <li><span class="vfck" style="background:#fbbf2420;color:#fbbf24">&#10003;</span>Soporte 1 a 1</li>
          </ul>
          <button class="vf-plan-btn ultra-btn" id="vf-btn-ultra" onclick="window._vfGoCheckout&&window._vfGoCheckout('ultra')||window.open('https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d','_blank')">&#8599; Elegir Ultra</button>
        </div>
      </div>

      <!-- ── Ilimitado ──────────────────────────────── -->
      <div class="vf-plan-card" id="vf-card-unlimited" style="background:linear-gradient(160deg,rgba(147,51,234,.1) 0%,rgba(192,132,252,.04) 100%);border-color:rgba(192,132,252,.25)">
        <div class="vf-plan-accent" style="background:linear-gradient(90deg,#9333ea,#c084fc,#e879f9)"></div>
        <div class="vf-plan-card-inner">
          <div class="vf-plan-ribbon" style="background:linear-gradient(135deg,#9333ea,#c084fc)">&#9855; Enterprise</div>
          <div class="vf-plan-name-row">
            <span class="vf-plan-icon-badge" style="background:rgba(192,132,252,.15);color:#c084fc;border:1px solid rgba(192,132,252,.25)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.364 5.636a9 9 0 1 1-12.728 0M12 2v7"/></svg>
            </span>
            <span class="vf-plan-name" style="color:#c084fc">Ilimitado</span>
          </div>
          <div class="vf-plan-tagline">Sin restricciones, m&aacute;xima potencia</div>
          <div class="vf-plan-price">
            <span class="amt" style="color:#c084fc">$350</span>
            <span class="per">/mes</span>
          </div>
          <div class="vf-plan-sep"></div>
          <ul class="vf-plan-features">
            <li><span class="vfck" style="background:#c084fc20;color:#c084fc">&#10003;</span>Videos ilimitados</li>
            <li><span class="vfck" style="background:#c084fc20;color:#c084fc">&#10003;</span>Shorts ilimitados</li>
            <li><span class="vfck" style="background:#c084fc20;color:#c084fc">&#10003;</span>Audio ilimitado</li>
            <li><span class="vfck" style="background:#c084fc20;color:#c084fc">&#10003;</span>Todas las funciones Ultra</li>
            <li><span class="vfck" style="background:#c084fc20;color:#c084fc">&#10003;</span>Soporte 1 a 1 prioritario</li>
          </ul>
          <button class="vf-plan-btn unlimited-btn" id="vf-btn-unlimited" onclick="window._vfGoCheckout&&window._vfGoCheckout('unlimited')||window.open('https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e','_blank')">&#8599; Elegir Ilimitado</button>
        </div>
      </div>

    </div>
    <p style="font-family:var(--mono,'JetBrains Mono',monospace);font-size:10px;
       color:rgba(255,255,255,.22);text-align:center">
      Los pagos se procesan de forma segura a trav&eacute;s de Stripe. &nbsp;|&nbsp;
      Pago mensual cancelable cuando quieras.
    </p>
  </div>
</div>

<script>
(function(){
'use strict';

/* ─── Datos de planes (mirror del servidor) ─────────────────── */
var VF_PLANS = {
  basico:    {name:'Básico',    emoji:'🌱', price:75,  color:'#22d3a0',
    videosMonth:45,  ttsHours:30,  shortsMonth:15,  highlight:false},
  pro:       {name:'Pro',       emoji:'⚡', price:105, color:'#7c6aff',
    videosMonth:60,  ttsHours:45,  shortsMonth:25,  highlight:true},
  ultra:     {name:'Ultra',     emoji:'🔥', price:145, color:'#fbbf24',
    videosMonth:75,  ttsHours:60,  shortsMonth:35,  highlight:false},
  unlimited: {name:'Ilimitado', emoji:'♾️', price:350, color:'#c084fc',
    videosMonth:null,ttsHours:null,shortsMonth:null,highlight:false}
};
/* Alias para nombres de plan alternativos que puede tener la BD */
var VF_PLAN_ALIASES = {
  starter:'basico', basic:'basico', free:'basico',
  standard:'pro', premium:'pro', advanced:'pro',
  enterprise:'unlimited', ilimitado:'unlimited',
  business:'ultra'
};
function _vfResolvePlan(raw){
  var k = (raw||'basico').toLowerCase().trim();
  return VF_PLAN_ALIASES[k] || (VF_PLANS[k] ? k : 'basico');
}
var VF_STRIPE = {
  'basico-pro':       'https://buy.stripe.com/9B614p78h0sr7ow1iX3cc0c',
  'basico-ultra':     'https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d',
  'basico-unlimited': 'https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e',
  'pro-ultra':        'https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d',
  'pro-unlimited':    'https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e',
  'ultra-unlimited':  'https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e'
};

/* ─── Helpers ────────────────────────────────────────────────── */
var _currentPlan = 'basico';

function _charsToMin(c){
  if(!c || c < 1) return '0 min';
  var m = c / 900;
  return m < 1 ? Math.round(m * 60) + 's' : Math.floor(m) + ' min';
}
function _charsToHours(c){
  if(!c || c < 1) return '0 h';
  var h = c / 900 / 60;
  return h < 1 ? Math.round(h * 60) + ' min' : h.toFixed(1) + ' h';
}
function _pct(used, limit){
  return limit > 0 ? Math.min(100, Math.round(used/limit*100)) : 0;
}
function _barColor(pct){
  if(pct >= 90) return 'linear-gradient(90deg,#ef4444,#f87171)';
  if(pct >= 70) return 'linear-gradient(90deg,#f59e0b,#fbbf24)';
  return null; // use default
}

/* ─── Overlay open/close ─────────────────────────────────────── */
window.vfCloseOverlay = function(name){
  var el = document.getElementById('vf-overlay-'+name);
  if(!el) return;
  /* Doble mecanismo: inline style + clase CSS con !important */
  el.style.display   = 'none';
  el.style.animation = 'none';
  try{ el.classList.add('vf-overlay-closed'); }catch(e){}
  /* Restaurar scroll de la página subyacente */
  try{ document.documentElement.style.overflow = ''; document.body.style.overflow = ''; }catch(e){}
};
function _vfOpenOverlay(name){
  var el = document.getElementById('vf-overlay-'+name);
  if(!el) return;
  /* Quitar clase de cierre y reactivar animación */
  try{ el.classList.remove('vf-overlay-closed'); }catch(e){}
  el.style.animation = ''; /* eliminar override inline para que corra la animación CSS */
  void el.offsetWidth;     /* forzar reflow --> reinicia la animación */
  el.style.display = 'block';
  window.scrollTo(0,0);
}
/* vfOpenUpgrade y vfOpenSettings se definen en _vfWireButtons() más abajo
   con null-checks y manejo de errores. Placeholders hasta que _vfInitUI corra: */
window.vfOpenUpgrade  = function(){ window._vfPendingOpen='upgrade';  };
window.vfOpenSettings = function(){ window._vfPendingOpen='settings'; };

/* ─── Renderizar datos de perfil en el DOM ───────────────────── */
function _renderProfileData(d){
  var sub = document.getElementById('vf-settings-sub');
  try{
    _currentPlan = _vfResolvePlan(d.plan || 'basico');
    var plan  = VF_PLANS[_currentPlan] || VF_PLANS.basico;
    var uname = d.username || d.name || '';
    var initial = uname ? uname[0].toUpperCase() : '?';
    var colors = [
      'linear-gradient(135deg,#6c56ff,#a855f7)',
      'linear-gradient(135deg,#0ea5e9,#6366f1)',
      'linear-gradient(135deg,#f472b6,#ec4899)',
      'linear-gradient(135deg,#22d3a0,#0ea5e9)',
      'linear-gradient(135deg,#fbbf24,#f59e0b)'
    ];
    var grad = colors[initial.charCodeAt(0) % colors.length];

    var av = document.getElementById('vf-avatar');
    if(av){ av.textContent = initial; av.style.background = grad; }

    var pn = document.getElementById('vf-profile-name');
    if(pn) pn.textContent = uname || '—';

    var pe = document.getElementById('vf-profile-email');
    if(pe) pe.textContent = d.email || '—';

    var badge = document.getElementById('vf-plan-badge');
    if(badge){
      badge.textContent = (plan.emoji||'') + ' ' + plan.name;
      badge.style.background = plan.color+'22';
      badge.style.color      = plan.color;
      badge.style.border     = '1px solid '+plan.color+'44';
    }

    if(sub) sub.textContent = '';

    var vu     = d.usage  || {};
    var lim    = d.limits || {};
    var vUsed  = vu.videos    || 0;
    var sUsed  = vu.shorts    || 0;
    var tUsed  = vu.tts_chars || 0;

    var vLim   = (lim.videos_per_month  !== null && lim.videos_per_month  !== undefined)
                   ? lim.videos_per_month  : (plan.videosMonth !== null && plan.videosMonth !== undefined ? plan.videosMonth : null);
    var sLim   = (lim.shorts_per_month  !== null && lim.shorts_per_month  !== undefined)
                   ? lim.shorts_per_month  : (plan.shortsMonth !== null && plan.shortsMonth !== undefined ? plan.shortsMonth : null);
    var tLimC  = (lim.tts_chars_per_month !== null && lim.tts_chars_per_month !== undefined)
                   ? lim.tts_chars_per_month : (plan.ttsHours ? plan.ttsHours * 54000 * 60 : null);
    var tLimH  = tLimC ? Math.round(tLimC / 900 / 60) : null; /* horas/mes */

    var vPct  = (typeof vLim === 'number' && vLim > 0) ? _pct(vUsed, vLim) : 0;
    var vl    = document.getElementById('vf-usage-videos-label');
    if(vl)  vl.textContent  = vUsed + ' / ' + (vLim !== null ? vLim + ' videos/mes' : '∞');
    var vBar  = document.getElementById('vf-usage-videos-bar');
    if(vBar){ vBar.style.width = vPct+'%'; if(_barColor(vPct)) vBar.style.background=_barColor(vPct); }

    var sPct  = (typeof sLim === 'number' && sLim > 0) ? _pct(sUsed, sLim) : 0;
    var sl    = document.getElementById('vf-usage-shorts-label');
    if(sl)  sl.textContent  = sUsed + ' / ' + (sLim !== null ? sLim + ' shorts/mes' : '∞');
    var sBar  = document.getElementById('vf-usage-shorts-bar');
    if(sBar){ sBar.style.width = sPct+'%'; if(_barColor(sPct)) sBar.style.background=_barColor(sPct); }

    var tPct  = tLimC ? _pct(tUsed, tLimC) : 0;
    var tl    = document.getElementById('vf-usage-tts-label');
    if(tl)  tl.textContent  = _charsToHours(tUsed) + ' / ' + (tLimH !== null ? tLimH + ' h/mes' : '∞');
    var tBar  = document.getElementById('vf-usage-tts-bar');
    if(tBar){ tBar.style.width = tPct+'%'; if(_barColor(tPct)) tBar.style.background=_barColor(tPct); }

    var upWrap = document.getElementById('vf-settings-upgrade-wrap');
    if(upWrap) upWrap.style.display = (_currentPlan !== 'unlimited') ? 'block' : 'none';

    /* Payment dates */
    var _fmtDate = function(s){
      if(!s || s === 'None' || s === 'null' || s === '') return 'No disponible';
      try{
        var dt = new Date(s);
        if(isNaN(dt.getTime())) return s;
        return dt.toLocaleDateString('es-ES',{day:'2-digit',month:'long',year:'numeric'});
      }catch(e){ return s; }
    };
    var pay = d.payment || {};
    var paySub  = document.getElementById('vf-payment-subdate');
    var payAct  = document.getElementById('vf-payment-activated');
    var payRen  = document.getElementById('vf-payment-renewal');
    if(paySub) paySub.textContent = _fmtDate(d.subscription_date);
    if(payAct) payAct.textContent = _fmtDate(pay.activated_at || pay.created_at);
    if(payRen) payRen.textContent = _fmtDate(pay.expires_at   || pay.plan_expires_at);

    /* Payment history — lazy load */
    var hCard = document.getElementById('vf-history-card');
    var hList = document.getElementById('vf-history-list');
    if(hCard && hList && !hList.__loaded){
      hList.__loaded = true;
      fetch('/api/user/payments', {credentials:'same-origin'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(ph){
          if(!ph || !ph.payments || ph.payments.length === 0){ hCard.style.display='none'; return; }
          hCard.style.display = 'block';
          hList.innerHTML = '';
          ph.payments.forEach(function(p){
            var row = document.createElement('div');
            row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:12px;';
            var planNames = {free:'Free',basico:'Básico',pro:'Pro',ultra:'Ultra',unlimited:'Ilimitado'};
            var pName = planNames[p.plan] || p.plan;
            row.innerHTML = '<span style="color:#a0a0c0">' + _fmtDate(p.paid_at) + '</span>'
              + '<span style="color:#eeeef5;font-weight:600">' + pName + '</span>'
              + '<span style="color:#22d3a0;font-weight:700">$' + (p.amount_usd||0).toFixed(0) + '</span>';
            hList.appendChild(row);
          });
        })
        .catch(function(){ hCard.style.display='none'; });
    }
  }catch(e){
    console.error('[VF Profile render]', e);
    if(sub) sub.textContent = 'Error al mostrar perfil.';
  }
}

/* ─── Load profile — siempre fetch fresco para reflejar TTS/video actual ─ */
function _loadProfile(){
  var sub = document.getElementById('vf-settings-sub');
  /* Mostrar datos cacheados inmediatamente mientras llega el fetch */
  if(window._VF_PROFILE) _renderProfileData(window._VF_PROFILE);
  else if(sub) sub.textContent = 'Cargando perfil…';
  /* Siempre pedir datos frescos al servidor (el cache puede estar obsoleto
     si el usuario generó voz o videos durante la sesión) */
  fetch('/api/user/profile', {credentials:'same-origin'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(function(d){
      window._VF_PROFILE = d; /* actualizar cache */
      _renderProfileData(d);
    })
    .catch(function(err){
      console.error('[VF Profile]', err);
      /* Si ya mostramos cache, no sobreescribir con error */
      if(!window._VF_PROFILE && sub) sub.textContent = 'Error al cargar perfil.';
    });
}

/* ─── Render plans grid — 100% inline styles (sin dependencia de CSS) ─── */
var VF_PLAN_FEATS = {
  basico:    ['30 h audio/mes','45 videos/mes','15 shorts/mes','Imagen a video','Renderizado','Miniaturas'],
  pro:       ['45 h audio/mes','60 videos/mes','25 shorts/mes','Modelado video (YouTube)','Guión a video (1 clic)','Renderizado + Miniaturas'],
  ultra:     ['60 h audio/mes','75 videos/mes','35 shorts/mes','Editor dinámico','Soporte 1 a 1','Todas las funciones Pro'],
  unlimited: ['Audio ilimitado','Videos ilimitados','Shorts ilimitados','Todas las funciones Ultra','Soporte 1 a 1 prioritario','Sin restricciones']
};
/* Orden ascendente para determinar si es posible hacer upgrade */
var VF_PLAN_ORDER = ['free','basico','pro','ultra','unlimited'];
/* ─── Checkout: crea sesión en servidor y abre Stripe ────────── */
var VF_STRIPE_FALLBACK = {
  basico:    'https://buy.stripe.com/6oU3cx2S10sr24c4v93cc0b',
  pro:       'https://buy.stripe.com/9B614p78h0sr7ow1iX3cc0c',
  ultra:     'https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d',
  unlimited: 'https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e'
};
function _vfGoCheckout(planKey){
  var btn = document.querySelector('#vf-card-'+planKey+' .vf-plan-btn');
  var origText = btn ? btn.textContent : '';
  if(btn){ btn.textContent = 'Abriendo...'; btn.disabled = true; }

  fetch('/api/stripe/checkout?plan=' + planKey, {credentials:'same-origin'})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(btn){ btn.textContent = origText; btn.disabled = false; }
      var url = d.url || VF_STRIPE_FALLBACK[planKey];
      if(url){
        /* Guardar session_id para polling directo */
        _vfSessionId = d.session_id || null;
        window.open(url, '_blank');
        _vfStartPollUpgrade(planKey);
      }
    })
    .catch(function(){
      if(btn){ btn.textContent = origText; btn.disabled = false; }
      /* Fallback directo al Payment Link si el servidor falla */
      var fb = VF_STRIPE_FALLBACK[planKey];
      if(fb){ window.open(fb, '_blank'); _vfStartPollUpgrade(planKey); }
    });
}

/* ─── Plan-change polling after clicking upgrade ─────────────── */
var _vfPollTimer   = null;
var _vfPollTimeout = null;
var _vfSessionId   = null;   /* session_id del Checkout Session activo */
var _vfPollPlan    = null;   /* plan esperado */

function _vfStopPoll(){
  if(_vfPollTimer)   clearInterval(_vfPollTimer);
  if(_vfPollTimeout) clearTimeout(_vfPollTimeout);
  _vfPollTimer = _vfPollTimeout = null;
  _vfSessionId = null;
  _vfPollPlan  = null;
}

function _vfShowPayWaiting(planName){
  var ov = document.getElementById('vf-pay-waiting');
  if(!ov) return;
  var nm = ov.querySelector('.vf-pw-plan');
  if(nm) nm.textContent = planName;
  ov.style.display = 'flex';
}
function _vfHidePayWaiting(){
  var ov = document.getElementById('vf-pay-waiting');
  if(ov) ov.style.display = 'none';
}
function _vfShowPayOk(planName){
  var ov = document.getElementById('vf-pay-ok');
  if(!ov) return;
  var nm = ov.querySelector('.vf-pk-plan');
  if(nm) nm.textContent = planName;
  ov.style.display = 'flex';
  setTimeout(function(){
    ov.style.display = 'none';
    window.vfCloseOverlay('upgrade');
  }, 3500);
}

function _vfStartPollUpgrade(expectedPlan){
  _vfStopPoll();
  _vfPollPlan = expectedPlan;
  _vfShowPayWaiting(VF_PLANS[expectedPlan] ? VF_PLANS[expectedPlan].name : expectedPlan);

  function _onPlanActivated(planKey){
    _vfStopPoll();
    _vfHidePayWaiting();
    var resolvedPlan = _vfResolvePlan(planKey || expectedPlan);
    _currentPlan = resolvedPlan;
    _vfShowPayOk(VF_PLANS[resolvedPlan] ? VF_PLANS[resolvedPlan].name : resolvedPlan);
    _renderPlansGrid();
    /* Actualizar el popup del sidebar: _VF_PROFILE es la fuente de verdad */
    try {
      if(window._VF_PROFILE){ window._VF_PROFILE.plan = resolvedPlan; }
      if(typeof window._vfFillProfile === 'function'){ window._vfFillProfile(); }
    } catch(e){}
  }

  _vfPollTimer = setInterval(function(){
    /* Siempre verificar cambio de plan en el perfil (detecta pagos via n8n/webhook) */
    fetch('/api/user/profile', {credentials:'same-origin'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(d){
        if(!d) return;
        var newPlan = _vfResolvePlan(d.plan || 'free');
        if(newPlan !== _vfResolvePlan(_currentPlan)){
          window._VF_PROFILE = d;
          _onPlanActivated(newPlan);
        }
      }).catch(function(){});
    /* En paralelo: si tenemos session_id, verificar también con Stripe */
    if(_vfSessionId){
      var sid = _vfSessionId;
      fetch('/api/stripe/poll-session?session_id=' + encodeURIComponent(sid) + '&plan=' + _vfPollPlan,
            {credentials:'same-origin'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(d){
          if(d && d.paid){ _onPlanActivated(d.plan || _vfPollPlan); }
        }).catch(function(){});
    }
  }, 4000);

  /* Detener polling después de 15 minutos */
  _vfPollTimeout = setTimeout(function(){
    _vfStopPoll();
    _vfHidePayWaiting();
  }, 900000);
}

window._vfCancelPoll = function(){
  _vfStopPoll();
  _vfHidePayWaiting();
};

function _renderPlansGrid(){
  var curKey = _vfResolvePlan(_currentPlan);
  var curIdx = VF_PLAN_ORDER.indexOf(curKey);
  var BCLASS = {free:'free-btn',basico:'starter-btn',pro:'pro-btn',ultra:'ultra-btn',unlimited:'unlimited-btn'};
  var BNAMES = {free:'Free',basico:'Básico',pro:'Pro',ultra:'Ultra',unlimited:'Ilimitado'};
  VF_PLAN_ORDER.forEach(function(k){
    var card = document.getElementById('vf-card-' + k);
    if(!card) return;
    var btn  = card.querySelector('.vf-plan-btn');
    if(!btn) return;
    var kIdx = VF_PLAN_ORDER.indexOf(k);
    card.classList.toggle('current', k === curKey);
    if(k === curKey){
      btn.className   = 'vf-plan-btn current-plan';
      btn.textContent = '✓ Plan actual';
      btn.onclick     = null;
    } else if(k === 'free'){
      btn.className   = 'vf-plan-btn free-btn';
      btn.textContent = 'Plan gratuito';
      btn.onclick     = null;
    } else if(kIdx < curIdx){
      btn.className   = 'vf-plan-btn ' + (BCLASS[k]||'starter-btn');
      btn.innerHTML   = '&#8599; Cambiar a ' + BNAMES[k];
      (function(pk){ btn.onclick = function(){ _vfGoCheckout(pk); }; })(k);
    } else {
      btn.className   = 'vf-plan-btn ' + (BCLASS[k]||'starter-btn');
      btn.innerHTML   = '&#8599; Upgrade a ' + BNAMES[k];
      (function(pk){ btn.onclick = function(){ _vfGoCheckout(pk); }; })(k);
    }
  });
}

/* ─── Limit popup ────────────────────────────────────────────── */
window.vfShowLimitPopup = function(data){
  /* data: {title, message, used, limit, type} */
  var popup = document.getElementById('vf-limit-popup');
  if(!popup) return;
  document.getElementById('vflp-title').textContent = data.title || 'Límite alcanzado';
  document.getElementById('vflp-msg').textContent   = data.message || '';
  var pct = (data.limit > 0) ? Math.min(100, Math.round((data.used||0)/data.limit*100)) : 100;
  var bar = document.getElementById('vflp-bar');
  bar.style.width = pct + '%';
  bar.style.background = pct >= 90
    ? 'linear-gradient(90deg,#ef4444,#f87171)'
    : 'linear-gradient(90deg,#7c6aff,#f472b6)';
  popup.style.display = 'flex';
};

/* ─── Global pre-check helper (llamado antes de cada generación) ─
   Devuelve Promise<bool>. Si false, ya mostró el popup.         */
window.vfCheckLimit = function(type, amount){
  amount = amount || 1;
  return fetch('/api/usage/check', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({type: type, amount: amount})
  }).then(function(r){return r.json();})
    .then(function(d){
      if(!d.allowed){
        window.vfShowLimitPopup({
          title:   type === 'tts' ? 'Límite de voz alcanzado'
                                  : 'Límite de videos alcanzado',
          message: d.message || '',
          used:    (d.extra && d.extra.used)  || 0,
          limit:   (d.extra && d.extra.limit) || 1,
          type:    type
        });
        return false;
      }
      return true;
    }).catch(function(){return true;}); /* falla silenciosamente: el servidor lo rechazará */
};

/* ─── Add sidebar buttons ────────────────────────────────────── */
function _vfAddSidebarButtons(){
  var sb = document.querySelector('.sb');
  var footer = document.querySelector('.sb-footer');
  if(!sb || document.getElementById('vf-logout-btn')) return;

  /* SVG icons */
  var icLogout = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>';
  var icConfig = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

  /* Upgrade button */
  var btnUp = document.createElement('button');
  btnUp.id = 'vf-upgrade-btn';
  btnUp.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" style="flex-shrink:0"><polyline points="17,11 12,6 7,11"/><line x1="12" y1="6" x2="12" y2="18"/></svg>Upgrade';
  btnUp.onclick = function(){ window.vfOpenUpgrade(); };

  /* Divider */
  var div1 = document.createElement('div');
  div1.className = 'sb-div';

  /* Config button */
  var btnCfg = document.createElement('button');
  btnCfg.id = 'vf-config-btn';
  btnCfg.className = 'vf-sb-btn';
  btnCfg.innerHTML = '<span style="opacity:.6">'+icConfig+'</span>Configuración';
  btnCfg.onclick = function(){ window.vfOpenSettings(); };

  /* Divider */
  var div2 = document.createElement('div');
  div2.className = 'sb-div';

  /* Logout button */
  var btnOut = document.createElement('button');
  btnOut.id = 'vf-logout-btn';
  btnOut.className = 'vf-sb-btn';
  btnOut.innerHTML = '<span style="opacity:.5">'+icLogout+'</span>Cerrar sesión';
  btnOut.onclick = function(){
    fetch('/api/logout',{method:'POST'}).finally(function(){
      try{window.parent.postMessage({__vf:true,type:'session',loggedIn:false},'*');}catch(e){}
      window.location.href='/login';
    });
  };

  function ins(el){ if(footer){sb.insertBefore(el,footer);}else{sb.appendChild(el);} }
  ins(btnUp); ins(div1); ins(btnCfg); ins(div2); ins(btnOut);
}

/* ─── Ocultar Upgrade si el usuario es Ilimitado ──────────────── */
function _vfApplyPlanUI(){
  /* Usar datos pre-cargados si están disponibles */
  var d = window._VF_PROFILE;
  if(d){
    _currentPlan = _vfResolvePlan(d.plan || 'basico');
    var btnUp = document.getElementById('vf-upgrade-btn');
    var div1  = btnUp && btnUp.previousElementSibling;
    if(_currentPlan === 'unlimited' && btnUp){
      btnUp.style.display = 'none';
      if(div1 && div1.classList.contains('vf-sb-divider')) div1.style.display = 'none';
    }
    return;
  }
  /* Fallback fetch */
  fetch('/api/user/profile')
    .then(function(r){return r.json();})
    .then(function(d2){
      _currentPlan = _vfResolvePlan(d2.plan || 'basico');
      var btnUp = document.getElementById('vf-upgrade-btn');
      var div1  = btnUp && btnUp.previousElementSibling;
      if(_currentPlan === 'unlimited' && btnUp){
        btnUp.style.display = 'none';
        if(div1 && div1.classList.contains('vf-sb-divider')) div1.style.display = 'none';
      }
    }).catch(function(){});
}

/* ─── Inactivity timer ───────────────────────────────────────── */
/* La sesión dura hasta que la app se cierre (sin expiración por inactividad). */
/* Solo se oculta el banner de advertencia al detectar actividad. */
function _vfResetIdle(){
  var w = document.getElementById('vf-session-warn');
  if(w) w.style.display = 'none';
}
window._vfResetIdle = _vfResetIdle;
['mousedown','mousemove','keydown','scroll','touchstart','click'].forEach(function(ev){
  document.addEventListener(ev, _vfResetIdle, {passive:true});
});

/* ─── Init con retry ─────────────────────────────────────────── */
/* ─── Conectar eventos a los botones (estáticos o JS) ───────── */
function _vfWireButtons(){
  var btnUp  = document.getElementById('vf-upgrade-btn');
  var btnCfg = document.getElementById('vf-config-btn');
  var btnOut = document.getElementById('vf-logout-btn');
  if(btnUp)  btnUp.onclick  = function(){ _vfShowOverlay('upgrade'); };
  if(btnCfg) btnCfg.onclick = function(){ _vfShowOverlay('settings'); };
  if(btnOut) btnOut.onclick = function(){
    fetch('/api/logout',{method:'POST'}).finally(function(){
      try{window.parent.postMessage({__vf:true,type:'session',loggedIn:false},'*');}catch(e){}
      window.location.href='/login';
    });
  };
}
function _vfShowOverlay(name){
  try{
    if(name === 'upgrade'){
      var lp = document.getElementById('vf-limit-popup');
      if(lp) lp.style.display='none';
      _renderPlansGrid();
      _vfOpenOverlay('upgrade');
    } else {
      _vfOpenOverlay('settings');
      _loadProfile();
    }
  }catch(e){ console.error('[VF] overlay error:',e); }
}
/* Exponer para compatibilidad con otros llamadores */
window.vfOpenUpgrade  = function(){ _vfShowOverlay('upgrade');  };
window.vfOpenSettings = function(){ _vfShowOverlay('settings'); };
window.vfOpenLogout   = function(){
  fetch('/api/logout',{method:'POST'}).finally(function(){
    try{window.parent.postMessage({__vf:true,type:'session',loggedIn:false},'*');}catch(e){}
    window.location.href='/login';
  });
};

function _vfInitUI(){
  _vfAddSidebarButtons(); /* añade botones si no están en el DOM */
  _vfResetIdle();
  /* Si aún no hay botones (inyección estática no disponible), reintenta con JS */
  if(!document.getElementById('vf-logout-btn')){
    var _tries = 0;
    var _retryTimer = setInterval(function(){
      _vfAddSidebarButtons();
      if(document.getElementById('vf-logout-btn') || _tries++ > 40){
        clearInterval(_retryTimer);
        _vfWireButtons();
      }
    }, 150);
  } else {
    _vfWireButtons(); /* botones estáticos: solo conectar eventos */
  }
  _vfApplyPlanUI();
  /* Si hubo un clic antes de que el DOM estuviera listo, abrirlo ahora */
  if(window._vfPendingOpen){ _vfShowOverlay(window._vfPendingOpen); window._vfPendingOpen=null; }
}
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', _vfInitUI);
} else {
  _vfInitUI();
}

})();
</script>
"""

# ─────────────────────────────────────────────────────────────────
# BASE DE DATOS
# ─────────────────────────────────────────────────────────────────

def _get_db_connection():
    try:
        import pymysql
    except ImportError:
        raise RuntimeError("pymysql no instalado. Ejecuta: pip install pymysql")

    # Intento 1: conectar con el host configurado (IP o hostname)
    last_err = None
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception as e:
        last_err = e

    # Intento 2: fallback con IP directa del VPS
    _ip       = "5.189.149.112"
    _hostname = "vmi3378735.contaboserver.net"
    fallback_host = _ip if DB_CONFIG["host"] == _hostname else _hostname
    try:
        alt_cfg = {**DB_CONFIG, "host": fallback_host}
        conn = pymysql.connect(**alt_cfg)
        print(f"[AUTH] ⚠ Conectado via fallback host '{fallback_host}' (principal falló: {last_err})")
        return conn
    except Exception as e2:
        pass

    raise RuntimeError(f"Error conectando a la base de datos: {last_err}")


def _hash_password(password):
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = "videoforge_salt_2024_"
        return "sha256:" + hashlib.sha256((salt + password).encode()).hexdigest()


def verify_password(plain, hashed):
    try:
        if not hashed:
            return False
        if hashed.startswith("sha256:"):
            salt = "videoforge_salt_2024_"
            return hmac.compare_digest(
                hashed,
                "sha256:" + hashlib.sha256((salt + plain).encode("utf-8")).hexdigest()
            )
        # bcrypt hash ($2b$ / $2a$)
        try:
            import bcrypt as _bcrypt
            plain_bytes  = plain.encode("utf-8")
            hashed_bytes = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
            return _bcrypt.checkpw(plain_bytes, hashed_bytes)
        except ImportError:
            # bcrypt no disponible (fallback: rehash con sha256 y comparar)
            print("[AUTH] bcrypt no disponible — usando sha256 fallback", flush=True)
            salt = "videoforge_salt_2024_"
            expected = "sha256:" + hashlib.sha256((salt + plain).encode("utf-8")).hexdigest()
            return hmac.compare_digest(hashed, expected)
        except Exception as _be:
            print(f"[AUTH] bcrypt.checkpw error: {_be}", flush=True)
            return False
    except Exception as _e:
        print(f"[AUTH] verify_password error: {_e}", flush=True)
        return False


def authenticate_user(username, password):
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role, active, must_change_password "
                "FROM vf_users WHERE username = %s LIMIT 1",
                (username,)
            )
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        print(f"[AUTH] DB error: {e}")
        return None, str(e)

    if not row:
        return None, "Usuario no encontrado"

    user_id, uname, pw_hash, role, active, must_change = row

    if not active:
        return None, "Cuenta desactivada. Contacta al administrador."

    if not verify_password(password, pw_hash):
        return None, "Contraseña incorrecta"

    return {
        "id": user_id,
        "username": uname,
        "role": role,
        "must_change_password": bool(must_change)
    }, None




# ─────────────────────────────────────────────────────────────────
# INIT AUTH
# ─────────────────────────────────────────────────────────────────


def init_auth(app):
    from flask import request, redirect, make_response, jsonify, g

    app.secret_key = APP_SECRET_KEY
    _ensure_tables()   # garantiza que vf_usage exista en la BD

    # ── 1. Verificar autenticación en cada request ─────────────────
    @app.before_request
    def check_auth():
        path = request.path
        if _is_public(path):
            return None
        user = _get_current_user(request, APP_SECRET_KEY)
        if not user:
            if path.startswith("/api/"):
                return jsonify({"error": "No autenticado", "redirect": "/login"}), 401
            return redirect("/login")
        # Guardar usuario en contexto para after_request
        g._vf_user = user
        return None

    # ── 2. Renovar token (ventana deslizante) + inyectar UI + datos ──
    @app.after_request
    def after_auth(response):
        import json as _json
        user = getattr(g, "_vf_user", None)
        if user:
            # Renueva el token --> reinicia el contador de inactividad
            new_token = _make_token(user, APP_SECRET_KEY)
            response.set_cookie(
                SESSION_COOKIE, new_token,
                httponly=True, samesite="Lax", secure=False,
                max_age=SESSION_MINUTES * 60,
            )
            # Inyectar solo en respuestas HTML principales
            if "text/html" in (response.content_type or "") and response.status_code == 200:
                try:
                    html = response.get_data(as_text=True)
                    modified = False

                    # A) Inyectar overlays/JS si no están ya presentes
                    if "</body>" in html and 'id="vf-logout-btn"' not in html:
                        html = html.replace("</body>", _INJECT_HTML + "</body>", 1)
                        modified = True

                    # B) Inyectar datos de perfil como window._VF_PROFILE (siempre)
                    #    Sentinel: 'vf-profile-data' — id único del script tag de datos
                    if "</head>" in html and 'id="vf-profile-data"' not in html:
                        try:
                            _u = _get_user_full(user)
                            if _u:
                                _pkey = normalize_plan_key(_u["plan"])
                                _plan = PLANS[_pkey]
                                _usg  = get_today_usage(_u["id"])
                                _prof = {
                                    "username": _u["username"],
                                    "email":    _u["email"],
                                    "plan":     _pkey,
                                    "plan_name": _plan["name"],
                                    "usage": {
                                        "videos":    _usg["videos"],
                                        "tts_chars": _usg["tts_chars"],
                                    },
                                    "limits": {
                                        "videos_per_day":    _plan.get("videos_per_day"),
                                        "tts_chars_per_day": _plan.get("tts_chars_per_day"),
                                        "max_video_minutes": _plan.get("max_video_minutes"),
                                    },
                                    "payment": {
                                        "activated_at": _u.get("created_at"),
                                        "expires_at":   _u.get("plan_expires_at"),
                                    },
                                }
                                _tag = ('<script id="vf-profile-data">window._VF_PROFILE='
                                        + _json.dumps(_prof, ensure_ascii=False)
                                        + ';</script>')
                                html = html.replace("</head>", _tag + "\n</head>", 1)
                                modified = True
                        except Exception as _pe:
                            print(f"[AUTH] profile inject ERROR: {_pe}")

                    if modified:
                        enc = html.encode("utf-8")
                        response.set_data(enc)
                        response.headers["Content-Length"] = len(enc)
                        import sys as _sys
                        print(f"[AUTH] HTML modificado: _VF_PROFILE inyectado OK", flush=True)
                except Exception:
                    pass
        return response

    # ── Rutas públicas ─────────────────────────────────────────────
    @app.route("/login")
    def login_page():
        if _get_current_user(request, APP_SECRET_KEY):
            return redirect("/")
        # Si viene de expiración, mostrar mensaje
        expired = request.args.get("expired")
        if expired:
            html = LOGIN_HTML.replace(
                'id="msg"',
                'id="msg" class="msg warn show"',
                1,
            ).replace(
                '</div>\n<div class="sep">',
                "Sesi&oacute;n expirada por inactividad. Ingresa nuevamente.</div>\n<div class=\"sep\">",
                1,
            )
            return html
        return LOGIN_HTML

    @app.route("/api/login", methods=["POST"])
    def api_login():
        ip = _get_client_ip(request)
        locked, secs = _is_locked_out(ip)
        if locked:
            mins = secs // 60
            return jsonify({"ok": False, "lockout": True,
                            "error": f"Demasiados intentos. Espera {mins}m {secs%60}s."}), 429

        data = request.get_json(force=True) or {}
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "")

        if not username or not password:
            return jsonify({"ok": False, "error": "Usuario y contraseña requeridos"}), 400

        user, err = authenticate_user(username, password)

        if not user:
            _register_fail(ip)
            locked2, secs2 = _is_locked_out(ip)
            if locked2:
                mins = secs2 // 60
                return jsonify({"ok": False, "lockout": True,
                                "error": f"Cuenta bloqueada por {mins}m {secs2%60}s."}), 429
            return jsonify({"ok": False, "error": err or "Credenciales incorrectas"}), 401

        _clear_fails(ip)

        if user.get("must_change_password"):
            return jsonify({"ok": True, "must_change_password": True, "user": user["username"]})

        token = _make_token(user["username"], APP_SECRET_KEY)
        resp = make_response(jsonify({"ok": True, "user": user["username"]}))
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="Lax",
                        secure=False, max_age=SESSION_MINUTES * 60)
        return resp

    @app.route("/api/change-password", methods=["POST"])
    def api_change_password():
        data = request.get_json(force=True) or {}
        username     = (data.get("username") or "").strip()
        new_password = (data.get("new_password") or "")

        if not username or not new_password:
            return jsonify({"ok": False, "error": "Datos incompletos"}), 400
        if len(new_password) < 8:
            return jsonify({"ok": False, "error": "Mínimo 8 caracteres"}), 400
        if new_password == "1234":
            return jsonify({"ok": False, "error": "No puedes usar la contraseña temporal"}), 400

        try:
            new_hash = _hash_password(new_password)
            conn = _get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE vf_users SET password_hash=%s, must_change_password=0 "
                    "WHERE username=%s AND must_change_password=1",
                    (new_hash, username)
                )
                affected = cur.rowcount
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[AUTH] change-password error: {e}")
            return jsonify({"ok": False, "error": "Error interno al actualizar"}), 500

        if affected == 0:
            return jsonify({"ok": False, "error": "Usuario no encontrado o ya completó el cambio"}), 404

        token = _make_token(username, APP_SECRET_KEY)
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="Lax",
                        secure=False, max_age=SESSION_MINUTES * 60)
        return resp

    @app.route("/api/logout", methods=["POST", "GET"])
    def api_logout():
        resp = make_response(redirect("/login"))
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @app.route("/api/register", methods=["POST"])
    def api_register():
        import re as _re
        data     = request.get_json(force=True) or {}
        username = (data.get("username") or "").strip()
        email    = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "")
        plan     = normalize_plan_key(data.get("plan") or "basico")

        # ── Validar campos ─────────────────────────────────────
        if not username or not email or not password:
            return jsonify({"ok": False, "error": "Todos los campos son requeridos"}), 400
        if not _re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
            return jsonify({"ok": False, "error": "Usuario: 3-20 caracteres (letras, números y _)"}), 400
        if '@' not in email or '.' not in email.split('@')[-1]:
            return jsonify({"ok": False, "error": "Correo electrónico inválido"}), 400
        if len(password) < 8:
            return jsonify({"ok": False, "error": "La contraseña debe tener al menos 8 caracteres"}), 400

        try:
            conn = _get_db_connection()
            # Verificar si ya existe el usuario o email
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM vf_users WHERE username=%s LIMIT 1", (username,))
                if cur.fetchone():
                    conn.close()
                    return jsonify({"ok": False, "error": "Este nombre de usuario ya está en uso"}), 409
                cur.execute("SELECT id FROM vf_users WHERE user_mail=%s LIMIT 1", (email,))
                if cur.fetchone():
                    conn.close()
                    return jsonify({"ok": False, "error": "Este correo ya está registrado"}), 409
            # Crear usuario
            pw_hash = _hash_password(password)
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO vf_users "
                    "(username, password_hash, role, active, must_change_password, user_mail, plan, user_type) "
                    "VALUES (%s, %s, 'user', 1, 0, %s, %s, 'standard')",
                    (username, pw_hash, email, plan)
                )
            conn.commit()
            conn.close()
            print(f"[AUTH] Nuevo usuario registrado: {username}, plan={plan}, email={email}", flush=True)
        except Exception as e:
            print(f"[AUTH] register error: {e}", flush=True)
            return jsonify({"ok": False, "error": "Error interno al registrar. Intenta de nuevo."}), 500

        # Auto-login: emitir cookie de sesión
        token = _make_token(username, APP_SECRET_KEY)
        resp  = make_response(jsonify({"ok": True, "user": username}))
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="Lax",
                        secure=False, max_age=SESSION_MINUTES * 60)
        return resp

    @app.route("/api/auth/me")
    def api_me():
        user = _get_current_user(request, APP_SECRET_KEY)
        if not user:
            return jsonify({"authenticated": False}), 401
        return jsonify({"authenticated": True, "username": user})

    # ── Planes y uso ──────────────────────────────────────────────

    @app.route("/api/user/profile")
    def api_user_profile():
        """Devuelve perfil completo: username, email, plan, uso mensual, historial."""
        username = _get_current_user(request, APP_SECRET_KEY)
        if not username:
            return jsonify({"error": "No autenticado"}), 401
        user = _get_user_full(username)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        usage    = get_month_usage(user["id"])
        plan_key = normalize_plan_key(user["plan"])
        plan     = PLANS[plan_key]

        sub_date = user.get("subscription_date")
        if sub_date and hasattr(sub_date, "strftime"):
            sub_date = sub_date.strftime("%Y-%m-%d")

        return jsonify({
            "username":  user["username"],
            "email":     user["email"],
            "plan":      plan_key,
            "plan_name": plan["name"],
            "subscription_date": sub_date,
            "usage": {
                "videos":    usage["videos"],
                "tts_chars": usage["tts_chars"],
                "shorts":    usage["shorts"],
            },
            "limits": {
                "videos_per_month":    plan["videos_per_month"],
                "tts_chars_per_month": plan["tts_chars_per_month"],
                "audio_hours_per_month": plan["audio_hours_per_month"],
                "shorts_per_month":    plan["shorts_per_month"],
                "max_video_minutes":   plan["max_video_minutes"],
                # compatibilidad con código viejo
                "videos_per_day":      plan.get("videos_per_day"),
                "tts_chars_per_day":   plan["tts_chars_per_day"],
            },
            "payment": {
                "activated_at": str(user.get("created_at", "")),
                "expires_at":   str(user.get("plan_expires_at", "") or ""),
            },
        })

    @app.route("/api/user/payments")
    def api_user_payments():
        """Historial de pagos del usuario actual desde vf_stripe_payments."""
        username = _get_current_user(request, APP_SECRET_KEY)
        if not username:
            return jsonify({"error": "No autenticado"}), 401
        try:
            conn = _get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT plan, amount_usd, paid_at, stripe_session_id "
                    "FROM vf_stripe_payments "
                    "WHERE username=%s ORDER BY paid_at DESC LIMIT 20",
                    (username,),
                )
                rows = cur.fetchall()
            conn.close()
            payments = []
            for r in rows:
                paid_at = r[2]
                if hasattr(paid_at, "strftime"):
                    paid_at = paid_at.strftime("%Y-%m-%d %H:%M")
                payments.append({
                    "plan":       r[0],
                    "amount_usd": float(r[1]) if r[1] else 0,
                    "paid_at":    str(paid_at),
                    "session_id": r[3],
                })
            return jsonify({"payments": payments})
        except Exception as e:
            print(f"[AUTH] api_user_payments error: {e}")
            return jsonify({"payments": []})

    @app.route("/api/plans")
    def api_plans():
        """Lista todos los planes disponibles (sin info sensible)."""
        out = []
        for key, p in PLANS.items():
            tts_day = p.get("tts_chars_per_day")
            out.append({
                "id":                  key,
                "name":                p["name"],
                "emoji":               p["emoji"],
                "price_usd":           p["price_usd"],
                "videos_per_day":      p.get("videos_per_day"),
                "videos_per_month":    p.get("videos_per_month"),
                "audio_hours_per_month": p.get("audio_hours_per_month"),
                "shorts_per_month":    p.get("shorts_per_month"),
                "tts_mins_per_day":    (tts_day // 900) if tts_day else None,
                "max_video_minutes":   p["max_video_minutes"],
                "highlight":           p.get("highlight", False),
            })
        return jsonify(out)

    @app.route("/api/stripe/checkout", methods=["POST", "GET"])
    def api_stripe_checkout():
        """
        Crea una Stripe Checkout Session y retorna la URL.
        Params: plan (basico|pro|ultra|unlimited)
        El success_url incluye session_id para verificación.
        """
        username = _get_current_user(request, APP_SECRET_KEY)
        if not username:
            return jsonify({"error": "No autenticado"}), 401

        plan_param = (request.args.get("plan") or (request.get_json(force=True) or {}).get("plan") or "").lower().strip()
        plan_key   = normalize_plan_key(plan_param) if plan_param else None
        if not plan_key or plan_key not in PLANS:
            return jsonify({"error": "Plan inválido"}), 400

        # Fallback: si no hay Stripe key, redirigir al Payment Link
        if not STRIPE_SECRET_KEY:
            return jsonify({"url": STRIPE_PAYMENT_LINKS.get(plan_key, ""), "fallback": True})

        try:
            import stripe as _stripe
            _stripe.api_key = STRIPE_SECRET_KEY
            price_info = STRIPE_PRICES[plan_key]
            user_info  = _get_user_full(username) or {}

            # Si el plan tiene product_id, buscar el precio activo en Stripe
            # para no duplicar productos en la cuenta
            price_id   = None
            product_id = price_info.get("product_id")
            if product_id:
                try:
                    prices = _stripe.Price.list(product=product_id, active=True,
                                                recurring={"interval": "month"}, limit=1)
                    if prices.data:
                        price_id = prices.data[0].id
                except Exception as _pe:
                    print(f"[STRIPE] No se pudo obtener precio del producto {product_id}: {_pe}")

            line_item = (
                {"price": price_id, "quantity": 1}
                if price_id else
                {"price_data": {
                    "currency":     "usd",
                    "product_data": {"name": price_info["name"]},
                    "unit_amount":  price_info["amount"],
                    "recurring":    {"interval": "month"},
                }, "quantity": 1}
            )

            session = _stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[line_item],
                mode="subscription",
                success_url=(
                    "http://localhost:8080/stripe-success"
                    "?session_id={CHECKOUT_SESSION_ID}&plan=" + plan_key
                ),
                cancel_url="http://localhost:8080/",
                customer_email=user_info.get("email") or None,
                metadata={"username": username, "plan": plan_key},
            )
            return jsonify({"url": session.url, "session_id": session.id})
        except Exception as e:
            print(f"[STRIPE] checkout error: {e}")
            # Fallback al Payment Link existente
            return jsonify({"url": STRIPE_PAYMENT_LINKS.get(plan_key, ""), "fallback": True, "error": str(e)})

    @app.route("/api/stripe/poll-session", methods=["GET"])
    def api_stripe_poll_session():
        """
        El frontend llama esto cada N segundos con el session_id.
        Verifica con Stripe si el pago completó y, si es así, actualiza el plan.
        Retorna {paid: bool, plan: str|null}
        """
        session_id = request.args.get("session_id", "").strip()
        username   = _get_current_user(request, APP_SECRET_KEY)
        if not session_id:
            return jsonify({"paid": False, "error": "Sin session_id"}), 400
        if not username:
            return jsonify({"paid": False, "error": "No autenticado"}), 401

        result = _verify_stripe_session(session_id)
        if not result or not result.get("paid"):
            return jsonify({"paid": False})

        plan_meta = result.get("plan")
        plan_url  = request.args.get("plan", "").lower().strip()
        plan_key  = normalize_plan_key(plan_meta or plan_url) if (plan_meta or plan_url) else None

        if plan_key and plan_key in PLANS:
            _update_user_plan(username, plan_key, session_id)
            return jsonify({"paid": True, "plan": plan_key})

        return jsonify({"paid": True, "plan": None})

    @app.route("/stripe-success")
    def stripe_success():
        """
        Stripe redirige aquí después de completar el pago.
        Verifica la sesión con la API de Stripe y actualiza el plan automáticamente.
        """
        session_id = request.args.get("session_id", "").strip()
        plan_param = request.args.get("plan", "").lower().strip()

        # Intentar obtener usuario autenticado (mismo navegador = misma cookie)
        username = _get_current_user(request, APP_SECRET_KEY)

        verified   = False
        plan_key   = None
        error_msg  = None

        if session_id and STRIPE_SECRET_KEY:
            result = _verify_stripe_session(session_id)
            if result and result["paid"]:
                verified = True
                # Plan: preferir metadata de la sesión, luego URL param
                meta_plan = result.get("plan")
                plan_key  = normalize_plan_key(meta_plan or plan_param) if (meta_plan or plan_param) else None

                # Si no tenemos username por cookie, buscar por email de Stripe
                if not username and result.get("customer_email"):
                    try:
                        conn = _get_db_connection()
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT username FROM vf_users WHERE user_mail=%s OR email=%s LIMIT 1",
                                (result["customer_email"], result["customer_email"])
                            )
                            row = cur.fetchone()
                        conn.close()
                        if row:
                            username = row[0]
                    except Exception:
                        pass

                # Actualizar plan en BD
                if username and plan_key:
                    _update_user_plan(username, plan_key, session_id)
                else:
                    error_msg = "No se pudo identificar el usuario. El plan se activará manualmente."
            else:
                error_msg = "El pago no fue confirmado por Stripe."
        else:
            error_msg = "Sesión inválida o clave Stripe no configurada."

        plan_name  = PLANS[plan_key]["name"] if plan_key and plan_key in PLANS else "nuevo"
        color      = PLANS[plan_key]["color"] if plan_key and plan_key in PLANS else "#22d3a0"
        is_success = verified and not error_msg

        status_html = (
            f'<h1>&#161;Plan <span style="color:{color}">{plan_name}</span> activado!</h1>'
            f'<p>Tu cuenta ya tiene acceso a todas las funciones del plan <strong>{plan_name}</strong>.'
            f'<br>Esta pesta&ntilde;a se cerrar&aacute; en 5 segundos.</p>'
        ) if is_success else (
            f'<h1 style="color:#fbbf24">Pago recibido</h1>'
            f'<p style="color:rgba(255,255,255,.5)">{error_msg or "Contacta soporte si el plan no se activa."}</p>'
        )

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Pago completado — Studio IVR</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#06060e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#eef2ff}}
.card{{text-align:center;padding:52px 44px;background:rgba(255,255,255,.04);
  border:1px solid {color}44;border-radius:24px;max-width:440px;
  box-shadow:0 0 80px {color}15;animation:fadeIn .4s ease}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(14px)}}to{{opacity:1;transform:none}}}}
.icon{{font-size:58px;margin-bottom:22px}}
h1{{font-size:26px;font-weight:800;margin-bottom:12px;line-height:1.2}}
p{{font-size:14px;color:rgba(255,255,255,.5);line-height:1.6;margin-bottom:28px}}
.btn{{display:inline-block;padding:13px 28px;border-radius:12px;border:none;cursor:pointer;
  background:linear-gradient(135deg,{color},{color}99);color:#fff;
  font-size:13px;font-weight:700;letter-spacing:.04em;text-decoration:none;
  box-shadow:0 6px 24px {color}44}}
.note{{margin-top:20px;font-size:10px;color:rgba(255,255,255,.18);font-family:monospace;letter-spacing:.05em}}
.countdown{{display:inline-block;font-size:11px;color:rgba(255,255,255,.3);margin-top:14px;font-family:monospace}}
</style>
</head>
<body>
<div class="card">
  <div class="icon">{'&#127881;' if is_success else '&#9200;'}</div>
  {status_html}
  <a class="btn" href="http://localhost:8080/" onclick="window.close();return false;">
    Volver al app
  </a>
  {'<div class="countdown" id="cd">Cerrando en 5s...</div>' if is_success else ''}
  <p class="note">Studio IVR &mdash; Pago procesado por Stripe</p>
</div>
<script>
{'var s=5;var t=setInterval(function(){s--;document.getElementById("cd").textContent="Cerrando en "+s+"s...";if(s<=0){clearInterval(t);try{window.close();}catch(e){}}},1000);' if is_success else ''}
</script>
</body>
</html>""", 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/usage/check", methods=["POST"])
    def api_usage_check():
        """
        Verifica si el usuario puede realizar la acción.
        Body: {type: 'video'|'tts', amount: int}
        ⚠ Consulta la BD — no confíes solo en el cliente.
        """
        username = _get_current_user(request, APP_SECRET_KEY)
        if not username:
            return jsonify({"allowed": False, "message": "No autenticado"}), 401
        data  = request.get_json(force=True) or {}
        ctype = data.get("type", "video")
        amt   = int(data.get("amount", 1))
        allowed, msg, extra = check_limit(username, ctype, amt)
        return jsonify({"allowed": allowed, "message": msg, "extra": extra})

    @app.route("/api/usage/record", methods=["POST"])
    def api_usage_record():
        """
        Registra uso completado.
        Body: {videos: int, tts_chars: int}
        Solo acepta valores positivos y razonables.
        """
        username = _get_current_user(request, APP_SECRET_KEY)
        if not username:
            return jsonify({"ok": False, "error": "No autenticado"}), 401
        user = _get_user_full(username)
        if not user:
            return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404
        data      = request.get_json(force=True) or {}
        videos    = max(0, min(int(data.get("videos", 0)),    10))
        tts_chars = max(0, min(int(data.get("tts_chars", 0)), 500_000))
        ok = record_usage(user["id"], videos=videos, tts_chars=tts_chars)
        return jsonify({"ok": ok})

    print("[AUTH] Sistema de autenticacion registrado "
          "(SESSION_MINUTES=40, boot-epoch activo, planes Starter/Pro/Ultra).")

# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def crear_usuario_cli(username, password, role="user"):
    pw_hash = _hash_password(password)
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vf_users (username, password_hash, role, active, must_change_password) "
                "VALUES (%s, %s, %s, 1, 0)",
                (username, pw_hash, role)
            )
        conn.commit()
        conn.close()
        print(f"[OK] Usuario '{username}' creado con rol '{role}'.")
    except Exception as e:
        print(f"[ERROR] Error al crear usuario: {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "crear_usuario":
        crear_usuario_cli(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "user")
    else:
        print("Uso: python auth_module.py crear_usuario <username> <password> [role]")
