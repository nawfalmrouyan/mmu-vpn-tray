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

### 1. OpenFortiVPN Configuration (`~/.config/openfortivpn/mmu-vpn.conf`)

`mmu-vpn-tray` reads its connection settings from `~/.config/openfortivpn/mmu-vpn.conf`.

1. Create the configuration directory:
   ```bash
   mkdir -p ~/.config/openfortivpn
   ```

2. Create `~/.config/openfortivpn/mmu-vpn.conf` with the following content:
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

3. Secure the configuration file permissions:
   ```bash
   chmod 600 ~/.config/openfortivpn/mmu-vpn.conf
   ```

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

Connecting and disconnecting the VPN, as well as updating interface DNS domains via `resolvectl`, require elevated privileges. To allow `mmu-vpn-tray` to run smoothly in the background without password prompts, configure `/etc/sudoers.d/openfortivpn`.

1. Create `/etc/sudoers.d/openfortivpn` using `visudo`:
   ```bash
   sudo visudo -f /etc/sudoers.d/openfortivpn
   ```

2. Add the configuration:

   **For members of the `wheel` group (recommended):**
   ```sudoers
   %wheel ALL=(root) NOPASSWD: /usr/bin/openfortivpn, /bin/openfortivpn, /usr/bin/pkill -INT openfortivpn, /bin/pkill -INT openfortivpn, /usr/bin/resolvectl domain ppp0 mmu.edu.my, /bin/resolvectl domain ppp0 mmu.edu.my
   ```

   **Alternatively, for a specific user account:**
   ```sudoers
   your_username ALL=(root) NOPASSWD: /usr/bin/openfortivpn, /bin/openfortivpn, /usr/bin/pkill -INT openfortivpn, /bin/pkill -INT openfortivpn, /usr/bin/resolvectl domain ppp0 mmu.edu.my, /bin/resolvectl domain ppp0 mmu.edu.my
   ```

3. Ensure strict file permissions (required by sudo):
   ```bash
   sudo chmod 440 /etc/sudoers.d/openfortivpn
   ```

#### Why These Sudo Permissions Are Required

- `/usr/bin/openfortivpn`: Needed to create the PPP tunnel interface (`ppp0`) and modify kernel routing tables.
- `/usr/bin/pkill -INT openfortivpn`: Sends a graceful `SIGINT` signal to openfortivpn so it can tear down routes and close the session cleanly.
- `/usr/bin/resolvectl domain ppp0 mmu.edu.my`: Configures `systemd-resolved` to route DNS queries matching `mmu.edu.my` to the VPN DNS servers on `ppp0`.

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
Extracts SAML Auth URL from /tmp/openfortivpn-mmu.log
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
3. **Browser Invocation**: The client continuously scans the log (`/tmp/openfortivpn-mmu.log`) for the SAML portal address. Once detected, it invokes `xdg-open`, opening the SAML URL in your default web browser (e.g. Firefox, Chromium, Zen, Brave, Chrome).
4. **Sign-In**: Log in using your MMU credentials (`@mmu.edu.my` or `@student.mmu.edu.my`) and approve any multi-factor authentication (MFA) prompts.
5. **Tunnel Handshake**: Upon successful browser authentication, FortiGate passes the session token back to openfortivpn. The PPP tunnel interface `ppp0` is established.
6. **Automatic Split-DNS**: Once `mmu-vpn-tray` verifies the `ppp0` interface is active, it runs `resolvectl domain ppp0 mmu.edu.my`.
7. **Connected**: The tray icon turns green and a desktop notification announces: `Connected (mmu.edu.my routed)`.

> **Note**: If your browser does not open automatically, check `/tmp/openfortivpn-mmu.log` for the login URL or open the fallback address: `https://vpn.mmu.edu.my:443/remote/saml/start?redirect=1`.

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

The OpenFortiVPN connection log is stored at:

```bash
cat /tmp/openfortivpn-mmu.log
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

## License

This project is licensed under the BSD 3-Clause License. See [LICENSE](file:///home/opal/Projects/mmu-vpn-tray/LICENSE) for details.
