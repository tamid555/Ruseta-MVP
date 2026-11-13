import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pymysql
from dotenv import load_dotenv

from utilidades import distanciaMetros

load_dotenv()

PASO_METROS = 40  # distancia máxima entre puntos guardados

# --- Pegar los tramos rectos a las calles (usa el servicio de rutas OSRM, basado en OpenStreetMap) ---
UMBRAL_HUECO_M = 200      # si dos puntos seguidos están a más de esto, se busca el camino real por calles
RAZON_MAXIMA = 4          # si el camino por calles mide más de 4 veces la recta, algo raro pasó: se deja la recta
PAUSA_OSRM_S = float(os.getenv("OSRM_PAUSA", "1.1"))   # el servidor público pide máximo 1 consulta por segundo
URL_OSRM = os.getenv("OSRM_URL", "https://router.project-osrm.org")
ARCHIVO_CACHE = os.path.join("datos", "cache_osrm.json")

usarCalles = True         # se apaga con --sin-calles
filtroSolo = None         # se llena con --solo
filtroOmitir = []         # se llena con --omitir
cacheOsrm = {}            # {"lat,lng;lat,lng": camino}: así no se repiten consultas
fallosSeguidos = 0        # si el servicio no responde varias veces seguidas, se deja de intentar


def distanciaPuntos(p1, p2):
    return distanciaMetros(p1[0], p1[1], p2[0], p2[1])


def extraerTramos(relacion):
    """Saca de la relación de OSM los tramos de calle (ways) en el orden en que vienen."""
    tramos = []
    for miembro in relacion.get("members", []):
        if miembro.get("type") != "way" or miembro.get("role") not in ("", "forward", "backward"):
            continue
        geometria = miembro.get("geometry") or []
        tramo = [(p["lat"], p["lon"]) for p in geometria if p]
        if len(tramo) >= 2:
            tramos.append(tramo)
    return tramos


def unirTramos(tramos):
    """Une los tramos en una sola línea, volteando los que vienen al revés.
    Devuelve (línea, saltos): 'saltos' son las uniones con un hueco de más de 100 m."""
    if not tramos:
        return [], 0
    if len(tramos) > 1:
        a, b = tramos[0], tramos[1]
        distFin = min(distanciaPuntos(a[-1], b[0]), distanciaPuntos(a[-1], b[-1]))
        distIni = min(distanciaPuntos(a[0], b[0]), distanciaPuntos(a[0], b[-1]))
        if distIni < distFin:
            a.reverse()
    linea = []
    saltos = 0
    for tramo in tramos:
        if linea:
            if distanciaPuntos(linea[-1], tramo[0]) > distanciaPuntos(linea[-1], tramo[-1]):
                tramo = tramo[::-1]
            if distanciaPuntos(linea[-1], tramo[0]) > 100:
                saltos += 1
            if tramo[0] == linea[-1]:
                tramo = tramo[1:]
        linea.extend(tramo)
    return linea, saltos


def densificar(linea, paso=PASO_METROS):
    """Agrega puntos intermedios para que no haya huecos mayores a 'paso' metros."""
    if not linea:
        return []
    salida = [linea[0]]
    for (lat1, lng1), (lat2, lng2) in zip(linea, linea[1:]):
        distancia = distanciaMetros(lat1, lng1, lat2, lng2)
        partes = max(1, int(distancia // paso))
        for i in range(1, partes + 1):
            f = i / partes
            salida.append((lat1 + (lat2 - lat1) * f, lng1 + (lng2 - lng1) * f))
    return salida


def cargarCache():
    global cacheOsrm
    if os.path.exists(ARCHIVO_CACHE):
        with open(ARCHIVO_CACHE, encoding="utf-8") as archivo:
            cacheOsrm = json.load(archivo)


def guardarCache():
    with open(ARCHIVO_CACHE, "w", encoding="utf-8") as archivo:
        json.dump(cacheOsrm, archivo)


def longitudCamino(camino):
    return sum(distanciaPuntos(a, b) for a, b in zip(camino, camino[1:]))


def caminoPorCalles(p1, p2):
    """Camino real por calles entre dos puntos (lista de (lat, lng)), o None si no se pudo."""
    global fallosSeguidos
    clave = f"{p1[0]:.6f},{p1[1]:.6f};{p2[0]:.6f},{p2[1]:.6f}"
    if clave in cacheOsrm:
        return cacheOsrm[clave] and [tuple(p) for p in cacheOsrm[clave]]
    if fallosSeguidos >= 3:
        return None
    url = (f"{URL_OSRM}/route/v1/driving/{p1[1]:.6f},{p1[0]:.6f};{p2[1]:.6f},{p2[0]:.6f}"
           "?overview=full&geometries=geojson")
    datos = None
    ultimoError = ""
    for intento in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as respuesta:
                datos = json.load(respuesta)
            break
        except urllib.error.HTTPError as error:
            if error.code == 400:               # OSRM: no encontró calle cerca de uno de los puntos
                cacheOsrm[clave] = None
                return None
            ultimoError = str(error)
        except Exception as error:
            ultimoError = str(error)
        time.sleep(5 * (intento + 1))           # esperar y reintentar
    if datos is None:
        fallosSeguidos += 1
        print(f"   aviso: el servicio de calles no respondió ({ultimoError}); se deja la línea recta")
        return None
    fallosSeguidos = 0
    time.sleep(PAUSA_OSRM_S)
    camino = None
    if datos.get("code") == "Ok" and datos.get("routes"):
        camino = [(lat, lng) for lng, lat in datos["routes"][0]["geometry"]["coordinates"]]
    cacheOsrm[clave] = camino
    return camino


def pegarACalles(linea):
    """Donde dos puntos seguidos están muy separados (hueco en OpenStreetMap), cambia la recta por el camino por calles.
    Devuelve (línea nueva, cuántos tramos se arreglaron)."""
    huecos = sum(1 for a, b in zip(linea, linea[1:]) if distanciaPuntos(a, b) > UMBRAL_HUECO_M)
    if huecos == 0:
        return linea, 0
    print(f"   {huecos} tramos rectos largos: buscando el camino por calles...")
    resultado = [linea[0]]
    pegados = 0
    for a, b in zip(linea, linea[1:]):
        recta = distanciaPuntos(a, b)
        if recta > UMBRAL_HUECO_M:
            camino = caminoPorCalles(a, b)
            if camino and len(camino) >= 2 and longitudCamino(camino) <= RAZON_MAXIMA * recta:
                resultado.extend(camino)
                pegados += 1
        resultado.append(b)
    guardarCache()
    return resultado, pegados


def crearRuta(osmId, etiquetas, tramos):
    referencia = etiquetas.get("ref", "")
    nombre = etiquetas.get("name") or f"Ruta {referencia or osmId}"
    if filtroSolo and filtroSolo.lower() not in nombre.lower():
        return None
    if any(texto.lower() in nombre.lower() for texto in filtroOmitir):
        return None
    linea, saltos = unirTramos(tramos)
    if len(linea) < 2:
        return None
    print(f"Procesando: {nombre}")
    huecos = 0
    if usarCalles:
        linea, huecos = pegarACalles(linea)
    return {"osmId": osmId, "nombre": nombre[:100], "ref": referencia[:20],
            "puntos": densificar(linea), "saltos": saltos, "huecos": huecos}


def leerRutasOsmJson(datos):
    """Formato 'raw OSM' de Overpass (con 'elements' y 'out geom')."""
    rutas = []
    for elemento in datos.get("elements", []):
        etiquetas = elemento.get("tags", {})
        if elemento.get("type") != "relation" or etiquetas.get("route") not in ("bus", "minibus"):
            continue
        ruta = crearRuta(elemento["id"], etiquetas, extraerTramos(elemento))
        if ruta:
            rutas.append(ruta)
    return rutas


def leerRutasGeoJson(datos):
    """Formato GeoJSON que exporta overpass-turbo (con 'features')."""
    rutas = []
    for feature in datos.get("features", []):
        propiedades = feature.get("properties", {})
        identificador = str(feature.get("id", ""))
        geometria = feature.get("geometry") or {}
        if not identificador.startswith("relation/") or propiedades.get("route") not in ("bus", "minibus"):
            continue
        if geometria.get("type") == "MultiLineString":
            lineas = geometria["coordinates"]
        elif geometria.get("type") == "LineString":
            lineas = [geometria["coordinates"]]
        else:
            continue
        # GeoJSON guarda [longitud, latitud]; nosotros trabajamos como (latitud, longitud)
        tramos = [[(punto[1], punto[0]) for punto in linea] for linea in lineas if len(linea) >= 2]
        ruta = crearRuta(int(identificador.split("/")[1]), propiedades, tramos)
        if ruta:
            rutas.append(ruta)
    return rutas


def leerRutas(rutaArchivo):
    with open(rutaArchivo, encoding="utf-8") as archivo:
        datos = json.load(archivo)
    if "features" in datos:
        return leerRutasGeoJson(datos)
    return leerRutasOsmJson(datos)


def guardarRutas(rutas):
    conexion = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conexion.cursor() as cursor:
            for ruta in rutas:
                cursor.execute("SELECT id FROM rutas WHERE osm_id = %s", (ruta["osmId"],))
                existente = cursor.fetchone()
                if existente:
                    rutaId = existente["id"]
                    cursor.execute("UPDATE rutas SET nombre_ruta = %s, ref = %s WHERE id = %s",
                                   (ruta["nombre"], ruta["ref"], rutaId))
                    cursor.execute("DELETE FROM ruta_puntos WHERE ruta_id = %s", (rutaId,))
                else:
                    cursor.execute("INSERT INTO rutas (nombre_ruta, osm_id, ref) VALUES (%s, %s, %s)",
                                   (ruta["nombre"], ruta["osmId"], ruta["ref"]))
                    rutaId = cursor.lastrowid
                filas = [(rutaId, orden, lat, lng) for orden, (lat, lng) in enumerate(ruta["puntos"])]
                cursor.executemany(
                    "INSERT INTO ruta_puntos (ruta_id, orden, latitud, longitud) VALUES (%s, %s, %s, %s)", filas)
                print(f"OK  {ruta['nombre']}  ({len(filas)} puntos, {ruta['saltos']} saltos, {ruta['huecos']} tramos pegados a calles)")
        conexion.commit()
    finally:
        conexion.close()


if __name__ == "__main__":
    analizador = argparse.ArgumentParser(description="Carga rutas de bus desde un GeoJSON de Overpass a MySQL")
    analizador.add_argument("archivo", nargs="?", default="datos/export.geojson")
    analizador.add_argument("--sin-calles", action="store_true", help="no pegar los tramos rectos a las calles")
    analizador.add_argument("--solo", help="cargar solo las rutas cuyo nombre contenga este texto")
    analizador.add_argument("--omitir", action="append", default=[],
                            help="omitir las rutas cuyo nombre contenga este texto (se puede repetir)")
    opciones = analizador.parse_args()
    usarCalles = not opciones.sin_calles
    filtroSolo = opciones.solo
    filtroOmitir = opciones.omitir
    cargarCache()

    rutas = leerRutas(opciones.archivo)
    if not rutas:
        print("No se encontró ninguna ruta con geometría. Revisa el archivo exportado de Overpass.")
        sys.exit(1)
    print(f"Rutas encontradas: {len(rutas)}")
    guardarRutas(rutas)