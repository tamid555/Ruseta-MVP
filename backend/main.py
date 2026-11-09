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

# Endpoint para enviar las rutas al mapa con puntos de origen y destino
@app.get("/api/rutas")
def obtener_rutas():
    try:
        conexion = conectar_bd()
        with conexion.cursor() as cursor:
            # Consultamos las rutas reales de la base de datos
            sql = "SELECT id, nombre_ruta FROM rutas"
            cursor.execute(sql)
            rutas_db = cursor.fetchall()
            
        conexion.close()
        
        # Asignamos coordenadas de origen y destino (Ejemplo en Cúcuta)
        # Esto simula un trayecto desde Los Patios (origen) hasta el Centro (destino)
        rutas_con_coordenadas = []
        for ruta in rutas_db:
            rutas_con_coordenadas.append({
                "id": ruta["id"],
                "nombre": ruta["nombre_ruta"],
                "origen": {"lat": 7.8285, "lng": -72.5042}, # Los Patios
                "destino": {"lat": 7.8939, "lng": -72.5078} # Centro Cúcuta
            })

        return {"estado": "exito", "rutas": rutas_con_coordenadas}
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}