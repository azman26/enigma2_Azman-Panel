#!/bin/sh

set -eu

MANIFEST_URL="https://raw.githubusercontent.com/azman26/enigma2_Azman-Panel/main/feed/manifest.json"
TMP_DIR="/tmp/.azmanpanel-installer"
IPK_FILE="$TMP_DIR/azman-panel.ipk"

download_file() {
    url="$1"
    target="$2"

    if command -v wget >/dev/null 2>&1; then
        wget -q --no-check-certificate "$url" -O "$target"
        return
    fi

    if command -v curl >/dev/null 2>&1; then
        curl -fsSLk "$url" -o "$target"
        return
    fi

    echo "Blad: brak wget i curl."
    exit 1
}

cleanup() {
    rm -rf "$TMP_DIR"
}

trap cleanup EXIT INT TERM

if [ "$(id -u)" != "0" ]; then
    echo "Blad: uruchom instalator jako root."
    exit 1
fi

mkdir -p "$TMP_DIR"
MANIFEST_FILE="$TMP_DIR/manifest.json"

echo "Pobieranie informacji o najnowszym Azman Panel..."
download_file "$MANIFEST_URL" "$MANIFEST_FILE"

PACKAGE_URL=$(sed -n '/"id"[[:space:]]*:[[:space:]]*"azman-panel"/,/"protected"[[:space:]]*:/ s/.*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST_FILE" | head -n 1)
PACKAGE_SHA256=$(sed -n '/"id"[[:space:]]*:[[:space:]]*"azman-panel"/,/"protected"[[:space:]]*:/ s/.*"sha256"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST_FILE" | head -n 1)
PACKAGE_VERSION=$(sed -n '/"id"[[:space:]]*:[[:space:]]*"azman-panel"/,/"protected"[[:space:]]*:/ s/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST_FILE" | head -n 1)

if [ -z "$PACKAGE_URL" ] || [ -z "$PACKAGE_SHA256" ]; then
    echo "Blad: manifest nie zawiera poprawnej paczki Azman Panel."
    exit 1
fi

echo "Pobieranie Azman Panel ${PACKAGE_VERSION:-najnowsza wersja}..."
download_file "$PACKAGE_URL" "$IPK_FILE"

if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA256=$(sha256sum "$IPK_FILE" | awk '{print $1}')
    if [ "$ACTUAL_SHA256" != "$PACKAGE_SHA256" ]; then
        echo "Blad: nieprawidlowa suma SHA-256 pobranej paczki."
        exit 1
    fi
    echo "Suma SHA-256 poprawna."
else
    echo "Uwaga: brak sha256sum, pomijam lokalna weryfikacje sumy."
fi

echo "Instalowanie Azman Panel..."
opkg update
opkg --force-reinstall install "$IPK_FILE"

echo "Azman Panel zostal zainstalowany. Zalecany jest restart GUI Enigma2."
