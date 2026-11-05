{{ config(materialized='table') }}

-- la dimensión de fecha, generada: un día por fila desde el inicio de la
-- carga hasta el final de 2026, con los atributos que piden las consultas
with dias as (
    select d::date as fecha
    from generate_series('2024-01-01'::date, '2026-12-31'::date, interval '1 day') as d
)
select
    to_char(fecha, 'YYYYMMDD')::int               as fecha_id,
    fecha,
    extract(year from fecha)::int                  as anio,
    extract(month from fecha)::int                 as mes,
    (array['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
           'septiembre','octubre','noviembre','diciembre'])[extract(month from fecha)::int] as nombre_mes,
    to_char(fecha, 'YYYY-MM')                      as anio_mes,
    extract(quarter from fecha)::int               as trimestre,
    extract(week from fecha)::int                  as semana_iso,
    extract(day from fecha)::int                   as dia,
    extract(isodow from fecha)::int                as dia_semana_iso,
    (array['lunes','martes','miércoles','jueves','viernes','sábado','domingo'])[extract(isodow from fecha)::int] as nombre_dia,
    extract(isodow from fecha) in (6, 7)           as es_fin_de_semana
from dias
