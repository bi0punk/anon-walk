#!/usr/bin/env python3
"""
setup_proxychains_macchanger.py

Script que:
 - Instala proxychains4 y macchanger (si es posible con apt/dnf/pacman)
 - Backea y configura /etc/proxychains.conf según parámetros
 - Cambia periódicamente la MAC de una interfaz y reinicia/renueva la conexión de red
 - Logging, manejo de errores, señales (CTRL+C)
 - Opción para renovar DHCP tras el cambio de MAC (--renew-dhcp / --no-renew-dhcp)

USO:
 sudo python3 setup_proxychains_macchanger.py --interface wlan0 --interval 10 \
    --proxies "socks5 127.0.0.1 9050" --mode strict_chain --proxy-dns --renew-dhcp

Advertencias:
 - Requiere permisos root.
 - Testear antes en VM/entorno controlado.
 - Cambiar MAC puede afectar acceso a redes que usan filtrado por MAC.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

# ---------------------------
# Logging
# ---------------------------
DEFAULT_LOG_PATH = "/var/log/proxychains_macchanger.log"
if not os.access("/var/log", os.W_OK):
    DEFAULT_LOG_PATH = os.path.join(os.getcwd(), "proxychains_macchanger.log")

logging.basicConfig(
    filename=DEFAULT_LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(fmt)
logging.getLogger().addHandler(console)


# ---------------------------
# Utils
# ---------------------------
def run(
    cmd: list[str], check: bool = True, capture_output: bool = False, text: bool = True
) -> subprocess.CompletedProcess:
    logging.debug("Ejecutando: %s", " ".join(cmd))
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)
    except subprocess.CalledProcessError as e:
        logging.error("Comando falló (%s): %s", " ".join(cmd), e)
        raise


def is_root() -> bool:
    return os.geteuid() == 0


def detect_package_manager() -> str | None:
    for p in ("apt-get", "apt", "dnf", "yum", "pacman"):
        if shutil.which(p):
            return p
    return None


# ---------------------------
# Install packages
# ---------------------------
def install_packages(packages: list[str]) -> None:
    pm = detect_package_manager()
    if pm is None:
        logging.warning(
            "No se detectó gestor de paquetes conocido. Instala manualmente: %s",
            ", ".join(packages),
        )
        return
    logging.info("Gestor de paquetes detectado: %s", pm)
    try:
        if pm in ("apt-get", "apt"):
            run([pm, "update"])
            run([pm, "install", "-y"] + packages)
        elif pm in ("dnf", "yum"):
            run([pm, "install", "-y"] + packages)
        elif pm == "pacman":
            run([pm, "-Sy", "--noconfirm"] + packages)
        logging.info("Instalación finalizada (o ya estaban instalados): %s", ", ".join(packages))
    except (subprocess.CalledProcessError, OSError) as e:
        logging.error("Error instalando paquetes: %s", e)
        raise


# ---------------------------
# Proxychains config
# ---------------------------
PROXYCHAINS_CONF = "/etc/proxychains.conf"
BACKUP_SUFFIX = ".backup-by-script"


def backup_file(path: str) -> str:
    dst = f"{path}{BACKUP_SUFFIX}.{int(time.time())}"
    shutil.copy2(path, dst)
    logging.info("Backup creado: %s", dst)
    return dst


def configure_proxychains(
    proxy_lines: list[str], mode: str = "strict_chain", proxy_dns: bool = True
) -> None:
    if not os.path.exists(PROXYCHAINS_CONF):
        logging.warning("%s no existe. Creando archivo base.", PROXYCHAINS_CONF)
        with open(PROXYCHAINS_CONF, "w") as f:
            f.write("# Created by setup_proxychains_macchanger.py\n\n")
            f.write("strict_chain\nproxy_dns\n[ProxyList]\n")
    backup_file(PROXYCHAINS_CONF)
    logging.info("Configurando %s (mode=%s proxy_dns=%s)", PROXYCHAINS_CONF, mode, proxy_dns)
    with open(PROXYCHAINS_CONF, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # Ajustar modo
    content = re.sub(r"(?m)^(strict_chain|dynamic_chain|random_chain).*$", mode, content)
    if not re.search(r"^(strict_chain|dynamic_chain|random_chain)$", content, flags=re.M):
        content = mode + "\n" + content
    # proxy_dns
    if proxy_dns:
        if "proxy_dns" not in content:
            content = content.replace(mode + "\n", mode + "\nproxy_dns\n", 1)
    else:
        content = re.sub(r"(?m)^\s*proxy_dns\s*$", "", content)
    # Reescribir lista de proxies
    if "[ProxyList]" in content:
        before, _sep, _after = content.partition("[ProxyList]")
        content = before + "[ProxyList]\n" + "\n".join(proxy_lines).strip() + "\n"
    else:
        content = content + "\n[ProxyList]\n" + "\n".join(proxy_lines).strip() + "\n"
    with open(PROXYCHAINS_CONF, "w", encoding="utf-8") as f:
        f.write(content)
    logging.info("proxychains configurado. Revisa %s para ajustes adicionales.", PROXYCHAINS_CONF)


# ---------------------------
# MAC change & network restart
# ---------------------------
def generate_random_mac() -> str:
    import secrets

    mac = [
        0x02,
        secrets.randbelow(0x100),
        secrets.randbelow(0x100),
        secrets.randbelow(0x100),
        secrets.randbelow(0x100),
        secrets.randbelow(0x100),
    ]
    return ":".join(f"{b:02x}" for b in mac)


def change_mac_with_macchanger(interface: str, new_mac: str | None = None) -> str:
    if shutil.which("macchanger"):
        cmd = (
            ["macchanger", "-r", interface]
            if new_mac is None
            else ["macchanger", "-m", new_mac, interface]
        )
        try:
            cp = run(cmd, capture_output=True)
            out = cp.stdout.strip() if cp.stdout else ""
            logging.info("macchanger output: %s", out)
            m = re.search(r"New MAC: ([0-9a-f:]{17})", out, re.IGNORECASE)
            if m:
                mac = m.group(1)
                logging.info("MAC cambiada a %s en %s (macchanger)", mac, interface)
                return mac
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("macchanger falló: %s", e)
    # fallback ip link
    mac = new_mac or generate_random_mac()
    try:
        run(["ip", "link", "set", "dev", interface, "down"])
        run(["ip", "link", "set", "dev", interface, "address", mac])
        run(["ip", "link", "set", "dev", interface, "up"])
        logging.info("MAC cambiada a %s en %s (ip link)", mac, interface)
        return mac
    except (subprocess.CalledProcessError, OSError) as e:
        logging.error("No se pudo cambiar la MAC con ip link: %s", e)
        raise


def restart_network(interface: str) -> None:
    logging.info("Reiniciando conexión de red para la interfaz: %s", interface)
    if shutil.which("nmcli"):
        try:
            run(["nmcli", "device", "disconnect", interface])
            time.sleep(1)
            run(["nmcli", "device", "connect", interface])
            logging.info("nmcli: reconectada la interfaz %s", interface)
            return
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("nmcli reconectar falló: %s", e)
    if shutil.which("systemctl"):
        try:
            run(["systemctl", "restart", "NetworkManager"])
            logging.info("NetworkManager reiniciado con systemctl")
            return
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("systemctl NetworkManager falló: %s", e)
    try:
        run(["ip", "link", "set", "dev", interface, "down"])
        time.sleep(1)
        run(["ip", "link", "set", "dev", interface, "up"])
        logging.info("Interfaz %s bajada/subida con ip link", interface)
    except (subprocess.CalledProcessError, OSError) as e:
        logging.error("No se pudo reiniciar la interfaz %s: %s", interface, e)
        raise


def renew_dhcp(interface: str) -> None:
    """Intenta renovar la concesión DHCP. Se intentan varios métodos y se ignoran fallos no críticos."""
    logging.info("Intentando renovar DHCP en %s", interface)
    # Si NetworkManager está presente, intentar usar nmcli para renovar la conexión específica
    if shutil.which("nmcli"):
        try:
            # reapply connection for interface (mejor que reiniciar NM completo si funciona)
            run(["nmcli", "device", "reapply", interface])
            # también solicitar re-connection para forzar DHCP
            run(["nmcli", "device", "disconnect", interface])
            time.sleep(1)
            run(["nmcli", "device", "connect", interface])
            logging.info("DHCP: nmcli reapply/reconnect ejecutado.")
            return
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("nmcli reapply/reconnect falló: %s", e)
    # Intentar usar dhclient
    if shutil.which("dhclient"):
        try:
            run(["dhclient", "-r", interface])
            time.sleep(1)
            run(["dhclient", interface])
            logging.info("DHCP: dhclient renew ejecutado.")
            return
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("dhclient falló: %s", e)
    # Intentar dhcpcd si está instalado
    if shutil.which("dhcpcd"):
        try:
            run(["dhcpcd", "-k", interface])
            time.sleep(1)
            run(["dhcpcd", interface])
            logging.info("DHCP: dhcpcd renew ejecutado.")
            return
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("dhcpcd falló: %s", e)
    logging.warning(
        "No se pudo renovar DHCP con los métodos intentados. Verifica configuración del sistema."
    )


def get_current_mac(interface: str) -> str | None:
    try:
        cp = run(["cat", f"/sys/class/net/{interface}/address"], capture_output=True)
        mac = cp.stdout.strip()
        return mac
    except (subprocess.CalledProcessError, OSError):
        return None


# ---------------------------
# Periodic task
# ---------------------------
stop_event = threading.Event()


def _restart_and_renew(interface: str, renew_dhcp_flag: bool, label: str = "") -> None:
    prefix = f"[{label}] " if label else ""
    logging.info("%sReiniciando red + DHCP para %s", prefix, interface)
    restart_network(interface)
    if renew_dhcp_flag:
        renew_dhcp(interface)


def periodic_mac_change_loop(
    interface: str, interval_minutes: int, immediate: bool, renew_dhcp_flag: bool
) -> None:
    interval = max(1, int(interval_minutes))
    logging.info(
        "Iniciando loop: cambio de MAC cada %d minutos en %s (renew_dhcp=%s)",
        interval,
        interface,
        renew_dhcp_flag,
    )
    if immediate:
        try:
            old = get_current_mac(interface)
            logging.info("MAC antes del primer cambio: %s", old)
            new_mac = change_mac_with_macchanger(interface)
            logging.info("MAC tras primer cambio: %s", new_mac)
            _restart_and_renew(interface, renew_dhcp_flag, "inicio")
        except (subprocess.CalledProcessError, OSError) as e:
            logging.error("Error en cambio inicial de MAC: %s", e)
    next_wait = interval * 60
    while not stop_event.wait(timeout=next_wait):
        try:
            old = get_current_mac(interface)
            logging.info("Cambio periódico: MAC actual: %s", old)
            new_mac = change_mac_with_macchanger(interface)
            logging.info("MAC cambiada a %s", new_mac)
            _restart_and_renew(interface, renew_dhcp_flag, "periódico")
        except (subprocess.CalledProcessError, OSError) as e:
            logging.error("Error en cambio periódico de MAC: %s", e)


# ---------------------------
# Signals
# ---------------------------
def signal_handler(sig, _frame):
    logging.info("Señal recibida: %s - deteniendo...", sig)
    stop_event.set()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ---------------------------
# Optional checks
# ---------------------------
def check_public_ip(use_proxy: bool = False) -> str | None:
    if not shutil.which("curl"):
        logging.debug("curl no disponible para check_public_ip")
        return None
    cmd = ["curl", "-s", "ifconfig.me"]
    if use_proxy:
        if shutil.which("proxychains4"):
            cmd = ["proxychains4", "curl", "-s", "ifconfig.me"]
        elif shutil.which("proxychains"):
            cmd = ["proxychains", "curl", "-s", "ifconfig.me"]
    try:
        cp = run(cmd, capture_output=True)
        ip = cp.stdout.strip()
        logging.info("IP pública (use_proxy=%s): %s", use_proxy, ip)
        return ip
    except (subprocess.CalledProcessError, OSError):
        return None


# ---------------------------
# Helpers parse proxies
# ---------------------------
def parse_proxy_lines(raw: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[,\n;]+", raw) if p.strip()]
    cleaned = []
    for p in parts:
        toks = p.split()
        if len(toks) >= 3:
            cleaned.append(" ".join(toks[:3]))
        else:
            logging.warning("Proxy ignorado por formato inválido: %s", p)
    return cleaned


# ---------------------------
# Main
# ---------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Configura proxychains y macchanger (cambio MAC periódico)."
    )
    parser.add_argument("--interface", required=True, help="Interfaz a modificar (ej. wlan0, eth0)")
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Intervalo en minutos para cambiar MAC (default 10)",
    )
    parser.add_argument(
        "--proxies",
        default="socks5 127.0.0.1 9050",
        help="Lista de proxies separadas por coma. Ej: 'socks5 127.0.0.1 9050, socks5 1.2.3.4 1080'",
    )
    parser.add_argument(
        "--mode",
        choices=["strict_chain", "dynamic_chain", "random_chain"],
        default="strict_chain",
        help="Modo de proxychains",
    )
    parser.add_argument(
        "--proxy-dns", dest="proxy_dns", action="store_true", help="Activar proxy_dns"
    )
    parser.add_argument(
        "--no-install",
        dest="no_install",
        action="store_true",
        help="No instalar paquetes automáticamente",
    )
    parser.add_argument(
        "--immediate",
        dest="immediate",
        action="store_true",
        help="Aplicar cambio de MAC inmediatamente al iniciar",
    )
    parser.add_argument(
        "--renew-dhcp",
        dest="renew_dhcp",
        action="store_true",
        help="Renovar DHCP tras cada cambio de MAC",
    )
    parser.add_argument(
        "--no-renew-dhcp",
        dest="renew_dhcp",
        action="store_false",
        help="No renovar DHCP (contrario).",
    )
    parser.add_argument(
        "--logfile", default=DEFAULT_LOG_PATH, help=f"Ruta logfile (default {DEFAULT_LOG_PATH})"
    )
    args = parser.parse_args()

    # configure logfile handler path if user provided
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.FileHandler):
            h.baseFilename = args.logfile

    logging.info(
        "Inicio - proxychains/macchanger - interface=%s interval=%d renew_dhcp=%s",
        args.interface,
        args.interval,
        args.renew_dhcp,
    )

    if not is_root():
        logging.error("Este script requiere ejecutarse como root. Salida.")
        print("Ejecuta: sudo python3 setup_proxychains_macchanger.py ...")
        sys.exit(1)

    if not args.no_install:
        try:
            install_packages(["proxychains4", "macchanger", "curl", "dhclient"])
        except (subprocess.CalledProcessError, OSError) as e:
            logging.warning("No se pudo instalar paquetes automáticamente: %s", e)

    proxy_lines = parse_proxy_lines(args.proxies)
    if not proxy_lines:
        logging.error("No se entregaron proxies válidos. Salida.")
        sys.exit(1)
    try:
        configure_proxychains(proxy_lines, mode=args.mode, proxy_dns=args.proxy_dns)
    except (subprocess.CalledProcessError, OSError) as e:
        logging.error("Error configurando proxychains: %s", e)

    ip_before = check_public_ip(use_proxy=False)
    ip_before_proxy = check_public_ip(use_proxy=True)

    worker = threading.Thread(
        target=periodic_mac_change_loop,
        args=(args.interface, args.interval, args.immediate, args.renew_dhcp),
        daemon=True,
    )
    worker.start()

    logging.info("Presiona Ctrl+C para detener el script.")
    try:
        while not stop_event.wait(timeout=1):
            pass
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt recibido.")

    logging.info("Finalizando... esperando al worker")
    stop_event.set()
    worker.join(timeout=10)
    logging.info("Script terminado. Logs: %s", args.logfile)
    logging.info(
        "IP antes: %s (sin proxy) - IP con proxy (si config): %s", ip_before, ip_before_proxy
    )


if __name__ == "__main__":
    main()
