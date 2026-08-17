


import threading
import urllib.request
import urllib.parse
import subprocess
import gzip
import re
import os
import tempfile
import zipfile
import json
import hashlib
import shutil
from xml.etree import ElementTree
from datetime import datetime
from enigma import eTimer, eDVBDB
from . import constants, utils, runtime
from .epg_mapper import PanelEpgMapper

class BaseWorker(threading.Thread):
    
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

class SatellitesXmlUpdateWorker(BaseWorker):
    MAX_SIZE = 10 * 1024 * 1024

    def __init__(self, source_name, source_url, target_paths, callback_finished):
        super(SatellitesXmlUpdateWorker, self).__init__(callback_finished)
        self.source_name = source_name
        self.source_url = source_url
        self.target_paths = target_paths

    def run(self):
        try:
            request = urllib.request.Request(self.source_url, headers={"User-Agent": "AzmanPanel/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(self.MAX_SIZE + 1)
            if len(data) > self.MAX_SIZE:
                raise ValueError("Pobrany plik satellites.xml jest zbyt duży.")
            root = ElementTree.fromstring(data)
            if root.tag != "satellites":
                raise ValueError("Pobrany plik nie jest poprawnym satellites.xml.")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            saved = []
            for path in self.target_paths:
                directory = os.path.dirname(path)
                if not os.path.isdir(directory):
                    os.makedirs(directory)
                if os.path.exists(path):
                    shutil.copy2(path, "%s.bak-%s" % (path, timestamp))
                fd, temporary_path = tempfile.mkstemp(prefix=".azmanpanel-sat-", dir=directory)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary_path, path)
                except Exception:
                    if os.path.exists(temporary_path):
                        os.unlink(temporary_path)
                    raise
                saved.append(path)
            message = "Zaktualizowano satellites.xml ze źródła %s.\n\nZapisano: %s\nPrzed zapisem utworzono kopię istniejącego pliku." % (self.source_name, ", ".join(saved))
            self._safe_call_main_thread(None, message)
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, source=self.source_url)
            self._safe_call_main_thread("Nie udało się zaktualizować satellites.xml: %s" % error, None)

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

class ManifestPackageDownloadWorker(BaseWorker):
    """Pobiera pakiet z manifestu i weryfikuje jego SHA-256 przed instalacją."""
    MAX_PACKAGE_SIZE = 100 * 1024 * 1024
    TEMP_DIR = "/tmp/.azmanpanel"

    def __init__(self, package_id, callback_finished):
        super(ManifestPackageDownloadWorker, self).__init__(callback_finished)
        self.package_id = package_id
        self.error_message = None
        self.package_path = None

    def run(self):
        target = None
        try:
            utils.log_event("Rozpoczęto pobieranie pakietu", package_id=self.package_id)
            with urllib.request.urlopen(constants.AZMAN_MANIFEST_URL, timeout=20) as response:
                manifest = json.loads(response.read().decode("utf-8"))
            entry = next((item for item in manifest.get("packages", [])
                          if item.get("id") == self.package_id), None)
            if not entry:
                raise ValueError("Pakiet nie występuje w manifeście.")
            variant, variant_tag, compatibility_error = runtime.select_manifest_variant(entry)
            if compatibility_error:
                raise ValueError(compatibility_error)
            if not variant or not variant.get("sha256"):
                raise ValueError("Brak zgodnego wariantu lub sumy SHA-256.")
            package_url = variant.get("url")
            if entry.get("protected"):
                query = urllib.parse.urlencode({
                    "package_id": self.package_id,
                    "variant": variant_tag
                })
                api_url = "%s?%s" % (constants.AZMAN_PACKAGE_URL_API, query)
                with urllib.request.urlopen(api_url, timeout=20) as response:
                    access = json.loads(response.read().decode("utf-8"))
                package_url = access.get("url")
                if not package_url:
                    raise ValueError("Serwer nie udostępnił tymczasowego adresu pakietu.")
            if not package_url:
                raise ValueError("Brak adresu pobierania pakietu.")
            os.makedirs(self.TEMP_DIR, mode=0o700, exist_ok=True)
            os.chmod(self.TEMP_DIR, 0o700)
            fd, target = tempfile.mkstemp(prefix=".package-", suffix=".ipk", dir=self.TEMP_DIR)
            os.close(fd)
            os.chmod(target, 0o600)
            digest = hashlib.sha256()
            size = 0
            with urllib.request.urlopen(package_url, timeout=60) as response, open(target, "wb") as handle:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.MAX_PACKAGE_SIZE:
                        raise ValueError("Pakiet przekracza limit rozmiaru.")
                    handle.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest().lower() != variant["sha256"].lower():
                try:
                    os.unlink(target)
                except OSError:
                    pass
                raise ValueError("Nieprawidłowa suma SHA-256 pobranego pakietu.")
            self.package_path = target
            utils.log_event("Pakiet pobrany i zweryfikowany", package_id=self.package_id, size=size)
        except Exception as error:
            self.error_message = str(error)
            utils.log_error(error, self.__class__.__name__, package_id=self.package_id)
            if target:
                try:
                    os.unlink(target)
                except OSError:
                    pass
        finally:
            self._safe_call_main_thread(self.error_message, self.package_path)


class ManifestUpdateCheckWorker(BaseWorker):
    def __init__(self, callback_finished):
        super(ManifestUpdateCheckWorker, self).__init__(callback_finished)

    @staticmethod
    def _version_key(value):
        numbers = re.findall(r"\d+", str(value or ""))
        return tuple(int(number) for number in numbers) or (0,)

    def _installed_packages(self):
        installed = {}
        process = subprocess.Popen(["opkg", "list-installed"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, _ = process.communicate(timeout=20)
        if process.returncode:
            raise RuntimeError("Nie można odczytać listy zainstalowanych pakietów.")
        for line in output.decode("utf-8", "ignore").splitlines():
            if " - " in line:
                package, version = line.split(" - ", 1)
                installed[package.strip()] = version.strip()
        return installed

    @staticmethod
    def _entry_package_names(entry):
        names = set()
        package = str(entry.get("package") or "").strip()
        if package:
            names.add(package)
        for variant in (entry.get("variants") or {}).values():
            filename = os.path.basename(str(variant.get("ipk") or ""))
            if filename.count("_") >= 2:
                names.add(filename.rsplit("_", 2)[0])
        return names

    def _installed_entry_version(self, entry, installed):
        versions = []
        for package_name in self._entry_package_names(entry):
            version = installed.get(package_name)
            if version:
                versions.append(version)
        return max(versions, key=self._version_key) if versions else ""

    def run(self):
        try:
            request = urllib.request.Request(constants.AZMAN_MANIFEST_URL, headers={"User-Agent": "AzmanPanel/1.0"})
            with urllib.request.urlopen(request, timeout=12) as response:
                manifest = json.loads(response.read().decode("utf-8"))
            installed = self._installed_packages()
            updates = []
            panel_update = ""
            for entry in manifest.get("packages", []):
                package = entry.get("package")
                remote_version = str(entry.get("version") or "")
                if not package or not remote_version:
                    continue
                local_version = constants.PLUGIN_VERSION if entry.get("id") == "azman-panel" else self._installed_entry_version(entry, installed)
                if not local_version or self._version_key(remote_version) <= self._version_key(local_version):
                    continue
                name = str(entry.get("name") or entry.get("id") or package)
                if entry.get("id") == "azman-panel":
                    panel_update = remote_version
                else:
                    updates.append((name, local_version, remote_version))
            self._safe_call_main_thread(None, panel_update, updates)
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, url=constants.AZMAN_MANIFEST_URL)
            self._safe_call_main_thread(str(error), "", [])

class PiconZipListWorker(BaseWorker):
    
    def __init__(self, callback_finished):
        super(PiconZipListWorker, self).__init__(callback_finished)
        self.error_message = None
        self.picon_zip_filenames = []
    def run(self):
        try:
            with urllib.request.urlopen(constants.PICONS_BASE_URL, timeout=10) as response:
                payload = json.loads(response.read().decode('utf-8'))
            self.picon_zip_filenames = [item['name'] for item in payload.get('packages', []) if item.get('name')]
            self.picon_zip_filenames.sort(key=lambda x: x.lower())
            if not self.picon_zip_filenames:
                self.error_message = "Nie znaleziono plików *.zip w katalogu picon."
        except Exception as e:
            utils.log_error(e, self.__class__.__name__, url=constants.PICONS_BASE_URL)
            self.error_message = "Błąd pobierania listy picon."
        finally:
            self._safe_call_main_thread(self.error_message, self.picon_zip_filenames)

class PiconInstallationWorker(ProgressWorkerMixin, BaseWorker):
    
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
                    
                    safe_name = os.path.basename(zip_filename)
                    temp_zip_path = os.path.join(temp_dir, safe_name)
                    query = urllib.parse.urlencode({'name': safe_name})
                    with urllib.request.urlopen(constants.PICON_URL_API + '?' + query, timeout=20) as response:
                        access = json.loads(response.read().decode('utf-8'))
                    picon_zip_url = access.get('url')
                    if not picon_zip_url:
                        raise ValueError("Serwer nie udostępnił paczki picon.")
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
            source_filenames = [utils.validate_bouquet_filename(name) for name in self.selected_bouquets]
            filenames = [utils.panel_bouquet_filename(name) for name in source_filenames]
            total_bouquets = len(source_filenames)
            for i, (source_filename, filename) in enumerate(zip(source_filenames, filenames)):
                if self._is_cancelled: raise InterruptedError("Installation cancelled")
                self._safe_call_progress(i, total_bouquets, f"Pobieranie: {source_filename}")
                
                download_url = self.base_url + source_filename
                target_path = os.path.join(target_dir, filename)
                urllib.request.urlretrieve(download_url, target_path, reporthook=self._internal_reporthook)
                if source_filename != filename:
                    utils.remove_bouquet_and_registration(target_dir, source_filename)

            self._safe_call_progress(total_bouquets, total_bouquets, "Aktualizowanie bouquets.tv...")
            
            existing_lines = []
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as f:
                    existing_lines = f.readlines()
            
            while existing_lines and existing_lines[-1].strip() == "":
                existing_lines.pop()

            existing_services = {line.strip() for line in existing_lines if 'FROM BOUQUET' in line}
            
            for filename in filenames:
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

class PrivateBouquetListWorker(BaseWorker):
    def __init__(self, callback_finished):
        super(PrivateBouquetListWorker, self).__init__(callback_finished)

    def run(self):
        error_message = None
        bouquet_filenames = []
        try:
            with urllib.request.urlopen(constants.BOUQUETS_LIST_API, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            bouquet_filenames = sorted(
                [item.get("name") for item in payload.get("packages", []) if item.get("name")],
                key=lambda name: name.lower()
            )
            bouquet_filenames = [utils.validate_bouquet_filename(name) for name in bouquet_filenames]
            if not bouquet_filenames:
                error_message = "Nie znaleziono dostępnych bukietów IPTV PL."
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, url=constants.BOUQUETS_LIST_API)
            error_message = "Nie udało się pobrać listy bukietów IPTV PL."
        finally:
            self._safe_call_main_thread(error_message, bouquet_filenames)

class PrivateBouquetInstallWorker(ProgressWorkerMixin, BaseWorker):
    def __init__(self, selected_bouquets, callback_progress, callback_finished):
        super(PrivateBouquetInstallWorker, self).__init__(callback_finished)
        self.selected_bouquets = selected_bouquets
        self.callback_progress = callback_progress
        self._init_progress()

    def run(self):
        target_dir = "/etc/enigma2"
        bouquets_tv_path = os.path.join(target_dir, "bouquets.tv")
        final_message = ""
        try:
            source_filenames = [utils.validate_bouquet_filename(name) for name in self.selected_bouquets]
            filenames = [utils.panel_bouquet_filename(name) for name in source_filenames]
            for index, (source_filename, filename) in enumerate(zip(source_filenames, filenames)):
                if self._is_cancelled:
                    raise InterruptedError("Installation cancelled")
                self._safe_call_progress(index, len(filenames), "Pobieranie: %s" % source_filename)
                query = urllib.parse.urlencode({"name": source_filename})
                with urllib.request.urlopen(constants.BOUQUET_URL_API + "?" + query, timeout=20) as response:
                    access = json.loads(response.read().decode("utf-8"))
                download_url = access.get("url")
                if not download_url:
                    raise ValueError("Serwer nie udostępnił wybranego bukietu.")
                target_path = os.path.join(target_dir, filename)
                urllib.request.urlretrieve(download_url, target_path, reporthook=self._internal_reporthook)
                if source_filename != filename:
                    utils.remove_bouquet_and_registration(target_dir, source_filename)

            self._safe_call_progress(len(filenames), len(filenames), "Aktualizowanie bouquets.tv...")
            existing_lines = []
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as handle:
                    existing_lines = handle.readlines()
            existing_services = {line.strip() for line in existing_lines if "FROM BOUQUET" in line}
            for filename in filenames:
                service_line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % filename
                if service_line not in existing_services:
                    existing_lines.append(service_line + "\n")
            utils.atomic_write_lines(bouquets_tv_path, existing_lines)

            self._safe_call_progress(len(filenames), len(filenames), "Przeładowywanie listy kanałów...")
            database = eDVBDB.getInstance()
            database.reloadBouquets()
            database.reloadServicelist()
            final_message = "Zainstalowano %d bukiet(ów). Lista kanałów została przeładowana." % len(filenames)
        except InterruptedError:
            final_message = "Instalacja anulowana przez użytkownika."
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, selected_bouquets=self.selected_bouquets)
            final_message = "Wystąpił błąd podczas instalacji: %s" % error
        finally:
            self._safe_call_main_thread(final_message)

class IptvBouquetUninstallWorker(ProgressWorkerMixin, BaseWorker):
    
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
            self.selected_bouquets = [utils.panel_bouquet_filename(name) for name in self.selected_bouquets]
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


class MyRadioOnlineBouquetWorker(BaseWorker):
    """Pobiera publiczny katalog MyRadioOnline i tworzy bukiet radiowy."""

    def __init__(self, callback_finished):
        super(MyRadioOnlineBouquetWorker, self).__init__(callback_finished)

    @staticmethod
    def _bitrate(value):
        match = re.search(r"\d+", str(value or ""))
        return int(match.group(0)) if match else 0

    def run(self):
        bouquet_path = os.path.join("/etc/enigma2", constants.MYRADIOONLINE_BOUQUET_FILENAME)
        bouquets_tv_path = "/etc/enigma2/bouquets.tv"
        try:
            now = datetime.now().strftime("%Y-%m-%d_%H")
            request = urllib.request.Request(
                constants.MYRADIOONLINE_API_URL,
                data=urllib.parse.urlencode({
                    "ver": "andr1439",
                    "sec-key": "a_febe521d77cbd235bc27268789e8592bb9378cb47e4e5fd5dc89493578a64049ec2c8282eda9a80d720e656c8639ba7ea1d5bf8812b0a5a198373164acf35fd6",
                    "time": now,
                }).encode("utf-8"),
                headers={
                    "User-Agent": "okhttp/3.12.12 - hu.myonlineradio.radio.pl.myonlineradio.onlineradioapplication",
                    "Referer": "https://myradioonline.pl",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            radios = payload.get("radios") if isinstance(payload, dict) else []
            epg_mapper = PanelEpgMapper()
            epg_mapper.prefetch([radio.get("r_name") for radio in radios if isinstance(radio, dict)])
            lines = ["#NAME MyRadioOnline (azman)\n"]
            seen = set()
            count = 0
            for radio in radios or []:
                if not isinstance(radio, dict):
                    continue
                name = str(radio.get("r_name") or "").strip()
                streams = radio.get("streamServers") or {}
                candidates = []
                for stream in streams.values():
                    if not isinstance(stream, dict):
                        continue
                    url = str(stream.get("rsu_url") or "").strip()
                    if url.startswith(("http://", "https://")):
                        candidates.append((self._bitrate(stream.get("rsu_bandwidth")), url))
                if not name or not candidates:
                    continue
                candidates.sort(key=lambda item: item[0], reverse=True)
                bitrate, stream_url = candidates[0]
                if stream_url in seen:
                    continue
                seen.add(stream_url)
                safe_name = re.sub(r"[\r\n:]", " ", name).strip()
                encoded_url = urllib.parse.quote(stream_url, safe="")
                epg_reference = epg_mapper.reference(safe_name)
                service_prefix = "4097:%s" % epg_reference if epg_reference else "4097:0:2:0:0:0:0:0:0:0"
                lines.append("#SERVICE %s:%s:%s\n" % (service_prefix, encoded_url, safe_name))
                lines.append("#DESCRIPTION %s\n" % safe_name)
                count += 1
            if not count:
                raise ValueError("Nie znaleziono dostępnych stacji radiowych.")
            utils.atomic_write_lines(bouquet_path, lines)
            utils.remove_bouquet_and_registration("/etc/enigma2", "userbouquet.azman_iptv_myradioonline.tv")
            service_line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % constants.MYRADIOONLINE_BOUQUET_FILENAME
            existing = []
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as handle:
                    existing = handle.readlines()
            if not any(constants.MYRADIOONLINE_BOUQUET_FILENAME in line for line in existing):
                existing.append(service_line + "\n")
                utils.atomic_write_lines(bouquets_tv_path, existing)
            db = eDVBDB.getInstance()
            db.reloadBouquets()
            db.reloadServicelist()
            self.final_message = "Utworzono bukiet MyRadioOnline.\n\nDodano %d stacji radiowych." % count
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, target=bouquet_path)
            self.error_message = "Nie udało się utworzyć bukietu MyRadioOnline:\n%s" % error
        finally:
            if not self._is_cancelled:
                self._safe_call_main_thread(getattr(self, "error_message", None), getattr(self, "final_message", None))


class PolskieRadioBouquetWorker(BaseWorker):
    def __init__(self, callback_finished):
        super(PolskieRadioBouquetWorker, self).__init__(callback_finished)

    def run(self):
        bouquet_name = constants.POLSKIE_RADIO_BOUQUET_FILENAME
        bouquet_path = os.path.join("/etc/enigma2", bouquet_name)
        bouquets_tv_path = "/etc/enigma2/bouquets.tv"
        try:
            epg_mapper = PanelEpgMapper()
            epg_mapper.prefetch([name for name, _stream_url in constants.POLSKIE_RADIO_STREAMS])
            lines = ["#NAME Polskie Radio (azman)\n"]
            for name, stream_url in constants.POLSKIE_RADIO_STREAMS:
                safe_name = re.sub(r"[\r\n:]", " ", name).strip()
                encoded_url = urllib.parse.quote(stream_url, safe="")
                epg_reference = epg_mapper.reference(safe_name)
                service_prefix = "4097:%s" % epg_reference if epg_reference else "4097:0:2:0:0:0:0:0:0:0"
                lines.append("#SERVICE %s:%s:%s\n" % (service_prefix, encoded_url, safe_name))
                lines.append("#DESCRIPTION %s\n" % safe_name)
            utils.atomic_write_lines(bouquet_path, lines)
            utils.remove_bouquet_and_registration("/etc/enigma2", "userbouquet.azman_iptv_polskieradio.tv")
            service_line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % bouquet_name
            existing = []
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as handle:
                    existing = handle.readlines()
            if not any(bouquet_name in line for line in existing):
                existing.append(service_line + "\n")
                utils.atomic_write_lines(bouquets_tv_path, existing)
            db = eDVBDB.getInstance()
            db.reloadBouquets()
            db.reloadServicelist()
            self.final_message = "Utworzono bukiet Polskie Radio.\n\nDodano %d stacji radiowych." % len(constants.POLSKIE_RADIO_STREAMS)
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, target=bouquet_path)
            self.error_message = "Nie udało się utworzyć bukietu Polskie Radio:\n%s" % error
        finally:
            if not self._is_cancelled:
                self._safe_call_main_thread(getattr(self, "error_message", None), getattr(self, "final_message", None))


class _RadioApiBouquetWorker(BaseWorker):
    def _write_bouquet(self, filename, title, stations):
        path = os.path.join("/etc/enigma2", filename)
        lines = ["#NAME %s (azman)\n" % title]
        mapper = PanelEpgMapper()
        mapper.prefetch([name for name, _url in stations])
        for name, url in stations:
            name = re.sub(r"[\r\n:]", " ", str(name)).strip()
            encoded = urllib.parse.quote(str(url), safe="")
            reference = mapper.reference(name)
            prefix = "4097:%s" % reference if reference else "4097:0:2:0:0:0:0:0:0:0"
            lines.append("#SERVICE %s:%s:%s\n" % (prefix, encoded, name))
            lines.append("#DESCRIPTION %s\n" % name)
        if not stations:
            raise ValueError("Nie znaleziono dostępnych stacji radiowych.")
        utils.atomic_write_lines(path, lines)
        legacy_filename = filename.replace("userbouquet.azmanpanel_", "userbouquet.azman_iptv_", 1)
        utils.remove_bouquet_and_registration("/etc/enigma2", legacy_filename)
        bouquets = "/etc/enigma2/bouquets.tv"
        existing = open(bouquets, "r").readlines() if os.path.exists(bouquets) else []
        marker = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet\n' % filename
        if not any(filename in line for line in existing):
            existing.append(marker)
            utils.atomic_write_lines(bouquets, existing)
        db = eDVBDB.getInstance()
        db.reloadBouquets()
        db.reloadServicelist()


class RmfonBouquetWorker(_RadioApiBouquetWorker):
    def run(self):
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            req = urllib.request.Request(constants.RMFON_API_URL + "stations", headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            stations = []
            for item in payload if isinstance(payload, list) else payload.get("stations", []):
                sid = item.get("id") or item.get("station_id")
                name = item.get("name") or item.get("title")
                if not sid or not name: continue
                req = urllib.request.Request(constants.RMFON_API_URL + "stations/%s/streams" % sid, headers=headers)
                with urllib.request.urlopen(req, timeout=25) as response:
                    data = json.loads(response.read().decode("utf-8"))
                candidates = []
                for key in ("playlist", "playlistMp3"):
                    group = data.get(key, {}) if isinstance(data, dict) else {}
                    values = group.get("item", []) if key == "playlist" else group.get("item_mp3", [])
                    candidates.extend(v for v in values if isinstance(v, str) and v.startswith("http"))
                if candidates: stations.append((name, candidates[0]))
            self._write_bouquet(constants.RMFON_BOUQUET_FILENAME, "RMF ON", stations)
            self.final_message = "Utworzono bukiet RMF ON.\n\nDodano %d stacji radiowych." % len(stations)
        except Exception as error:
            self.error_message = "Nie udało się utworzyć bukietu RMF ON:\n%s" % error
        finally:
            if not self._is_cancelled: self._safe_call_main_thread(getattr(self, "error_message", None), getattr(self, "final_message", None))


class EurozetBouquetWorker(_RadioApiBouquetWorker):
    def run(self):
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            stations = []
            for slug, title in constants.EUROZET_STATIONS:
                url = constants.EUROZET_API_URL + "stations/(station)/" + slug
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=25) as response:
                    data = json.loads(response.read().decode("utf-8"))
                stream = ((data.get("player") or {}).get("stream") if isinstance(data, dict) else None)
                if stream: stations.append((title, stream))
            self._write_bouquet(constants.EUROZET_BOUQUET_FILENAME, "Eurozet", stations)
            self.final_message = "Utworzono bukiet Eurozet.\n\nDodano %d stacji radiowych." % len(stations)
        except Exception as error:
            self.error_message = "Nie udało się utworzyć bukietu Eurozet:\n%s" % error
        finally:
            if not self._is_cancelled: self._safe_call_main_thread(getattr(self, "error_message", None), getattr(self, "final_message", None))


class LgChannelsPlBouquetWorker(BaseWorker):
    def __init__(self, callback_finished):
        super(LgChannelsPlBouquetWorker, self).__init__(callback_finished)
        self.error_message = None
        self.final_message = None

    def _attribute(self, line, name):
        match = re.search(r'(?:^|\s)%s="([^"]*)"' % re.escape(name), line)
        return match.group(1).strip() if match else ""

    def _prepare_url(self, url):
        values = {
            "APP_BUNDLE": "pl.azman.panel",
            "APP_NAME": "Azman Panel",
            "APP_VERSION": "1.0",
            "COUNTRY": "PL",
            "DEVICE_ID": "00000000-0000-0000-0000-000000000000",
            "DEVICE_MAKE": "Enigma2",
            "DEVICE_MODEL": "Linux STB",
            "DEVICE_TYPE": "connected_tv",
            "GDPR": "1",
            "TARGETAD_ALLOWED": "0",
            "UA": "Mozilla/5.0 (X11; Linux armv7l) AzmanPanel/1.0",
            "VIEWSIZE": "1920x1080",
        }
        prepared = str(url).strip()
        for name, value in values.items():
            prepared = prepared.replace("[%s]" % name, urllib.parse.quote(value, safe=""))
        return re.sub(r"\[[A-Z0-9_]+\]", "", prepared)

    def run(self):
        bouquet_filepath = os.path.join("/etc/enigma2", constants.LGCHANNELSPL_BOUQUET_FILENAME)
        bouquets_tv_path = "/etc/enigma2/bouquets.tv"
        try:
            request = urllib.request.Request(constants.LGCHANNELSPL_PLAYLIST_URL, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux armv7l) AzmanPanel/1.0",
                "Accept": "audio/mpegurl, application/vnd.apple.mpegurl, text/plain, */*",
                "Referer": "https://www.apsattv.com/streams.html",
            })
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read().decode("utf-8-sig", errors="replace")
            if not content.lstrip().startswith("#EXTM3U"):
                raise ValueError("Pobrana lista LG Channels PL ma nieprawidłowy format.")
            lines = ["#NAME LG Channels PL (azman)\n"]
            metadata = None
            seen_urls = set()
            count = 0
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#EXTINF"):
                    metadata = line
                    continue
                if line.startswith("#"):
                    continue
                if metadata is None or not line.startswith(("http://", "https://")):
                    metadata = None
                    continue
                stream_url = self._prepare_url(line)
                if ".m3u8" not in stream_url.lower() or stream_url in seen_urls:
                    metadata = None
                    continue
                seen_urls.add(stream_url)
                name = metadata.rsplit(",", 1)[-1].strip() or "LG Channels"
                name = re.sub(r"^\d+\s+", "", name).replace(":", " ").replace("\n", " ")
                encoded_url = urllib.parse.quote(stream_url, safe="")
                lines.append("#SERVICE 4097:0:1:0:0:0:0:0:0:0:%s:%s\n" % (encoded_url, name))
                lines.append("#DESCRIPTION %s\n" % name)
                count += 1
                metadata = None
            if self._is_cancelled:
                raise InterruptedError()
            if count == 0:
                raise ValueError("Nie znaleziono kanałów HLS na liście LG Channels PL.")
            utils.atomic_write_lines(bouquet_filepath, lines)
            utils.remove_bouquet_and_registration("/etc/enigma2", "userbouquet.azmanplayer_lgchannelspl.tv")
            existing = []
            if os.path.exists(bouquets_tv_path):
                with open(bouquets_tv_path, "r") as handle:
                    existing = handle.readlines()
            if not any(constants.LGCHANNELSPL_BOUQUET_FILENAME in line for line in existing):
                existing.append('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet\n' % constants.LGCHANNELSPL_BOUQUET_FILENAME)
                utils.atomic_write_lines(bouquets_tv_path, existing)
            db = eDVBDB.getInstance()
            db.reloadBouquets()
            db.reloadServicelist()
            self.final_message = "Utworzono bukiet LG Channels PL.\n\nDodano %d kanałów." % count
        except InterruptedError:
            self.error_message = "Operacja anulowana przez użytkownika."
        except Exception as error:
            utils.log_error(error, self.__class__.__name__, url=constants.LGCHANNELSPL_PLAYLIST_URL, target=bouquet_filepath)
            self.error_message = "Nie udało się utworzyć bukietu LG Channels PL:\n%s" % error
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
        bouquet_filename = constants.IPTVORG_BOUQUET_FILENAME
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
                            
                            cleaned_name = channel_name.replace(':', ' ')
                            
                            
                            
                            encoded_url = urllib.parse.quote(stream_url)
                            
                            
                            bouquet_lines.append(f"#SERVICE 4097:0:1:0:0:0:0:0:0:0:{encoded_url}:{cleaned_name}\n")
                            
                            bouquet_lines.append(f"#DESCRIPTION {cleaned_name}\n")
                            channel_count += 1
                    except IndexError:
                        continue
            
            if self._is_cancelled: raise InterruptedError()

            if channel_count == 0:
                raise ValueError("Nie znaleziono żadnych kanałów w pobranej liście M3U.")
            
            utils.atomic_write_lines(bouquet_filepath, bouquet_lines)
            utils.remove_bouquet_and_registration("/etc/enigma2", "userbouquet.iptv-org-pl.tv")
                
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
