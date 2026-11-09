import math

def distanciaMetros(lat1, lng1, lat2, lng2):
    """Distancia en metros entre dos coordenadas (fórmula de Haversine)."""
    radioTierra = 6371000
    fi1 = math.radians(lat1)
    fi2 = math.radians(lat2)
    deltaFi = math.radians(lat2 - lat1)
    deltaLambda = math.radians(lng2 - lng1)
    a = math.sin(deltaFi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(deltaLambda / 2) ** 2
    return 2 * radioTierra * math.asin(math.sqrt(a))