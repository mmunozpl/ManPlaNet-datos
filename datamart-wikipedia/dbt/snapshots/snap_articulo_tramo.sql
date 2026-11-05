{% snapshot snap_articulo_tramo %}
{{ config(
    target_schema='marts',
    unique_key='articulo_id',
    strategy='check',
    check_cols=['tramo']
) }}

-- dimensión con historia (SCD2): cada vez que el tramo de un artículo
-- cambia, dbt cierra la fila vigente (dbt_valid_to) y abre otra
select * from {{ ref('int_articulo_tramo') }}

{% endsnapshot %}
