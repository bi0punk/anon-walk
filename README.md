# anon-walk

Anonymity-enhancing tool that installs and configures proxychains-ng and macchanger, periodically randomizes the MAC address of a network interface, and optionally renews DHCP.

## Stack

Python 3, bash (system packages)

## Usage

```bash
sudo python app.py
```

The script will:
- Install proxychains-ng and macchanger (apt/dnf/pacman)
- Configure proxychains.conf
- Periodically randomize the MAC address
- Optionally renew DHCP lease

## License

MIT
