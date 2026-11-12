import json
import math
import os

# Fórmula de Haversine para medir la distancia real en kilómetros entre dos coordenadas
def calcular_distancia(lat1, lon1, lat2, lon2):
    R = 6371.0  # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Función para sumar la distancia de todos los puntos de una ruta
def longitud_ruta(coordenadas):
    distancia_total = 0.0
    for i in range(len(coordenadas) - 1):
        # GeoJSON guarda las coordenadas como [longitud, latitud]
        lon1, lat1 = coordenadas[i]
        lon2, lat2 = coordenadas[i + 1]
        distancia_total += calcular_distancia(lat1, lon1, lat2, lon2)
    return distancia_total

def limpiar_geojson():
    ruta_entrada = os.path.join('datos', 'export.geojson')
    ruta_salida = os.path.join('datos', 'rutas_limpias.geojson')

    print("Abriendo archivo original...")
    with open(ruta_entrada, 'r', encoding='utf-8') as f:
        datos = json.load(f)

    rutas_validas = []
    rutas_descartadas = 0

    print("Midiendo rutas...")
    for feature in datos.get('features', []):
        geometria = feature.get('geometry', {})
        tipo = geometria.get('type')
        coordenadas = geometria.get('coordinates', [])

        longitud_total = 0.0

        if tipo == 'LineString':
            longitud_total = longitud_ruta(coordenadas)
        elif tipo == 'MultiLineString':
            # Si la ruta está dividida en varios segmentos, los sumamos todos
            for segmento in coordenadas:
                longitud_total += longitud_ruta(segmento)

        # Filtro: Solo guardamos las rutas que midan 3 km o más
        if longitud_total >= 3.0:
            # Le inyectamos la longitud calculada a las propiedades por si nos sirve luego
            feature['properties']['longitud_km'] = round(longitud_total, 2)
            rutas_validas.append(feature)
        else:
            rutas_descartadas += 1

    # Actualizamos el JSON solo con las rutas buenas
    datos['features'] = rutas_validas

    # Guardamos el nuevo archivo
    with open(ruta_salida, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print("-" * 30)
    print("¡Limpieza completada!")
    print(f"Rutas válidas guardadas (>= 3km): {len(rutas_validas)}")
    print(f"Tramos cortos eliminados: {rutas_descartadas}")
    print(f"Archivo generado: {ruta_salida}")

if __name__ == '__main__':
    limpiar_geojson()