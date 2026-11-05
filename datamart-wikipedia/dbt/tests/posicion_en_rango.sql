-- la posición viene de una lista de mil: fuera de 1 a 1000 es un error de
-- carga, y las visitas nunca son negativas
select *
from {{ ref('hechos_visualizaciones') }}
where posicion < 1 or posicion > 1000 or visitas < 0
