{{ config(severity='warn') }}

-- entre el primer y el último día cargados no debería faltar ninguno; la
-- API tiene días sin datos, y este test los saca a la luz (avisa, no
-- detiene: el hueco está en la fuente, no en la carga)
with cargados as (
    select distinct f.fecha
    from {{ ref('hechos_visualizaciones') }} h
    join {{ ref('dim_fecha') }} f on f.fecha_id = h.fecha_id
    join {{ ref('dim_acceso') }} a on a.acceso_id = h.acceso_id
    where a.acceso = 'all-access'
),
rango as (
    select min(fecha) as desde, max(fecha) as hasta from cargados
)
select f.fecha as dia_sin_datos
from {{ ref('dim_fecha') }} f
cross join rango r
left join cargados c on c.fecha = f.fecha
where f.fecha between r.desde and r.hasta and c.fecha is null
order by 1
