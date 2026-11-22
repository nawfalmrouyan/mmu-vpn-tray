#!/usr/bin/env python3

# dependencies: openfortivpn python-gobject libnotify xdg-utils sudo systemd procps-ng

import fcntl
import os
import re
import shutil
import socket
import struct
from gi.repository import Gio, GLib

CONFIG = os.path.expanduser("~/.config/openfortivpn/mmu-vpn.conf")
FALLBACK_VPN_URL = "https://vpn.mmu.edu.my:443/remote/saml/start?redirect=1"
VPN_BIN = shutil.which("openfortivpn") or "/usr/bin/openfortivpn"
LOG_FILE = "/tmp/openfortivpn-mmu.log"

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
    try:
        for entry in os.scandir("/proc"):
            if entry.name.isdigit():
                try:
                    with open(os.path.join(entry.path, "comm"), "r") as f:
                        if f.read().strip() == "openfortivpn":
                            return True
                except OSError:
                    continue
    except OSError:
        pass
    return False


def has_ppp0_ipv4():
    if not os.path.exists("/sys/class/net/ppp0"):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            fcntl.ioctl(
                s.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack("256s", b"ppp0"),
            )
            return True
    except OSError:
        return False


def read_log():
    try:
        with open(LOG_FILE, "r") as log:
            return log.read()
    except OSError:
        return ""


def extract_saml_url(log_text):
    match = re.search(r"(https://[^\s'\"<>]+)", log_text)
    return match.group(1) if match else None


def notify(summary, body=""):
    try:
        Gio.Subprocess.new(["notify-send", summary, body], Gio.SubprocessFlags.NONE)
    except GLib.Error:
        pass


class VpnTrayService:
    def __init__(self, loop):
        self.loop = loop
        self.connecting = False
        self.tunnel_logged_up = False
        self.revision = 1
        self.state = "disconnected"
        self.icon_name = "mmu-vpn-disconnected"
        self.title = "MMU VPN: Disconnected"

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
                -1,
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

    def _menu_items(self):
        if self.state == "connected":
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
            1: {"label": GLib.Variant("s", status_label), "enabled": GLib.Variant("b", False)},
            2: {"type": GLib.Variant("s", "separator")},
            3: {"label": GLib.Variant("s", "Connect"), "enabled": GLib.Variant("b", can_connect)},
            4: {"label": GLib.Variant("s", "Disconnect"), "enabled": GLib.Variant("b", can_disconnect)},
            5: {"type": GLib.Variant("s", "separator")},
            6: {"label": GLib.Variant("s", "Quit Tray"), "enabled": GLib.Variant("b", True)},
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
            else:
                self.disconnect_vpn()
        invocation.return_value(None)

    def _on_menu_get_prop(self, _conn, _sender, _path, _iface, prop):
        if prop == "Version":
            return GLib.Variant("u", 3)
        if prop == "Status":
            return GLib.Variant("s", "normal")
        return None

    def _on_menu_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        items = self._menu_items()

        if method == "GetLayout":
            parent_id, _depth, _prop_names = params.unpack()
            if parent_id == 0:
                children = [
                    GLib.Variant("(ia{sv}av)", (item_id, props, []))
                    for item_id, props in items.items()
                ]
                layout = (0, {"children-display": GLib.Variant("s", "submenu")}, children)
            else:
                layout = (parent_id, items.get(parent_id, {}), [])
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, layout)))

        elif method == "GetGroupProperties":
            ids, _prop_names = params.unpack()
            result = [(i, items[i]) for i in ids if i in items]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (result,)))

        elif method == "GetProperty":
            item_id, name = params.unpack()
            val = items.get(item_id, {}).get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (val,)))

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
            invocation.return_value(None)

    def _handle_click(self, item_id):
        if item_id == 3:
            self.start_connect()
        elif item_id == 4:
            self.disconnect_vpn()
        elif item_id == 6:
            self.loop.quit()

    def update_ui(self):
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
            self.revision += 1

            self.bus.emit_signal(
                None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewIcon", None
            )
            self.bus.emit_signal(
                None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewTitle", None
            )
            self.bus.emit_signal(
                None,
                "/MenuBar",
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                GLib.Variant("(ui)", (self.revision, 0)),
            )

        return True

    def start_connect(self):
        if self.connecting or is_vpn_running():
            return

        self.connecting = True
        self.tunnel_logged_up = False
        self.update_ui()

        cmd = f'setsid sudo {VPN_BIN} -c "{CONFIG}" --saml-login >"{LOG_FILE}" 2>&1 </dev/null &'
        try:
            Gio.Subprocess.new(["/bin/sh", "-c", cmd], Gio.SubprocessFlags.NONE)
        except GLib.Error as e:
            self.connecting = False
            notify("MMU VPN", f"Failed to start openfortivpn: {e.message}")
            self.update_ui()
            return

        self._poll_saml_url(attempts=30)

    def _poll_saml_url(self, attempts):
        if not self.connecting:
            return
        if is_vpn_running():
            log_text = read_log()
            saml_url = extract_saml_url(log_text)
            if saml_url:
                self._open_browser(saml_url)
                return
        if attempts <= 0:
            if is_vpn_running():
                self._open_browser(FALLBACK_VPN_URL)
                return
            self.connecting = False
            notify("MMU VPN", f"Timed out waiting for openfortivpn. Check {LOG_FILE}")
            self.update_ui()
            return
        GLib.timeout_add(300, lambda: (self._poll_saml_url(attempts - 1), False)[1])

    def _open_browser(self, url):
        try:
            Gio.Subprocess.new(["xdg-open", url], Gio.SubprocessFlags.NONE)
        except GLib.Error as e:
            self.connecting = False
            notify("MMU VPN", f"Failed to open browser: {e.message}")
            self.update_ui()
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
            GLib.timeout_add(500, lambda: (self._apply_dns(), False)[1])
            return
        if attempts <= 0:
            self.connecting = False
            notify("MMU VPN", f"Timed out waiting for browser login. Check {LOG_FILE}")
            self.update_ui()
            return
        GLib.timeout_add(500, lambda: (self._poll_tunnel_ready(attempts - 1), False)[1])

    def _apply_dns(self):
        try:
            proc = Gio.Subprocess.new(
                ["sudo", "resolvectl", "domain", "ppp0", "mmu.edu.my"],
                Gio.SubprocessFlags.STDERR_PIPE,
            )
            proc.communicate_utf8_async(None, None, self._on_dns_done, None)
        except GLib.Error as e:
            self.connecting = False
            notify("MMU VPN", f"Connected, but resolvectl failed: {e.message}")
            self.update_ui()

    def _on_dns_done(self, proc, result, _user_data):
        try:
            ok, _stdout, stderr = proc.communicate_utf8_finish(result)
            if ok and proc.get_exit_status() == 0:
                notify("MMU VPN", "Connected (mmu.edu.my routed)")
            else:
                notify("MMU VPN", f"Connected, but resolvectl failed: {(stderr or '').strip()}")
        except GLib.Error as e:
            notify("MMU VPN", f"Connected, but resolvectl error: {e.message}")
        finally:
            self.connecting = False
            self.update_ui()

    def disconnect_vpn(self):
        if is_vpn_running():
            try:
                Gio.Subprocess.new(
                    ["sudo", "pkill", "-INT", "openfortivpn"],
                    Gio.SubprocessFlags.NONE,
                )
            except GLib.Error:
                pass
            notify("MMU VPN", "Disconnected")
        self.connecting = False
        self.tunnel_logged_up = False
        self.update_ui()


if __name__ == "__main__":
    loop = GLib.MainLoop()
    VpnTrayService(loop)
    loop.run()
