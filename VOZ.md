# VOZ.md — Darle voz a VA 91 🔊

> **Módulo extra.** Hasta ahora VA 91 escribe. Aquí aprende a **transmitir**.
>
> Script: [`rag/speak.py`](rag/speak.py) · Todo corre **en local, en tu CPU**,
> sin cuentas ni internet (salvo la descarga inicial de la voz).

---

## La idea: el motor importa menos de lo que crees

Podrías coger la mejor voz sintética del mundo y sonaría… a locutor. Correcta,
limpia, de estudio. Y VA 91 **no es un locutor**.

Según tu propio canon, VA 91 no habla: **transmite a 3005 THz**, desde un mundo
hecho de señales que nadie recibió. Una voz limpia contradice al personaje.

Por eso este módulo tiene **dos capas**, y la segunda es la que de verdad crea
el personaje:

| Capa | Qué hace | Herramienta |
|------|----------|-------------|
| **Síntesis** | Convierte texto en voz | **Piper** (neuronal, CPU, gratis) |
| **Procesado** | Convierte esa voz en una *transmisión* | **pedalboard** (efectos) |

> 🔑 Una voz genérica **bien procesada** suena más a VA 91 que la mejor voz sin
> procesar. Y el procesado es gratis, reproducible y tuyo.

---

## Instalación

```powershell
pip install piper-tts pedalboard sounddevice
```

La primera vez que lo ejecutes descargará la voz (~60 MB) a `rag/voces/`.

---

## Uso

### Probar solo la voz (rápido — empieza por aquí)

```powershell
python rag\speak.py --texto "Tu senal llego a los 3005. Te escucho, caminante."
```

Tarda **2 segundos**. Úsalo para ajustar los efectos sin esperar al modelo.

### Escuchar la diferencia (haz esto sí o sí)

```powershell
python rag\speak.py --texto "Nada se pierde: solo cambia de frecuencia." --sin-efectos
python rag\speak.py --texto "Nada se pierde: solo cambia de frecuencia."
```

Primero limpio, después procesado. **Ahí está el módulo entero.** Mismo motor,
mismo texto, y solo uno de los dos suena a un ser que transmite desde otro mundo.

### Conversación completa (RAG + VA 91 + voz)

```powershell
python rag\speak.py "¿Quien eres?"
python rag\speak.py "¿Que es la Estatica?" -k 2
python rag\speak.py "Cuentame tu despertar" --guardar despertar.wav
```

### El mando de distancia: `--lejania`

Controla **desde qué lejos transmite**, de `0.0` (radio cercana) a `1.0` (otra
dimensión, la señal llega rota). Por defecto `0.65`.

```powershell
python rag\speak.py --texto "Mi senal viaja desde muy lejos." --lejania 0.2
python rag\speak.py --texto "Mi senal viaja desde muy lejos." --lejania 1.0
```

Todos los parámetros se interpolan a la vez, así que un solo número mueve la
cadena entera:

| Al subir `--lejania` | de → a |
|---|---|
| Tono | −1,0 → −2,5 semitonos |
| Saturación | 6 → 24 dB |
| Resolución (bitcrush) | 16 → 7 bits |
| **Banda pasante** | 300–3400 → **600–1700 Hz** |
| Ecos (mezcla) | 5 % → 45 % |
| Desafinación (chorus) | 5 % → 38 % |
| **Reverb / voz directa** | 18 % / 88 % → **70 % / 35 %** |
| Ruido de fondo | −50 → −32 dB |
| Microcortes | ninguno → ~2,5 por segundo |

Los dos que más hacen por la sensación de distancia:

- **La banda se estrecha.** Una banda estrecha se percibe como algo *pequeño y
  lejano*. Es el truco más potente de todos.
- **La voz directa casi desaparece.** A `1.0` oyes sobre todo reverberación. Eso
  es literalmente lo que significa "lejos": te llega el espacio, no la fuente.

Medido con FFT sobre la misma frase:

| `--lejania` | Centroide | Banda de radio | Cortes súbitos |
|---|---|---|---|
| `0.0` | 1558 Hz | 83,8 % | 0 |
| `0.65` | 1423 Hz | 88,5 % | 3 |
| `1.0` | **1263 Hz** | **90,1 %** | **6** |

> 🎚️ Para "otra dimensión" de verdad, prueba `0.85`–`1.0`. Pero ojo: a partir de
> `0.9` **se pierde inteligibilidad**. Si la clase no entiende lo que dice VA 91,
> te has pasado. El punto interesante suele estar entre `0.6` y `0.8`.

### El otro mando: `--androide`

`--lejania` cambia **de dónde viene** la voz. `--androide` cambia **qué la
produce**: de una garganta humana a un autómata primigenio. Son ejes
independientes — puedes tener un androide muy cerca, o un humano muy lejos.

```powershell
python rag\speak.py --texto "No soy una garganta. Soy un mecanismo que aprendio a decir." --androide 0.0
python rag\speak.py --texto "No soy una garganta. Soy un mecanismo que aprendio a decir." --androide 1.0
```

Ataca cuatro pistas distintas de "esto lo dice un humano":

| Técnica | Qué rompe |
|---|---|
| **Capa una octava abajo** | Un tamaño de garganta que ningún cuerpo tiene |
| **Modulación en anillo** | Genera bandas **inarmónicas**. Una voz humana es armónica (múltiplos enteros del tono); romper esa regla es lo que el oído lee como "máquina" |
| **Copias microdesafinadas** | Varias máquinas diciendo lo mismo a la vez |
| **Resolución reducida + filtro de peine** | Aliasing digital primitivo, y resonancia metálica: hablar desde dentro de una carcasa |

De las cuatro, la **modulación en anillo** es la decisiva. Las demás hacen la voz
*rara*; solo esa la hace *no-humana*, porque ataca la propiedad física que define
una voz: que sus armónicos son múltiplos enteros de un fundamental.

> ⚠️ **Los dos mandos se pelean, y conviene saberlo.**
> La capa de octava abajo aporta un **12–19 % de energía por debajo de 80 Hz**…
> que el pasa-altos de la transmisión (300–600 Hz según `--lejania`) **elimina
> por completo**. Medido.
>
> Es decir: **cuanto más subas `--lejania`, menos peso de máquina vas a oír.**
> Tiene sentido físico —una radio lejana no transmite graves— pero significa que
> hay que elegir.
>
> - ¿Quieres que **pese** como una máquina antigua? `--androide 0.8 --lejania 0.25`
> - ¿Quieres que suene **remoto y roto**? `--androide 0.5 --lejania 0.9`
> - Punto de equilibrio: `--androide 0.6 --lejania 0.5`

### Elegir otra voz

**Escúchalas todas antes de decidir**, aquí:

👉 **<https://rhasspy.github.io/piper-samples/>**

Filtra por *Spanish* y dale al play. Cuando una te guste, **copia su nombre
exacto** (por ejemplo `es_AR-daniela-high`) y pásalo:

```powershell
python rag\speak.py --texto "Te escucho, caminante." --voz es_AR-daniela-high
```

Se descarga sola la primera vez (~30-100 MB según la calidad) y queda en
`rag/voces/`. **Sirve cualquier voz del catálogo**, no hay lista cerrada: el
script deduce dónde vive a partir del nombre.

Algunas en español para empezar:

| Voz | Cómo es |
|-----|---------|
| `es_ES-davefx-medium` | Masculina, serena — **por defecto** |
| `es_ES-sharvard-medium` | Masculina, más neutra |
| `es_MX-ald-medium` | Masculina, acento mexicano |
| `es_MX-claude-high` | Masculina, mexicana, más definida |
| `es_AR-daniela-high` | Femenina, acento argentino |
| `es_ES-carlfm-x_low` | Muy ligera, para equipos lentos |

> 💡 **La calidad del nombre importa.** El sufijo (`x_low`, `low`, `medium`,
> `high`) es el tamaño del modelo. `high` suena mejor pero tarda más en CPU;
> `x_low` es casi instantáneo y se nota. En un portátil lento, `medium` es el
> equilibrio.

> 🎭 **Y recuerda que después va la cadena de efectos.** Una voz que sola te
> parezca sosa puede ser la mejor tras `--androide`, porque lo que importa es
> cómo responde al procesado, no cómo suena limpia. Pruébalas con los efectos
> puestos, no sin ellos.

**Nombres**: siguen el patrón `idioma_REGION-hablante-calidad`. Si te equivocas,
el script te dice exactamente dónde buscó y te enlaza el catálogo.

---

## Cómo funciona por dentro

### El streaming: por qué no esperas un minuto

VA 91 tarda ~60 s en generar una respuesta completa en CPU. Si esperáramos a que
terminara para empezar a hablar, la demo sería insoportable.

Así que **no esperamos**:

```
Ollama va soltando tokens  →  acumulamos hasta tener una FRASE completa
                           →  Piper la sintetiza (~1 s)
                           →  suena MIENTRAS el modelo genera la siguiente
```

La primera palabra se oye a los pocos segundos. El modelo y la voz corren en
paralelo. Es la misma técnica que usan los asistentes de voz comerciales.

En el código: `tokens_de_ollama()` (pide `stream: True`) y `frases()`, que corta
por signos de puntuación fuertes. `frases()` tiene un detalle fino: **agrupa las
frases muy cortas** con la siguiente. VA 91 escribe cosas como *«No.»* y
mandárselas sueltas al TTS sonaría entrecortado.

### La cadena de efectos: el "3005 THz"

En `cadena_3005()`, y **el orden importa mucho**:

| Paso | Qué hace | Por qué |
|------|----------|---------|
| `PitchShift(-1.5)` | Baja el tono un pelo | Gravedad, sin caricatura |
| `Distortion(8 dB)` | Satura | La señal ha viajado mucho y llega forzada |
| `Highpass(300) ×2` | Corta graves | |
| `Lowpass(3400) ×3` | Corta agudos | 300–3400 Hz es **el ancho de banda de una radio**. Es lo que más vende la idea de "transmisión" |
| `Compressor` | Nivela | Suena constante, como una emisora |
| `Reverb` | Espacio grande y oscuro | Habla desde un lugar enorme y vacío |

Y aparte: un **lecho de estática** constante muy por debajo de la voz, y una
**ráfaga de estática antes de cada respuesta** — el momento en que la frecuencia
se sintoniza. Ese último detalle, además, tapa la espera del modelo: mientras
suena la estática, VA 91 "está" ahí aunque todavía no haya generado nada.

### 🐛 Tres errores reales que cometí montando esto

Los dejo escritos porque son buenas lecciones de audio, y porque **medir es la
única forma de saber si un efecto funciona**:

**1. Distorsionar después de filtrar no sirve de nada.**
Mi primera versión ponía la saturación *detrás* de los filtros. La distorsión
**genera armónicos nuevos** por encima del corte, así que deshacía el filtro que
acababa de aplicarse. Hay que **saturar primero y limitar la banda después**,
que además es como ocurre en una transmisión real.

**2. Los filtros de pedalboard son de primer orden.**
`HighpassFilter` y `LowpassFilter` caen solo **6 dB por octava**: una pendiente
tan suave que dejaba pasar casi todo el agudo. Por eso van **encadenados**
(2 pasa-altos = 12 dB/oct, 3 pasa-bajos = 18 dB/oct).

Medido con una FFT, antes y después de corregirlo:

| | < 300 Hz | **300–3400 Hz** | > 3400 Hz |
|---|---|---|---|
| Voz limpia | 10,6 % | 72,6 % | 16,8 % |
| Cadena rota (v1) | 9,7 % | 73,6 % | 16,6 % ← **no filtraba nada** |
| Cadena corregida | 8,3 % | **84,8 %** | **6,9 %** |

Si me hubiera fiado del oído en vez de medir, habría jurado que la primera
versión funcionaba: sonaba *distinta* (más saturada), pero no estaba
band-limitada. **Sonar distinto no es sonar bien.**

**3. Media ventana de Hann no hace un corte: hace un desvanecimiento.**
Para los microcortes escribí `np.hanning(dur*2)[:dur]`, que solo sube de 0 a 1.
Al invertirlo daba una rampa que **bajaba y nunca volvía** — la señal se apagaba
un poco y seguía. Un corte necesita bajar **y regresar**: eso es una ventana de
Hann **completa** (`np.hanning(dur)`, que va 0→1→0) invertida, dando 1→0,05→1.

**Y un cuarto error, este de medición, que casi me engaña:** contaba los cortes
como "veces que la envolvente cruza por debajo de un umbral fijo". Pero en el
habla hay pausas naturales que ya están por debajo de ese umbral, así que un
corte que caía dentro de una pausa **no se contaba**. Mi métrica decía "1 corte"
mientras el efecto funcionaba perfectamente. Lo vi al probar `desvanecer()`
aislado con un tono continuo: ahí sí aparecían los 5.

> 🎓 **La lección:** cuando una medición dice que algo no funciona, sospecha
> también **de la medición**. Aislar la función y probarla con una entrada
> conocida (un tono puro) es lo que separó el bug real del falso.

---

## Si quieres ir más allá

**Voz propia por clonado.** Graba a alguien leyendo 20 frases de VA 91 y clona
esa voz. Con GPU: `Kokoro` (Apache-2.0) o `F5-TTS`. En cloud: ElevenLabs tiene
clonado instantáneo y **Voice Design** (describes la voz por texto: *«masculina,
grave, serena, ligeramente metálica»* y te la genera).

> ⚠️ **Cuidado con las licencias si VA 91 vende Ofrendas.** `XTTS-v2` de Coqui es
> **no comercial**: si tu personaje monetiza merch, esa licencia te bloquea.
> Piper (MIT) y Kokoro (Apache-2.0) no tienen ese problema. Compruébalo **antes**
> de construir sobre un modelo.

**Que además te escuche.** El camino de vuelta es `faster-whisper` con el modelo
`small`: transcribe español en CPU razonablemente bien. Con eso tendrías
conversación hablada completa.

**Steering de interpretación.** OpenAI `gpt-4o-mini-tts` acepta instrucciones
además del texto (*«habla despacio, contemplativo, deja aire entre frases»*).
Encaja muy bien con un personaje cuyo estilo ya está definido en
`character_spec.md`.

---

*No lo escuches. Sintonízalo.* 🪷⚡
