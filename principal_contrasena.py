from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_ultra_segura'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

# === CONFIGURACIÓN DE LA BASE DE DATOS ===
def init_db():
    conn = sqlite3.connect('espacios.db')
    cursor = conn.cursor()
    # Creamos la tabla para registrar los códigos de los espacios creados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS espacios (
            codigo TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === RUTA PRINCIPAL (EL PANEL DE BIENVENIDA) ===
@app.route('/', methods=['GET', 'POST'])
def home():
    # Si ya tiene una sesión activa en un espacio, lo mandamos directo adentro
    if 'espacio_activo' in session:
        return redirect(url_for('espacio_virtual'))

    mensaje_error = None
    mensaje_exito = None

    if request.method == 'POST':
        accion = request.form.get('accion')
        codigo = request.form.get('codigo', '').strip().lower() # Limpiamos espacios y pasamos a minúsculas

        if not codigo:
            mensaje_error = "¡Por favor, escribe un código!"
        else:
            conn = sqlite3.connect('espacios.db')
            cursor = conn.cursor()

            # --- CASO 1: CREAR UN NUEVO ESPACIO ---
            if accion == 'crear':
                try:
                    cursor.execute('INSERT INTO espacios (codigo) VALUES (?)', (codigo,))
                    conn.commit()
                    mensaje_exito = f'¡Espacio "{codigo}" creado con éxito! Ahora puedes entrar.'
                except sqlite3.IntegrityError:
                    mensaje_error = "Ese código de espacio ya existe. ¡Prueba con otro!"

            # --- CASO 2: ENTRAR A UN ESPACIO EXISTENTE ---
            elif accion == 'entrar':
                cursor.execute('SELECT codigo FROM espacios WHERE codigo = ?', (codigo,))
                resultado = cursor.fetchone()
                if resultado:
                    # Guardamos el código en la sesión permanente
                    session.permanent = True
                    session['espacio_activo'] = codigo
                    conn.close()
                    return redirect(url_for('espacio_virtual'))
                else:
                    mensaje_error = "Ese espacio no existe. ¿Escribiste bien el código?"

            conn.close()

    # === DISEÑO EN HTML (ESTILO TIERNO) ===
    # Usamos Tailwind CSS para darle un diseño moderno, limpio y con colores suaves
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


# === EL ESPACIO VIRTUAL ADENTRO ===
@app.route('/espacio')
def espacio_virtual():
    # Si alguien intenta entrar directamente sin loguearse, lo pateamos a la entrada
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))

    # Diseño básico del interior del espacio
    html_espacio = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Espacio: {{ codigo_sala }}</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-pink-50 min-h-screen flex flex-col items-center justify-center font-sans p-4">
        <div class="bg-white p-8 rounded-3xl shadow-xl max-w-lg w-full text-center border border-pink-100">
            <h2 class="text-2xl font-bold text-pink-600">💖 Espacio Privado: {{ codigo_sala }} 💖</h2>
            <p class="text-gray-500 mt-2">¡Felicidades, están adentro de su rincón secreto permanente!</p>
            
            <div class="my-8 p-6 bg-pink-50 rounded-2xl border border-dashed border-pink-200 text-gray-600">
                <p class="italic">"Aquí es donde empezaremos a construir los besitos virtuales, las notitas románticas y los abrazos."</p>
            </div>

            <a href="/salir" class="text-xs text-gray-400 hover:text-red-400 underline">Cerrar sesión en este espacio</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_espacio, codigo_sala=session['espacio_activo'])


# === CERRAR SESIÓN (Por si quieren cambiar de espacio) ===
@app.route('/salir')
def salir():
    session.pop('espacio_activo', None)
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
