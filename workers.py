# /usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/workers.py
# KOD Z OSTATECZNĄ POPRAWKĄ KODOWANIA URL DLA IPTV.ORG

import threading
import urllib.request
import urllib.parse
import subprocess
import gzip
import re
import os
import tempfile
import zipfile
from enigma import eTimer, eDVBDB
from . import constants, utils, runtime

class BaseWorker(threading.Thread):
    # ... (bez zmian) ...
    def __init__(self, callback_finished):
        threading.Thread.__init__(self)
        self._is_cancelled = False
        self.callback_finished = callback_finished
        self.timer = eTimer()
        self.timer.callback.append(self._safe_callback)
        self._callback_args = ()

    def cancel(self):
        self._is_cancelled = True

    def _safe_call_main_thread(self, *args):
        self._callback_args = args
        self.timer.start(0, True)

    def _safe_callback(self):
        self.timer.stop()
        if not self._is_cancelled and self.callback_finished:
            self.callback_finished(*self._callback_args)

    def _internal_reporthook(self, count, block_size, total_size):
        if self._is_cancelled:
            raise InterruptedError("Download cancelled by user")

class ProgressWorkerMixin:
    """Wspólna obsługa bezpiecznego raportowania postępu do GUI."""
    def _init_progress(self):
        self.progress_timer = eTimer()
        self.progress_timer.callback.append(self._safe_progress_callback)
        self._progress_args = ()

    def _safe_call_progress(self, *args):
        self._progress_args = args
        self.progress_timer.start(0, True)

    def _safe_progress_callback(self):
        self.progress_timer.stop()
        if not self._is_cancelled and self.callback_progress:
            self.callback_progress(*self._progress_args)

class PackageListWorker(BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, callback_finished):
        super(PackageListWorker, self).__init__(callback_finished)
        self.error_message = None
        self.packages = []
    def _parse_packages_file(self, content):
        packages = []
        current_package = {}
        for line in content.split('\n'):
            if not line:
                if 'Package' in current_package: packages.append(current_package)
                current_package = {}
                continue
            if ': ' in line:
                key, value = line.split(': ', 1)
                current_package[key] = value
        if 'Package' in current_package: packages.append(current_package)
        return packages
    def _get_installed_packages(self):
        installed = {}
        try:
            process = subprocess.Popen(["opkg", "list-installed"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=60)
            if process.returncode == 0:
                for line in stdout.decode('utf-8', errors='ignore').split('\n'):
                    if ' - ' in line:
                        name, version = line.split(' - ', 1)
                        installed[name.strip()] = version.strip()
            else:
                raise Exception(stderr.decode('utf-8', errors='ignore'))
        except Exception as e:
            utils.log_error(e, "opkg list-installed")
            self.error_message = "Błąd sprawdzania zainstalowanych pakietów."
        return installed
    def run(self):
        try:
            packages_content = None
            packages_gz_url = None
            # Warianty środowiskowe są opcjonalne. Zachowujemy fallback do
            # istniejącego feeda all, aby starsze instalacje nadal działały.
            for tag in runtime.package_runtime_tags():
                candidate_url = f"{constants.AZMAN_FEED_BASE_URL}/{tag}/Packages.gz"
                try:
                    with urllib.request.urlopen(candidate_url, timeout=10) as response:
                        packages_content = gzip.decompress(response.read()).decode('utf-8')
                    packages_gz_url = candidate_url
                    break
                except Exception:
                    continue
            if packages_content is None:
                packages_gz_url = f"{constants.FEED_PACKAGES_BASE_URL}/all/Packages.gz"
                with urllib.request.urlopen(packages_gz_url, timeout=20) as response:
                    packages_content = gzip.decompress(response.read()).decode('utf-8')
            available_packages = self._parse_packages_file(packages_content)
            installed_packages = self._get_installed_packages()
            if self.error_message: raise Exception(self.error_message)
            for pkg in available_packages:
                pkg_name = pkg.get('Package')
                if not pkg_name: continue
                self.packages.append({'name': pkg_name, 'version': pkg.get('Version', 'N/A'), 'description': pkg.get('Description', 'Brak opisu.'), 'status': 'Zainstalowany' if pkg_name in installed_packages else 'Dostępny'})
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, url=packages_gz_url)
            self.error_message = "Nie można pobrać listy pakietów. Sprawdź połączenie z internetem."
        finally:
            self._safe_call_main_thread(self.error_message, self.packages)

class PiconZipListWorker(BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, callback_finished):
        super(PiconZipListWorker, self).__init__(callback_finished)
        self.error_message = None
        self.picon_zip_filenames = []
    def run(self):
        try:
            with urllib.request.urlopen(constants.PICONS_BASE_URL, timeout=10) as response:
                html = response.read().decode('utf-8')
            self.picon_zip_filenames = sorted(re.findall(r'href="([^"]+\.zip)"', html), key=lambda x: x.lower())
            if not self.picon_zip_filenames:
                self.error_message = "Nie znaleziono plików *.zip w katalogu picon."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, url=constants.PICONS_BASE_URL)
            self.error_message = "Błąd pobierania listy picon."
        finally:
            self._safe_call_main_thread(self.error_message, self.picon_zip_filenames)

class PiconInstallationWorker(ProgressWorkerMixin, BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, selected_zips, target_dir, callback_progress, callback_finished):
        super(PiconInstallationWorker, self).__init__(callback_finished)
        self.selected_zips = selected_zips
        self.target_dir = target_dir
        self.callback_progress = callback_progress
        self._init_progress()
    def run(self):
        installed_summary = []
        total_installed_packages = 0
        final_message = ""
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                if not os.path.exists(self.target_dir):
                    os.makedirs(self.target_dir)
                total_zips = len(self.selected_zips)
                
                for i, zip_filename in enumerate(self.selected_zips):
                    if self._is_cancelled: break
                    
                    display_filename = urllib.parse.unquote(zip_filename)
                    self._safe_call_progress(i, total_zips, f"Pobieranie: {display_filename}")
                    
                    temp_zip_path = os.path.join(temp_dir, zip_filename)
                    picon_zip_url = urllib.parse.urljoin(constants.PICONS_BASE_URL, zip_filename)
                    urllib.request.urlretrieve(picon_zip_url, temp_zip_path, reporthook=self._internal_reporthook)
                    
                    self._safe_call_progress(i, total_zips, f"Rozpakowywanie: {display_filename}")
                    
                    picon_count_in_zip = 0
                    with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                        for member in zip_ref.infolist():
                            if self._is_cancelled: break
                            if not member.is_dir() and member.filename.lower().endswith('.png'):
                                picon_count_in_zip += 1
                            utils.safe_extract_zip_member(zip_ref, member, self.target_dir)

                    if picon_count_in_zip > 0:
                        display_name = display_filename.replace('.zip', '')
                        installed_summary.append(f"- {display_name} ({picon_count_in_zip} picon)")
                    
                    total_installed_packages += 1

            if self._is_cancelled:
                 final_message = "Instalacja anulowana przez użytkownika."
            elif total_installed_packages > 0:
                final_message = f"Zainstalowano pomyślnie {total_installed_packages} paczek:\n\n"
                final_message += "\n".join(installed_summary)
            else:
                 final_message = "Nie zainstalowano żadnych paczek."

        except InterruptedError:
            final_message = "Instalacja anulowana przez użytkownika."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, selected_zips=self.selected_zips, target_dir=self.target_dir)
            final_message = f"Wystąpił błąd podczas instalacji:\n{e}"
        finally:
            self._safe_call_main_thread(final_message)
            
class IptvBouquetListWorker(BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, list_url, callback_finished):
        super(IptvBouquetListWorker, self).__init__(callback_finished)
        self.list_url = list_url
        self.error_message = None
        self.bouquet_filenames = []
        
    def run(self):
        try:
            with urllib.request.urlopen(self.list_url, timeout=10) as response:
                html = response.read().decode('utf-8')
            found_files = re.findall(r'href="[^"]*?(userbouquet\.[^"]+\.tv)"', html)
            self.bouquet_filenames = sorted(list(set(found_files)), key=lambda x: x.lower())
            if not self.bouquet_filenames:
                self.error_message = "Nie znaleziono żadnych plików bukietów w repozytorium."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, url=self.list_url)
            self.error_message = "Błąd pobierania listy bukietów."
        finally:
            self._safe_call_main_thread(self.error_message, self.bouquet_filenames)

class IptvBouquetInstallWorker(ProgressWorkerMixin, BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, selected_bouquets, base_url, callback_progress, callback_finished):
        super(IptvBouquetInstallWorker, self).__init__(callback_finished)
        self.selected_bouquets = selected_bouquets
        self.base_url = base_url
        self.callback_progress = callback_progress
        self._init_progress()
            
    def run(self):
        final_message = ""
        target_dir = "/etc/enigma2"
        bouquets_tv_path = os.path.join(target_dir, "bouquets.tv")
        
        try:
            self.selected_bouquets = [utils.validate_bouquet_filename(name) for name in self.selected_bouquets]
            total_bouquets = len(self.selected_bouquets)
            for i, filename in enumerate(self.selected_bouquets):
                if self._is_cancelled: raise InterruptedError("Installation cancelled")
                self._safe_call_progress(i, total_bouquets, f"Pobieranie: {filename}")
                
                download_url = self.base_url + filename
                target_path = os.path.join(target_dir, filename)
                urllib.request.urlretrieve(download_url, target_path, reporthook=self._internal_reporthook)

            self._safe_call_progress(total_bouquets, total_bouquets, "Aktualizowanie bouquets.tv...")
            
            existing_lines = []
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as f:
                    existing_lines = f.readlines()
            
            while existing_lines and existing_lines[-1].strip() == "":
                existing_lines.pop()

            existing_services = {line.strip() for line in existing_lines if 'FROM BOUQUET' in line}
            
            for filename in self.selected_bouquets:
                bouquet_line = f'#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "{filename}" ORDER BY bouquet'
                if bouquet_line not in existing_services:
                    existing_lines.append(bouquet_line + "\n")
            
            utils.atomic_write_lines(bouquets_tv_path, existing_lines)
            
            self._safe_call_progress(total_bouquets, total_bouquets, "Przeładowywanie listy kanałów...")
            
            db = eDVBDB.getInstance()
            db.reloadBouquets()
            db.reloadServicelist()
            final_message = f"Zainstalowano pomyślnie {len(self.selected_bouquets)} bukiet(ów).\nLista kanałów została przeładowana."
                
        except InterruptedError:
            final_message = "Instalacja anulowana przez użytkownika."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, selected_bouquets=self.selected_bouquets)
            final_message = f"Wystąpił błąd podczas instalacji:\n{e}"
        finally:
            self._safe_call_main_thread(final_message)

class IptvBouquetUninstallWorker(ProgressWorkerMixin, BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, selected_bouquets, callback_progress, callback_finished):
        super(IptvBouquetUninstallWorker, self).__init__(callback_finished)
        self.selected_bouquets = selected_bouquets
        self.callback_progress = callback_progress
        self._init_progress()
            
    def run(self):
        final_message = ""
        target_dir = "/etc/enigma2"
        bouquets_tv_path = os.path.join(target_dir, "bouquets.tv")
        
        try:
            self.selected_bouquets = [utils.validate_bouquet_filename(name) for name in self.selected_bouquets]
            total_bouquets = len(self.selected_bouquets)
            for i, filename in enumerate(self.selected_bouquets):
                if self._is_cancelled: raise InterruptedError("Uninstallation cancelled")
                self._safe_call_progress(i, total_bouquets, f"Usuwanie: {filename}")
                
                target_path = os.path.join(target_dir, filename)
                if os.path.exists(target_path):
                    os.remove(target_path)

            self._safe_call_progress(total_bouquets, total_bouquets, "Aktualizowanie bouquets.tv...")
            
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as f:
                    lines = f.readlines()
                
                selected_lines = {
                    f'FROM BOUQUET "{name}"' for name in self.selected_bouquets
                }
                new_lines = [line for line in lines if not any(marker in line for marker in selected_lines)]

                utils.atomic_write_lines(bouquets_tv_path, new_lines)

            self._safe_call_progress(total_bouquets, total_bouquets, "Przeładowywanie listy kanałów...")

            db = eDVBDB.getInstance()
            db.reloadBouquets()
            db.reloadServicelist()
            final_message = f"Odinstalowano pomyślnie {len(self.selected_bouquets)} bukiet(ów).\nLista kanałów została przeładowana."
                
        except InterruptedError:
            final_message = "Odinstalowywanie anulowane przez użytkownika."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, selected_bouquets=self.selected_bouquets)
            final_message = f"Wystąpił błąd podczas odinstalowywania:\n{e}"
        finally:
            self._safe_call_main_thread(final_message)

class SourcesXmlDownloadWorker(BaseWorker):
    # ... (bez zmian) ...
    def __init__(self, callback_finished):
        super(SourcesXmlDownloadWorker, self).__init__(callback_finished)
        self.error_message = None
        self.final_message = None

    def run(self):
        target_path = os.path.join(constants.SOURCES_XML_TARGET_DIR, constants.SOURCES_XML_FILENAME)
        filename = constants.SOURCES_XML_FILENAME
        try:
            if self._is_cancelled: return
            
            if not os.path.exists(constants.SOURCES_XML_TARGET_DIR):
                os.makedirs(constants.SOURCES_XML_TARGET_DIR, exist_ok=True)
            
            urllib.request.urlretrieve(constants.SOURCES_XML_URL, target_path, reporthook=self._internal_reporthook)
            
            self.final_message = f"Plik '{filename}' pomyślnie zainstalowany."
        except InterruptedError:
            self.error_message = "Pobieranie anulowane przez użytkownika."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, url=constants.SOURCES_XML_URL, target=target_path)
            self.error_message = f"Błąd pobierania pliku {filename}."
        finally:
            if not self._is_cancelled:
                self._safe_call_main_thread(self.error_message, self.final_message)

class IptvOrgWorker(BaseWorker):
    def __init__(self, callback_finished):
        super(IptvOrgWorker, self).__init__(callback_finished)
        self.error_message = None
        self.final_message = None

    def run(self):
        m3u_url = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/pl.m3u"
        bouquet_filename = "userbouquet.iptv-org-pl.tv"
        bouquet_filepath = os.path.join("/etc/enigma2", bouquet_filename)
        bouquets_tv_path = "/etc/enigma2/bouquets.tv"
        
        try:
            with urllib.request.urlopen(m3u_url, timeout=20) as response:
                m3u_content = response.read().decode('utf-8')

            if self._is_cancelled: raise InterruptedError()
            
            bouquet_lines = ["#NAME IPTV.ORG Poland\n"]
            channel_count = 0
            
            lines = m3u_content.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("#EXTINF:-1"):
                    try:
                        channel_name = re.search(r'tvg-name="([^"]+)"', line)
                        if not channel_name:
                            channel_name = line.split(',')[-1]
                        else:
                            channel_name = channel_name.group(1)
                        
                        stream_url = lines[i+1].strip()
                        
                        if channel_name and stream_url:
                            # <<< POCZĄTEK MODYFIKACJI ---
                            cleaned_name = channel_name.replace(':', ' ')
                            
                            # POPRAWKA: URL musi być w pełni zakodowany, aby : zmienił się na %3a
                            # Używamy quote bez żadnych bezpiecznych znaków.
                            encoded_url = urllib.parse.quote(stream_url)
                            
                            # POPRAWKA: Wracamy do typu serwisu 4097, który jest bardziej standardowy dla tego formatu
                            bouquet_lines.append(f"#SERVICE 4097:0:1:0:0:0:0:0:0:0:{encoded_url}:{cleaned_name}\n")
                            # <<< KONIEC MODYFIKACJI ---
                            bouquet_lines.append(f"#DESCRIPTION {cleaned_name}\n")
                            channel_count += 1
                    except IndexError:
                        continue
            
            if self._is_cancelled: raise InterruptedError()

            if channel_count == 0:
                raise ValueError("Nie znaleziono żadnych kanałów w pobranej liście M3U.")
            
            utils.atomic_write_lines(bouquet_filepath, bouquet_lines)
                
            service_line_to_add = f'#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "{bouquet_filename}" ORDER BY bouquet'
            main_bouquet_lines = []
            found = False
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as f:
                    main_bouquet_lines = f.readlines()
                if any(bouquet_filename in line for line in main_bouquet_lines):
                    found = True
            
            if not found:
                main_bouquet_lines.append(service_line_to_add + "\n")
                utils.atomic_write_lines(bouquets_tv_path, main_bouquet_lines)

            db = eDVBDB.getInstance()
            db.reloadBouquets()
            db.reloadServicelist()
            
            self.final_message = f"Utworzono bukiet IPTV.ORG Poland.\n\nDodano {channel_count} kanałów.\nLista kanałów została odświeżona."

        except InterruptedError:
            self.error_message = "Operacja anulowana przez użytkownika."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, url=m3u_url, target=bouquet_filepath)
            self.error_message = f"Wystąpił błąd:\n{e}"
        finally:
            if not self._is_cancelled:
                self._safe_call_main_thread(self.error_message, self.final_message)
