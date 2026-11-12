import json
import os
import sys

import pymysql
from dotenv import load_dotenv

from utilidades import distanciaMetros

load_dotenv()

PASO_METROS = 40  # distancia máxima entre puntos guardados


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


def crearRuta(osmId, etiquetas, tramos):
    linea, saltos = unirTramos(tramos)
    if len(linea) < 2:
        return None
    referencia = etiquetas.get("ref", "")
    nombre = etiquetas.get("name") or f"Ruta {referencia or osmId}"
    return {"osmId": osmId, "nombre": nombre[:100], "ref": referencia[:20],
            "puntos": densificar(linea), "saltos": saltos}


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
                print(f"OK  {ruta['nombre']}  ({len(filas)} puntos, {ruta['saltos']} saltos)")
        conexion.commit()
    finally:
        conexion.close()


if __name__ == "__main__":
    rutaArchivo = sys.argv[1] if len(sys.argv) > 1 else "datos/export.geojson"
    rutas = leerRutas(rutaArchivo)
    if not rutas:
        print("No se encontró ninguna ruta con geometría. Revisa el archivo exportado de Overpass.")
        sys.exit(1)
    print(f"Rutas encontradas: {len(rutas)}")
    guardarRutas(rutas)