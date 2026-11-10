# Un SGSI medido: instantánea

Alcance: tres sistemas publicados con su código y sus mediciones (pam-minimo, datamart-wikipedia y rag-sintetico, este último el sistema de IA). Ninguno trata datos personales. Política en fuentes/politica.md.

## Mapa de marcos

Categorías de NIST CSF 2.0 (22) que cubre cada marco: ISO/IEC 27001:2022 (anexo A) 22; ENS (RD 311/2022) 21; NIST CSF 2.0 22; NIST SP 800-53 Rev. 5 22; NIS2 16; DORA 19; PCI DSS v4.0 22.
Pares con menor solape (Jaccard): NIS2 / DORA 0.591; ENS (RD 311/2022) / NIS2 0.682; ISO/IEC 27001:2022 (anexo A) / NIS2 0.727.

## Riesgos (MAGERIT v3 simplificado, apetito 12 sobre 50)

- pam-minimo: 28 riesgos; promedio 16.7 → residual 7.6 (54.4 % menos); 7 sobre el apetito
- datamart-wikipedia: 19 riesgos; promedio 15.7 → residual 7.0 (55.2 % menos); 1 sobre el apetito
- rag-sintetico: 8 riesgos; promedio 12.8 → residual 4.8 (62.6 % menos); 1 sobre el apetito
- total: 55 riesgos; promedio 15.8 → residual 7.0 (55.6 % menos); 9 sobre el apetito

## Declaración de aplicabilidad (anexo A de ISO/IEC 27001:2022)

93 controles: 71 aplican (24 implantados, 39 parciales, 8 sin implantar) y 22 no aplican.

## Sistema de IA (ISO/IEC 27090:2026)

10 elementos declarados (las nueve amenazas de la cláusula 6 y el anexo B): 3 aplican (2 implantadas, 1 parciales); mitigaciones de ATLAS asociadas a las aplicables: 42.

## Auditoría interna

- pam-minimo: 31 comprobaciones; 24 conformes, 4 no conformes, 3 observaciones; conformidad 85.7 %
- datamart-wikipedia: 27 comprobaciones; 19 conformes, 5 no conformes, 3 observaciones; conformidad 79.2 %
- rag-sintetico: 13 comprobaciones; 11 conformes, 2 no conformes, 0 observaciones; conformidad 84.6 %
- sgsi: 20 comprobaciones; 12 conformes, 4 no conformes, 4 observaciones; conformidad 75.0 %
- total: 91 comprobaciones; 66 conformes, 15 no conformes, 10 observaciones; conformidad 81.5 %
- por marco: ISO/IEC 27001:2022 91 comprobaciones y 59 referencias; ISO/IEC 27090:2026 14 comprobaciones y 9 referencias; ENS (RD 311/2022) 87 comprobaciones y 32 referencias; NIST CSF 2.0 91 comprobaciones y 44 referencias; NIS2 art. 21.2 76 comprobaciones y 13 referencias; DORA 82 comprobaciones y 20 referencias; PCI DSS v4.0.1 72 comprobaciones y 18 referencias

## Indicadores (OKR)

- O1 Los accesos privilegiados están bajo control: 4 cumplen, 1 no cumplen, 0 sin meta
- O2 Los datos son íntegros y recuperables: 7 cumplen, 2 no cumplen, 0 sin meta
- O3 Las vulnerabilidades y la cadena de suministro se tratan en plazo: 1 cumplen, 2 no cumplen, 0 sin meta
- O4 El cumplimiento se mide, no se declara: 2 cumplen, 3 no cumplen, 0 sin meta
- O5 El sistema de IA está evaluado frente a ISO/IEC 27090: 2 cumplen, 2 no cumplen, 0 sin meta
- C Contexto del sector (sin meta propia): 0 cumplen, 0 no cumplen, 7 sin meta

## Simulacro de continuidad (tiempo real de recuperación, segundos)

- pam-minimo: 34 s
- datamart-wikipedia: 951 s
- rag-sintetico: 2 s

## Plan director

- alta: 4 iniciativas, 72 horas (2027-T1 2027-T2)
- media: 8 iniciativas, 128 horas (2027-T2 2027-T3 2027-T4)
- baja: 5 iniciativas, 55 horas (2027-T1 2027-T2 2027-T3 2027-T4)

Serie ISO/IEC 27000 y normas hermanas identificadas: 24, con su edición vigente en fuentes/serie_27000.csv.
