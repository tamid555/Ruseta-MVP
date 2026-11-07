from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pymysql

# ¡Esta es la variable "app" que Uvicorn no encuentra!
app = FastAPI(title="Backend Ruseta - Cúcuta")

# Permitir que el HTML (Frontend) se comunique con Python (Backend) sin bloqueos de seguridad
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de conexión a tu base de datos MySQL local
def conectar_bd():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="1234", # <-- Pon tu clave real aquí
        database="ruseta_db",
        cursorclass=pymysql.cursors.DictCursor
    )

@app.get("/")
def estado_servidor():
    return {"mensaje": "Servidor de Ruseta en línea y esperando conexiones"}

# Endpoint para enviar las rutas al mapa
@app.get("/api/rutas")
def obtener_rutas():
    try:
        conexion = conectar_bd()
        with conexion.cursor() as cursor:
            # Consultamos las rutas y fingimos unas coordenadas de origen/destino temporales
            # (Más adelante las cruzaremos con la tabla de comunas real)
            sql = "SELECT id, nombre_ruta FROM rutas"
            cursor.execute(sql)
            rutas_db = cursor.fetchall()
            
        conexion.close()
        return {"estado": "exito", "rutas": rutas_db}
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}