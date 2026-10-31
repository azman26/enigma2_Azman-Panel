# Azman Panel

Centralny panel narzędziowy dla dekoderów Enigma2.

Azman Panel służy do instalowania i zarządzania pluginami, listami kanałów, źródłami EPG, piconami oraz innymi dodatkami z ekosystemu Azman.

## Instalacja

Najprostsza instalacja przez SSH — pobierze i zainstaluje najnowszą wersję Azman Panel:

```sh
wget -q --no-check-certificate https://raw.githubusercontent.com/azman26/enigma2_Azman-Panel/main/installer.sh -O - | /bin/sh
```

Alternatywnie pobierz IPK z Releases, skopiuj go na dekoder i zainstaluj:

```sh
opkg install /tmp/enigma2-plugin-extensions--azman-azmanpanel_YYYY.MM.DD-HHMM_all.ipk
```

Po zakończeniu instalacji uruchom ponownie interfejs Enigma2:

```sh
systemctl restart enigma2
```

Azman Panel będzie dostępny w menu wtyczek oraz — po włączeniu tej opcji w zakładce Info — w głównym menu Enigma2.

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

## Licencja

Azman Panel jest udostępniany na licencji:

```text
GPL-2.0-or-later
```

Szczegóły znajdują się w pliku [LICENSE](LICENSE).

## Wydania

Gotowe pakiety IPK są publikowane w sekcji [GitHub Releases](../../releases).

## Publikowanie zmian

Push zmian pluginu na `main` automatycznie uruchamia budowanie IPK,
tworzenie GitHub Release i aktualizacje wpisu `azman-panel` w `feed/manifest.json`.
Pozostale pakiety feedu sa zachowywane. Nie trzeba recznie tworzyc Release.

Numer wydania `YYYY.MM.DD-HHMM` jest nadawany automatycznie wedlug czasu
Europe/Warsaw. Builder wpisuje go do kodu i metadanych wewnatrz gotowego IPK.
Wersje opublikowana wskazuje manifest; zrodla moga zawierac wersje bazowa.
Reczny `Run workflow` tez publikuje wydanie. Zmiana samego manifestu lub
glownej dokumentacji nie uruchamia nowego wydania.

Instrukcje budowania lokalnego: [packaging/README.md](packaging/README.md).
