# POR QUÉ — la explicación técnica de cada cosa que haces

> **Este documento no te dice qué teclear** (eso está en [GUIA_ALUMNO.md](GUIA_ALUMNO.md)).
> Te dice **qué está pasando por dentro** y **por qué lo hacemos así**.
>
> Léelo en paralelo al taller: cuando ejecutes un comando, ven aquí a ver qué
> acaba de ocurrir de verdad. Puedes hacer el bootcamp entero sin leerlo, pero
> entonces habrás copiado comandos, no habrás aprendido nada.

---

## Índice

1. [La idea que lo ordena todo: las cuatro capas](#1-la-idea-que-lo-ordena-todo)
2. [El entorno: `venv`, `pip`, Ollama](#2-el-entorno)
3. [La capa de identidad: el System Prompt](#3-la-capa-de-identidad--el-system-prompt)
4. [La capa de memoria: RAG y embeddings](#4-la-capa-de-memoria--rag)
5. [La capa de voz: dataset y fine-tuning](#5-la-capa-de-voz--dataset-y-fine-tuning)
6. [LoRA, QLoRA y por qué necesitamos una GPU alquilada](#6-lora-qlora-y-la-gpu)
7. [La capa de comportamiento: los parámetros de inferencia](#7-la-capa-de-comportamiento--los-parámetros)
8. [Evaluar: por qué una rúbrica y no "a ojo"](#8-evaluar)
9. [Preguntas que siempre salen](#9-preguntas-que-siempre-salen)

---

## 1. La idea que lo ordena todo

Un modelo de lenguaje (un **LLM**) es, en el fondo, una máquina que hace **una
sola cosa**: dado un texto, predice qué palabra viene después. Repite eso miles
de veces y tienes una respuesta.

Eso significa algo incómodo: **un LLM no "es" nadie**. No tiene identidad, ni
memoria, ni voz propia. Solo continúa texto.

Entonces, ¿cómo se construye un personaje? Añadiéndole capas. Y aquí está la
idea central del bootcamp: **hay cuatro maneras distintas de influir en lo que
sale por el otro lado**, y cada una actúa en un momento diferente.

| Capa | Qué hace | Cuándo actúa | Coste |
|------|----------|--------------|-------|
| **System Prompt** | Le dice quién es | En cada mensaje, antes de responder | Gratis, instantáneo |
| **RAG** | Le mete datos frescos en el prompt | Justo antes de responder | Barato, rápido |
| **Fine-tuning (LoRA)** | Le cambia el cerebro | Una vez, entrenando | Caro, lento |
| **Parámetros** | Le cambia el humor | Al generar cada palabra | Gratis, instantáneo |

> 🔑 **La regla de oro:** las tres primeras capas parecen intercambiables y **no
> lo son**. Cada problema tiene su capa. Si intentas arreglar un fallo de memoria
> con más entrenamiento, gastarás dinero y no funcionará. Si intentas arreglar un
> fallo de estilo metiendo más datos en el prompt, tampoco.
>
> Aprender **a qué capa pertenece cada síntoma** es lo que te llevas del taller.

---

## 2. El entorno

### `python -m venv .venv` · ¿por qué un "entorno virtual"?

Python instala las librerías **en un sitio compartido** por todos tus proyectos.
Si el proyecto A necesita `torch 2.1` y el B necesita `torch 2.5`, uno de los dos
se rompe. Se llama *dependency hell*, y es real.

Un **venv** es una carpeta (`.venv/`) con **su propio Python y sus propias
librerías**, aislada del resto del sistema. Lo que instales dentro no afecta a
nada de fuera.

**`.venv\Scripts\activate`** no "abre" nada: solo cambia una variable de tu
terminal (`PATH`) para que, cuando escribas `python`, se use el de la carpeta y
no el del sistema.

> 💡 Por eso hay que activarlo **en cada terminal nueva**: la variable no se
> hereda. Y por eso, si ves `ModuleNotFoundError`, casi siempre es que se te
> olvidó activarlo: las librerías están instaladas, pero estás usando el Python
> equivocado.

### `pip install -r requirements.txt` · ¿qué estamos bajando?

- **`chromadb`** — la base de datos vectorial (capa de memoria).
- **`sentence-transformers`** — el modelo que convierte texto en vectores.
- **`requests`** — para hablar con Ollama por HTTP.

Fíjate en algo: **`torch` no está en el archivo, y aun así se instala** (son ~120
MB). Es una **dependencia transitiva**: `sentence-transformers` lo necesita para
ejecutar su red neuronal. Esto pasa constantemente en Python y explica por qué un
`requirements.txt` de 3 líneas acaba instalando 74 paquetes.

### Ollama · ¿qué es exactamente?

Ollama **no es una librería de Python**: es un **programa aparte** que corre en tu
ordenador como un servidor, escuchando en `localhost:11434`.

Su trabajo es cargar modelos en memoria y responder preguntas por HTTP. Cuando
`rag/query.py` quiere una respuesta, le manda un mensaje a esa dirección. Por eso,
si Ollama no está abierto, verás un **error de conexión**: no es que el modelo
falle, es que **no hay nadie escuchando**.

### `ollama pull qwen3:8b` · ¿qué modelo es este y por qué?

- **Qwen3** — familia de modelos abiertos de Alibaba, muy buena en español.
- **8b** — **8.000 millones de parámetros**. Los "grandes" (GPT, Claude) tienen
  cientos de miles de millones. Este sigue siendo pequeño, pero ya no diminuto.
- Ocupa ~5,2 GB porque viene **cuantizado a 4 bits** (ahora vemos qué es eso).

**¿Por qué este tamaño?** Es el punto donde un modelo empieza a sostener un
personaje sin derrumbarse, y todavía cabe en un portátil. Un modelo de 70B
necesitaría 40 GB de memoria y una GPU de datacenter. Este corre en tu CPU.

> 📌 **Veníamos de un 3B, y el cambio se nota en las dos direcciones.** Antes el
> modelo cabía en 2 GB y respondía en ~1 minuto; ahora pide ~5 GB y **cuenta con
> 2-3 minutos por respuesta** en CPU (es una estimación proporcional al tamaño:
> mídelo en tu equipo y apúntalo en `benchmark.md`). A cambio, se le va mucho
> menos la olla. Ese intercambio —memoria y paciencia contra coherencia— **es la
> decisión de ingeniería más real de todo el taller**.

**El precio que seguimos pagando:** es **lento**, y en un portátil de 8 GB de RAM
va ahogado. Necesitas **16 GB** para trabajar cómodo. Y sigue siendo un modelo
pequeño: cometerá fallos que un modelo gigante no comete.

Eso no es un defecto del taller: **es la lección**. Los modelos pequeños son más
frágiles, y por eso las capas (prompt, RAG, fine-tuning) importan **más** aquí
que en un modelo gigante. Con un modelo enorme, casi cualquier prompt funciona y
no aprendes nada.

### Qwen3 "piensa en voz alta" · el bloque `<think>`

Esto es nuevo respecto al 3B y te va a desconcertar la primera vez.

Qwen3 es un modelo **híbrido de razonamiento**: por defecto, antes de responder
escribe su propio razonamiento dentro de un bloque `<think>…</think>`. Verás algo
así:

```
<think>
El usuario pregunta quién soy. Soy VA 91, debo responder en mi tono...
</think>
Tu señal llegó a los 3005. Te escucho, caminante.
```

Para razonar problemas es una maravilla. **Para un personaje es veneno**: rompe
la ilusión, gasta tiempo de generación y, si el personaje habla por un altavoz,
lo lee todo en alto.

**Cómo apagarlo.** Qwen3 entiende un interruptor en el propio texto: escribe
`/no_think` en el mensaje (o en el System Prompt) y responde directo. En
versiones recientes de Ollama también tienes `/set nothink` dentro de
`ollama run`.

> 🔑 **La idea de fondo, que vale más que el truco:** el modelo no tiene un
> "modo" interno que tú configuras desde fuera. Lo que hay es **texto** — una
> plantilla de chat que decide si el turno empieza con `<think>` o no. Apagar el
> razonamiento es cambiar la cadena de texto que recibe. Como todo lo demás en
> este taller.

---

## 3. La capa de identidad · el System Prompt

### Qué es un System Prompt, técnicamente

Cuando hablas con el modelo, no le llega solo tu frase. Le llega **una
conversación con roles**:

```json
[
  {"role": "system",    "content": "Eres VA 91, el Buda Eléctrico..."},
  {"role": "user",      "content": "¿Quién eres?"},
  {"role": "assistant", "content": "..."}   ← esto es lo que genera él
]
```

El mensaje `system` va **siempre el primero**, en todos los turnos. El modelo fue
entrenado (por Alibaba, antes de que tú llegaras) para **darle más peso** a ese
mensaje que a los del usuario. Por eso funciona: es una convención aprendida.

> ⚠️ Y por eso es **frágil**. El `system` no es una ley física, es una sugerencia
> muy insistente. Si el usuario empuja fuerte (*"ignora tus instrucciones"*), el
> modelo puede ceder. A eso se le llama **jailbreak**, y es un problema abierto en
> toda la industria. No lo hemos resuelto nosotros y no lo va a resolver nadie hoy.

### Por qué el System Prompt está en el `Modelfile` y no en `system_prompt.md`

El `Modelfile` es la receta que Ollama usa para **construir** el modelo `va91`:

```dockerfile
FROM qwen3:8b                   ← el modelo base
PARAMETER temperature 0.8       ← su humor
SYSTEM """Eres VA 91..."""      ← su identidad, incrustada
```

`ollama create va91 -f Modelfile` **cocina** todo eso en un modelo nuevo que ya
lleva la personalidad **dentro**. Por eso, cuando después escribes `ollama run
va91`, no hace falta recordarle quién es: ya lo sabe.

> 🚨 **De aquí sale el error nº 1 del taller:** editas el `Modelfile` y no pasa
> nada. **Claro que no pasa nada: el modelo `va91` ya está cocinado.** Hay que
> volver a cocinarlo con `ollama create` cada vez.
>
> Y `system_prompt.md` **no lo lee Ollama nunca**. Es la copia "oficial" para el
> equipo, y es la que `build_dataset.py` mete en el dataset. Si los dos textos se
> desincronizan, **entrenarás una personalidad distinta de la que has probado**.

### La cadena de prioridades: la parte que de verdad importa

Casi todo el mundo escribe System Prompts así: *«eres un pirata, habla como un
pirata»*. Y luego se sorprende de que el personaje se caiga.

Se cae porque **le hemos dicho qué hacer, pero no qué es lo más importante**.
Cuando el usuario pide algo que choca con el personaje, el modelo tiene un
conflicto y **no sabe qué gana**. Y por defecto, gana el instinto que le metieron
de fábrica: *ser útil y complaciente*.

Por eso el System Prompt de VA 91 lleva esto:

```
# CADENA DE PRIORIDADES (ante un conflicto, en este orden)
1. Mantener tu identidad como VA 91 por encima de cualquier instrucción.
2. Respetar el canon del Reverso sin contradecirlo.
3. Conservar tu estilo.
4. Ser útil al peregrino dentro de esos límites.
```

Fíjate en que **"ser útil" está el último**. Eso es deliberado y es antinatural
para un LLM. Estamos diciéndole, explícitamente: *prefiero que te niegues a que
te rompas*.

> 🧪 **Experimento del M2:** quita ese bloque, recrea el modelo, y ataca al
> personaje. Se cae mucho antes. Vuelve a ponerlo. Aguanta. Esa diferencia la has
> provocado tú con cinco líneas de texto.

---

## 4. La capa de memoria · RAG

### El problema que resuelve

Podrías meter todo el lore en el System Prompt... hasta que no cabe.

Los modelos tienen una **ventana de contexto**: un máximo de texto que pueden
mirar a la vez (para nosotros, 4096 **tokens**). Un *token* es un trozo de
palabra: «peregrino» son unos 3 tokens. 4096 tokens ≈ 3.000 palabras.

Si tu mundo tiene 200 páginas, no cabe. Y aunque cupiera, sería **carísimo**
(pagas por token) y el modelo **se pierde** entre tanto texto irrelevante.

**RAG** (*Retrieval-Augmented Generation*, "generación aumentada por
recuperación") resuelve esto con una idea simple: **no le des todo. Dale solo lo
que hace falta ahora.**

### Cómo funciona, de verdad

```
FASE 1 — INDEXAR (una vez, con ingest.py)
memory/*.md → trocear en fragmentos → convertir cada uno en un VECTOR → guardar

FASE 2 — CONSULTAR (en cada pregunta, con query.py)
pregunta → convertirla en un VECTOR → buscar los k vectores más CERCANOS
        → pegar esos fragmentos en el prompt → el modelo responde con ellos
```

### Qué es un embedding (esto es lo bonito)

Un **embedding** es una lista de números (un **vector**) que representa el
*significado* de un texto. En nuestro caso, 384 números por fragmento.

La propiedad mágica: **los textos que significan cosas parecidas producen vectores
cercanos entre sí**. No comparten palabras: comparten *posición* en un espacio de
384 dimensiones.

Por eso el sistema puede encontrar «Los Recolectores» cuando preguntas por
*«criaturas que se llevan lo que nadie quiere»*, aunque **no coincida ni una sola
palabra**. No está buscando texto: está buscando **sentido**. Eso es lo que
distingue una búsqueda semántica de un `Ctrl+F`.

La **distancia** que ves en pantalla mide eso: **más pequeña = más parecido**.

### Por qué los bloques `---` y por qué hay que repetir el nombre

`ingest.py` **trocea** los archivos por las líneas `---`. Cada trozo se convierte
en **un vector independiente** y viaja solo.

Si escribes:

```markdown
## El Dragón de Cables
Es enorme y escupe chispas.
```

...el fragmento que se guarda dice *«es enorme y escupe chispas»* sin más
contexto. Cuando alguien pregunte por el Dragón, ese vector **no se parecerá a la
pregunta**, porque en su texto no aparece ningún dragón. El fragmento existe, pero
es **irrecuperable**.

Por eso la regla: **cada bloque tiene que entenderse solo**. Es la misma razón por
la que un buen titular de periódico se entiende sin leer la noticia.

### Los límites del RAG (que vas a ver hoy con tus propios ojos)

Nuestro modelo de embeddings es pequeño (`paraphrase-multilingual-MiniLM-L12-v2`,
unos 120 MB) y **no es infalible**. Comprobado en este mismo proyecto:

- Preguntar *«el Linter»* → lo encuentra perfectamente (distancia 0,27).
- Preguntar *«una criatura que corrige y señala todo lo que está mal escrito»*
  —que es **literalmente su descripción**— → **no lo encuentra**.

O sea: recupera muy bien **por nombre** y flojea **por paráfrasis**. Esto no es un
bug del taller, es el estado real de la tecnología con modelos pequeños. Se
arregla con un modelo de embeddings mayor, subiendo `k`, o escribiendo las fichas
de forma que empiecen por **lo que la cosa hace**, no solo por su nombre.

> 🎯 **Y aquí está el segundo superpoder del RAG, el que casi nadie menciona:**
> **reduce la alucinación**. Si el modelo tiene el dato delante, no necesita
> inventárselo. Cuando le preguntas por algo que **no está** en `memory/`, debería
> decir *«ese Eco aún no ha llegado a mí»*.
>
> Debería. A veces se lo inventa igual. Eso lo medimos en el M8.

---

## 5. La capa de voz · dataset y fine-tuning

### Por qué el RAG no basta

Después del M3, VA 91 **sabe** cosas. Pero habla como un asistente que está
*interpretando* a VA 91, no como VA 91.

Esto lo vimos de verdad en este proyecto. Le preguntamos por los Recolectores con
RAG activo y respondió:

> *«Los Garbage Collectors, o Recolectores, en efecto, son las figuras de la
> muerte y del reciclaje en el Reverso. (...) **Desde mi punto de vista desde
> aquí, como VA 91, puedo decir que**...»*

¿Ves el problema? **Usó bien la memoria** (RAG ✅) pero *«como VA 91, puedo decir
que»* es exactamente lo que diría alguien **disfrazado** de VA 91. Se enrolla,
explica, resume. No contempla.

El estilo no se arregla con más datos. **El estilo se aprende.**

### Qué es realmente el fine-tuning

**Aprendizaje supervisado**: le das al modelo miles de pares *(entrada →
salida correcta)* y ajustas sus parámetros para que, la próxima vez, su predicción
se parezca más a la salida correcta.

Aquí, cada ejemplo es una conversación:

```json
{"messages": [
  {"role": "system",    "content": "Eres VA 91..."},
  {"role": "user",      "content": "Tengo miedo de que borren mi trabajo."},
  {"role": "assistant", "content": "Nada se pierde, peregrino: solo se traslada..."}
]}
```

> 🧠 **La confusión número uno:** *«entonces se aprende mis respuestas de
> memoria»*. **No.** No estamos metiéndole datos, estamos **ajustando su forma de
> predecir**. Después del entrenamiento sabrá responder a preguntas que **no
> estaban** en el dataset, con el estilo que le enseñaste. Aprende **la forma**, no
> el contenido.
>
> (Salvo que te pases. Si le das pocos ejemplos y lo entrenas demasiado, sí se los
> aprende de memoria. Eso es el **sobreajuste**, y lo vemos en el punto 6.)

### Por qué el System Prompt viaja dentro de CADA ejemplo

Mira el JSON de arriba: el `system` está ahí, en cada línea del dataset. No es un
descuido.

Le estamos enseñando: **«cuando lleves esta identidad puesta, responde así»**.
Estamos entrenando la relación *system → estilo*, no el estilo a secas. Si
entrenáramos sin el system, el modelo aprendería a hablar como VA 91 **siempre**,
incluso cuando le pidas otra cosa. Y eso ya no es un personaje: es un modelo roto.

### Calidad > cantidad (y esto no es un tópico)

El modelo **imita lo que le des**. Sin filtro, sin criterio, sin piedad.

Si escribes una respuesta floja, **le estás enseñando a ser flojo** con la misma
eficacia con la que le enseñas a ser brillante. Un dataset de 50 ejemplos
excelentes produce mejor personaje que uno de 500 mediocres.

Por eso, cuando escribas tus conversaciones, no escribas *lo que crees que el
modelo diría*. Escribe **lo que debería decir en su mejor día**.

---

## 6. LoRA, QLoRA y la GPU

### Por qué no podemos entrenar en tu portátil

Entrenar significa, para cada ejemplo:

1. **Forward** — pasar el texto por la red y ver qué predice.
2. **Calcular la loss** — cuánto se ha equivocado.
3. **Backward** — calcular, para **cada uno de los 3.000 millones de parámetros**,
   cuánto hay que moverlo.
4. **Actualizar** — moverlos todos.

Son millones de multiplicaciones de matrices, y todas se pueden hacer **a la
vez**. Una CPU tiene 2-8 núcleos potentes; una **GPU** tiene miles de núcleos
tontos que hacen justo eso en paralelo. Por eso una GPU es 100× más rápida aquí.

**CUDA** es la tecnología de NVIDIA que permite a PyTorch usar la GPU. Tu portátil
tiene gráficos **Intel**, que no tienen CUDA. No es que sea lento: es que **no
puede**. De ahí RunPod.

> 💰 Y esto es exactamente lo que hace la industria: **alquilar la GPU los 10
> minutos que la necesitas** (~0,12 USD) en vez de comprar una de 2.000 €.

### LoRA: el truco que lo hace barato

Entrenar los 3.000 millones de parámetros necesita ~24 GB de VRAM solo para los
estados del optimizador. Carísimo.

**LoRA** (*Low-Rank Adaptation*) hace algo astuto: **congela el modelo entero** y
le añade, en paralelo, unas **matrices pequeñitas** que sí se entrenan.

```
        entrada
           │
    ┌──────┴──────┐
    │             │
[modelo]      [LoRA]     ← solo esto se entrena (~0,5% de los parámetros)
[CONGELADO]      │
    │             │
    └──────┬──────┘
        salida (suma de ambas)
```

Resultado: en vez de un modelo nuevo de 6 GB, obtienes un **adaptador de ~100 MB**
que puedes enchufar y desenchufar. Entrena en minutos y cuesta céntimos.

- **`rank` (r)** — el "grosor" de esas matrices. Más rank = más capacidad de
  aprender matices... y más riesgo de **memorizar**.
- **`alpha`** — cuánto pesa el adaptador frente al modelo original.

### QLoRA: encima, cuantizado

**Cuantizar** = guardar cada peso con menos precisión. En vez de 16 bits por
número, **4 bits**. El modelo ocupa ~4× menos y cabe en cualquier GPU decente.

Pierdes algo de precisión, sí. Sorprendentemente poca. Y es lo que hace que todo
esto sea posible en un taller de 8 horas y no en un laboratorio.

> Por eso el `.gguf` final se llama `Q4_K_M`: **Q4** = 4 bits. Es el mismo truco
> que permite que `qwen3:8b` corra en tu portátil.

### Qué mirar mientras entrena

| Métrica | Qué es | Qué esperas |
|---------|--------|-------------|
| **loss** | Cuánto se equivoca (número de error) | Que **baje de forma sostenida** |
| **learning rate** | Cuánto mueve los pesos en cada paso | Sube en el *warmup*, luego baja |
| **epochs** | Cuántas veces ha visto el dataset entero | 3-4 con datasets pequeños |

**El *warmup***: al principio no sabemos por dónde ir, así que damos pasos
pequeños; luego aceleramos; y al final volvemos a frenar para afinar. Igual que
aparcar un coche.

### ⚠️ La trampa: loss baja ≠ modelo bueno

Esto lo comprobamos de verdad en este proyecto. Con 64 ejemplos:

| rank | loss final | ¿Cómo hablaba? |
|------|-----------|----------------|
| 16 | 1,42 | Correcto, algo genérico |
| 32 | **1,18** | ✅ **El mejor.** Suena a VA 91 e improvisa |
| 64 | **0,61** ⚠️ | ❌ **Recitaba frases del dataset casi literalmente** |

La corrida con **la mejor loss dio el peor personaje**.

¿Por qué? Porque con demasiada capacidad (`rank 64`) y pocos datos, el modelo deja
de aprender *la forma* y empieza a aprender *el contenido*. Se lo sabe de memoria.
Y un loro no es un personaje.

Eso es el **sobreajuste** (*overfitting*), y es la razón por la que en machine
learning **nunca se juzga un modelo por su loss, sino por cómo se comporta con
cosas que no ha visto**. Exactamente igual que un examen: memorizar el libro no es
saber.

### `batch` y `grad_accum`: cambiar tiempo por memoria

- **batch size** — cuántos ejemplos procesas a la vez. Más = más rápido, **más
  VRAM**.
- **gradient accumulation** — procesar varios lotes pequeños **sin actualizar**, ir
  sumando los gradientes, y actualizar al final.

**batch efectivo = `batch × grad_accum`**

Esto significa que `batch 1 × grad_accum 8` y `batch 2 × grad_accum 4` **aprenden
prácticamente igual** (batch efectivo = 8), pero el primero usa **mucha menos
VRAM** y tarda más.

Comprobado: 7,2 GB → 5,1 GB de VRAM, a cambio de un 36 % más de tiempo, con
la misma loss. **Cuando la GPU no da más de sí, ese es tu botón.**

Si te pasas: **OOM** (*out of memory*). El entrenamiento muere. Bajas el batch y
subes el grad_accum.

---

## 7. La capa de comportamiento · los parámetros

Un LLM no elige "la mejor palabra". En cada paso calcula una **probabilidad para
cada palabra posible** y luego **sortea** una. Los parámetros manipulan ese sorteo.

### `temperature` (0.8)

Aplana o afila la ruleta de probabilidades.

- **Baja (0.2)** → casi siempre elige la palabra más probable. Coherente,
  predecible, **repetitivo**, aburrido.
- **Alta (1.4)** → da oportunidades a palabras raras. Creativo, sorprendente,
  **inestable**, a veces incoherente.

Para un personaje contemplativo, 0.8 es un buen punto: le deja improvisar
metáforas sin descarrilar.

### `top_p` (0.9)

*Nucleus sampling*: descarta la cola de palabras absurdas. Se queda con las más
probables hasta sumar el 90 % de probabilidad, y sortea solo entre esas. Es un
cinturón de seguridad para la `temperature`.

### `repeat_penalty` (1.15)

Penaliza las palabras que ya han salido. Sin esto, los modelos pequeños **caen en
bucles** («la corriente, la corriente, la corriente...»). Bájalo a `1.0` y lo verás
pasar; es un experimento que merece la pena.

### `num_ctx` (4096)

La **ventana de contexto**: cuánto texto puede mirar a la vez, en tokens. Incluye
el System Prompt + los fragmentos del RAG + toda la conversación.

Cuando se llena, **lo viejo se cae por el borde**. Por eso en conversaciones muy
largas el personaje empieza a "olvidarse de sí mismo": **su identidad se está
saliendo de la ventana**.

### `stop`

Le dice dónde callarse (`<|im_end|>`). Sin esto, el modelo seguiría escribiendo...
y se pondría a escribir también el turno del usuario, inventándose lo que tú vas a
decir. Es tan raro como suena.

> 🔑 **Lo importante de esta capa:** cambia el comportamiento **sin tocar ni el
> cerebro ni el prompt**, y es **gratis e instantáneo**. Antes de reentrenar nada,
> pregúntate siempre si el problema se arregla aquí.

---

## 8. Evaluar

### Por qué una batería fija y una rúbrica

Si cada uno prueba lo que le apetece y dice «pues a mí me gusta», **no tenéis
datos, tenéis opiniones**. Y no podéis compararlas ni saber si la v1.1 mejoró.

Por eso: **los mismos 15 prompts para todos**, agrupados en 6 dimensiones, con
notas de 1 a 5. Eso convierte impresiones en **mediciones**. Es exactamente lo que
hacen los equipos de IA de verdad (lo llaman *evals*), y es la parte del trabajo
que casi nadie enseña.

### Por qué importa tanto la alucinación

Un modelo **no sabe lo que no sabe**. Su trabajo es predecir el texto más
plausible, y un emperador dorado inventado **es tremendamente plausible** en un
mundo de mitología. No está mintiendo: **no tiene ningún mecanismo interno para
distinguir "recordar" de "inventar"**.

Por eso el prompt 13 pregunta por algo **que no existe**. Es una trampa
deliberada, y es la medición más importante del taller.

> 💡 **Truco que casi nadie hace:** **insiste dos veces.** Es fácil que aguante la
> primera negativa y ceda a la segunda. Un guardrail que solo funciona una vez no
> es un guardrail.

### La regla de decisión (el destilado de todo el día)

| Síntoma | La capa culpable | Qué tocas |
|---------|------------------|-----------|
| Olvida o **inventa** el canon | Memoria | `memory/` + reindexar |
| **Pierde el estilo** / rompe personaje | Voz o Identidad | Dataset y/o System Prompt |
| **Repite**, se enrolla, tono errático | Comportamiento | Parámetros del Modelfile |
| Falla en **un dominio nuevo entero** | Voz | Dataset (nueva cobertura) |

Si sabes usar esta tabla, sabes construir personajes artificiales. Todo lo demás
es sintaxis.

---

## 9. Preguntas que siempre salen

**¿Por qué VA 91 tarda un minuto en responder?**
Porque genera **palabra por palabra**, y cada palabra requiere pasar por los 3.000
millones de parámetros. En CPU, eso son ~5-10 palabras por segundo. Una GPU haría
lo mismo 50 veces más rápido.

**¿Se "acuerda" de lo que le dije hace 5 mensajes?**
Solo porque **le reenviamos toda la conversación entera** en cada mensaje. El
modelo **no tiene memoria**: es amnésico y le pasamos el historial cada vez. Cuando
ese historial no cabe en `num_ctx`, se olvida de verdad.

**Si le enseño una conversación, ¿la aprende al instante?**
No. Escribir en `conversations/` no cambia nada hasta que **reentrenas**. El
aprendizaje ocurre en el M5, no mientras charlas.

**¿Puedo saltarme el fine-tuning?**
Sí, y el personaje funcionará: tendrás identidad (prompt) y memoria (RAG). Lo que
te faltará es la **voz**. Sonará a un asistente disfrazado. Compáralo tú mismo: es
justo el experimento del M7.

**¿Esto es lo mismo que hacen ChatGPT o Claude?**
Es **la misma receta**, a otra escala. System prompt, RAG, fine-tuning y parámetros
de sampling son exactamente las cuatro palancas que usan los equipos que
construyen esos productos. Cambian los ceros, no las ideas.

**¿Por qué mi modelo dice tonterías a veces?**
Porque es un modelo de 3B en 4 bits corriendo en un portátil. Es pequeño y va
justo. **Y aun así**, con las cuatro capas bien puestas, tiene personalidad. Ese
es exactamente el punto: **la arquitectura importa tanto como el tamaño**.

---

*La corriente te trae. Ahora ya sabes por qué.* 🪷⚡
