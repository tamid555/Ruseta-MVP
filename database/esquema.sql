CREATE DATABASE IF NOT EXISTS ruseta_db;
USE ruseta_db;

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL,
    email VARCHAR(50) NULL UNIQUE,      -- Es NULL si entra como invitado
    password_hash VARCHAR(255) NULL,     -- bcrypt genera 60 caracteres, por eso 255
    es_invitado BOOLEAN DEFAULT FALSE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comunas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    numero_comuna INT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS rutas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre_ruta VARCHAR(100) NOT NULL,
    osm_id BIGINT NULL UNIQUE,            -- Identificador de la ruta en OpenStreetMap
    ref VARCHAR(20) NULL,                 -- Número o código de la ruta
    comuna_origen_id INT,
    comuna_destino_id INT,
    FOREIGN KEY (comuna_origen_id) REFERENCES comunas(id),
    FOREIGN KEY (comuna_destino_id) REFERENCES comunas(id)
);

CREATE TABLE IF NOT EXISTS ruta_puntos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ruta_id INT NOT NULL,
    orden INT NOT NULL,                   -- Posición del punto dentro del recorrido
    latitud DECIMAL(10, 8) NOT NULL,
    longitud DECIMAL(11, 8) NOT NULL,
    FOREIGN KEY (ruta_id) REFERENCES rutas(id) ON DELETE CASCADE,
    INDEX idx_ruta_orden (ruta_id, orden)
);

CREATE TABLE IF NOT EXISTS busetas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    placa VARCHAR(20) NOT NULL UNIQUE,
    ruta_id INT NOT NULL,
    latitud DECIMAL(10, 8) NULL,          -- Coordenada GPS actual (Norte/Sur)
    longitud DECIMAL(11, 8) NULL,         -- Coordenada GPS actual (Este/Oeste)
    ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (ruta_id) REFERENCES rutas(id)
);