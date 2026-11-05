{{ config(
    materialized='incremental',
    unique_key=['fecha_id', 'articulo_id', 'acceso_id'],
    incremental_strategy=var('estrategia'),
    on_schema_change='fail',
    indexes=[
        {'columns': ['fecha_id']},
        {'columns': ['articulo_id']},
        {'columns': ['acceso_id', 'fecha_id']}
    ]
) }}

-- la tabla de hechos: una fila por artículo, día y tipo de acceso (el
-- grano), con las claves de las tres dimensiones y dos medidas. En cada
-- carga incremental se reprocesan los tres últimos días ya cargados, por si
-- la fuente los corrige; con append eso duplica, con delete+insert y merge no.
-- el corte se calcula desde la propia clave de fecha, sin ref() dentro del
-- condicional: dbt no infiere dependencias que solo aparecen ahí
select
    to_char(v.fecha, 'YYYYMMDD')::int as fecha_id,
    md5(v.titulo)                     as articulo_id,
    a.acceso_id,
    v.visitas,
    v.posicion
from {{ ref('stg_visualizaciones') }} v
join {{ ref('dim_acceso') }} a on a.acceso = v.acceso
{% if is_incremental() %}
where v.fecha >= (
    select coalesce(to_date(max(fecha_id)::text, 'YYYYMMDD'), '1900-01-01'::date) - interval '3 days'
    from {{ this }}
)
{% endif %}
