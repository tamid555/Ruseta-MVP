import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pymysql
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from utilidades import distanciaMetros

load_dotenv()

app = FastAPI(title="Backend Ruseta - Cúcuta")

# Aceptamos peticiones desde Live Server en cualquier puerto, pero solo desde este mismo computador
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

RADIO_CAMINATA = 500          # metros máximos que el usuario camina hasta/desde la ruta
PASO_METROS = 40              # distancia entre puntos guardados (la fija importar_osm.py)
VELOCIDAD_SIMULADA = 12       # metros por segundo de las busetas simuladas (aprox. 43 km/h)

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Falta JWT_SECRET en el archivo .env")
HORAS_SESION = 8              # cuánto dura la sesión antes de pedir login otra vez


def conectar_bd():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor
    )


class DatosLogin(BaseModel):
    email: str
    password: str


class DatosRegistro(BaseModel):
    nombre: str
    email: str
    password: str


@app.get("/")
def estado_servidor():
    return {"mensaje": "Servidor de Ruseta en línea y esperando conexiones"}


# ---------------------- SESIONES Y PERMISOS -----------------------

esquemaBearer = HTTPBearer(auto_error=False)   # lee el encabezado "Authorization: Bearer <token>"


def crearToken(idUsuario):
    """Crea el 'carnet' firmado que el navegador manda en cada petición protegida."""
    carga = {"sub": str(idUsuario), "exp": datetime.now(timezone.utc) + timedelta(hours=HORAS_SESION)}
    return jwt.encode(carga, JWT_SECRET, algorithm="HS256")


def usuarioActual(credenciales: HTTPAuthorizationCredentials | None = Depends(esquemaBearer)):
    """Verifica el token y devuelve el usuario con su rol actual (leído de la base de datos)."""
    if credenciales is None:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")
    try:
        carga = jwt.decode(credenciales.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Tu sesión expiró, inicia sesión de nuevo")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sesión no válida")

    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id, nombre, email, rol FROM usuarios WHERE id = %s", (int(carga["sub"]),))
            usuario = cursor.fetchone()
    finally:
        conexion.close()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    return usuario


def soloAdmin(usuario=Depends(usuarioActual)):
    """Deja pasar solo a los administradores."""
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para hacer esto")
    return usuario


# ---------------------------- USUARIOS ----------------------------

PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validarRegistro(datos):
    """Revisa los datos del formulario de registro. Si algo está mal, responde 400 con un mensaje claro."""
    if not datos.nombre.strip():
        raise HTTPException(status_code=400, detail="Escribe tu nombre")
    if not PATRON_CORREO.match(datos.email.strip()):
        raise HTTPException(status_code=400, detail="Escribe un correo válido")
    if len(datos.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    if len(datos.password.encode("utf-8")) > 72:   # bcrypt solo admite 72 bytes
        raise HTTPException(status_code=400, detail="La contraseña es demasiado larga")


@app.post("/api/registro")
def registrar_usuario(datos: DatosRegistro):
    validarRegistro(datos)
    nombre = datos.nombre.strip()
    email = datos.email.strip().lower()
    hashClave = bcrypt.hashpw(datos.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Ese correo ya está registrado")
            cursor.execute(
                "INSERT INTO usuarios (nombre, email, password_hash, es_invitado) VALUES (%s, %s, %s, FALSE)",
                (nombre, email, hashClave)
            )
        conexion.commit()
        return {"estado": "exito", "mensaje": "Usuario creado"}
    finally:
        conexion.close()


@app.post("/api/login")
def iniciar_sesion(datos: DatosLogin):
    email = datos.email.strip().lower()
    claveBytes = datos.password.encode("utf-8")
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT id, nombre, rol, password_hash FROM usuarios WHERE email = %s AND es_invitado = FALSE",
                (email,)
            )
            usuario = cursor.fetchone()
    finally:
        conexion.close()

    # Mismo mensaje si el correo no existe o la contraseña es incorrecta (no revela qué correos hay registrados)
    if not usuario or len(claveBytes) > 72 or not bcrypt.checkpw(claveBytes, usuario["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

    return {
        "estado": "exito",
        "token": crearToken(usuario["id"]),
        "usuario": {"id": usuario["id"], "nombre": usuario["nombre"], "rol": usuario["rol"], "esInvitado": False},
    }


@app.get("/api/yo")
def datos_de_mi_cuenta(usuario=Depends(usuarioActual)):
    """Devuelve los datos del usuario que inició sesión (requiere token)."""
    return {"estado": "exito", "usuario": {"id": usuario["id"], "nombre": usuario["nombre"],
                                           "email": usuario["email"], "rol": usuario["rol"]}}


@app.get("/api/admin/resumen")
def resumen_para_admin(admin=Depends(soloAdmin)):
    """Cifras generales del sistema (solo administradores)."""
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM usuarios WHERE es_invitado = FALSE")
            usuarios = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) AS total FROM rutas")
            rutas = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) AS total FROM ruta_puntos")
            puntos = cursor.fetchone()["total"]
    finally:
        conexion.close()
    return {"estado": "exito", "usuarios": usuarios, "rutas": rutas, "puntos": puntos}


# ------------------------------ RUTAS -----------------------------

@app.get("/api/rutas")
def obtener_rutas():
    """Lista de rutas (sin puntos, para que la respuesta sea liviana)."""
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id, nombre_ruta, ref FROM rutas ORDER BY nombre_ruta")
            rutas = cursor.fetchall()
    finally:
        conexion.close()
    return {"estado": "exito", "rutas": [{"id": r["id"], "nombre": r["nombre_ruta"], "ref": r["ref"]} for r in rutas]}


@app.get("/api/rutas/{ruta_id}/puntos")
def obtener_puntos_ruta(ruta_id: int):
    """Todos los puntos de UNA ruta, en orden, para dibujarla en el mapa."""
    conexion = conectar_bd()
    
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT orden, latitud, longitud FROM ruta_puntos WHERE ruta_id = %s ORDER BY orden", (ruta_id,))
            filas = cursor.fetchall()
    finally:
        conexion.close()
    if not filas:
        raise HTTPException(status_code=404, detail="Ruta sin puntos")
    return {"estado": "exito",
            "puntos": [{"orden": f["orden"], "lat": float(f["latitud"]), "lng": float(f["longitud"])} for f in filas]}


def puntoMasCercanoPorRuta(cursor, lat, lng, radio):
    """Para cada ruta, el punto suyo más cercano a (lat, lng), si está dentro del radio."""
    deltaLat = radio / 111000
    deltaLng = radio / (111000 * math.cos(math.radians(lat)))
    # Primero filtramos con un cuadro en SQL (rápido) y luego medimos la distancia real