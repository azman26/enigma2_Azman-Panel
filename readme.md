# Azman Panel

Centralny panel narzędziowy ekosystemu Azman dla Enigma2.

Azman Panel jest instalowany jako pierwszy plugin na dekoderze. Z niego będą instalowane pozostałe pluginy Azman, bukiety, listy kanałów, EPG, picony i inne narzędzia z własnego feeda.

## Aktualna wersja

- Wersja wydania: `2026.08.07-2151`
- Format: `YYYY.MM.DD-HHMM`
- Build: `azman-panel-2026.08.07-2039`

Wersja jest wyświetlana wyłącznie na dolnej belce jako `v...`.

## Zrobione

### Pierwszy ekran

- układ kafelkowy 6×3,
- turkusowa kolorystyka,
- nagłówek `Azman Panel`,
- aktywny kafelek i opis,
- wersja na dolnej belce,
- tekstowe akcje kolorowych przycisków bez grafik OK/EXIT,
- czerwony: `Zamknij`, żółty: poprzednia zakładka, niebieski: następna zakładka.

### Zakładki

- `Pluginy`
- `Bukiety/Listy kanałów`
- `EPG/Picony`
- `Narzędzia/Inne wtyczki`
- `Info`

### Kafelki pluginów

- Azman Player,
- Stacja Meteo MMz,
- IMGW Meteo,
- Shelly Control Center,
- Karcher Radio Control,
- MiHome Control,
- YT Playlist Player,
- Monitoring Burz,
- Kalendarz Ogrodnika.

### Kafelki danych i narzędzi

- Bukiety IPTV PL,
- Bukiety FAST,
- IPTV.ORG,
- Polskie źródła EPG,
- Picons,
- M3UIPTV,
- Azman OPKG Feed,
- Dodatki do E2K,
- ArchivCZSK,
- AJPanel.

### Info

Zakładka nie zawiera kafelków. Po jej otwarciu pokazuje bezpośrednio opis Azman Panelu i jego wersję.

## Ikony

Kafelki korzystają z ikon z katalogu `icons`, m.in.:

- `icon_azmanplayer.png`,
- `icon_stacjameteommz.png`,
- `icon_imgwmeteo.png`,
- `icon_shellycontrolcenter.png`,
- `icon_karcherradiocontrol.png`,
- `icon_mihomecontrol.png`,
- `icon_ytplaylistplayer.png`,
- `icon_monitoringburz.png`,
- `icon_m3uiptv.png`,
- `icon_kalendarzogrod.png`.

Dla projektów bez dedykowanej grafiki używany jest `icon_placeholder.png`.

## Pozostałe zadania

## Plan realizacji feeda — kolejność prac

### Etap 1 — publiczny Azman Panel `all` **[ZAKOŃCZONY]**

- [x] przygotować strukturę instalacyjną IPK,
- [x] sprawdzić poprawność pakietu i metadanych,
- [x] upewnić się, że pakiet zawiera `panel_skin.xml` oraz wszystkie ikony,
- [x] utworzyć `enigma2-plugin-extensions--azman-azmanpanel_YYYY.MM.DD-HHMM_all.ipk`,
- [x] zainstalować IPK testowo na dekoderze.

### Etap 2 — publiczna publikacja IPK

- [ ] utworzyć GitHub Release dla Azman Panelu,
- [ ] dodać plik IPK jako asset release,
- [ ] opublikować sumę SHA-256,
- [ ] przygotować publiczny `azman-feed.conf`,
- [ ] przetestować instalację na świeżym dekoderze.

### Etap 3 — prywatny feed pluginów

- [ ] przygotować IPK pierwszego chronionego pluginu dla Python 3.13,
- [ ] usunąć z niego pliki `.py`,
- [ ] opublikować IPK na `topolowa4.pl`,
- [ ] wygenerować `Packages` i `Packages.gz`,
- [ ] dodać warianty Python 3.12 i 3.14,
- [ ] podłączyć wybór pakietu przez manifest.

### Etap 4 — autoryzacja użytkowników

- [ ] przygotować whitelistę użytkowników,
- [ ] dodać parowanie boxa kodem,
- [ ] generować osobny token dla każdego urządzenia,
- [ ] obsłużyć limit 1–3 urządzeń,
- [ ] dodać wygaszanie i unieważnianie tokenów.

### Etap 5 — prywatne listy kanałów i picony

- [ ] przenieść dane do prywatnego magazynu FTP/SFTP,
- [ ] dodać pobieranie przez autoryzowane HTTPS API,
- [ ] generować krótkotrwałe linki,
- [ ] zablokować anonimowe indeksowanie katalogów,
- [ ] przetestować pobieranie bouquetów i piconów z panelu.

### Stabilizacja UI

- [ ] Przetestować pierwszy ekran na SF8008/OpenATV 7.6.
- [ ] Sprawdzić czytelność wszystkich nazw kafelków.

### Feed Azman

- [ ] Zapewnić instalację i aktualizację Azman OPKG Feed.
- [ ] Zbudować manifest pluginów Azman.
- [ ] W manifeście przechowywać nazwę, identyfikator, pakiet, wersję, ikonę, kategorię, opis i zależności.
- [ ] Zastąpić ręczne przypisywanie pluginów w `screens.py` danymi z manifestu.
- [ ] Dodać statusy: `Zainstalowany`, `Dostępna aktualizacja`, `Dostępny`, `Błąd`.

### Instalacja pluginów

- [ ] Dodać akcje `Zainstaluj`, `Aktualizuj`, `Otwórz` i `Odinstaluj`.
- [ ] Nie zakładać obecności żadnego pluginu poza Azman Panelem.
- [ ] Dodać sprawdzanie nazw pakietów i zależności.

### Bezpieczeństwo i stabilność

- [ ] Usunąć `curl/wget | sh`.
- [x] Naprawić logger w `utils.py`.
- [x] Poprawić ZIP path traversal.
- [x] Dodać walidację nazw bukietów i ścieżek.
- [x] Wprowadzić atomowy zapis plików Enigma2.
- [ ] Dodać limity rozmiaru pobieranych plików.

### Dokumentacja i testy

- [ ] Ujednolicić kodowanie plików do UTF-8.
- [ ] Dodać testy parserów pakietów, bukietów i manifestu.
- [ ] Dodać testy filtrowania zakładek i kafelków.
- [ ] Opisać budowanie i instalację pluginu.

## Docelowy przepływ

```text
Świeży dekoder
    ↓
Instalacja Azman Panel
    ↓
Konfiguracja Azman Feed
    ↓
Lista pluginów, bukietów, EPG i narzędzi
    ↓
Instalacja oraz aktualizacja wybranych komponentów
```

## Kontrola techniczna

- Python `compileall`: OK.
- XML skórki: OK.
- Test na fizycznym dekoderze: do wykonania.

## Docelowa dystrybucja i ochrona pluginów

### Założenia

Azman Panel jest publicznym pluginem instalowanym jako pierwszy na dekoderze. Pozostałe pluginy są budowane prywatnie i udostępniane użytkownikowi jako IPK bez plików źródłowych `.py`.

```text
Publiczny GitHub
└── Azman Panel
    └── wykrywa wersję Python/OpenATV
        └── pobiera właściwy IPK z feeda Azman

topolowa4.pl
├── feed IPK
│   ├── Packages
│   ├── Packages.gz
│   └── pliki *.ipk bez .py
└── API dostępu do danych

Prywatne zaplecze FTP/SFTP
├── listy kanałów
└── picony
```

### Budowanie IPK

Pakiety pluginów są tworzone na komputerze lub w prywatnym procesie CI:

```text
kod źródłowy .py
    ↓
kompilacja dla konkretnej wersji Pythona
    ↓
pliki .pyc
    ↓
usunięcie plików .py
    ↓
utworzenie IPK
    ↓
SHA-256 i publikacja w feedzie
```

Wersja Python musi być uwzględniona w wariancie pakietu, niezależnie od używanego image Enigma2, np.:

```text
enigma2-plugin-extensions--azman-imgwmeteo-py312_..._all.ipk
enigma2-plugin-extensions--azman-imgwmeteo-py313_..._all.ipk
enigma2-plugin-extensions--azman-imgwmeteo-py314_..._all.ipk
```

Azman Panel wykrywa wersję Pythona, architekturę procesora i podstawowe informacje o image, a następnie wybiera właściwy pakiet. OpenATV 7.6/Python 3.13 jest jednym z testowanych środowisk, ale nie jedynym obsługiwanym image.

W kodzie panelu działa już wybór feeda środowiskowego. Kolejność prób to tag Pythona, architektura, `all`, a następnie dotychczasowy publiczny feed kompatybilności. Brak katalogu wariantowego na serwerze nie blokuje starszych instalacji.

W pierwszej kolejności sprawdzane są:

- wersja Python (`3.12`, `3.13`, `3.14`),
- architektura boxa (`all`, `arm`, `arm64`, `mipsel` itp.),
- obecność wymaganych komponentów Enigma2,
- opcjonalnie nazwa i wersja image (`OpenATV`, `OpenPLi`, `OpenViX`, `OpenHDF` i inne).

Jeżeli plugin jest czysto pythonowy i nie zawiera bibliotek binarnych, może być oznaczony jako `all` dla danej wersji Pythona. Pakiety z bibliotekami `.so` wymagają osobnych wariantów według architektury i ABI.

### Feed IPK

Feed jest udostępniany przez HTTPS na stronie `topolowa4.pl`. Azman Panel pobiera manifest, sprawdza zgodność pakietu, weryfikuje sumę SHA-256 i instaluje IPK przez `opkg`.

Kod źródłowy chronionych pluginów nie powinien znajdować się w publicznych repozytoriach GitHub. Publiczny pozostaje Azman Panel oraz dokumentacja.

### Listy kanałów i picony

Listy kanałów i picony są przechowywane na prywatnym zapleczu FTP/SFTP. Nie powinny być dostępne przez stałe, publiczne adresy.

Docelowy dostęp:

```text
Azman Panel
    ↓
autoryzacja boxa przez HTTPS API
    ↓
krótkotrwały token lub link
    ↓
pobranie listy kanałów albo paczki piconów
    ↓
wygaśnięcie tokena
```

FTP/SFTP służy do przechowywania i administracji. Użytkownicy pobierają dane przez panel i autoryzowane HTTPS API.

### Granice ochrony

IPK bez `.py`, pliki `.pyc`, autoryzacja i krótkotrwałe linki utrudniają kopiowanie oraz masowe pobieranie. Nie zapewniają jednak pełnej ochrony przed właścicielem dekodera z dostępem `root`, ponieważ każdy kod i plik pobrany na box może zostać skopiowany.

Najważniejszą logikę, dane dostępowe i wartościowe listy należy w miarę możliwości obsługiwać po stronie serwera. Na dekoderze powinien pozostać klient Azman Panelu.

## Planowana autoryzacja użytkowników i tokeny

W przyszłości prywatne pluginy, listy kanałów i picony będą dostępne wyłącznie dla użytkowników zatwierdzonych na whiteliście.

### Whitelist użytkowników

Administrator dodaje użytkownika wraz z informacją o forum, z którego pochodzi, np.:

```text
Login: MikiMouse
Forum: sat-4-all
Status: aktywny
Limit urządzeń: 3
```

Forum służy wyłącznie jako informacja administracyjna i nie jest sekretem ani częścią tokena.

### Parowanie boxa

Podczas pierwszej próby pobrania chronionego zasobu Azman Panel pokazuje jednorazowy kod parowania. Użytkownik przekazuje administratorowi login i kod urządzenia. Po zatwierdzeniu serwer automatycznie przypisuje instalację do konta i wydaje token.

```text
Azman Panel
    ↓
jednorazowy kod parowania
    ↓
administrator sprawdza whitelistę
    ↓
serwer przypisuje urządzenie do konta
    ↓
panel otrzymuje osobny token
```

### Wiele urządzeń

Jedno konto może mieć kilka osobnych urządzeń. Każdy box otrzymuje własny identyfikator i token:

```text
MikiMouse
├── SF8008 — salon — aktywny
├── VU+ — sypialnia — aktywny
└── Octagon — domek — aktywny
```

Limit urządzeń będzie ustawiany na koncie, np. 1, 3 lub 5. Token nie będzie współdzielony między boxami.

### Tokeny dostępu

Tokeny będą:

- losowe i osobne dla każdego urządzenia,
- powiązane z kontem oraz instalacją,
- możliwe do unieważnienia,
- okresowo odnawiane,
- przechowywane na serwerze wyłącznie jako skróty,
- używane do pobierania krótkotrwałych linków do IPK, list i piconów.

Nie będziemy wiązać dostępu wyłącznie z adresem MAC, ponieważ zmiana image może wygenerować nową instalację. W razie potrzeby administrator będzie mógł zwolnić stary slot i ponownie sparować box.

### Zakres uprawnień

Planowane poziomy dostępu:

```text
public
    Azman Panel i publiczne materiały

user
    prywatne pluginy i aktualizacje

channels
    listy kanałów

picons
    paczki piconów

admin
    pełny dostęp administracyjny
```

Autoryzacja i tokeny są planowanym etapem rozwoju. Obecna wersja panelu nie wymaga logowania i korzysta z istniejącego feeda.

## Nazewnictwo Enigma2

- katalog instalacyjny pluginu: `Extensions/AzmanPanel`,
- punkt wejścia: `plugin.py` z funkcją `Plugins(**kwargs)`,
- ekran główny: `AzmanPanelMainScreen`,
- pakiety opkg: `enigma2-plugin-extensions--azman-*`,
- ustawienia: `config.plugins.AzmanPanel`,
- wersja wydania i build mają ten sam znacznik czasu.
