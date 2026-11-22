# Maintainer: Nawfal bin Mohmad Rouyan <https://github.com/nawfalmrouyan>
pkgname=mmu-vpn-tray-git
pkgver=r1.0.0
pkgrel=1
pkgdesc="Tray StatusNotifierItem for Multimedia University Fortinet SAML VPN (development git branch)"
arch=('any')
url="https://github.com/nawfalmrouyan/mmu-vpn-tray"
license=('BSD-3-Clause')
depends=(
    'python'
    'python-gobject'
    'libayatana-appindicator-glib'
    'openfortivpn'
    'libnotify'
    'xdg-utils'
    'sudo'
    'systemd'
    'procps-ng'
)
makedepends=(
    'git'
)
optdepends=(
    'hyprland: Wayland compositor'
    'waybar: Status bar with SNI tray support'
)
provides=('mmu-vpn-tray')
conflicts=('mmu-vpn-tray')
install="mmu-vpn-tray.install"
source=("${pkgname}::git+${url}.git")
sha256sums=('SKIP')

pkgver() {
    cd "${srcdir}/${pkgname}"
    if git describe --long --tags >/dev/null 2>&1; then
        git describe --long --tags | sed 's/^v//;s/\([^-]*-g\)/r\1/;s/-/./g'
    else
        printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short=7 HEAD)"
    fi
}

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
    install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}
