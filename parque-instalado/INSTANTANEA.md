# Instantánea — el parque instalado

- Extracción: 16-09-2026.
- Catálogo de explotadas de CISA, versión 2026.09.14 (`https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json`). La edad es el año de alta menos el año del identificador CVE; es una cota inferior de la edad del fallo, porque el identificador se reserva en el año de asignación.
- Dispositivos de borde de red: los proveedores de la lista `BORDE` de `generar.py`, declarada y ampliable.
- Versiones de Windows en escritorio: StatCounter Global Stats (`https://gs.statcounter.com/windows-version-market-share/desktop/`), serie mensual descargada en CSV para el mundo y para España. Es una estimación por tráfico web, no un censo.

| año de alta | altas | 0 años | 1-4 | 5-9 | ≥10 | ≥5 años | borde de red | más antiguo |
|---|---|---|---|---|---|---|---|---|
| 2023 | 187 | 121 | 48 | 15 | 3 | 9.6 % | 32 (17.1 %) | CVE-2004-1464 (Cisco) |
| 2024 | 186 | 116 | 52 | 11 | 7 | 9.7 % | 39 (21.0 %) | CVE-2012-4792 (Microsoft) |
| 2025 | 245 | 151 | 64 | 21 | 9 | 12.2 % | 53 (21.6 %) | CVE-2007-0671 (Microsoft) |
| 2026 | 226 | 147 | 54 | 13 | 12 | 11.1 % | 46 (20.4 %) | CVE-2008-4128 (Cisco) |

Windows en escritorio, último mes de la serie:

- mundo, 2026-08: Windows 11 68.6 %, Windows 10 30.15 %, Windows 7 0.95 %
- espana, 2026-08: Windows 11 65.85 %, Windows 10 30.54 %, Windows 7 3.22 %

No interviene ningún dato de ninguna persona.
