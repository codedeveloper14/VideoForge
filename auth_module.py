"""
VideoForge — Módulo de Autenticación  v2.1
==========================================
Cambios en esta versión:
  ✅  SESSION_MINUTES = 40   — sesión deslizante (se renueva con cada request)
  ✅  _SERVER_BOOT           — invalida TODAS las sesiones al reiniciar el servidor
  ✅  Botón "Cerrar sesión"  — inyectado automáticamente en la barra lateral
  ✅  Toast de advertencia   — aparece 5 min antes de expirar por inactividad

Dependencias:
    pip install pymysql bcrypt flask

Integración en launcher.py (igual que antes):
    from auth_module import init_auth
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
# CONFIGURACIÓN  ← Editar aquí con tus datos de Hostinger
# ─────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     "us-bos-web1915.main-hosting.eu",
    "user":     "u433942558_root",
    "password": "Lumora2025",
    "database": "u433942558_videoforge",
    "port":     3306,
    "connect_timeout": 10,
    "charset":  "utf8mb4",
}

APP_SECRET_KEY      = "Videoforgepassa34432fsdsdfs"
SESSION_MINUTES     = 40          # ← inactividad máxima (minutos)
PUBLIC_ROUTES       = {"/api/login", "/login", "/api/change-password", "/favicon.ico", "/api/logout"}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS     = 300

# ─────────────────────────────────────────────────────────────────
# BOOT EPOCH  — invalida TODAS las sesiones previas al reiniciar
# ─────────────────────────────────────────────────────────────────
_SERVER_BOOT = int(time.time())
# Cada vez que el proceso arranca, _SERVER_BOOT cambia.
# Los tokens incluyen este valor; si no coincide → sesión inválida → re-login.
print(f"[AUTH] 🔑 SERVER_BOOT={_SERVER_BOOT}  — sesiones anteriores invalidadas.")


# ─────────────────────────────────────────────────────────────────
# HTML DE LOGIN — diseño premium VideoForge
# ─────────────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>VideoForge — Acceso</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --c1:#7c6aff;--c2:#a78bfa;--c3:#f472b6;--c5:#22d3a0;--c4:#fbbf24;
  --bg:#06060d;--s:#0d0d1a;--p:#111121;--b:#1a1a2e;--b2:#232336;
  --t:#eeeef5;--m:#606080;--m2:#383852;
  --mono:'JetBrains Mono',monospace;
}
html,body{height:100%;background:var(--bg);color:var(--t);font-family:'Syne',sans-serif;overflow:hidden}
body::after{content:'';position:fixed;inset:0;pointer-events:none;z-index:9000;opacity:.025;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
.scene{position:fixed;inset:0;overflow:hidden}
.orb{position:absolute;border-radius:50%;filter:blur(100px);animation:float 12s ease-in-out infinite alternate}
.o1{width:900px;height:900px;background:radial-gradient(circle,rgba(124,106,255,.18),transparent 60%);top:-35%;left:-20%}
.o2{width:700px;height:700px;background:radial-gradient(circle,rgba(244,114,182,.10),transparent 60%);top:-10%;right:-20%;animation-delay:-4s}
.o3{width:600px;height:600px;background:radial-gradient(circle,rgba(34,211,160,.09),transparent 60%);bottom:-30%;left:25%;animation-delay:-7s}
.o4{width:400px;height:400px;background:radial-gradient(circle,rgba(251,191,36,.07),transparent 60%);bottom:10%;right:10%;animation-delay:-2s}
@keyframes float{0%{transform:translate(0,0) scale(1)}100%{transform:translate(40px,30px) scale(1.08)}}
.grid{position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(255,255,255,.015) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.015) 1px,transparent 1px);background-size:56px 56px;-webkit-mask-image:radial-gradient(ellipse 90% 80% at 50% 50%,black 30%,transparent 100%);mask-image:radial-gradient(ellipse 90% 80% at 50% 50%,black 30%,transparent 100%)}
.wrap{position:relative;z-index:10;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.card{width:100%;max-width:400px;background:rgba(17,17,33,.82);border:1px solid rgba(255,255,255,.07);border-radius:24px;padding:40px 36px 36px;backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);box-shadow:0 0 0 1px rgba(124,106,255,.08),0 32px 80px rgba(0,0,0,.7),0 0 120px rgba(124,106,255,.05);animation:pop .4s cubic-bezier(.22,1,.36,1);position:relative}
.card::before{content:'';position:absolute;top:0;left:10%;right:10%;height:1px;background:linear-gradient(90deg,transparent,rgba(167,139,250,.6),transparent);border-radius:50%}
@keyframes pop{from{opacity:0;transform:translateY(20px) scale(.97)}to{opacity:1;transform:none}}
.logo{display:flex;align-items:center;gap:14px;margin-bottom:36px;justify-content:center}
.lmark{width:44px;height:44px;border-radius:13px;flex-shrink:0;background:linear-gradient(145deg,#5b45e8 0%,#8b5cf6 50%,#a855f7 100%);display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 1px rgba(168,85,247,.25),0 6px 24px rgba(124,106,255,.5),0 0 40px rgba(124,106,255,.15);position:relative;overflow:hidden}
.lmark::before{content:'';position:absolute;top:-40%;left:-10%;width:60%;height:90%;background:linear-gradient(140deg,rgba(255,255,255,.22),transparent);transform:rotate(-15deg);border-radius:50%}
.lmark svg{width:18px;height:18px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;position:relative;z-index:1}
.ltext{display:flex;flex-direction:column;gap:3px}
.lname{font-size:20px;font-weight:800;letter-spacing:-.6px;color:var(--t);line-height:1}
.lsub{font-family:var(--mono);font-size:9px;color:rgba(167,139,250,.7);letter-spacing:.14em;text-transform:uppercase}
.heading{font-size:24px;font-weight:800;letter-spacing:-.6px;margin-bottom:6px;text-align:center;line-height:1.2}
.heading .grad{background:linear-gradient(110deg,var(--t) 30%,var(--c2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.subheading{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,.35);text-align:center;margin-bottom:30px;line-height:1.7}
.sep{height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.06),transparent);margin-bottom:24px}
.field{margin-bottom:14px}
.field label{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:9px;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:.12em;margin-bottom:7px}
.fico{width:11px;height:11px;opacity:.5}
.field input{width:100%;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:11px;padding:12px 40px 12px 14px;color:var(--t);font-family:'Syne',sans-serif;font-size:14px;font-weight:600;outline:none;transition:border-color .2s,box-shadow .2s,background .2s;letter-spacing:-.2px}
.field input:focus{border-color:rgba(124,106,255,.5);background:rgba(124,106,255,.04);box-shadow:0 0 0 3px rgba(124,106,255,.08)}
.field input::placeholder{color:rgba(255,255,255,.2);font-weight:400}
.pw-wrap{position:relative}
.pw-toggle{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:rgba(255,255,255,.3);font-size:13px;padding:4px;transition:color .15s;line-height:1}
.pw-toggle:hover{color:rgba(255,255,255,.6)}
.btn{width:100%;padding:14px;border-radius:12px;border:none;cursor:pointer;background:linear-gradient(135deg,#6c56ff 0%,#9f7aea 100%);color:#fff;font-family:var(--mono);font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;box-shadow:0 4px 20px rgba(124,106,255,.4),0 0 40px rgba(124,106,255,.1);transition:all .22s;margin-top:6px;position:relative;overflow:hidden}
.btn::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,.12),transparent);opacity:0;transition:opacity .22s}
.btn:hover::before{opacity:1}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(124,106,255,.55),0 0 60px rgba(124,106,255,.15)}
.btn:active{transform:none}
.btn:disabled{opacity:.45;cursor:not-allowed;transform:none;box-shadow:none}
.msg{display:none;padding:11px 14px;border-radius:10px;font-family:var(--mono);font-size:11px;margin-bottom:16px;line-height:1.55}
.msg.err{background:rgba(255,60,80,.08);border:1px solid rgba(255,60,80,.2);color:#ff6677}
.msg.warn{background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.2);color:#fbbf24}
.msg.ok{background:rgba(34,211,160,.08);border:1px solid rgba(34,211,160,.2);color:#22d3a0}
.msg.show{display:block}
.ldots{display:none;gap:4px;align-items:center;justify-content:center}
.ldots.show{display:flex}
.ld{width:5px;height:5px;border-radius:50%;background:rgba(255,255,255,.75);animation:ld .9s ease-in-out infinite}
.ld:nth-child(2){animation-delay:.15s}
.ld:nth-child(3){animation-delay:.30s}
@keyframes ld{0%,80%,100%{transform:scale(.45);opacity:.35}40%{transform:scale(1);opacity:1}}
.foot{margin-top:22px;padding-top:16px;border-top:1px solid rgba(255,255,255,.04);font-family:var(--mono);font-size:9px;color:rgba(255,255,255,.2);text-align:center;line-height:1.8}
.sdot{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--c5);box-shadow:0 0 6px var(--c5);margin-right:5px;vertical-align:middle;animation:sp 2.5s ease-in-out infinite}
@keyframes sp{0%,100%{opacity:.4;transform:scale(.8)}50%{opacity:1;transform:scale(1.2)}}

/* MODAL cambio de contraseña */
.overlay{display:none;position:fixed;inset:0;z-index:500;background:rgba(0,0,0,.75);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);align-items:center;justify-content:center;padding:20px}
.overlay.show{display:flex}
.modal{width:100%;max-width:380px;background:rgba(18,18,32,.96);border:1px solid rgba(255,255,255,.09);border-radius:22px;padding:36px 32px;box-shadow:0 0 0 1px rgba(124,106,255,.1),0 40px 100px rgba(0,0,0,.8);animation:pop .35s cubic-bezier(.22,1,.36,1);position:relative}
.modal::before{content:'';position:absolute;top:0;left:15%;right:15%;height:1px;background:linear-gradient(90deg,transparent,rgba(251,191,36,.5),transparent)}
.modal-icon{width:54px;height:54px;border-radius:15px;background:linear-gradient(135deg,rgba(251,191,36,.15),rgba(251,191,36,.05));border:1px solid rgba(251,191,36,.25);display:flex;align-items:center;justify-content:center;font-size:22px;margin:0 auto 20px}
.modal-title{font-size:20px;font-weight:800;letter-spacing:-.4px;text-align:center;margin-bottom:6px}
.modal-sub{font-family:var(--mono);font-size:10.5px;color:rgba(255,255,255,.35);text-align:center;margin-bottom:24px;line-height:1.65}
.modal-sep{height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.06),transparent);margin-bottom:20px}
.req{display:flex;flex-direction:column;gap:5px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:12px 14px;margin-bottom:16px}
.req-item{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10px;color:rgba(255,255,255,.3);transition:color .2s}
.req-item.ok{color:var(--c5)}
.req-item.ok .ricon{color:var(--c5)}
.ricon{font-size:11px;width:14px;text-align:center}
.match-hint{font-family:var(--mono);font-size:10px;margin-top:5px;margin-left:2px;transition:color .2s;color:rgba(255,255,255,.3)}
.match-hint.ok{color:var(--c5)}
.match-hint.err{color:#ff6677}
.btn-change{width:100%;padding:13px;border-radius:11px;border:none;cursor:pointer;background:linear-gradient(135deg,#c58f1e,#fbbf24);color:#000;font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;box-shadow:0 4px 20px rgba(251,191,36,.3);transition:all .22s;margin-top:4px}
.btn-change:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(251,191,36,.45)}
.btn-change:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}
</style>
</head>
<body>
<div class="scene">
  <div class="orb o1"></div><div class="orb o2"></div>
  <div class="orb o3"></div><div class="orb o4"></div>
</div>
<div class="grid"></div>

<div class="wrap">
  <div class="card">
    <div class="logo">
      <div class="lmark">
        <svg viewBox="0 0 24 24">
          <rect x="2" y="4" width="4" height="16" rx="1" fill="rgba(255,255,255,.25)"/>
          <rect x="2.5" y="6" width="3" height="2" rx=".5" fill="rgba(255,255,255,.65)"/>
          <rect x="2.5" y="11" width="3" height="2" rx=".5" fill="rgba(255,255,255,.65)"/>
          <rect x="2.5" y="16" width="3" height="2" rx=".5" fill="rgba(255,255,255,.65)"/>
          <path d="M9 8.5L18.5 12 9 15.5V8.5Z" fill="white"/>
        </svg>
      </div>
      <div class="ltext">
        <span class="lname">VideoForge</span>
        <span class="lsub">AI Pipeline</span>
      </div>
    </div>

    <h1 class="heading"><span class="grad">Bienvenido</span></h1>
    <p class="subheading">Ingresa tus credenciales para acceder<br>al panel de producción.</p>
    <div class="sep"></div>

    <div class="msg err"  id="errMsg"></div>
    <div class="msg warn" id="warnMsg"></div>

    <div class="field">
      <label>
        <svg class="fico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        Usuario
      </label>
      <input type="text" id="uInput" placeholder="tu_usuario" autocomplete="username" autocapitalize="off" spellcheck="false">
    </div>
    <div class="field">
      <label>
        <svg class="fico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        Contraseña
      </label>
      <div class="pw-wrap">
        <input type="password" id="pInput" placeholder="••••••••" autocomplete="current-password">
        <button class="pw-toggle" onclick="togglePw('pInput',this)" type="button">👁</button>
      </div>
    </div>

    <button class="btn" id="loginBtn" onclick="doLogin()">
      <span id="btnTxt">Ingresar al sistema →</span>
      <span class="ldots" id="ldots"><span class="ld"></span><span class="ld"></span><span class="ld"></span></span>
    </button>

    <div class="foot"><span class="sdot"></span>Servidor activo · Conexión segura</div>
  </div>
</div>

<!-- MODAL: cambio de contraseña obligatorio -->
<div class="overlay" id="cpOverlay">
  <div class="modal">
    <div class="modal-icon">🔐</div>
    <div class="modal-title">Cambia tu contraseña</div>
    <p class="modal-sub">Es tu primer acceso. Por seguridad<br>debes establecer una contraseña nueva.</p>
    <div class="modal-sep"></div>

    <div class="msg err" id="cpErr"></div>
    <div class="msg ok"  id="cpOk"></div>

    <div class="req">
      <div class="req-item" id="req-len"><span class="ricon">○</span> Mínimo 8 caracteres</div>
      <div class="req-item" id="req-num"><span class="ricon">○</span> Al menos un número</div>
      <div class="req-item" id="req-up"><span class="ricon">○</span> Al menos una mayúscula</div>
    </div>

    <div class="field">
      <label>Nueva contraseña</label>
      <div class="pw-wrap">
        <input type="password" id="np1" placeholder="Nueva contraseña" oninput="checkReqs()" autocomplete="new-password">
        <button class="pw-toggle" onclick="togglePw('np1',this)" type="button">👁</button>
      </div>
    </div>
    <div class="field">
      <label>Confirmar contraseña</label>
      <div class="pw-wrap">
        <input type="password" id="np2" placeholder="Repite la contraseña" oninput="checkMatch()" autocomplete="new-password">
        <button class="pw-toggle" onclick="togglePw('np2',this)" type="button">👁</button>
      </div>
      <div class="match-hint" id="mhint"></div>
    </div>

    <button class="btn-change" id="cpBtn" onclick="doChange()" disabled>
      <span id="cpTxt">Guardar contraseña →</span>
      <span class="ldots" id="cpLd"><span class="ld"></span><span class="ld"></span><span class="ld"></span></span>
    </button>
  </div>
</div>

<script>
let _pu = null; // pending user

function togglePw(id,btn){const i=document.getElementById(id);if(i.type==='password'){i.type='text';btn.textContent='🙈';}else{i.type='password';btn.textContent='👁';}}

function msg(id,type,txt){const e=document.getElementById(id);e.textContent=(type==='err'?'⚠ ':type==='warn'?'⏱ ':'✓ ')+txt;e.className='msg '+type+' show';}
function clr(id){const e=document.getElementById(id);if(e)e.className='msg';}

function setLoad(btn,ld,txt,on){document.getElementById(btn).disabled=on;document.getElementById(ld).className='ldots'+(on?' show':'');document.getElementById(txt).style.display=on?'none':'';}

async function doLogin(){
  clr('errMsg');clr('warnMsg');
  const u=document.getElementById('uInput').value.trim();
  const p=document.getElementById('pInput').value;
  if(!u||!p){msg('errMsg','err','Completa usuario y contraseña.');return;}
  setLoad('loginBtn','ldots','btnTxt',true);
  try{
    const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(d.ok&&d.must_change_password){_pu=u;document.getElementById('cpOverlay').classList.add('show');setLoad('loginBtn','ldots','btnTxt',false);}
    else if(d.ok){window.location.replace('/');}
    else if(d.lockout){msg('warnMsg','warn',d.error);setLoad('loginBtn','ldots','btnTxt',false);}
    else{msg('errMsg','err',d.error||'Credenciales incorrectas.');setLoad('loginBtn','ldots','btnTxt',false);}
  }catch(e){msg('errMsg','err','Error de conexión.');setLoad('loginBtn','ldots','btnTxt',false);}
}

function setReq(id,ok){const e=document.getElementById(id);e.className='req-item'+(ok?' ok':'');e.querySelector('.ricon').textContent=ok?'✓':'○';}
function checkReqs(){
  const v=document.getElementById('np1').value;
  setReq('req-len',v.length>=8);
  setReq('req-num',/\d/.test(v));
  setReq('req-up',/[A-Z]/.test(v));
  checkMatch();
}
function checkMatch(){
  const v1=document.getElementById('np1').value,v2=document.getElementById('np2').value;
  const h=document.getElementById('mhint');
  if(!v2){h.textContent='';h.className='match-hint';return;}
  if(v1===v2){h.textContent='✓ Coinciden';h.className='match-hint ok';}
  else{h.textContent='✗ No coinciden';h.className='match-hint err';}
  const ok=v1.length>=8&&/\d/.test(v1)&&/[A-Z]/.test(v1)&&v1===v2;
  document.getElementById('cpBtn').disabled=!ok;
}

async function doChange(){
  clr('cpErr');clr('cpOk');
  const np=document.getElementById('np1').value,nc=document.getElementById('np2').value;
  if(np!==nc){msg('cpErr','err','Las contraseñas no coinciden.');return;}
  setLoad('cpBtn','cpLd','cpTxt',true);
  try{
    const r=await fetch('/api/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:_pu,new_password:np})});
    const d=await r.json();
    if(d.ok){msg('cpOk','ok','¡Contraseña guardada! Ingresando…');setTimeout(()=>window.location.replace('/'),1200);}
    else{msg('cpErr','err',d.error||'Error al guardar.');setLoad('cpBtn','cpLd','cpTxt',false);}
  }catch(e){msg('cpErr','err','Error de conexión.');setLoad('cpBtn','cpLd','cpTxt',false);}
}

document.addEventListener('keydown',function(e){
  if(e.key!=='Enter')return;
  if(document.getElementById('cpOverlay').classList.contains('show')){if(!document.getElementById('cpBtn').disabled)doChange();}
  else doLogin();
});
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
    """Verifica firma, expiración Y que el boot epoch coincida con el arranque actual."""
    try:
        import base64
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        encoded, sig = parts
        if not hmac.compare_digest(sig, _sign(encoded, secret)):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode())
        if time.time() > payload.get("exp", 0):
            return None
        # Rechaza tokens de sesiones de un arranque anterior
        if payload.get("boot") != _SERVER_BOOT:
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
    return path in PUBLIC_ROUTES or path.startswith("/static/")


# ─────────────────────────────────────────────────────────────────
# UI INYECTADA — botón logout + timer de inactividad en el frontend
# ─────────────────────────────────────────────────────────────────

_INJECT_HTML = """
<style>
#vf-logout-btn{
  display:flex;align-items:center;gap:8px;width:calc(100% - 20px);
  margin:0 10px 2px;padding:9px 10px;
  background:none;border:none;cursor:pointer;
  font-family:var(--mono,'JetBrains Mono',monospace);
  font-size:11px;font-weight:400;color:rgba(255,80,80,.65);
  letter-spacing:.01em;border-radius:9px;
  transition:color .15s,background .15s;text-align:left;
}
#vf-logout-btn:hover{color:#ff5566;background:rgba(255,50,50,.07)}
#vf-session-warn{
  position:fixed;bottom:22px;right:22px;z-index:9999;
  background:rgba(15,15,28,.97);
  border:1px solid rgba(251,191,36,.35);border-radius:14px;
  padding:14px 18px;font-family:'JetBrains Mono',monospace;
  font-size:12px;color:#fbbf24;
  box-shadow:0 8px 36px rgba(0,0,0,.6);
  display:none;flex-direction:row;gap:14px;align-items:center;
}
#vf-session-warn button{
  background:rgba(251,191,36,.14);border:1px solid rgba(251,191,36,.3);
  border-radius:7px;padding:4px 11px;color:#fbbf24;cursor:pointer;
  font-family:inherit;font-size:11px;white-space:nowrap;
}
</style>
<div id="vf-session-warn">
  <span>&#9201; Sesi&oacute;n expira en 5&nbsp;min</span>
  <button onclick="window._vfResetIdle()">Mantener sesi&oacute;n</button>
</div>
<script>
(function(){
  /* Boton Cerrar sesion */
  function _vfAddLogout(){
    var sb = document.querySelector('.sb');
    var footer = document.querySelector('.sb-footer');
    if(!sb || document.getElementById('vf-logout-btn')) return;
    var divider = document.createElement('div');
    divider.className = 'sb-div';
    var ic = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>';
    var btn = document.createElement('button');
    btn.id = 'vf-logout-btn';
    btn.innerHTML = '<span style="opacity:.5">'+ic+'</span>Cerrar sesión';
    btn.onclick = function(){
      if(confirm('¿Cerrar sesión de VideoForge?')){
        fetch('/api/logout',{method:'POST'}).finally(function(){
          window.location.href='/login';
        });
      }
    };
    if(footer){
      sb.insertBefore(divider, footer);
      sb.insertBefore(btn, footer);
    } else {
      sb.appendChild(divider);
      sb.appendChild(btn);
    }
  }

  /* Timer inactividad 40 min */
  var IDLE_MS = 2400000;
  var WARN_MS = 2100000;
  var _idleT, _warnT;

  function _vfResetIdle(){
    clearTimeout(_idleT); clearTimeout(_warnT);
    var w = document.getElementById('vf-session-warn');
    if(w) w.style.display = 'none';
    _warnT = setTimeout(function(){
      var w2 = document.getElementById('vf-session-warn');
      if(w2) w2.style.display = 'flex';
    }, WARN_MS);
    _idleT = setTimeout(function(){
      window.location.href = '/login?expired=1';
    }, IDLE_MS);
  }
  window._vfResetIdle = _vfResetIdle;

  ['mousedown','mousemove','keydown','scroll','touchstart','click'].forEach(function(e){
    document.addEventListener(e, _vfResetIdle, {passive:true});
  });

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){ _vfAddLogout(); _vfResetIdle(); });
  } else {
    _vfAddLogout(); _vfResetIdle();
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
        return pymysql.connect(**DB_CONFIG)
    except ImportError:
        raise RuntimeError("pymysql no instalado. Ejecuta: pip install pymysql")
    except Exception as e:
        raise RuntimeError(f"Error conectando a la base de datos: {e}")


def _hash_password(password):
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = "videoforge_salt_2024_"
        return "sha256:" + hashlib.sha256((salt + password).encode()).hexdigest()


def verify_password(plain, hashed):
    try:
        if hashed.startswith("sha256:"):
            salt = "videoforge_salt_2024_"
            return hmac.compare_digest(
                hashed,
                "sha256:" + hashlib.sha256((salt + plain).encode()).hexdigest()
            )
        import bcrypt
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
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

    # ── 2. Renovar token (ventana deslizante) + inyectar UI ────────
    @app.after_request
    def after_auth(response):
        user = getattr(g, "_vf_user", None)
        if user:
            # Renueva el token → reinicia el contador de inactividad
            new_token = _make_token(user, APP_SECRET_KEY)
            response.set_cookie(
                SESSION_COOKIE, new_token,
                httponly=True, samesite="Lax", secure=False,
                max_age=SESSION_MINUTES * 60,
            )
            # Inyectar botón logout + timer solo en respuestas HTML principales
            if "text/html" in (response.content_type or "") and response.status_code == 200:
                try:
                    html = response.get_data(as_text=True)
                    if "</body>" in html and "vf-logout-btn" not in html:
                        html = html.replace("</body>", _INJECT_HTML + "</body>", 1)
                        response.set_data(html.encode("utf-8"))
                        response.headers["Content-Length"] = len(response.get_data())
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

    @app.route("/api/auth/me")
    def api_me():
        user = _get_current_user(request, APP_SECRET_KEY)
        if not user:
            return jsonify({"authenticated": False}), 401
        return jsonify({"authenticated": True, "username": user})

    print("[AUTH] Sistema de autenticacion registrado (SESSION_MINUTES=40, boot-epoch activo).")

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
        print(f"✅ Usuario '{username}' creado con rol '{role}'.")
    except Exception as e:
        print(f"❌ Error al crear usuario: {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "crear_usuario":
        crear_usuario_cli(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "user")
    else:
        print("Uso: python auth_module.py crear_usuario <username> <password> [role]")