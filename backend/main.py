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

# Si no tienes utilidades.py, podemos incluir la función distancia aquí
def distanciaMetros(lat1, lon1, lat2, lon2):
    R = 6371000  # Radio de la Tierra en metros
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

load_dotenv()

app = FastAPI(title="Backend Ruseta - Cúcuta")

# Configuración estricta de CORS para desarrollo local
origenes_permitidos = [
    "http://127.0.0.1:5500",
    "http://localhost:5500"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RADIO_CAMINATA = 500          
PASO_METROS = 40              
VELOCIDAD_SIMULADA = 12       

JWT_SECRET = os.getenv("JWT_SECRET", "secreto_temporal") # Agregado un default por si falla el .env
HORAS_SESION = 8              

def conectar_bd():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "ruseta"),
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
esquemaBearer = HTTPBearer(auto_error=False)   

def crearToken(idUsuario):
    carga = {"sub": str(idUsuario), "exp": datetime.now(timezone.utc) + timedelta(hours=HORAS_SESION)}
    return jwt.encode(carga, JWT_SECRET, algorithm="HS256")

def usuarioActual(credenciales: HTTPAuthorizationCredentials | None = Depends(esquemaBearer)):
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
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para hacer esto")
    return usuario

# ---------------------------- USUARIOS ----------------------------
PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def validarRegistro(datos):
    if not datos.nombre.strip():
        raise HTTPException(status_code=400, detail="Escribe tu nombre")
    if not PATRON_CORREO.match(datos.email.strip()):
        raise HTTPException(status_code=400, detail="Escribe un correo válido")
    if len(datos.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    if len(datos.password.encode("utf-8")) > 72:   
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

    if not usuario or len(claveBytes) > 72 or not bcrypt.checkpw(claveBytes, usuario["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

    return {
        "estado": "exito",
        "token": crearToken(usuario["id"]),
        "usuario": {"id": usuario["id"], "nombre": usuario["nombre"], "rol": usuario["rol"], "esInvitado": False},
    }

@app.get("/api/yo")
def datos_de_mi_cuenta(usuario=Depends(usuarioActual)):
    return {"estado": "exito", "usuario": {"id": usuario["id"], "nombre": usuario["nombre"],
                                           "email": usuario["email"], "rol": usuario["rol"]}}

@app.get("/api/admin/resumen")
def resumen_para_admin(admin=Depends(soloAdmin)):
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

# ------------------------------ RUTAS GEOESPACIALES -----------------------------

@app.get("/api/rutas")
def obtener_rutas():
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
            "puntos": [{"lat": float(f["latitud"]), "lng": float(f["longitud"])} for f in filas]}

class SolicitudRuta(BaseModel):
    lat_origen: float
    lng_origen: float
    lat_destino: float
    lng_destino: float

@app.post("/api/buscar-ruta-buseta")
def buscar_mejor_buseta(solicitud: SolicitudRuta):
    """
    Busca qué ruta de MySQL tiene puntos cerca al Origen Y al Destino.
    """
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            # 1. Buscar rutas que pasen cerca del ORIGEN (Cuadro delimitador rápido + Haversine)
            deltaLat_O = RADIO_CAMINATA / 111000
            deltaLng_O = RADIO_CAMINATA / (111000 * math.cos(math.radians(solicitud.lat_origen)))
            
            cursor.execute("""
                SELECT DISTINCT ruta_id 
                FROM ruta_puntos 
                WHERE latitud BETWEEN %s AND %s 
                  AND longitud BETWEEN %s AND %s
            """, (solicitud.lat_origen - deltaLat_O, solicitud.lat_origen + deltaLat_O, 
                  solicitud.lng_origen - deltaLng_O, solicitud.lng_origen + deltaLng_O))
            
            rutas_cerca_origen = {fila['ruta_id'] for fila in cursor.fetchall()}

            # 2. Buscar rutas que pasen cerca del DESTINO
            deltaLat_D = RADIO_CAMINATA / 111000
            deltaLng_D = RADIO_CAMINATA / (111000 * math.cos(math.radians(solicitud.lat_destino)))
            
            cursor.execute("""
                SELECT DISTINCT ruta_id 
                FROM ruta_puntos 
                WHERE latitud BETWEEN %s AND %s 
                  AND longitud BETWEEN %s AND %s
            """, (solicitud.lat_destino - deltaLat_D, solicitud.lat_destino + deltaLat_D, 
                  solicitud.lng_destino - deltaLng_D, solicitud.lng_destino + deltaLng_D))
            
            rutas_cerca_destino = {fila['ruta_id'] for fila in cursor.fetchall()}

            # 3. Intersección: ¿Qué rutas cumplen ambas condiciones?
            rutas_viables = rutas_cerca_origen.intersection(rutas_cerca_destino)

            if not rutas_viables:
                return {"encontrada": False, "mensaje": "Ninguna buseta hace este trayecto directo"}

            # Tomar la primera ruta viable (podrías añadir lógica luego para elegir "la más rápida")
            ruta_ganadora = list(rutas_viables)[0]

            # 4. Traer el nombre y los puntos de la ruta ganadora para dibujarla
            cursor.execute("SELECT nombre_ruta FROM rutas WHERE id = %s", (ruta_ganadora,))
            info_ruta = cursor.fetchone()

            cursor.execute("SELECT latitud, longitud FROM ruta_puntos WHERE ruta_id = %s ORDER BY orden", (ruta_ganadora,))
            puntos = [{"lat": float(f["latitud"]), "lng": float(f["longitud"])} for f in cursor.fetchall()]

            return {
                "encontrada": True,
                "nombre_ruta": info_ruta['nombre_ruta'],
                "ruta_id": ruta_ganadora,
                "puntos": puntos
            }
    finally:
        conexion.close()