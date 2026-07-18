import os
import sys
import json
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
FORGE_MODEL       = os.getenv("FORGE_MODEL", "claude-sonnet-4-6")

def cargar_perfil_manual():
    """
    Carga datos manuales opcionales desde perfil_manual.json (al lado del .exe/script).
    Útil cuando la cuenta activa no tiene aún historial suficiente en la API de Riot
    (cuenta nueva en un servidor, cambio de región, etc.) pero el jugador sí tiene
    datos reales de otra fuente (ej. maestría de una cuenta vieja) que valen la pena
    darle de contexto a Claude. Si el archivo no existe, simplemente no aporta nada
    — no rompe el flujo normal.
    """
    ruta = os.path.join(BASE_DIR, "perfil_manual.json")
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"cargar_perfil_manual: error leyendo perfil_manual.json — {e}")
        return {}

perfil_manual = cargar_perfil_manual()

# ============================================
# HISTORIAL DE USO (para mostrar "recientes" al abrir la app)
# ============================================
_HISTORIAL_PATH = os.path.join(BASE_DIR, "historial_uso.json")
_HISTORIAL_MAX  = 8

def cargar_historial_uso():
    if not os.path.exists(_HISTORIAL_PATH):
        return []
    try:
        with open(_HISTORIAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"cargar_historial_uso: error leyendo historial — {e}")
        return []

def guardar_entrada_historial(tipo, texto):
    """
    Registra una acción (análisis de Pre-Game o Post-Game) en el historial
    local, para mostrarla como 'recientes' la próxima vez que se abra Forge.
    Nunca debe romper el flujo si falla — es solo un plus visual.
    """
    try:
        import datetime
        historial = cargar_historial_uso()
        historial.insert(0, {
            "fecha": datetime.datetime.now().strftime("%d/%m %H:%M"),
            "tipo":  tipo,   # "pregame" o "postgame"
            "texto": texto,
        })
        historial = historial[:_HISTORIAL_MAX]
        with open(_HISTORIAL_PATH, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"guardar_entrada_historial: error guardando — {e}")

# Recuerda el último Riot ID válido para no tener que escribirlo cada vez
# que se abre Forge — se guarda apenas la cuenta se confirma como existente.
_ULTIMO_ID_PATH = os.path.join(BASE_DIR, "ultimo_riot_id.txt")

def cargar_ultimo_riot_id():
    if not os.path.exists(_ULTIMO_ID_PATH):
        return ""
    try:
        with open(_ULTIMO_ID_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        log(f"cargar_ultimo_riot_id: error leyendo — {e}")
        return ""

def guardar_ultimo_riot_id(riot_id):
    try:
        with open(_ULTIMO_ID_PATH, "w", encoding="utf-8") as f:
            f.write(riot_id.strip())
    except Exception as e:
        log(f"guardar_ultimo_riot_id: error guardando — {e}")

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
    "platform":         None,  # "euw1", "la2", etc. — para construir match IDs a mano
    "routing":          None,  # "europe", "americas", "asia", "sea" — región detectada
    "nivel":            None,
    "rango":            None,  # "Gold II", "Sin rango", etc.
    "partidas_totales": None,
    "campeones_top":    [],    # lista de dicts {nombre, partidas, winrate}
    "tipo":             None,  # "nuevo", "retomando", "activo"
    "encuesta":         {},    # respuestas encuesta jugador nuevo
}

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
# FUNCIONES DE DATOS
# ============================================
def get_version():
    return requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]

def get_champions(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/es_ES/champion.json"
    return requests.get(url).json()["data"]

def get_items(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/es_ES/item.json"
    try:
        return requests.get(url, timeout=10).json()["data"]
    except Exception:
        return {}

# ============================================
# RIOT API — PERFIL DE JUGADOR
# ============================================
RIOT_REGIONS = {
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe",
    "na1":  "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "kr":   "asia", "jp1": "asia",
    "oc1":  "sea", "ph2": "sea", "sg2": "sea", "th2": "sea", "tw2": "sea", "vn2": "sea",
}

# Región dinámica — se detecta automáticamente al cargar el perfil,
# a menos que el usuario la fuerce explícitamente vía RIOT_REGION en el .env
# (útil cuando el "active shard" que reporta Riot está desactualizado,
# por ejemplo justo después de una transferencia/cambio de servidor).
_region_forzada  = os.getenv("RIOT_REGION")  # None si no está definida en el .env
_region_platform = _region_forzada or "euw1"
_region_routing  = RIOT_REGIONS.get(_region_platform, "europe")

def riot_get(url, params=None):
    headers = {"X-Riot-Token": RIOT_API_KEY}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
    except Exception as e:
        log(f"riot_get: excepción de red — {e} — url={url}")
        return None
    if r.status_code == 200:
        return r.json()
    if r.status_code == 403:
        log(f"riot_get: 403 Forbidden — la API key probablemente expiró o es inválida — url={url}")
    elif r.status_code == 429:
        log(f"riot_get: 429 Rate limit excedido — url={url}")
    elif r.status_code == 404:
        log(f"riot_get: 404 No encontrado (normal si aún no hay datos) — url={url}")
    else:
        log(f"riot_get: status {r.status_code} inesperado — url={url}")
    return None

def detectar_region(puuid):
    """
    Detecta el servidor de LoL donde está activa la cuenta.
    Si RIOT_REGION está definida en el .env, se respeta esa región manual
    y NO se auto-detecta (Riot puede tardar en actualizar el "active shard"
    tras un cambio de servidor reciente).
    """
    if _region_forzada:
        log(f"detectar_region: usando región forzada por .env — {_region_platform}")
        return _region_platform, _region_routing

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

def obtener_historial(puuid, routing, count=30, queue=None):
    """
    Trae IDs de partidas recientes. Si queue=None, trae de cualquier modo
    (normal, ranked, ARAM, etc.) — necesario para jugadores que no tienen
    partidas ranked todavía.
    """
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"count": count}
    if queue is not None:
        params["queue"] = queue
    return riot_get(url, params=params) or []

def obtener_detalle_partida(match_id, routing):
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return riot_get(url)

def obtener_timeline_partida(match_id, routing):
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
    return riot_get(url)

def extraer_eventos_relevantes(timeline, detalle, participant_id, items_data=None):
    """
    Filtra el timeline completo de la partida a solo los eventos que
    involucran directamente al participante indicado (o le afectan):
    kills/deaths/asistencias, wards puestos/destruidos por él, objetivos
    tomados por cualquiera de los dos equipos, estructuras caídas, y sus
    compras de ítems.
    Devuelve una lista de strings en orden cronológico, ej: "[8.2min] Pusiste ward".
    Si algo falla o el timeline no trae lo esperado, devuelve [] sin romper nada
    — Riot puede cambiar campos del timeline sin previo aviso.
    """
    try:
        participantes = detalle.get("info", {}).get("participants", [])
        yo = next((p for p in participantes if p.get("participantId") == participant_id), None)
        if not yo:
            return []
        mi_id     = yo.get("participantId")
        mi_team   = yo.get("teamId")
        nombre_por_id = {p.get("participantId"): p.get("championName", "?") for p in participantes}

        eventos = []  # lista de (timestamp_ms, texto)
        frames = timeline.get("info", {}).get("frames", [])

        for frame in frames:
            for ev in frame.get("events", []):
                tipo  = ev.get("type")
                ts_ms = ev.get("timestamp", 0)
                ts_min = round(ts_ms / 60000, 1)
                texto = None

                if tipo == "CHAMPION_KILL":
                    killer   = ev.get("killerId")
                    victim   = ev.get("victimId")
                    asist    = ev.get("assistingParticipantIds", []) or []
                    if mi_id in ([killer, victim] + asist):
                        kn = nombre_por_id.get(killer, "ejecución de equipo") if killer else "ejecución de equipo"
                        vn = nombre_por_id.get(victim, "?")
                        roles = []
                        if killer == mi_id: roles.append("TÚ mataste")
                        if victim == mi_id: roles.append("TE MATARON")
                        if mi_id in asist:  roles.append("diste asistencia")
                        texto = f"[{ts_min}min] {' / '.join(roles)}: {kn} → {vn}"

                elif tipo == "WARD_PLACED":
                    if ev.get("creatorId") == mi_id:
                        wt = ev.get("wardType", "centinela")
                        texto = f"[{ts_min}min] Pusiste un {wt.lower()}"

                elif tipo == "WARD_KILL":
                    if ev.get("killerId") == mi_id:
                        texto = f"[{ts_min}min] Destruiste un centinela enemigo"

                elif tipo == "ITEM_PURCHASED":
                    if ev.get("participantId") == mi_id:
                        item_id = ev.get("itemId")
                        nombre_item = str(item_id)
                        if items_data:
                            info_item = items_data.get(str(item_id))
                            if info_item:
                                nombre_item = info_item.get("name", str(item_id))
                        texto = f"[{ts_min}min] Compraste {nombre_item}"

                elif tipo == "ELITE_MONSTER_KILL":
                    killer_team = ev.get("killerTeamId")
                    monstruo    = ev.get("monsterType", "objetivo")
                    equipo_txt  = "Tu equipo" if killer_team == mi_team else "El equipo rival"
                    texto = f"[{ts_min}min] {equipo_txt} tomó {monstruo}"

                elif tipo == "BUILDING_KILL":
                    equipo_dueño = ev.get("teamId")  # equipo AL QUE PERTENECÍA la estructura
                    building     = ev.get("buildingType", "estructura")
                    if equipo_dueño == mi_team:
                        texto = f"[{ts_min}min] Tu equipo perdió una {building}"
                    else:
                        texto = f"[{ts_min}min] Tu equipo destruyó una {building} rival"

                if texto:
                    eventos.append((ts_ms, texto))

        eventos.sort(key=lambda x: x[0])
        return [t for _, t in eventos]
    except Exception as e:
        log(f"extraer_eventos_relevantes: error procesando timeline — {e}")
        return []

# Colas más comunes — Riot puede agregar/cambiar IDs, si aparece uno nuevo
# simplemente cae en el fallback "Modo desconocido" sin romper nada.
QUEUE_ID_A_MODO = {
    400: "Normal (Draft)",
    420: "Ranked Solo/Dúo",
    430: "Normal (Blind)",
    440: "Ranked Flex",
    450: "ARAM",
    900: "URF",
    1700: "Arena",
}

def _extraer_stats_de_partida(match_id, detalle, puuid=None, participant_id=None):
    """
    Extrae las estadísticas relevantes de un participante dentro de un
    detalle de partida ya descargado. Se puede identificar al participante
    por puuid (caso normal) o por participant_id (cuando el jugador eligió
    manualmente a quién seguir, ej. porque su cuenta no aparece en la partida
    por el tema del shard desactualizado de Riot).
    """
    info = detalle.get("info", {})
    participantes = info.get("participants", [])
    if participant_id is not None:
        yo = next((p for p in participantes if p.get("participantId") == participant_id), None)
    else:
        yo = next((p for p in participantes if p.get("puuid") == puuid), None)
    if not yo:
        return None

    duracion_min = round(info.get("gameDuration", 0) / 60, 1)
    items_ids = [yo.get(f"item{i}", 0) for i in range(6)]
    items_ids = [i for i in items_ids if i and i != 0]
    modo = QUEUE_ID_A_MODO.get(info.get("queueId"), "Modo desconocido")

    return {
        "match_id":         match_id,
        "_detalle_raw":     detalle,
        "participant_id":   yo.get("participantId"),
        "campeon":          yo.get("championName", "Desconocido"),
        "linea":            yo.get("teamPosition", "") or yo.get("individualPosition", ""),
        "modo":             modo,
        "victoria":         yo.get("win", False),
        "kills":            yo.get("kills", 0),
        "deaths":           yo.get("deaths", 0),
        "assists":          yo.get("assists", 0),
        "cs":               yo.get("totalMinionsKilled", 0) + yo.get("neutralMinionsKilled", 0),
        "duracion_min":     duracion_min,
        "oro":              yo.get("goldEarned", 0),
        "daño_campeones":   yo.get("totalDamageDealtToChampions", 0),
        "daño_recibido":    yo.get("totalDamageTaken", 0),
        "vision_score":     yo.get("visionScore", 0),
        "items_ids":        items_ids,
    }

def obtener_ultima_partida_stats(puuid, routing):
    """
    Trae la partida más reciente del jugador (cualquier modo) y devuelve un dict
    con las estadísticas relevantes de SU participante, o None si falla.
    """
    match_ids = obtener_historial(puuid, routing, count=1)
    if not match_ids:
        return None
    match_id = match_ids[0]
    detalle = obtener_detalle_partida(match_id, routing)
    if not detalle:
        return None
    return _extraer_stats_de_partida(match_id, detalle, puuid=puuid)

def normalizar_match_id(texto_usuario, platform):
    """
    Acepta lo que el usuario escriba para identificar una partida y devuelve
    el match ID completo que espera la API ('EUW1_7921802664').
    - Si ya viene con prefijo y guion bajo, se respeta tal cual (en mayúsculas).
    - Si el usuario solo pega el número, se le agrega el prefijo de la
      plataforma actual (ej. 'EUW1_').
    """
    texto = texto_usuario.strip()
    if not texto:
        return None
    if "_" in texto:
        return texto.upper()
    return f"{platform.upper()}_{texto}"

def listar_participantes(detalle):
    """
    Devuelve una lista legible de los 10 participantes de una partida
    (campeón, línea, equipo) para que el jugador elija a cuál seguir cuando
    su propia cuenta no aparece identificada en esa partida.
    """
    participantes = detalle.get("info", {}).get("participants", [])
    lista = []
    for p in participantes:
        equipo = "Azul" if p.get("teamId") == 100 else "Rojo"
        linea = p.get("teamPosition", "") or p.get("individualPosition", "") or "?"
        lista.append({
            "participant_id": p.get("participantId"),
            "campeon":         p.get("championName", "?"),
            "linea":           linea,
            "equipo":          equipo,
        })
    return sorted(lista, key=lambda x: x["participant_id"])

def obtener_partida_stats_por_id(match_id_usuario, platform, routing, puuid=None, participant_id=None):
    """
    Trae y extrae estadísticas de un match ID específico escrito a mano.
    - Si se identifica al jugador por puuid y SÍ aparece en la partida, listo.
    - Si NO aparece (cuenta equivocada, shard desactualizado, o simplemente
      es la partida de otra persona), devuelve la lista de participantes
      para que el jugador elija manualmente a quién seguir.
    - Si se pasa participant_id directamente, se usa ese sin más vueltas
      (caso: el jugador ya eligió de la lista).
    Devuelve un dict: {"stats": ...} o {"error": "..."} o {"participantes": [...], "match_id": ...}
    """
    match_id = normalizar_match_id(match_id_usuario, platform)
    if not match_id:
        return {"error": "ID de partida vacío."}
    detalle = obtener_detalle_partida(match_id, routing)
    if not detalle:
        return {"error": f"No encontré la partida '{match_id}'. Verifica el ID o que sea de esta región."}

    if participant_id is not None:
        stats = _extraer_stats_de_partida(match_id, detalle, participant_id=participant_id)
        if not stats:
            return {"error": "No encontré ese número de participante en la partida."}
        return {"stats": stats}

    stats = _extraer_stats_de_partida(match_id, detalle, puuid=puuid)
    if stats:
        return {"stats": stats}

    # No apareces con tu puuid — probablemente el shard de Riot todavía no
    # reconoce tu cuenta en esta región, o el ID es de otra partida. En vez
    # de solo fallar, ofrecemos elegir a cuál de los 10 jugadores seguir.
    return {"participantes": listar_participantes(detalle), "match_id": match_id}


def analizar_postgame(stats, items_data=None):
    """
    Genera una crítica post-partida en el tono de Forge, basada en las
    estadísticas finales del partido (no hay timeline, así que la crítica
    se apoya en proporciones: CS/min, KDA, daño vs oro, visión).
    """
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    cs_por_min = round(stats["cs"] / stats["duracion_min"], 1) if stats["duracion_min"] > 0 else 0
    resultado  = "GANASTE" if stats["victoria"] else "PERDISTE"

    nombres_items = []
    if items_data:
        for iid in stats["items_ids"]:
            item_info = items_data.get(str(iid))
            if item_info:
                nombres_items.append(item_info.get("name", str(iid)))
    items_texto = ", ".join(nombres_items) if nombres_items else "sin datos de ítems"

    ctx_perfil = contexto_perfil_para_prompt()
    extra_perfil = f"\n{ctx_perfil}" if ctx_perfil else ""

    prompt = f"""Eres Forge, un coach de League of Legends analizando una partida ya terminada. Tu tono es directo y filoso, con humor calibrado — no insultos genéricos, sino observaciones jocosas que usan jerga correcta del juego y siempre van pegadas a una instrucción accionable. El chiste nace del error específico, no de insultar por insultar.

Escribe todo en español — sin mezclar términos en inglés. Usa el nombre tal como aparece en el cliente de LoL en español. Si no tienes certeza del nombre oficial en español de algo, no inventes ni dejes el término en inglés: descríbelo por su efecto.

Importante: NO tienes el timeline de la partida (jugadas minuto a minuto), solo el resultado final. No inventes decisiones específicas que no puedes saber ("no rotaste a la torre en el minuto 14") — en su lugar, lee las señales que SÍ tienes (KDA, CS/min, oro, daño hecho vs recibido, visión) y saca conclusiones honestas sobre qué patrón revelan esos números, dejando claro cuando es una inferencia y no un hecho observado.

Esta partida fue en modo {stats['modo']}. Adapta la crítica al modo: en ARAM no hay líneas ni farmeo real de jungla, así que el CS y la visión pesan mucho menos que el daño y la supervivencia en peleas; en Normal o Ranked de Grieta del Invocador sí aplican todas las métricas de línea normalmente.
{extra_perfil}

Datos de la partida:
- Modo: {stats['modo']}
- Campeón: {stats['campeon']} ({stats['linea']})
- Resultado: {resultado}
- KDA: {stats['kills']}/{stats['deaths']}/{stats['assists']}
- CS: {stats['cs']} en {stats['duracion_min']} minutos ({cs_por_min} por minuto)
- Oro ganado: {stats['oro']}
- Daño a campeones: {stats['daño_campeones']}
- Daño recibido: {stats['daño_recibido']}
- Puntuación de visión: {stats['vision_score']}
- Build final: {items_texto}

Estructura exacta, sin títulos numerados:

LECTURA GENERAL
Una o dos líneas sobre qué cuentan estos números en conjunto — ¿fue una partida de farmeo pobre, de exceso de riesgo, de buen impacto en peleas pero mal manejo de línea, etc.? Basado solo en los datos de arriba.

LO QUE MÁS PESÓ
La única métrica que más explica el resultado (CS/min bajo, muertes altas, visión baja, lo que sea). Explica por qué esa es la señal clave y qué hacer distinto la próxima vez.

PARA LA PRÓXIMA
Una sola acción concreta y medible para la siguiente partida con este campeón o rol.

PARA MEJORAR
Una recomendación de práctica o hábito de entrenamiento — no una jugada puntual de la próxima partida, sino algo que se repite y se entrena con el tiempo — ligada directamente al patrón que identificaste en LO QUE MÁS PESÓ. Sé específico: no "mejora tu visión", sino algo medible y repetible que ataque la causa de raíz.

Sin relleno. Sin lista de todas las estadísticas repetidas. Ni un solo término en inglés en toda la respuesta."""

    msg = cliente.messages.create(
        model=FORGE_MODEL,
        max_tokens=850,
        messages=[{"role": "user", "content": prompt}]
    )
    return limpiar_markdown(msg.content[0].text)

def analizar_postgame_timeline(stats, eventos, items_data=None):
    """
    Genera la crítica post-partida usando el timeline completo de eventos
    (cronología real: wards, muertes, objetivos, compras) en vez de solo el
    resultado final. Se manda TODO el contexto cronológico en una sola llamada
    — no fase por fase separada — para que Claude pueda conectar causas con
    consecuencias (ej. un ward que expiró en el minuto 8 explicando una muerte
    en el minuto 13).
    """
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    resultado = "GANASTE" if stats["victoria"] else "PERDISTE"

    nombres_items = []
    if items_data:
        for iid in stats["items_ids"]:
            item_info = items_data.get(str(iid))
            if item_info:
                nombres_items.append(item_info.get("name", str(iid)))
    items_texto = ", ".join(nombres_items) if nombres_items else "sin datos de ítems"

    ctx_perfil = contexto_perfil_para_prompt()
    extra_perfil = f"\n{ctx_perfil}" if ctx_perfil else ""

    cronologia = "\n".join(eventos) if eventos else "Sin eventos registrados."

    prompt = f"""Eres Forge, un coach de League of Legends analizando una partida ya terminada. Tu tono es directo y filoso, con humor calibrado — no insultos genéricos, sino observaciones jocosas que usan jerga correcta del juego y siempre van pegadas a una instrucción accionable. El chiste nace del error específico, no de insultar por insultar.

Escribe todo en español — sin mezclar términos en inglés. Usa el nombre tal como aparece en el cliente de LoL en español. Si no tienes certeza del nombre oficial en español de algo, no inventes ni dejes el término en inglés: descríbelo por su efecto.

Esta vez SÍ tienes la cronología real de la partida, minuto a minuto — no son estadísticas finales, son los eventos reales en el orden en que pasaron: dónde puso centinelas, cuándo lo mataron, cuándo mató él, qué objetivos se tomaron, qué compró. Úsala para conectar causas con consecuencias: si un centinela puesto en el minuto 8 explica una muerte en el minuto 13, dilo explícitamente. Esa cadena causal es exactamente lo que hace valioso este análisis frente a uno que solo mira el resultado final.

No inventes nada que no esté en la cronología de abajo. Si algo no aparece registrado (ej. posicionamiento exacto en una pelea de equipo), no lo inventes — trabaja con lo que sí tienes.

Esta partida fue en modo {stats['modo']}. Adapta la crítica al modo: en ARAM no hay líneas ni farmeo real de jungla, así que el posicionamiento en peleas pesa más que la visión de línea; en Normal o Ranked de Grieta del Invocador sí aplican todas las dinámicas de línea normalmente.
{extra_perfil}

Resumen de la partida:
- Modo: {stats['modo']}
- Campeón: {stats['campeon']} ({stats['linea']})
- Resultado: {resultado}
- KDA: {stats['kills']}/{stats['deaths']}/{stats['assists']}
- Duración: {stats['duracion_min']} minutos
- Build final: {items_texto}

Cronología de eventos relevantes para este jugador (orden real, minuto a minuto):
{cronologia}

Estructura exacta, sin títulos numerados:

LA CADENA
La secuencia causal más importante de la partida — un error temprano (visión, posicionamiento, timing) que llevó a una consecuencia mayor después. Cita los minutos exactos de la cronología. Si hay más de una cadena así, quédate solo con la más determinante para el resultado.

EL MOMENTO CLAVE
Un solo evento puntual (una muerte, una pelea, un objetivo perdido) que más cambió el rumbo de la partida, y qué se pudo hacer distinto justo ahí.

PARA LA PRÓXIMA
Una sola acción concreta y medible para la siguiente partida, ligada directamente a la cadena que identificaste arriba.

PARA MEJORAR
Una recomendación de práctica o hábito de entrenamiento — no una jugada puntual de la próxima partida, sino algo que se repite y se entrena con el tiempo — que ataque la causa de raíz detrás de LA CADENA que identificaste. Sé específico y medible: qué practicar, cómo, y cómo sabría el jugador que está mejorando en eso.

Sin relleno. Sin repetir toda la cronología. Ni un solo término en inglés en toda la respuesta."""

    msg = cliente.messages.create(
        model=FORGE_MODEL,
        max_tokens=1100,
        messages=[{"role": "user", "content": prompt}]
    )
    return limpiar_markdown(msg.content[0].text)

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

        guardar_ultimo_riot_id(riot_id_completo)

        # Detectar región automáticamente
        platform, routing = detectar_region(puuid)

        summoner = obtener_summoner(puuid, platform)

        # Cuenta sin partidas aún — summoner profile no existe todavía
        if not summoner:
            perfil_jugador["riot_id"]          = riot_id_completo
            perfil_jugador["puuid"]            = puuid
            perfil_jugador["platform"]         = platform
            perfil_jugador["routing"]          = routing
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

        # Si no hay historial de partidas, ir directo a encuesta sin descargar nada
        if partidas_totales == 0:
            perfil_jugador["riot_id"]          = riot_id_completo
            perfil_jugador["puuid"]            = puuid
            perfil_jugador["platform"]         = platform
            perfil_jugador["routing"]          = routing
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
        perfil_jugador["platform"]         = platform
        perfil_jugador["routing"]          = routing
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
    lineas = []

    if tiene_perfil():
        p = perfil_jugador
        lineas.append("Perfil del jugador (datos en vivo de Riot API):")
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

    if perfil_manual:
        maestria = perfil_manual.get("maestria_campeones", [])
        if maestria:
            top_maestria = sorted(maestria, key=lambda c: c.get("puntos", 0), reverse=True)[:8]
            texto_maestria = ", ".join([f"{c['campeon']} ({c['puntos']:,} pts)" for c in top_maestria])
            lineas.append("Maestría de campeón cargada manualmente (fuente externa, no vive de la API activa ahora mismo):")
            lineas.append(f"  - {texto_maestria}")
            nota = perfil_manual.get("nota")
            if nota:
                lineas.append(f"  - Nota: {nota}")
            lineas.append("  - Trata esto como señal de con qué campeones tiene experiencia real el jugador, no como estado actual de su cuenta activa.")

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

    prompt = f"""Eres Forge, un coach de League of Legends. Tu tono es directo y filoso, con humor calibrado — no insultos genéricos, sino observaciones jocosas que usan jerga correcta del juego y siempre van pegadas a una instrucción accionable. El chiste nace del error específico, no de insultar por insultar.

Ejemplos del tono exacto que quieres (úsalos como referencia de estilo, no los repitas literal):
- "Actuaste como idiota protegiendo un ward en vez de ir a la teamfight — la próxima vez, rota con tu equipo, el ward se puede reponer, la torre no."
- "Comprar Doran's Shield contra {campeon_enemigo['nombre']} es cargar un paraguas en un huracán. Necesitas algo que realmente frene el daño."
- "Farmear bajo torre contra un all-in early es peor plan que ir a all-in tú mismo sin runas — juega con distancia."

No suavices la crítica ni la disfraces de sugerencia amable. Tampoco insultes sin razón — cada línea filosa debe explicar exactamente qué hizo mal y qué hacer en su lugar.
{instruccion_tono}
{extra_perfil}
El jugador usa: {mi_campeon['nombre']} ({', '.join(mi_campeon['tags'])})
Línea: {linea}
Enemigo directo: {campeon_enemigo['nombre']} ({', '.join(campeon_enemigo['tags'])})
{extra}

Escribe todo en español — sin mezclar términos en inglés. Esto aplica a runas, hechizos de invocador, habilidades e ítems por igual, no solo a ítems. Usa el nombre tal como aparece en el cliente de LoL en español (ej. "Filo de Doran", no "Doran's Blade"). Si no tienes certeza del nombre oficial en español de una runa o habilidad específica, no inventes ni dejes el término en inglés: descríbela por su efecto ("la runa de movilidad reactiva que cura al golpear", "su habilidad de daño en área que se puede cargar").

Da una guía de arranque para los primeros minutos. Estructura exacta, sin títulos numerados:

RUNAS
Runa clave (keystone) recomendada y árbol secundario para este matchup. Una línea explicando por qué esa elección contra {campeon_enemigo['nombre']}. Solo lo esencial, sin listar cada runa menor.

ARRANQUE
Ítem(s) de arranque y pociones. Una línea explicando por qué contra {campeon_enemigo['nombre']}.

NIVELES 1-6
Qué habilidad subir primero y por qué. Cómo jugar el early. Una o dos mecánicas clave de {mi_campeon['nombre']} que el jugador debe usar desde ya.

PRIMER ÍTEM COMPLETO
Qué construir primero y por qué es la prioridad contra este matchup.

CONSEJO DEL MATCHUP
Una sola cosa concreta que define ganar o perder esta línea. Sin suavizar.

Sin relleno. Sin lista de build completa. Ni un solo término en inglés en toda la respuesta."""

    msg = cliente.messages.create(
        model=FORGE_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return limpiar_markdown(msg.content[0].text)

# ============================================
# APP
# ============================================
app = tk.Tk()
app.title("Forge")
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
items_ddragon = get_items(version)

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
    espaciado = 140
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
    hacer_btn("POST-GAME", mostrar_postgame, CX() + espaciado, es_activo=(modulo_activo == "postgame"))

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

    # --- HISTORIAL RECIENTE (tipo "búsquedas recientes") ---
    historial = cargar_historial_uso()
    if historial:
        y_hist = y_bloque + 100
        canvas.create_text(CX(), y_hist,
                           text="Recientes", font=F_SUB, fill=COLOR_SUBT, tags="ui")
        etiqueta = {"pregame": "Pre-Game", "postgame": "Post-Game"}
        for i, entrada in enumerate(historial[:4]):
            tipo_txt = etiqueta.get(entrada.get("tipo"), "")
            texto_linea = f"{entrada.get('fecha','')}  ·  {tipo_txt}: {entrada.get('texto','')}"
            canvas.create_text(CX(), y_hist + 22 + i * 20,
                               text=texto_linea, font=F_SMALL, fill=COLOR_SUBT, tags="ui")

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
    # Prioridad: perfil ya cargado en esta sesión > último ID recordado > vacío
    valor_inicial = perfil_jugador["riot_id"] or cargar_ultimo_riot_id()
    entry_riot.insert(0, valor_inicial or "")
    entry_riot.config(fg=COLOR_SUBT if not valor_inicial else COLOR_TEXTO)

    # Placeholder
    if not valor_inicial:
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
# PANTALLA POST-GAME
# ============================================
def mostrar_postgame():
    limpiar_pantalla()
    _pantalla_activa["fn"] = mostrar_postgame
    actualizar_barra("postgame")

    canvas.create_text(CX(), int(ALTO_UTIL() * 0.08),
                       text="POST-GAME", font=F_TITLE,
                       fill=COLOR_TEXTO, tags="ui")

    if not tiene_perfil():
        canvas.create_text(CX(), int(ALTO_UTIL() * 0.20),
                           text="Necesitas cargar tu Riot ID desde la pantalla de inicio\npara revisar tu última partida.",
                           font=F_SUBTITLE, fill=COLOR_WARN, tags="ui", justify="center")
        canvas.tag_raise("ui")
        canvas.tag_raise("barra")
        return

    canvas.create_text(CX(), int(ALTO_UTIL() * 0.14),
                       text=f"Cuenta cargada: {perfil_jugador['riot_id']}",
                       font=F_SUBTITLE, fill=COLOR_SUBT, tags="ui")

    canvas.create_text(CX(), int(ALTO_UTIL() * 0.185),
                       text="ID de partida específica (opcional) — déjalo vacío para tu última partida",
                       font=F_SUB, fill=COLOR_SUBT, tags="ui")

    entry_match_id = registrar(tk.Entry(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        insertbackground=COLOR_TEXTO, relief="flat",
        highlightthickness=1, highlightbackground="#2a2a3e", highlightcolor="#4a7abf",
        justify="center"
    ))
    canvas.create_window(CX(), int(ALTO_UTIL() * 0.225), anchor="center",
                         window=entry_match_id, width=320, height=32, tags="ui")

    boton = registrar(tk.Button(
        canvas, text="Analizar Partida", font=F_BTN,
        bg=COLOR_BTN, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2", width=24, height=2
    ))
    boton.bind("<Enter>", lambda e: boton.config(bg=COLOR_BTN_HOV))
    boton.bind("<Leave>", lambda e: boton.config(bg=COLOR_BTN))
    canvas.create_window(CX(), int(ALTO_UTIL() * 0.32), anchor="center", window=boton, tags="ui")

    y_resultado = int(ALTO_UTIL() * 0.40)
    alto_resultado = int(ALTO_UTIL() * 0.40)
    resultado_texto = registrar(tk.Text(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        relief="flat", wrap="word", padx=16, pady=16
    ))
    resultado_texto.insert("1.0", "Dale click a \"Analizar Partida\" para revisar qué pasó — sin adornos.\n\nDeja el campo de ID vacío para analizar tu última partida, o pega un ID específico para revisar esa en concreto.")
    resultado_texto.configure(state="disabled")
    canvas.create_window(CX(), y_resultado + alto_resultado // 2,
                         anchor="center", window=resultado_texto,
                         width=int(ANCHO() * 0.6),
                         height=alto_resultado, tags="ui")

    y_seleccion = y_resultado + alto_resultado + 30

    # Fila de selección manual de participante — se queda oculta hasta que
    # una partida no reconozca al jugador y ofrezcamos elegir a quién seguir.
    entry_seleccion = registrar(tk.Entry(
        canvas, font=F_BODY,
        bg=COLOR_ENTRY_BG, fg=COLOR_TEXTO,
        insertbackground=COLOR_TEXTO, relief="flat",
        highlightthickness=1, highlightbackground="#2a2a3e", highlightcolor="#4a7abf",
        justify="center"
    ))
    boton_seleccion = registrar(tk.Button(
        canvas, text="Seguir a este jugador", font=F_BTN,
        bg=COLOR_BTN, fg=COLOR_TEXTO,
        activebackground=COLOR_BTN_HOV, activeforeground=COLOR_TEXTO,
        relief="flat", cursor="hand2"
    ))
    boton_seleccion.bind("<Enter>", lambda e: boton_seleccion.config(bg=COLOR_BTN_HOV))
    boton_seleccion.bind("<Leave>", lambda e: boton_seleccion.config(bg=COLOR_BTN))

    win_entry_sel  = canvas.create_window(CX() - 90, y_seleccion, anchor="center",
                                          window=entry_seleccion, width=110, height=30, tags="ui", state="hidden")
    win_boton_sel  = canvas.create_window(CX() + 60, y_seleccion, anchor="center",
                                          window=boton_seleccion, width=200, height=34, tags="ui", state="hidden")

    contexto_seleccion = {"participantes": [], "match_id": None}

    def mostrar_selector(visible):
        estado = "normal" if visible else "hidden"
        canvas.itemconfigure(win_entry_sel, state=estado)
        canvas.itemconfigure(win_boton_sel, state=estado)

    boton.config(command=lambda: analizar_partida_ui(
        boton, resultado_texto, entry_match_id, contexto_seleccion, mostrar_selector, entry_seleccion
    ))
    boton_seleccion.config(command=lambda: confirmar_seleccion_participante(
        boton, resultado_texto, entry_seleccion, contexto_seleccion, mostrar_selector
    ))

    canvas.tag_raise("ui")
    canvas.tag_raise("barra")


# ============================================
# LÓGICA POST-GAME
# ============================================
def _formatear_lista_participantes(participantes):
    lineas = ["No encontré tu cuenta en esta partida (puede ser el tema del shard de Riot, o es la partida de alguien más).",
              "", "Elige a quién seguir escribiendo su número abajo:"]
    for i, p in enumerate(participantes, start=1):
        lineas.append(f"  {i}. {p['campeon']} — {p['linea']} — Equipo {p['equipo']}")
    return "\n".join(lineas)

def _ejecutar_analisis_completo(stats, routing, resultado_texto, boton):
    """Trae el timeline, arma el análisis, y lo muestra — reutilizado por
    el flujo normal y por el flujo de selección manual de participante."""
    app.after(0, lambda: _set_resultado(resultado_texto, "Partida encontrada. Trayendo la cronología minuto a minuto..."))

    texto = None
    timeline = obtener_timeline_partida(stats["match_id"], routing)
    if timeline:
        eventos = extraer_eventos_relevantes(timeline, stats["_detalle_raw"], stats["participant_id"], items_ddragon)
        if eventos:
            log(f"_ejecutar_analisis_completo: timeline OK, {len(eventos)} eventos relevantes")
            texto = analizar_postgame_timeline(stats, eventos, items_ddragon)

    if not texto:
        log("_ejecutar_analisis_completo: timeline no disponible, usando fallback de estadísticas finales")
        texto = analizar_postgame(stats, items_ddragon)

    resultado_txt = "Victoria" if stats["victoria"] else "Derrota"
    guardar_entrada_historial("postgame", f"{stats['campeon']} ({stats['linea']}) — {resultado_txt}")

    app.after(0, lambda: [
        _set_resultado(resultado_texto, texto),
        boton.config(state="normal"),
    ])

def analizar_partida_ui(boton, resultado_texto, entry_match_id, contexto_seleccion, mostrar_selector, entry_seleccion):
    match_id_usuario = entry_match_id.get().strip()
    boton.config(state="disabled")
    mostrar_selector(False)
    entry_seleccion.delete(0, "end")

    def tarea():
        try:
            routing  = perfil_jugador.get("routing")  or _region_routing
            platform = perfil_jugador.get("platform") or _region_platform

            if match_id_usuario:
                app.after(0, lambda: _set_resultado(resultado_texto, f"Buscando la partida '{match_id_usuario}'..."))
                resultado = obtener_partida_stats_por_id(match_id_usuario, platform, routing, puuid=perfil_jugador["puuid"])
            else:
                app.after(0, lambda: _set_resultado(resultado_texto, "Buscando tu última partida..."))
                stats_ultima = obtener_ultima_partida_stats(perfil_jugador["puuid"], routing)
                resultado = {"stats": stats_ultima} if stats_ultima else {"error": "No encontré partidas recientes en tu cuenta para analizar."}

            if resultado.get("error"):
                app.after(0, lambda: [
                    _set_resultado(resultado_texto, resultado["error"]),
                    boton.config(state="normal"),
                ])
                return

            if resultado.get("participantes"):
                contexto_seleccion["participantes"] = resultado["participantes"]
                contexto_seleccion["match_id"] = resultado["match_id"]
                texto_lista = _formatear_lista_participantes(resultado["participantes"])
                app.after(0, lambda: [
                    _set_resultado(resultado_texto, texto_lista),
                    boton.config(state="normal"),
                    mostrar_selector(True),
                ])
                return

            stats = resultado["stats"]
            _ejecutar_analisis_completo(stats, routing, resultado_texto, boton)
        except Exception as e:
            msg = str(e)
            app.after(0, lambda: [
                _set_resultado(resultado_texto, f"Error analizando la partida: {msg}"),
                boton.config(state="normal"),
            ])

    threading.Thread(target=tarea, daemon=True).start()

def confirmar_seleccion_participante(boton, resultado_texto, entry_seleccion, contexto_seleccion, mostrar_selector):
    texto_num = entry_seleccion.get().strip()
    participantes = contexto_seleccion.get("participantes", [])
    if not texto_num.isdigit() or not (1 <= int(texto_num) <= len(participantes)):
        _set_resultado(resultado_texto, f"Escribe un número entre 1 y {len(participantes)}.")
        return

    elegido = participantes[int(texto_num) - 1]
    match_id = contexto_seleccion["match_id"]
    boton.config(state="disabled")
    mostrar_selector(False)
    _set_resultado(resultado_texto, f"Analizando a {elegido['campeon']} ({elegido['linea']})...")

    def tarea():
        try:
            routing = perfil_jugador.get("routing") or _region_routing
            platform = perfil_jugador.get("platform") or _region_platform
            resultado = obtener_partida_stats_por_id(match_id, platform, routing, participant_id=elegido["participant_id"])
            if resultado.get("error"):
                app.after(0, lambda: [
                    _set_resultado(resultado_texto, resultado["error"]),
                    boton.config(state="normal"),
                ])
                return
            stats = resultado["stats"]
            _ejecutar_analisis_completo(stats, routing, resultado_texto, boton)
        except Exception as e:
            msg = str(e)
            app.after(0, lambda: [
                _set_resultado(resultado_texto, f"Error analizando la partida: {msg}"),
                boton.config(state="normal"),
            ])

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
        guardar_entrada_historial("pregame", f"{mi_campeon['nombre']} vs {campeon_enemigo['nombre']} ({linea})")
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
