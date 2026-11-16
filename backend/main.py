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
        port=int(os.getenv("DB_PORT", "3306")),
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

M_POR_MIN_CAMINANDO = 80          # ~4.8 km/h
M_POR_MIN_BUSETA = 300            # ~18 km/h promedio en ciudad
VIAJE_MINIMO_M = 300              # si el trayecto en buseta es menor, no vale la pena
RADIOS_CAMINATA = (500, 800, 1200)  # se prueba en orden: primero lo más cercano
SENTIDO_ESTRICTO = False          # False: se acepta cada ruta en sus dos sentidos (ida y vuelta)

def rutas_cerca(cursor, punto, radio):
    """Ids de las rutas con algún punto dentro del radio (cuadro rápido en SQL)."""
    lat, lng = punto
    d_lat = radio / 111000
    d_lng = radio / (111000 * math.cos(math.radians(lat)))
    cursor.execute(
        "SELECT DISTINCT ruta_id FROM ruta_puntos "
        "WHERE latitud BETWEEN %s AND %s AND longitud BETWEEN %s AND %s",
        (lat - d_lat, lat + d_lat, lng - d_lng, lng + d_lng))
    return {fila["ruta_id"] for fila in cursor.fetchall()}

def mejor_tramo(puntos, origen, destino, radio):
    """Mejor tramo (subida -> bajada) de UNA ruta, en el orden en que está guardada.
    Minimiza el tiempo estimado: caminata al subir + viaje en buseta + caminata al bajar."""
    n = len(puntos)
    if n < 2:
        return None
    directa = distanciaMetros(origen[0], origen[1], destino[0], destino[1])
    acumulada = [0.0] * n
    for k in range(1, n):
        acumulada[k] = acumulada[k - 1] + distanciaMetros(
            puntos[k - 1][0], puntos[k - 1][1], puntos[k][0], puntos[k][1])

    mejor_subida = None   # (valor, indice, metros_caminando)
    resultado = None
    for j in range(n):
        lat, lng = puntos[j]

        # ¿j sirve como punto de bajada? (la subida tiene que venir ANTES en el recorrido)
        dist_destino = distanciaMetros(lat, lng, destino[0], destino[1])
        if mejor_subida is not None and dist_destino <= radio:
            _, i, dist_origen = mejor_subida
            viaje = acumulada[j] - acumulada[i]
            # solo sirve si el viaje no es mínimo y caminar hasta/desde la buseta es menos que ir caminando directo
            if viaje >= VIAJE_MINIMO_M and dist_origen + dist_destino < directa:
                minutos = (dist_origen + dist_destino) / M_POR_MIN_CAMINANDO + viaje / M_POR_MIN_BUSETA
                if resultado is None or minutos < resultado["minutos"]:
                    resultado = {"i": i, "j": j, "caminata_origen": dist_origen,
                                 "caminata_destino": dist_destino, "viaje": viaje, "minutos": minutos}

        # ¿j sirve como punto de subida?
        dist_origen = distanciaMetros(lat, lng, origen[0], origen[1])
        if dist_origen <= radio:
            valor = dist_origen / M_POR_MIN_CAMINANDO - acumulada[j] / M_POR_MIN_BUSETA
            if mejor_subida is None or valor < mejor_subida[0]:
                mejor_subida = (valor, j, dist_origen)
    return resultado

@app.post("/api/buscar-ruta-buseta")
def buscar_mejor_buseta(solicitud: SolicitudRuta):
    origen = (solicitud.lat_origen, solicitud.lng_origen)
    destino = (solicitud.lat_destino, solicitud.lng_destino)

    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            opciones = []
            radio_usado = None
            for radio in RADIOS_CAMINATA:
                candidatas = rutas_cerca(cursor, origen, radio) & rutas_cerca(cursor, destino, radio)
                for ruta_id in candidatas:
                    cursor.execute(
                        "SELECT latitud, longitud FROM ruta_puntos WHERE ruta_id = %s ORDER BY orden", (ruta_id,))
                    puntos = [(float(f["latitud"]), float(f["longitud"])) for f in cursor.fetchall()]

                    # la ruta tal como está guardada y, si no es estricto, también al revés
                    versiones = [(puntos, False)]
                    if not SENTIDO_ESTRICTO:
                        versiones.append((puntos[::-1], True))

                    mejor = None
                    for pts, invertido in versiones:
                        tramo = mejor_tramo(pts, origen, destino, radio)
                        if tramo and (mejor is None or tramo["minutos"] < mejor[0]["minutos"]):
                            mejor = (tramo, pts, invertido)
                    if mejor:
                        cursor.execute("SELECT nombre_ruta, ref FROM rutas WHERE id = %s", (ruta_id,))
                        opciones.append((mejor[0], ruta_id, cursor.fetchone(), mejor[1], mejor[2]))
                if opciones:
                    radio_usado = radio
                    break

            if not opciones:
                return {"encontrada": False,
                        "mensaje": f"Ninguna buseta conecta tu origen y tu destino (se buscó hasta {RADIOS_CAMINATA[-1]} m a pie)"}

            opciones.sort(key=lambda o: o[0]["minutos"])
            tramo, ruta_id, info, puntos, invertido = opciones[0]
            i, j = tramo["i"], tramo["j"]
            return {
                "encontrada": True,
                "ruta_id": ruta_id,
                "nombre_ruta": info["nombre_ruta"],
                "ref": info["ref"],
                "puntos": [{"lat": p[0], "lng": p[1]} for p in puntos[i:j + 1]],
                "subida": {"lat": puntos[i][0], "lng": puntos[i][1]},
                "bajada": {"lat": puntos[j][0], "lng": puntos[j][1]},
                "caminata_origen_m": round(tramo["caminata_origen"]),
                "caminata_destino_m": round(tramo["caminata_destino"]),
                "viaje_m": round(tramo["viaje"]),
                "minutos_estimados": round(tramo["minutos"]),
                "radio_usado_m": radio_usado,
                "sentido_por_confirmar": invertido,
                "alternativas": [
                    {"nombre_ruta": o[2]["nombre_ruta"], "minutos_estimados": round(o[0]["minutos"])}
                    for o in opciones[1:3]
                ],
            }
    finally:
        conexion.close()