CREATE DATABASE IF NOT EXISTS ruseta_db;
USE ruseta_db;

CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(100) NULL UNIQUE,      -- Es NULL si entra como invitado
    password_hash VARCHAR(255) NULL,     -- Es NULL si entra como invitado
    es_invitado BOOLEAN DEFAULT FALSE,   -- Identifica si es un usuario temporal
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comunas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    numero_comuna INT NOT NULL UNIQUE
);

CREATE TABLE rutas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre_ruta VARCHAR(100) NOT NULL,    -- Ej: "Ruta 8 - Los Patios a Centro"
    comuna_origen_id INT,
    comuna_destino_id INT,
    FOREIGN KEY (comuna_origen_id) REFERENCES comunas(id),
    FOREIGN KEY (comuna_destino_id) REFERENCES comunas(id)
);

CREATE TABLE busetas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    placa VARCHAR(20) NOT NULL UNIQUE,
    ruta_id INT NOT NULL,
    latitud DECIMAL(10, 8) NULL,          -- Coordenada GPS actual (Norte/Sur)
    longitud DECIMAL(11, 8) NULL,         -- Coordenada GPS actual (Este/Oeste)
    ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (ruta_id) REFERENCES rutas(id)
);