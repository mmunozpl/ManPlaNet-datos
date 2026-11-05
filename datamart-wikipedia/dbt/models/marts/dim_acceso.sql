{{ config(materialized='table') }}

-- la dimensión de acceso viene de un seed: cuatro filas que no cambian
select acceso_id, acceso, canal, es_agregado, descripcion
from {{ ref('accesos') }}
