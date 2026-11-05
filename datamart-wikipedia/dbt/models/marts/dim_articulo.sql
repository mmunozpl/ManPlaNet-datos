{{ config(
    materialized='incremental',
    unique_key='articulo_id',
    incremental_strategy='merge',
    merge_exclude_columns=['primera_fecha_vista']
) }}

-- la dimensión de artículo crece con cada carga: entra lo nuevo y se
-- actualiza la última fecha vista; la primera fecha vista no se pisa en
-- el merge (merge_exclude_columns), porque en una carga incremental solo
-- se ven las fechas nuevas y el mínimo saldría mal
with vistos as (
    select titulo, espacio_nombres, es_articulo,
           min(fecha) as primera_fecha_vista, max(fecha) as ultima_fecha_vista
    from {{ ref('stg_visualizaciones') }}
    {% if is_incremental() %}
    where fecha > (select coalesce(max(ultima_fecha_vista), '1900-01-01'::date) from {{ this }})
    {% endif %}
    group by 1, 2, 3
)
select
    md5(titulo)                as articulo_id,
    titulo,
    replace(titulo, '_', ' ')  as titulo_legible,
    espacio_nombres,
    es_articulo,
    primera_fecha_vista,
    ultima_fecha_vista
from vistos
