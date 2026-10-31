# Azman Panel

Centralny panel narzędziowy dla dekoderów Enigma2.

Instalowanie i aktualizowanie wtyczek Azman, bukietów, źródeł EPG, piconów oraz dodatkowych narzędzi.

Strona projektu: **[topolowa4.pl](https://www.topolowa4.pl/)**.

## Instalacja

Instalator SSH pobiera najnowszy pakiet wskazany w manifeście:

```sh
wget -q --no-check-certificate https://raw.githubusercontent.com/azman26/enigma2_Azman-Panel/main/installer.sh -O - | /bin/sh
```

Alternatywnie pobierz IPK z [najnowszego wydania](https://github.com/azman26/enigma2_Azman-Panel/releases/latest), skopiuj go do `/tmp` na dekoderze i zainstaluj:

```sh
opkg install /tmp/enigma2-plugin-extensions--azman-azmanpanel_YYYY.MM.DD-HHMM_all.ipk
```

Zastąp `YYYY.MM.DD-HHMM` numerem pobranego pakietu. Po instalacji wybierz w menu dekodera **Restart GUI** (restart interfejsu Enigma2).

Panel jest dostępny w menu wtyczek. Widoczność w głównym menu Enigma2 można włączyć w zakładce **Informacje**.

## Zakładki

- **Pluginy** — instalacja wtyczek Azman.
- **Bukiety/Listy kanałów** — listy kanałów telewizyjnych i stacji radiowych.
- **EPG/Picony** — polskie źródła EPG i picony.
- **Narzędzia/Inne wtyczki** — dodatkowe narzędzia dla Enigma2.
- **Aktualizacje** — sprawdzanie i instalowanie dostępnych aktualizacji.
- **Informacje** — wersja Panelu i jego ustawienia.

## EPG

Panel korzysta z tego samego mechanizmu EPG co FTVP: automatycznej rejestracji dostępu do API, mapowania kanałów i pobierania wydarzeń dla własnych bukietów. Import odbywa się po zapisaniu bukietu, przy starcie GUI i co 12 godzin. Dostępność programu zależy od danych źródłowych dla danego kanału.

## Środowisko

Pakiet ma architekturę `all` i jest przeznaczony dla środowisk Enigma2 z Pythonem 3.12–3.14. Przed instalacją sprawdź wersję Pythona w swoim obrazie.

## Wydania i aktualizacje

Gotowe pakiety są dostępne w [GitHub Releases](https://github.com/azman26/enigma2_Azman-Panel/releases). Bieżący adres IPK, wersję i sumę SHA-256 zawiera [manifest aktualizacji](feed/manifest.json).

Wersje mają format `YYYY.MM.DD-HHMM`.

Push zmian kodu wtyczki na `main` automatycznie uruchamia budowę IPK, tworzenie GitHub Release i aktualizację wpisu `azman-panel` w manifeście. Pozostałe pakiety feedu są zachowywane.

Numer wydania jest nadawany według czasu `Europe/Warsaw`. Builder wpisuje go do kodu i metadanych wewnątrz pakietu. Źródła mogą zawierać wersję bazową; opublikowaną wersję wskazuje manifest.

Ręczne **Run workflow** również publikuje wydanie i pozwala podać numer wersji. Zmiana samego README lub manifestu nie uruchamia nowego wydania.

Instrukcje budowania lokalnego: [packaging/README.md](packaging/README.md).

## Licencja

[GPL-2.0-or-later](LICENSE).
