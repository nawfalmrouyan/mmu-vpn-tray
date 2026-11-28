# MMU VPN Tray (`mmu-vpn-tray`)

> [!NOTE]
> This project is 100% vibe coded. ✨

A lightweight, native system tray client for Multimedia University (MMU) Fortinet SSL-VPN with SAML 2.0 Single Sign-On (SSO) authentication.

Built with Python and GLib/GIO, `mmu-vpn-tray` implements the `org.kde.StatusNotifierItem` (SNI) and `com.canonical.dbusmenu` specifications. It integrates cleanly with Wayland compositors (such as Hyprland, Sway) and status bars (such as Waybar) as well as traditional X11 desktop environments without requiring heavy toolkit dependencies.

---

## Features

- **Native StatusNotifierItem (SNI) Tray**: Real-time status display and interactive menu (Connect, Disconnect, Status, Quit).
- **Default Browser SAML SSO**: Detects the SAML login URL from OpenFortiVPN and automatically launches your system's default browser via `xdg-open`.
- **Split-DNS Routing**: Configures `systemd-resolved` (`resolvectl domain ppp0 mmu.edu.my`) so that university resources (`*.mmu.edu.my`) resolve through campus DNS while regular internet browsing remains fast and untouched.
- **Split-Tunneling**: Only campus subnets are routed over the VPN; default gateway traffic is preserved.
- **Desktop Notifications**: Instant alerts when authenticating, connected, or disconnected via `libnotify`.
- **Clean Lifecycle**: Graceful termination with `pkill -INT` to ensure routes and interface teardowns occur cleanly.

---

## Dependencies

### Runtime Dependencies

| Dependency | Arch Linux Package | Purpose |
| :--- | :--- | :--- |
| **Python 3** | `python` | Script execution runtime |
| **PyGObject** | `python-gobject` | GLib, Gio DBus, and event loop bindings |
| **Ayatana Indicators (GLib)** | `libayatana-appindicator-glib` | Ayatana AppIndicator GLib library |
| **OpenFortiVPN** | `openfortivpn` | Fortinet SSL-VPN client with SAML support |
| **Libnotify** | `libnotify` | Desktop notifications (`notify-send`) |
| **XDG Utils** | `xdg-utils` | Opening the default browser (`xdg-open`) |
| **Sudo** | `sudo` | Passwordless execution for VPN operations |
| **Systemd** | `systemd` | Split-DNS management via `resolvectl` |
| **Procps-ng** | `procps-ng` | Process monitoring and termination (`pkill`) |

Install all runtime dependencies with your preferred AUR helper:

```bash
paru -S python python-gobject libayatana-appindicator-glib openfortivpn libnotify xdg-utils sudo systemd procps-ng
# or
yay -S python python-gobject libayatana-appindicator-glib openfortivpn libnotify xdg-utils sudo systemd procps-ng
```

---

## Installation

### From Arch User Repository (AUR)

Install the `-git` package using your preferred AUR helper:

```bash
paru -S mmu-vpn-tray-git
# or
yay -S mmu-vpn-tray-git
```

### Manual Build with `makepkg`

Clone this repository and run `makepkg`:

```bash
git clone https://github.com/nawfalmrouyan/mmu-vpn-tray.git
cd mmu-vpn-tray
makepkg -si
```

---

## Configuration

### 1. OpenFortiVPN Configuration (`/etc/openfortivpn/mmu-vpn.conf`)

The package installs a root-owned configuration at `/etc/openfortivpn/mmu-vpn.conf`. `mmu-vpn-tray` prefers this file so passwordless sudo can pin `openfortivpn` to a config the invoking user cannot modify.

> [!IMPORTANT]
> Keep this file owned by `root` and not writable by your user. `openfortivpn` supports options such as `pppd-plugin` and `pppd-log`, so a user-writable config combined with passwordless sudo is equivalent to giving that user root access.

For a manual build, install it with:
```bash
sudo install -Dm644 openfortivpn/mmu-vpn.conf /etc/openfortivpn/mmu-vpn.conf
```

The file contains:

```ini
# MMU Fortinet SSL-VPN OpenFortiVPN Configuration
host = vpn.mmu.edu.my
port = 443

# Enable SAML Single Sign-On
saml-login = 1

# DNS settings:
# set-dns = 0 prevents openfortivpn from overriding your global resolvers.
# Split-DNS is configured dynamically by mmu-vpn-tray using systemd-resolved.
set-dns = 0
use-resolvconf = 1
pppd-use-peerdns = 1

# Routing settings:
# set-routes = 1 enables routing for campus networks provided by the gateway.
# half-internet-routes = 0 ensures your normal internet traffic does NOT route through the VPN.
set-routes = 1
half-internet-routes = 0
```

#### Per-user configuration (development only)

When no system config exists, the tray falls back to `~/.config/openfortivpn/mmu-vpn.conf`. You can also point it at an explicit file with `MMU_VPN_CONFIG`:

```bash
MMU_VPN_CONFIG="$PWD/openfortivpn/mmu-vpn.conf" ./mmu-vpn-tray.py
```

If you use a non-default path, update the sudoers rule to match that exact path. Make the file root-owned before granting passwordless sudo on it.

#### Configuration Options Explained

- `host = vpn.mmu.edu.my`: The MMU FortiGate SSL-VPN gateway hostname.
- `port = 443`: SSL port for the gateway connection.
- `saml-login = 1`: Enables SAML 2.0 authentication mode, allowing single sign-on through MMU's Microsoft 365 identity provider.
- `set-dns = 0`: Disables openfortivpn's standard global DNS override. This is essential for split-tunnel setups so your local network DNS resolvers remain active for general internet traffic.
- `use-resolvconf = 1`: Enables integration with resolvconf/pppd.
- `pppd-use-peerdns = 1`: Solicits DNS server IP addresses from the remote VPN server for interface `ppp0`.
- `set-routes = 1`: Instructs openfortivpn to install route entries pushed by the VPN gateway for university subnets.
- `half-internet-routes = 0`: Prevents openfortivpn from adding `0.0.0.0/1` and `128.0.0.0/1` routes, ensuring split-tunneling (only university subnets traverse the VPN tunnel).

---

### 2. Sudoers Configuration (`/etc/sudoers.d/openfortivpn`)

Connecting and disconnecting the VPN, as well as updating interface DNS domains via `resolvectl`, require elevated privileges. The package installs `/etc/sudoers.d/openfortivpn` (mode `0440`) so `mmu-vpn-tray` can run these commands without password prompts.

The installed rule applies to members of the `wheel` group:

```sudoers
%wheel ALL=(root) NOPASSWD: /usr/bin/openfortivpn, /bin/openfortivpn, /usr/bin/pkill -INT openfortivpn, /bin/pkill -INT openfortivpn, /usr/bin/resolvectl domain ppp0 mmu.edu.my, /bin/resolvectl domain ppp0 mmu.edu.my
```

   **For members of the `wheel` group (recommended):**
   ```sudoers
   Defaults!/usr/bin/openfortivpn env_keep -= "https_proxy http_proxy all_proxy HTTPS_PROXY HTTP_PROXY ALL_PROXY"
   %wheel ALL=(root) NOPASSWD: /usr/bin/openfortivpn -c /etc/openfortivpn/mmu-vpn.conf --saml-login, \
                               /usr/bin/pkill -INT -x openfortivpn, \
                               /usr/bin/resolvectl domain ppp0 mmu.edu.my
   ```

   **Alternatively, for a specific user account:**
   ```sudoers
   Defaults!/usr/bin/openfortivpn env_keep -= "https_proxy http_proxy all_proxy HTTPS_PROXY HTTP_PROXY ALL_PROXY"
   your_username ALL=(root) NOPASSWD: /usr/bin/openfortivpn -c /etc/openfortivpn/mmu-vpn.conf --saml-login, \
                              /usr/bin/pkill -INT -x openfortivpn, \
                              /usr/bin/resolvectl domain ppp0 mmu.edu.my
   ```

To allow a specific account instead, edit the installed file with `visudo`:

```bash
sudo visudo -f /etc/sudoers.d/openfortivpn
```

Then replace the `%wheel` line with:

```sudoers
your_username ALL=(root) NOPASSWD: /usr/bin/openfortivpn, /bin/openfortivpn, /usr/bin/pkill -INT openfortivpn, /bin/pkill -INT openfortivpn, /usr/bin/resolvectl domain ppp0 mmu.edu.my, /bin/resolvectl domain ppp0 mmu.edu.my
```

Verify the file at any time with:

```bash
sudo visudo -cf /etc/sudoers.d/openfortivpn
```

#### Why These Sudo Permissions Are Required

- `/usr/bin/openfortivpn -c /etc/openfortivpn/mmu-vpn.conf --saml-login`: Needed to create the PPP tunnel interface (`ppp0`) and modify kernel routing tables. The exact `-c` path is pinned so the user cannot pass `pppd-plugin`, `pppd-log`, or another privileged openfortivpn option through a different config.
- `/usr/bin/pkill -INT -x openfortivpn`: Sends a graceful `SIGINT` signal to `openfortivpn` so it can tear down routes and close the session cleanly. `-x` prevents matching similarly named helper processes.
- `/usr/bin/resolvectl domain ppp0 mmu.edu.my`: Configures `systemd-resolved` to route DNS queries matching `mmu.edu.my` to the VPN DNS servers on `ppp0`.

> [!WARNING]
> Do not replace the exact rules above with wildcards such as `/usr/bin/openfortivpn *` or `/usr/bin/pkill *`. Sudo wildcards can match additional arguments and would let any member of `wheel` run privileged commands with attacker-controlled options.

---

## Authentication via Default Web Browser

MMU SSL-VPN uses SAML 2.0 Single Sign-On (SSO) integrated with Microsoft 365. `mmu-vpn-tray` automates the entire authentication lifecycle using your system's default browser:

```
[Tray: Connect] 
       │
       ▼
Spawns: openfortivpn --saml-login
       │
       ▼
Extracts SAML Auth URL from $XDG_RUNTIME_DIR/mmu-vpn-tray/openfortivpn.log
       │
       ▼
Calls: xdg-open <SAML_URL> (launches Default Browser)
       │
       ▼
User completes Login & 2FA/MFA in Browser
       │
       ▼
FortiGate validates SAML response -> Tunnel ppp0 comes UP
       │
       ▼
Applies Split-DNS: resolvectl domain ppp0 mmu.edu.my
       │
       ▼
Tray Icon changes to Connected + Desktop Notification
```

### Authentication Workflow

1. **Initiate Connection**: Click the tray icon and select **Connect** (or left-click the icon).
2. **Background Process**: `mmu-vpn-tray` executes `openfortivpn` in the background and sets its status to **Authenticating...** (yellow shield icon).
3. **Browser Invocation**: The client scans its private log (`$XDG_RUNTIME_DIR/mmu-vpn-tray/openfortivpn.log`) for the SAML portal address. Only HTTPS URLs for the configured VPN host are accepted. Once detected, it invokes `xdg-open`, opening the SAML URL in your default web browser (e.g. Firefox, Chromium, Zen, Brave, Chrome).
4. **Sign-In**: Log in using your MMU credentials (`@mmu.edu.my` or `@student.mmu.edu.my`) and approve any multi-factor authentication (MFA) prompts.
5. **Tunnel Handshake**: Upon successful browser authentication, FortiGate passes the session token back to openfortivpn. The PPP tunnel interface `ppp0` is established.
6. **Automatic Split-DNS**: Once `mmu-vpn-tray` verifies the `ppp0` interface is active, it runs `resolvectl domain ppp0 mmu.edu.my`.
7. **Connected**: The tray icon turns green and a desktop notification announces: `Connected (mmu.edu.my routed)`.

> **Note**: If your browser does not open automatically, check the log file for the login URL or open the fallback address: `https://vpn.mmu.edu.my:443/remote/saml/start?redirect=1`.

---

## Hyprland Integration (hyprlua)

If you configure Hyprland using Lua (`hyprlua` / `hyprland.lua`), you can register `mmu-vpn-tray` to autostart when Hyprland launches and terminate cleanly when Hyprland exits.

### Table-Driven Configuration (Recommended)

In your `~/.config/hypr/hyprland.lua`:

```lua
-- List of commands to run when Hyprland starts
local startup_cmds = {
    -- other autostart entries...
    "mmu-vpn-tray",
}

-- List of commands to run when Hyprland exits
local shutdown_cmds = {
    -- other cleanup entries...
    "pkill -f mmu-vpn-tray",
}

-- Hook into hyprland.start event
hl.on("hyprland.start", function()
    for _, cmd in ipairs(startup_cmds) do
        hl.exec_cmd(cmd)
    end
end)

-- Hook into hyprland.shutdown event
hl.on("hyprland.shutdown", function()
    for _, cmd in ipairs(shutdown_cmds) do
        hl.exec_cmd(cmd)
    end
end)
```

### Direct Callback Configuration

Alternatively, register event hooks directly:

```lua
-- Autostart MMU VPN Tray on Hyprland startup
hl.on("hyprland.start", function()
    hl.exec_cmd("mmu-vpn-tray")
end)

-- Stop MMU VPN Tray when Hyprland shuts down
hl.on("hyprland.shutdown", function()
    hl.exec_cmd("pkill -f mmu-vpn-tray")
end)
```

### Standard Hyprlang (`hyprland.conf`)

For standard `hyprland.conf` (without Lua), add:

```ini
exec-once = mmu-vpn-tray
```

---

## Waybar Tray Configuration

To display the tray icon in Waybar, ensure the `tray` module is present in your `~/.config/waybar/config`:

```json
"modules-right": [
    "tray"
],
"tray": {
    "icon-size": 18,
    "spacing": 8
}
```

---

## Manual Execution & Troubleshooting

### Running from Terminal

To test the application in foreground and inspect output:

```bash
mmu-vpn-tray
```

### Checking Logs

The OpenFortiVPN connection log is stored in the tray's private runtime directory (mode `0700`, log mode `0600`):

```bash
cat "${XDG_RUNTIME_DIR:-$HOME/.cache}/mmu-vpn-tray/openfortivpn.log"
```

### Verifying Split-DNS

To verify that DNS queries for `mmu.edu.my` route through the `ppp0` VPN interface:

```bash
resolvectl domain ppp0
# Output should include:
# Link 2 (ppp0): mmu.edu.my
```

Test domain resolution:

```bash
resolvectl query intranet.mmu.edu.my
```

---

## Security Notes

- **No shell interpolation**: `openfortivpn`, `pkill`, `resolvectl`, and `xdg-open` are launched with argument arrays, never through `/bin/sh -c`. The config path and other values cannot inject shell commands.
- **Private log**: connection output (which can contain SAML tokens) is written to `${XDG_RUNTIME_DIR:-~/.cache}/mmu-vpn-tray/`, created with mode `0700` and the log with mode `0600`. It is opened with `O_NOFOLLOW` so another user cannot pre-create a symlink and redirect writes.
- **Login URL allow-list**: before calling `xdg-open`, the tray accepts only `https://` URLs whose hostname matches the configured VPN host (`vpn.mmu.edu.my` by default). A forged log entry cannot open an arbitrary URL.
- **Pinned sudo commands**: the sample sudoers rule allows only the exact `openfortivpn`, `pkill`, and `resolvectl` invocations the tray uses, and pins `openfortivpn` to a root-owned config. Avoid wildcards.
- **Process matching**: the tray identifies `openfortivpn` by its exact process name and by the configured `-c` path, instead of treating any process with a similar name as the VPN.
- **Single instance**: an advisory `flock` in the runtime directory prevents duplicate tray processes from fighting over the same VPN state.

> [!NOTE]
> `pkill -INT -x openfortivpn` is still system-wide because all VPN processes run as root. On a multi-user machine, disconnecting from one account can stop another account's openfortivpn process that uses the same config path.

---

## License

This project is licensed under the BSD 3-Clause License. See [LICENSE](LICENSE) for details.
