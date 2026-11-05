{{ config(materialized='view') }}

-- la fuente con los nombres y los tipos del DataMart; el espacio de nombres
-- se reconoce contra la lista de los que existen en es.wikipedia, para no
-- tomar por espacio cualquier título con dos puntos
with crudo as (
    select proyecto, acceso, fecha, articulo as titulo, visitas, posicion, cargado_en
    from {{ source('crudo', 'visualizaciones_top') }}
),
con_espacio as (
    select c.*,
           case when position(':' in c.titulo) > 0 then split_part(c.titulo, ':', 1) end as posible_espacio
    from crudo c
)
select
    ce.proyecto,
    ce.acceso,
    ce.fecha,
    ce.titulo,
    coalesce(en.espacio, 'Principal') as espacio_nombres,
    en.espacio is null as es_articulo,
    ce.visitas,
    ce.posicion,
    ce.cargado_en
from con_espacio ce
left join {{ ref('espacios_nombres') }} en on en.espacio = ce.posible_espacio
