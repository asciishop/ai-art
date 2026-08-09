"""
La voz de los guardianes: síntesis local + cadena de efectos.

La voz del NAVEGADOR (Web Speech API) es correcta y gratis, pero no se puede
tocar: el navegador la manda directa a la tarjeta de sonido y no hay ningún
nodo de audio que interceptar. Para que un guardián suene a máquina que
transmite desde otro sitio hay que sintetizar aquí y procesar aquí.

Dos capas, y la segunda es la que crea al personaje:

    síntesis   Piper (neuronal, CPU, sin nube)      texto -> voz
    procesado  pedalboard                           voz  -> transmisión

Dos mandos independientes por personaje (en personajes.yaml):

    voz_androide  0-1   QUÉ produce la voz: de garganta a autómata.
                        Sube armónicos inarmónicos, subgraves y resonancia
                        metálica. Es lo que suena a "robot".
    voz_lejania   0-1   DE DÓNDE llega: banda de radio, ecos, ruido de fondo,
                        microcortes. Es lo que suena a "otra dimensión".

Se pelean entre sí, y conviene saberlo: la capa de octava abajo del androide
vive por debajo de 80 Hz, justo donde el pasa-altos de la lejanía corta. Cuanto
más lejanía, menos peso de máquina se oye. Por eso los presets de la plataforma
llevan androide ALTO y lejanía MODERADA: se pidió robótico y raro pero legible,
y es la lejanía la que se come la inteligibilidad, no el androide.

Todo corre en CPU. Si faltan piper-tts o pedalboard, este módulo se declara no
disponible y la web vuelve sola a la voz del navegador.

Portado de rag/speak.py del taller, donde la cadena se ajustó midiendo con FFT
(ver VOZ.md). Los comentarios de por qué cada efecto está donde está vienen de
allí: son errores ya cometidos.
"""

import io
import os
import threading
import wave

import numpy as np

# --- Config ---------------------------------------------------------------
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOCES_DIR = os.path.join(RAIZ, "voces")
BASE_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOZ_POR_DEFECTO = "es_ES-sharvard-medium"

_voces = {}       # cache de modelos Piper cargados
_boards = {}      # cache de cadenas de efectos por (sr, lejania)
_lock = threading.Lock()   # Piper no es reentrante; en una sala sobra con esto
_motivo = ""      # por qué no está disponible, si no lo está


def disponible() -> tuple:
    """(bool, motivo). La web lo consulta al arrancar para saber qué voz usar."""
    global _motivo
    try:
        import piper  # noqa: F401
    except ImportError:
        _motivo = "falta piper-tts (pip install piper-tts)"
        return False, _motivo
    try:
        import pedalboard  # noqa: F401
    except ImportError:
        _motivo = "falta pedalboard (pip install pedalboard)"
        return False, _motivo
    return True, ""


# --- 1. Piper: texto -> voz limpia ---------------------------------------

def _ruta_hf(nombre: str):
    """es_ES-davefx-medium -> es/es_ES/davefx/medium

    Deducirlo permite usar CUALQUIER voz del catálogo sin listarla aquí.
    Catálogo y muestras: https://rhasspy.github.io/piper-samples/
    """
    partes = nombre.split("-")
    if len(partes) < 3 or "_" not in partes[0]:
        return None
    local, calidad = partes[0], partes[-1]
    hablante = "-".join(partes[1:-1])
    return f"{local.split('_')[0]}/{local}/{hablante}/{calidad}"


def _descargar(nombre: str) -> str:
    """Baja el .onnx y su .json si faltan. Devuelve la ruta del .onnx."""
    import httpx
    ruta = _ruta_hf(nombre)
    if ruta is None:
        raise ValueError(f"nombre de voz mal formado: {nombre} "
                         f"(se espera idioma_REGION-hablante-calidad)")
    os.makedirs(VOCES_DIR, exist_ok=True)
    for sufijo in (".onnx", ".onnx.json"):
        destino = os.path.join(VOCES_DIR, nombre + sufijo)
        if os.path.exists(destino):
            continue
        url = f"{BASE_HF}/{ruta}/{nombre}{sufijo}"
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r:
            if r.status_code == 404:
                raise ValueError(f"esa voz no existe en el catálogo: {nombre}")
            r.raise_for_status()
            # A un fichero temporal: si se corta la descarga, no queda un .onnx
            # a medias que luego pareciera válido y reventara al cargarlo.
            tmp = destino + ".parcial"
            with open(tmp, "wb") as f:
                for bloque in r.iter_bytes(1 << 16):
                    f.write(bloque)
            os.replace(tmp, destino)
    return os.path.join(VOCES_DIR, f"{nombre}.onnx")


def _cargar(nombre: str):
    if nombre not in _voces:
        from piper import PiperVoice
        _voces[nombre] = PiperVoice.load(_descargar(nombre))
    return _voces[nombre]


def _sintetizar(voz, texto: str):
    """Texto -> (float32 en [-1,1], sample_rate). Tolera las dos APIs de Piper."""
    sr = getattr(getattr(voz, "config", None), "sample_rate", 22050)
    partes = []
    if hasattr(voz, "synthesize"):                     # piper-tts >= 1.3
        for trozo in voz.synthesize(texto):
            if isinstance(trozo, (bytes, bytearray)):
                partes.append(np.frombuffer(trozo, dtype=np.int16))
            else:
                sr = getattr(trozo, "sample_rate", sr)
                crudo = getattr(trozo, "audio_int16_bytes", None)
                if crudo is not None:
                    partes.append(np.frombuffer(crudo, dtype=np.int16))
                elif hasattr(trozo, "audio_float_array"):
                    partes.append((trozo.audio_float_array * 32767).astype(np.int16))
    else:                                              # piper-tts < 1.3
        crudo = b"".join(voz.synthesize_stream_raw(texto))
        partes.append(np.frombuffer(crudo, dtype=np.int16))
    if not partes:
        return np.zeros(0, dtype=np.float32), sr
    return np.concatenate(partes).astype(np.float32) / 32768.0, sr


# --- 2. Los efectos -------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _cadena(sr: int, lejania: float):
    """La transmisión: banda de radio, ecos, deriva y un espacio enorme."""
    from pedalboard import (Pedalboard, HighpassFilter, LowpassFilter,
                            Distortion, Compressor, Reverb, Gain, PitchShift,
                            Bitcrush, Delay, Chorus)
    t = max(0.0, min(1.0, lejania))
    return Pedalboard([
        PitchShift(semitones=_lerp(-1.0, -2.5, t)),
        # Saturar ANTES de filtrar. Al revés no sirve: la distorsión genera
        # armónicos por encima del corte y deshace el filtro que acaba de pasar.
        # 24 dB emborronaba las oclusivas; con 15 sigue sonando forzada.
        Distortion(drive_db=_lerp(5.0, 15.0, t)),
        # "Pixelado": resolución reducida, la señal perdió bits por el camino.
        # El bitcrush toca la resolución de AMPLITUD, no la temporal: da la
        # textura digital sin borrar consonantes. Es el sitio correcto para
        # buscar "pixelado", no el diezmado del androide.
        Bitcrush(bit_depth=_lerp(14.0, 9.0, t)),
        # Banda de radio. Los filtros de pedalboard son de primer orden
        # (6 dB/oct), pendiente demasiado suave: van encadenados.
        HighpassFilter(cutoff_frequency_hz=_lerp(280, 520, t)),
        HighpassFilter(cutoff_frequency_hz=_lerp(280, 520, t)),
        # Antes esto bajaba a 1700 Hz con TRES etapas (18 dB/oct). Las eses y
        # las efes viven en 4-8 kHz: con el corte ahí la voz sonaba a radio,
        # sí, pero no se entendía. Se sube el corte y se quita una etapa: se
        # conserva el color de transmisión y vuelven las consonantes.
        LowpassFilter(cutoff_frequency_hz=_lerp(5000, 2800, t)),
        LowpassFilter(cutoff_frequency_hz=_lerp(5000, 2800, t)),
        Delay(delay_seconds=_lerp(0.09, 0.28, t),
              feedback=_lerp(0.10, 0.55, t), mix=_lerp(0.05, 0.45, t)),
        # Desafinación lenta: la frecuencia no se sostiene, deriva. Esto es lo
        # que suena "de otra dimensión" y no solo "de lejos".
        Chorus(rate_hz=0.35, depth=_lerp(0.10, 0.45, t),
               centre_delay_ms=9.0, mix=_lerp(0.05, 0.38, t)),
        Compressor(threshold_db=-20, ratio=3.5, attack_ms=5, release_ms=140),
        # La reverb es lo segundo que más emborrona: cada sílaba se solapa con
        # la cola de la anterior. Se recorta el envío y se sube la voz directa;
        # sigue habiendo espacio, pero se oye a quien habla y no solo la sala.
        Reverb(room_size=_lerp(0.80, 0.95, t), damping=_lerp(0.50, 0.80, t),
               wet_level=_lerp(0.12, 0.42, t), dry_level=_lerp(0.92, 0.62, t),
               width=1.0),
        Gain(gain_db=-2.0),
    ])


def _androidizar(audio: np.ndarray, sr: int, intensidad: float):
    """De garganta a autómata. Cuatro frentes contra "esto lo dice un humano".

    El decisivo es la modulación en anillo: genera bandas INARMÓNICAS. Una voz
    humana es armónica (múltiplos enteros del fundamental); romper esa regla es
    exactamente lo que el oído lee como "máquina". Los demás la hacen rara; solo
    ese la hace no-humana.
    """
    if intensidad <= 0.01 or audio.size == 0:
        return audio
    from pedalboard import Pedalboard, PitchShift, Delay, PeakFilter

    t = max(0.0, min(1.0, intensidad))
    n = audio.size
    tiempo = np.arange(n, dtype=np.float32) / sr

    def desplazar(semitonos):
        if abs(semitonos) < 0.01:
            return audio
        s = Pedalboard([PitchShift(semitones=semitonos)])(audio.reshape(1, -1), sr)
        return s.reshape(-1)[:n]

    sub = desplazar(-12.0)                                   # peso de máquina grande
    ring = audio * np.sin(2 * np.pi * _lerp(40.0, 85.0, t) * tiempo).astype(np.float32)
    coro = desplazar(_lerp(0.0, 0.28, t)) + desplazar(_lerp(0.0, -0.28, t))

    # La voz SECA es el esqueleto y se queda casi entera: es la única capa que
    # lleva las consonantes. Las demás se suman por debajo, como maquinaria.
    # Bajar la seca es lo que hacía ininteligible la primera versión.
    mezcla = (audio * (1.0 - 0.08 * t)          # la seca casi intacta
              + sub * _lerp(0.0, 0.40, t)
              + ring * _lerp(0.0, 0.13, t)      # el anillo hace de máquina, pero
              + coro * _lerp(0.0, 0.09, t))     # en exceso tapa los formantes

    # Aliasing digital primitivo — el efecto que MÁS daño hace a la claridad,
    # porque reduce la resolución TEMPORAL y ahí es donde viven las consonantes.
    # Antes se calculaba con int(round(lerp(1,2,t))), que salta a 2 en cuanto
    # t >= 0.5: los tres personajes lo tenían puesto sin que se viera en ningún
    # dial. Ahora solo entra en ajustes deliberadamente extremos.
    if t >= 0.92:
        mezcla = np.repeat(mezcla[::2], 2)[:n]

    # Filtro de peine: resonancia metálica, hablar dentro de una carcasa.
    if t > 0.05:
        peine = Pedalboard([Delay(delay_seconds=_lerp(0.020, 0.008, t),
                                  feedback=_lerp(0.0, 0.25, t),
                                  mix=_lerp(0.0, 0.11, t))])
        mezcla = peine(mezcla.reshape(1, -1), sr).reshape(-1)[:n]

    # Realce de presencia: devuelve las consonantes que la maquinaria se comió.
    # 1,5-4 kHz es donde se distingue una "s" de una "f". Sin esto suena a
    # máquina pero no se entiende nada, que es justo lo que NO se quería.
    # Se añade una tercera banda arriba (4,5 kHz) para las sibilantes, que son
    # las primeras en caer y las que más se echan de menos.
    claridad = Pedalboard([
        PeakFilter(cutoff_frequency_hz=4500.0, gain_db=_lerp(0.0, 4.0, t), q=0.8),
        PeakFilter(cutoff_frequency_hz=2600.0, gain_db=_lerp(0.0, 7.0, t), q=0.7),
        PeakFilter(cutoff_frequency_hz=1400.0, gain_db=_lerp(0.0, 3.5, t), q=0.9),
    ])
    mezcla = claridad(mezcla.reshape(1, -1), sr).reshape(-1)[:n]

    pico = float(np.max(np.abs(mezcla))) if mezcla.size else 0.0
    if pico > 0:
        mezcla = mezcla * (0.9 / pico)
    return mezcla.astype(np.float32)


def _desvanecer(audio: np.ndarray, sr: int, lejania: float):
    """Deriva de volumen + microcortes. Ningún efecto de pedalboard hace esto,
    y es lo que más vende que la señal viene de lejos: respira y a veces se cae."""
    t = max(0.0, min(1.0, lejania))
    if audio.size == 0 or t <= 0.01:
        return audio
    n = audio.size
    tiempo = np.arange(n, dtype=np.float32) / sr
    prof = _lerp(0.0, 0.35, t)
    onda = (np.sin(2 * np.pi * 0.23 * tiempo) * 0.6 +
            np.sin(2 * np.pi * 0.07 * tiempo + 1.3) * 0.4)
    envolvente = (1.0 - prof) + prof * (0.5 + 0.5 * onda)

    # Menos cortes que antes (eran 2,5/s): cada uno se lleva una sílaba entera
    # por delante. Con ~1 por segundo la señal sigue pareciendo inestable.
    rng = np.random.default_rng()
    for _ in range(int(_lerp(0.0, 1.1, t) * (n / sr))):
        dur = int(sr * rng.uniform(0.03, 0.09))
        if dur < 4:
            continue
        ini = int(rng.uniform(0, max(1, n - dur)))
        # Ventana de Hann COMPLETA (0->1->0) invertida = un hoyo que vuelve.
        # Con media ventana solo habría un desvanecimiento que nunca regresa.
        hoyo = 1.0 - np.hanning(dur) * 0.95
        tramo = envolvente[ini:ini + dur]
        envolvente[ini:ini + dur] = tramo * hoyo[:len(tramo)]
    return (audio * envolvente.astype(np.float32)).astype(np.float32)


def _ruido(n: int, nivel_db: float):
    """Lecho de estática, muy por debajo de la voz."""
    r = np.random.randn(n).astype(np.float32)
    r = np.convolve(r, np.ones(8, dtype=np.float32) / 8, mode="same")
    return r * (10.0 ** (nivel_db / 20.0))


def _estatica(sr: int, duracion: float = 0.40, nivel_db: float = -30.0):
    """Ráfaga de sintonía: el instante en que se engancha la frecuencia.
    Además tapa la espera: mientras suena, el guardián ya "está ahí"."""
    n = int(sr * duracion)
    r = np.random.randn(n).astype(np.float32)
    r = np.convolve(r, np.ones(6, dtype=np.float32) / 6, mode="same")
    return r * (np.linspace(1.0, 0.0, n, dtype=np.float32) ** 1.6) * (10.0 ** (nivel_db / 20.0))


# --- 3. La pieza pública --------------------------------------------------

def sintetizar(texto: str, modelo: str = VOZ_POR_DEFECTO,
               lejania: float = 0.35, androide: float = 0.75,
               sintonia: bool = False) -> bytes:
    """Devuelve un WAV mono listo para reproducir en el navegador."""
    with _lock:
        voz = _cargar(modelo or VOZ_POR_DEFECTO)
        audio, sr = _sintetizar(voz, texto)
        if audio.size == 0:
            return _wav(np.zeros(0, dtype=np.float32), sr)

        clave = (sr, round(lejania, 2))
        if clave not in _boards:
            _boards[clave] = _cadena(sr, lejania)
        board = _boards[clave]

        # Primero QUÉ produce la voz (el autómata), después POR DÓNDE llega (la
        # transmisión). Androidizar una señal ya filtrada y reverberada emborrona
        # el timbre en vez de definirlo.
        audio = _androidizar(audio, sr, androide)
        # El ruido entra ANTES de la cadena: así se filtra junto con la voz y
        # suena a estática de radio, con su misma banda, en vez de a siseo
        # blanco pegado encima.
        nivel = _lerp(-50.0, -32.0, max(0.0, min(1.0, lejania)))
        salida = board((audio + _ruido(audio.size, nivel)).reshape(1, -1), sr).reshape(-1)
        salida = _desvanecer(salida, sr, lejania)

        if sintonia:
            salida = np.concatenate([_estatica(sr), salida])

        pico = float(np.max(np.abs(salida))) if salida.size else 0.0
        if pico > 0.99:
            salida = salida * (0.99 / pico)
        return _wav(salida.astype(np.float32), sr)


def _wav(audio: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
