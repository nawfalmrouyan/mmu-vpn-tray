#!/usr/bin/env python3

# 100% vibe coded ✨
# dependencies: openfortivpn python-gobject libayatana-appindicator-glib libnotify xdg-utils sudo systemd procps-ng

import fcntl
import os
import re
import shutil
import signal
import socket
import stat
import struct
import sys
import urllib.parse

from gi.repository import Gio, GLib

try:
    from gi.repository import GLibUnix
except ImportError:  # older GLib
    GLibUnix = None

APP_ID = "mmu-vpn-tray"
VPN_HOST_FALLBACK = "vpn.mmu.edu.my"

# Absolute paths are used deliberately: these binaries are executed via sudo,
# so a user-controlled PATH must never influence which program runs.
OPENFORTIVPN = "/usr/bin/openfortivpn"
SUDO = "/usr/bin/sudo"
PKILL = "/usr/bin/pkill"
RESOLVECTL = "/usr/bin/resolvectl"
SETSID = shutil.which("setsid") or "/usr/bin/setsid"

SYSTEM_CONFIG = "/etc/openfortivpn/mmu-vpn.conf"
LOG_READ_LIMIT = 64 * 1024

# Menu item ids from _menu_items().
MENU_STATUS = 1
MENU_CONNECT = 3
MENU_DISCONNECT = 4
MENU_QUIT = 6


def _user_config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "openfortivpn", "mmu-vpn.conf")


def _resolve_config():
    """Prefer the root-owned system config; fall back to the user config."""
    override = os.environ.get("MMU_VPN_CONFIG")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.path.isfile(SYSTEM_CONFIG):
        return SYSTEM_CONFIG
    return _user_config_path()


def _runtime_dir():
    """Return a private (0700) directory for the log and lock file."""
    candidates = []
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        candidates.append(os.path.join(runtime, APP_ID))
    candidates.append(os.path.join(os.path.expanduser("~/.cache"), APP_ID))

    for directory in candidates:
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            info = os.lstat(directory)
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
            ):
                continue
            os.chmod(directory, 0o700)
            return directory
        except OSError:
            continue

    raise RuntimeError("could not create a private runtime directory")


CONFIG = _resolve_config()


def read_config_host(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as config:
            for raw_line in config:
                line = raw_line.split("#", 1)[0].strip()
                match = re.match(r"host\s*=\s*(\S+)", line, re.IGNORECASE)
                if match:
                    return match.group(1).strip("\"'")
    except OSError:
        pass
    return VPN_HOST_FALLBACK


CONFIG_HOST = read_config_host(CONFIG)
FALLBACK_VPN_URL = f"https://{CONFIG_HOST}:443/remote/saml/start?redirect=1"
ALLOWED_SAML_HOSTS = frozenset({CONFIG_HOST.lower()})

RUNTIME_DIR = _runtime_dir()
LOG_FILE = os.path.join(RUNTIME_DIR, "openfortivpn.log")
LOCK_FILE = os.path.join(RUNTIME_DIR, "tray.lock")

_script_dir = os.path.dirname(os.path.abspath(__file__))
_local_icon_dir = os.path.join(_script_dir, "mmu-vpn-tray")
_user_icon_dir = os.path.expanduser("~/.local/share/icons/mmu-vpn-tray")
_system_icon_dir = "/usr/share/icons/mmu-vpn-tray"

if os.path.isdir(_user_icon_dir):
    ICON_DIR = _user_icon_dir
elif os.path.isdir(_system_icon_dir):
    ICON_DIR = _system_icon_dir
elif os.path.isdir(_local_icon_dir):
    ICON_DIR = _local_icon_dir
else:
    ICON_DIR = _user_icon_dir

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewStatus">
      <arg type="s" name="status"/>
    </signal>
    <signal name="NewTitle"/>
  </interface>
</node>
"""

DBUSMENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
  </interface>
</node>
"""


def is_vpn_running():
    """Return True if an openfortivpn process uses our config file."""
    try:
        entries = os.scandir("/proc")
    except OSError:
        return False

    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                with open(
                    os.path.join(entry.path, "comm"),
                    "r",
                    encoding="utf-8",
                    errors="replace",
                ) as comm:
                    if comm.read().strip() != "openfortivpn":
                        continue
                with open(os.path.join(entry.path, "cmdline"), "rb") as cmdline:
                    command = cmdline.read().replace(b"\0", b" ").decode(
                        "utf-8", "replace"
                    )
                if CONFIG in command:
                    return True
            except OSError:
                continue
    return False


def has_ppp0_ipv4():
    if not os.path.exists("/sys/class/net/ppp0"):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            fcntl.ioctl(
                sock.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack("16s24x", b"ppp0"),
            )
            return True
    except OSError:
        return False


def read_log():
    """Read the tail of the private VPN log, refusing symlinks."""
    try:
        fd = os.open(LOG_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return ""
    try:
        with os.fdopen(fd, "rb") as log:
            info = os.fstat(log.fileno())
            if not stat.S_ISREG(info.st_mode):
                return ""
            if info.st_size > LOG_READ_LIMIT:
                log.seek(info.st_size - LOG_READ_LIMIT)
            return log.read().decode("utf-8", "replace")
    except OSError:
        return ""


def is_allowed_saml_url(url, allowed_hosts=ALLOWED_SAML_HOSTS):
    # Reject control characters and backslashes, which different URL parsers
    # (and browsers) can interpret inconsistently.
    if any(ord(char) < 0x20 or char == "\\" for char in url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.hostname.lower() in allowed_hosts
    )


def extract_saml_url(log_text, allowed_hosts=ALLOWED_SAML_HOSTS):
    """Find the first HTTPS URL that points at the configured VPN host."""
    for match in re.finditer(r"https://[^\s'\"<>]+", log_text):
        url = match.group(0).rstrip(".,;:)]}")
        if is_allowed_saml_url(url, allowed_hosts):
            return url
    return None


def notify(summary, body=""):
    try:
        Gio.Subprocess.new(
            ["notify-send", "--app-name=MMU VPN", "--", summary, body],
            Gio.SubprocessFlags.NONE,
        )
    except GLib.Error:
        pass


def acquire_instance_lock():
    """Take an exclusive lock so only one tray instance runs per user."""
    try:
        fd = os.open(
            LOCK_FILE,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
    except OSError:
        return None

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None

    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        pass
    return fd


class VpnTrayService:
    def __init__(self, loop):
        self.loop = loop
        self.connecting = False
        self.disconnecting = False
        self.tunnel_logged_up = False
        self.revision = 1
        self.state = "disconnected"
        self.icon_name = "mmu-vpn-disconnected"
        self.title = "MMU VPN: Disconnected"
        self.proc = None
        self._dns_scheduled = False
        self._allowed_saml_hosts = ALLOWED_SAML_HOSTS
        self._menu_key = (self.state, self.disconnecting)

        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

        sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu_info = Gio.DBusNodeInfo.new_for_xml(DBUSMENU_XML).interfaces[0]

        self.bus.register_object(
            "/StatusNotifierItem",
            sni_info,
            self._on_sni_call,
            self._on_sni_get_prop,
            None,
        )
        self.bus.register_object(
            "/MenuBar",
            menu_info,
            self._on_menu_call,
            self._on_menu_get_prop,
            None,
        )

        Gio.bus_own_name_on_connection(
            self.bus,
            self.bus_name,
            Gio.BusNameOwnerFlags.NONE,
            self._on_name_acquired,
            None,
        )

        self.update_ui()
        GLib.timeout_add_seconds(3, self.update_ui)

    def _on_name_acquired(self, connection, _name):
        self._register_with_watcher()
        connection.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            "org.kde.StatusNotifierWatcher",
            Gio.DBusSignalFlags.NONE,
            lambda *_args: self._register_with_watcher(),
        )

    def _register_with_watcher(self):
        try:
            self.bus.call_sync(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (self.bus_name,)),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
        except GLib.Error:
            pass

    def _is_tunnel_ready(self):
        if not has_ppp0_ipv4():
            self.tunnel_logged_up = False
            return False
        if not self.tunnel_logged_up:
            self.tunnel_logged_up = "tunnel is up and running" in read_log().lower()
        return self.tunnel_logged_up

    def _reap_process(self):
        if self.proc is None:
            return
        try:
            if self.proc.get_if_exited():
                self.proc = None
        except GLib.Error:
            self.proc = None

    def _startup_error(self):
        """Return a fatal startup line, if the helper could not be launched."""
        for line in read_log().splitlines():
            low = line.lower()
            if "sudo:" in low or low.startswith("error:"):
                return line.strip()[:300]
        return None

    def _menu_items(self):
        if self.disconnecting:
            status_label = "Status: Disconnecting..."
            can_connect = False
            can_disconnect = False
        elif self.state == "connected":
            status_label = "Status: Connected"
            can_connect = False
            can_disconnect = True
        elif self.state == "connecting":
            status_label = "Status: Authenticating..."
            can_connect = False
            can_disconnect = True
        else:
            status_label = "Status: Disconnected"
            can_connect = True
            can_disconnect = False

        return {
            MENU_STATUS: {
                "label": GLib.Variant("s", status_label),
                "enabled": GLib.Variant("b", False),
            },
            2: {"type": GLib.Variant("s", "separator")},
            MENU_CONNECT: {
                "label": GLib.Variant("s", "Connect"),
                "enabled": GLib.Variant("b", can_connect),
            },
            MENU_DISCONNECT: {
                "label": GLib.Variant("s", "Disconnect"),
                "enabled": GLib.Variant("b", can_disconnect),
            },
            5: {"type": GLib.Variant("s", "separator")},
            MENU_QUIT: {
                "label": GLib.Variant("s", "Quit Tray"),
                "enabled": GLib.Variant("b", True),
            },
        }

    def _on_sni_get_prop(self, _conn, _sender, _path, _iface, prop):
        props = {
            "Category": GLib.Variant("s", "SystemServices"),
            "Id": GLib.Variant("s", "mmu-vpn-tray"),
            "Title": GLib.Variant("s", self.title),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", self.icon_name),
            "IconThemePath": GLib.Variant("s", ICON_DIR),
            "Menu": GLib.Variant("o", "/MenuBar"),
            "ItemIsMenu": GLib.Variant("b", False),
        }
        return props.get(prop)

    def _on_sni_call(self, _conn, _sender, _path, _iface, method, _params, invocation):
        if method == "Activate":
            if self.state == "disconnected":
                self.start_connect()
            elif not self.disconnecting:
                self.disconnect_vpn()
            invocation.return_value(None)
        elif method == "SecondaryActivate":
            invocation.return_value(None)
        else:
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.UnknownMethod",
                f"Unknown method: {method}",
            )

    def _on_menu_get_prop(self, _conn, _sender, _path, _iface, prop):
        if prop == "Version":
            return GLib.Variant("u", 3)
        if prop == "Status":
            return GLib.Variant("s", "normal")
        return None

    def _on_menu_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        items = self._menu_items()
        try:
            if method == "GetLayout":
                parent_id, _depth, _prop_names = params.unpack()
                if parent_id == 0:
                    children = [
                        GLib.Variant("(ia{sv}av)", (item_id, props, []))
                        for item_id, props in items.items()
                    ]
                    layout = (
                        0,
                        {"children-display": GLib.Variant("s", "submenu")},
                        children,
                    )
                else:
                    layout = (parent_id, items.get(parent_id, {}), [])
                invocation.return_value(
                    GLib.Variant("(u(ia{sv}av))", (self.revision, layout))
                )

            elif method == "GetGroupProperties":
                ids, _prop_names = params.unpack()
                result = [(i, items[i]) for i in ids if i in items]
                invocation.return_value(GLib.Variant("(a(ia{sv}))", (result,)))

            elif method == "GetProperty":
                item_id, name = params.unpack()
                value = items.get(item_id, {}).get(name, GLib.Variant("s", ""))
                invocation.return_value(GLib.Variant("(v)", (value,)))

            elif method == "Event":
                item_id, event_id, _data, _ts = params.unpack()
                if event_id == "clicked":
                    self._handle_click(item_id)
                invocation.return_value(None)

            elif method == "EventGroup":
                events = params.unpack()[0]
                for item_id, event_id, _data, _ts in events:
                    if event_id == "clicked":
                        self._handle_click(item_id)
                invocation.return_value(GLib.Variant("(ai)", ([],)))

            elif method == "AboutToShow":
                invocation.return_value(GLib.Variant("(b)", (False,)))

            elif method == "AboutToShowGroup":
                invocation.return_value(GLib.Variant("(aiai)", ([], [])))

            else:
                invocation.return_dbus_error(
                    "org.freedesktop.DBus.Error.UnknownMethod",
                    f"Unknown method: {method}",
                )
        except (TypeError, ValueError, KeyError) as exc:
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Invalid arguments: {exc}",
            )

    def _handle_click(self, item_id):
        if item_id == MENU_CONNECT:
            self.start_connect()
        elif item_id == MENU_DISCONNECT:
            self.disconnect_vpn()
        elif item_id == MENU_QUIT:
            self.loop.quit()

    def update_ui(self):
        self._reap_process()

        if self._is_tunnel_ready():
            new_state = "connected"
            new_icon = "mmu-vpn-connected"
            new_title = "MMU VPN: Connected"
        elif self.connecting or is_vpn_running():
            new_state = "connecting"
            new_icon = "mmu-vpn-connecting"
            new_title = "MMU VPN: Authenticating..."
        else:
            new_state = "disconnected"
            new_icon = "mmu-vpn-disconnected"
            new_title = "MMU VPN: Disconnected"

        if new_state != self.state:
            self.state = new_state
            self.icon_name = new_icon
            self.title = new_title

            self.bus.emit_signal(
                None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewIcon", None
            )
            self.bus.emit_signal(
                None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewTitle", None
            )
            self.bus.emit_signal(
                None,
                "/StatusNotifierItem",
                "org.kde.StatusNotifierItem",
                "NewStatus",
                GLib.Variant("(s)", ("Active",)),
            )

        menu_key = (self.state, self.disconnecting)
        if menu_key != self._menu_key:
            self._menu_key = menu_key
            self.revision += 1
            self.bus.emit_signal(
                None,
                "/MenuBar",
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                GLib.Variant("(ui)", (self.revision, 0)),
            )

        return True

    def _spawn_vpn(self):
        argv = [
            SETSID,
            "--wait",
            SUDO,
            "-n",
            OPENFORTIVPN,
            "-c",
            CONFIG,
            "--saml-login",
        ]

        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.NONE)
        launcher.set_stdin_file_path(os.devnull)

        # Open the log ourselves with O_NOFOLLOW and 0600 so it can never be a
        # symlink planted by another user and never world-readable.
        out_fd = os.open(
            LOG_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            os.fchmod(out_fd, 0o600)
            err_fd = os.dup(out_fd)
        except OSError:
            os.close(out_fd)
            raise

        launcher.take_stdout_fd(out_fd)
        launcher.take_stderr_fd(err_fd)
        self.proc = launcher.spawnv(argv)

    def start_connect(self):
        if self.connecting or self.disconnecting or is_vpn_running():
            return

        if not os.path.isfile(CONFIG):
            notify("MMU VPN", f"Configuration not found: {CONFIG}")
            return

        self.connecting = True
        self.disconnecting = False
        self.tunnel_logged_up = False
        self._dns_scheduled = False
        self.update_ui()

        try:
            self._spawn_vpn()
        except (GLib.Error, OSError) as exc:
            self.connecting = False
            notify("MMU VPN", f"Failed to start openfortivpn: {exc}")
            self.update_ui()
            return

        self._poll_saml_url(attempts=100)

    def _poll_saml_url(self, attempts):
        if not self.connecting:
            return

        if is_vpn_running():
            saml_url = extract_saml_url(read_log(), self._allowed_saml_hosts)
            if saml_url:
                self._open_browser(saml_url)
                return
        else:
            error = self._startup_error()
            if error:
                self.connecting = False
                notify("MMU VPN", f"Could not start VPN: {error}")
                self.update_ui()
                return

        if attempts <= 0:
            if is_vpn_running():
                self._open_browser(FALLBACK_VPN_URL)
                return
            self.connecting = False
            notify("MMU VPN", f"Timed out waiting for openfortivpn. Check {LOG_FILE}")
            self.update_ui()
            return

        GLib.timeout_add(300, self._poll_saml_url_tick, attempts - 1)

    def _poll_saml_url_tick(self, attempts):
        self._poll_saml_url(attempts)
        return False

    def _open_browser(self, url):
        if not is_allowed_saml_url(url, self._allowed_saml_hosts):
            notify("MMU VPN", "Refusing to open an unexpected login URL")
            self.disconnect_vpn()
            return

        try:
            Gio.Subprocess.new(["xdg-open", url], Gio.SubprocessFlags.NONE)
        except GLib.Error as exc:
            notify("MMU VPN", f"Failed to open browser: {exc.message}")
            self.disconnect_vpn()
            return

        self._poll_tunnel_ready(attempts=180)

    def _poll_tunnel_ready(self, attempts):
        if not self.connecting:
            return

        if not is_vpn_running():
            self.connecting = False
            notify("MMU VPN", f"Connection cancelled or failed. Check {LOG_FILE}")
            self.update_ui()
            return

        if self._is_tunnel_ready():
            if not self._dns_scheduled:
                self._dns_scheduled = True
                GLib.timeout_add(500, self._apply_dns_tick)
            return

        if attempts <= 0:
            self.connecting = False
            notify("MMU VPN", f"Timed out waiting for browser login. Check {LOG_FILE}")
            self.update_ui()
            return

        GLib.timeout_add(500, self._poll_tunnel_ready_tick, attempts - 1)

    def _poll_tunnel_ready_tick(self, attempts):
        self._poll_tunnel_ready(attempts)
        return False

    def _apply_dns_tick(self):
        self._apply_dns()
        return False

    def _apply_dns(self):
        try:
            proc = Gio.Subprocess.new(
                [SUDO, "-n", RESOLVECTL, "domain", "ppp0", "mmu.edu.my"],
                Gio.SubprocessFlags.STDERR_PIPE,
            )
            proc.communicate_utf8_async(None, None, self._on_dns_done, None)
        except GLib.Error as exc:
            self.connecting = False
            notify("MMU VPN", f"Connected, but resolvectl failed: {exc.message}")
            self.update_ui()

    def _on_dns_done(self, proc, result, _user_data):
        try:
            ok, _stdout, stderr = proc.communicate_utf8_finish(result)
            if not is_vpn_running():
                return
            if ok and proc.get_exit_status() == 0:
                notify("MMU VPN", "Connected (mmu.edu.my routed)")
            else:
                detail = (stderr or "").strip()[:300]
                notify("MMU VPN", f"Connected, but resolvectl failed: {detail}")
        except GLib.Error as exc:
            if is_vpn_running():
                notify("MMU VPN", f"Connected, but resolvectl error: {exc.message}")
        finally:
            self.connecting = False
            self.update_ui()

    def disconnect_vpn(self):
        if self.disconnecting:
            return

        self.connecting = False
        self.tunnel_logged_up = False
        self._dns_scheduled = False

        # If nothing was started by us and no matching process exists, there is
        # nothing to stop.
        if self.proc is None and not is_vpn_running():
            self.update_ui()
            return

        self.disconnecting = True
        self.update_ui()
        notify("MMU VPN", "Disconnecting...")
        self._send_disconnect_signal()
        self._poll_disconnect(attempts=30)

    def _send_disconnect_signal(self):
        try:
            Gio.Subprocess.new(
                [SUDO, "-n", PKILL, "-INT", "-x", "openfortivpn"],
                Gio.SubprocessFlags.NONE,
            )
            return True
        except GLib.Error as exc:
            notify("MMU VPN", f"Failed to stop openfortivpn: {exc.message}")
            return False

    def _poll_disconnect(self, attempts):
        if not self.disconnecting:
            return

        if is_vpn_running():
            # The process may have appeared just after the first signal; send
            # it again once the startup grace period has elapsed.
            if attempts == 25:
                self._send_disconnect_signal()
        elif attempts <= 25:
            # Give a just-spawned openfortivpn a moment to show up in /proc.
            self.disconnecting = False
            self.proc = None
            notify("MMU VPN", "Disconnected")
            self.update_ui()
            return

        if attempts <= 0:
            self.disconnecting = False
            notify("MMU VPN", "Disconnect timed out; check the openfortivpn process")
            self.update_ui()
            return

        GLib.timeout_add(300, self._poll_disconnect_tick, attempts - 1)

    def _poll_disconnect_tick(self, attempts):
        self._poll_disconnect(attempts)
        return False


def _quit_loop(loop):
    loop.quit()
    return GLib.SOURCE_REMOVE


def main():
    lock_fd = acquire_instance_lock()
    if lock_fd is None:
        notify("MMU VPN", "mmu-vpn-tray is already running")
        return 1

    loop = GLib.MainLoop()
    signal_add = GLibUnix.signal_add if GLibUnix is not None else GLib.unix_signal_add
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal_add(GLib.PRIORITY_DEFAULT, sig, _quit_loop, loop)

    VpnTrayService(loop)

    try:
        loop.run()
    finally:
        os.close(lock_fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
