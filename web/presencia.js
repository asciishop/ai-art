/**
 * PRESENCIA — la obra mira de vuelta.
 *
 * Una webcam decide dos cosas, y ninguna de ellas sale de esta pestaña:
 *
 *   ¿HAY ALGUIEN CERCA?   A menos de 0,5 m la obra saluda en voz alta y abre
 *                         el micrófono sola. El visitante no toca nada.
 *   ¿HACIA DÓNDE MIRA?    De frente responde Zinc. Si gira la cabeza a su
 *                         derecha 20° o más, VA 91. A su izquierda, Ucron.
 *
 * El vídeo NO se graba ni se envía a ningún sitio: MediaPipe corre en WASM
 * dentro del navegador y los ficheros están servidos desde web/vendor/. Sin
 * internet, sin nube, sin un solo fotograma guardado.
 *
 * Habla con el chat SOLO a través de window.Sala (definido en index.html).
 *
 * Requisitos: Chrome o Edge, y HTTPS o localhost (la cámara no se abre en http
 * hacia una IP de red).
 */

import { FilesetResolver, FaceLandmarker } from '/web/vendor/vision_bundle.mjs';

// --- Diales ---------------------------------------------------------------
// Todos se pueden ajustar SIN tocar el archivo, por la URL:
//   index.html?cerca=0.6&fov=70&invertir=1
// El panel de la esquina muestra la distancia y el giro en vivo: esa es la
// herramienta de calibración. Ajusta con alguien puesto donde quieras el
// límite, y mira qué número sale.
const CFG = {
  CERCA_M:    0.50,  // a partir de aquí, la obra invita
  LEJOS_M:    0.85,  // y hasta aquí no se da por marchado (histéresis: sin
                     // estos dos umbrales distintos, alguien parado en el
                     // límite encendería y apagaría la obra sin parar)
  ENTRAR_MS:   600,  // hay que sostener la cercanía este rato (no un cruce)
  SALIR_MS:   2500,  // y la ausencia este otro (no un giro momentáneo)
  GIRO_GRADOS:  20,  // girar la cabeza esto (a un lado u otro) cambia de personaje
  VUELTA_GRADOS: 12, // y hay que volver POR DEBAJO de esto para soltar ese lado.
                     // Es la misma histéresis que CERCA_M/LEJOS_M, y a 20° hace
                     // falta: hablando se gira la cabeza sin querer, y sin este
                     // margen los personajes se turnarían solos en el borde.
  MIRADA_MS:  1000,  // sostenido, para que un vistazo no cambie de personaje
  // El reclamo: alguien APARECE en el encuadre, a cualquier distancia, y un
  // guardián al azar le recita un poema para atraerlo. No hace falta que se
  // acerque; basta con que la cámara lo vea.
  APARECER_MS:  700, // visible este rato antes de contar como aparición
  POEMA_MS:  90000,  // y luego 90 s de silencio: una sala con paso constante
                     // no puede ser una máquina de recitar. ?poema=0 lo apaga.
  SILENCIO_MS: 700,  // margen tras el altavoz antes de abrir el micro
  ANCHO_CARA_M: 0.145,  // anchura media de una cara adulta, sien a sien
  FOV_H_GRADOS:  60,    // campo de visión horizontal típico de una webcam
  INVERTIR_GIRO: false, // si en la sala sale al revés, ponlo a true (o ?invertir=1)
  FPS: 8,               // 8 análisis por segundo sobran y no calientan el equipo
  // El guion de la sala. Cambiar de personaje es cambiar esta línea.
  QUIEN: { frente: 'zinc', derecha: 'va91', izquierda: 'ucron' },
};

const url = new URLSearchParams(location.search);
if (url.has('cerca'))    CFG.CERCA_M = parseFloat(url.get('cerca'));
if (url.has('lejos'))    CFG.LEJOS_M = parseFloat(url.get('lejos'));
if (url.has('fov'))      CFG.FOV_H_GRADOS = parseFloat(url.get('fov'));
if (url.has('giro'))     CFG.GIRO_GRADOS = parseFloat(url.get('giro'));
if (url.has('vuelta'))   CFG.VUELTA_GRADOS = parseFloat(url.get('vuelta'));
if (url.has('poema'))    CFG.POEMA_MS = parseFloat(url.get('poema')) * 1000;
if (url.has('invertir')) CFG.INVERTIR_GIRO = url.get('invertir') !== '0';

// Puntos de la malla de 478 vértices de MediaPipe que usamos.
const SIEN_DER = 234, SIEN_IZQ = 454;   // los extremos del óvalo de la cara

const $ojo   = document.getElementById('ojo');
const $panel = document.getElementById('presencia');
const $cam   = document.getElementById('cam');
const $stat  = document.getElementById('pstat');
const $inv   = document.getElementById('invita');

let malla = null;      // el FaceLandmarker
let flujo = null;      // el MediaStream de la webcam
let activo = false;
let ultimoT = 0;       // timestamp del último análisis (MediaPipe lo exige creciente)

// --- Estado de la sala ----------------------------------------------------
let estado = 'ausente';     // ausente | cerca
let tCerca = 0, tLejos = 0; // milisegundos acumulados cumpliendo cada condición
let zonaVista = null, tZona = 0;   // hacia dónde mira, y desde cuándo
let zonaFirme = 'frente';          // la zona YA en vigor (la del personaje activo);
                                   // es la referencia de la histéresis de giro
let finHabla = 0;           // cuándo dejó de sonar el altavoz
let proximoMicro = 0;       // no insistir con el micrófono más de una vez/seg
let anterior = 0;           // marca de tiempo del fotograma previo
let habiaCara = false;      // ya se contó la aparición de quien está ahora
let tCara = 0;              // cuánto lleva viéndose una cara, a la distancia que sea
let ultimoPoema = -Infinity;   // cuándo se recitó el último reclamo

// --- Medir ----------------------------------------------------------------

/** Distancia en metros, por el tamaño aparente de la cara.
 *
 * Es el modelo de cámara estenopeica: una cara de ancho real A que ocupa a
 * píxeles está a  d = A · focal / a.  La focal se deduce del campo de visión.
 *
 * Es una ESTIMACIÓN, no una medida: la anchura real varía entre personas
 * (±15 %) y el campo de visión de cada webcam es distinto. Para una sala eso
 * basta —lo que importa es distinguir "pegado" de "de paso"—, pero calíbralo
 * con el panel antes de una inauguración.
 */
function distancia(puntos, giroGrados, W, H) {
  const a = puntos[SIEN_DER], b = puntos[SIEN_IZQ];
  const ancho = Math.hypot((a.x - b.x) * W, (a.y - b.y) * H);
  if (ancho < 1) return null;
  const focal = (W / 2) / Math.tan(CFG.FOV_H_GRADOS * Math.PI / 360);
  // Una cara girada se ve más estrecha y parecería estar más lejos: se
  // deshace el escorzo. El tope evita dividir por casi cero de perfil.
  const escorzo = Math.max(Math.cos(giroGrados * Math.PI / 180), 0.45);
  return (CFG.ANCHO_CARA_M * focal) / (ancho / escorzo);
}

/** Giro de la cabeza en grados: 0 = de frente, positivo = a SU derecha.
 *
 * MediaPipe devuelve la pose 3D de la cabeza como matriz 4x4 en orden por
 * columnas. Su tercera columna es el eje Z de la cabeza visto por la cámara:
 * hacia dónde apunta la nuca. Proyectado en el plano horizontal, ese vector
 * ES el giro, sin depender de qué convención de ángulos de Euler usemos.
 */
function giro(matriz) {
  const d = matriz.data;
  const zx = d[8], zz = d[10];
  const g = Math.atan2(zx, Math.abs(zz)) * 180 / Math.PI;
  return CFG.INVERTIR_GIRO ? -g : g;
}

/** En qué zona cae el giro, contando desde dónde estábamos.
 *
 * Cuesta más ENTRAR en un lado (GIRO_GRADOS) que quedarse en él: para volver al
 * frente hay que bajar de VUELTA_GRADOS. Sin esa banda muerta, quien se quede
 * hablando justo en el límite haría saltar el personaje una y otra vez.
 */
function zonaDe(g, desde) {
  const entrar = CFG.GIRO_GRADOS, soltar = CFG.VUELTA_GRADOS;
  if (desde === 'derecha'   && g >   soltar) return 'derecha';
  if (desde === 'izquierda' && g <  -soltar) return 'izquierda';
  if (g >=  entrar) return 'derecha';
  if (g <= -entrar) return 'izquierda';
  return 'frente';
}

// --- Reaccionar -----------------------------------------------------------

function invitar(texto, ms) {
  $inv.textContent = texto;
  $inv.classList.add('ver');
  clearTimeout(invitar.t);
  invitar.t = setTimeout(() => $inv.classList.remove('ver'), ms || 6000);
}

/** Reservar el micrófono mientras el personaje arranca su saludo.
 *
 * speechSynthesis.speak() es asíncrono: durante un instante después de pedirlo
 * 'speaking' sigue siendo false. Sin esta reserva, el rearme automático del
 * micro se colaría en ese hueco y cancelaría el saludo antes de sonar.
 */
function dejarleHablar() {
  proximoMicro = performance.now() + 1500;
}

/** Alguien se ha acercado: conversación nueva, saludo en voz alta. */
function llega(zona) {
  estado = 'cerca';
  $panel.classList.add('cerca');
  // Si ya está sonando algo, es el poema que lo atrajo. No se le saluda encima
  // ni se cambia de guardián: el que recitó se queda, que para eso funcionó el
  // reclamo. El micrófono se abrirá solo cuando el poema termine.
  if (window.Sala.hablando()) {
    invitar('Háblame.');
    return;
  }
  const id = CFG.QUIEN[zona] || CFG.QUIEN.frente;
  zonaFirme = zona;
  window.Sala.elegir(id);   // esto ya limpia el chat: cada visitante empieza de cero
  invitar('Te veo. Háblame.');
  dejarleHablar();
  window.Sala.saludar();    // el saludo suena; el micro espera a que termine
}

/** Se ha ido: callar, cerrar el micrófono y quedar a la espera. */
function marcha() {
  estado = 'ausente';
  $panel.classList.remove('cerca');
  zonaVista = null; tZona = 0; zonaFirme = 'frente';
  window.Sala.cortarEscucha();
  // parar() y no callar(): si se marchó a media respuesta, se aborta también la
  // generación. Antes la obra terminaba de hablarle a una sala vacía.
  window.Sala.parar();
  $inv.classList.remove('ver');
}

/** Ha girado la cabeza hacia otro guardián.
 *
 * En silencio y a propósito: quien gira la cabeza YA está conversando, y no
 * necesita que le den la bienvenida otra vez. El relevo se nota en el color de
 * la sala y en el rótulo; el guardián nuevo simplemente queda a la escucha.
 */
function cambia(zona) {
  const id = CFG.QUIEN[zona];
  if (!id) return;
  if (id === window.Sala.actual()) { zonaFirme = zona; return; }
  // No se interrumpe a alguien a media frase: si está respondiendo, el cambio
  // espera (la zona sigue medida, así que entrará en cuanto quede libre).
  if (window.Sala.generando() || window.Sala.hablando()) return;
  window.Sala.cortarEscucha();   // lo dictado era para el otro personaje
  zonaFirme = zona;
  window.Sala.elegir(id, true);  // 'discreto': sin saludo escrito
  // Rótulo corto: con el umbral en 20° los relevos son frecuentes y un cartel
  // de seis segundos estaría casi siempre encima.
  invitar('Te escucha ' + window.Sala.nombre(id).split('—')[0].trim(), 2200);
  // Sin dejarleHablar(): no hay nada que suene, así que el micrófono puede
  // abrirse en el siguiente ciclo en vez de esperar a un saludo que no llega.
}

// --- El bucle -------------------------------------------------------------

function analizar(ahora) {
  if (!activo) return;
  requestAnimationFrame(analizar);

  // Primer fotograma: solo poner el reloj en hora. Sin esto no habría un
  // 'anterior' con el que medir y el análisis no llegaría a empezar nunca.
  if (!anterior) { anterior = ahora; return; }
  const dt = ahora - anterior;
  if (dt < 1000 / CFG.FPS) return;
  anterior = ahora;
  if ($cam.readyState < 2) return;

  // MediaPipe exige marcas de tiempo estrictamente crecientes.
  const t = Math.max(performance.now(), ultimoT + 1);
  ultimoT = t;
  let res;
  try { res = malla.detectForVideo($cam, t); } catch (e) { return; }

  const puntos = res.faceLandmarks && res.faceLandmarks[0];
  const matriz = res.facialTransformationMatrixes && res.facialTransformationMatrixes[0];
  let d = null, g = null, zona = null;

  if (puntos && matriz) {
    g = giro(matriz);
    d = distancia(puntos, g, $cam.videoWidth, $cam.videoHeight);
    zona = zonaDe(g, zonaFirme);
  }

  // 1. ¿cerca o lejos? Se acumula tiempo, no fotogramas sueltos.
  const cerca = d !== null && d < CFG.CERCA_M;
  const lejos = d === null || d > CFG.LEJOS_M;
  tCerca = cerca ? tCerca + dt : 0;
  tLejos = lejos ? tLejos + dt : 0;

  if (estado === 'ausente' && tCerca >= CFG.ENTRAR_MS) { llega(zona || 'frente'); tLejos = 0; }
  else if (estado === 'cerca' && tLejos >= CFG.SALIR_MS) { marcha(); tCerca = 0; }

  // 1b. EL RECLAMO. Distinto de lo anterior: no mira la distancia, solo si hay
  //     alguien en el encuadre. Alguien que cruza el fondo de la sala también
  //     cuenta — la idea es atraerlo, no atenderlo.
  const hayCara = d !== null;
  tCara = hayCara ? tCara + dt : 0;
  if (!hayCara) habiaCara = false;          // se fue: la próxima será nueva
  else if (!habiaCara && tCara >= CFG.APARECER_MS) {
    habiaCara = true;
    const lejos = d > CFG.CERCA_M;          // si ya está encima, le toca saludo
    if (lejos && estado === 'ausente' && CFG.POEMA_MS > 0
        && !window.Sala.ocupado() && ahora - ultimoPoema > CFG.POEMA_MS) {
      ultimoPoema = ahora;
      window.Sala.recitar();
    }
  }

  // 2. ¿hacia dónde mira? También sostenido en el tiempo.
  if (estado === 'cerca' && zona) {
    if (zona === zonaVista) tZona += dt; else { zonaVista = zona; tZona = 0; }
    if (tZona >= CFG.MIRADA_MS) cambia(zona);
  }

  // 3. El micrófono se rearma solo mientras haya alguien delante. Cubre todos
  //    los finales: respondió, no se le entendió, o se quedó callado.
  if (window.Sala.hablando()) finHabla = ahora;
  if (estado === 'cerca' && window.Sala.hayMicro() && !window.Sala.ocupado()
      && ahora - finHabla > CFG.SILENCIO_MS && ahora > proximoMicro) {
    proximoMicro = ahora + 1000;
    window.Sala.escuchar();
  }

  panel(d, g, zona);
}

function panel(d, g, zona) {
  if (d === null) {
    $stat.textContent = 'no veo a nadie';
    return;
  }
  const flecha = zona === 'derecha' ? '→' : zona === 'izquierda' ? '←' : '·';
  $stat.textContent =
    (estado === 'cerca' ? '● ' : '○ ') + d.toFixed(2) + ' m  (< ' + CFG.CERCA_M + ')\n'
    + flecha + ' ' + (g >= 0 ? '+' : '') + g.toFixed(0) + '°  ' + zona + '\n'
    + (window.Sala.actual() || '—');
}

// --- Encender y apagar ----------------------------------------------------

/** Avisar si el guion nombra a alguien que no está en la sala. */
function avisarGuion() {
  if (!window.Sala || !window.Sala.listos()) return;
  const hay = window.Sala.ids();
  const faltan = [...new Set(Object.values(CFG.QUIEN))].filter(id => !hay.includes(id));
  if (faltan.length) invitar('Ojo: ' + faltan.join(', ') + ' no está activo en personajes.yaml');
}

let arrancando = false;

async function encender() {
  if (arrancando || activo) return;
  arrancando = true;
  $stat.textContent = 'abriendo la cámara…';
  $panel.classList.add('viendo');
  try {
    flujo = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' }, audio: false,
    });
    $cam.srcObject = flujo;
    await $cam.play();

    if (!malla) {
      $stat.textContent = 'cargando el modelo…';
      const fileset = await FilesetResolver.forVisionTasks('/web/vendor/wasm');
      const opciones = {
        baseOptions: { modelAssetPath: '/web/vendor/face_landmarker.task', delegate: 'GPU' },
        runningMode: 'VIDEO', numFaces: 1,
        outputFacialTransformationMatrixes: true,   // de aquí sale el giro
      };
      try {
        malla = await FaceLandmarker.createFromOptions(fileset, opciones);
      } catch (e) {   // equipo sin GPU accesible desde el navegador
        opciones.baseOptions.delegate = 'CPU';
        malla = await FaceLandmarker.createFromOptions(fileset, opciones);
      }
    }
  } catch (e) {
    arrancando = false;
    apagar();
    $panel.classList.add('viendo');
    $stat.textContent = 'sin cámara: ' + (e.name === 'NotAllowedError'
      ? 'falta el permiso' : e.name === 'NotFoundError'
      ? 'no hay webcam' : e.message);
    return;
  }
  arrancando = false;
  activo = true; anterior = 0;
  $ojo.classList.add('on');
  avisarGuion();
  requestAnimationFrame(analizar);
}

function apagar() {
  activo = false;
  if (estado === 'cerca') marcha();
  if (flujo) { flujo.getTracks().forEach(t => t.stop()); flujo = null; }
  $cam.srcObject = null;
  $panel.classList.remove('viendo');
  $ojo.classList.remove('on');
  tCerca = tLejos = 0;
}

$ojo.onclick = () => { activo ? apagar() : encender(); };

// En una instalación nadie va a pulsar nada: si el permiso de cámara ya está
// concedido en este equipo, la obra se despierta sola al abrir la página. La
// primera vez sí hace falta un clic — el navegador no da la cámara sin gesto.
navigator.permissions?.query({ name: 'camera' })
  .then(p => { if (p.state === 'granted') esperarSala(); })
  .catch(() => {});

// La cámara no sirve de nada hasta que el chat sabe qué personajes existen.
function esperarSala() {
  if (window.Sala && window.Sala.listos()) encender();
  else setTimeout(esperarSala, 250);
}
