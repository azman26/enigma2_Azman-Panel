# Budowanie IPK Azman Panel

`build_ipk.py` korzysta wylacznie z biblioteki standardowej Pythona.
`opkg-build` ani Docker nie sa wymagane. Builder sprawdza wymagane pliki,
skladnie modulow, metadane i format wersji.

IPK instaluje moduly Python, skorke XML i ikony do:
`/usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/`.
Nie zawiera feedu, dokumentacji, skryptow pakowania ani danych kont.

## Automatyczne wydanie

Push zmian pluginu na `main` uruchamia workflow. Workflow nadaje wersje,
buduje IPK, tworzy Release przypiety do commita zrodlowego, dolacza pakiet,
pobiera go ponownie i sprawdza SHA256. Potem aktualizuje manifest.
Wpis Panelu wskazuje publiczny plik z GitHub Releases (`protected: false`).
Inne pakiety manifestu pozostaja bez zmian.

Ponowienie przebiegu dla tego samego commita uzywa jego istniejacego taga.
Reczny `Run workflow` tez publikuje wydanie, a nie tylko artefakt.

## Build lokalny w PowerShell

Uruchom z glownego katalogu sklonowanego repozytorium:

```powershell
$env:SOURCE_DIR = (Get-Location).Path
$env:OUTPUT_DIR = Join-Path (Get-Location) 'build/ipk'
$env:VERSION = '2026.10.31-1333' # ustaw wersje do budowania
python packaging/build_ipk.py
```

Wynik: `build/ipk/all/*.ipk`. Wersja trafia do kodu i metadanych wewnatrz
IPK; builder nie zmienia plikow zrodlowych.

## Opcjonalny Docker

Z katalogu repozytorium:

```powershell
docker build -t azman-panel-ipk packaging
New-Item -ItemType Directory -Force build/ipk | Out-Null
docker run --rm -e VERSION=2026.10.31-1333 -v "${PWD}:/source:ro" -v "${PWD}/build/ipk:/output" azman-panel-ipk
```

`build_ipk.sh` jest wrapperem buildera dla srodowisk z poleceniem `python`.
Obie metody korzystaja z tego samego `build_ipk.py`.
