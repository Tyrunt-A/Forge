import os
import sys
import traceback
from dotenv import load_dotenv

# ============================================
# LOGGING A ARCHIVO
# ============================================
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forge_debug.log")

def log(msg):
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            import datetime
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except:
        pass

log("=== ARRANQUE ===")

def _tkinter_error_handler(exc, val, tb):
    msg = "".join(traceback.format_exception(exc, val, tb))
    log(f"[TKINTER ERROR]\n{msg}")
import anthropic
import requests
import threading
from PIL import Image, ImageTk
import io

import tkinter as tk
from tkinter import font as tkfont
import speech_recognition as sr
import pyttsx3

# ============================================
# CONFIGURACIÓN
# ============================================
# Buscar .env siempre al lado del .exe, no en carpeta temporal de PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))
RIOT_API_KEY      = os.getenv("RIOT_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FORGE_MODEL       = os.getenv("FORGE_MODEL", "claude-sonnet-4-20250514")
FONDO_PATH        = os.path.join(BASE_DIR, "fondo.jpg")

COLOR_ENTRY_BG      = "#1a1a2e"
COLOR_BTN           = "#7a4f1a"
COLOR_BTN_HOV       = "#a86b22"
COLOR_TEXTO         = "#e8d5a3"
COLOR_SUBT          = "#8a7a5a"
COLOR_WARN          = "#ff9900"
COLOR_BLOQUEADO     = "#2a2a3e"
COLOR_BLOQUEADO_TXT = "#555577"
COLOR_BARRA         = "#0a0a14"
COLOR_GRABANDO      = "#cc3333"
COLOR_GRABANDO_HOV  = "#ff4444"
COLOR_PAUSADO       = "#555555"
COLOR_PAUSADO_HOV   = "#777777"
COLOR_OVERLAY_BG    = "#0a0a18"
COLOR_BTN_EQUIPO    = "#2a3a5a"
COLOR_BTN_EQUIPO_HOV= "#3a4a7a"

LINEAS_EQUIPO = ["Top", "Jungle", "Mid", "Bot (ADC)", "Support"]

CAMPEONES_POR_LINEA = {
    "Top":       ["Fighter", "Tank", "Mage", "Assassin", "Marksman"],
    "Jungle":    ["Assassin", "Fighter", "Tank", "Mage", "Marksman"],
    "Mid":       ["Mage", "Assassin", "Fighter", "Marksman"],
    "Bot (ADC)": ["Marksman"],
    "Support":   ["Support", "Tank", "Mage"]
}
LINEAS     = ["Top", "Jungle", "Mid", "Bot (ADC)", "Support"]
ALTO_BARRA = 64

# Línea principal por tag de campeón — orden de prioridad
TAG_A_LINEA = {
    "Marksman": "Bot (ADC)",
    "Support":  "Support",
    "Assassin": "Mid",
    "Mage":     "Mid",
    "Fighter":  "Top",
    "Tank":     "Top",
}

# Campeones que la API clasifica con tags incorrectos para su rol real
LINEA_OVERRIDE = {
    "Teemo":     "Top",
    "Kennen":    "Top",
    "Gnar":      "Top",
    "Quinn":     "Top",
    "Vayne":     "Top",      # puede ir top o bot
    "Kayle":     "Top",
    "Gangplank": "Top",
    "Corki":     "Mid",
    "Tristana":  "Bot (ADC)",
    "Graves":    "Jungle",
    "Kindred":   "Jungle",
    "Twitch":    "Bot (ADC)",
}

def detectar_linea_campeon(campeon):
    """Devuelve la línea más probable para un campeón según su nombre o tags"""
    if not campeon:
        return None
    # Override explícito por nombre
    nombre = campeon.get("nombre", "")
    if nombre in LINEA_OVERRIDE:
        return LINEA_OVERRIDE[nombre]
    # Fallback por tags
    for tag in campeon.get("tags", []):
        if tag in TAG_A_LINEA:
            return TAG_A_LINEA[tag]
    return None

# ============================================
# ESTADO COMPARTIDO
# ============================================
estado_partida = {
    "mi_campeon":      None,
    "campeon_enemigo": None,
    "linea":           None,
    "mi_equipo":       {l: None for l in LINEAS_EQUIPO},
    "equipo_rival":    {l: None for l in LINEAS_EQUIPO},
}

perfil_jugador = {
    "riot_id":          None,  # "Nombre#TAG"
    "puuid":            None,
    "nivel":            None,
    "rango":            None,  # "Gold II", "Sin rango", etc.
    "partidas_totales": None,
    "campeones_top":    [],    # lista de dicts {nombre, partidas, winrate}
    "tipo":             None,  # "nuevo", "retomando", "activo"
    "encuesta":         {},    # respuestas encuesta jugador nuevo
}

escucha_activa = {"valor": False}

def tiene_contexto():
    return estado_partida["mi_campeon"] is not None

def resumen_contexto():
    if not tiene_contexto():
        return ""
    return (f"{estado_partida['mi_campeon']['nombre']} "
            f"({estado_partida['linea']}) "
            f"vs {estado_partida['campeon_enemigo']['nombre']}")

def contexto_equipos_para_prompt():
    """Genera texto con los equipos completos para el prompt de Claude"""
    lineas = []

    mi_eq = estado_partida["mi_equipo"]
    filled_mi = {l: c for l, c in mi_eq.items() if c is not None}
    if filled_mi:
        lineas.append("Mi equipo:")
        for l, c in filled_mi.items():
            lineas.append(f"  - {l}: {c['nombre']}")

    eq_rival = estado_partida["equipo_rival"]
    filled_rival = {l: c for l, c in eq_rival.items() if c is not None}
    if filled_rival:
        lineas.append("Equipo rival:")
        for l, c in filled_rival.items():
            lineas.append(f"  - {l}: {c['nombre']}")

    return "\n".join(lineas) if lineas else ""


# ============================================
# TTS
# ============================================
tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 165)
tts_engine.setProperty("volume", 1.0)

def hablar(texto):
    def _hablar():
        tts_engine.say(texto)
        tts_engine.runAndWait()
    threading.Thread(target=_hablar, daemon=True).start()


# ============================================
# FUNCIONES DE DATOS
# ============================================
def get_version():
    return requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]

def get_champions(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/es_ES/champion.json"
    return requests.get(url).json()["data"]

# ============================================
# RIOT API — PERFIL DE JUGADOR
# ============================================
RIOT_REGIONS = {
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe",
    "na1":  "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "kr":   "asia", "jp1": "asia",
    "oc1":  "sea", "ph2": "sea", "sg2": "sea", "th2": "sea", "tw2": "sea", "vn2": "sea",
}

# Región dinámica — se detecta automáticamente al cargar el perfil
_region_platform = os.getenv("RIOT_REGION", "euw1")
_region_routing  = RIOT_REGIONS.get(_region_platform, "europe")

def riot_get(url, params=None):
    headers = {"X-Riot-Token": RIOT_API_KEY}
    r = requests.get(url, headers=headers, params=params, timeout=10)
    return r.json() if r.status_code == 200 else None

def detectar_region(puuid):
    """Detecta el servidor de LoL donde está activa la cuenta"""
    # Intentamos europe primero (más común), luego el resto
    for routing in ["europe", "americas", "asia", "sea"]:
        url = f"https://{routing}.api.riotgames.com/riot/account/v1/active-shards/by-game/lol/by-puuid/{puuid}"
        data = riot_get(url)
        if data and "activeShard" in data:
            platform = data["activeShard"]  # ej: "euw1", "la2", "na1"
            routing_final = RIOT_REGIONS.get(platform, routing)
            return platform, routing_final
    return _region_platform, _region_routing  # fallback al .env

def obtener_puuid(game_name, tag_line):
    # account-v1 funciona desde cualquier routing — usamos europe por defecto
    url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    data = riot_get(url)
    if not data:
        # Intentar otros routings por si acaso
        for routing in ["americas", "asia", "sea"]:
            url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            data = riot_get(url)
            if data and "puuid" in data:
                break
    return data.get("puuid") if data else None

def obtener_summoner(puuid, platform):
    url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    return riot_get(url)

def obtener_rango(summoner_id, platform):
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    data = riot_get(url)
    if not data:
        return "Sin rango"
    for entry in data:
        if entry.get("queueType") == "RANKED_SOLO_5x5":
            tier = entry.get("tier", "").capitalize()
            rank = entry.get("rank", "")
            return f"{tier} {rank}".strip()
    return "Sin rango clasificatorio"

def obtener_historial(puuid, routing, count=30):
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    return riot_get(url, params={"count": count, "queue": 420}) or []

def obtener_detalle_partida(match_id, routing):
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return riot_get(url)

def calcular_perfil_jugador(riot_id_completo):
    """
    Recibe "Nombre#TAG", consulta la API y rellena perfil_jugador.
    Detecta la región automáticamente. Devuelve (True, "") o (False, error).
    """
    try:
        partes = riot_id_completo.strip().split("#")
        if len(partes) != 2:
            return False, "Formato incorrecto. Usa Nombre#TAG (ej: Faker#KR1)", False

        game_name, tag_line = partes[0].strip(), partes[1].strip()

        puuid = obtener_puuid(game_name, tag_line)
        if not puuid:
            return False, f"No encontré la cuenta '{riot_id_completo}'. Verifica el nombre y tag.", False

        # Detectar región automáticamente
        platform, routing = detectar_region(puuid)

        summoner = obtener_summoner(puuid, platform)

        # Cuenta sin partidas aún — summoner profile no existe todavía
        if not summoner:
            perfil_jugador["riot_id"]          = riot_id_completo
            perfil_jugador["puuid"]            = puuid
            perfil_jugador["nivel"]            = 1
            perfil_jugador["rango"]            = "Sin rango"
            perfil_jugador["partidas_totales"] = 0
            perfil_jugador["campeones_top"]    = []
            perfil_jugador["tipo"]             = "nuevo"
            return True, "", False

        nivel = summoner.get("summonerLevel", 0)
        rango = obtener_rango(summoner.get("id", ""), platform)

        # Verificar rápido si hay partidas antes de descargar detalles
        match_ids = obtener_historial(puuid, routing, count=30)
        partidas_totales = len(match_ids)

        # Si no hay historial ranked, ir directo a encuesta sin descargar nada
        if partidas_totales == 0:
            perfil_jugador["riot_id"]          = riot_id_completo
            perfil_jugador["puuid"]            = puuid
            perfil_jugador["nivel"]            = nivel
            perfil_jugador["rango"]            = rango
            perfil_jugador["partidas_totales"] = 0
            perfil_jugador["campeones_top"]    = []
            perfil_jugador["tipo"]             = "nuevo"
            return True, "", False

        # Contar partidas por campeón
        stats_campeones = {}
        for mid in match_ids:
            detalle = obtener_detalle_partida(mid, routing)
            if not detalle:
                continue
            participantes = detalle.get("info", {}).get("participants", [])
            for p in participantes:
                if p.get("puuid") == puuid:
                    champ_name = p.get("championName", "")
                    win        = p.get("win", False)
                    if champ_name not in stats_campeones:
                        stats_campeones[champ_name] = {"partidas": 0, "victorias": 0}
                    stats_campeones[champ_name]["partidas"]  += 1
                    stats_campeones[champ_name]["victorias"] += 1 if win else 0
                    break

        # Top 3 campeones por partidas jugadas
        top = sorted(stats_campeones.items(), key=lambda x: x[1]["partidas"], reverse=True)[:3]
        campeones_top = []
        for nombre_champ, s in top:
            wr = round(s["victorias"] / s["partidas"] * 100) if s["partidas"] > 0 else 0
            campeones_top.append({"nombre": nombre_champ, "partidas": s["partidas"], "winrate": wr})

        # Clasificar tipo de jugador
        if nivel < 30 or partidas_totales < 5:
            tipo = "nuevo"
        elif partidas_totales < 15:
            tipo = "retomando"
        else:
            tipo = "activo"

        # Guardar en estado global
        perfil_jugador["riot_id"]          = riot_id_completo
        perfil_jugador["puuid"]            = puuid
        perfil_jugador["nivel"]            = nivel
        perfil_jugador["rango"]            = rango
        perfil_jugador["partidas_totales"] = partidas_totales
        perfil_jugador["campeones_top"]    = campeones_top
        perfil_jugador["tipo"]             = tipo

        # Si es nuevo con pocas partidas Y nivel muy bajo, mostrar encuesta
        necesita_encuesta = (tipo == "nuevo" and nivel < 10 and not perfil_jugador.get("encuesta"))

        return True, "", necesita_encuesta

    except Exception as e:
        return False, f"Error inesperado: {str(e)}", False

def tiene_perfil():
    return perfil_jugador["riot_id"] is not None

def contexto_perfil_para_prompt():
    """Genera texto del perfil para inyectar en prompts de Claude"""
    if not tiene_perfil():
        return ""
    p = perfil_jugador
    lineas = ["Perfil del jugador:"]
    lineas.append(f"  - Riot ID: {p['riot_id']}")
    lineas.append(f"  - Nivel: {p['nivel']} | Rango: {p['rango']}")
    lineas.append(f"  - Tipo: {p['tipo'].upper()}")
    if p["campeones_top"]:
        tops = ", ".join([f"{c['nombre']} ({c['partidas']}p, {c['winrate']}%wr)" for c in p["campeones_top"]])
        lineas.append(f"  - Campeones recientes: {tops}")
    enc = p.get("encuesta", {})
    if enc:
        exp_map    = {"nunca": "nunca jugó LoL", "pc_antes": "jugó LoL PC antes", "wildrift": "jugó Wild Rift"}
        juegos_map = {"ninguno": "sin experiencia en otros juegos", "moba": "experiencia en otros MOBAs", "rpg": "experiencia en RPGs/estrategia"}
        lineas.append(f"  - Experiencia: {exp_map.get(enc.get('experiencia_previa',''), enc.get('experiencia_previa',''))}")
        lineas.append(f"  - Juegos previos: {juegos_map.get(enc.get('juegos_similares',''), enc.get('juegos_similares',''))}")
        lineas.append(f"  - Línea de interés: {enc.get('linea_preferida','')}")
    return "\n".join(lineas)

def buscar_campeon(nombre, champions):
    nombre_lower = nombre.lower().strip()
    mejor_match  = None
    mejor_score  = 0
    for key, champ in champions.items():
        nc = champ["name"].lower()
        kl = key.lower()
        if nombre_lower == nc or nombre_lower == kl:
            return {"id": key, "nombre": champ["name"], "tags": champ["tags"]}
        if nc.startswith(nombre_lower) or kl.startswith(nombre_lower):
            score = len(nombre_lower) / len(nc) + 0.5
            if score > mejor_score:
                mejor_score = score
                mejor_match = {"id": key, "nombre": champ["name"], "tags": champ["tags"]}
        elif nombre_lower in nc or nombre_lower in kl:
            score = len(nombre_lower) / len(nc)
            if score > mejor_score:
                mejor_score = score
                mejor_match = {"id": key, "nombre": champ["name"], "tags": champ["tags"]}
    return mejor_match

def campeon_inusual_en_linea(campeon, linea):
    for tag in campeon["tags"]:
        if tag in CAMPEONES_POR_LINEA.get(linea, []):
            return False
    return True

def obtener_sugerencias(texto, champions, max_s=5):
    tl = texto.lower().strip()
    if not tl:
        return []
    res = [c["name"] for k, c in champions.items()
           if c["name"].lower().startswith(tl) or k.lower().startswith(tl)]
    return sorted(res)[:max_s]

def limpiar_markdown(texto):
    out = []
    for linea in texto.split("\n"):
        linea = linea.strip()
        while linea.startswith("#"):
            linea = linea.lstrip("#").strip()
        out.append(linea.replace("**", "").replace("*", ""))
    return "\n".join(out)

def get_splash_art(champ_id):
    try:
        url = f"https://ddragon.leagueoflegends.com/cdn/img/champion/loading/{champ_id}_0.jpg"
        r   = requests.get(url, timeout=10)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content))
    except:
        pass
    return None

def recomendar_build(mi_campeon, campeon_enemigo, linea):
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    ctx_equipos = contexto_equipos_para_prompt()
    ctx_perfil  = contexto_perfil_para_prompt()
    extra       = f"\n\nComposición completa:\n{ctx_equipos}" if ctx_equipos else ""
    extra_perfil = f"\n\n{ctx_perfil}" if ctx_perfil else ""

    # Adaptar tono según tipo de jugador
    tipo = perfil_jugador.get("tipo", "activo")
    if tipo == "nuevo":
        instruccion_tono = "El jugador es NUEVO. Explica brevemente el para qué de cada ítem. Usa lenguaje simple."
    elif tipo == "retomando":
        instruccion_tono = "El jugador está RETOMANDO el juego. Puede que no conozca cambios recientes. Menciona si algo cambió mucho."
    else:
        instruccion_tono = "El jugador es ACTIVO. Sé directo y técnico, sin explicaciones básicas."

    prompt = f"""Eres Forge, un coach de League of Legends. Tu tono es duro y directo — destruyes el ego y en la misma frase dices qué hacer. No insultas por insultar: cada crítica va acompañada de una instrucción accionable.
{instruccion_tono}
{extra_perfil}
El jugador usa: {mi_campeon['nombre']} ({', '.join(mi_campeon['tags'])})
Línea: {linea}
Enemigo directo: {campeon_enemigo['nombre']} ({', '.join(campeon_enemigo['tags'])})
{extra}

Da una guía de arranque para los primeros minutos. Estructura exacta, sin títulos numerados:

RUNAS
Keystona recomendada y árbol secundario para este matchup. Una línea explicando por qué esa elección contra {campeon_enemigo['nombre']}. Solo lo esencial, sin listar cada runa menor.

ARRANQUE
Ítem(s) de arranque y pociones. Nombres en español. Una línea explicando por qué contra {campeon_enemigo['nombre']}.

NIVELES 1-6
Qué habilidad subir primero y por qué. Cómo jugar el early. Una o dos mecánicas clave de {mi_campeon['nombre']} que el jugador debe usar desde ya.

PRIMER ÍTEM COMPLETO
Qué construir primero y por qué es la prioridad contra este matchup. Nombre en español.

CONSEJO DEL MATCHUP
Una sola cosa concreta que define ganar o perder esta línea. Sin suavizar.

Nombres de ítems siempre en español. Sin relleno. Sin lista de build completa."""

    msg = cliente.messages.create(
        model=FORGE_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return limpiar_markdown(msg.content[0].text)

def coach_ingame(pregunta):
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    contexto_matchup = ""
    if tiene_contexto():
        mc = estado_partida["mi_campeon"]
        ce = estado_partida["campeon_enemigo"]
        li = estado_partida["linea"]
        ctx_equipos = contexto_equipos_para_prompt()
        contexto_matchup = f"""
Contexto de la partida:
- El jugador usa {mc['nombre']} ({', '.join(mc['tags'])}) en {li}
- Enemigo directo: {ce['nombre']} ({', '.join(ce['tags'])})
{ctx_equipos}
"""
    ctx_perfil = contexto_perfil_para_prompt()
    if ctx_perfil:
        contexto_matchup += f"\n{ctx_perfil}"

    prompt = f"""Eres un coach de League of Legends dando consejos en tiempo real durante una partida.
{contexto_matchup}
El jugador pregunta: {pregunta}

Responde en máximo 2-3 frases. Directo, accionable, sin relleno.
El jugador está en medio de una partida — no tiene tiempo para leer mucho."""

    msg = cliente.messages.create(
        model=FORGE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    return limpiar_markdown(msg.content[0].text)


# ============================================
# APP
# ============================================
app = tk.Tk()
app.title("LOL Coach")
app.configure(bg="black")
app.report_callback_exception = _tkinter_error_handler
log("app creado")

app.resizable(True, True)
app.wm_attributes("-fullscreen", True)

def ANCHO():         return app.winfo_width()
def ALTO():          return app.winfo_height()
def ANCHO_LATERAL(): return int(ANCHO() * 0.22)
def ANCHO_CENTRO():  return ANCHO() - (ANCHO_LATERAL() * 2)
def ALTO_UTIL():     return ALTO() - ALTO_BARRA
def ALTO_SPLASH():   return int((ALTO_UTIL() - 140) * 0.90)
def CX():            return ANCHO() // 2

version   = get_version()
champions = get_champions(version)

F_TITLE    = tkfont.Font(family="Georgia", size=36, weight="bold")
F_SUBTITLE = tkfont.Font(family="Georgia", size=13)
F_SUB      = tkfont.Font(family="Georgia", size=11)
F_LABEL    = tkfont.Font(family="Georgia", size=12)
F_LARGE    = tkfont.Font(family="Georgia", size=13)
F_BODY     = tkfont.Font(family="Arial",  size=13)
F_SMALL    = tkfont.Font(family="Georgia", size=10)
F_BTN      = tkfont.Font(family="Georgia", size=13, weight="bold")
F_BTN_MENU = tkfont.Font(family="Georgia", size=14, weight="bold")
F_BTN_SM   = tkfont.Font(family="Georgia", size=11, weight="bold")

canvas = tk.Canvas(app, highlightthickness=0, bd=0, bg="black")
canvas.pack(fill="both", expand=True)

_photos      = {}
_widgets     = []
_overlay_ref = {"frame": None}  # referencia al overlay activo


def limpiar_pantalla():
    escucha_activa["valor"] = False
    cerrar_overlay()
    canvas.delete("ui")
    canvas.delete("splash_izq")
    canvas.delete("splash_der")
    for w in _widgets:
        try:
            w.destroy()
        except:
            pass
    _widgets.clear()
    app.unbind("<Return>")


def registrar(widget):
    _widgets.append(widget)
    return widget


def init_fondo():
    try:
        img = Image.open(FONDO_PATH).resize((ANCHO(), ALTO()), Image.LANCZOS)
        _photos["fondo"] = ImageTk.PhotoImage(img)
        canvas.create_image(0, 0, anchor="nw", image=_photos["fondo"], tags="fondo")
        canvas.tag_lower("fondo")
    except Exception as e:
        # Sin imagen de fondo: usar color sólido oscuro (la app funciona igual)
        log(f"Fondo no encontrado, usando color sólido: {e}")
        canvas.create_rectangle(0, 0, ANCHO(), ALTO(),
                                fill="#0a0a14", outline="", tags="fondo")
        canvas.tag_lower("fondo")


# ============================================
# OVERLAY DE EQUIPO
# ============================================
def cerrar_overlay():
    if _overlay_ref["frame"] and _overlay_ref["frame"].winfo_exists():
        _overlay_ref["frame"].destroy()
    _overlay_ref["frame"] = None


def abrir_overlay_equipo(tipo, linea_var=None):
    """
    tipo: 'mi_equipo' o 'equipo_rival'
    linea_var: StringVar del selector de línea principal (para excluirla en tiempo real)
    """
    cerrar_overlay()

    titulo     = "Mi Equipo" if tipo == "mi_equipo" else "Equipo Rival"
    linea_excl = (linea_var.get() if linea_var else None) or estado_partida["linea"]
    lineas_overlay = [l for l in LINEAS_EQUIPO if l != linea_excl] if linea_excl else LINEAS_EQUIPO

    ov_w  = int(ANCHO() * 0.42)
    ov_h  = min(60 + len(lineas_overlay) * 110 + 80, int(ALTO_UTIL() * 0.85))
    ov_x  = CX() - ov_w // 2
    ov_y  = int(ALTO_UTIL() * 0.06)

    frame = tk.Frame(app, bg=COLOR_OVERLAY_BG,
                     highlightthickness=1, highlightbackground="#2a2a5a")
    frame.place(x=ov_x, y=ov_y, width=ov_w, height=ov_h)
    _overlay_ref["frame"] = frame

    # Título fijo arriba
    tk.Label(frame, text=titulo, font=F_BTN_MENU,
             bg=COLOR_OVERLAY_BG, fg=COLOR_TEXTO).pack(pady=(14, 4))

    # Botones fijos abajo — se declaran antes del scroll para que pack los ancle al fondo
    btn_frame = tk.Frame(frame, bg=COLOR_OVERLAY_BG)
    btn_frame.pack(side="bottom", pady=10)

    slot_entries = {}
    equipo_dict  = estado_partida[tipo]

    def guardar():
        for linea, (entry, _) in slot_entries.items():
            nombre = entry.get().strip()
            if nombre:
                campeon = buscar_campeon(nombre, champions)
                estado_partida[tipo][linea] = campeon if campeon else None
            else:
                estado_partida[tipo][linea] = None
        cerrar_overlay()

    tk.Button(btn_frame, text="Guardar", font=F_BTN_SM,
              bg=COLOR_BTN, fg=COLOR_TEXTO,
              activebackground=COLOR_BTN_HOV,
              relief="flat", cursor="hand2",
              command=guardar).pack(side="left", padx=8, ipadx=12, ipady=4)

    tk.Button(btn_frame, text="Cerrar", font=F_BTN_SM,
              bg=COLOR_ENTRY_BG, fg=COLOR_SUBT,
              activebackground=COLOR_BTN,
              relief="flat", cursor="hand2",
              command=cerrar_overlay).pack(side="left", padx=8, ipadx=12, ipady=4)

    # Área scrollable
    scroll_outer = tk.Frame(frame, bg=COLOR_OVERLAY_BG)
    scroll_outer.pack(fill="both", expand=True, padx=4)

    scrollbar = tk.Scrollbar(scroll_outer, orient="vertical",
                             bg=COLOR_OVERLAY_BG, troughcolor=COLOR_ENTRY_BG,
                             activebackground=COLOR_BTN)
    scrollbar.pack(side="right", fill="y")

    inner_canvas = tk.Canvas(scroll_outer, bg=COLOR_OVERLAY_BG,
                             highlightthickness=0, yscrollcommand=scrollbar.set)
    inner_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=inner_canvas.yview)

    content_frame = tk.Frame(inner_canvas, bg=COLOR_OVERLAY_BG)
    content_window = inner_canvas.create_window((0, 0), window=content_frame, anchor="nw")

    def on_content_configure(e):
        inner_canvas.configure(scrollregion=inner_canvas.bbox("all"))

    def on_canvas_configure(e):
        inner_canvas.itemconfig(content_window, width=e.width)

    content_frame.bind("<Configure>", on_content_configure)
    inner_canvas.bind("<Configure>", on_canvas_configure)

    def on_mousewheel(e):
        inner_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    inner_canvas.bind("<MouseWheel>", on_mousewheel)

    # Slots por línea
    for linea in lineas_overlay:
        fila = tk.Frame(content_frame, bg=COLOR_OVERLAY_BG)
        fila.pack(fill="x", padx=20, pady=6)

        tk.Label(fila, text=f"{linea}:", font=F_LABEL,
                 bg=COLOR_OVERLAY_BG, fg=COLOR_SUBT,
                 width=10, anchor="w").pack(side="left")

        entry = tk.Entry(fila, font=F_BODY,
                         bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
                         insertbackground=COLOR_TEXTO,
                         relief="flat", highlightthickness=1,
                         highlightbackground="#2a2a3e", highlightcolor="#4a7abf")
        entry.pack(side="left", fill="x", expand=True, ipady=4)

        if equipo_dict[linea]:
            entry.insert(0, equipo_dict[linea]["nombre"])

        sug_frame = tk.Frame(content_frame, bg=COLOR_OVERLAY_BG)
        sug_frame.pack(fill="x", padx=20 + 80)

        slot_entries[linea] = (entry, sug_frame)

        warn_label = tk.Label(content_frame, text="", font=F_SMALL,
                              bg=COLOR_OVERLAY_BG, fg=COLOR_WARN)
        warn_label.pack(fill="x", padx=20 + 80)

        def make_handler(e=entry, sf=sug_frame, wl=warn_label, t=tipo, l=linea):
            def handler(event):
                texto = e.get()
                for w in sf.winfo_children():
                    w.destroy()
                # Advertencia solo si el nombre escrito coincide exactamente con un campeón
                campeon_check = buscar_campeon(texto, champions)
                nombre_exacto = campeon_check and campeon_check["nombre"].lower() == texto.lower().strip()
                if nombre_exacto and campeon_inusual_en_linea(campeon_check, l):
                    wl.config(text=f"⚠ {campeon_check['nombre']} inusual en {l}")
                else:
                    wl.config(text="")
                for nombre in obtener_sugerencias(texto, champions, max_s=4):
                    def seleccionar(n=nombre, en=e, s=sf, wll=wl, tp=t, li=l):
                        en.delete(0, "end")
                        en.insert(0, n)
                        for w in s.winfo_children():
                            w.destroy()
                        campeon = buscar_campeon(n, champions)
                        if campeon:
                            estado_partida[tp][li] = campeon
                            if campeon_inusual_en_linea(campeon, li):
                                wll.config(text=f"⚠ {campeon['nombre']} inusual en {li}")
                            else:
                                wll.config(text="")
                    btn_sug = tk.Button(sf, text=nombre, font=F_SMALL,
                                        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
                                        activebackground=COLOR_BTN,
                                        activeforeground=COLOR_TEXTO,
                                        relief="flat", cursor="hand2",
                                        command=seleccionar)
                    btn_sug.pack(side="left", padx=1)
            return handler

        entry.bind("<KeyRelease>", make_handler())

    frame.lift()


# ============================================
# BARRA INFERIOR
# ============================================
def actualizar_barra(modulo_activo="inicio"):
    canvas.delete("barra")

    y_barra   = ALTO() - ALTO_BARRA
    btn_w     = 220
    btn_h     = 42
    espaciado = 280
    cy        = y_barra + ALTO_BARRA // 2

    canvas.create_rectangle(0, y_barra, ANCHO(), ALTO(),
                             fill=COLOR_BARRA, outline="", tags="barra")

    def hacer_btn(texto, comando, x, es_activo):
        if es_activo:
            btn = tk.Button(
                canvas, text="← Volver", font=F_BTN_MENU,
                bg=COLOR_ENTRY_BG, fg=COLOR_SUBT,
                activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
                relief="flat", cursor="hand2",
                command=mostrar_inicio
            )
            btn.bind("<Enter>", lambda e: btn.config(bg=COLOR_BTN, fg=COLOR_TEXTO))
            btn.bind("<Leave>", lambda e: btn.config(bg=COLOR_ENTRY_BG, fg=COLOR_SUBT))
        else:
            btn = tk.Button(
                canvas, text=texto, font=F_BTN_MENU,
                bg=COLOR_BTN, fg=COLOR_TEXTO,
                activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
                relief="flat", cursor="hand2",
                command=comando
            )
            btn.bind("<Enter>", lambda e: btn.config(bg=COLOR_BTN_HOV))
            btn.bind("<Leave>", lambda e: btn.config(bg=COLOR_BTN))
        canvas.create_window(x, cy, anchor="center", window=btn,
                             width=btn_w, height=btn_h, tags="barra")

    hacer_btn("PRE-GAME", mostrar_pregame, CX() - espaciado, es_activo=(modulo_activo == "pregame"))
    hacer_btn("IN-GAME",  mostrar_ingame,  CX(),              es_activo=(modulo_activo == "ingame"))

    btn_post = tk.Button(
        canvas, text="POST-GAME", font=F_BTN_MENU,
        bg=COLOR_BLOQUEADO, fg=COLOR_BLOQUEADO_TXT,
        relief="flat", cursor="arrow", state="disabled"
    )
    canvas.create_window(CX() + espaciado, cy, anchor="center", window=btn_post,
                         width=btn_w, height=btn_h, tags="barra")

    canvas.tag_raise("barra")


# ============================================
# PANTALLAS
# ============================================
def mostrar_inicio():
    if tiene_perfil():
        mostrar_pregame()
        return
    limpiar_pantalla()
    actualizar_barra("inicio")

    canvas.create_text(CX(), int(ALTO_UTIL() * 0.22),
                       text="FORGE", font=F_TITLE,
                       fill=COLOR_TEXTO, tags="ui")
    canvas.create_text(CX(), int(ALTO_UTIL() * 0.22) + 55,
                       text="Tu coach. Sin filtros.",
                       font=F_SUBTITLE, fill=COLOR_SUBT, tags="ui")

    # --- BLOQUE RIOT ID ---
    y_bloque = int(ALTO_UTIL() * 0.48)

    if tiene_perfil():
        p = perfil_jugador
        tipo_color = {"nuevo": "#ff9900", "retomando": "#aaaacc", "activo": "#44aa44"}.get(p["tipo"], COLOR_SUBT)
        tipo_texto = {"nuevo": "Jugador nuevo", "retomando": "Retomando el juego", "activo": "Jugador activo"}.get(p["tipo"], "")

        canvas.create_text(CX(), y_bloque - 20,
                           text=f"● {p['riot_id']}  —  Nv.{p['nivel']}  |  {p['rango']}",
                           font=F_LABEL, fill="#44aa44", tags="ui")
        canvas.create_text(CX(), y_bloque + 12,
                           text=tipo_texto, font=F_SMALL, fill=tipo_color, tags="ui")

        if p["campeones_top"]:
            tops_txt = "  ·  ".join([f"{c['nombre']} ({c['winrate']}%wr)" for c in p["campeones_top"]])
            canvas.create_text(CX(), y_bloque + 38,
                               text=f"Recientes: {tops_txt}",
                               font=F_SMALL, fill=COLOR_SUBT, tags="ui")

        btn_cambiar = registrar(tk.Button(
            canvas, text="Cambiar cuenta", font=F_SMALL,
            bg=COLOR_ENTRY_BG, fg=COLOR_SUBT,
            activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
            relief="flat", cursor="hand2",
            command=lambda: _mostrar_input_riot_id(y_bloque + 70)
        ))
        canvas.create_window(CX(), y_bloque + 68, anchor="center",
                             window=btn_cambiar, width=160, height=26, tags="ui")
    else:
        canvas.create_text(CX(), y_bloque - 30,
                           text="Ingresa tu Riot ID para personalizar las recomendaciones",
                           font=F_SUBTITLE, fill=COLOR_SUBT, tags="ui")
        _mostrar_input_riot_id(y_bloque + 10)

    if tiene_contexto():
        canvas.create_text(CX(), int(ALTO_UTIL() * 0.88),
                           text=f"Partida activa: {resumen_contexto()}",
                           font=F_SMALL, fill="#44aa44", tags="ui")

    canvas.tag_raise("ui")
    canvas.tag_raise("barra")


def _mostrar_input_riot_id(y):
    """Dibuja el campo de entrada de Riot ID en la posición y indicada"""
    entry_riot = registrar(tk.Entry(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        insertbackground=COLOR_TEXTO, relief="flat",
        highlightthickness=1, highlightbackground="#2a2a3e", highlightcolor="#4a7abf"
    ))
    entry_riot.insert(0, perfil_jugador["riot_id"] or "")
    entry_riot.config(fg=COLOR_SUBT if not perfil_jugador["riot_id"] else COLOR_TEXTO)

    # Placeholder
    if not perfil_jugador["riot_id"]:
        entry_riot.insert(0, "Nombre#TAG")
        def on_focus_in(e):
            if entry_riot.get() == "Nombre#TAG":
                entry_riot.delete(0, "end")
                entry_riot.config(fg=COLOR_TEXTO)
        def on_focus_out(e):
            if not entry_riot.get():
                entry_riot.insert(0, "Nombre#TAG")
                entry_riot.config(fg=COLOR_SUBT)
        entry_riot.bind("<FocusIn>",  on_focus_in)
        entry_riot.bind("<FocusOut>", on_focus_out)

    canvas.create_window(CX() - 10, y, anchor="center",
                         window=entry_riot, width=280, height=38, tags="ui")

    status_label = registrar(tk.Label(
        canvas, text="", font=F_SMALL, bg="black", fg=COLOR_SUBT
    ))
    canvas.create_window(CX(), y + 34, anchor="center",
                         window=status_label, width=400, tags="ui")

    def cargar_perfil():
        riot_id = entry_riot.get().strip()
        if not riot_id or riot_id == "Nombre#TAG":
            return
        status_label.config(text="Cargando perfil...", fg=COLOR_SUBT)
        btn_cargar.config(state="disabled")

        def tarea():
            ok, error, encuesta = calcular_perfil_jugador(riot_id)
            if ok:
                if encuesta:
                    app.after(0, mostrar_encuesta_nuevo)
                else:
                    app.after(0, mostrar_inicio)
            else:
                app.after(0, lambda: [
                    status_label.config(text=error, fg=COLOR_WARN),
                    btn_cargar.config(state="normal")
                ])

        threading.Thread(target=tarea, daemon=True).start()

    btn_cargar = registrar(tk.Button(
        canvas, text="Cargar", font=F_BTN_SM,
        bg=COLOR_BTN, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2",
        command=cargar_perfil
    ))
    btn_cargar.bind("<Enter>", lambda e: btn_cargar.config(bg=COLOR_BTN_HOV))
    btn_cargar.bind("<Leave>", lambda e: btn_cargar.config(bg=COLOR_BTN))
    canvas.create_window(CX() + 160, y, anchor="center",
                         window=btn_cargar, width=90, height=38, tags="ui")

    app.bind("<Return>", lambda e: cargar_perfil())


def contexto_encuesta_para_prompt():
    """Genera texto de la encuesta para inyectar en prompts de Claude"""
    enc = perfil_jugador.get("encuesta", {})
    if not enc:
        return ""
    lineas = ["Contexto adicional del jugador nuevo:"]
    if enc.get("experiencia_previa"):
        lineas.append(f"  - Experiencia previa: {enc['experiencia_previa']}")
    if enc.get("juegos_similares"):
        lineas.append(f"  - Juegos similares jugados: {enc['juegos_similares']}")
    if enc.get("linea_preferida"):
        lineas.append(f"  - Línea de interés: {enc['linea_preferida']}")
    return "\n".join(lineas)


def mostrar_encuesta_nuevo():
    limpiar_pantalla()
    _pantalla_activa["fn"] = mostrar_encuesta_nuevo
    actualizar_barra("inicio")

    # Fuentes locales +40%
    F_ENC_TITLE  = tkfont.Font(family="Georgia", size=50, weight="bold")
    F_ENC_SUB    = tkfont.Font(family="Georgia", size=18)
    F_ENC_LABEL  = tkfont.Font(family="Georgia", size=17)
    F_ENC_BTN    = tkfont.Font(family="Georgia", size=14)
    F_ENC_CONT   = tkfont.Font(family="Georgia", size=18, weight="bold")

    canvas.create_text(CX(), int(ALTO_UTIL() * 0.10),
                       text="FORGE", font=F_ENC_TITLE,
                       fill=COLOR_TEXTO, tags="ui")
    canvas.create_text(CX(), int(ALTO_UTIL() * 0.10) + 65,
                       text="Cuéntanos un poco sobre ti para personalizar tu experiencia",
                       font=F_ENC_SUB, fill=COLOR_SUBT, tags="ui")

    y_base    = int(ALTO_UTIL() * 0.30)
    espaciado = int(ALTO_UTIL() * 0.20)

    # --- Pregunta 1: Experiencia previa ---
    canvas.create_text(CX(), y_base,
                       text="¿Jugaste LoL antes en alguna plataforma?",
                       font=F_ENC_LABEL, fill=COLOR_TEXTO, tags="ui")

    exp_var = tk.StringVar(value="")
    opciones_exp = [("Nunca jugué LoL", "nunca"), ("Jugué en PC antes", "pc_antes"),
                    ("Jugué Wild Rift (móvil)", "wildrift")]
    x_start = CX() - 360
    btns_exp = []
    for i, (texto, valor) in enumerate(opciones_exp):
        btn = registrar(tk.Button(
            canvas, text=texto, font=F_ENC_BTN,
            bg=COLOR_ENTRY_BG, fg=COLOR_SUBT,
            activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
            relief="flat", cursor="hand2"
        ))
        btns_exp.append(btn)
        def hacer_sel_exp(v=valor, b=btn, bl=btns_exp):
            exp_var.set(v)
            for x in bl:
                x.config(bg=COLOR_ENTRY_BG, fg=COLOR_SUBT)
            b.config(bg=COLOR_BTN, fg=COLOR_TEXTO)
        btn.config(command=hacer_sel_exp)
        canvas.create_window(x_start + i * 240, y_base + 42,
                             anchor="center", window=btn,
                             width=230, height=38, tags="ui")

    # --- Pregunta 2: Juegos similares ---
    canvas.create_text(CX(), y_base + espaciado,
                       text="¿Tienes experiencia con otros juegos similares?",
                       font=F_ENC_LABEL, fill=COLOR_TEXTO, tags="ui")

    juegos_var = tk.StringVar(value="")
    opciones_juegos = [("Ninguno", "ninguno"), ("MOBAs (Dota, Smite...)", "moba"),
                       ("RPGs / Estrategia", "rpg")]
    btns_juegos = []
    for i, (texto, valor) in enumerate(opciones_juegos):
        btn = registrar(tk.Button(
            canvas, text=texto, font=F_ENC_BTN,
            bg=COLOR_ENTRY_BG, fg=COLOR_SUBT,
            activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
            relief="flat", cursor="hand2"
        ))
        btns_juegos.append(btn)
        def hacer_sel_juegos(v=valor, b=btn, bl=btns_juegos):
            juegos_var.set(v)
            for x in bl:
                x.config(bg=COLOR_ENTRY_BG, fg=COLOR_SUBT)
            b.config(bg=COLOR_BTN, fg=COLOR_TEXTO)
        btn.config(command=hacer_sel_juegos)
        canvas.create_window(x_start + i * 240, y_base + espaciado + 42,
                             anchor="center", window=btn,
                             width=230, height=38, tags="ui")

    # --- Pregunta 3: Línea preferida ---
    canvas.create_text(CX(), y_base + espaciado * 2,
                       text="¿Qué línea te llama más la atención?",
                       font=F_ENC_LABEL, fill=COLOR_TEXTO, tags="ui")

    linea_var  = tk.StringVar(value="")
    ancho_btn  = int(ANCHO_CENTRO() * 0.16)
    x_linea    = CX() - ancho_btn * 2 - 8
    btns_linea = []
    for i, linea in enumerate(["Top", "Jungle", "Mid", "Bot (ADC)", "Support"]):
        btn = registrar(tk.Button(
            canvas, text=linea, font=F_ENC_BTN,
            bg=COLOR_ENTRY_BG, fg=COLOR_SUBT,
            activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
            relief="flat", cursor="hand2"
        ))
        btns_linea.append(btn)
        def hacer_sel_linea(v=linea, b=btn, bl=btns_linea):
            linea_var.set(v)
            for x in bl:
                x.config(bg=COLOR_ENTRY_BG, fg=COLOR_SUBT)
            b.config(bg=COLOR_BTN, fg=COLOR_TEXTO)
        btn.config(command=hacer_sel_linea)
        canvas.create_window(x_linea + i * (ancho_btn + 4), y_base + espaciado * 2 + 42,
                             anchor="center", window=btn,
                             width=ancho_btn, height=36, tags="ui")

    # --- Botón Continuar ---
    aviso_label = registrar(tk.Label(
        canvas, text="", font=F_ENC_BTN, bg="black", fg=COLOR_WARN
    ))
    canvas.create_window(CX(), y_base + espaciado * 3 + 10,
                         anchor="center", window=aviso_label,
                         width=500, tags="ui")

    def guardar_encuesta():
        if not exp_var.get() or not juegos_var.get() or not linea_var.get():
            aviso_label.config(text="Por favor responde las tres preguntas")
            return
        perfil_jugador["encuesta"] = {
            "experiencia_previa": exp_var.get(),
            "juegos_similares":   juegos_var.get(),
            "linea_preferida":    linea_var.get(),
        }
        mostrar_pregame()  # Va directo al Pre-Game

    btn_continuar = registrar(tk.Button(
        canvas, text="Continuar →", font=F_ENC_CONT,
        bg=COLOR_BTN, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2",
        command=guardar_encuesta
    ))
    btn_continuar.bind("<Enter>", lambda e: btn_continuar.config(bg=COLOR_BTN_HOV))
    btn_continuar.bind("<Leave>", lambda e: btn_continuar.config(bg=COLOR_BTN))
    canvas.create_window(CX(), y_base + espaciado * 3 + 52,
                         anchor="center", window=btn_continuar,
                         width=220, height=50, tags="ui")

    canvas.tag_raise("ui")
    canvas.tag_raise("barra")


def mostrar_pregame():
    limpiar_pantalla()
    _pantalla_activa["fn"] = mostrar_pregame
    actualizar_barra("pregame")

    # Posiciones Y basadas en porcentaje de ALTO_UTIL()
    Y_TITULO     = int(ALTO_UTIL() * 0.07)
    Y_SUBTITULO  = int(ALTO_UTIL() * 0.14)
    Y_LINEA_LBL  = int(ALTO_UTIL() * 0.22)
    Y_SELECTOR   = int(ALTO_UTIL() * 0.28)
    Y_BTNS_EQ    = int(ALTO_UTIL() * 0.36)
    Y_ANALIZAR   = int(ALTO_UTIL() * 0.44)
    Y_RESULTADO  = int(ALTO_UTIL() * 0.52)

    canvas.create_text(ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.05),
                       text="Tu campeón:", font=F_LABEL,
                       fill=COLOR_TEXTO, tags="ui")
    canvas.create_text(ANCHO() - ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.05),
                       text="Campeón enemigo:", font=F_LABEL,
                       fill=COLOR_TEXTO, tags="ui")

    # Fondo opaco detrás de los inputs para que no floten sobre el splash
    _ent_w = ANCHO_LATERAL() - 30
    _ent_h = 34
    _pad   = 6
    for _ex in [ANCHO_LATERAL() // 2, ANCHO() - ANCHO_LATERAL() // 2]:
        _ey = int(ALTO_UTIL() * 0.10)
        canvas.create_rectangle(
            _ex - _ent_w // 2 - _pad, _ey - _ent_h // 2 - _pad,
            _ex + _ent_w // 2 + _pad, _ey + _ent_h // 2 + _pad,
            fill=COLOR_ENTRY_BG, outline="#2a2a3e", tags="ui"
        )
    canvas.create_text(CX(), Y_TITULO,
                       text="FORGE", font=F_TITLE,
                       fill=COLOR_TEXTO, tags="ui")
    canvas.create_text(CX(), Y_SUBTITULO,
                       text="Tu coach. Sin filtros.",
                       font=F_SUB, fill=COLOR_SUBT, tags="ui")
    canvas.create_text(CX(), Y_LINEA_LBL,
                       text="Tu línea:", font=F_LARGE,
                       fill=COLOR_TEXTO, tags="ui")

    input_mi_campeon = registrar(tk.Entry(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        insertbackground=COLOR_TEXTO, relief="flat", width=20,
        highlightthickness=1, highlightbackground="#2a2a3e", highlightcolor="#a86b22"
    ))
    if tiene_contexto():
        input_mi_campeon.insert(0, estado_partida["mi_campeon"]["nombre"])
    canvas.create_window(ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.10),
                         anchor="center", window=input_mi_campeon,
                         width=ANCHO_LATERAL() - 30, tags="ui")

    frame_sug_izq = registrar(tk.Frame(canvas, bg=COLOR_ENTRY_BG, bd=0))
    canvas.create_window(ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.16),
                         anchor="center", window=frame_sug_izq,
                         width=ANCHO_LATERAL() - 10, height=28, tags="ui")

    advertencia_label = registrar(tk.Label(
        canvas, text="", font=F_SMALL, bg=COLOR_ENTRY_BG, fg=COLOR_WARN
    ))
    canvas.create_window(ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.19),
                         anchor="center", window=advertencia_label,
                         width=ANCHO_LATERAL() - 10, tags="ui")

    input_enemigo = registrar(tk.Entry(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        insertbackground=COLOR_TEXTO, relief="flat", width=20,
        highlightthickness=1, highlightbackground="#2a2a3e", highlightcolor="#a86b22"
    ))
    if tiene_contexto():
        input_enemigo.insert(0, estado_partida["campeon_enemigo"]["nombre"])
    canvas.create_window(ANCHO() - ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.10),
                         anchor="center", window=input_enemigo,
                         width=ANCHO_LATERAL() - 30, tags="ui")

    frame_sug_der = registrar(tk.Frame(canvas, bg=COLOR_ENTRY_BG, bd=0))
    canvas.create_window(ANCHO() - ANCHO_LATERAL() // 2, int(ALTO_UTIL() * 0.16),
                         anchor="center", window=frame_sug_der,
                         width=ANCHO_LATERAL() - 10, height=28, tags="ui")

    linea_var = tk.StringVar(value=estado_partida["linea"] if tiene_contexto() else "Top")
    selector_linea = registrar(tk.OptionMenu(
        canvas, linea_var, *LINEAS,
        command=lambda x: verificar_advertencia(input_mi_campeon, linea_var, advertencia_label)
    ))
    selector_linea.config(font=F_LABEL, bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
                          activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
                          relief="flat", width=16, highlightthickness=0, bd=0)
    selector_linea["menu"].config(bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO, font=F_LABEL,
                                  activebackground=COLOR_BTN)
    canvas.create_window(CX(), Y_SELECTOR, anchor="center", window=selector_linea, tags="ui")

    # Botones de equipo
    btn_mi_equipo = registrar(tk.Button(
        canvas, text="👥 Mi Equipo", font=F_BTN_SM,
        bg=COLOR_BTN_EQUIPO, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_EQUIPO_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2",
        command=lambda: abrir_overlay_equipo("mi_equipo", linea_var)
    ))
    btn_mi_equipo.bind("<Enter>", lambda e: btn_mi_equipo.config(bg=COLOR_BTN_EQUIPO_HOV))
    btn_mi_equipo.bind("<Leave>", lambda e: btn_mi_equipo.config(bg=COLOR_BTN_EQUIPO))
    canvas.create_window(CX() - 130, Y_BTNS_EQ, anchor="center", window=btn_mi_equipo,
                         width=200, height=34, tags="ui")

    btn_eq_rival = registrar(tk.Button(
        canvas, text="⚔ Equipo Rival", font=F_BTN_SM,
        bg=COLOR_BTN_EQUIPO, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_EQUIPO_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2",
        command=lambda: abrir_overlay_equipo("equipo_rival", linea_var)
    ))
    btn_eq_rival.bind("<Enter>", lambda e: btn_eq_rival.config(bg=COLOR_BTN_EQUIPO_HOV))
    btn_eq_rival.bind("<Leave>", lambda e: btn_eq_rival.config(bg=COLOR_BTN_EQUIPO))
    canvas.create_window(CX() + 130, Y_BTNS_EQ, anchor="center", window=btn_eq_rival,
                         width=200, height=34, tags="ui")

    boton = registrar(tk.Button(
        canvas, text="Analizar Matchup", font=F_BTN,
        bg=COLOR_BTN, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2", width=20, height=2,
        command=lambda: analizar(input_mi_campeon, input_enemigo, linea_var, boton, resultado_texto)
    ))
    boton.bind("<Enter>", lambda e: boton.config(bg=COLOR_BTN_HOV))
    boton.bind("<Leave>", lambda e: boton.config(bg=COLOR_BTN))
    canvas.create_window(CX(), Y_ANALIZAR, anchor="center", window=boton, tags="ui")

    alto_resultado = ALTO_UTIL() - Y_RESULTADO - 20
    resultado_texto = registrar(tk.Text(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        relief="flat", wrap="word", padx=14, pady=14
    ))
    resultado_texto.insert("1.0", "Aquí aparecerá tu recomendación de build...")
    resultado_texto.configure(state="disabled")
    canvas.create_window(CX(), Y_RESULTADO + alto_resultado // 2,
                         anchor="center", window=resultado_texto,
                         width=int(ANCHO_CENTRO() * 0.88),
                         height=alto_resultado, tags="ui")

    def on_mi_campeon_key(e):
        texto = input_mi_campeon.get()
        mostrar_sugerencias(texto, input_mi_campeon, frame_sug_izq, "izq", linea_var)
        verificar_advertencia(input_mi_campeon, linea_var, advertencia_label)
        # Auto-selección de línea cuando hay match exacto
        campeon = buscar_campeon(texto, champions)
        if campeon:
            linea_auto = detectar_linea_campeon(campeon)
            if linea_auto:
                linea_var.set(linea_auto)

    input_mi_campeon.bind("<KeyRelease>", on_mi_campeon_key)
    input_enemigo.bind("<KeyRelease>", lambda e:
        mostrar_sugerencias(input_enemigo.get(), input_enemigo, frame_sug_der, "der")
    )
    app.bind("<Return>", lambda e: analizar(input_mi_campeon, input_enemigo, linea_var, boton, resultado_texto))

    if tiene_contexto():
        threading.Thread(target=lambda: actualizar_splash_izq(estado_partida["mi_campeon"]["id"]), daemon=True).start()
        threading.Thread(target=lambda: actualizar_splash_der(estado_partida["campeon_enemigo"]["id"]), daemon=True).start()

    canvas.tag_raise("ui")
    canvas.tag_raise("barra")


# ============================================
# PANTALLA IN-GAME
# ============================================
def mostrar_ingame():
    log("mostrar_ingame: inicio")
    limpiar_pantalla()
    _pantalla_activa["fn"] = mostrar_ingame
    log("mostrar_ingame: pantalla limpia")
    actualizar_barra("ingame")

    ancho_caja = int(ANCHO() * 0.55)
    CY_CENTRO  = int(ALTO_UTIL() * 0.48)

    canvas.create_text(CX(), 50,
                       text="IN-GAME COACH", font=F_TITLE,
                       fill=COLOR_TEXTO, tags="ui")

    if tiene_contexto():
        canvas.create_text(CX(), 95,
                           text=f"Partida: {resumen_contexto()}",
                           font=F_SUBTITLE, fill="#44aa44", tags="ui")
    else:
        canvas.create_text(CX(), 95,
                           text="Sin matchup activo — ve al Pre-Game primero para más contexto",
                           font=F_SUBTITLE, fill=COLOR_WARN, tags="ui")

    respuesta_box = registrar(tk.Text(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        relief="flat", wrap="word", padx=16, pady=16,
        state="disabled"
    ))
    canvas.create_window(CX(), CY_CENTRO,
                         anchor="center", window=respuesta_box,
                         width=ancho_caja,
                         height=int(ALTO_UTIL() * 0.45), tags="ui")

    estado_label = registrar(tk.Label(
        canvas, text="", font=F_LABEL,
        bg="black", fg=COLOR_SUBT
    ))
    canvas.create_window(CX(), int(ALTO_UTIL() * 0.78),
                         anchor="center", window=estado_label,
                         width=ancho_caja, tags="ui")

    input_texto = registrar(tk.Entry(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        insertbackground=COLOR_TEXTO, relief="flat",
        highlightthickness=1, highlightbackground="#2a2a3e", highlightcolor="#4a7abf"
    ))
    canvas.create_window(CX() - 60, int(ALTO_UTIL() * 0.87),
                         anchor="center", window=input_texto,
                         width=ancho_caja - 130, height=40, tags="ui")

    btn_enviar = registrar(tk.Button(
        canvas, text="Enviar", font=F_BTN,
        bg=COLOR_BTN, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2"
    ))
    btn_enviar.bind("<Enter>", lambda e: btn_enviar.config(bg=COLOR_BTN_HOV))
    btn_enviar.bind("<Leave>", lambda e: btn_enviar.config(bg=COLOR_BTN))
    canvas.create_window(CX() + (ancho_caja // 2) - 50, int(ALTO_UTIL() * 0.87),
                         anchor="center", window=btn_enviar,
                         width=110, height=40, tags="ui")

    btn_pausa = registrar(tk.Button(
        canvas, text="⏸ Pausar", font=F_BTN,
        bg=COLOR_PAUSADO, fg=COLOR_TEXTO,
        activebackground=COLOR_PAUSADO_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2"
    ))
    btn_pausa.bind("<Enter>", lambda e: btn_pausa.config(bg=COLOR_PAUSADO_HOV))
    btn_pausa.bind("<Leave>", lambda e: btn_pausa.config(bg=COLOR_PAUSADO))
    canvas.create_window(CX(), int(ALTO_UTIL() * 0.93),
                         anchor="center", window=btn_pausa,
                         width=200, height=44, tags="ui")

    btn_enviar.config(command=lambda: procesar_pregunta_texto(
        input_texto, respuesta_box, estado_label, btn_pausa))
    btn_pausa.config(command=lambda: toggle_pausa(
        btn_pausa, respuesta_box, estado_label))

    app.bind("<Return>", lambda e: procesar_pregunta_texto(
        input_texto, respuesta_box, estado_label, btn_pausa))

    canvas.tag_raise("ui")
    canvas.tag_raise("barra")
    log("mostrar_ingame: widgets listos, iniciando loop")
    iniciar_loop(respuesta_box, estado_label, btn_pausa)


# ============================================
# LÓGICA IN-GAME
# ============================================
def set_respuesta(caja, texto):
    caja.config(state="normal")
    caja.delete("1.0", "end")
    caja.insert("1.0", texto)
    caja.config(state="disabled")

def toggle_pausa(btn_pausa, respuesta_box, estado_label):
    if escucha_activa["valor"]:
        escucha_activa["valor"] = False
        btn_pausa.config(text="▶ Reanudar", bg=COLOR_GRABANDO)
        btn_pausa.bind("<Enter>", lambda e: btn_pausa.config(bg=COLOR_GRABANDO_HOV))
        btn_pausa.bind("<Leave>", lambda e: btn_pausa.config(bg=COLOR_GRABANDO))
        estado_label.config(text="Pausado", fg=COLOR_SUBT)
    else:
        btn_pausa.config(text="⏸ Pausar", bg=COLOR_PAUSADO)
        btn_pausa.bind("<Enter>", lambda e: btn_pausa.config(bg=COLOR_PAUSADO_HOV))
        btn_pausa.bind("<Leave>", lambda e: btn_pausa.config(bg=COLOR_PAUSADO))
        iniciar_loop(respuesta_box, estado_label, btn_pausa)

def iniciar_loop(respuesta_box, estado_label, btn_pausa):
    log("iniciar_loop llamado")
    escucha_activa["valor"] = True
    threading.Thread(
        target=lambda: loop_escucha(respuesta_box, estado_label, btn_pausa),
        daemon=True
    ).start()

def _widget_vivo(w):
    try:
        return bool(w.winfo_exists())
    except Exception:
        return False

def _get_mic_index():
    """Busca el índice del micrófono por defecto del sistema."""
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        idx = pa.get_default_input_device_info()["index"]
        pa.terminate()
        return idx
    except Exception:
        return None

def loop_escucha(respuesta_box, estado_label, btn_pausa):
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = False
    mic_index = _get_mic_index()

    while escucha_activa["valor"]:
        try:
            if not _widget_vivo(estado_label):
                break
            app.after(0, lambda: _widget_vivo(estado_label) and estado_label.config(
                text="● Escuchando...", fg="#44aa44"))

            with sr.Microphone(device_index=mic_index) as source:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=8)

            if not escucha_activa["valor"] or not _widget_vivo(estado_label):
                break

            app.after(0, lambda: _widget_vivo(estado_label) and estado_label.config(
                text="Procesando...", fg=COLOR_SUBT))

            pregunta = recognizer.recognize_google(audio, language="es-ES")

            if not escucha_activa["valor"] or not _widget_vivo(estado_label):
                break

            p = pregunta
            app.after(0, lambda t=p: _widget_vivo(estado_label) and estado_label.config(
                text=f'"{t}"', fg=COLOR_SUBT))
            app.after(0, lambda: _widget_vivo(respuesta_box) and set_respuesta(respuesta_box, "Procesando..."))

            escucha_activa["valor"] = False

            respuesta = coach_ingame(pregunta)

            def reanudar(r=respuesta):
                if not _widget_vivo(respuesta_box):
                    return
                set_respuesta(respuesta_box, r)
                hablar(r)
                app.after(2000, lambda: _reanudar_si_activo(
                    respuesta_box, estado_label, btn_pausa))

            app.after(0, reanudar)
            return

        except sr.WaitTimeoutError:
            if not _widget_vivo(estado_label):
                break
            continue
        except sr.UnknownValueError:
            app.after(0, lambda: _widget_vivo(estado_label) and estado_label.config(
                text="No entendí, intenta de nuevo", fg=COLOR_WARN))
            continue
        except Exception as err:
            msg = str(err)
            app.after(0, lambda m=msg: _widget_vivo(estado_label) and estado_label.config(
                text=f"Error: {m}", fg=COLOR_WARN))
            break

def _reanudar_si_activo(respuesta_box, estado_label, btn_pausa):
    if any(w for w in _widgets if isinstance(w, tk.Button) and w.winfo_exists()):
        escucha_activa["valor"] = True
        threading.Thread(
            target=lambda: loop_escucha(respuesta_box, estado_label, btn_pausa),
            daemon=True
        ).start()

def procesar_pregunta_texto(input_widget, respuesta_box, estado_label, btn_pausa):
    pregunta = input_widget.get().strip()
    if not pregunta:
        return
    input_widget.delete(0, "end")
    escucha_activa["valor"] = False
    set_respuesta(respuesta_box, "Procesando...")
    estado_label.config(text="")

    def tarea():
        respuesta = coach_ingame(pregunta)
        app.after(0, lambda: [
            set_respuesta(respuesta_box, respuesta),
            hablar(respuesta),
        ])
        app.after(2500, lambda: _reanudar_si_activo(respuesta_box, estado_label, btn_pausa))

    threading.Thread(target=tarea, daemon=True).start()


# ============================================
# LÓGICA PRE-GAME
# ============================================
def mostrar_sugerencias(texto, input_widget, frame, lado, linea_var=None):
    for w in frame.winfo_children():
        w.destroy()
    for nombre in obtener_sugerencias(texto, champions):
        btn = tk.Button(
            frame, text=nombre, font=F_SMALL,
            bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
            activebackground=COLOR_BTN, activeforeground=COLOR_TEXTO,
            relief="flat", cursor="hand2", padx=4, pady=1,
            command=lambda n=nombre, i=input_widget, f=frame, l=lado, lv=linea_var: seleccionar_sugerencia(n, i, f, l, lv)
        )
        btn.pack(side="left", padx=1)

def seleccionar_sugerencia(nombre, input_widget, frame, lado, linea_var=None):
    input_widget.delete(0, "end")
    input_widget.insert(0, nombre)
    for w in frame.winfo_children():
        w.destroy()
    campeon = buscar_campeon(nombre, champions)
    if campeon:
        if lado == "izq":
            threading.Thread(target=lambda: actualizar_splash_izq(campeon["id"]), daemon=True).start()
            if linea_var:
                linea_auto = detectar_linea_campeon(campeon)
                if linea_auto:
                    linea_var.set(linea_auto)
        else:
            threading.Thread(target=lambda: actualizar_splash_der(campeon["id"]), daemon=True).start()

def verificar_advertencia(input_widget, linea_var, label):
    mi_nombre = input_widget.get().strip()
    linea     = linea_var.get()
    if not mi_nombre:
        label.config(text="")
        return
    campeon = buscar_campeon(mi_nombre, champions)
    if campeon and campeon_inusual_en_linea(campeon, linea):
        label.config(text=f"⚠ {campeon['nombre']} inusual en {linea}")
    else:
        label.config(text="")

def _set_resultado(resultado_texto, texto):
    resultado_texto.config(state="normal")
    resultado_texto.delete("1.0", "end")
    resultado_texto.insert("1.0", texto)
    resultado_texto.config(state="disabled")

def analizar(input_mi_campeon, input_enemigo, linea_var, boton, resultado_texto):
    mi_nombre      = input_mi_campeon.get().strip()
    enemigo_nombre = input_enemigo.get().strip()
    linea          = linea_var.get()

    if not mi_nombre or not enemigo_nombre:
        _set_resultado(resultado_texto, "Por favor escribe los dos campeones.")
        return

    mi_campeon      = buscar_campeon(mi_nombre, champions)
    campeon_enemigo = buscar_campeon(enemigo_nombre, champions)

    if not mi_campeon:
        _set_resultado(resultado_texto, f"No encontré '{mi_nombre}'.")
        return
    if not campeon_enemigo:
        _set_resultado(resultado_texto, f"No encontré '{enemigo_nombre}'.")
        return

    estado_partida["mi_campeon"]      = mi_campeon
    estado_partida["campeon_enemigo"] = campeon_enemigo
    estado_partida["linea"]           = linea

    # Guardar también en el slot correspondiente del equipo propio
    estado_partida["mi_equipo"][linea]    = mi_campeon
    estado_partida["equipo_rival"][linea] = campeon_enemigo

    _set_resultado(resultado_texto, f"Analizando {mi_campeon['nombre']} en {linea} vs {campeon_enemigo['nombre']}...")
    boton.config(state="disabled")
    cerrar_overlay()

    threading.Thread(target=lambda: actualizar_splash_izq(mi_campeon["id"]), daemon=True).start()
    threading.Thread(target=lambda: actualizar_splash_der(campeon_enemigo["id"]), daemon=True).start()

    def tarea():
        rec = recomendar_build(mi_campeon, campeon_enemigo, linea)
        app.after(0, lambda: [_set_resultado(resultado_texto, rec), boton.config(state="normal")])

    threading.Thread(target=tarea, daemon=True).start()


# ============================================
# SPLASHES
# ============================================
def _resize_splash(img):
    ow, oh   = img.size
    target_w = ANCHO_LATERAL()
    target_h = ALTO_SPLASH()
    r        = target_w / ow
    nw, nh   = target_w, int(oh * r)
    if nh < target_h:
        r      = target_h / oh
        nw, nh = int(ow * r), target_h
    img  = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - target_w) // 2
    return img.crop((left, 0, left + target_w, target_h))

def actualizar_splash_izq(champ_id):
    img = get_splash_art(champ_id)
    if img:
        photo = ImageTk.PhotoImage(_resize_splash(img))
        app.after(0, lambda p=photo: _set_splash("izq", p))

def actualizar_splash_der(champ_id):
    img = get_splash_art(champ_id)
    if img:
        photo = ImageTk.PhotoImage(_resize_splash(img))
        app.after(0, lambda p=photo: _set_splash("der", p))

def _set_splash(lado, photo):
    _photos[f"splash_{lado}"] = photo
    canvas.delete(f"splash_{lado}")
    padding = 20
    x = (ANCHO_LATERAL() // 2) + padding if lado == "izq" else ANCHO() - (ANCHO_LATERAL() // 2) - padding
    y = 140 + (ALTO_UTIL() - 140) // 2
    canvas.create_image(x, y, anchor="center", image=photo, tags=f"splash_{lado}")
    canvas.tag_lower(f"splash_{lado}")
    canvas.tag_raise(f"splash_{lado}", "fondo")
    canvas.tag_raise("ui")
    canvas.tag_raise("barra")


# ============================================
# ATAJOS GLOBALES
# ============================================
app.bind("<Escape>", lambda e: app.wm_attributes("-fullscreen", False))
app.bind("<F11>",    lambda e: app.wm_attributes("-fullscreen", True))

_pantalla_activa = {"fn": None}
_resize_timer    = {"id": None}
_ultimo_size     = {"w": 0, "h": 0}

def _on_resize(event):
    if event.widget is not app:
        return
    # Solo redibujar si el TAMAÑO cambió, no si fue foco/posición
    w, h = event.width, event.height
    if w == _ultimo_size["w"] and h == _ultimo_size["h"]:
        return
    _ultimo_size["w"] = w
    _ultimo_size["h"] = h
    if _resize_timer["id"]:
        app.after_cancel(_resize_timer["id"])
    _resize_timer["id"] = app.after(200, _redibujar_pantalla)

def _redibujar_pantalla():
    fn = _pantalla_activa.get("fn")
    log(f"_redibujar: fn={fn.__name__ if fn else None}")
    escucha_activa["valor"] = False
    init_fondo()
    canvas.tag_lower("fondo")
    if fn:
        fn()

app.bind("<Configure>", _on_resize)


# ============================================
# ARRANQUE
# ============================================
app.update()
init_fondo()
canvas.tag_lower("fondo")
mostrar_inicio()

app.mainloop()
