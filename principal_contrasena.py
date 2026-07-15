from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import timedelta
import os
import random
import psycopg2

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_ultra_segura'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

DATABASE_URL = os.environ.get('DATABASE_URL')


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# === CONFIGURACIÓN DE LA BASE DE DATOS ===
def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS espacios (
            codigo TEXT PRIMARY KEY
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            espacio TEXT NOT NULL,
            slot INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            genero TEXT NOT NULL,
            PRIMARY KEY (espacio, slot)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notas (
            id SERIAL PRIMARY KEY,
            espacio TEXT NOT NULL,
            slot INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            genero TEXT NOT NULL,
            contenido TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()


# === HELPERS DE IDENTIDAD (bloque 1 / bloque 2) ===
def obtener_usuarios(codigo):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT slot, nombre, genero FROM usuarios WHERE espacio = %s', (codigo,))
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return {slot: {'nombre': nombre, 'genero': genero} for slot, nombre, genero in filas}


def mi_identidad():
    """Devuelve dict con slot/nombre/genero de la persona actual, o None si no ha elegido bloque."""
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
    """Si falta algo, devuelve un redirect. Si todo está OK, devuelve None."""
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))
    if 'mi_slot' not in session:
        return redirect(url_for('quien_eres'))
    return None


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
                    mensaje_exito = f'¡Espacio "{codigo}" creado con éxito! Ahora puedes entrar.'
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
    return render_template_string(html_bienvenida, error=mensaje_error, exito=mensaje_exito)


# === EL ESPACIO VIRTUAL ADENTRO (hub con las 8 ventanas) ===
@app.route('/espacio')
def espacio_virtual():
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))
    if 'mi_slot' not in session:
        return redirect(url_for('quien_eres'))

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
                position: relative;
                overflow: hidden;
                transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1),
                            box-shadow 0.35s ease;
            }
            .ventana:hover {
                transform: translateY(-6px) scale(1.06);
                box-shadow: 0 20px 40px -12px rgba(236, 72, 153, 0.35);
                z-index: 10;
            }
            .ventana-icono { transition: transform 0.35s ease; }
            .ventana:hover .ventana-icono { transform: scale(1.15) rotate(-4deg); }
            .ventana-detalle {
                max-height: 0; opacity: 0;
                transition: max-height 0.35s ease, opacity 0.3s ease, margin-top 0.35s ease;
            }
            .ventana:hover .ventana-detalle { max-height: 100px; opacity: 1; margin-top: 0.5rem; }
            .ventana::before {
                content: ""; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
                background: radial-gradient(circle, rgba(244, 114, 182, 0.12) 0%, transparent 60%);
                opacity: 0; transition: opacity 0.35s ease; pointer-events: none;
            }
            .ventana:hover::before { opacity: 1; }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-12 px-4">

        <div class="w-full max-w-5xl flex justify-end mb-4">
            <a href="/salir"
               class="text-xs text-gray-400 hover:text-red-400 hover:bg-red-50 border border-transparent hover:border-red-100 px-3 py-2 rounded-xl transition-all flex items-center gap-1">
                <span>Cerrar sesión</span>
                <span>🔒</span>
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

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">📸</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Fotos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Guarden juntos las fotos que más les gustan de su historia.</p>
            </a>

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">💌</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Cartas</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Escriban cartas más largas para ocasiones especiales.</p>
            </a>

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">📅</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Recuerdos</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Una línea de tiempo con los momentos más importantes juntos.</p>
            </a>

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="ventana-icono text-4xl">🎵</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Playlist</h3>
                <p class="ventana-detalle text-sm text-gray-500 px-2">Las canciones que les recuerdan a ustedes dos.</p>
            </a>

            <a href="#" class="ventana bg-white rounded-3xl border border-pink-100 p-6 shadow-md flex flex-col items-center text-center cursor-pointer">
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
    </body>
    </html>
    '''
    return render_template_string(html_espacio, codigo_sala=session['espacio_activo'])


# === ¿QUIÉN ERES? (elección de bloque / identidad de pareja) ===
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
                            ">
                                Soy {{ datos.nombre }}
                            </button>
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
                        ">
                            Soy {{ datos.nombre }}
                        </button>
                    </form>
                    {% endfor %}
                </div>
            {% endif %}

            <a href="/salir" class="text-xs text-gray-400 hover:text-red-400 underline mt-8 inline-block">Cerrar sesión</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_quien_eres, codigo_sala=codigo, ocupados=ocupados,
                                   slot_libre=slot_libre, error=mensaje_error)


# === MENÚ DE NOTITAS ===
@app.route('/notas')
def notas_menu():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

    html_notas_menu = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Notitas</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .opcion { transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.3s ease; }
            .opcion:hover { transform: translateY(-6px) scale(1.04); box-shadow: 0 20px 40px -12px rgba(236,72,153,0.35); }
        </style>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center py-12 px-4">
        <div class="w-full max-w-3xl flex justify-between items-center mb-10">
            <a href="/espacio" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver al espacio</a>
            <a href="/salir" class="text-xs text-gray-400 hover:text-red-400 underline">Cerrar sesión</a>
        </div>

        <h1 class="text-3xl font-bold text-pink-600 mb-8">📝 Notitas</h1>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-2xl w-full">
            <a href="/notas/escribir" class="opcion bg-white rounded-3xl border border-pink-100 p-8 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="text-4xl">✍️</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Escribir una nota</h3>
            </a>
            <a href="/notas/ver" class="opcion bg-white rounded-3xl border border-pink-100 p-8 shadow-md flex flex-col items-center text-center cursor-pointer">
                <span class="text-4xl">📬</span>
                <h3 class="text-lg font-bold text-pink-600 mt-3">Ver notas enviadas</h3>
            </a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_notas_menu, codigo_sala=session['espacio_activo'])


# === ESCRIBIR UNA NOTA NUEVA ===
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
            return redirect(url_for('ver_notas'))

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
        <div class="w-full max-w-xl">
            <a href="/notas" class="text-sm text-gray-400 hover:text-pink-500">&larr; Volver</a>
        </div>
        <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl max-w-xl w-full border border-pink-100 mt-4">
            <p class="text-xs text-gray-400 mb-1">Escribiendo como</p>
            <p class="font-bold mb-4
                {% if identidad.genero == 'hombre' %} text-blue-600
                {% elif identidad.genero == 'mujer' %} text-pink-600
                {% else %} text-gray-600 {% endif %}
            ">{{ identidad.nombre }}</p>

            <textarea name="contenido" rows="10" placeholder="Escribe algo lindo..."
                class="w-full px-4 py-3 rounded-2xl border-2 border-pink-100 focus:border-pink-300 focus:outline-none resize-none text-gray-700"
                required></textarea>

            <button type="submit" class="mt-4 w-full bg-pink-500 hover:bg-pink-600 text-white font-semibold py-3 px-6 rounded-2xl shadow-md transition-all active:scale-[0.98]">
                Enviar nota 💌
            </button>
        </form>
    </body>
    </html>
    '''
    return render_template_string(html_escribir_nota, codigo_sala=codigo, identidad=identidad)


# === VER NOTAS ENVIADAS (estilo corcho, esparcidas) ===
@app.route('/notas/ver')
def ver_notas():
    redir = requiere_espacio_e_identidad()
    if redir:
        return redir

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
    return render_template_string(html_ver_notas, codigo_sala=codigo, notas=notas)


# === CERRAR SESIÓN ===
@app.route('/salir')
def salir():
    session.pop('espacio_activo', None)
    session.pop('mi_slot', None)
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
