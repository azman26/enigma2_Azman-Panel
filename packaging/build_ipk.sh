#!/bin/sh
set -eu

SOURCE_DIR=${SOURCE_DIR:-/source}
OUTPUT_DIR=${OUTPUT_DIR:-/output}
PACKAGE_OUTPUT_DIR="$OUTPUT_DIR/all"
PACKAGE_DIR=/tmp/ipk-root
INSTALL_DIR="$PACKAGE_DIR/usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel"

# Wersja jest znaczona czasem builda (YYYY.MM.DD-HHMM), więc nikt nie musi
# już ręcznie wpisywać jej w constants.py ani packaging/control. Ustaw
# zmienną środowiskową VERSION przed uruchomieniem, żeby wymusić konkretną
# wartość (np. przy odtwarzaniu wcześniejszego builda).
VERSION=${VERSION:-$(date -u +%Y.%m.%d-%H%M)}

rm -rf "$PACKAGE_DIR"
mkdir -p "$INSTALL_DIR" "$PACKAGE_OUTPUT_DIR"

find "$SOURCE_DIR" -maxdepth 1 -type f -name '*.py' -exec cp {} "$INSTALL_DIR"/ \;
sed -i "s/^PLUGIN_VERSION = .*/PLUGIN_VERSION = \"$VERSION\"/" "$INSTALL_DIR/constants.py"
cp "$SOURCE_DIR"/panel_skin.xml "$INSTALL_DIR"/
cp "$SOURCE_DIR"/plugin.png "$INSTALL_DIR"/
cp -R "$SOURCE_DIR"/icons "$INSTALL_DIR"/
mkdir -p "$PACKAGE_DIR/CONTROL"
sed "s/^Version: .*/Version: $VERSION/" "$SOURCE_DIR"/packaging/control > "$PACKAGE_DIR/CONTROL/control"
cp "$SOURCE_DIR"/packaging/prerm "$PACKAGE_DIR/CONTROL/prerm"
chmod 0755 "$PACKAGE_DIR/CONTROL/prerm"

opkg-build -o root -g root "$PACKAGE_DIR" "$PACKAGE_OUTPUT_DIR"

echo "IPK zapisany w: $PACKAGE_OUTPUT_DIR (wersja $VERSION)"
