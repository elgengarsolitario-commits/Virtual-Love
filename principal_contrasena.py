from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import timedelta
import os
import re
import json
import random
import urllib.request
import urllib.parse
import psycopg2

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_ultra_segura'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

DATABASE_URL = os.environ.get('DATABASE_URL')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_UPLOAD_PRESET = os.environ.get('CLOUDINARY_UPLOAD_PRESET', '')
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# === CONFIGURACIÓN DE LA BASE DE DATOS ===
def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS espacios (
        codigo TEXT PRIMARY KEY
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        genero TEXT NOT NULL,
        PRIMARY KEY (espacio, slot)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS notas (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        genero TEXT NOT NULL,
        contenido TEXT NOT NULL,
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS fotos (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        genero TEXT NOT NULL,
        url TEXT NOT NULL,
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS cartas (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        autor_slot INTEGER NOT NULL,
        autor_nombre TEXT NOT NULL,
        autor_genero TEXT NOT NULL,
        plantilla TEXT NOT NULL,
        etiquetas TEXT NOT NULL,
        respondida BOOLEAN DEFAULT FALSE,
        contenido_final TEXT,
        completado_por TEXT,
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS recuerdos (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        genero TEXT NOT NULL,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        fecha DATE,
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS playlist (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        genero TEXT NOT NULL,
        youtube_id TEXT NOT NULL,
        titulo TEXT,
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS planes (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        genero TEXT NOT NULL,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        imagen_url TEXT,
        estado TEXT DEFAULT 'pendiente',
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ultima_actividad TIMESTAMP DEFAULT NOW()''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS trivia_juegos (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        autor_slot INTEGER NOT NULL,
        preguntas TEXT NOT NULL,
        adivinador_slot INTEGER,
        respuestas_adivinador TEXT,
        puntaje INTEGER,
        estado TEXT DEFAULT 'esperando_adivinanza',
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ahorcado_juegos (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        autor_slot INTEGER NOT NULL,
        palabra TEXT NOT NULL,
        pista TEXT,
        letras_probadas TEXT DEFAULT '',
        vidas INTEGER DEFAULT 6,
        estado TEXT DEFAULT 'jugando',
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS penales_marcador (
        espacio TEXT NOT NULL,
        slot INTEGER NOT NULL,
        goles INTEGER DEFAULT 0,
        tiros INTEGER DEFAULT 0,
        PRIMARY KEY (espacio, slot)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS notificaciones (
        id SERIAL PRIMARY KEY,
        espacio TEXT NOT NULL,
        para_slot INTEGER NOT NULL,
        de_nombre TEXT,
        tipo TEXT NOT NULL,
        mensaje TEXT NOT NULL,
        emoji TEXT DEFAULT '💗',
        url TEXT DEFAULT '/espacio',
        leida BOOLEAN DEFAULT FALSE,
        creado_en TIMESTAMP DEFAULT NOW()
    )''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()


# === MENSAJES ALEATORIOS DE LA MASCOTA ===
MENSAJES_IDLE = [
    "¿Ya le dijiste algo bonito hoy? 🐻💗", "Recuerda tomar agua 💧", "¡Estoy aquí acompañándote! 🐾",
    "Un mensajito nunca sobra ✨", "¿Y si dejas una notita sorpresa? 📝", "Hoy es un buen día para sonreír 🌸",
    "Psst... revisa la playlist, hay canciones nuevas 🎵", "¿Ya vieron sus planes juntos? 🎯",
]

MENSAJES_EVENTOS = {
    'nota': ["¡Qué bonito mensaje dejaste! 💌", "Awww, se van a poner feliz con esto 🥰", "Eso sí que alegra el día 🌸"],
    'foto': ["¡Qué recuerdo tan lindo! 📸", "Esa foto quedó preciosa 💕", "Un momento más guardado para siempre 🖼️"],
    'carta': ["¡Carta enviada! Qué sorpresa se van a llevar 💌", "Esto va a ser divertido de completar ✨"],
    'carta_completada': ["¡Sorpresa revelada! 🎉", "Jaja, qué carta tan graciosa quedó 😂", "Esto hay que guardarlo para siempre 💗"],
    'recuerdo': ["Un recuerdo más en su historia 📅", "Qué bonito momento para no olvidar 🕰️"],
    'cancion': ["¡Buena elección de canción! 🎶", "Esa se va a quedar sonando en la cabeza 🎧"],
    'plan': ["¡Qué ganas de que cumplan ese plan! 🎯", "Se ve divertido, ojalá lo hagan pronto ✨"],
    'plan_cumplido': ["¡Lo lograron! 🎉🎉", "Un plan más cumplido juntos 💗"],
}


def mensaje_evento(clave):
    opciones = MENSAJES_EVENTOS.get(clave)
    if not opciones:
        return None
    return random.choice(opciones)


# === HELPERS DE IDENTIDAD ===
def obtener_usuarios(codigo):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT slot, nombre, genero FROM usuarios WHERE espacio = %s', (codigo,))
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return {slot: {'nombre': nombre, 'genero': genero} for slot, nombre, genero in filas}


def mi_identidad():
    if 'espacio_activo' not in session or 'mi_slot' not in session:
        return None
    codigo = session['espacio_activo']
    slot = session['mi_slot']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT nombre, genero FROM usuarios WHERE espacio = %s AND slot = %s', (codigo, slot))
    fila = cursor.fetchone()
    cursor.close()
    conn.close()
    if fila:
        return {'slot': slot, 'nombre': fila[0], 'genero': fila[1]}
    return None


def requiere_espacio_e_identidad():
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))
    if 'mi_slot' not in session:
        return redirect(url_for('quien_eres'))
    return None


SEGUNDOS_EN_LINEA = 45


def marcar_actividad(codigo, slot):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE usuarios SET ultima_actividad = NOW() WHERE espacio = %s AND slot = %s', (codigo, slot))
    conn.commit()
    cursor.close()
    conn.close()


def estado_en_linea(codigo):
    """Devuelve {slot: True/False} según actividad reciente de cada usuario."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT slot, (NOW() - ultima_actividad) < INTERVAL '%s seconds' FROM usuarios WHERE espacio = %%s" % SEGUNDOS_EN_LINEA,
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return {slot: en_linea for slot, en_linea in filas}


def ambos_en_linea(codigo):
    estados = estado_en_linea(codigo)
    return len(estados) == 2 and all(estados.values())


def otro_slot(slot):
    return 2 if slot == 1 else 1


def crear_notificacion(codigo, para_slot, de_nombre, tipo, mensaje, emoji='💗', url='/espacio'):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO notificaciones (espacio, para_slot, de_nombre, tipo, mensaje, emoji, url) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (codigo, para_slot, de_nombre, tipo, mensaje, emoji, url)
    )
    conn.commit()
    cursor.close()
    conn.close()


def extraer_youtube_id(url):
    patrones = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([A-Za-z0-9_-]{11})'
    ]
    for p in patrones:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def obtener_titulo_youtube(video_id):
    try:
        url = 'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=' + video_id + '&format=json'
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get('title', 'Canción')
    except Exception:
        return 'Canción'


def buscar_youtube(query):
    """Busca videos en YouTube usando YouTube Data API v3 (requiere YOUTUBE_API_KEY)."""
    if not YOUTUBE_API_KEY:
        return []
    try:
        params = urllib.parse.urlencode({
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': 8,
            'key': YOUTUBE_API_KEY
        })
        url = 'https://www.googleapis.com/youtube/v3/search?' + params
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read().decode())
        resultados = []
        for item in data.get('items', []):
            vid = item.get('id', {}).get('videoId')
            snippet = item.get('snippet', {})
            if vid:
                resultados.append({
                    'id': vid,
                    'titulo': snippet.get('title', 'Canción'),
                    'canal': snippet.get('channelTitle', ''),
                    'thumb': snippet.get('thumbnails', {}).get('medium', {}).get('url', '')
                })
        return resultados
    except Exception:
        return []


# === MASCOTA FLOTANTE (aparece en todas las pantallas) ===
MASCOTA_HTML = '''
<div id="mascota-flotante" style="position:fixed; z-index:9999; cursor:grab; user-select:none; touch-action:none; font-size:46px; line-height:1; filter: drop-shadow(0 6px 10px rgba(0,0,0,0.25));">
    <div style="position:relative;">
        <div id="mascota-burbuja" style="position:absolute; bottom:110%; right:0; min-width:140px; max-width:220px; background:#fff; border-radius:16px; border:2px solid #fbcfe8; padding:10px 12px; font-size:13px; font-family:'Segoe UI', system-ui, sans-serif; color:#db2777; font-weight:600; box-shadow:0 8px 20px rgba(0,0,0,0.15); display:none; opacity:0; transition:opacity 0.35s ease; text-align:left; line-height:1.3;"></div>

        <div id="mascota-menu" style="position:absolute; bottom:110%; right:0; width:230px; background:#fff; border-radius:20px; border:2px solid #fbcfe8; padding:14px; box-shadow:0 14px 30px rgba(0,0,0,0.2); display:none; font-family:'Segoe UI', system-ui, sans-serif; text-align:left;">
            <p style="font-size:11px; color:#9ca3af; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; margin:0 0 8px 2px;">Mandar cariño</p>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:8px;">
                <button type="button" class="mascota-opcion" data-tipo="besito" style="background:#fdf2f8; border:1px solid #fbcfe8; border-radius:12px; padding:8px 4px; font-size:12px; color:#db2777; font-weight:600; cursor:pointer;">💋 Besito</button>
                <button type="button" class="mascota-opcion" data-tipo="abrazo" style="background:#fdf2f8; border:1px solid #fbcfe8; border-radius:12px; padding:8px 4px; font-size:12px; color:#db2777; font-weight:600; cursor:pointer;">🤗 Abrazo</button>
                <button type="button" class="mascota-opcion" data-tipo="cariño" style="background:#fdf2f8; border:1px solid #fbcfe8; border-radius:12px; padding:8px 4px; font-size:12px; color:#db2777; font-weight:600; cursor:pointer;">🥰 Cariño</button>
                <button type="button" class="mascota-opcion" data-tipo="te_extraño" style="background:#fdf2f8; border:1px solid #fbcfe8; border-radius:12px; padding:8px 4px; font-size:12px; color:#db2777; font-weight:600; cursor:pointer;">🥺 Te extraño</button>
                <button type="button" class="mascota-opcion" data-tipo="te_amo" style="background:#fdf2f8; border:1px solid #fbcfe8; border-radius:12px; padding:8px 4px; font-size:12px; color:#db2777; font-weight:600; cursor:pointer; grid-column: span 2;">❤️ Te amo</button>
            </div>
            <p style="font-size:11px; color:#9ca3af; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; margin:0 0 6px 2px;">O elige un emoji</p>
            <div id="mascota-emojis" style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px; font-size:20px;">
                <span class="mascota-emoji-opcion" style="cursor:pointer;">😘</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">🥳</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">😍</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">🌹</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">✨</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">🐻</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">😂</span>
                <span class="mascota-emoji-opcion" style="cursor:pointer;">🍫</span>
            </div>
            <div style="border-top:1px solid #f3f4f6; padding-top:8px;">
                <p id="mascota-notif-titulo" style="font-size:11px; color:#9ca3af; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; margin:0 0 6px 2px;">Notificaciones</p>
                <div id="mascota-notif-lista" style="max-height:140px; overflow-y:auto; display:flex; flex-direction:column; gap:4px;">
                    <p style="font-size:11px; color:#d1d5db; margin:0;">Sin novedades por ahora</p>
                </div>
            </div>
        </div>

        <span id="mascota-emoji" style="position:relative; display:inline-block;">🐻<span id="mascota-badge" style="position:absolute; top:-6px; left:-6px; background:#ef4444; color:#fff; font-size:11px; font-weight:700; min-width:18px; height:18px; border-radius:9999px; display:none; align-items:center; justify-content:center; padding:0 4px; font-family:'Segoe UI', system-ui, sans-serif; box-shadow:0 2px 6px rgba(0,0,0,0.25);">0</span></span>
        <span id="mascota-cerrar" style="position:absolute; top:-8px; right:-10px; background:#fff; border-radius:9999px; width:20px; height:20px; font-size:12px; display:none; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(0,0,0,0.25); cursor:pointer; color:#999;">✕</span>
    </div>
</div>
<div id="mascota-tab" style="position:fixed; bottom:16px; right:16px; z-index:9999; background:#fff; border-radius:9999px; width:36px; height:36px; display:none; align-items:center; justify-content:center; box-shadow:0 4px 10px rgba(0,0,0,0.2); cursor:pointer; font-size:18px;">🐾</div>
<script>
(function(){
    var mascota = document.getElementById('mascota-flotante');
    var cerrar = document.getElementById('mascota-cerrar');
    var tab = document.getElementById('mascota-tab');
    var burbuja = document.getElementById('mascota-burbuja');
    var menu = document.getElementById('mascota-menu');
    var emojiSpan = document.getElementById('mascota-emoji');
    var badge = document.getElementById('mascota-badge');
    var notifLista = document.getElementById('mascota-notif-lista');
    var oculta = localStorage.getItem('mascotaOculta');

    if (oculta === '1') {
        mascota.style.display = 'none';
        tab.style.display = 'flex';
    } else {
        var savedPos = localStorage.getItem('mascotaPos');
        if (savedPos) {
            try {
                var pos = JSON.parse(savedPos);
                mascota.style.left = pos.left + 'px';
                mascota.style.top = pos.top + 'px';
            } catch(e) {
                mascota.style.right = '20px';
                mascota.style.bottom = '20px';
            }
        } else {
            mascota.style.right = '20px';
            mascota.style.bottom = '20px';
        }
    }

    mascota.addEventListener('mouseenter', function(){ cerrar.style.display = 'flex'; });
    mascota.addEventListener('mouseleave', function(){ cerrar.style.display = 'none'; });

    cerrar.addEventListener('click', function(e){
        e.stopPropagation();
        mascota.style.display = 'none';
        tab.style.display = 'flex';
        localStorage.setItem('mascotaOculta', '1');
    });

    tab.addEventListener('click', function(){
        tab.style.display = 'none';
        mascota.style.display = 'block';
        localStorage.setItem('mascotaOculta', '0');
    });

    var dragging = false, offsetX = 0, offsetY = 0, movio = false;

    function startDrag(x, y) {
        dragging = true;
        movio = false;
        var rect = mascota.getBoundingClientRect();
        offsetX = x - rect.left;
        offsetY = y - rect.top;
        mascota.style.cursor = 'grabbing';
        mascota.style.right = 'auto';
        mascota.style.bottom = 'auto';
    }
    function moveDrag(x, y) {
        if (!dragging) return;
        movio = true;
        var left = x - offsetX;
        var top = y - offsetY;
        left = Math.max(0, Math.min(window.innerWidth - mascota.offsetWidth, left));
        top = Math.max(0, Math.min(window.innerHeight - mascota.offsetHeight, top));
        mascota.style.left = left + 'px';
        mascota.style.top = top + 'px';
    }
    function endDrag() {
        if (!dragging) return;
        dragging = false;
        mascota.style.cursor = 'grab';
        var rect = mascota.getBoundingClientRect();
        localStorage.setItem('mascotaPos', JSON.stringify({left: rect.left, top: rect.top}));
    }

    mascota.addEventListener('mousedown', function(e){ if (e.target === emojiSpan) startDrag(e.clientX, e.clientY); });
    window.addEventListener('mousemove', function(e){ moveDrag(e.clientX, e.clientY); });
    window.addEventListener('mouseup', endDrag);

    mascota.addEventListener('touchstart', function(e){ if (e.target === emojiSpan) { var t = e.touches[0]; startDrag(t.clientX, t.clientY); } }, {passive:true});
    window.addEventListener('touchmove', function(e){ moveDrag(e.touches[0].clientX, e.touches[0].clientY); }, {passive:true});
    window.addEventListener('touchend', endDrag);

    // === Menú de opciones (clic sin arrastrar abre el menú) ===
    emojiSpan.addEventListener('click', function(e){
        e.stopPropagation();
        if (movio) { movio = false; return; }
        var abierto = menu.style.display === 'block';
        menu.style.display = abierto ? 'none' : 'block';
        burbuja.style.display = 'none';
        if (!abierto) { cargarNotificaciones(true); }
    });
    document.addEventListener('click', function(e){
        if (menu.style.display === 'block' && !menu.contains(e.target) && e.target !== emojiSpan) {
            menu.style.display = 'none';
        }
    });

    document.querySelectorAll('.mascota-opcion').forEach(function(btn){
        btn.addEventListener('click', function(e){
            e.stopPropagation();
            enviarMimo(btn.getAttribute('data-tipo'), null);
            menu.style.display = 'none';
            mostrarBurbuja('¡Enviado! 💗', 2500);
        });
    });
    document.querySelectorAll('.mascota-emoji-opcion').forEach(function(span){
        span.addEventListener('click', function(e){
            e.stopPropagation();
            enviarMimo('emoji', span.textContent);
            menu.style.display = 'none';
            mostrarBurbuja('¡Enviado! ' + span.textContent, 2500);
        });
    });

    function enviarMimo(tipo, emoji) {
        var body = new URLSearchParams();
        body.append('tipo', tipo);
        if (emoji) body.append('emoji', emoji);
        fetch('/mimo/enviar', {method: 'POST', body: body}).catch(function(){});
    }

    // === Burbuja de mensajes ===
    var MENSAJES_IDLE = ["¿Ya le dijiste algo bonito hoy? 🐻💗", "Recuerda tomar agua 💧", "¡Estoy aquí acompañándote! 🐾", "Un mensajito nunca sobra ✨", "¿Y si dejas una notita sorpresa? 📝", "Hoy es un buen día para sonreír 🌸", "Psst... revisa la playlist, hay canciones nuevas 🎵", "¿Ya vieron sus planes juntos? 🎯", "Tócame para mandar cariño 💗"];
    var mostrandoBurbuja = false;

    function mostrarBurbuja(texto, duracionMs) {
        if (mascota.style.display === 'none') return;
        burbuja.textContent = texto;
        burbuja.style.display = 'block';
        requestAnimationFrame(function(){ burbuja.style.opacity = '1'; });
        mostrandoBurbuja = true;
        setTimeout(function(){
            burbuja.style.opacity = '0';
            setTimeout(function(){ burbuja.style.display = 'none'; mostrandoBurbuja = false; }, 350);
        }, duracionMs || 4500);
    }

    var mensajeEvento = window.__mascotaMensajeEvento;
    if (mensajeEvento) {
        setTimeout(function(){ mostrarBurbuja(mensajeEvento, 5500); }, 500);
    }

    function ciclarIdle() {
        var espera = 45000 + Math.random() * 45000;
        setTimeout(function(){
            if (!mostrandoBurbuja && menu.style.display !== 'block') {
                var msg = MENSAJES_IDLE[Math.floor(Math.random() * MENSAJES_IDLE.length)];
                mostrarBurbuja(msg, 4500);
            }
            ciclarIdle();
        }, espera);
    }
    ciclarIdle();

    // === Notificaciones ===
    var ultimasNoLeidas = 0;

    function cargarNotificaciones(marcarLeidas) {
        fetch('/notificaciones/listar')
            .then(function(res){ return res.json(); })
            .then(function(data){
                if (data.no_leidas > ultimasNoLeidas && !marcarLeidas) {
                    var nuevo = data.items[0];
                    if (nuevo) { mostrarBurbuja((nuevo.de_nombre ? nuevo.de_nombre + ': ' : '') + nuevo.mensaje.replace(/^.*?te /, 'Te ') + ' ' + nuevo.emoji, 6000); }
                }
                ultimasNoLeidas = data.no_leidas;
                if (data.no_leidas > 0) {
                    badge.style.display = 'flex';
                    badge.textContent = data.no_leidas > 9 ? '9+' : data.no_leidas;
                } else {
                    badge.style.display = 'none';
                }
                notifLista.innerHTML = '';
                if (!data.items || data.items.length === 0) {
                    notifLista.innerHTML = '<p style="font-size:11px;color:#d1d5db;margin:0;">Sin novedades por ahora</p>';
                } else {
                    data.items.forEach(function(it){
                        var div = document.createElement('a');
                        div.href = it.url;
                        div.style.cssText = 'display:block; text-decoration:none; font-size:11px; color:#374151; background:' + (it.leida ? '#fafafa' : '#fdf2f8') + '; border-radius:10px; padding:6px 8px; line-height:1.3;';
                        div.innerHTML = '<span style="margin-right:4px;">' + it.emoji + '</span>' + it.mensaje + '<br><span style="color:#d1d5db; font-size:10px;">' + it.fecha + '</span>';
                        notifLista.appendChild(div);
                    });
                }
                if (marcarLeidas && data.no_leidas > 0) {
                    fetch('/notificaciones/marcar-leidas', {method: 'POST'}).then(function(){
                        badge.style.display = 'none';
                        ultimasNoLeidas = 0;
                    }).catch(function(){});
                }
            })
            .catch(function(){});
    }
    cargarNotificaciones(false);
    setInterval(function(){ cargarNotificaciones(false); }, 15000);

    // === Ping de presencia (para saber si ambos están en línea) ===
    function ping() {
        fetch('/presencia/ping', {method: 'POST'}).catch(function(){});
    }
    ping();
    setInterval(ping, 20000);
})();
</script>
'''


def con_mascota(html_renderizado, mensaje_evento=None):
    mascota = MASCOTA_HTML
    if mensaje_evento:
        mensaje_js = json.dumps(mensaje_evento)
        mascota = mascota.replace(
            '<script>\n(function(){',
            '<script>\nwindow.__mascotaMensajeEvento = ' + mensaje_js + ';\n(function(){'
        )
    return html_renderizado.replace('</body>', mascota + '</body>')


# === PRESENCIA (para saber si ambos están conectados) ===
@app.route('/presencia/ping', methods=['POST'])
def presencia_ping():
    if 'espacio_activo' in session and 'mi_slot' in session:
        marcar_actividad(session['espacio_activo'], session['mi_slot'])
    return ('', 204)


MIMOS_TEXTO = {
    'besito': ('te mandó un besito', '💋'),
    'abrazo': ('te mandó un abrazo', '🤗'),
    'cariño': ('te mandó cariño', '🥰'),
    'te_extraño': ('te dice que te extraña', '🥺'),
    'te_amo': ('te dice que te ama', '❤️'),
}


@app.route('/mimo/enviar', methods=['POST'])
def enviar_mimo():
    if 'espacio_activo' not in session or 'mi_slot' not in session:
        return json.dumps({'ok': False}), 401, {'Content-Type': 'application/json'}

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    if not identidad:
        return json.dumps({'ok': False}), 401, {'Content-Type': 'application/json'}

    tipo = request.form.get('tipo', '').strip()
    emoji_personalizado = request.form.get('emoji', '').strip()

    if tipo == 'emoji' and emoji_personalizado:
        texto = identidad['nombre'] + ' te mandó ' + emoji_personalizado
        emoji = emoji_personalizado
    elif tipo in MIMOS_TEXTO:
        frase, emoji = MIMOS_TEXTO[tipo]
        texto = identidad['nombre'] + ' ' + frase
    else:
        return json.dumps({'ok': False}), 400, {'Content-Type': 'application/json'}

    crear_notificacion(codigo, otro_slot(identidad['slot']), identidad['nombre'], 'mimo', texto, emoji=emoji, url='/espacio')
    return json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}


@app.route('/notificaciones/listar')
def listar_notificaciones():
    if 'espacio_activo' not in session or 'mi_slot' not in session:
        return json.dumps({'no_leidas': 0, 'items': []}), 200, {'Content-Type': 'application/json'}

    codigo = session['espacio_activo']
    slot = session['mi_slot']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, de_nombre, tipo, mensaje, emoji, url, leida, creado_en FROM notificaciones '
        'WHERE espacio = %s AND para_slot = %s ORDER BY creado_en DESC LIMIT 15',
        (codigo, slot)
    )
    filas = cursor.fetchall()
    cursor.execute(
        'SELECT COUNT(*) FROM notificaciones WHERE espacio = %s AND para_slot = %s AND leida = FALSE',
        (codigo, slot)
    )
    no_leidas = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    items = [{
        'id': i, 'de_nombre': n, 'tipo': t, 'mensaje': m, 'emoji': e, 'url': u, 'leida': l,
        'fecha': f.strftime('%d/%m %H:%M') if f else ''
    } for i, n, t, m, e, u, l, f in filas]

    return json.dumps({'no_leidas': no_leidas, 'items': items}), 200, {'Content-Type': 'application/json'}


@app.route('/notificaciones/marcar-leidas', methods=['POST'])
def marcar_notificaciones_leidas():
    if 'espacio_activo' not in session or 'mi_slot' not in session:
        return ('', 204)
    codigo = session['espacio_activo']
    slot = session['mi_slot']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notificaciones SET leida = TRUE WHERE espacio = %s AND para_slot = %s AND leida = FALSE',
        (codigo, slot)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return ('', 204)


# === RUTA PRINCIPAL (EL PANEL DE BIENVENIDA) ===
@app.route('/', methods=['GET', 'POST'])
def home():
    if 'espacio_activo' in session:
        return redirect(url_for('espacio_virtual'))

    mensaje_error = None
    mensaje_exito = None

    if request.method == 'POST':
        accion = request.form.get('accion')
        codigo = request.form.get('codigo', '').strip().lower()

        if not codigo:
            mensaje_error = "¡Por favor, escribe un código!"
        else:
            conn = get_conn()
            cursor = conn.cursor()

            if accion == 'crear':
                try:
                    cursor.execute('INSERT INTO espacios (codigo) VALUES (%s)', (codigo,))
                    conn.commit()
                    mensaje_exito = '¡Espacio "' + codigo + '" creado con éxito! Ahora puedes entrar.'
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    mensaje_error = "Ese código de espacio ya existe. ¡Prueba con otro!"

            elif accion == 'entrar':
                cursor.execute('SELECT codigo FROM espacios WHERE codigo = %s', (codigo,))
                resultado = cursor.fetchone()
                if resultado:
                    session.permanent = True
                    session['espacio_activo'] = codigo
                    cursor.close()
                    conn.close()
                    return redirect(url_for('espacio_virtual'))
                else:
                    mensaje_error = "Ese espacio no existe. ¿Escribiste bien el código?"

            cursor.close()
            conn.close()

    html_bienvenida = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Nuestro Rincón Secreto</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex items-center justify-center font-sans p-4">
        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-md w-full border border-pink-100 text-center">

            <h1 class="text-3xl font-bold text-pink-500 mb-2">🌸 ¡Bienvenido! 🌸</h1>
            <p class="text-gray-500 text-sm mb-6">Crea tu rincón privado o entra al que ya tienes con tu personita especial.</p>

            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}
            {% if exito %}
                <div class="bg-green-50 text-green-600 p-3 rounded-xl text-sm mb-4 border border-green-100">{{ exito }}</div>
            {% endif %}

            <form method="POST" class="space-y-6">
                <div>
                    <label class="block text-gray-600 text-xs font-semibold uppercase tracking-wider mb-2">Ingresa tu código único</label>
                    <input type="text" name="codigo" placeholder="ej: nuestrocodigo"
                           class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none text-center text-lg text-pink-600 font-medium placeholder-gray-300 transition-all">
                </div>

                <div class="flex flex-col gap-3">
                    <button type="submit" name="accion" value="entrar"
                            class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                        Entrar al Espacio Virtual ✨
                    </button>

                    <div class="flex items-center my-2">
                        <div class="flex-grow border-t border-gray-200"></div>
                        <span class="mx-3 text-xs text-gray-400">¿No tienes uno?</span>
                        <div class="flex-grow border-t border-gray-200"></div>
                    </div>

                    <button type="submit" name="accion" value="crear"
                            class="w-full bg-white hover:bg-pink-50 text-pink-500 font-semibold py-3 px-6 rounded-2xl border-2 border-pink-200 transition-all flex items-center justify-center gap-2 active:scale-[0.98]">
                        <span>Crear nuevo espacio</span>
                        <span class="text-xl font-bold">+</span>
                    </button>
                </div>
            </form>
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_bienvenida, error=mensaje_error, exito=mensaje_exito))


# === EL ESPACIO VIRTUAL ADENTRO (hub con las 8 ventanas) ===
@app.route('/espacio')
def espacio_virtual():
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))
    if 'mi_slot' not in session:
        return redirect(url_for('quien_eres'))

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT nombre, genero, contenido, creado_en FROM notas WHERE espacio = %s ORDER BY creado_en DESC',
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    notas = []
    for nombre, genero, contenido, creado_en in filas:
        notas.append({
            'nombre': nombre,
            'genero': genero,
            'contenido': contenido,
            'rotacion': round(random.uniform(-12, 12), 1),
            'top': round(random.uniform(2, 88), 1),
            'left': round(random.uniform(1, 84), 1)
        })

    html_espacio = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Espacio: {{ codigo_sala }}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { font-family: 'Segoe UI', system-ui, sans-serif; }
            .ventana {
                position: relative; overflow: hidden;
                transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.35s ease;
            }
            .ventana:hover { transform: translateY(-6px) scale(1.06); box-shadow: 0 20px 40px -12px rgba(236, 72, 153, 0.35); z-index: 10; }
            .ventana-icono { transition: transform 0.35s ease; }
            .ventana:hover .ventana-icono { transform: scale(1.15) rotate(-4deg); }
            .ventana-detalle { max-height: 0; opacity: 0; transition: max-height 0.35s ease, opacity 0.3s ease, margin-top 0.35s ease; }
            .ventana:hover .ventana-detalle { max-height: 100px; opacity: 1; margin-top: 0.5rem; }
            .ventana::before {
                content: ""; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
                background: radial-gradient(circle, rgba(244, 114, 182, 0.12) 0%, transparent 60%);
                opacity: 0; transition: opacity 0.35s ease; pointer-events: none;
            }
            .ventana:hover::before { opacity: 1; }
            .fondo-notas { position: fixed; inset: 0; overflow: hidden; z-index: 0; pointer-events: none; }
            .nota-fondo { position: absolute; width: 170px; padding: 14px; border-radius: 16px; opacity: 0.9; box-shadow: 0 8px 20px -8px rgba(0,0,0,0.15); }
            .contenido-principal { position: relative; z-index: 10; }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-12 px-4">

        <div class="fondo-notas">
            {% for n in notas %}
            <div class="nota-fondo
                {% if n.genero == 'hombre' %} bg-blue-100
                {% elif n.genero == 'mujer' %} bg-pink-100
                {% else %} bg-gray-100 {% endif %}
            " style="top: {{ n.top }}%; left: {{ n.left }}%; transform: rotate({{ n.rotacion }}deg);">
                <p class="text-[10px] font-bold uppercase text-gray-500 mb-1">{{ n.nombre }}</p>
                <p class="text-xs text-gray-600">{{ n.contenido }}</p>
            </div>
            {% endfor %}
        </div>

        <div class="contenido-principal w-full flex flex-col items-center">

        <div class="w-full max-w-5xl flex justify-end mb-4">
            <a href="/salir"
               class="text-xs text-gray-400 hover:text-red-400 hover:bg-red-50 border border-transparent hover:border-red-100 px-3 py-2 rounded-xl transition-all flex items-center gap-1">
                <span>Cerrar sesión</span><span>🔒</span>
            </a>
        </div>

        <div class="text-center mb-10">
            <h1 class="text-3xl font-bold text-pink-600">💖 Espacio Privado: {{ codigo_sala }} 💖</h1>
            <p class="text-gray-500 mt-2">Elige una ventana para entrar</p>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-5xl w-full">

            <a href="/notas" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">📝</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Notitas</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Deja mensajitos cortos para que tu personita los lea cuando entre.</p>
            </a>

            <a href="/fotos" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">📸</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Fotos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Guarden juntos las fotos que más les gustan de su historia.</p>
            </a>

            <a href="/cartas" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">💌</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Cartas</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Un juego de completar frases, sorpresa incluida.</p>
            </a>

            <a href="/recuerdos" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">📅</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Recuerdos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Una línea de tiempo con los momentos más importantes juntos.</p>
            </a>

            <a href="/playlist" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">🎵</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Playlist</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Las canciones que les recuerdan a ustedes dos.</p>
            </a>

            <a href="/planes" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">🎯</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Planes juntos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Cosas que quieren hacer, ver o visitar juntos algún día.</p>
            </a>

            <a href="/juegos" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">🎮</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Juegos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Mini juegos para hacer juntos cuando ambos estén conectados.</p>
            </a>

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">💞</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Sobre nosotros</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Datos, aniversarios y cositas curiosas de su relación.</p>
            </a>

        </div>

        {% if not notas %}
        <div class="w-full max-w-5xl mt-8 text-center">
            <p class="text-sm text-gray-400">Todavía no hay notitas por aquí… ¡anímate a dejar la primera! 💭</p>
        </div>
        {% endif %}

        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_espacio, codigo_sala=codigo, notas=notas),
                        mensaje_evento=mensaje_evento(request.args.get('evento')))


# === ¿QUIÉN ERES? ===
@app.route('/quien-eres', methods=['GET', 'POST'])
def quien_eres():
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))

    codigo = session['espacio_activo']
    mensaje_error = None

    if request.method == 'POST':
        slot = int(request.form.get('slot', 0))
        accion = request.form.get('accion')

        if accion == 'soy_yo':
            session['mi_slot'] = slot
            return redirect(url_for('espacio_virtual'))

        elif accion == 'crear' and slot in (1, 2):
            nombre = request.form.get('nombre', '').strip()
            genero = request.form.get('genero', 'nd')
            if not nombre:
                mensaje_error = "Escribe un nombre antes de continuar."
            else:
                ocupados_actual = obtener_usuarios(codigo)
                nombre_duplicado = any(
                    datos['nombre'].strip().lower() == nombre.lower()
                    for s_existente, datos in ocupados_actual.items() if s_existente != slot
                )
                if nombre_duplicado:
                    mensaje_error = ('Ya hay alguien registrado en este espacio con el nombre "' + nombre + '". '
                                      'Si esa persona eres tú, usa el botón "Soy ' + nombre + '" más abajo para identificarte. '
                                      'Si eres otra persona, usa un nombre distinto (por ejemplo, agrega tu apellido o una inicial).')
                else:
                    conn = get_conn()
                    cursor = conn.cursor()
                    try:
                        cursor.execute(
                            'INSERT INTO usuarios (espacio, slot, nombre, genero) VALUES (%s, %s, %s, %s)',
                            (codigo, slot, nombre, genero)
                        )
                        conn.commit()
                        session['mi_slot'] = slot
                        cursor.close()
                        conn.close()
                        return redirect(url_for('espacio_virtual'))
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        mensaje_error = "Ese bloque ya fue tomado por otra persona. Elige el otro."
                    cursor.close()
                    conn.close()

        elif accion == 'liberar' and slot in (1, 2):
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM usuarios WHERE espacio = %s AND slot = %s', (codigo, slot))
            conn.commit()
            cursor.close()
            conn.close()
            if session.get('mi_slot') == slot:
                session.pop('mi_slot', None)

    ocupados = obtener_usuarios(codigo)
    slot_libre = None
    for s in (1, 2):
        if s not in ocupados:
            slot_libre = s
            break

    html_quien_eres = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>¿Quién eres?</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex items-center justify-center font-sans p-4">
        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-md w-full border border-pink-100 text-center">
            <h1 class="text-2xl font-bold text-pink-600 mb-1">¿Quién eres tú? 💭</h1>
            <p class="text-gray-500 text-sm mb-6">Así sabremos quién escribe cada nota.</p>

            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}

            {% if slot_libre %}
                <form method="POST" class="space-y-4 text-left">
                    <input type="hidden" name="slot" value="{{ slot_libre }}">
                    <input type="hidden" name="accion" value="crear">
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">Tu nombre</label>
                        <input type="text" name="nombre" placeholder="Tu nombre" autofocus
                            class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none text-center text-lg text-pink-600 font-medium">
                    </div>
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">Tu género</label>
                        <select name="genero" class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none text-center">
                            <option value="hombre">Hombre 💙</option>
                            <option value="mujer">Mujer 💗</option>
                            <option value="nd">Prefiero no decir</option>
                        </select>
                    </div>
                    <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                        Guardar y continuar ✨
                    </button>
                </form>

                {% if ocupados %}
                    <div class="mt-6 pt-4 border-t border-gray-100 space-y-3">
                        <p class="text-xs text-gray-400 mb-1">¿Ya habías elegido tu nombre antes en otro dispositivo?</p>
                        {% for s, datos in ocupados.items() %}
                        <div>
                            <form method="POST">
                                <input type="hidden" name="slot" value="{{ s }}">
                                <input type="hidden" name="accion" value="soy_yo">
                                <button type="submit" class="w-full text-sm py-2 px-4 rounded-xl border-2 font-semibold transition-all
                                    {% if datos.genero == 'hombre' %} bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100
                                    {% elif datos.genero == 'mujer' %} bg-pink-50 border-pink-200 text-pink-600 hover:bg-pink-100
                                    {% else %} bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100 {% endif %}
                                ">Soy {{ datos.nombre }} <span class="opacity-60 font-normal">· lugar {{ s }}</span></button>
                            </form>
                            <form method="POST" onsubmit="return confirm('¿Seguro que quieres liberar el lugar {{ s }} ({{ datos.nombre }})? La persona tendrá que registrarse de nuevo.');" class="mt-1">
                                <input type="hidden" name="slot" value="{{ s }}">
                                <input type="hidden" name="accion" value="liberar">
                                <button type="submit" class="w-full text-[11px] text-gray-400 hover:text-red-400 underline">No soy yo, liberar este lugar</button>
                            </form>
                        </div>
                        {% endfor %}
                    </div>
                {% endif %}
            {% else %}
                <p class="text-sm text-gray-500 mb-4">Ya hay dos personas en este espacio. ¿Cuál de ellas eres?</p>
                <div class="space-y-4">
                    {% for s, datos in ocupados.items() %}
                    <div>
                        <form method="POST">
                            <input type="hidden" name="slot" value="{{ s }}">
                            <input type="hidden" name="accion" value="soy_yo">
                            <button type="submit" class="w-full py-3 px-4 rounded-2xl border-2 font-semibold transition-all
                                {% if datos.genero == 'hombre' %} bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100
                                {% elif datos.genero == 'mujer' %} bg-pink-50 border-pink-200 text-pink-600 hover:bg-pink-100
                                {% else %} bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100 {% endif %}
                            ">Soy {{ datos.nombre }} <span class="opacity-60 font-normal">· lugar {{ s }}</span></button>
                        </form>
                        <form method="POST" onsubmit="return confirm('¿Seguro que quieres liberar el lugar {{ s }} ({{ datos.nombre }})? La persona tendrá que registrarse de nuevo.');" class="mt-1">
                            <input type="hidden" name="slot" value="{{ s }}">
                            <input type="hidden" name="accion" value="liberar">
                            <button type="submit" class="w-full text-[11px] text-gray-400 hover:text-red-400 underline">No soy yo, liberar este lugar</button>
                        </form>
                    </div>
                    {% endfor %}
                </div>
            {% endif %}

            <a href="/salir" class="text-xs text-gray-400 hover:text-red-400 underline mt-8 inline-block">Cerrar sesión</a>
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_quien_eres, codigo_sala=codigo, ocupados=ocupados,
                                                slot_libre=slot_libre, error=mensaje_error))


# === PLANTILLAS COMPARTIDAS (nav y menú de 2 opciones) ===
NAV_HTML = '''
<div class="w-full max-w-3xl flex justify-between items-center mb-10 mx-auto">
    <a href="{{ volver_url }}" class="text-sm text-gray-400 hover:text-pink-500">&larr; {{ volver_texto }}</a>
    <a href="/salir" class="text-xs text-gray-400 hover:text-red-400 underline">Cerrar sesión</a>
</div>
'''


def pagina_menu(titulo, emoji_titulo, opciones, volver_url='/espacio', volver_texto='Volver al espacio'):
    filas = ''
    for op in opciones:
        filas += ('<a href="' + op['url'] + '" class="opcion bg-white rounded-3xl border border-pink-100 p-8 '
                   'shadow-md flex flex-col items-center text-center cursor-pointer">'
                   '<span class="text-4xl">' + op['emoji'] + '</span>'
                   '<h3 class="text-lg font-bold text-pink-600 mt-3">' + op['texto'] + '</h3></a>')

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>''' + titulo + '''</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .opcion { transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.3s ease; }
            .opcion:hover { transform: translateY(-6px) scale(1.04); box-shadow: 0 20px 40px -12px rgba(236,72,153,0.35); }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-12 px-4">
        <div class="w-full max-w-3xl flex justify-between items-center mb-10">
            <a href="''' + volver_url + '''" class="text-sm text-gray-400 hover:text-pink-500">&larr; ''' + volver_texto + '''</a>
            <a href="/salir" class="text-xs text-gray-400 hover:text-red-400 underline">Cerrar sesión</a>
        </div>
        <h1 class="text-3xl font-bold text-pink-600 mb-8">''' + emoji_titulo + ' ' + titulo + '''</h1>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-2xl w-full">
            ''' + filas + '''
        </div>
    </body>
    </html>
    '''
    return con_mascota(html)


# === NOTITAS ===
@app.route('/notas')
def notas_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Notitas', '📝', [
        {'url': '/notas/escribir', 'emoji': '✍️', 'texto': 'Escribir una nota'},
        {'url': '/notas/ver', 'emoji': '📬', 'texto': 'Ver notas enviadas'},
    ])


@app.route('/notas/escribir', methods=['GET', 'POST'])
def escribir_nota():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        if contenido:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO notas (espacio, slot, nombre, genero, contenido) VALUES (%s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], contenido)
            )
            conn.commit()
            cursor.close()
            conn.close()
            crear_notificacion(
                codigo, otro_slot(identidad['slot']), identidad['nombre'], 'nota',
                identidad['nombre'] + ' te dejó una notita nueva', emoji='📝', url='/notas/ver'
            )
            return redirect(url_for('espacio_virtual', evento='nota'))

    html_escribir_nota = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Escribir nota</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/notas" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <p class="text-xs text-gray-400 mb-1">Escribiendo como</p>
            <p class="font-bold mb-4
                {% if identidad.genero == 'hombre' %} text-blue-600
                {% elif identidad.genero == 'mujer' %} text-pink-600
                {% else %} text-gray-600 {% endif %}
            ">{{ identidad.nombre }}</p>
            <textarea name="contenido" rows="10" placeholder="Escribe algo lindo..."
                class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none resize-none text-gray-700" required></textarea>
            <button type="submit" class="mt-4 w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Enviar nota 💌
            </button>
        </form>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_escribir_nota, codigo_sala=codigo, identidad=identidad))


@app.route('/notas/ver')
def ver_notas():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT nombre, genero, contenido, creado_en FROM notas WHERE espacio = %s ORDER BY creado_en DESC', (codigo,))
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    notas = []
    for nombre, genero, contenido, creado_en in filas:
        notas.append({
            'nombre': nombre, 'genero': genero, 'contenido': contenido,
            'fecha': creado_en.strftime('%d/%m/%Y %H:%M') if creado_en else '',
            'rotacion': round(random.uniform(-5, 5), 1)
        })

    html_ver_notas = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Notas enviadas</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .nota { transition: transform 0.25s ease; }
            .nota:hover { transform: scale(1.05) rotate(0deg) !important; z-index: 10; }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen py-10 px-4">
        <div class="w-full max-w-5xl mx-auto flex justify-between items-center mb-8">
            <a href="/notas" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
            <a href="/notas/escribir" class="text-sm bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 px-4 rounded-xl transition-all">+ Nueva nota</a>
        </div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-10">📬 Notas enviadas</h1>
        {% if notas|length == 0 %}
            <p class="text-center text-gray-400 mt-16">Todavía no hay notas. ¡Sé el primero en escribir una! ✍️</p>
        {% else %}
        <div class="max-w-5xl mx-auto columns-1 sm:columns-2 md:columns-3 gap-6 space-y-6">
            {% for n in notas %}
            <div class="nota break-inside-avoid rounded-2xl shadow-md p-5 border-2
                {% if n.genero == 'hombre' %} bg-blue-50 border-blue-200
                {% elif n.genero == 'mujer' %} bg-pink-50 border-pink-200
                {% else %} bg-gray-50 border-gray-200 {% endif %}
            " style="transform: rotate({{ n.rotacion }}deg);">
                <p class="text-xs font-bold uppercase tracking-wide mb-2
                    {% if n.genero == 'hombre' %} text-blue-500
                    {% elif n.genero == 'mujer' %} text-pink-500
                    {% else %} text-gray-500 {% endif %}
                ">{{ n.nombre }}</p>
                <p class="text-gray-700 whitespace-pre-wrap">{{ n.contenido }}</p>
                <p class="text-[10px] text-gray-400 mt-3 text-right">{{ n.fecha }}</p>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_notas, codigo_sala=codigo, notas=notas))


# === FOTOS (con Cloudinary) ===
@app.route('/fotos')
def fotos_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Fotos', '📸', [
        {'url': '/fotos/subir', 'emoji': '⬆️', 'texto': 'Subir una foto'},
        {'url': '/fotos/ver', 'emoji': '🖼️', 'texto': 'Ver galería'},
    ])


@app.route('/fotos/subir', methods=['GET', 'POST'])
def subir_foto():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if url:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO fotos (espacio, slot, nombre, genero, url) VALUES (%s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], url)
            )
            conn.commit()
            cursor.close()
            conn.close()
            crear_notificacion(
                codigo, otro_slot(identidad['slot']), identidad['nombre'], 'foto',
                identidad['nombre'] + ' subió una foto nueva', emoji='📸', url='/fotos/ver'
            )
            return redirect(url_for('ver_fotos', evento='foto'))

    html_subir = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Subir foto</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/fotos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4 text-center">
            <p class="text-xs text-gray-400 mb-1">Subiendo como</p>
            <p class="font-bold mb-4
                {% if identidad.genero == 'hombre' %} text-blue-600
                {% elif identidad.genero == 'mujer' %} text-pink-600
                {% else %} text-gray-600 {% endif %}
            ">{{ identidad.nombre }}</p>

            {% if not cloud_name %}
                <div class="bg-yellow-50 text-yellow-700 text-sm p-4 rounded-xl border border-yellow-200 text-left">
                    Todavía no está configurado Cloudinary en este servidor. Se necesitan las variables de entorno
                    <b>CLOUDINARY_CLOUD_NAME</b> y <b>CLOUDINARY_UPLOAD_PRESET</b> en Render.
                </div>
            {% else %}
                <div class="flex gap-2 mb-4">
                    <label for="input-camara" class="flex-1 cursor-pointer bg-pink-50 hover:bg-pink-100 border-2 border-pink-200 text-pink-600 font-semibold text-sm py-3 rounded-2xl text-center transition-all">
                        📷 Tomar foto
                    </label>
                    <label for="input-galeria" class="flex-1 cursor-pointer bg-white hover:bg-pink-50 border-2 border-pink-100 text-pink-600 font-semibold text-sm py-3 rounded-2xl text-center transition-all">
                        🖼️ Elegir de galería
                    </label>
                </div>
                <input type="file" id="input-camara" accept="image/*" capture="environment" class="hidden">
                <input type="file" id="input-galeria" accept="image/*" class="hidden">
                <div id="preview-foto" class="mb-4"></div>
                <button id="btn-subir" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]" disabled style="opacity:0.5;">
                    Subir foto 💗
                </button>
                <p id="estado-subida" class="text-xs text-gray-400 mt-3"></p>

                <form id="form-guardar" method="POST" class="hidden">
                    <input type="hidden" name="url" id="input-url">
                </form>

                <script>                    var cloudName = "{{ cloud_name }}";
                    var uploadPreset = "{{ upload_preset }}";
                    var inputCamara = document.getElementById('input-camara');
                    var inputGaleria = document.getElementById('input-galeria');
                    var preview = document.getElementById('preview-foto');
                    var btn = document.getElementById('btn-subir');
                    var estado = document.getElementById('estado-subida');
                    var archivoElegido = null;

                    function archivoSeleccionado(file) {
                        archivoElegido = file;
                        preview.innerHTML = '';
                        if (file) {
                            var img = document.createElement('img');
                            img.src = URL.createObjectURL(file);
                            img.className = 'rounded-2xl max-h-56 mx-auto';
                            preview.appendChild(img);
                            btn.disabled = false;
                            btn.style.opacity = '1';
                        }
                    }

                    inputCamara.addEventListener('change', function() { archivoSeleccionado(inputCamara.files[0]); });
                    inputGaleria.addEventListener('change', function() { archivoSeleccionado(inputGaleria.files[0]); });

                    btn.addEventListener('click', function() {
                        var file = archivoElegido;
                        if (!file) { estado.textContent = 'Elige una foto primero.'; return; }
                        estado.textContent = 'Subiendo...';
                        btn.disabled = true;

                        var formData = new FormData();
                        formData.append('file', file);
                        formData.append('upload_preset', uploadPreset);

                        fetch('https://api.cloudinary.com/v1_1/' + cloudName + '/image/upload', {
                            method: 'POST',
                            body: formData
                        })
                        .then(function(res) { return res.json(); })
                        .then(function(data) {
                            if (data.secure_url) {
                                document.getElementById('input-url').value = data.secure_url;
                                document.getElementById('form-guardar').submit();
                            } else {
                                estado.textContent = 'Ocurrió un error al subir la foto.';
                                btn.disabled = false;
                            }
                        })
                        .catch(function() {
                            estado.textContent = 'Ocurrió un error al subir la foto.';
                            btn.disabled = false;
                        });
                    });
                </script>
            {% endif %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_subir, identidad=identidad,
                                                cloud_name=CLOUDINARY_CLOUD_NAME,
                                                upload_preset=CLOUDINARY_UPLOAD_PRESET))


@app.route('/fotos/ver')
def ver_fotos():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT nombre, genero, url, creado_en FROM fotos WHERE espacio = %s ORDER BY creado_en DESC', (codigo,))
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    fotos = [{'nombre': n, 'genero': g, 'url': u, 'fecha': f.strftime('%d/%m/%Y') if f else ''} for n, g, u, f in filas]

    html_ver_fotos = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Galería</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .foto-card { transition: transform 0.25s ease, box-shadow 0.25s ease; }
            .foto-card:hover { transform: scale(1.03); box-shadow: 0 14px 28px -10px rgba(236,72,153,0.35); }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen py-10 px-4">
        <div class="w-full max-w-5xl mx-auto flex justify-between items-center mb-8">
            <a href="/fotos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
            <a href="/fotos/subir" class="text-sm bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 px-4 rounded-xl transition-all">+ Subir foto</a>
        </div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-10">🖼️ Galería</h1>
        {% if fotos|length == 0 %}
            <p class="text-center text-gray-400 mt-16">Todavía no hay fotos. ¡Sube la primera! 📸</p>
        {% else %}
        <div class="max-w-5xl mx-auto grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {% for f in fotos %}
            <div class="foto-card bg-white rounded-2xl border-2
                {% if f.genero == 'hombre' %} border-blue-200
                {% elif f.genero == 'mujer' %} border-pink-200
                {% else %} border-gray-200 {% endif %}
            overflow-hidden shadow-md">
                <img src="{{ f.url }}" class="w-full h-40 object-cover">
                <div class="p-2">
                    <p class="text-xs font-bold
                        {% if f.genero == 'hombre' %} text-blue-500
                        {% elif f.genero == 'mujer' %} text-pink-500
                        {% else %} text-gray-500 {% endif %}
                    ">{{ f.nombre }}</p>
                    <p class="text-[10px] text-gray-400">{{ f.fecha }}</p>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_fotos, fotos=fotos),
                        mensaje_evento=mensaje_evento(request.args.get('evento')))


# === CARTAS (juego de completar frases) ===
@app.route('/cartas')
def cartas_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Cartas', '💌', [
        {'url': '/cartas/crear', 'emoji': '✍️', 'texto': 'Crear una carta con espacios'},
        {'url': '/cartas/libre', 'emoji': '📜', 'texto': 'Escribir una carta libre'},
        {'url': '/cartas/ver', 'emoji': '📖', 'texto': 'Ver mis cartas'},
    ])


@app.route('/cartas/libre', methods=['GET', 'POST'])
def carta_libre():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    mensaje_error = None

    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        if not contenido:
            mensaje_error = "Escribe algo antes de enviar tu carta."
        else:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO cartas (espacio, autor_slot, autor_nombre, autor_genero, plantilla, etiquetas, '
                'respondida, contenido_final, completado_por) VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], contenido, '[]',
                 contenido, identidad['nombre'])
            )
            conn.commit()
            cursor.close()
            conn.close()
            crear_notificacion(
                codigo, otro_slot(identidad['slot']), identidad['nombre'], 'carta',
                identidad['nombre'] + ' te escribió una carta 💌', emoji='📜', url='/cartas/ver'
            )
            return redirect(url_for('ver_cartas', evento='carta'))

    html_libre = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Carta libre</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/cartas" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <h2 class="text-lg font-bold text-pink-600 mb-1">Escribe una carta libre 📜</h2>
            <p class="text-xs text-gray-500 mb-4">Sin juego de espacios, solo tú y tus palabras. Se enviará directo, sin sorpresas que completar.</p>

            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}

            <textarea name="contenido" rows="10" placeholder="Escribe todo lo que quieras decirle..."
                class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none resize-none text-gray-700" required></textarea>

            <button type="submit" class="mt-4 w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Enviar carta 💌
            </button>
        </form>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_libre, error=mensaje_error))


@app.route('/cartas/crear', methods=['GET', 'POST'])
def crear_carta():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    mensaje_error = None

    if request.method == 'POST':
        plantilla = request.form.get('plantilla', '').strip()
        numeros_usados = sorted(set(int(x) for x in re.findall(r'\{(\d+)\}', plantilla)))
        etiquetas = []
        for n in numeros_usados:
            et = request.form.get('etiqueta_' + str(n), '').strip()
            etiquetas.append(et if et else ('espacio ' + str(n)))

        if not plantilla or not numeros_usados:
            mensaje_error = "Escribe tu carta y usa {1}, {2}, {3}... donde quieras que tu pareja complete."
        else:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO cartas (espacio, autor_slot, autor_nombre, autor_genero, plantilla, etiquetas) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], plantilla, json.dumps(etiquetas))
            )
            conn.commit()
            cursor.close()
            conn.close()
            crear_notificacion(
                codigo, otro_slot(identidad['slot']), identidad['nombre'], 'carta',
                identidad['nombre'] + ' te dejó una carta para completar', emoji='💌', url='/cartas/ver'
            )
            return redirect(url_for('ver_cartas', evento='carta'))

    html_crear = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Crear carta</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-xl"><a href="/cartas" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>

        <div class="max-w-xl w-full mt-4 mb-2">
            <p class="text-xs text-gray-500 mb-2">💡 ¿No sabes qué escribir? Toca una idea para usarla:</p>
            <div class="flex flex-wrap gap-2" id="plantillas-sugeridas">
                <button type="button" data-plantilla="Hoy quiero decirte que {1} y que me haces sentir {2}. Si tuviera que describirte con una palabra sería {3}. Y si pudiera regalarte algo ahora mismo sería {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">💗 Clásica romántica</button>
                <button type="button" data-plantilla="Si furamos un dúo seríamos como {1} y {2}. Mi recuerdo favorito contigo es cuando {3}. Prometo que siempre {4}. Y cuando estamos juntos lo que más me hace reír es {5}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">😂 Divertida</button>
                <button type="button" data-plantilla="Lo que más admiro de ti es {1}. Cuando estamos juntos me siento {2}. Nuestro próximo plan debería ser {3}. Y en cinco años me imagino que estaremos {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">✨ Reflexiva</button>
                <button type="button" data-plantilla="Quiero confesarte que {1}. Algo que nunca te había dicho es {2}. Y algo que quiero hacer contigo pronto es {3}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">🤫 Confesión</button>
                <button type="button" data-plantilla="Si tuviéramos que ir a una isla desierta llevaría {1}. Lo más loco que haría por ti es {2}. Mi apodo secreto para ti sería {3}. Y si fuéramos superhéroes, tu poder sería {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">🏝️ Isla desierta</button>
                <button type="button" data-plantilla="Nuestra canción debería ser {1}. Si fuéramos personajes de película seríamos {2}. Lo que más extraño cuando no estás es {3}. Y algo que quiero que sepas es {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">🎬 Cine y música</button>
                <button type="button" data-plantilla="Hoy me desperté pensando en {1}. Si pudiéramos viajar a cualquier lugar del mundo iría a {2}. Algo que quiero mejorar de mí para ti es {3}. Gracias por {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">🌅 Buenos días</button>
                <button type="button" data-plantilla="Nuestra primera vez juntos haciendo {1} fue inolvidable porque {2}. Lo que más valoro de nuestra relación es {3}. Y quiero que juntos logremos {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">📖 Nuestra historia</button>
                <button type="button" data-plantilla="Si fueras un postre serías {1} porque {2}. Lo más tierno que has hecho por mí es {3}. Y algo random que amo de ti es {4}." class="sugerencia text-xs bg-white border border-pink-200 text-pink-600 px-3 py-2 rounded-xl hover:bg-pink-100 transition-all">🍰 Random y tierna</button>
            </div>
        </div>

        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-2">
            <h2 class="text-lg font-bold text-pink-600 mb-2">Crea tu carta con espacios ✍️</h2>
            <p class="text-xs text-gray-500 mb-4">
                Escribe tu carta y usa <b>{1}</b>, <b>{2}</b>, <b>{3}</b>... donde quieras que tu pareja complete,
                por ejemplo: "Hoy quiero decirte que {1} y que me haces sentir {2}."
            </p>

            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}

            <textarea id="plantilla-textarea" name="plantilla" rows="6" placeholder="Escribe tu carta usando {1}, {2}, {3}..."
                class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none resize-none text-gray-700 mb-4" required></textarea>

            <p class="text-xs text-gray-500 mb-2">Describe qué tipo de palabra va en cada espacio (opcional, ej: "un adjetivo"):</p>
            <div class="space-y-2 mb-4">
                {% for i in range(1, 6) %}
                <input type="text" name="etiqueta_{{ i }}" placeholder="Pista para el espacio {{ i }} (opcional)"
                    class="w-full px-3 py-2 rounded-xl border-2 border-gray-100 focus:border-pink-300 focus:outline-none text-sm">
                {% endfor %}
            </div>

            <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Enviar carta 💌
            </button>
        </form>

        <script>
            document.querySelectorAll('.sugerencia').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    document.getElementById('plantilla-textarea').value = btn.getAttribute('data-plantilla');
                });
            });
        </script>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_crear, error=mensaje_error))


@app.route('/cartas/completar/<int:carta_id>', methods=['GET', 'POST'])
def completar_carta(carta_id):
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT autor_slot, plantilla, etiquetas, respondida FROM cartas WHERE id = %s AND espacio = %s',
        (carta_id, codigo)
    )
    fila = cursor.fetchone()

    if not fila or fila[0] == identidad['slot'] or fila[3]:
        cursor.close()
        conn.close()
        return redirect(url_for('ver_cartas'))

    plantilla = fila[1]
    etiquetas = json.loads(fila[2])

    if request.method == 'POST':
        contenido_final = plantilla
        for i, et in enumerate(etiquetas, start=1):
            respuesta = request.form.get('respuesta_' + str(i), '').strip() or '___'
            contenido_final = contenido_final.replace('{' + str(i) + '}', respuesta)

        cursor.execute(
            'UPDATE cartas SET respondida = TRUE, contenido_final = %s, completado_por = %s WHERE id = %s',
            (contenido_final, identidad['nombre'], carta_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        crear_notificacion(
            codigo, fila[0], identidad['nombre'], 'carta_completada',
            identidad['nombre'] + ' completó tu carta, ¡ve la sorpresa!', emoji='✨', url='/cartas/ver'
        )
        return redirect(url_for('ver_cartas', revelada=carta_id, evento='carta_completada'))

    cursor.close()
    conn.close()

    html_completar = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Completar carta</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @keyframes flotar { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
            .emoji-flotante { animation: flotar 2.5s ease-in-out infinite; }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/cartas/ver" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <p class="emoji-flotante text-4xl text-center mb-2">💌</p>
            <h2 class="text-lg font-bold text-pink-600 mb-1 text-center">¡Te dejaron una carta!</h2>
            <p class="text-xs text-gray-500 mb-6 text-center">Completa cada espacio sin ver el resto. ¡Es sorpresa! Puedes usar palabras o emojis.</p>
            {% for et in etiquetas %}
            {% set n = loop.index %}
            <div class="mb-4">
                <label class="block text-xs text-gray-500 mb-1">Espacio {{ n }}: {{ et }}</label>
                <input type="text" name="respuesta_{{ n }}" id="campo-{{ n }}" required
                    class="w-full px-4 py-2 rounded-xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none mb-1">
                <div class="flex flex-wrap gap-1">
                    {% for e in ['😍','😂','🥰','😘','🔥','💗','🤩','😭','🍫','🌹','✨','😏'] %}
                    <span class="emoji-pick text-lg cursor-pointer hover:scale-125 transition-transform" data-campo="campo-{{ n }}" data-emoji="{{ e }}">{{ e }}</span>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
            <button type="submit" class="mt-3 w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Revelar carta ✨
            </button>
        </form>
        <script>
            document.querySelectorAll('.emoji-pick').forEach(function(el){
                el.addEventListener('click', function(){
                    var campo = document.getElementById(el.getAttribute('data-campo'));
                    campo.value = (campo.value + ' ' + el.getAttribute('data-emoji')).trim();
                    campo.focus();
                });
            });
        </script>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_completar, etiquetas=etiquetas))


@app.route('/cartas/ver')
def ver_cartas():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    revelada = request.args.get('revelada', type=int)

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, autor_slot, autor_nombre, autor_genero, respondida, contenido_final, completado_por, creado_en '
        'FROM cartas WHERE espacio = %s ORDER BY creado_en DESC', (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    cartas = []
    for cid, autor_slot, autor_nombre, autor_genero, respondida, contenido_final, completado_por, creado_en in filas:
        cartas.append({
            'id': cid, 'autor_slot': autor_slot, 'autor_nombre': autor_nombre, 'autor_genero': autor_genero,
            'respondida': respondida, 'contenido_final': contenido_final, 'completado_por': completado_por,
            'es_mia': autor_slot == identidad['slot'],
            'es_libre': completado_por == autor_nombre,
            'fecha': creado_en.strftime('%d/%m/%Y %H:%M') if creado_en else ''
        })

    html_ver_cartas = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mis cartas</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @keyframes cartaPop {
                0% { transform: scale(0.85); opacity: 0; }
                60% { transform: scale(1.03); opacity: 1; }
                100% { transform: scale(1); }
            }
            .carta-revelada { animation: cartaPop 0.5s cubic-bezier(0.34,1.56,0.64,1); }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen py-10 px-4">
        <div class="w-full max-w-3xl mx-auto flex justify-between items-center mb-8">
            <a href="/cartas" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
            <a href="/cartas/crear" class="text-sm bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 px-4 rounded-xl transition-all">+ Nueva carta</a>
        </div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-10">💌 Cartas</h1>

        {% if cartas|length == 0 %}
            <p class="text-center text-gray-400 mt-16">Todavía no hay cartas. ¡Crea la primera! ✍️</p>
        {% endif %}

        <div class="max-w-3xl mx-auto space-y-4">
            {% for c in cartas %}
            <div class="bg-white rounded-2xl border-2 p-5 shadow-md {% if c.id == revelada %} carta-revelada {% endif %}
                {% if c.autor_genero == 'hombre' %} border-blue-200
                {% elif c.autor_genero == 'mujer' %} border-pink-200
                {% else %} border-gray-200 {% endif %}
            ">
                {% if c.respondida %}
                    {% if c.es_libre %}
                        <p class="text-xs font-bold uppercase text-gray-400 mb-2">📜 Carta directa de {{ c.autor_nombre }}</p>
                    {% else %}
                        <p class="text-xs font-bold uppercase text-gray-400 mb-2">De {{ c.autor_nombre }} · completada por {{ c.completado_por }}</p>
                    {% endif %}
                    <p class="text-gray-700 whitespace-pre-wrap">{{ c.contenido_final }}</p>
                    {% if c.id == revelada %}<p class="text-xs text-pink-400 mt-2">✨ ¡Sorpresa revelada! ✨</p>{% endif %}
                {% elif c.es_mia %}
                    <p class="text-xs font-bold uppercase text-gray-400 mb-2">Tu carta</p>
                    <p class="text-sm text-gray-500">Esperando a que la completen... 💭</p>
                {% else %}
                    <p class="text-xs font-bold uppercase text-gray-400 mb-2">De {{ c.autor_nombre }}</p>
                    <p class="text-sm text-gray-500 mb-3">Te dejaron una carta para completar.</p>
                    <a href="/cartas/completar/{{ c.id }}" class="inline-block bg-pink-500 hover:bg-pink-600 text-white text-sm font-semibold py-2 px-4 rounded-xl transition-all">
                        Completar carta ✨
                    </a>
                {% endif %}
                <p class="text-[10px] text-gray-400 mt-3 text-right">{{ c.fecha }}</p>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_cartas, cartas=cartas, revelada=revelada),
                        mensaje_evento=mensaje_evento(request.args.get('evento')))


# === RECUERDOS (línea de tiempo) ===
@app.route('/recuerdos')
def recuerdos_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Recuerdos', '📅', [
        {'url': '/recuerdos/agregar', 'emoji': '➕', 'texto': 'Agregar un recuerdo'},
        {'url': '/recuerdos/ver', 'emoji': '🕰️', 'texto': 'Ver línea de tiempo'},
    ])


@app.route('/recuerdos/agregar', methods=['GET', 'POST'])
def agregar_recuerdo():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        fecha = request.form.get('fecha') or None
        if titulo:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO recuerdos (espacio, slot, nombre, genero, titulo, descripcion, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], titulo, descripcion, fecha)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('ver_recuerdos', evento='recuerdo'))

    html_agregar = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agregar recuerdo</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/recuerdos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4 space-y-4">
            <h2 class="text-lg font-bold text-pink-600">Agregar un recuerdo 📅</h2>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Título</label>
                <input type="text" name="titulo" required placeholder="Ej: Nuestra primera cita"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Fecha</label>
                <input type="date" name="fecha"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Descripción</label>
                <textarea name="descripcion" rows="4"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none resize-none"></textarea>
            </div>
            <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Guardar recuerdo 💗
            </button>
        </form>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_agregar))


@app.route('/recuerdos/ver')
def ver_recuerdos():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT nombre, genero, titulo, descripcion, fecha FROM recuerdos WHERE espacio = %s ORDER BY fecha DESC NULLS LAST, creado_en DESC',
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    recuerdos = []
    for nombre, genero, titulo, descripcion, fecha in filas:
        recuerdos.append({
            'nombre': nombre, 'genero': genero, 'titulo': titulo, 'descripcion': descripcion,
            'fecha': fecha.strftime('%d/%m/%Y') if fecha else 'Sin fecha'
        })

    html_ver_recuerdos = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Línea de tiempo</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen py-10 px-4">
        <div class="w-full max-w-2xl mx-auto flex justify-between items-center mb-8">
            <a href="/recuerdos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
            <a href="/recuerdos/agregar" class="text-sm bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 px-4 rounded-xl transition-all">+ Agregar</a>
        </div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-10">🕰️ Línea de tiempo</h1>

        {% if recuerdos|length == 0 %}
            <p class="text-center text-gray-400 mt-16">Todavía no hay recuerdos guardados. ¡Agreguen el primero! 📅</p>
        {% endif %}

        <div class="max-w-2xl mx-auto relative border-l-2 border-pink-200 pl-6 space-y-6">
            {% for r in recuerdos %}
            <div class="relative">
                <div class="absolute -left-[31px] top-1 w-3 h-3 rounded-full
                    {% if r.genero == 'hombre' %} bg-blue-400
                    {% elif r.genero == 'mujer' %} bg-pink-400
                    {% else %} bg-gray-400 {% endif %}
                "></div>
                <div class="bg-white rounded-2xl border border-pink-100 p-4 shadow-md">
                    <p class="text-xs font-bold text-gray-400">{{ r.fecha }} · {{ r.nombre }}</p>
                    <p class="font-bold text-pink-600 mt-1">{{ r.titulo }}</p>
                    {% if r.descripcion %}<p class="text-sm text-gray-600 mt-1">{{ r.descripcion }}</p>{% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_recuerdos, recuerdos=recuerdos),
                        mensaje_evento=mensaje_evento(request.args.get('evento')))


# === PLAYLIST (YouTube) ===
@app.route('/playlist')
def playlist_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Playlist', '🎵', [
        {'url': '/playlist/agregar', 'emoji': '➕', 'texto': 'Agregar una canción'},
        {'url': '/playlist/ver', 'emoji': '🎧', 'texto': 'Ver playlist'},
    ])


@app.route('/playlist/buscar')
def buscar_playlist():
    """Endpoint AJAX para buscar canciones en YouTube."""
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    query = request.args.get('q', '').strip()
    if not query:
        return json.dumps({'ok': False, 'resultados': [], 'sin_api_key': not bool(YOUTUBE_API_KEY)}), 200, {'Content-Type': 'application/json'}
    resultados = buscar_youtube(query)
    return json.dumps({'ok': True, 'resultados': resultados, 'sin_api_key': not bool(YOUTUBE_API_KEY)}), 200, {'Content-Type': 'application/json'}


@app.route('/playlist/agregar', methods=['GET', 'POST'])
def agregar_cancion():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    mensaje_error = None

    if request.method == 'POST':
        video_id = request.form.get('video_id', '').strip()
        titulo_directo = request.form.get('titulo_directo', '').strip()
        url = request.form.get('url', '').strip()

        if not video_id and url:
            video_id = extraer_youtube_id(url)

        if not video_id:
            mensaje_error = "No pude reconocer esa canción. Búscala en la biblioteca o pega un link válido de YouTube."
        else:
            titulo = titulo_directo or obtener_titulo_youtube(video_id)
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO playlist (espacio, slot, nombre, genero, youtube_id, titulo) VALUES (%s, %s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], video_id, titulo)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('ver_playlist', evento='cancion'))

    html_agregar = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agregar canción</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/playlist" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>

        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <h2 class="text-lg font-bold text-pink-600 mb-4">Agregar una canción 🎵</h2>
            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}

            {% if not tiene_api_key %}
                <div class="bg-yellow-50 text-yellow-700 text-xs p-3 rounded-xl border border-yellow-200 mb-4">
                    La búsqueda con biblioteca de YouTube no está activa (falta la variable <b>YOUTUBE_API_KEY</b> en el servidor).
                    Por ahora puedes pegar el link directamente. 👇
                </div>
            {% else %}
                <label class="block text-xs text-gray-500 mb-1">Buscar en YouTube</label>
                <input type="text" id="buscador" placeholder="Escribe el nombre de la canción..."
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none mb-2">
                <div id="resultados" class="space-y-2 max-h-80 overflow-y-auto mb-4"></div>
                <div class="flex items-center my-3">
                    <div class="flex-grow border-t border-gray-200"></div>
                    <span class="mx-3 text-xs text-gray-400">o pega un link</span>
                    <div class="flex-grow border-t border-gray-200"></div>
                </div>
            {% endif %}

            <form method="POST" id="form-link">
                <input type="text" name="url" placeholder="Pega el link de YouTube"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none mb-4">
                <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                    Agregar a la playlist 🎧
                </button>
            </form>

            <form method="POST" id="form-elegido" class="hidden">
                <input type="hidden" name="video_id" id="input-video-id">
                <input type="hidden" name="titulo_directo" id="input-titulo-directo">
            </form>
        </div>

        {% if tiene_api_key %}
        <script>
            var buscador = document.getElementById('buscador');
            var resultadosDiv = document.getElementById('resultados');
            var timeoutId = null;

            buscador.addEventListener('input', function() {
                clearTimeout(timeoutId);
                var q = buscador.value.trim();
                if (!q) { resultadosDiv.innerHTML = ''; return; }
                timeoutId = setTimeout(function() {
                    resultadosDiv.innerHTML = '<p class="text-xs text-gray-400">Buscando...</p>';
                    fetch('/playlist/buscar?q=' + encodeURIComponent(q))
                        .then(function(res) { return res.json(); })
                        .then(function(data) {
                            resultadosDiv.innerHTML = '';
                            if (!data.resultados || data.resultados.length === 0) {
                                resultadosDiv.innerHTML = '<p class="text-xs text-gray-400">Sin resultados.</p>';
                                return;
                            }
                            data.resultados.forEach(function(r) {
                                var item = document.createElement('div');
                                item.className = 'flex items-center gap-3 p-2 rounded-xl border border-pink-100 hover:bg-pink-50 cursor-pointer';
                                item.innerHTML = '<img src="' + r.thumb + '" class="w-16 h-12 object-cover rounded-lg">' +
                                    '<div class="flex-1"><p class="text-xs font-semibold text-gray-700 line-clamp-2">' + r.titulo + '</p>' +
                                    '<p class="text-[10px] text-gray-400">' + r.canal + '</p></div>';
                                item.addEventListener('click', function() {
                                    document.getElementById('input-video-id').value = r.id;
                                    document.getElementById('input-titulo-directo').value = r.titulo;
                                    document.getElementById('form-elegido').submit();
                                });
                                resultadosDiv.appendChild(item);
                            });
                        })
                        .catch(function() {
                            resultadosDiv.innerHTML = '<p class="text-xs text-red-400">Error al buscar.</p>';
                        });
                }, 400);
            });
        </script>
        {% endif %}
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_agregar, error=mensaje_error, tiene_api_key=bool(YOUTUBE_API_KEY)))


@app.route('/playlist/ver')
def ver_playlist():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT nombre, genero, youtube_id, titulo, creado_en FROM playlist WHERE espacio = %s ORDER BY creado_en DESC',
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    canciones = [{'nombre': n, 'genero': g, 'youtube_id': yid, 'titulo': t,
                  'fecha': f.strftime('%d/%m/%Y') if f else ''} for n, g, yid, t, f in filas]

    html_ver_playlist = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Playlist</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen py-10 px-4">
        <div class="w-full max-w-3xl mx-auto flex justify-between items-center mb-8">
            <a href="/playlist" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
            <a href="/playlist/agregar" class="text-sm bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 px-4 rounded-xl transition-all">+ Agregar</a>
        </div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-10">🎧 Nuestra Playlist</h1>

        {% if canciones|length == 0 %}
            <p class="text-center text-gray-400 mt-16">Todavía no hay canciones. ¡Agreguen la primera! 🎵</p>
        {% endif %}

        <div class="max-w-3xl mx-auto grid grid-cols-1 sm:grid-cols-2 gap-6">
            {% for c in canciones %}
            <div class="bg-white rounded-2xl border-2 overflow-hidden shadow-md
                {% if c.genero == 'hombre' %} border-blue-200
                {% elif c.genero == 'mujer' %} border-pink-200
                {% else %} border-gray-200 {% endif %}
            ">
                <div style="aspect-ratio: 16/9;">
                    <iframe class="w-full h-full" src="https://www.youtube.com/embed/{{ c.youtube_id }}" frameborder="0" allowfullscreen></iframe>
                </div>
                <div class="p-3">
                    <p class="font-bold text-gray-700 text-sm">{{ c.titulo }}</p>
                    <p class="text-xs text-gray-400 mt-1">Agregada por {{ c.nombre }} · {{ c.fecha }}</p>
                </div>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_playlist, canciones=canciones),
                        mensaje_evento=mensaje_evento(request.args.get('evento')))


# === PLANES JUNTOS ===
PLANES_SUGERIDOS = [
    {'titulo': 'Ir a la playa juntos', 'descripcion': 'Un día de sol, arena y buenas vibras.', 'emoji': '🏖️'},
    {'titulo': 'Maratón de películas', 'descripcion': 'Snacks, cobijas y sus pelis favoritas.', 'emoji': '🎬'},
    {'titulo': 'Cita de cocina', 'descripcion': 'Cocinar juntos una receta nueva.', 'emoji': '🍳'},
    {'titulo': 'Viaje de fin de semana', 'descripcion': 'Escaparse a un lugar nuevo, aunque sea cerca.', 'emoji': '🧳'},
    {'titulo': 'Noche de juegos de mesa', 'descripcion': 'Competir sanamente por el título de campeón/a.', 'emoji': '🎲'},
    {'titulo': 'Picnic al aire libre', 'descripcion': 'Una manta, comida rica y buena compañía.', 'emoji': '🧺'},
    {'titulo': 'Concierto o evento en vivo', 'descripcion': 'Ver a un artista que les guste a los dos.', 'emoji': '🎤'},
    {'titulo': 'Sesión de fotos juntos', 'descripcion': 'Capturar el momento para el recuerdo.', 'emoji': '📷'},
]


@app.route('/planes')
def planes_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Planes juntos', '🎯', [
        {'url': '/planes/agregar', 'emoji': '➕', 'texto': 'Agregar un plan'},
        {'url': '/planes/ver', 'emoji': '🗺️', 'texto': 'Ver tablero de planes'},
    ])


@app.route('/planes/agregar', methods=['GET', 'POST'])
def agregar_plan():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        imagen_url = request.form.get('imagen_url', '').strip() or None
        if titulo:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO planes (espacio, slot, nombre, genero, titulo, descripcion, imagen_url) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], titulo, descripcion, imagen_url)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('ver_planes', evento='plan'))

    html_agregar = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agregar plan</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-xl"><a href="/planes" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>

        <div class="max-w-xl w-full mt-4 mb-2">
            <p class="text-xs text-gray-500 mb-2">💡 Ideas rápidas, toca una para usarla:</p>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2" id="sugerencias-planes">
                {% for s in sugerencias %}
                <button type="button" data-titulo="{{ s.titulo }}" data-descripcion="{{ s.descripcion }}"
                    class="sugerencia-plan bg-white border border-pink-200 rounded-xl p-3 text-center hover:bg-pink-100 transition-all">
                    <span class="text-2xl block">{{ s.emoji }}</span>
                    <span class="text-[10px] text-pink-600 font-semibold">{{ s.titulo }}</span>
                </button>
                {% endfor %}
            </div>
        </div>

        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-2 space-y-4">
            <h2 class="text-lg font-bold text-pink-600">Agregar un plan 🎯</h2>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Título</label>
                <input id="input-titulo" type="text" name="titulo" required placeholder="Ej: Ir a la playa"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Descripción</label>
                <textarea id="input-descripcion" name="descripcion" rows="3"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none resize-none"></textarea>
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Link de una imagen (opcional)</label>
                <input type="text" name="imagen_url" placeholder="https://..."
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Guardar plan 💗
            </button>
        </form>

        <script>
            document.querySelectorAll('.sugerencia-plan').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    document.getElementById('input-titulo').value = btn.getAttribute('data-titulo');
                    document.getElementById('input-descripcion').value = btn.getAttribute('data-descripcion');
                });
            });
        </script>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_agregar, sugerencias=PLANES_SUGERIDOS))


@app.route('/planes/ver')
def ver_planes():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, nombre, genero, titulo, descripcion, imagen_url, estado, creado_en FROM planes WHERE espacio = %s ORDER BY creado_en DESC',
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    planes = []
    for pid, nombre, genero, titulo, descripcion, imagen_url, estado, creado_en in filas:
        planes.append({
            'id': pid, 'nombre': nombre, 'genero': genero, 'titulo': titulo,
            'descripcion': descripcion, 'imagen_url': imagen_url, 'estado': estado,
            'fecha': creado_en.strftime('%d/%m/%Y') if creado_en else ''
        })

    html_ver_planes = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Planes juntos</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .plan-card { transition: transform 0.25s ease, box-shadow 0.25s ease; }
            .plan-card:hover { transform: translateY(-4px); box-shadow: 0 16px 30px -12px rgba(236,72,153,0.3); }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen py-10 px-4">
        <div class="w-full max-w-5xl mx-auto flex justify-between items-center mb-8">
            <a href="/planes" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
            <a href="/planes/agregar" class="text-sm bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 px-4 rounded-xl transition-all">+ Agregar plan</a>
        </div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-10">🗺️ Planes juntos</h1>

        {% if planes|length == 0 %}
            <p class="text-center text-gray-400 mt-16">Todavía no hay planes. ¡Agreguen el primero! 🎯</p>
        {% endif %}

        <div class="max-w-5xl mx-auto grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-5">
            {% for p in planes %}
            <div class="plan-card bg-white rounded-2xl border-2 overflow-hidden shadow-md
                {% if p.genero == 'hombre' %} border-blue-200
                {% elif p.genero == 'mujer' %} border-pink-200
                {% else %} border-gray-200 {% endif %}
            ">
                {% if p.imagen_url %}
                    <img src="{{ p.imagen_url }}" class="w-full h-36 object-cover">
                {% else %}
                    <div class="w-full h-24 flex items-center justify-center text-3xl bg-pink-50">🎯</div>
                {% endif %}
                <div class="p-4">
                    <div class="flex items-center justify-between mb-1">
                        <p class="font-bold text-pink-600">{{ p.titulo }}</p>
                        {% if p.estado == 'cumplido' %}
                            <span class="text-[10px] bg-green-50 text-green-600 border border-green-200 px-2 py-1 rounded-full">Cumplido 🎉</span>
                        {% else %}
                            <span class="text-[10px] bg-yellow-50 text-yellow-600 border border-yellow-200 px-2 py-1 rounded-full">Pendiente</span>
                        {% endif %}
                    </div>
                    {% if p.descripcion %}<p class="text-sm text-gray-600 mb-2">{{ p.descripcion }}</p>{% endif %}
                    <p class="text-[10px] text-gray-400 mb-3">Agregado por {{ p.nombre }} · {{ p.fecha }}</p>
                    {% if p.estado != 'cumplido' %}
                    <form method="POST" action="/planes/marcar/{{ p.id }}">
                        <button type="submit" class="w-full text-xs bg-pink-500 hover:bg-pink-600 text-white font-semibold py-2 rounded-xl transition-all">
                            Marcar como cumplido ✓
                        </button>
                    </form>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_planes, planes=planes),
                        mensaje_evento=mensaje_evento(request.args.get('evento')))


@app.route('/planes/marcar/<int:plan_id>', methods=['POST'])
def marcar_plan(plan_id):
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE planes SET estado = 'cumplido' WHERE id = %s AND espacio = %s", (plan_id, codigo))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('ver_planes', evento='plan_cumplido'))


# === JUEGOS ===
PREGUNTAS_TRIVIA = [
    "Mi color favorito es...",
    "Mi comida favorita es...",
    "Si pudiera viajar a cualquier lugar del mundo iría a...",
    "Algo que me hace muy feliz es...",
    "Mi película o serie favorita es...",
]

VERDADES = [
    "¿Cuál fue tu primera impresión de mí?", "¿Cuál es tu recuerdo favorito de nosotros?",
    "¿Qué es lo que más te gusta de mí físicamente?", "¿Cuál ha sido el momento más vergonzoso que has vivido?",
    "¿Qué canción te recuerda a mí?", "¿Cuál es tu mayor sueño en la vida?",
    "¿Qué es lo que más admiras de nuestra relación?", "¿Cuál sería tu cita perfecta conmigo?",
    "¿Qué es algo que siempre quisiste decirme y no te habías animado?", "¿Cuál es tu miedo más grande?",
]
RETOS = [
    "Mándame un audio cantando algo random", "Escríbeme un piropo súper cursi ahora mismo",
    "Cuéntame un chiste malo", "Mándame la última foto de tu galería",
    "Dime tres cosas que amas de mí sin pensarlo", "Imita mi forma de hablar en un audio",
    "Mándame un emoji que resuma cómo te sientes ahora", "Cuéntame algo random que nadie más sepa de ti",
    "Escríbeme un mini poema de 4 líneas para mí", "Dime cuál sería nuestro nombre de pareja famosa",
]

DIRECCIONES_PENAL = ['izquierda', 'centro', 'derecha']


@app.route('/juegos')
def juegos_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    ocupados = obtener_usuarios(codigo)

    if len(ocupados) < 2 or not ambos_en_linea(codigo):
        html_esperando = '''
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Juegos</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <meta http-equiv="refresh" content="8">
        </head>
        <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4 text-center">
            <div class="w-full max-w-md mb-4"><a href="/espacio" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver al espacio</a></div>
            <div class="bg-white p-8 rounded-3xl shadow-xl max-w-md w-full border border-pink-100">
                <span class="text-5xl">🎮</span>
                <h1 class="text-xl font-bold text-pink-600 mt-4 mb-2">Esperando a que ambos estén en línea</h1>
                <p class="text-sm text-gray-500">Los juegos son para disfrutarlos juntos. Cuando los dos estén conectados al mismo tiempo, esta pantalla se actualizará sola. 💗</p>
            </div>
        </body>
        </html>
        '''
        return con_mascota(html_esperando)

    return pagina_menu('Juegos', '🎮', [
        {'url': '/juegos/verdad-o-reto', 'emoji': '🎡', 'texto': 'Verdad o Reto'},
        {'url': '/juegos/trivia', 'emoji': '💭', 'texto': '¿Qué tanto me conoces?'},
        {'url': '/juegos/ahorcado', 'emoji': '🔤', 'texto': 'Ahorcado en pareja'},
        {'url': '/juegos/penales', 'emoji': '⚽', 'texto': 'Penales'},
    ])


# --- Verdad o Reto ---
@app.route('/juegos/verdad-o-reto')
def verdad_o_reto():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verdad o Reto</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @keyframes girar { from { transform: rotate(0deg); } to { transform: rotate(1080deg); } }
            .girando { animation: girar 1.2s cubic-bezier(0.2,0.8,0.2,1); }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4 text-center">
        <div class="w-full max-w-md mb-4"><a href="/juegos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver a juegos</a></div>
        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-md w-full border border-pink-100">
            <span id="ruleta" class="text-6xl block mb-4">🎡</span>
            <div id="resultado" class="min-h-[90px] flex items-center justify-center text-lg font-semibold text-pink-600 px-2">
                Elige y gira la ruleta para empezar
            </div>
            <div class="flex gap-3 mt-4">
                <button onclick="jugar('verdad')" class="flex-1 bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 rounded-2xl transition-all active:scale-95">💭 Verdad</button>
                <button onclick="jugar('reto')" class="flex-1 bg-white border-2 border-pink-300 hover:bg-pink-50 text-pink-600 font-semibold py-3 rounded-2xl transition-all active:scale-95">🎯 Reto</button>
            </div>
        </div>
        <script>
            var VERDADES = ''' + json.dumps(VERDADES) + ''';
            var RETOS = ''' + json.dumps(RETOS) + ''';
            function jugar(tipo) {
                var ruleta = document.getElementById('ruleta');
                var resultado = document.getElementById('resultado');
                ruleta.classList.remove('girando');
                void ruleta.offsetWidth;
                ruleta.classList.add('girando');
                resultado.textContent = '...';
                setTimeout(function() {
                    var lista = tipo === 'verdad' ? VERDADES : RETOS;
                    var elegido = lista[Math.floor(Math.random() * lista.length)];
                    resultado.textContent = (tipo === 'verdad' ? '💭 ' : '🎯 ') + elegido;
                }, 900);
            }
        </script>
    </body>
    </html>
    '''
    return con_mascota(html)


# --- Trivia: ¿Qué tanto me conoces? ---
@app.route('/juegos/trivia', methods=['GET', 'POST'])
def trivia_juego():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    if request.method == 'POST':
        respuestas = [request.form.get('pregunta_' + str(i), '').strip() for i in range(len(PREGUNTAS_TRIVIA))]
        preguntas_payload = [{'pregunta': p, 'respuesta': r} for p, r in zip(PREGUNTAS_TRIVIA, respuestas)]
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO trivia_juegos (espacio, autor_slot, preguntas) VALUES (%s, %s, %s)',
            (codigo, identidad['slot'], json.dumps(preguntas_payload))
        )
        conn.commit()
        cursor.close()
        conn.close()
        crear_notificacion(
            codigo, otro_slot(identidad['slot']), identidad['nombre'], 'trivia',
            identidad['nombre'] + ' te retó a un trivia: ¿Qué tanto me conoces? 💭', emoji='💭', url='/juegos/trivia'
        )
        return redirect(url_for('trivia_juego'))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, autor_slot, preguntas, estado, puntaje FROM trivia_juegos WHERE espacio = %s ORDER BY creado_en DESC LIMIT 5',
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    pendiente_de_adivinar = None
    esperando_pareja = False
    resultados = []
    for tid, autor_slot, preguntas_json, estado, puntaje in filas:
        if estado == 'esperando_adivinanza' and autor_slot != identidad['slot']:
            pendiente_de_adivinar = {'id': tid, 'preguntas': json.loads(preguntas_json)}
        elif estado == 'esperando_adivinanza' and autor_slot == identidad['slot']:
            esperando_pareja = True
        elif estado == 'completado':
            resultados.append({'id': tid, 'puntaje': puntaje, 'total': len(json.loads(preguntas_json))})

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>¿Qué tanto me conoces?</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-lg mb-6"><a href="/juegos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver a juegos</a></div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-2">💭 ¿Qué tanto me conoces?</h1>
        <p class="text-xs text-gray-500 text-center mb-8 max-w-md">Responde sobre ti mismo/a y luego tu pareja intentará adivinar tus respuestas.</p>

        {% if pendiente %}
        <div class="bg-white p-6 rounded-3xl shadow-xl max-w-lg w-full border border-pink-100 mb-6">
            <p class="font-bold text-pink-600 mb-3">¡Tienes un trivia por adivinar! 🎯</p>
            <a href="/juegos/trivia/jugar/{{ pendiente.id }}" class="inline-block bg-pink-500 hover:bg-pink-600 text-white text-sm font-semibold py-2 px-4 rounded-xl transition-all">Adivinar ahora</a>
        </div>
        {% elif esperando %}
        <div class="bg-yellow-50 border border-yellow-200 text-yellow-700 text-sm p-4 rounded-2xl max-w-lg w-full mb-6">
            Ya creaste tu trivia, esperando a que tu pareja adivine tus respuestas... 💭
        </div>
        {% else %}
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-lg w-full border border-pink-100 mb-6">
            <p class="text-xs text-gray-500 mb-4">Responde estas preguntas sobre ti. ¡Tu pareja no verá las respuestas hasta que adivine!</p>
            {% for p in preguntas %}
            <div class="mb-3">
                <label class="block text-xs text-gray-500 mb-1">{{ p }}</label>
                <input type="text" name="pregunta_{{ loop.index0 }}" required class="w-full px-4 py-2 rounded-xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            {% endfor %}
            <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 rounded-2xl shadow-md transition-all active:scale-[0.98] mt-2">Enviar mis respuestas ✨</button>
        </form>
        {% endif %}

        {% if resultados %}
        <div class="max-w-lg w-full space-y-2">
            <p class="text-xs text-gray-400 uppercase font-bold mb-1">Resultados anteriores</p>
            {% for r in resultados %}
            <div class="bg-white rounded-xl border border-pink-100 p-3 text-sm text-gray-600 flex justify-between">
                <span>Trivia #{{ r.id }}</span>
                <span class="font-bold text-pink-600">{{ r.puntaje }} / {{ r.total }} ✅</span>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </body>
    </html>
    '''
    return con_mascota(render_template_string(
        html, preguntas=PREGUNTAS_TRIVIA, pendiente=pendiente_de_adivinar,
        esperando=esperando_pareja, resultados=resultados
    ))


@app.route('/juegos/trivia/jugar/<int:trivia_id>', methods=['GET', 'POST'])
def trivia_jugar(trivia_id):
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT autor_slot, preguntas, estado FROM trivia_juegos WHERE id = %s AND espacio = %s',
        (trivia_id, codigo)
    )
    fila = cursor.fetchone()

    if not fila or fila[0] == identidad['slot'] or fila[2] != 'esperando_adivinanza':
        cursor.close()
        conn.close()
        return redirect(url_for('trivia_juego'))

    autor_slot, preguntas_json, estado = fila
    preguntas = json.loads(preguntas_json)

    if request.method == 'POST':
        puntaje = 0
        respuestas_guess = []
        for i, p in enumerate(preguntas):
            guess = request.form.get('adivinanza_' + str(i), '').strip()
            respuestas_guess.append(guess)
            if guess.lower() == p['respuesta'].strip().lower():
                puntaje += 1

        cursor.execute(
            'UPDATE trivia_juegos SET adivinador_slot = %s, respuestas_adivinador = %s, puntaje = %s, estado = %s WHERE id = %s',
            (identidad['slot'], json.dumps(respuestas_guess), puntaje, 'completado', trivia_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        crear_notificacion(
            codigo, autor_slot, identidad['nombre'], 'trivia_resultado',
            identidad['nombre'] + ' terminó el trivia, ¡mira cuánto te conoce!', emoji='🎉', url='/juegos/trivia/resultado/' + str(trivia_id)
        )
        return redirect(url_for('trivia_resultado', trivia_id=trivia_id))

    cursor.close()
    conn.close()

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Adivina</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-lg mb-6"><a href="/juegos/trivia" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-lg w-full border border-pink-100">
            <h2 class="text-lg font-bold text-pink-600 mb-4">Adivina las respuestas de tu pareja 🎯</h2>
            {% for p in preguntas %}
            <div class="mb-3">
                <label class="block text-xs text-gray-500 mb-1">{{ p.pregunta }}</label>
                <input type="text" name="adivinanza_{{ loop.index0 }}" required class="w-full px-4 py-2 rounded-xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            {% endfor %}
            <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 rounded-2xl shadow-md transition-all active:scale-[0.98] mt-2">Revelar puntaje ✨</button>
        </form>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html, preguntas=preguntas))


@app.route('/juegos/trivia/resultado/<int:trivia_id>')
def trivia_resultado(trivia_id):
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT preguntas, respuestas_adivinador, puntaje FROM trivia_juegos WHERE id = %s AND espacio = %s',
        (trivia_id, codigo)
    )
    fila = cursor.fetchone()
    cursor.close()
    conn.close()

    if not fila:
        return redirect(url_for('trivia_juego'))

    preguntas = json.loads(fila[0])
    adivinanzas = json.loads(fila[1]) if fila[1] else []
    puntaje = fila[2]
    comparacion = []
    for i, p in enumerate(preguntas):
        guess = adivinanzas[i] if i < len(adivinanzas) else ''
        acerto = guess.strip().lower() == p['respuesta'].strip().lower()
        comparacion.append({'pregunta': p['pregunta'], 'real': p['respuesta'], 'guess': guess, 'acerto': acerto})

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Resultado</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-lg mb-6"><a href="/juegos/trivia" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <div class="text-center mb-6">
            <span class="text-5xl">🎉</span>
            <h1 class="text-2xl font-bold text-pink-600 mt-2">{{ puntaje }} / {{ comparacion|length }} respuestas correctas</h1>
        </div>
        <div class="max-w-lg w-full space-y-3">
            {% for c in comparacion %}
            <div class="bg-white rounded-2xl border-2 {% if c.acerto %} border-green-200 {% else %} border-red-100 {% endif %} p-4">
                <p class="text-xs text-gray-500 mb-1">{{ c.pregunta }}</p>
                <p class="text-sm"><b>Respuesta real:</b> {{ c.real }}</p>
                <p class="text-sm"><b>Adivinanza:</b> {{ c.guess }} {% if c.acerto %} ✅ {% else %} ❌ {% endif %}</p>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html, comparacion=comparacion, puntaje=puntaje))


# --- Ahorcado en pareja ---
@app.route('/juegos/ahorcado', methods=['GET', 'POST'])
def ahorcado_juego():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()

    if request.method == 'POST':
        palabra = request.form.get('palabra', '').strip().upper()
        pista = request.form.get('pista', '').strip()
        if palabra:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO ahorcado_juegos (espacio, autor_slot, palabra, pista) VALUES (%s, %s, %s, %s)',
                (codigo, identidad['slot'], palabra, pista)
            )
            conn.commit()
            cursor.close()
            conn.close()
            crear_notificacion(
                codigo, otro_slot(identidad['slot']), identidad['nombre'], 'ahorcado',
                identidad['nombre'] + ' te retó a adivinar una palabra secreta 🔤', emoji='🔤', url='/juegos/ahorcado'
            )
        return redirect(url_for('ahorcado_juego'))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, autor_slot, palabra, pista, letras_probadas, vidas, estado FROM ahorcado_juegos '
        'WHERE espacio = %s ORDER BY creado_en DESC LIMIT 1',
        (codigo,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conn.close()

    juego = None
    if fila:
        gid, autor_slot, palabra, pista, letras_probadas, vidas, estado = fila
        letras = letras_probadas.split(',') if letras_probadas else []
        mostrar = ' '.join([c if c in letras or c == ' ' else '_' for c in palabra])
        juego = {
            'id': gid, 'autor_slot': autor_slot, 'es_autor': autor_slot == identidad['slot'],
            'pista': pista, 'letras': letras, 'vidas': vidas, 'estado': estado,
            'mostrar': mostrar, 'palabra': palabra if estado != 'jugando' else None
        }

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ahorcado en pareja</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <meta http-equiv="refresh" content="12">
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-lg mb-6"><a href="/juegos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver a juegos</a></div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-6">🔤 Ahorcado en pareja</h1>

        {% if not juego or juego.estado != 'jugando' %}
            {% if juego and juego.estado != 'jugando' %}
            <div class="bg-white p-6 rounded-3xl shadow-xl max-w-lg w-full border border-pink-100 mb-6 text-center">
                {% if juego.estado == 'ganado' %}
                    <p class="text-2xl mb-2">🎉</p><p class="font-bold text-green-600">¡Adivinaron la palabra! Era "{{ juego.palabra }}"</p>
                {% else %}
                    <p class="text-2xl mb-2">😢</p><p class="font-bold text-red-500">Se acabaron las vidas. Era "{{ juego.palabra }}"</p>
                {% endif %}
            </div>
            {% endif %}
            <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-lg w-full border border-pink-100">
                <p class="text-xs text-gray-500 mb-4">Elige una palabra secreta (algo de ustedes dos) para que tu pareja adivine.</p>
                <input type="text" name="palabra" placeholder="Palabra secreta" required class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none mb-3">
                <input type="text" name="pista" placeholder="Pista (opcional)" class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none mb-4">
                <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 rounded-2xl shadow-md transition-all active:scale-[0.98]">Crear palabra secreta 🔒</button>
            </form>
        {% elif juego.es_autor %}
            <div class="bg-yellow-50 border border-yellow-200 text-yellow-700 text-sm p-4 rounded-2xl max-w-lg w-full text-center">
                Tu pareja está adivinando tu palabra secreta... 🤫 (esta página se actualiza sola)
            </div>
        {% else %}
            <div class="bg-white p-8 rounded-3xl shadow-xl max-w-lg w-full border border-pink-100 text-center">
                {% if juego.pista %}<p class="text-xs text-gray-400 mb-2">Pista: {{ juego.pista }}</p>{% endif %}
                <p class="text-3xl font-mono tracking-widest text-pink-600 mb-4">{{ juego.mostrar }}</p>
                <p class="text-sm text-gray-500 mb-4">Vidas: {% for i in range(juego.vidas) %}🐻{% endfor %}</p>
                <form method="POST" action="/juegos/ahorcado/letra" class="grid grid-cols-7 gap-1">
                    {% for l in 'ABCDEFGHIJKLMNÑOPQRSTUVWXYZ' %}
                    <button type="submit" name="letra" value="{{ l }}" {% if l in juego.letras %}disabled{% endif %}
                        class="text-xs font-bold py-2 rounded-lg {% if l in juego.letras %} bg-gray-100 text-gray-300 {% else %} bg-pink-50 hover:bg-pink-200 text-pink-600 {% endif %}">{{ l }}</button>
                    {% endfor %}
                </form>
            </div>
        {% endif %}
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html, juego=juego))


@app.route('/juegos/ahorcado/letra', methods=['POST'])
def ahorcado_letra():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    letra = request.form.get('letra', '').strip().upper()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, autor_slot, palabra, letras_probadas, vidas, estado FROM ahorcado_juegos '
        'WHERE espacio = %s ORDER BY creado_en DESC LIMIT 1',
        (codigo,)
    )
    fila = cursor.fetchone()

    if fila and fila[5] == 'jugando' and fila[1] != identidad['slot'] and letra:
        gid, autor_slot, palabra, letras_probadas, vidas, estado = fila
        letras = letras_probadas.split(',') if letras_probadas else []
        if letra not in letras:
            letras.append(letra)
            if letra not in palabra:
                vidas -= 1
            nuevo_estado = 'jugando'
            if vidas <= 0:
                nuevo_estado = 'perdido'
            elif all(c in letras or c == ' ' for c in palabra):
                nuevo_estado = 'ganado'
            cursor.execute(
                'UPDATE ahorcado_juegos SET letras_probadas = %s, vidas = %s, estado = %s WHERE id = %s',
                (','.join(letras), vidas, nuevo_estado, gid)
            )
            conn.commit()
            if nuevo_estado in ('ganado', 'perdido'):
                crear_notificacion(
                    codigo, autor_slot, identidad['nombre'], 'ahorcado_resultado',
                    'El ahorcado terminó: ' + ('¡lo lograron! 🎉' if nuevo_estado == 'ganado' else 'se acabaron las vidas 😢'),
                    emoji='🔤', url='/juegos/ahorcado'
                )
    cursor.close()
    conn.close()
    return redirect(url_for('ahorcado_juego'))


# --- Penales ---
@app.route('/juegos/penales')
def penales_juego():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    ocupados = obtener_usuarios(codigo)

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT slot, goles, tiros FROM penales_marcador WHERE espacio = %s', (codigo,))
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    marcador = {slot: {'goles': g, 'tiros': t} for slot, g, t in filas}
    tabla = []
    for s, datos in ocupados.items():
        m = marcador.get(s, {'goles': 0, 'tiros': 0})
        tabla.append({'nombre': datos['nombre'], 'genero': datos['genero'], 'goles': m['goles'], 'tiros': m['tiros']})

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Penales</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-10 px-4">
        <div class="w-full max-w-md mb-6"><a href="/juegos" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver a juegos</a></div>
        <h1 class="text-2xl font-bold text-pink-600 text-center mb-2">⚽ Penales</h1>
        <p class="text-xs text-gray-500 text-center mb-6">Pateen 5 penales cada quien y comparen quién mete más goles.</p>

        <div class="max-w-md w-full space-y-2 mb-6">
            {% for t in tabla %}
            <div class="bg-white rounded-2xl border-2
                {% if t.genero == 'hombre' %} border-blue-200
                {% elif t.genero == 'mujer' %} border-pink-200
                {% else %} border-gray-200 {% endif %}
            p-4 flex justify-between items-center">
                <span class="font-bold text-gray-700">{{ t.nombre }}</span>
                <span class="text-pink-600 font-bold">{{ t.goles }} goles / {{ t.tiros }} tiros</span>
            </div>
            {% endfor %}
        </div>

        <a href="/juegos/penales/jugar" class="w-full max-w-md text-center bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 rounded-2xl shadow-md transition-all active:scale-[0.98]">
            Patear 5 penales ⚽
        </a>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html, tabla=tabla))


@app.route('/juegos/penales/jugar')
def penales_jugar():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pateando penales</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4 text-center">
        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-md w-full border border-pink-100">
            <p id="ronda" class="text-xs text-gray-400 mb-2">Tiro 1 de 5</p>
            <span id="pelota" class="text-6xl block mb-4">⚽</span>
            <p id="mensaje" class="font-semibold text-pink-600 min-h-[28px] mb-4">Elige dónde patear</p>
            <div class="flex gap-2">
                <button onclick="patear('izquierda')" class="flex-1 bg-pink-50 hover:bg-pink-200 text-pink-600 font-bold py-4 rounded-2xl transition-all active:scale-95">⬅️</button>
                <button onclick="patear('centro')" class="flex-1 bg-pink-50 hover:bg-pink-200 text-pink-600 font-bold py-4 rounded-2xl transition-all active:scale-95">⬆️</button>
                <button onclick="patear('derecha')" class="flex-1 bg-pink-50 hover:bg-pink-200 text-pink-600 font-bold py-4 rounded-2xl transition-all active:scale-95">➡️</button>
            </div>
        </div>
        <form id="form-guardar" method="POST" action="/juegos/penales/guardar" class="hidden">
            <input type="hidden" name="goles" id="input-goles">
        </form>
        <script>
            var DIRECCIONES = ['izquierda', 'centro', 'derecha'];
            var tiro = 0, goles = 0;
            function patear(direccion) {
                var portero = DIRECCIONES[Math.floor(Math.random() * 3)];
                tiro++;
                var mensaje = document.getElementById('mensaje');
                if (portero !== direccion) {
                    goles++;
                    mensaje.textContent = '¡GOOOL! ⚽🎉';
                    mensaje.className = 'font-semibold text-green-600 min-h-[28px] mb-4';
                } else {
                    mensaje.textContent = '¡Atajada del portero! 🧤';
                    mensaje.className = 'font-semibold text-red-500 min-h-[28px] mb-4';
                }
                if (tiro >= 5) {
                    setTimeout(function() {
                        document.getElementById('input-goles').value = goles;
                        document.getElementById('form-guardar').submit();
                    }, 900);
                } else {
                    document.getElementById('ronda').textContent = 'Tiro ' + (tiro + 1) + ' de 5';
                }
            }
        </script>
    </body>
    </html>
    '''
    return con_mascota(html)


@app.route('/juegos/penales/guardar', methods=['POST'])
def penales_guardar():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    goles = request.form.get('goles', type=int) or 0
    goles = max(0, min(5, goles))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO penales_marcador (espacio, slot, goles, tiros) VALUES (%s, %s, %s, 5) '
        'ON CONFLICT (espacio, slot) DO UPDATE SET goles = penales_marcador.goles + %s, tiros = penales_marcador.tiros + 5',
        (codigo, identidad['slot'], goles, goles)
    )
    conn.commit()
    cursor.close()
    conn.close()

    crear_notificacion(
        codigo, otro_slot(identidad['slot']), identidad['nombre'], 'penales',
        identidad['nombre'] + ' metió ' + str(goles) + '/5 penales ⚽', emoji='⚽', url='/juegos/penales'
    )
    return redirect(url_for('penales_juego'))


# === CERRAR SESIÓN ===
@app.route('/salir')
def salir():
    session.pop('espacio_activo', None)
    session.pop('mi_slot', None)
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
