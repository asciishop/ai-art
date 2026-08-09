/web-setup# Plataforma de personajes artificiales 🪷

> Una máquina para **dar vida a personajes**: entidades con identidad, memoria,
> voz propia y la capacidad de recordar lo que viven con quien las visita.
> Pensada para instalaciones artísticas.
>
> Aquí conviven tres: **VA 91** (el Buda Eléctrico), **Zinc** (Guardián de la
> Memoria de los Metales) y **Ucron** (Guardián del Imaginario Basura).

---

## La idea, para un artista

No estás "usando una IA". Estás **criando una entidad**. Y una entidad tiene
capas, como un ser tiene cuerpo, memoria, voz y temperamento:

| Capa | Qué le da al personaje | De dónde sale |
|------|------------------------|---------------|
| **Identidad** | Quién es, qué nunca haría | Un texto: su *System Prompt* |
| **Memoria** | Qué sabe de su mundo | Sus textos de canon (RAG) |
| **Voz / estilo** | Cómo habla, su tono | Entrenamiento con ejemplos (LoRA) |
| **Carácter en vivo** | Si es sereno o alocado | Unos parámetros |
| **Memoria viva** ✨ | Recuerda lo que vive contigo | Se escribe sola, al conversar |

Todo lo técnico existe **solo para sostener una de esas capas**. Cuando el
personaje falla, siempre es una capa concreta la que hay que tocar — nunca "la
IA" en abstracto.

---

## El recorrido, de la idea a la sala

```
1. IMAGINAR      escribes quién es (character_spec)
2. DAR VOZ       le enseñas a hablar con ejemplos (conversations → LoRA)
3. DAR MEMORIA   escribes su mundo (memory → RAG)
4. ENTRENAR      en una GPU de alquiler (RunPod), unos minutos
5. DESPLEGAR     el motor (vLLM) sirve los personajes
6. CONVERSAR     una web (o una instalación) donde el público les habla
7. RECORDAR      la obra guarda y destila lo que vive con la gente
```

Cada personaje recorre los pasos 1→4 una vez. Del 5 en adelante es la plataforma
común que los sirve a todos.

---

## Estructura del proyecto

```
plataforma/
├── personajes.yaml         · EL REGISTRO: define los personajes (fuente única)
├── personajes/
│   ├── va91/ · zinc/ · ucron/
│   │   ├── character_spec.md   · quién es (la biblia del personaje)
│   │   ├── system_prompt.md    · su identidad, lo que lee el modelo
│   │   ├── memory/*.md         · su mundo → memoria RAG
│   │   ├── conversations/*.json· ejemplos de cómo habla → entrenamiento
│   │   └── adapter/            · su "voz" ya entrenada (LoRA)
├── tools/                  · scripts: registro, dataset, indexar, entrenar
├── backend/                · el orquestador (FastAPI) + memoria que escribe
│   ├── main.py             · une las capas en cada conversación
│   └── memoria.py          · la memoria viva (SQLite + experiencias)
├── web/                    · la interfaz de chat
├── pod/                    · cómo arrancar todo en RunPod
└── vector_store/           · las memorias (canon + lo vivido). NO se sube a git.
```

📄 **Guías detalladas:**
- [`COMPLETAR_PERSONAJE.md`](COMPLETAR_PERSONAJE.md) — crear un personaje nuevo, paso a paso.
- [`pod/CORRER.md`](pod/CORRER.md) — desplegar en RunPod, con solución de errores reales.

---

## PARTE A · Crear y entrenar un personaje

Todo esto se hace **en tu ordenador** (solo el paso de entrenar necesita GPU).

**1. Imaginarlo — `character_spec.md`.** El brief creativo: quién es, de qué
mundo viene, cómo habla, qué nunca hace, cómo llama a quien le habla. **Todo lo
demás deriva de aquí**; cuanto más rico, mejor sale lo que sigue.

**2. Su identidad — `system_prompt.md`.** Condensas el brief en instrucciones
directas (bloque ` ```text `). Es lo que el modelo lee para saber quién es.
Funciona al instante, sin entrenar.

**3. Su mundo — `memory/*.md`.** Su canon (lugares, criaturas, historia…), un
bloque por tema separado por `---`. NO va dentro del modelo: se guarda aparte y
el personaje **recupera lo relevante** al responder. Así sabe de un mundo enorme
sin memorizarlo.

**4. Su voz — `conversations/*.json`.** Conversaciones **ideales**: cómo
respondería en su mejor día. Con esto se entrena su voz.
> 💎 **Calidad sobre cantidad.** El modelo imita lo que le des, sin filtro. 100
> conversaciones excelentes valen más que 500 mediocres.

**5. Prepararlo:**
```bash
python tools/build_dataset.py --personaje <id>   # junta las conversaciones
python tools/ingest.py --personaje <id> --reset  # indexa su mundo (RAG)
```

**6. Entrenar la voz (en RunPod, con GPU)** — el único paso con GPU:
```bash
python tools/train.py --dataset personajes/<id>/dataset.jsonl \
                      --salida  personajes/<id>/adapter \
                      --modelo  unsloth/Qwen2.5-3B-Instruct --rank 16
```
~10 minutos y unos céntimos. El resultado es `adapter/`: la voz del personaje, un
archivo pequeño que se "enchufa" al modelo base.

> **Todos los personajes se entrenan sobre el MISMO modelo base** (Qwen2.5-3B).
> Es lo que permite servir a los tres a la vez con un solo motor.

---

## PARTE B · Desplegar (dar vida a los tres a la vez)

El motor es **vLLM**: carga **un modelo base + las voces (adaptadores) de todos
los personajes** y elige cuál usar en cada mensaje. Un cerebro, muchas voces.

```
navegador / instalación → backend → vLLM (base + va91 + zinc + ucron)
                             │
                             ├─ RAG: recupera el mundo del personaje elegido
                             └─ memoria: guarda y destila lo que se vive
```

Guía completa con comandos y errores resueltos: [`pod/CORRER.md`](pod/CORRER.md).
En resumen:

1. Pod en RunPod, plantilla vLLM, GPU de 20-24 GB, **driver CUDA ≥12.8**.
2. **Comando de arranque** del pod (sirve los 3 personajes):
   ```
   --model Qwen/Qwen2.5-3B-Instruct --host 0.0.0.0 --port 8000 --enable-lora
   --max-loras 3 --max-lora-rank 32 --gpu-memory-utilization 0.85
   --lora-modules va91-text=<ruta>/va91/adapter zinc-text=<ruta>/zinc/adapter
                  ucron-text=<ruta>/ucron/adapter
   ```
3. Backend + web:
   ```bash
   python -m pip install -r backend/requirements.txt
   python tools/ingest.py --todos --reset
   export VLLM_URL="http://localhost:8000/v1/chat/completions"
   export VLLM_API_KEY="sk-$RUNPOD_POD_ID"   # solo si vLLM pide api-key
   uvicorn backend.main:app --host 0.0.0.0 --port 3000
   ```
4. Expones el **puerto 3000** → la web con los tres personajes.

---

## PARTE C · La memoria que escribe ✨

Es lo que separa una demo de una obra viva. Al terminar cada conversación, en
segundo plano:

1. **Archiva** el intercambio crudo en `vector_store/archivo.db` (SQLite): el
   diario completo de la obra, todo lo que la gente preguntó.
2. **Destila**: el modelo resume el encuentro en una frase digna de recordar (o
   lo descarta si es trivial — un saludo, una prueba).
3. **Recuerda**: guarda ese recuerdo en la memoria recuperable, sin duplicados.

Así, cuando alguien vuelva a hablar de algo parecido, el personaje **recuerda lo
que vivió** con otros visitantes. La obra evoluciona durante la exposición.

- **Ver qué pregunta la gente:** abre `vector_store/archivo.db` (con *DB Browser
  for SQLite*) o `SELECT fecha, pregunta FROM conversaciones ORDER BY fecha DESC;`
- **Desactivar la memoria:** `export RECORDAR=0` antes de arrancar el backend.

> **Ética:** si la obra es pública y guarda lo que dice la gente, avísalo (un
> cartel: *"esta obra recuerda las conversaciones"*). Es lo honesto — y encaja
> con el tema.

---

## PARTE D · Modo rayos X 🔬 (abrir la caja negra)

El botón **🔬 Rayos X** de la web no cambia la respuesta: **la explica**. Con él
activado, encima de cada respuesta aparece el proceso que la produjo, capa por
capa — las mismas cinco de la tabla del principio:

| Capa | Qué enseña |
|------|------------|
| ① **Identidad** | Qué modelo base y qué LoRA se usó, y el system prompt entero. Deja ver que los tres personajes son *un cerebro con voces distintas*. |
| ② **Recuerdo** | Cada fragmento consultado con su **distancia coseno**, y si `PASA` o se descarta contra el umbral. Aquí se ve la diferencia entre recordar e inventar. |
| ③ **El prompt** | El texto **literal** que recibió el modelo. Sin misterio: no "ve" la conversación, continúa una cadena de texto. |
| ④ **El dado** | `temperature` / `top_p`: por qué la misma pregunta nunca da dos veces la misma respuesta. |
| ⑤ **Memoria** | Qué destiló del encuentro: el recuerdo guardado, o por qué lo descartó. |

**Está apagado por defecto** y solo se activa desde el navegador (`rayosx:true`
en `/api/chat`). En una sala, el público ve al personaje; en clase, se enciende.

> 💡 **La capa ② es la lección.** Cuando ningún fragmento supera el umbral, el
> panel lo avisa: no se inyectó memoria y **lo que diga sale solo de su carácter**.
> Es el momento exacto en que un personaje alucina, y con el panel abierto se ve
> venir antes de leer la respuesta.

Ajusta los diales con `RAG_UMBRAL`, `RAG_MARGEN` y `RAG_K` antes de arrancar el
backend, y observa en el panel cómo cambia qué pasa el filtro.

---

## Añadir un cuarto personaje

Gracias al registro central, es mecánico:
1. Duplica una carpeta en `personajes/` y rellena sus 4 archivos (Parte A).
2. Añade su bloque en `personajes.yaml` con `activo: true`.
3. Entrénalo (paso 6) → su `adapter/`.
4. Añádelo a `--lora-modules` en el comando de arranque del pod.

Ni el backend ni la web se tocan: leen el registro y el personaje aparece solo.

---

## La instalación: sin teclado y sin botones

El visitante no toca nada. Se acerca, y la obra reacciona.

```
se acerca a <0,5 m  →  la webcam lo ve  →  el guardián saluda en voz alta
                                        →  el micrófono se abre solo
        habla  →  el modelo piensa y recuerda  →  responde por el altavoz
                                        →  el micrófono vuelve a abrirse
   gira la cabeza  →  le responde otro guardián
        se va  →  la obra calla y espera al siguiente
```

**Oído y voz** son la Web Speech API del navegador: sin servidor y sin claves.
El botón 🎤 sigue ahí para usarlo a mano.

**Presencia** ([`web/presencia.js`](web/presencia.js)) es MediaPipe Face
Landmarker corriendo en WASM dentro de la pestaña. Mide dos cosas:

| Qué | Cómo | Para qué |
|---|---|---|
| **Distancia** | El ancho aparente de la cara contra el modelo de cámara estenopeica | Por debajo de 0,5 m, invita |
| **Giro de cabeza** | La pose 3D que devuelve el propio modelo | De frente **Zinc**, a su derecha **VA 91**, a su izquierda **Ucron** |

> 🔒 **El vídeo no sale de la pestaña.** No se graba, no se sube y no se
> guarda un solo fotograma: el modelo y el WASM se sirven desde `web/vendor/`,
> así que la detección funciona con la sala entera sin internet.

### Calibrar el día del montaje

El panel de la esquina muestra **la distancia y el ángulo en vivo**: esa es la
herramienta. Pon a alguien donde quieras el límite y mira qué número sale.
Todo se ajusta desde la URL, sin tocar el código:

```
index.html?cerca=0.6&fov=70&giro=40&invertir=1
```

- `cerca` — el umbral en metros (por defecto `0.5`).
- `fov` — el campo de visión de tu webcam en grados (por defecto `60`). **Es el
  dial que más corrige la distancia**: si todas las lecturas salen cortas o
  largas por igual, es este.
- `giro` — los grados que exige el cambio de personaje (por defecto `45`).
- `invertir=1` — si la derecha y la izquierda salen cambiadas.

La distancia es una **estimación**, no una medida: la anchura de una cara varía
entre personas (±15 %) y cada webcam tiene su óptica. Para distinguir "pegado"
de "de paso" basta de sobra, pero calíbralo antes de una inauguración.

### Reglas de convivencia con el chat

Dos decisiones deliberadas, por si sorprenden:

- **Cada visitante empieza de cero.** Al detectar a alguien nuevo se limpia la
  conversación. Nadie hereda el chat del anterior — aunque los *recuerdos*
  destilados sí siguen ahí: para eso están.
- **No se interrumpe a media frase.** Si giras la cabeza mientras el guardián
  responde, el cambio espera a que termine.

### Lo que aún subiría el listón

La voz del navegador es correcta pero neutra, y un personaje pide timbre
propio: ahí entran **Piper + la cadena de efectos** (*prototipo en `../clase/`,
documentado en [VOZ.md](VOZ.md)*). Y en una sala ruidosa, `faster-whisper` en
local oye mejor que el navegador y no depende de conexión.

---

## Las reglas que no se rompen

1. **Los personajes se entrenan sobre el mismo base** (Qwen2.5-3B) — requisito
   del multi-LoRA de vLLM.
2. **vLLM usa el adaptador `safetensors`**, no GGUF (eso era para Ollama).
3. **Una colección de memoria por personaje** — nunca compartida, para que no se
   mezclen los mundos.
4. **Solo el backend se expone** a la web; vLLM queda por dentro.

---

*Todo el conocimiento técnico aquí existe al servicio de una sola pregunta:*
**¿puede una obra tener presencia, memoria y voz propia?** 🪷
