{{ config(materialized='view') }}

-- el tramo habitual de cada artículo en los últimos 30 días cargados (por
-- la mediana de su posición en all-access): es el atributo que cambia
-- despacio y que la snapshot con historia (SCD2) registra cuando cambia.
-- fecha_datos es el último día cargado al observarlo: la fecha de negocio
-- de cada versión, porque dbt_valid_from es la hora en que corrió la
-- snapshot (en un relleno histórico, minutos; en producción, cada mes)
with ultimo as (
    select max(f.fecha) as fecha_max
    from {{ ref('hechos_visualizaciones') }} h
    join {{ ref('dim_fecha') }} f on f.fecha_id = h.fecha_id
),
ventana as (
    select h.articulo_id, h.posicion
    from {{ ref('hechos_visualizaciones') }} h
    join {{ ref('dim_fecha') }} f on f.fecha_id = h.fecha_id
    join {{ ref('dim_acceso') }} a on a.acceso_id = h.acceso_id
    cross join ultimo u
    where a.acceso = 'all-access' and f.fecha > u.fecha_max - interval '30 days'
),
mediana as (
    select articulo_id,
           percentile_cont(0.5) within group (order by posicion) as posicion_mediana,
           count(*) as dias_en_ventana
    from ventana
    group by 1
)
select m.articulo_id,
       m.posicion_mediana,
       m.dias_en_ventana,
       case when m.posicion_mediana <= 10 then 'top 10'
            when m.posicion_mediana <= 100 then 'top 100'
            else 'top 1000' end as tramo,
       u.fecha_max as fecha_datos
from mediana m
cross join ultimo u
