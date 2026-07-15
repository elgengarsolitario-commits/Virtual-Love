from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import timedelta
import os
import re
import json
import random
import urllib.request
import psycopg2

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_ultra_segura'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

DATABASE_URL = os.environ.get('DATABASE_URL')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_UPLOAD_PRESET = os.environ.get('CLOUDINARY_UPLOAD_PRESET', '')


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
    conn.commit()
    cursor.close()
    conn.close()

init_db()


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


# === MASCOTA FLOTANTE (aparece en todas las pantallas) ===
MASCOTA_HTML = '''
<div id="mascota-flotante" style="position:fixed; z-index:9999; cursor:grab; user-select:none; touch-action:none; font-size:46px; line-height:1; filter: drop-shadow(0 6px 10px rgba(0,0,0,0.25));">
    <div style="position:relative;">
        <span id="mascota-emoji">🐻</span>
        <span id="mascota-cerrar" style="position:absolute; top:-8px; right:-10px; background:#fff; border-radius:9999px; width:20px; height:20px; font-size:12px; display:none; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(0,0,0,0.25); cursor:pointer; color:#999;">✕</span>
    </div>
</div>
<div id="mascota-tab" style="position:fixed; bottom:16px; right:16px; z-index:9999; background:#fff; border-radius:9999px; width:36px; height:36px; display:none; align-items:center; justify-content:center; box-shadow:0 4px 10px rgba(0,0,0,0.2); cursor:pointer; font-size:18px;">🐾</div>
<script>
(function(){
    var mascota = document.getElementById('mascota-flotante');
    var cerrar = document.getElementById('mascota-cerrar');
    var tab = document.getElementById('mascota-tab');
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

    mascota.addEventListener('mousedown', function(e){ startDrag(e.clientX, e.clientY); });
    window.addEventListener('mousemove', function(e){ moveDrag(e.clientX, e.clientY); });
    window.addEventListener('mouseup', endDrag);

    mascota.addEventListener('touchstart', function(e){ var t = e.touches[0]; startDrag(t.clientX, t.clientY); }, {passive:true});
    window.addEventListener('touchmove', function(e){ var t = e.touches[0]; moveDrag(t.clientX, t.clientY); }, {passive:true});
    window.addEventListener('touchend', endDrag);
})();
</script>
'''


def con_mascota(html_renderizado):
    return html_renderizado.replace('</body>', MASCOTA_HTML + '</body>')


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
            .nota-fondo { position: absolute; width: 170px; padding: 14px; border-radius: 16px; filter: blur(2.5px); opacity: 0.55; }
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

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">🎮</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Juegos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Pequeños juegos o retos para hacer juntos cuando se conecten.</p>
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
    return con_mascota(render_template_string(html_espacio, codigo_sala=codigo, notas=notas))


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
                    <div class="mt-6 pt-4 border-t border-gray-100 space-y-2">
                        <p class="text-xs text-gray-400 mb-1">¿Ya habías elegido tu nombre antes en otro dispositivo?</p>
                        {% for s, datos in ocupados.items() %}
                        <form method="POST">
                            <input type="hidden" name="slot" value="{{ s }}">
                            <input type="hidden" name="accion" value="soy_yo">
                            <button type="submit" class="w-full text-sm py-2 px-4 rounded-xl border-2 font-semibold transition-all
                                {% if datos.genero == 'hombre' %} bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100
                                {% elif datos.genero == 'mujer' %} bg-pink-50 border-pink-200 text-pink-600 hover:bg-pink-100
                                {% else %} bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100 {% endif %}
                            ">Soy {{ datos.nombre }}</button>
                        </form>
                        {% endfor %}
                    </div>
                {% endif %}
            {% else %}
                <p class="text-sm text-gray-500 mb-4">Ya hay dos personas en este espacio. ¿Cuál de ellas eres?</p>
                <div class="space-y-3">
                    {% for s, datos in ocupados.items() %}
                    <form method="POST">
                        <input type="hidden" name="slot" value="{{ s }}">
                        <input type="hidden" name="accion" value="soy_yo">
                        <button type="submit" class="w-full py-3 px-4 rounded-2xl border-2 font-semibold transition-all
                            {% if datos.genero == 'hombre' %} bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100
                            {% elif datos.genero == 'mujer' %} bg-pink-50 border-pink-200 text-pink-600 hover:bg-pink-100
                            {% else %} bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100 {% endif %}
                        ">Soy {{ datos.nombre }}</button>
                    </form>
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
            return redirect(url_for('espacio_virtual'))

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
            return redirect(url_for('ver_fotos'))

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
                <input type="file" id="input-foto" accept="image/*" class="w-full mb-4 text-sm">
                <div id="preview-foto" class="mb-4"></div>
                <button id="btn-subir" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                    Subir foto 💗
                </button>
                <p id="estado-subida" class="text-xs text-gray-400 mt-3"></p>

                <form id="form-guardar" method="POST" class="hidden">
                    <input type="hidden" name="url" id="input-url">
                </form>

                <script>
                    var cloudName = "{{ cloud_name }}";
                    var uploadPreset = "{{ upload_preset }}";
                    var inputFoto = document.getElementById('input-foto');
                    var preview = document.getElementById('preview-foto');
                    var btn = document.getElementById('btn-subir');
                    var estado = document.getElementById('estado-subida');

                    inputFoto.addEventListener('change', function() {
                        preview.innerHTML = '';
                        var file = inputFoto.files[0];
                        if (file) {
                            var img = document.createElement('img');
                            img.src = URL.createObjectURL(file);
                            img.className = 'rounded-2xl max-h-56 mx-auto';
                            preview.appendChild(img);
                        }
                    });

                    btn.addEventListener('click', function() {
                        var file = inputFoto.files[0];
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
    return con_mascota(render_template_string(html_ver_fotos, fotos=fotos))


# === CARTAS (juego de completar frases) ===
@app.route('/cartas')
def cartas_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir
    return pagina_menu('Cartas', '💌', [
        {'url': '/cartas/crear', 'emoji': '✍️', 'texto': 'Crear una carta con espacios'},
        {'url': '/cartas/ver', 'emoji': '📖', 'texto': 'Ver mis cartas'},
    ])


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
            return redirect(url_for('ver_cartas'))

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
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <h2 class="text-lg font-bold text-pink-600 mb-2">Crea tu carta con espacios ✍️</h2>
            <p class="text-xs text-gray-500 mb-4">
                Escribe tu carta y usa <b>{1}</b>, <b>{2}</b>, <b>{3}</b>... donde quieras que tu pareja complete,
                por ejemplo: "Hoy quiero decirte que {1} y que me haces sentir {2}."
            </p>

            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}

            <textarea name="plantilla" rows="6" placeholder="Escribe tu carta usando {1}, {2}, {3}..."
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
        return redirect(url_for('ver_cartas'))

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
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/cartas/ver" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <h2 class="text-lg font-bold text-pink-600 mb-1">¡Te dejaron una carta! 💌</h2>
            <p class="text-xs text-gray-500 mb-6">Completa cada espacio sin ver el resto. ¡Es sorpresa!</p>
            {% for et in etiquetas %}
            <div class="mb-3">
                <label class="block text-xs text-gray-500 mb-1">Espacio {{ loop.index }}: {{ et }}</label>
                <input type="text" name="respuesta_{{ loop.index }}" required
                    class="w-full px-4 py-2 rounded-xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            {% endfor %}
            <button type="submit" class="mt-3 w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Revelar carta ✨
            </button>
        </form>
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
            'fecha': creado_en.strftime('%d/%m/%Y') if creado_en else ''
        })

    html_ver_cartas = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mis cartas</title>
        <script src="https://cdn.tailwindcss.com"></script>
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
            <div class="bg-white rounded-2xl border-2 p-5 shadow-md
                {% if c.autor_genero == 'hombre' %} border-blue-200
                {% elif c.autor_genero == 'mujer' %} border-pink-200
                {% else %} border-gray-200 {% endif %}
            ">
                {% if c.respondida %}
                    <p class="text-xs font-bold uppercase text-gray-400 mb-2">De {{ c.autor_nombre }} · completada por {{ c.completado_por }}</p>
                    <p class="text-gray-700 whitespace-pre-wrap">{{ c.contenido_final }}</p>
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
    return con_mascota(render_template_string(html_ver_cartas, cartas=cartas))


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
            return redirect(url_for('ver_recuerdos'))

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
    return con_mascota(render_template_string(html_ver_recuerdos, recuerdos=recuerdos))


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


@app.route('/playlist/agregar', methods=['GET', 'POST'])
def agregar_cancion():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    identidad = mi_identidad()
    mensaje_error = None

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        video_id = extraer_youtube_id(url)
        if not video_id:
            mensaje_error = "No pude reconocer ese link de YouTube. Revisa que sea correcto."
        else:
            titulo = obtener_titulo_youtube(video_id)
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO playlist (espacio, slot, nombre, genero, youtube_id, titulo) VALUES (%s, %s, %s, %s, %s, %s)',
                (codigo, identidad['slot'], identidad['nombre'], identidad['genero'], video_id, titulo)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('ver_playlist'))

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
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <h2 class="text-lg font-bold text-pink-600 mb-4">Agregar una canción 🎵</h2>
            {% if error %}
                <div class="bg-red-50 text-red-600 p-3 rounded-xl text-sm mb-4 border border-red-100">{{ error }}</div>
            {% endif %}
            <input type="text" name="url" placeholder="Pega el link de YouTube" required
                class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none mb-4">
            <button type="submit" class="w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Agregar a la playlist 🎧
            </button>
        </form>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_agregar, error=mensaje_error))


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

    canciones = [{'nombre': n, 'genero': g, 'youtube_id': yid, 'titulo': t} for n, g, yid, t, _ in filas]

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
                    <p class="text-xs text-gray-400 mt-1">Agregada por {{ c.nombre }}</p>
                </div>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_ver_playlist, canciones=canciones))


# === PLANES JUNTOS ===
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
            return redirect(url_for('ver_planes'))

    html_agregar = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Agregar plan</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-xl"><a href="/planes" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a></div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4 space-y-4">
            <h2 class="text-lg font-bold text-pink-600">Agregar un plan 🎯</h2>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Título</label>
                <input type="text" name="titulo" required placeholder="Ej: Ir a la playa"
                    class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">Descripción</label>
                <textarea name="descripcion" rows="3"
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
    </body>
    </html>
    '''
    return con_mascota(render_template_string(html_agregar))


@app.route('/planes/ver')
def ver_planes():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    codigo = session['espacio_activo']
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, nombre, genero, titulo, descripcion, imagen_url, estado FROM planes WHERE espacio = %s ORDER BY creado_en DESC',
        (codigo,)
    )
    filas = cursor.fetchall()
    cursor.close()
    conn.close()

    planes = []
    for pid, nombre, genero, titulo, descripcion, imagen_url, estado in filas:
        planes.append({
            'id': pid, 'nombre': nombre, 'genero': genero, 'titulo': titulo,
            'descripcion': descripcion, 'imagen_url': imagen_url, 'estado': estado
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
                    <p class="text-[10px] text-gray-400 mb-3">Agregado por {{ p.nombre }}</p>
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
    return con_mascota(render_template_string(html_ver_planes, planes=planes))


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
    return redirect(url_for('ver_planes'))


# === CERRAR SESIÓN ===
@app.route('/salir')
def salir():
    session.pop('espacio_activo', None)
    session.pop('mi_slot', None)
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
