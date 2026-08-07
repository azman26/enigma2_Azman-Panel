# Azman Panel

Centralny panel narzędziowy dla dekoderów Enigma2.

Azman Panel służy do instalowania i zarządzania pluginami, listami kanałów, źródłami EPG, piconami oraz innymi dodatkami z ekosystemu Azman.

## Instalacja

1. Pobierz najnowszy plik IPK z sekcji [Releases](../../releases).
2. Skopiuj go do katalogu `/tmp` na dekoderze.
3. Połącz się z dekoderem przez SSH i wykonaj:

```sh
opkg install /tmp/enigma2-plugin-extensions--azman-azmanpanel_2026.08.07-2151_all.ipk
```

4. Uruchom ponownie interfejs Enigma2:

```sh
systemctl restart enigma2
```

Po restarcie Azman Panel będzie dostępny w menu wtyczek.

## Funkcje

- instalowanie pluginów Azman,
- obsługa pakietów IPK,
- bukiety i listy kanałów,
- źródła EPG,
- instalacja piconów,
- informacje o wersjach,
- obsługa narzędzi Enigma2,
- wybór pakietów dopasowanych do środowiska dekodera.

## Kompatybilność

Azman Panel jest przygotowany do pracy z różnymi image Enigma2, między innymi:

- OpenATV,
- OpenPLi,
- OpenViX,
- OpenHDF,
- innymi zgodnymi image Enigma2.

Pakiet Azman Panel ma architekturę `all` i jest przeznaczony dla środowisk Python 3.12–3.14.

## Struktura projektu

```text
AzmanPanel/
├── plugin.py
├── screens.py
├── workers.py
├── runtime.py
├── utils.py
├── config.py
├── constants.py
├── panel_skin.xml
├── plugin.png
└── icons/
```

## Wersjonowanie

Format wersji:

```text
YYYY.MM.DD-HHMM
```

Aktualna wersja:

```text
2026.08.07-2151
```

## Licencja

Azman Panel jest udostępniany na licencji:

```text
GPL-2.0-or-later
```

Szczegóły znajdują się w pliku [LICENSE](LICENSE).

## Wydania

Gotowe pakiety IPK są publikowane w sekcji [GitHub Releases](../../releases).

Najnowszy pakiet:

```text
enigma2-plugin-extensions--azman-azmanpanel_2026.08.07-2151_all.ipk
```

## Rozwój projektu

Azman Panel będzie rozwijany jako centralny panel ekosystemu Azman. W przyszłości planowane są:

- prywatny feed pluginów,
- automatyczny wybór IPK według wersji Pythona,
- chronione listy kanałów i picony.
