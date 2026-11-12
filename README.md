# Ruseta

App web para encontrar qué bus tomar en Cúcuta.

## Puesta en marcha (computador nuevo)
1. git pull
2. Base de datos: abrir MySQL Workbench, pegar todo el contenido de
   database/cambios_base_de_datos.txt y ejecutarlo (primer rayo).
   Si ya tienes la base, ejecutar solo los cambios que te falten.
3. Crear backend/.env con estas líneas:
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=tu_clave_de_mysql
   DB_NAME=ruseta_db
   JWT_SECRET=un_texto_largo
   (el JWT_SECRET se genera con: python -c "import secrets; print(secrets.token_hex(32))")
4. En la carpeta backend: python -m pip install -r requirements.txt
5. Cargar las rutas: python importar_osm.py datos/export.geojson
6. Encender el servidor: uvicorn main:app --reload (al terminar no olvide cerrarlo haciendo Ctrl + C en la Terminal)
7. Abrir frontend/index.html con Live Server y crear una cuenta en registro.html.