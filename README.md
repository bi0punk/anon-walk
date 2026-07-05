# anon-walk

> Herramienta de mejora de anonimato que instala proxychains-ng y macchanger, configura proxychains y randomiza la dirección MAC de una interfaz de red periódicamente.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)

## Tabla de Contenidos

- [Características](#características)
- [Stack](#stack)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Uso](#uso)
- [Tests](#tests)
- [Configuración](#configuración)
- [CI](#ci)
- [Limitaciones / Roadmap](#limitaciones--roadmap)
- [Licencia](#licencia)

## Características

- Instalación automática de proxychains-ng y macchanger (apt/dnf/pacman)
- Configuración de `/etc/proxychains.conf` con backup automático
- Cambio periódico de MAC (intervalo configurable) usando macchanger o `ip link`
- Renovación de DHCP tras cada cambio de MAC (dhclient, dhcpcd, nmcli)
- Verificación de IP pública antes/después con/sin proxy
- Logging detallado con timestamps
- Soporte para múltiples modos de proxychains (strict/dynamic/random)

## Stack

- **Python 3.11+** — argparse, threading, subprocess, logging
- **bash** — paquetes del sistema (proxychains4, macchanger, curl, dhclient)

## Arquitectura

```
anon-walk/
├── .env.example
├── .github/workflows/ci.yml
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
├── requirements.txt
├── app.py                   # Script principal
└── tests/
    └── test_smoke.py
```

## Requisitos

- **Python 3.11+**
- **Ejecución como root** (sudo)
- Sistema Linux con `apt`, `dnf` o `pacman`
- Interfaz de red inalámbrica o cableada

## Instalación

```bash
git clone <repo-url>
cd anon-walk
# Sin dependencias Python externas (usa stdlib + system packages)
```

## Uso

### Ejemplo básico

```bash
sudo python app.py --interface wlan0 --interval 10 \
  --proxies "socks5 127.0.0.1 9050" --mode strict_chain \
  --proxy-dns --renew-dhcp --immediate
```

### Opciones

| Argumento         | Default                     | Descripción                                  |
| ----------------- | --------------------------- | -------------------------------------------- |
| `--interface`     | *(requerido)*               | Interfaz de red (ej. wlan0, eth0)            |
| `--interval`      | 10                          | Minutos entre cambios de MAC                 |
| `--proxies`       | `socks5 127.0.0.1 9050`    | Proxies separados por coma                   |
| `--mode`          | `strict_chain`              | Modo proxychains (strict/dynamic/random)     |
| `--proxy-dns`     | off                         | Activar resolución DNS vía proxy             |
| `--renew-dhcp`    | off                         | Renovar DHCP tras cada cambio de MAC         |
| `--immediate`     | off                         | Cambiar MAC inmediatamente al iniciar        |
| `--no-install`    | off                         | Saltar instalación automática de paquetes    |
| `--logfile`       | `/var/log/proxychains_macchanger.log` | Ruta del archivo de log |

### Ejemplo renovación DHCP

```bash
sudo python app.py --interface eth0 --interval 5 \
  --proxies "socks5 192.168.1.100 1080, http 10.0.0.1 3128" \
  --renew-dhcp --immediate
```

## Tests

```bash
pip install pytest ruff
pytest -q
```

## Configuración

No requiere variables de entorno. Ver `.env.example`:

```
# Environment variables
# Add your configuration here
```

Toda la configuración se pasa por argumentos CLI. La configuración de proxychains se escribe automáticamente en `/etc/proxychains.conf` con backup.

## CI

GitHub Actions — Push/PR:

- `ruff check`
- `pytest`

## Limitaciones / Roadmap

- Requiere ejecución root (sudo) para cambios de MAC y escritura en `/etc/`
- No soporta Windows (Linux-only con ip link, macchanger, nmcli)
- Depende de `macchanger`, `proxychains4`, `curl` y `dhclient` (instalación automática intenta con apt/dnf/pacman)
- A futuro: soporte para Tailscale/WireGuard, integración Tor, notificaciones desktop

## Licencia

MIT — ver [LICENSE](LICENSE).
