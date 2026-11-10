# Un SGSI medido: riesgos, controles, auditoría, indicadores y continuidad sobre tres laboratorios publicados

Medición que acompaña a la entrada «Un SGSI puesto a prueba» de manpla.net. Monta un sistema de gestión de la seguridad de la
información (SGSI) con la estructura de ISO/IEC 27001:2022 sobre tres
sistemas que este repositorio ya publica con su código y sus mediciones: el
laboratorio de accesos privilegiados (`pam-minimo/`), el DataMart de Kimball
(`datamart-wikipedia/`) y la demo del RAG sintético (`rag-sintetico/`), que
es el sistema de inteligencia artificial del alcance y se evalúa contra
ISO/IEC 27090:2026. Todo lo que el SGSI afirma sale de un fichero de este
repositorio y se vuelve a calcular con `generar.py`.

Los datos de negocio de los tres sistemas no son personales; los registros
operativos llevan identidades ficticias y direcciones de la red interna del
laboratorio. Nada de aquí describe
la infraestructura del autor: el alcance son los laboratorios publicados, no
el equipo en que corren ni las cuentas de las plataformas.

## Reproducir

```bash
cd data && uv sync --frozen
cd sgsi-medido
uv run python generar.py           # mapa de marcos + riesgos + auditoría + KPI + resúmenes
SIMULACRO_LOG=/tmp/simulacro CACHE_CRUDO=/ruta/a/la/cache bash simulacro.sh   # opcional: ~20 min, exige Docker
```

`generar.py` descarga (o lee de `descargas/`) el núcleo de NIST CSF 2.0 con
sus referencias informativas, el texto consolidado del ENS en el BOE, la NIS2
y DORA en EUR-Lex y el Libro II de MAGERIT v3; clona el repositorio público de
la demo del RAG para auditar su configuración; y encadena `riesgo.py`,
`auditoria.py` y `kpis.py`. El simulacro de continuidad (`simulacro.sh`)
destruye y reconstruye los dos laboratorios en Docker y rehace el índice del
RAG desde la semilla; es el único paso que no es puro cálculo y por eso
`simulacro.csv` viaja ya calculado.

## Ficheros

| Fichero | Qué contiene | Lo escribe |
|---|---|---|
| `fuentes/politica.md` | la política de seguridad: alcance, compromisos, roles y marcos | el autor |
| `fuentes/activos.csv` | 22 activos de los tres sistemas con su valor en cinco dimensiones (D, I, C, A, T; 0 a 10) | el autor |
| `fuentes/riesgos_entrada.csv` | 55 pares activo-amenaza con frecuencia, degradación, salvaguardas y eficacia | el autor |
| `fuentes/amenazas_27090.csv` | las nueve amenazas de la cláusula 6 y el anexo B de ISO/IEC 27090:2026, como catálogo añadido a MAGERIT | el autor |
| `fuentes/soa_laboratorios.csv` | la declaración de aplicabilidad: 93 controles del anexo A con aplica, estado, justificación, evidencia y medida ENS | el autor |
| `fuentes/soa_27090.csv` | la declaración por amenaza de IA: aplica, estado, salvaguarda, evidencia, controles 27002, ENS y CSF | el autor |
| `fuentes/plan_director.csv` | 17 iniciativas con origen, controles, prioridad, trimestre, horas y KPI | el autor |
| `fuentes/proveedores.csv` | el inventario de proveedores (imágenes, bibliotecas, plataformas, fuentes de datos) | el autor |
| `fuentes/serie_27000.csv` | las normas de la serie 27000 y hermanas que usa el SGSI, con su edición vigente y su papel | el autor (ediciones verificadas en noviembre de 2026) |
| `fuentes/mapa_ens_csf.csv`, `fuentes/mapa_nis2_dora_csf.csv`, `fuentes/iso27001_anexoA.csv`, `fuentes/pci_dss_v401.csv` | las lecturas propias que alimentan el mapa de marcos | el autor |
| `csf_core.csv`, `csf_referencias.csv` | las 106 subcategorías del CSF 2.0 y sus referencias informativas (SP 800-53, ISO/IEC 27001, PCI DSS…) | `generar.py` desde el CPRT del NIST |
| `ens_medidas.csv`, `nis2_art21.csv`, `dora_cap2.csv`, `magerit_amenazas.csv` | las 73 medidas del ENS, las diez letras del 21.2 de la NIS2, los artículos 5 a 16 de DORA y las amenazas de MAGERIT | `generar.py` desde el BOE, EUR-Lex y el PAe |
| `mapa_controles.csv`, `cobertura_csf.csv`, `comparativa_pares.csv`, `iso_sin_csf.csv`, `ens_iso_candidatos.csv`, `exigencias_por_marco.csv` | el mapa de los seis marcos sobre las 22 categorías del CSF y sus comparativas (Jaccard) | `generar.py` |
| `riesgos.csv`, `riesgos_resumen.csv` | cada riesgo con impacto, frecuencia, riesgo, salvaguardas, eficacia, residual y si supera el apetito; resumen por sistema | `riesgo.py` |
| `auditoria.csv`, `auditoria_resumen.csv`, `auditoria_marcos.csv` | 91 comprobaciones con resultado, evidencia y referencia en siete marcos; resúmenes por sistema y por marco | `auditoria.py` |
| `kpis.csv`, `okr_resumen.csv` | los indicadores por objetivo y resultado clave, con valor, meta, fuente y periodicidad | `kpis.py` |
| `simulacro.csv` | las fases del simulacro de continuidad con su instante, sus segundos y su comprobación | `simulacro.sh` |
| `soa_resumen.csv`, `soa_controles.csv`, `soa_27090_detalle.csv`, `plan_director_resumen.csv` | resúmenes para las tablas de la entrada | `generar.py` |
| `INSTANTANEA.md`, `INSTANTANEA_mapa.md` | las cifras del SGSI y del mapa, tal como las imprime el cuaderno | `generar.py` |
| `reproducir.ipynb` | cuaderno de lectura: la instantánea y las tablas principales | el autor |

## Lo que mide

- **El mapa de marcos**: qué categorías de NIST CSF 2.0 cubre cada marco
  (ISO/IEC 27001 anexo A, ENS, NIS2 21.2, DORA capítulo II, PCI DSS v4.0.1 y
  SP 800-53) y cuánto se solapan dos a dos. Las correspondencias con ISO,
  SP 800-53 y PCI son las del NIST; las del ENS, la NIS2 y DORA son lectura
  propia y están declaradas fila a fila.
- **Los riesgos**: método de MAGERIT v3 simplificado (impacto = valor ×
  degradación; riesgo = impacto × frecuencia; residual = riesgo × (1 −
  eficacia)), con el catálogo de amenazas del Libro II y las nueve de ISO/IEC
  27090 para el sistema de IA, y un apetito declarado de 12 sobre 50.
- **La declaración de aplicabilidad**: los 93 controles del anexo A y las
  nueve amenazas y el anexo B de la 27090, cada uno con su estado y su evidencia en los
  ficheros de los laboratorios.
- **La auditoría interna**: 91 comprobaciones ejecutadas sobre los ficheros
  versionados (configuración, guiones, CSV de medición) y sobre la
  documentación del SGSI, cada una con su control en ISO/IEC 27001, ISO/IEC
  27090, el ENS, el CSF, la NIS2, DORA y PCI DSS.
- **Los indicadores**: cinco objetivos con sus resultados clave, calculados
  desde las mediciones publicadas, más siete indicadores de contexto sin meta.
- **La continuidad**: cada sistema destruido y reconstruido desde el código y
  su copia externa, con el tiempo real de recuperación (para contrastarlo con el objetivo RTO) y la comprobación de
  que los datos vuelven idénticos (integridad de la reconstrucción, que no es una
  medición del RPO), y lo que se pierde porque no tenía
  copia.

## Límites

- El SGSI cubre tres laboratorios de una persona: dirección, responsable de
  seguridad y responsable de cada sistema coinciden, y la auditoría es de
  primera parte. Lo que exigiría una certificación (revisión por la
  dirección, auditoría de tercera parte, procedimientos de incidentes y de
  continuidad aprobados) está en el plan director, no hecho.
- Las valoraciones de activos, frecuencias, degradaciones y eficacias son
  juicio del autor, declarado fila a fila para poder discutirlo; el método es
  el de MAGERIT, los números no vienen de ningún histórico de incidentes.
- Las correspondencias ENS → CSF y NIS2/DORA → CSF son lectura propia; las de
  ISO/IEC 27001, SP 800-53 y PCI DSS son las referencias informativas del
  NIST, que el propio NIST declara no exhaustivas.
- La NIS2, DORA y PCI DSS se usan como comparación: ninguno de los tres
  sistemas está sujeto a ellas. La ley española que transpone la NIS2 seguía
  sin publicarse en el BOE en la fecha de la medición.
- El simulacro reconstruye desde el código y las fuentes; no prueba una
  restauración desde copia de seguridad, porque los laboratorios no la tienen
  (es la primera iniciativa del plan).
