import math
import os
import time

import bcrypt
import pymysql
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from utilidades import distanciaMetros

load_dotenv()

app = FastAPI(title="Backend Ruseta - Cúcuta")

# Solo permitimos el origen de Live Server (cambia el puerto si el tuyo es otro)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RADIO_CAMINATA = 500          # metros máximos que el usuario camina hasta/desde la ruta
PASO_METROS = 40              # distancia entre puntos guardados (la fija importar_osm.py)
VELOCIDAD_SIMULADA = 12       # metros por segundo de las busetas simuladas (aprox. 43 km/h)


def conectar_bd():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
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


# ---------------------------- USUARIOS ----------------------------

@app.post("/api/registro")
def registrar_usuario(datos: DatosRegistro):
    hashClave = bcrypt.hashpw(datos.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (datos.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Ese correo ya está registrado")
            cursor.execute(
                "INSERT INTO usuarios (nombre, email, password_hash, es_invitado) VALUES (%s, %s, %s, FALSE)",
                (datos.nombre, datos.email, hashClave)
            )
        conexion.commit()
        return {"estado": "exito", "mensaje": "Usuario creado"}
    finally:
        conexion.close()


@app.post("/api/login")
def iniciar_sesion(datos: DatosLogin):
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT id, nombre, password_hash FROM usuarios WHERE email = %s AND es_invitado = FALSE",
                (datos.email,)
            )
            usuario = cursor.fetchone()
    finally:
        conexion.close()

    if not usuario or not bcrypt.checkpw(datos.password.encode("utf-8"), usuario["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

    return {"estado": "exito", "usuario": {"id": usuario["id"], "nombre": usuario["nombre"], "esInvitado": False}}


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
    cursor.execute(
        "SELECT ruta_id, orden, latitud, longitud FROM ruta_puntos "
        "WHERE latitud BETWEEN %s AND %s AND longitud BETWEEN %s AND %s",
        (lat - deltaLat, lat + deltaLat, lng - deltaLng, lng + deltaLng)
    )
    mejores = {}
    for fila in cursor.fetchall():
        puntoLat, puntoLng = float(fila["latitud"]), float(fila["longitud"])
        distancia = distanciaMetros(lat, lng, puntoLat, puntoLng)
        if distancia > radio:
            continue
        actual = mejores.get(fila["ruta_id"])
        if actual is None or distancia < actual["distancia"]:
            mejores[fila["ruta_id"]] = {"distancia": round(distancia), "orden": fila["orden"],
                                        "lat": puntoLat, "lng": puntoLng}
    return mejores


@app.get("/api/buscar")
def buscar_rutas(latA: float, lngA: float, latB: float, lngB: float, radio: int = RADIO_CAMINATA):
    """Rutas que pasan cerca de A y de B, y que van de A hacia B (no al revés)."""
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cercanosA = puntoMasCercanoPorRuta(cursor, latA, lngA, radio)
            cercanosB = puntoMasCercanoPorRuta(cursor, latB, lngB, radio)
            cursor.execute("SELECT id, nombre_ruta, ref FROM rutas")
            nombres = {r["id"]: r for r in cursor.fetchall()}
    finally:
        conexion.close()

    resultados = []
    for rutaId, subida in cercanosA.items():
        bajada = cercanosB.get(rutaId)
        if bajada and subida["orden"] < bajada["orden"]:   # el orden decide el sentido
            resultados.append({
                "id": rutaId,
                "nombre": nombres[rutaId]["nombre_ruta"],
                "ref": nombres[rutaId]["ref"],
                "subida": subida,
                "bajada": bajada,
                "caminataTotal": subida["distancia"] + bajada["distancia"],
            })
    resultados.sort(key=lambda r: r["caminataTotal"])
    return {"estado": "exito", "resultados": resultados[:5]}


# ------------------------ BUSETAS SIMULADAS -----------------------

@app.get("/api/busetas-simuladas/{ruta_id}")
def busetas_simuladas(ruta_id: int, ordenSubida: int = 0, cantidad: int = 3):
    """Posiciones SIMULADAS de busetas sobre la ruta (no hay GPS real todavía)."""
    conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT orden, latitud, longitud FROM ruta_puntos WHERE ruta_id = %s ORDER BY orden", (ruta_id,))
            puntos = cursor.fetchall()
    finally:
        conexion.close()
    if not puntos:
        raise HTTPException(status_code=404, detail="Ruta sin puntos")

    total = len(puntos)
    avance = time.time() * VELOCIDAD_SIMULADA / PASO_METROS   # cuántos puntos ha avanzado en el tiempo
    busetas = []
    for i in range(cantidad):
        indice = int(avance + i * total / cantidad) % total
        metrosParaLlegar = ((ordenSubida - indice) % total) * PASO_METROS   # cuánto le falta para tu punto de subida
        busetas.append({
            "placa": f"SIM-{i + 1:02d}",
            "lat": float(puntos[indice]["latitud"]),
            "lng": float(puntos[indice]["longitud"]),
            "metrosParaLlegar": metrosParaLlegar,
            "minutos": round(metrosParaLlegar / VELOCIDAD_SIMULADA / 60, 1),
        })
    busetas.sort(key=lambda b: b["metrosParaLlegar"])
    return {"estado": "exito", "simulado": True, "busetas": busetas}