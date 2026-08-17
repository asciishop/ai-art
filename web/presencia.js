/**
 * PRESENCIA — la obra mira de vuelta.
 *
 * Una webcam decide dos cosas, y ninguna de ellas sale de esta pestaña:
 *
 *   ¿HAY ALGUIEN CERCA?   A menos de 0,5 m la obra saluda en voz alta y abre
 *                         el micrófono sola. El visitante no toca nada.
 *   ¿HACIA DÓNDE MIRA?    De frente responde Zinc. Si gira la cabeza a su
 *                         derecha 15° o más, VA 91. A su izquierda, Ucron.
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
  GIRO_GRADOS:  15,  // girar la cabeza esto (a un lado u otro) cambia de personaje
  VUELTA_GRADOS:  9, // y hay que volver POR DEBAJO de esto para soltar ese lado.
                     // Es la misma histéresis que CERCA_M/LEJOS_M, y hace falta:
                     // hablando se gira la cabeza sin querer, y sin este margen
                     // los personajes se turnarían solos en el borde. Va atado a
                     // GIRO_GRADOS —unos dos tercios—, así que si bajas uno baja
                     // el otro: dejarlo alto estrecha la banda muerta y vuelve
                     // el temblor que este umbral existe para evitar.
  MIRADA_MS:  1000,  // sostenido, para que un vistazo no cambie de personaje
  // EL RECLAMO. No lo dispara una cara, sino MOVIMIENTO: quien pasa de largo
  // va de perfil, de espaldas o demasiado lejos para que el detector de caras
  // lo vea. Comparar un fotograma con el anterior no necesita modelo, funciona
  // a cualquier distancia y con cualquier cosa que cruce el encuadre.
  MOV_DELTA:    18,  // cuánto tiene que cambiar un píxel (0-255) para contar
  BORDE_FRAC: 0.25,  // qué parte del ancho, a cada lado, cuenta como BORDE.
                     // Solo dispara el movimiento de ahí: por los bordes es por
                     // donde ENTRA quien pasa de largo. Lo que se mueve en el
                     // centro es quien ya está delante, y ese no necesita que
                     // lo llamen — necesita que lo escuchen.
  MOV_UMBRAL: 0.02,  // fracción de la banda de borde en movimiento que dispara
  MOV_MAXIMO: 0.75,  // por encima de esto no es alguien: es que cambió la luz
                     // (se encendió una lámpara, o movieron la cámara)
  MOV_MS:      300,  // sostenido, para no saltar con un parpadeo del sensor
  POEMA_MS:  90000,  // y luego 90 s de silencio: una sala con paso constante
                     // no puede ser una máquina de recitar. ?poema=0 lo apaga.
  SILENCIO_MS: 700,  // margen tras el altavoz antes de abrir el micro
  ANCHO_CARA_M: 0.145,  // anchura media de una cara adulta, sien a sien
  FOV_H_GRADOS:  60,    // campo de visión horizontal típico de una webcam
  INVERTIR_GIRO: false, // si en la sala sale al revés, ponlo a true (o ?invertir=1)
  FPS: 8,               // 8 análisis por segundo sobran y no calientan el equipo
  // Qué cámara usar. Cuatro formas, y se puede forzar con ?cam=… :
  //   'usb'        la primera que NO sea la integrada  <- por defecto
  //   'integrada'  la del propio equipo
  //   'logitech'   cualquier trozo del nombre del dispositivo
  //   '1'          por índice en la lista
  // La elección queda guardada en el navegador. En la sala la webcam USB es la
  // que está colocada y encuadrada; la integrada del portátil mira a otro sitio.
  CAMARA: 'usb',
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
if (url.has('mov'))      CFG.MOV_UMBRAL = parseFloat(url.get('mov'));
// La cámara se recuerda entre sesiones: en una instalación se elige una vez con
// ?cam=... y el kiosco ya arranca solo con la correcta, sin URL especial.
if (url.has('cam')) {
  CFG.CAMARA = url.get('cam');
  try { localStorage.setItem('camara', CFG.CAMARA); } catch (e) {}
} else {
  try {
    // Los equipos donde ya se probó la obra tienen guardado 'integrada', que era
    // el valor por defecto anterior, y sin esto seguirían abriendo esa cámara
    // para siempre. Se descarta UNA sola vez; un ?cam=integrada posterior vuelve
    // a guardarse y se respeta.
    if (!localStorage.getItem('camara_usb_por_defecto')) {
      if ((localStorage.getItem('camara') || '').trim().toLowerCase() === 'integrada') {
        localStorage.removeItem('camara');
      }
      localStorage.setItem('camara_usb_por_defecto', '1');
    }
    // Si no hay nada guardado se conserva el valor por defecto de CFG, no ''.
    CFG.CAMARA = localStorage.getItem('camara') || CFG.CAMARA;
  } catch (e) {}
}
if (url.has('invertir')) CFG.INVERTIR_GIRO = url.get('invertir') !== '0';

// Puntos de la malla de 478 vértices de MediaPipe que usamos.
const SIEN_DER = 234, SIEN_IZQ = 454;   // los extremos del óvalo de la cara

const $ojo   = document.getElementById('ojo');
const $panel = document.getElementById('presencia');
// El visor enseña SOLO los números. La imagen de la webcam se pide aparte, con
// ?video=1, y es cosa del montaje: encuadrar la cámara sin verla es imposible.
if (url.get('video') === '1') $panel.classList.add('convideo');
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
let tMov = 0;               // cuánto lleva habiendo movimiento sostenido
let ultimoPoema = -Infinity;   // cuándo se recitó el último reclamo

// --- Movimiento por zonas: ¿entra alguien, o es el que ya estaba? --------
// Diferencia entre fotogramas consecutivos sobre una miniatura de 64x48. A esa
// resolución son 3072 píxeles: se compara entera en una fracción de
// milisegundo, y basta de sobra para saber si algo se movió. No distingue una
// persona de un perro ni falta que hace: solo queremos saber que pasó ALGO.
//
// Se mide por separado en dos zonas, y esa es la clave del reclamo:
//
//   |####|            |####|     BORDES  -> alguien ENTRA en el campo de
//   |####|   centro   |####|                visión. Esto lanza el poema.
//   |####|            |####|     CENTRO  -> alguien que YA está delante.
//                                          Ese no se llama, se atiende.
const $lienzo = document.createElement('canvas');
$lienzo.width = 64;
$lienzo.height = 48;
const _ctx = $lienzo.getContext('2d', { willReadFrequently: true });
let _previo = null;

function movimiento() {
  const ancho = $lienzo.width, alto = $lienzo.height, n = ancho * alto;
  _ctx.drawImage($cam, 0, 0, ancho, alto);
  const px = _ctx.getImageData(0, 0, ancho, alto).data;
  const luma = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const j = i << 2;
    // luma aproximada con enteros: R*0.30 + G*0.59 + B*0.11
    luma[i] = (px[j] * 77 + px[j + 1] * 150 + px[j + 2] * 29) >> 8;
  }
  if (!_previo || _previo.length !== n) { _previo = luma; return { borde: 0, centro: 0 }; }

  const franja = Math.max(1, Math.round(ancho * CFG.BORDE_FRAC));
  let camBorde = 0, nBorde = 0, camCentro = 0, nCentro = 0;
  for (let y = 0; y < alto; y++) {
    const fila = y * ancho;
    for (let x = 0; x < ancho; x++) {
      const cambio = Math.abs(luma[fila + x] - _previo[fila + x]) > CFG.MOV_DELTA;
      if (x < franja || x >= ancho - franja) { nBorde++; if (cambio) camBorde++; }
      else { nCentro++; if (cambio) camCentro++; }
    }
  }
  _previo = luma;
  return { borde: camBorde / nBorde, centro: camCentro / nCentro };
}

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
  // Rótulo corto: con el umbral en 15° los relevos son frecuentes y un cartel
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

  // 1b. EL RECLAMO. Solo mira los BORDES del encuadre: por ahí es por donde
  //     entra el que pasa de largo. No exige cara (irá de perfil o de espaldas)
  //     ni cercanía (estará lejos). Del que ya se paró delante se ocupa el
  //     saludo de arriba, y de hacia dónde mira, el giro de cabeza.
  const mov = movimiento();
  const entraAlguien = mov.borde > CFG.MOV_UMBRAL && mov.borde < CFG.MOV_MAXIMO;
  tMov = entraAlguien ? tMov + dt : 0;
  if (tMov >= CFG.MOV_MS && estado === 'ausente' && CFG.POEMA_MS > 0
      && !window.Sala.ocupado() && ahora - ultimoPoema > CFG.POEMA_MS) {
    ultimoPoema = ahora;
    tMov = 0;
    window.Sala.recitar();
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

  panel(d, g, zona, mov, ahora);
}

function panel(d, g, zona, mov, ahora) {
  // El movimiento se muestra SIEMPRE, haya cara o no: es el dial del reclamo y
  // la única forma de ajustar MOV_UMBRAL sin ir a ciegas. Mira el número con la
  // sala vacía (debe rondar 0) y con alguien cruzando al fondo.
  const espera = Math.max(0, Math.ceil((CFG.POEMA_MS - (ahora - ultimoPoema)) / 1000));
  const linea = 'borde ' + (mov.borde * 100).toFixed(1) + '%'
              + (mov.borde > CFG.MOV_UMBRAL ? '▲' : ' ')
              + ' centro ' + (mov.centro * 100).toFixed(1) + '%\n'
              + (espera ? 'poema en ' + espera + 's' : 'poema listo')
              + '  (borde > ' + (CFG.MOV_UMBRAL * 100).toFixed(1) + '%)';
  if (d === null) {
    $stat.textContent = 'no veo ninguna cara\n' + linea;
    return;
  }
  const flecha = zona === 'derecha' ? '→' : zona === 'izquierda' ? '←' : '·';
  $stat.textContent =
    (estado === 'cerca' ? '● ' : '○ ') + d.toFixed(2) + ' m  (< ' + CFG.CERCA_M + ')\n'
    + flecha + ' ' + (g >= 0 ? '+' : '') + g.toFixed(0) + '°  ' + zona + '\n'
    + linea + '\n'
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

let avisoCamara = null;   // lo rellena elegirCamara(); lo muestra encender()

/** Las cámaras que el navegador deja ver ahora mismo.
 *
 * OJO: enumerateDevices() devuelve las etiquetas VACÍAS mientras no se haya
 * concedido permiso de cámara, y sin etiquetas no se puede distinguir la USB de
 * la integrada. Por eso encender() mira si YA hay nombres: si los hay abre
 * directamente la buena, y si no, pide un stream cualquiera solo para conseguir
 * el permiso. Ese es el único caso en que se enciende la cámara equivocada.
 */
async function camarasVisibles() {
  const camaras = (await navigator.mediaDevices.enumerateDevices())
                    .filter(d => d.kind === 'videoinput');
  console.info('Cámaras disponibles:',
    camaras.map((c, i) => `[${i}] ${c.label || '(sin permiso aún)'}`).join(' · '));
  return camaras;
}

// Los nombres varían mucho entre fabricantes, así que 'integrada'/'usb' son una
// heurística sobre la etiqueta. Si acierta mal, se fuerza por nombre o por
// índice —eso sí es exacto— y queda guardado.
const ESINTEGRADA = /integrat|built.?in|internal|facetime|surface|easy ?camera|hd user|webcam interna|c[áa]mara integrada|chicony|sunplus/i;
const esIntegrada = c => ESINTEGRADA.test((c && c.label) || '');

/** Ordena las cámaras por preferencia: la primera es la que más queremos.
 *
 * Devuelve TODAS y no solo la elegida, y eso es lo importante. La lista de
 * Windows viene llena de FANTASMAS: "USB Camera", "USB2.0 PC CAMERA"… entradas
 * que quedaron de webcams enchufadas alguna vez y que el sistema sigue
 * ofreciendo aunque no haya nada al otro lado. Por el nombre no hay manera de
 * distinguirlas —suenan más a USB que la buena, que se llama "HD 2MP WEBCAM"—,
 * así que la única prueba que vale es intentar abrirlas: la que abre, existe.
 *
 * De ahí que esto ordene en vez de decidir. Encender() baja por la lista hasta
 * que una responde. Al final van TODAS las demás, la integrada incluida: tuerta
 * es mejor que ciega, pero solo después de haberlo intentado con las buenas.
 */
function ordenarCamaras(camaras) {
  const pref = (CFG.CAMARA || '').trim().toLowerCase();
  let preferidas;

  if (/^\d+$/.test(pref)) {
    preferidas = [camaras[Math.min(+pref, camaras.length - 1)]];
  } else if (pref === 'integrada') {
    preferidas = camaras.filter(esIntegrada);
  } else if (pref === 'usb' || pref === 'externa' || !pref) {
    // Con nombre y que no suene a integrada. Las que no tienen nombre van
    // detrás: sin etiqueta no se puede afirmar nada de ellas.
    preferidas = camaras.filter(c => c.label && !esIntegrada(c));
  } else {
    preferidas = camaras.filter(c => (c.label || '').toLowerCase().includes(pref));
    if (!preferidas.length) {
      console.warn(`Ninguna cámara contiene "${pref}"; pruebo por orden de lista.`);
    }
  }

  const orden = [...preferidas, ...camaras.filter(c => !preferidas.includes(c))];
  console.info('Orden de preferencia:',
    orden.map(c => c.label || '(sin nombre)').join(' → '));
  return orden;
}

/** ¿Está puesto el micrófono USB de la sala, o el del portátil?
 *
 * LÍMITE DEL NAVEGADOR, y conviene saberlo antes de buscar el fallo aquí: el
 * reconocimiento de voz (Web Speech API, en index.html) NO acepta que se le
 * diga qué micrófono usar. No hay deviceId que valga: siempre coge el
 * PREDETERMINADO del sistema. Desde este archivo es imposible forzarlo.
 *
 * Así que se hace lo único que sí se puede: comprobarlo y decirlo. El arreglo
 * es de una vez y en Windows —Configuración › Sonido › Entrada, elegir el micro
 * de la webcam como predeterminado—, pero sin este aviso la sala solo da la
 * pista de que "se oye raro" y nadie sabe por qué.
 *
 * La forma fiable de reconocer el micro de la webcam no es el nombre: es el
 * groupId. El navegador da el MISMO groupId a la cámara y al micrófono del
 * mismo aparato físico, así que se pregunta por el de la cámara ya elegida.
 */
async function comprobarMicro(camara) {
  const micros = (await navigator.mediaDevices.enumerateDevices())
                   .filter(d => d.kind === 'audioinput');
  // 'default' y 'communications' son alias de Windows, no aparatos: apuntan a
  // otra entrada de la lista, y esa es la que tiene nombre propio.
  const real = m => m.deviceId !== 'default' && m.deviceId !== 'communications';
  const fisicos = micros.filter(real);
  if (!fisicos.length) return 'No hay ningún micrófono conectado.';
  if (!fisicos.some(m => m.label)) return null;   // sin permiso: nada que comparar

  console.info('Micrófonos:', fisicos.map((m, i) => `[${i}] ${m.label}`).join(' · '));

  const alias = micros.find(m => m.deviceId === 'default');
  const puesto = (alias && fisicos.find(m => m.groupId === alias.groupId)) || fisicos[0];

  // Primero por groupId, que es exacto: el micro incorporado a la webcam. Pero
  // MUCHAS webcams no llevan micro —la de esta sala, sin ir más lejos— y el que
  // hay junto a ella es otro aparato USB independiente, con su propio groupId.
  // Así que si no hay incorporado se busca por nombre: cualquiera que no sea el
  // del portátil (Realtek y compañía son las tarjetas de audio integradas).
  const ESINTEGRADO = /realtek|high definition audio|integrat|internal|built.?in|conexant|matriz de micr|microphone array/i;
  const dela = (camara && camara.groupId
                 && fisicos.find(m => m.groupId === camara.groupId))
            || fisicos.find(m => m.label && !ESINTEGRADO.test(m.label));

  if (!dela) {
    console.warn('No distingo ningún micrófono externo; se oirá por:',
      puesto && puesto.label);
    return null;
  }
  if (puesto && puesto.deviceId === dela.deviceId) {
    console.info('Micrófono en uso (el externo, el bueno):', dela.label);
    return null;
  }
  console.warn('El micrófono PREDETERMINADO es "' + (puesto ? puesto.label : '?')
    + '", no el externo ("' + dela.label + '"). El reconocimiento de voz '
    + 'del navegador no deja elegirlo desde la página: cámbialo en Windows › '
    + 'Configuración › Sonido › Entrada.');
  return 'Se está oyendo por el micro del equipo, no por el USB: '
       + 'cámbialo en Sonido › Entrada.';
}

let avisoMicro = null;
let arrancando = false;

/** Abrir UNA cámara concreta, insistiendo antes de darla por perdida.
 *
 * `NotReadableError` en Windows no significa solo "ocupada": es el error que da
 * Chrome cuando no consigue ARRANCAR la fuente de vídeo, y una webcam UVC barata
 * la provoca con facilidad si se le pide un formato que su driver no sirve de
 * buena gana. La HD 2MP WEBCAM de la sala entrega 1920x1080; pedirle 640x480 es
 * razonable —menos píxeles que analizar— pero no vale la pena morir por ello.
 *
 * De ahí la escalera: primero lo cómodo, luego lo que sea. El resto del archivo
 * no depende de la resolución (la distancia se mide con $cam.videoWidth y el
 * movimiento sobre una miniatura de 64x48), así que aceptar 1080p no rompe nada.
 */
async function abrirCamara(dev) {
  const id = { deviceId: { exact: dev.deviceId } };
  const intentos = [
    { video: id, audio: false },                                  // su formato nativo
    { video: { ...id, width: 640, height: 480 }, audio: false },  // por si acaso
  ];
  let ultimo;
  for (const peticion of intentos) {
    try {
      return await navigator.mediaDevices.getUserMedia(peticion);
    } catch (e) {
      ultimo = e;
      if (e.name === 'NotAllowedError') throw e;   // sin permiso no hay insistencia
      console.warn('  no abre con', JSON.stringify(peticion.video), '→', e.name);
    }
  }
  throw ultimo;
}

async function encender() {
  if (arrancando || activo) return;
  arrancando = true;
  avisoCamara = avisoMicro = null;   // de un intento anterior fallido
  $stat.textContent = 'abriendo la cámara…';
  $panel.classList.add('viendo');
  const VIDEO = { width: 640, height: 480 };
  try {
    // 1) ¿Se puede decidir YA? Si el permiso está concedido de una visita
    //    anterior, enumerateDevices() da los nombres sin abrir nada, y se abre
    //    directamente la buena. Esto es lo normal en la sala, y así la integrada
    //    no llega a encenderse ni un segundo.
    let camaras = await camarasVisibles();

    if (!camaras.some(c => c.label)) {
      // Primera vez en este equipo: sin permiso no hay nombres, y sin nombres no
      // hay forma de distinguirlas. Toca abrir una cualquiera —el navegador dará
      // la integrada— solo para que conceda el permiso. Se cierra enseguida.
      //
      // Se pide también el AUDIO, aunque aquí no se grabe ni un segundo: con
      // ello el navegador concede los dos permisos de una vez —el
      // reconocimiento de voz ya no vuelve a preguntar, que en un kiosco sin
      // teclado importa— y aparecen los NOMBRES de los micrófonos, sin los que
      // no hay forma de comprobar cuál está puesto.
      $stat.textContent = 'pidiendo permiso…';
      try {
        flujo = await navigator.mediaDevices.getUserMedia({ video: VIDEO, audio: true });
      } catch (e) {
        // Un equipo sin micrófono, o con el micrófono bloqueado, no puede quedarse
        // además sin ojos: se reintenta pidiendo solo vídeo.
        flujo = await navigator.mediaDevices.getUserMedia({ video: VIDEO, audio: false });
      }
      flujo.getAudioTracks().forEach(t => { t.stop(); flujo.removeTrack(t); });
      camaras = await camarasVisibles();
    }

    // 2) Bajar por la lista hasta que una se deje abrir de verdad.
    const orden = ordenarCamaras(camaras);
    const puesta = flujo && flujo.getVideoTracks()[0].getSettings().deviceId;
    let quiero = orden[0];

    if (!puesta || !orden[0] || puesta !== orden[0].deviceId) {
      // Windows no deja abrir la misma webcam dos veces, así que se suelta la
      // anterior ANTES de pedir ninguna.
      if (flujo) flujo.getTracks().forEach(t => t.stop());
      flujo = null;
      quiero = null;
      for (const cam of orden) {
        try {
          flujo = await abrirCamara(cam);
          quiero = cam;
          break;
        } catch (e) {
          // Una fantasma da NotReadableError o NotFoundError y no pasa nada: se
          // sigue con la siguiente. Esto es lo que separa la webcam de verdad de
          // las tres entradas muertas que Windows arrastra.
          console.warn('Descarto "' + (cam.label || cam.deviceId) + '":', e.name);
        }
      }
      if (!flujo) throw new Error('ninguna de las ' + orden.length
        + ' cámaras de la lista se deja abrir');
    }

    // Se quería la USB y ha acabado abriendo la del portátil: en una sala eso
    // significa que la obra mira a la pared, así que se dice bien claro.
    if (esIntegrada(quiero) && !/^(integrada|\d+)$/.test((CFG.CAMARA || '').trim().toLowerCase())) {
      console.warn('Acabé en la cámara integrada:', quiero.label);
      avisoCamara = 'No pude abrir la cámara USB: uso la integrada. ¿Está enchufada?';
    }
    avisoMicro = await comprobarMicro(quiero);

    const nombre = (flujo.getVideoTracks()[0].label || 'cámara').slice(0, 40);
    $panel.title = 'Cámara: ' + nombre + '  ·  cámbiala con ?cam=<nombre o índice>';
    console.info('Presencia usando:', nombre);

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
  // Sin fotograma previo: el primero de todos no debe contar como movimiento.
  _previo = null; tMov = 0;
  activo = true; anterior = 0;
  $ojo.classList.add('on');
  avisarGuion();
  // Después de avisarGuion(): los tres comparten rótulo, y lo de los aparatos es
  // lo que hay que arreglar antes de abrir la sala.
  const avisos = [avisoCamara, avisoMicro].filter(Boolean);
  if (avisos.length) invitar(avisos.join('  ·  '), 10000);
  requestAnimationFrame(analizar);
}

function apagar() {
  activo = false;
  if (estado === 'cerca') marcha();
  if (flujo) { flujo.getTracks().forEach(t => t.stop()); flujo = null; }
  $cam.srcObject = null;
  $panel.classList.remove('viendo');
  $ojo.classList.remove('on');
  tCerca = tLejos = tMov = 0;
  _previo = null;
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
