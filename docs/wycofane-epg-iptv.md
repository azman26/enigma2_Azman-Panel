# Wycofane EPG dla IPTV

Funkcja zostala usunieta z GUI i autostartu w wersji 2026.10.31-2016.
Pozostawiony external_epg.py jest nieaktywnym kodem referencyjnym.
Standardowe polskie zrodla EPG i import epg_events.py pozostaja aktywne.

## Jak dzialala implementacja

- screens.py oferowal audyt, ostatni raport, naprawe referencji i przelacznik
  external_iptv_epg. Usunieto te akcje i definicje opcji konfiguracji.
- plugin.py uruchamial audyt po starcie GUI oraz co 12 godzin. Usunieto import
  external_epg, funkcje wywolujaca audyt i jego osobny timer.
- external_epg.scan() czytal userbouquet.* z /etc/enigma2, pomijal dowiazania
  i rozroznial bukiety wlasne oraz zewnetrzne. Limity: 1000 bukietow,
  10 000 kanalow, 24 MB danych.
- epg_validation.py sprawdzal referencje. PrivateEpgApiClient w epg_private.py
  dostarczal mapowanie z prywatnego API.
- plan() przygotowywal przypisania. update_bouquets() zmienial referencje,
  korzystajac z poprzedniej zawartosci plikow i kontroli ich stanu.
  Mechanizm korzystal z BackupStore.
- import_external() i audit_external() obslugiwaly import i audyt.
  Warianty asynchroniczne uzywaly ImportQueue. Operacje Enigmy trafialy do
  glownego watku przez mainthread.call_in_main_thread.
- Stan zapisywano w /tmp/azmanpanel_external_epg_status.json.
  Sciezke raportu okresla REPORT_FILE w zachowanym module.
- Testy zachowano w 00 AzmanPanel/tests/test_external_epg.py.

## Ewentualne przywrocenie

Przejrzec zachowany modul i testy; sprawdzic aktualny format API, uprawnienia,
limity i kopie bukietow. Nastepnie swiadomie przywrocic opcje konfiguracji,
akcje GUI i osobny timer. Stare ustawienie w /etc/enigma2/settings nie
uruchamia juz tej funkcji.

Z Narzedzi usunieto tez kafelki Kopie ustawien i Diagnostyka oraz ich metody
w ekranie. Moduly backups.py i diagnostics.py pozostaja jako narzedzia
techniczne, bez kafelkow w Panelu.
