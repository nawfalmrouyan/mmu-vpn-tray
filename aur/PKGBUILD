# Maintainer: Nawfal Mrouyan <https://github.com/nawfalmrouyan>
pkgname=mmu-vpn-tray
pkgver=1.0.0
pkgrel=1
pkgdesc="Tray StatusNotifierItem for Multimedia University Fortinet SAML VPN"
arch=('any')
url="https://github.com/nawfalmrouyan/mmu-vpn-tray"
license=('custom')
depends=(
    'python'
    'python-gobject'
    'openfortivpn'
    'libnotify'
    'xdg-utils'
    'sudo'
    'systemd'
    'procps-ng'
)
optdepends=(
    'hyprland: Wayland compositor'
    'waybar: Status bar with SNI tray support'
)
install="${pkgname}.install"
source=("git+${url}.git#tag=v${pkgver}")
sha256sums=('SKIP')

package() {
    cd "${srcdir}/${pkgname}"

    install -Dm755 mmu-vpn-tray.py "${pkgdir}/usr/bin/mmu-vpn-tray"
    install -Dm644 mmu-vpn-tray.desktop "${pkgdir}/usr/share/applications/mmu-vpn-tray.desktop"

    install -Dm644 mmu-vpn-tray/mmu-vpn-connected.svg "${pkgdir}/usr/share/icons/mmu-vpn-tray/mmu-vpn-connected.svg"
    install -Dm644 mmu-vpn-tray/mmu-vpn-connecting.svg "${pkgdir}/usr/share/icons/mmu-vpn-tray/mmu-vpn-connecting.svg"
    install -Dm644 mmu-vpn-tray/mmu-vpn-disconnected.svg "${pkgdir}/usr/share/icons/mmu-vpn-tray/mmu-vpn-disconnected.svg"

    install -Dm644 mmu-vpn-tray/mmu-vpn-connected.svg "${pkgdir}/usr/share/icons/hicolor/scalable/apps/mmu-vpn-tray.svg"

    install -Dm644 openfortivpn/mmu-vpn.conf "${pkgdir}/usr/share/doc/mmu-vpn-tray/mmu-vpn.conf.example"
    install -Dm644 sudoers.d/openfortivpn "${pkgdir}/usr/share/doc/mmu-vpn-tray/openfortivpn.sudoers.example"
}
