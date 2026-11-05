{{ config(materialized='table') }}

-- snapshot periódica: una fila por artículo, mes y acceso con las medidas
-- del mes entero; se reconstruye cada vez porque un mes cambia hasta que
-- se carga su último día
with mensual as (
    select f.anio_mes, h.articulo_id, h.acceso_id,
           sum(h.visitas)               as visitas_mes,
           count(*)                     as dias_en_top,
           round(avg(h.posicion), 1)    as posicion_media,
           min(h.posicion)              as mejor_posicion
    from {{ ref('hechos_visualizaciones') }} h
    join {{ ref('dim_fecha') }} f on f.fecha_id = h.fecha_id
    group by 1, 2, 3
)
select *,
       rank() over (partition by anio_mes, acceso_id order by visitas_mes desc) as posicion_mes
from mensual
