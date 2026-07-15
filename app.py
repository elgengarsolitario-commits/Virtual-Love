from flask import Flask, render_template, request, redirect, url_for, session
from datetime import timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_ultra_segura'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

# === CONFIGURACIÓN DE LA BASE DE DATOS ===
def init_db():
    conn = sqlite3.connect('espacios.db')
    cursor = conn.cursor()
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
            conn = sqlite3.connect('espacios.db')
            cursor = conn.cursor()

            if accion == 'crear':
                try:
                    cursor.execute('INSERT INTO espacios (codigo) VALUES (?)', (codigo,))
                    conn.commit()
                    mensaje_exito = f'¡Espacio "{codigo}" creado con éxito! Ahora puedes entrar.'
                except sqlite3.IntegrityError:
                    mensaje_error = "Ese código de espacio ya existe. ¡Prueba con otro!"

            elif accion == 'entrar':
                cursor.execute('SELECT codigo FROM espacios WHERE codigo = ?', (codigo,))
                resultado = cursor.fetchone()
                if resultado:
                    session.permanent = True
                    session['espacio_activo'] = codigo
                    conn.close()
                    return redirect(url_for('espacio_virtual'))
                else:
                    mensaje_error = "Ese espacio no existe. ¿Escribiste bien el código?"

            conn.close()

    return render_template('home.html', error=mensaje_error, exito=mensaje_exito)


# === EL ESPACIO VIRTUAL ADENTRO (hub con las 6 ventanas) ===
@app.route('/espacio')
def espacio_virtual():
    if 'espacio_activo' not in session:
        return redirect(url_for('home'))

    return render_template('espacio.html', codigo_sala=session['espacio_activo'])


# === CERRAR SESIÓN ===
@app.route('/salir')
def salir():
    session.pop('espacio_activo', None)
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
