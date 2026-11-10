# Política de seguridad de la información del SGSI de los laboratorios

Versión 1.0, aprobada el 9 de noviembre de 2026 por quien dirige el alcance
(el autor de los laboratorios, que en este SGSI ocupa el papel de la
dirección). Se revisa cada año y después de cualquier incidente o cambio del
alcance.

## Alcance

El sistema de gestión cubre tres sistemas publicados con su código y sus
mediciones en el repositorio de datos de este sitio: el laboratorio de gestión
de accesos privilegiados (`pam-minimo`), el DataMart de Kimball sobre los
accesos a Wikipedia (`datamart-wikipedia`) y la demo del RAG sintético
(`rag-sintetico`), que es el sistema de inteligencia artificial del alcance.
Quedan fuera el equipo anfitrión, su red y las cuentas personales de las
plataformas que alojan el código, los datos y la demo. Los datos de negocio de los
tres sistemas no son personales; los registros operativos llevan identidades
ficticias de laboratorio y direcciones de la red interna, que con personas
reales serían datos personales.

## Compromisos

1. La seguridad se decide por riesgo: cada activo tiene su valor en cinco
   dimensiones, cada amenaza su frecuencia y su degradación, y cada riesgo
   residual por encima del apetito declarado (12 sobre 50) entra en el plan.
2. Cada control se declara: la declaración de aplicabilidad recorre los 93
   controles del anexo A de ISO/IEC 27001:2022 y las nueve amenazas de la
   cláusula 6 de ISO/IEC 27090:2026, y dice de cada uno si aplica, en qué
   estado está y con qué evidencia.
3. Lo que se afirma se mide: los indicadores salen de los ficheros de medición
   publicados, con su fórmula y su fuente, y la auditoría interna comprueba los
   controles sobre los ficheros versionados, no sobre declaraciones.
4. La continuidad se ensaya: al menos una vez al año se destruye cada sistema
   y se reconstruye desde lo versionado y su copia, midiendo el tiempo hasta el
   servicio y la pérdida de datos.
5. Los proveedores se conocen: toda imagen, biblioteca, plataforma y fuente de
   datos está en el inventario con su versión y su control.
6. Las no conformidades se tratan: cada hallazgo de la auditoría y cada riesgo
   sobre el apetito tiene su iniciativa en el plan director, con prioridad,
   trimestre y esfuerzo.

## Roles

- Dirección y responsable de seguridad: el autor. Aprueba la política, el
  apetito de riesgo y el plan; revisa el sistema una vez al año.
- Responsable de cada sistema: el autor, con la evidencia en el `LEEME.md` de
  cada laboratorio.
- Enlace con protección de datos: no procede mientras el alcance no trate
  datos personales; si lo hiciera, se nombraría antes del primer tratamiento y
  se estudiaría la adopción de ISO/IEC 27701:2025 como marco complementario.

## Marcos de referencia

ISO/IEC 27001:2022 (estructura y controles), ISO/IEC 27005:2022 con el
catálogo de MAGERIT v3 (riesgos), ISO/IEC 27031:2025 (continuidad TIC),
ISO/IEC 27035 (incidentes), ISO/IEC 27090:2026 (sistema de IA), el Esquema
Nacional de Seguridad (RD 311/2022) y NIST CSF 2.0 con SP 800-53 Rev. 5 como
lenguas comunes, y la NIS2, DORA y PCI DSS v4.0.1 como comparación de lo que
exigiría cada régimen si el alcance les estuviera sujeto.
