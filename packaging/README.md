# Budowanie publicznego IPK Azman Panel

Pierwszy pakiet jest publiczny i zawiera pliki `.py`, ponieważ musi działać jako panel startowy na wielu wersjach Pythona.

Docelowa nazwa:

```text
enigma2-plugin-extensions--azman-azmanpanel_2026.08.07-2151_all.ipk
```

Pakiet musi instalować zawartość do:

```text
/usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/
```

Do utworzenia IPK potrzebne będzie narzędzie `opkg-build`, najlepiej uruchomione w środowisku Linux/Docker zgodnym z Enigma2. Na Windowsie przygotowujemy strukturę pakietu, ale końcowe archiwum budujemy w środowisku Linux.

## Build przez Docker

Po uruchomieniu Docker Desktop z katalogu głównego projektu:

```powershell
docker build -t azman-panel-ipk "00 AzmanPanel/packaging"
New-Item -ItemType Directory -Force build\ipk | Out-Null
docker run --rm -v "${PWD}\00 AzmanPanel:/source:ro" -v "${PWD}\build\ipk:/output" azman-panel-ipk
```

Gotowy plik IPK zostanie zapisany w `build/ipk`.
