WITH celdas AS (
    SELECT treatment AS t, exposure AS e, count(*) AS n,
           sum(visit) AS v, sum(conversion) AS c
    FROM read_csv('criteo-research-uplift-v2.1.csv.gz')
    GROUP BY ALL
), grupos AS (
    SELECT sum(n) FILTER (WHERE t = 1) AS n1,
           sum(n) FILTER (WHERE t = 0) AS n0,
           sum(v) FILTER (WHERE t = 1) / n1 AS v1,
           sum(v) FILTER (WHERE t = 0) / n0 AS v0,
           sum(c) FILTER (WHERE t = 1) / n1 AS c1,
           sum(c) FILTER (WHERE t = 0) / n0 AS c0,
           sum(n) FILTER (WHERE e = 1) / n1 AS pi,
           sum(v) FILTER (WHERE e = 1) / sum(n) FILTER (WHERE e = 1) AS ve1,
           sum(v) FILTER (WHERE e = 0) / sum(n) FILTER (WHERE e = 0) AS ve0
    FROM celdas
)
SELECT n1, n0,
       v1 - v0 AS itt_visita,
       sqrt(v1 * (1 - v1) / n1 + v0 * (1 - v0) / n0) AS ee_visita,
       itt_visita - 1.959964 * ee_visita AS ic_inf_visita,
       itt_visita + 1.959964 * ee_visita AS ic_sup_visita,
       c1 - c0 AS itt_conversion,
       sqrt(c1 * (1 - c1) / n1 + c0 * (1 - c0) / n0) AS ee_conversion,
       ve1 - ve0 AS ingenua_visita,
       pi,
       itt_visita / pi AS efecto_expuestos_visita
FROM grupos
