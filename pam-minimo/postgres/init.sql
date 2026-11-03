-- el objetivo de datos: la tabla 28193 del INE (Encuesta Anual de Estructura
-- Salarial: ganancia media anual por comunidad autónoma, ocupación, sexo y
-- año), descargada de su API y guardada en datos/. Datos reales, sin ninguna
-- persona. En el CSV del INE un signo «-» delante del dato marca que la
-- muestra tiene entre 100 y 500 observaciones; aquí se guarda como columna.
CREATE TABLE salarios (
    id                   serial PRIMARY KEY,
    comunidad            text NOT NULL,
    ocupacion            text NOT NULL,
    sexo                 text NOT NULL,
    periodo              integer NOT NULL,
    ganancia_media_anual numeric(10, 2) NOT NULL,
    muestra_pequena      boolean NOT NULL
);
CREATE TEMP TABLE bruto (
    comunidad text, ocupacion text, sexo text, periodo text, total text
);
COPY bruto FROM '/datos/ine_28193_salarios.csv'
    WITH (FORMAT csv, DELIMITER E'\t', HEADER true, ENCODING 'UTF8');
INSERT INTO salarios (comunidad, ocupacion, sexo, periodo,
                      ganancia_media_anual, muestra_pequena)
SELECT comunidad, ocupacion, sexo, periodo::integer,
       replace(replace(ltrim(total, '-'), '.', ''), ',', '.')::numeric,
       left(total, 1) = '-'
FROM bruto;
-- rol de solo lectura del que heredan las credenciales dinámicas de OpenBao
CREATE ROLE lectura_salarios NOLOGIN;
GRANT CONNECT ON DATABASE salarios TO lectura_salarios;
GRANT USAGE ON SCHEMA public TO lectura_salarios;
GRANT SELECT ON salarios TO lectura_salarios;
-- cuenta fija con la que entra el bastión; su contraseña la pone el guion de
-- inicio y se guarda en la bóveda, no en el bastión
CREATE ROLE bastion_lectura LOGIN IN ROLE lectura_salarios;
