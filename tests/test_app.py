import tempfile
from pathlib import Path
from unittest.mock import patch

from app import (
    _restart_and_renew,
    backup_file,
    detect_package_manager,
    generate_random_mac,
    is_root,
    parse_proxy_lines,
)


def test_is_root_returns_bool():
    assert isinstance(is_root(), bool)


def test_detect_package_manager():
    pm = detect_package_manager()
    assert pm is None or isinstance(pm, str)


def test_generate_random_mac():
    mac = generate_random_mac()
    parts = mac.split(":")
    assert len(parts) == 6
    assert all(0 <= int(p, 16) <= 255 for p in parts)


def test_parse_proxy_lines_basic():
    result = parse_proxy_lines("socks5 127.0.0.1 9050")
    assert len(result) == 1
    assert result[0] == "socks5 127.0.0.1 9050"


def test_parse_proxy_lines_multiple():
    result = parse_proxy_lines("socks5 127.0.0.1 9050, socks5 1.2.3.4 1080")
    assert len(result) == 2
    assert "socks5 127.0.0.1 9050" in result


def test_parse_proxy_lines_semicolon():
    result = parse_proxy_lines("socks5 127.0.0.1 9050; socks5 1.2.3.4 1080")
    assert len(result) == 2


def test_parse_proxy_lines_empty():
    assert parse_proxy_lines("") == []


def test_parse_proxy_lines_invalid_skipped():
    result = parse_proxy_lines("short, socks5 127.0.0.1 9050")
    assert len(result) == 1


def test_backup_file():
    with tempfile.NamedTemporaryFile(suffix=".test", delete=False) as f:
        f.write(b"test content")
        f.flush()
        src = f.name

    backup = backup_file(src)
    assert Path(backup).exists()
    Path(backup).unlink()
    Path(src).unlink()


def test_restart_and_renew_mock():
    with patch("app.restart_network") as mock_restart, patch("app.renew_dhcp") as mock_renew:
        _restart_and_renew("eth0", True)
        mock_restart.assert_called_once_with("eth0")
        mock_renew.assert_called_once_with("eth0")


def test_restart_and_renew_no_dhcp():
    with patch("app.restart_network") as mock_restart, patch("app.renew_dhcp") as mock_renew:
        _restart_and_renew("eth0", False)
        mock_restart.assert_called_once_with("eth0")
        mock_renew.assert_not_called()
