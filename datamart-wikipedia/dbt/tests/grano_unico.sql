-- el grano de la tabla de hechos: no puede haber dos filas para el mismo
-- artículo, día y acceso (con la estrategia append, este test falla)
select fecha_id, articulo_id, acceso_id, count(*) as filas
from {{ ref('hechos_visualizaciones') }}
group by 1, 2, 3
having count(*) > 1
