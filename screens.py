import os
import re
import urllib.parse
import subprocess
import shlex
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.ProgressBar import ProgressBar
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.Standby import TryQuitMainloop
from Tools.LoadPixmap import LoadPixmap
from skin import loadSkin
from enigma import eTimer, eConsoleAppContainer

from . import constants, runtime, utils
from .workers import PiconZipListWorker, PiconInstallationWorker, PrivateBouquetListWorker, PrivateBouquetInstallWorker, IptvBouquetUninstallWorker, IptvOrgWorker, MyRadioOnlineBouquetWorker, PolskieRadioBouquetWorker, RmfonBouquetWorker, EurozetBouquetWorker, PackageListWorker, ManifestPackageDownloadWorker, SatellitesXmlUpdateWorker
from .config import config, save_config

PLUGIN_PATH = os.path.dirname(os.path.realpath(__file__))
loadSkin(f"{PLUGIN_PATH}/panel_skin.xml")

class AzmanSelectListScreen(Screen):
    def __init__(self, session, title, item_list, on_install_callback=None, on_uninstall_callback=None):
        Screen.__init__(self, session)
        self.setTitle(title)
        self.item_list = item_list
        self.selected_items = []
        self.on_install_callback = on_install_callback
        self.on_uninstall_callback = on_uninstall_callback
        self.is_bouquet_list = bool(item_list and str(item_list[0][0]).startswith("userbouquet."))
        
        self["title"] = StaticText(title)
        self["selection_info"] = StaticText("")
        self["key_green"] = StaticText("Zainstaluj (0)")
        self["key_red"] = StaticText("Odinstaluj" if on_uninstall_callback else "Anuluj")
        self["key_yellow"] = StaticText("Zaznacz/Odznacz wszystko")
        self["list"] = MenuList([])
        
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"], 
            {
                "cancel": self.keyCancel, 
                "ok": self.toggle_selection, 
                "green": self.install_selected, 
                "red": self.uninstall_selected,
                "yellow": self.toggle_all
            }, 
            -1
        )
        self.onLayoutFinish.append(self.build_list)

    def build_list(self):
        current = self["list"].getCurrent()
        current_value = current[1] if current else None
        entries = []
        for value, label in self.item_list:
            checked = "☑" if value in self.selected_items else "☐"
            if self.is_bouquet_list:
                status = "  • ZAINSTALOWANY" if os.path.exists(os.path.join("/etc/enigma2", value)) else "  • NOWY"
            else:
                status = "  • PACZKA ZIP"
            entries.append((f"{checked}  {label}{status}", value))
        self["list"].setList(entries)
        self["selection_info"].setText("Zaznaczono: %d z %d   |   OK - zaznacz/odznacz" % (len(self.selected_items), len(self.item_list)))
        self["key_green"].setText("Zainstaluj (%d)" % len(self.selected_items))
        if current_value:
            for index, entry in enumerate(entries):
                if entry[1] == current_value:
                    self["list"].moveToIndex(index)
                    break

    def toggle_selection(self):
        current = self["list"].getCurrent()
        if not current: return
        path_value = current[1]
        if path_value in self.selected_items: 
            self.selected_items.remove(path_value)
        else: 
            self.selected_items.append(path_value)
        self.build_list()

    def toggle_all(self):
        all_paths = [i[0] for i in self.item_list]
        self.selected_items = [] if len(self.selected_items) == len(all_paths) else all_paths
        self.build_list()

    def install_selected(self):
        if self.on_install_callback and self.selected_items:
            selected = list(self.selected_items)
            self.close()
            self.on_install_callback(selected)

    def uninstall_selected(self):
        if self.on_uninstall_callback and self.selected_items:
            selected = list(self.selected_items)
            self.close()
            self.on_uninstall_callback(selected)
        elif not self.on_uninstall_callback:
            self.close([])

    def keyCancel(self):
        self.close([])

class PackageTileSelectionScreen(Screen):
    GRID_COLS = 3
    GRID_ROWS = 3
    PAGE_SIZE = GRID_COLS * GRID_ROWS

    def __init__(self, session, item_list, target_info, on_install_callback, title="Wybierz paczki Piconów", icon_name="icon_picons.png", on_uninstall_callback=None):
        Screen.__init__(self, session)
        self.item_list = item_list
        self.target_info = target_info
        self.on_install_callback = on_install_callback
        self.on_uninstall_callback = on_uninstall_callback
        self.is_bouquet_list = bool(item_list and str(item_list[0][0]).startswith("userbouquet."))
        self.selected_items = []
        self.selected_index = 0
        self.marker_pixmap = LoadPixmap(f"{PLUGIN_PATH}/icons/marker-cyan.png")
        self.default_icon_name = icon_name
        self["title"] = StaticText("Azman Panel  -  %s" % title)
        self["selection_info"] = StaticText("")
        self["target_info"] = StaticText(target_info)
        self["key_red"] = StaticText("Odinstaluj" if on_uninstall_callback else "Anuluj")
        self["key_green"] = StaticText("Zaznacz/Odznacz")
        self["key_yellow"] = StaticText("Zaznacz/Odznacz wszystko")
        for index in range(self.PAGE_SIZE):
            self["marker_%d" % index] = Pixmap()
            self["icon_%d" % index] = Pixmap()
            self["tile_%d" % index] = Label("")
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {
                "cancel": self.close,
                "red": self.uninstall_selected,
                "ok": self.install_selected,
                "green": self.toggle_selected,
                "yellow": self.toggle_all,
                "up": lambda: self.move(-self.GRID_COLS),
                "down": lambda: self.move(self.GRID_COLS),
                "left": lambda: self.move(-1),
                "right": lambda: self.move(1),
            }, -1
        )
        self.onLayoutFinish.append(self.draw)

    def _page_offset(self):
        return (self.selected_index // self.PAGE_SIZE) * self.PAGE_SIZE

    def _label(self, value, label):
        checked = "[x]" if value in self.selected_items else "[ ]"
        label = label.replace("-", " ")
        if len(label) > 27:
            label = label[:26] + "…"
        if self.is_bouquet_list:
            target_filename = utils.panel_bouquet_filename(value)
            status = "\n%s" % ("Zainstalowany" if os.path.exists(os.path.join("/etc/enigma2", target_filename)) else "Nowy")
        else:
            status = ""
        return "%s  %s%s" % (checked, label, status)

    def _tile_icon(self, value):
        if self.is_bouquet_list:
            name = re.sub(r"^userbouquet\.|\.tv$", "", value, flags=re.IGNORECASE)
            normalized_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            bouquet_icons = (
                ("regionalne", "icon_bouquet_regionalne_yt_radio.png"),
                ("okru", "icon_bouquet_iptv_okru_vk_azman.png"),
                ("endriu", "icon_bouquet_kamery_internetowe_pl_endriu.png"),
                ("toya", "icon_bouquet_kamery_toya_rysiek_52.png"),
                ("zet71", "icon_bouquet_polskie_stacje_radiowe_zet71.png"),
            )
            icon_name = next((candidate for key, candidate in bouquet_icons if key in normalized_name), "icon_bouquet_%s.png" % normalized_name)
        else:
            filename = urllib.parse.unquote(value).lower()
            mapping = (
                ("iptv muzyczne", "icon_picon_muzyka.png"),
                ("radio sat", "icon_picon_radio.png"),
                ("rakuten", "icon_picon_rakuten.png"),
                ("sweet", "icon_picon_sweettv.png"),
                ("lg channels", "icon_picon_lgchannels.png"),
                ("xiaomi", "icon_picon_xiaomi.png"),
                ("fast", "icon_picon_azman_fast.png"),
                ("sat", "icon_picon_sat.png"),
                ("iptv", "icon_picon_iptv_pl.png"),
            )
            icon_name = next((candidate for key, candidate in mapping if key in filename), self.default_icon_name)
        icon_path = os.path.join(PLUGIN_PATH, "icons", icon_name)
        fallback_path = os.path.join(PLUGIN_PATH, "icons", self.default_icon_name)
        return LoadPixmap(icon_path if os.path.exists(icon_path) else fallback_path)

    def draw(self):
        page_offset = self._page_offset()
        for tile_index in range(self.PAGE_SIZE):
            item_index = page_offset + tile_index
            marker = self["marker_%d" % tile_index]
            icon = self["icon_%d" % tile_index]
            label = self["tile_%d" % tile_index]
            marker.hide()
            if item_index < len(self.item_list):
                value, text = self.item_list[item_index]
                icon.instance.setPixmap(self._tile_icon(value))
                icon.show()
                label.setText(self._label(value, text))
                label.show()
                if item_index == self.selected_index:
                    marker.instance.setPixmap(self.marker_pixmap)
                    marker.show()
            else:
                icon.hide()
                label.hide()
        self["selection_info"].setText("Zaznaczono: %d z %d   |   OK - instaluj" % (len(self.selected_items), len(self.item_list)))

    def move(self, step):
        if not self.item_list:
            return
        self.selected_index = (self.selected_index + step) % len(self.item_list)
        self.draw()

    def toggle_selected(self):
        if not self.item_list:
            return
        value = self.item_list[self.selected_index][0]
        if value in self.selected_items:
            self.selected_items.remove(value)
        else:
            self.selected_items.append(value)
        self.draw()

    def toggle_all(self):
        all_values = [item[0] for item in self.item_list]
        self.selected_items = [] if len(self.selected_items) == len(all_values) else all_values
        self.draw()

    def install_selected(self):
        if not self.item_list:
            return
        selected = list(self.selected_items)
        if not selected:
            selected = [self.item_list[self.selected_index][0]]
        self.close()
        self.on_install_callback(selected)

    def uninstall_selected(self):
        if self.on_uninstall_callback and self.selected_items:
            selected = list(self.selected_items)
            self.close()
            self.on_uninstall_callback(selected)
        elif not self.on_uninstall_callback:
            self.close()

class OpkgCommandScreen(Screen):
    def __init__(self, session, command, title="", callback=None, restart_gui=False):
        Screen.__init__(self, session)
        self.command = command
        self.callback = callback
        self.restart_gui = restart_gui
        self.setTitle(title)
        self["console"] = ScrollLabel()
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions"], 
            {
                "ok": self.keyOk, 
                "cancel": self.keyOk,
                "up": self.pageUp,
                "down": self.pageDown
            }, -1)
        self.console_app = eConsoleAppContainer()
        self.console_app.dataAvail.append(self.on_console_data)
        self.console_app.appClosed.append(self.on_command_finished)
        self.onShown.append(self.run_command)
        self.is_finished = False

    def run_command(self):
        self["console"].setText(f"> {self.command}\n\n")
        self.console_app.execute(self.command)

    def on_console_data(self, data):
        if data:
            current_text = self["console"].getText()
            new_text = current_text + data.decode("utf-8", "ignore")
            self["console"].setText(new_text)
            self["console"].lastPage()

    def on_command_finished(self, result):
        self.is_finished = True
        self.appendText("\n\nPolecenie zakończone.")
        if self.callback:
            callback = self.callback
            self.callback = None
            callback()
        if self.restart_gui:
            self._ask_for_restart()
        else:
            self.appendText("\nNaciśnij OK/EXIT, aby zamknąć.")
    
    def appendText(self, text):
        current_text = self["console"].getText()
        self["console"].setText(current_text + text)
        self["console"].lastPage()
    
    def keyOk(self):
        if self.is_finished:
            if self.callback:
                callback = self.callback
                self.callback = None
                callback()
            self.close()

    def _ask_for_restart(self):
        self.session.openWithCallback(
            self._do_restart,
            MessageBox, 
            "Instalacja zakończona.\n\nZalecany jest restart interfejsu graficznego (GUI).\n\nCzy chcesz zrestartować teraz?", 
            type=MessageBox.TYPE_YESNO,
            default=True
        )
    
    def _do_restart(self, confirmed):
        if confirmed:
            self.session.open(TryQuitMainloop, 3)
        else:
            self.keyOk()

    def pageUp(self):
        self["console"].pageUp()

    def pageDown(self):
        self["console"].pageDown()

class DownloadProgressScreen(Screen):
    def __init__(self, session, title="", parent_worker=None):
        Screen.__init__(self, session)
        self.parent_worker = parent_worker
        self["title"] = StaticText(title)
        self["progress"] = ProgressBar()
        self["progresstext"] = Label("0%")
        self["actions"] = ActionMap(["OkCancelActions"], {"cancel": self.keyCancel}, -1)
    def keyCancel(self):
        if self.parent_worker and self.parent_worker.is_alive(): self.parent_worker.cancel()
        self.close()
    def setProgress(self, current, total, custom_title=""):
        if custom_title: self["title"].setText(custom_title)
        if total > 0:
            percent = int(current * 100 / total)
            self["progress"].setValue(percent)
            self["progresstext"].setText(f"{percent}%")

class BouquetGenerationScreen(Screen):
    def __init__(self, session, bouquet_name):
        Screen.__init__(self, session)
        self.setTitle("Tworzenie bukietu")
        self["title"] = StaticText("Tworzenie bukietu: %s" % bouquet_name)
        self["message"] = StaticText(
            "Trwa pobieranie stacji, generowanie bukietu i przypisywanie EPG.\n"
            "Proszę czekać..."
        )

class PiconPathSelectionScreen(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle("Wybierz ścieżkę instalacji picon")
        self["title"] = StaticText("Wybierz ścieżkę instalacji picon")
        self["key_green"] = StaticText("Wybierz")
        self["list"] = MenuList([])
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {"cancel": self.keyCancel, "ok": self.keyGreen, "green": self.keyGreen}, -1)
        self.onLayoutFinish.append(self.build_target_list)
    def build_target_list(self):
        choices = []
        for path, display_name in constants.PICON_RECOMMENDED_DIRS:
            parent_dir = os.path.dirname(path)
            if os.path.exists(parent_dir) and os.access(parent_dir, os.W_OK):
                status = " (zalecane)"
                if not os.path.exists(path): status += " - zostanie utworzony"
                choices.append((f"{display_name}{status}", path))
        if not choices:
            self.session.openWithCallback(self.keyCancel, MessageBox, "Nie znaleziono żadnej zapisywalnej lokalizacji (HDD/USB).", MessageBox.TYPE_ERROR)
        else:
            self["list"].setList(choices)
    def keyGreen(self):
        selection = self["list"].getCurrent()
        if selection: self.close(selection[1])
    def keyCancel(self): self.close(None)

class AzmanFeedScreen(Screen):
    def __init__(self, session, title="Azman Feed - Menedżer pakietów", filter_keywords=None):
        Screen.__init__(self, session)
        self.filter_keywords = filter_keywords
        self.setTitle(title)
        self.packages = []
        self.worker = None
        self["title"] = StaticText(title)
        self["description"] = Label("Wczytywanie listy pakietów...")
        self["key_green"] = StaticText("Zainstaluj")
        self["key_red"] = StaticText("Odinstaluj")
        self["key_yellow"] = StaticText("Odśwież")
        self["list"] = MenuList([])
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {"ok": self.handle_action, "cancel": self.close, "green": self.install_package, "red": self.remove_package, "yellow": self.refresh_list}, -1)
        self["list"].onSelectionChanged.append(self.on_selection_changed)
        self.onLayoutFinish.append(self.refresh_list)
        self.onClose.append(self.__onClose)

    def __onClose(self):
        if self.worker and self.worker.is_alive(): self.worker.cancel()

    def refresh_list(self):
        self["description"].setText("Aktualizowanie listy pakietów...")
        self["list"].setList([])
        self.worker = PackageListWorker(callback_finished=self._on_package_list_ready)
        self.worker.start()

    def _on_package_list_ready(self, error_message, packages):
        self.worker = None
        if error_message:
            self.session.open(MessageBox, error_message, type=MessageBox.TYPE_ERROR)
            self["description"].setText(error_message)
            return
        if self.filter_keywords:
            filtered_packages = []
            for pkg in packages:
                pkg_name_lower = pkg.get('name', '').lower()
                if any(keyword.lower() in pkg_name_lower for keyword in self.filter_keywords):
                    filtered_packages.append(pkg)
            self.packages = sorted(filtered_packages, key=lambda p: p['name'])
        else:
            self.packages = sorted(packages, key=lambda p: p['name'])
        if not self.packages:
            msg = "Nie znaleziono żadnych pasujących pakietów." if self.filter_keywords else "Brak dostępnych pakietów."
            self["description"].setText(msg)
            self["list"].setList([])
        else:
            menu_list = [(f"{p['name']} ({p['version']}) - [{p['status']}]", p) for p in self.packages]
            self["list"].setList(menu_list)
        self.on_selection_changed()

    def on_selection_changed(self):
        current = self["list"].getCurrent()
        if current:
            self["description"].setText(current[1].get('description', 'Brak opisu.'))
        else:
            msg = "Nie znaleziono żadnych pasujących pakietów." if self.filter_keywords else "Brak dostępnych pakietów."
            self["description"].setText(msg)

    def handle_action(self):
        current = self["list"].getCurrent()
        if not current: return
        self.install_package() if current[1]['status'] != 'Zainstalowany' else self.remove_package()

    def install_package(self): self._run_opkg_command("install")
    def remove_package(self): self._run_opkg_command("remove")

    def _run_opkg_command(self, action):
        current = self["list"].getCurrent()
        if not current: return
        pkg = current[1]
        if action == "install" and pkg['status'] == 'Zainstalowany':
            self.session.open(MessageBox, "Ten pakiet jest już zainstalowany.", type=MessageBox.TYPE_INFO)
            return
        if action == "remove" and pkg['status'] != 'Zainstalowany':
            self.session.open(MessageBox, "Ten pakiet nie jest zainstalowany.", type=MessageBox.TYPE_INFO)
            return
        command = f"opkg {action} {pkg['name']}"
        title = f"{'Instalowanie' if action == 'install' else 'Odinstalowywanie'}: {pkg['name']}"
        self.session.openWithCallback(self.refresh_list, OpkgCommandScreen, command=command, title=title)

class AzmanPanelMainScreen(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.current_worker = None
        
        
        self.GRID_ROWS, self.GRID_COLS = 3, 4
        self.GRID_WIDGET_COLS = 6
        
        self.menu_items = []
        self.all_menu_items = []
        self.tabs = ["Pluginy", "Bukiety/Listy kanałów", "EPG/Picony", "Narzędzia/Inne wtyczki", "Info"]
        self.current_tab_index = 0
        self.markerPixmap = LoadPixmap(f"{PLUGIN_PATH}/icons/marker-cyan.png")
        self.selected_pos = (0, 0)
        self.params_for_screen_after_install = None
        
        self.open_timer = eTimer()
        
        self["title"] = Label("Azman Panel")
        self["credits_label"] = Label(constants.PLUGIN_VERSION)
        self["key_red"] = StaticText("Zamknij")
        self["key_green"] = StaticText("Instaluj")
        self["key_yellow"] = StaticText("Poprzednia zakładka")
        self["key_blue"] = StaticText("Następna zakładka")
        self["description"] = Label("")
        self["selected_title"] = StaticText("")
        self["tabs"] = Label("")
        self["plugin_info_title"] = Label("")
        self["plugin_info_version"] = Label("")
        self["plugin_info_desc"] = Label("")
        self["info_content"] = Label("")
        for r in range(self.GRID_ROWS):
            for c in range(self.GRID_WIDGET_COLS):
                self[f"logo_{r}x{c}"], self[f"marker_{r}x{c}"] = Pixmap(), Pixmap()
                self[f"tile_title_{r}x{c}"] = Label("")
                if c >= self.GRID_COLS:
                    self[f"logo_{r}x{c}"].hide()
                    self[f"marker_{r}x{c}"].hide()
                    self[f"tile_title_{r}x{c}"].hide()
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {"ok": self.run_selected_item, "cancel": self.close,
             "up": lambda: self.move(-1, 0), "down": lambda: self.move(1, 0),
             "left": lambda: self.move(0, -1), "right": lambda: self.move(0, 1),
             "red": self.close, "green": self.install_selected, "yellow": self.previous_tab, "blue": self.next_tab}, -1)
        self.onLayoutFinish.append(self.prepare_menu)
        self.onClose.append(self.__onClose)

    def __onClose(self):
        if self.current_worker and self.current_worker.is_alive(): self.current_worker.cancel()
        self.open_timer.stop()

    def _load_icon(self, icon_name):
        path = f"{PLUGIN_PATH}/icons/{icon_name}"
        return LoadPixmap(path) if os.path.exists(path) else LoadPixmap(f"{PLUGIN_PATH}/icons/icon_placeholder.png")

    def prepare_menu(self):
        menu_definitions = [
            
            ("Azman Player", lambda: self.show_coming_soon("Azman Player"), "icon_azmanplayer.png", "Odtwarzacz i centrum kana\u0142\u00f3w Azman - telewizja, radio i zarz\u0105dzanie \u017ar\u00f3d\u0142ami w jednym miejscu."),
            ("Stacja Meteo MMz", self.start_stacjameteommz_install, "icon_stacjameteommz.png", "Szczeg\u00f3\u0142owe dane pogodowe, wiatr, opady, jako\u015b\u0107 powietrza i astronomia.\nKartka z kalendarza: imieniny, \u015bwi\u0119ta, przys\u0142owie, cytat dnia, porady ogrodnicze, wp\u0142yw Ksi\u0119\u017cyca i biorytm."),
            
            ("Bukiety IPTV PL", self.open_iptv_bouquet_manager, "icon_iptv_pl.png", "Polskie kana\u0142y IPTV uporz\u0105dkowane w gotowych bukietach Enigma2."),
            ("Bukiety FAST", lambda: self.show_coming_soon("Bukiety FAST"), "icon_fast.png", "Gotowe bukiety kana\u0142\u00f3w FAST - funkcja zostanie udost\u0119pniona wkr\u00f3tce."),
            ("MyRadioOnline", self.start_myradioonline_bouquet, "icon_myradioonline.png", "Tworzy bukiet polskich i zagranicznych stacji radiowych MyRadioOnline."),
            ("Polskie Radio", self.start_polskieradio_bouquet, "icon_polskieradio.png", "Tworzy bukiet stacji Polskiego Radia wraz z kana\u0142ami tematycznymi i regionalnymi."),
            ("RMF ON", self.start_rmfon_bouquet, "icon_rmfon.png", "Tworzy bukiet stacji radiowych dost\u0119pnych w serwisie RMF ON."),
            ("Eurozet", self.start_eurozet_bouquet, "icon_eurozet.png", "Tworzy bukiet stacji grupy Eurozet, m.in. Radio ZET, Antyradio i Meloradio."),
            
            
            ("Dodatki do E2K", self.open_e2k_addons_manager, "icon_e2k.png", "Miejsce na dodatki i rozszerzenia dla E2Kodi - wkr\u00f3tce."),
            ("Polskie \u017ar\u00f3d\u0142a EPG", lambda: self.show_coming_soon("Polskie zrodla EPG"), "icon_epg.png", "Polskie \u017ar\u00f3d\u0142a programu TV dla EPG Import - funkcja zostanie udost\u0119pniona wkr\u00f3tce."),
            ("IPTV.ORG", self.start_iptv_org_install, "icon_iptvorg.png", "Tworzy aktualny bukiet polskich kana\u0142\u00f3w z publicznej listy IPTV.ORG."),
            ("Picons", self.open_picon_manager, "icon_picons.png", "Pobieranie i instalacja picon\u00f3w kana\u0142\u00f3w do wybranej lokalizacji na dekoderze."),
            ("Karcher Radio Control", lambda: self.show_coming_soon("Karcher Radio Control"), "icon_karcherradiocontrol.png", "Sterowanie radiem Karcher, szybki dost\u0119p do jego funkcji oraz odczyt RDS aktualnie granej stacji."),
            ("YT Playlist Player", self.show_work_in_progress, "icon_ytplaylistplayer.png", "Wygodne odtwarzanie w\u0142asnych playlist YouTube na ekranie Enigma2."),
            ("Monitor Burz", self.start_monitoringburz_install, "icon_monitoringburz.png", "Bie\u017c\u0105cy podgl\u0105d wy\u0142adowa\u0144 atmosferycznych i aktywno\u015bci burzowej."),
            ("Kalendarz Ogrodnika", self.show_work_in_progress, "icon_kalendarzogrod.png", "Kalendarz, porady ogrodnicze, fazy Ksi\u0119\u017cyca i informacje pomocne w planowaniu prac."),
            
            ("IMGW Meteo", self.start_imgwmeteo_install, "icon_imgwmeteo.png", "Aktualna pogoda IMGW, mapy, prognozy i ostrze\u017cenia dla zapisanych lokalizacji."),
            ("Shelly Control", self.show_work_in_progress, "icon_shellycontrolcenter.png", "Sterowanie urz\u0105dzeniami Shelly bezpo\u015brednio z dekodera oraz odczyt danych urz\u0105dze\u0144 w czasie rzeczywistym."),
            ("MiHome Control", self.show_work_in_progress, "icon_mihomecontrol.png", "Obs\u0142uga wybranych urz\u0105dze\u0144 Xiaomi Mi Home. Obecnie odczyt i sterowanie Xiaomi Mi Purifier oraz Mi Box S."),
            ("Archiv CZSK", self.start_archivczsk_install, "icon_archivczsk.png", "Odtwarzanie tre\u015bci wideo i archiw\u00f3w czesko-s\u0142owackich w Enigma2."),
            ("AjPanel", self.start_ajpanel_install, "icon_ajpanel.png", "Zewn\u0119trzne narz\u0119dzie administracyjne i konfiguracyjne dla Enigma2."),
            ("M3UIPTV", self.start_m3uiptv_install, "icon_m3uiptv.png", "Konwertuje listy M3U do bukiet\u00f3w kana\u0142\u00f3w Enigma2."),
            ("Airly", self.start_airly_install, "icon_airly.png", "Monitoring jako\u015bci powietrza w Polsce i na \u015bwiecie."),
            ("Aktualizacja satellites.xml", self.start_satellites_xml_update, "icon_satellitesxml.png", "Pobiera aktualny satellites.xml z OE-Alliance lub OpenPLi i tworzy kopię pliku przed zapisem."),
        ]
        
        coming_soon_names = (
            "Bukiety FAST", "Polskie \u017ar\xf3d\u0142a EPG", "Azman Player", "YT Playlist Player",
            "Shelly Control", "MiHome Control", "Karcher Radio Control", "Kalendarz Ogrodnika",
        )
        menu_definitions = [
            (text, (lambda name=text: self.show_coming_soon(name)) if text in coming_soon_names else func, icon, description)
            for text, func, icon, description in menu_definitions
        ]

        num_items = len(menu_definitions)
        items_to_add = (self.GRID_COLS - (num_items % self.GRID_COLS)) % self.GRID_COLS
        
        for _ in range(items_to_add):
            menu_definitions.append(
                ("Wkrótce...", self.show_work_in_progress, "icon_placeholder.png", "Nowe funkcje pojawią się wkrótce.")
            )

        self.all_menu_items = [{"text": t, "func": f, "pixmap": self._load_icon(i), "desc": d} for t, f, i, d in menu_definitions]
        self.apply_tab_filter()
        self.draw_page()


    def get_item_category(self, item):
        text = item["text"]
        if "EPG" in text or text == "Picons":
            return "EPG/Picony"
        channel_names = ("Bukiety IPTV PL", "Bukiety FAST", "IPTV.ORG", "MyRadioOnline", "Polskie Radio", "RMF ON", "Eurozet")
        if text in channel_names:
            return "Bukiety/Listy kanałów"
        tool_names = ("Archiv CZSK", "AjPanel", "Dodatki do E2K", "M3UIPTV", "Airly", "Aktualizacja satellites.xml")
        if text in tool_names:
            return "Narzędzia/Inne wtyczki"
        plugin_names = ("Azman Player", "Stacja Meteo MMz", "IMGW Meteo", "Shelly Control", "Karcher Radio Control", "MiHome Control", "YT Playlist Player", "Monitor Burz", "Kalendarz Ogrodnika")
        if text in plugin_names:
            return "Pluginy"
        if text == "M3UIPTV":
            return "Narzędzia/Inne wtyczki"
        return "Info"

    def apply_tab_filter(self):
        selected_tab = self.tabs[self.current_tab_index]
        self.menu_items = [item for item in self.all_menu_items if self.get_item_category(item) == selected_tab]
        if selected_tab == "Pluginy":
            plugin_order = (
                "Azman Player", "YT Playlist Player", "IMGW Meteo", "Stacja Meteo MMz",
                "Monitor Burz", "Shelly Control", "MiHome Control", "Karcher Radio Control",
                "Kalendarz Ogrodnika"
            )
            order_map = {name: index for index, name in enumerate(plugin_order)}
            self.menu_items.sort(key=lambda item: order_map.get(item["text"], len(order_map)))
        elif selected_tab == "EPG/Picony":
            order = ("Picons", "Polskie \u017ar\u00f3d\u0142a EPG")
            order_map = {name: index for index, name in enumerate(order)}
            self.menu_items.sort(key=lambda item: order_map.get(item["text"], len(order_map)))
        elif selected_tab == "Bukiety/Listy kanałów":
            order = ("Bukiety IPTV PL", "Bukiety FAST", "IPTV.ORG", "MyRadioOnline", "RMF ON", "Polskie Radio", "Eurozet")
            order_map = {name: index for index, name in enumerate(order)}
            self.menu_items.sort(key=lambda item: order_map.get(item["text"], len(order_map)))
        elif selected_tab == "Narzędzia/Inne wtyczki":
            order = ("AjPanel", "M3UIPTV", "Dodatki do E2K", "Archiv CZSK", "Airly", "Aktualizacja satellites.xml")
            order_map = {name: index for index, name in enumerate(order)}
            self.menu_items.sort(key=lambda item: order_map.get(item["text"], len(order_map)))
        if selected_tab == "Info":
            self.menu_items = []
            python_version = runtime.get_runtime_info()["python"]
            self["info_content"].setText(
                "Azman Panel\n\n"
                "Centralny panel narzędziowy ekosystemu Azman dla Enigma2.\n\n"
                "Panel jest instalowany jako pierwszy plugin na dekoderze.\n"
                "Z niego instalowane są pozostałe pluginy Azman, bukiety, listy kanałów,\n"
                "EPG, picony oraz inne narzędzia z feeda Azman.\n\n"
                "Wersja panelu: %s\n"
                "Format wersji: YYYY.MM.DD-HHMM\n\n"
                "Sterowanie:\n"
                "OK — otwórz zaznaczony element\n"
                "ZIELONY — instaluj zaznaczony plugin\n"
                "ŻÓŁTY — poprzednia zakładka\n"
                "NIEBIESKI — następna zakładka\n"
                "CZERWONY — zamknij panel" % constants.PLUGIN_VERSION
            )
            self["info_content"].setText(
                "Azman Panel\n\n"
                "Centralny panel instalacyjny i narzedziowy dla Enigma2.\n\n"
                "Panel jest instalowany jako pierwszy plugin na dekoderze.\n"
                "Z niego instalujesz pluginy Azman, bukiety, EPG, picony i inne narzedzia.\n\n"
                "Srodowisko Python dekodera: %s\n"
                "Panel instaluje tylko paczki zgodne z ta wersja.\n\n"
                "Wersja panelu: %s\n"
                "Wersjonowanie: YYYY.MM.DD-HHMM\n\n"
                "ZIELONY - wlacz/wylacz widocznosc Panelu w glownym menu Enigma2\n\n"
                "Sterowanie:\n"
                "OK - otworz zaznaczony element\n"
                "ZIELONY - instaluj zaznaczony plugin\n"
                "ZOLTY - poprzednia zakladka\n"
                "NIEBIESKI - nastepna zakladka\n"
                "CZERWONY - zamknij panel" % (python_version, constants.PLUGIN_VERSION)
            )
            self["info_content"].show()
            self["key_green"].setText("Widocznosc menu")
        else:
            self["info_content"].setText("")
            self["info_content"].hide()
        self.GRID_ROWS = max(1, (len(self.menu_items) + self.GRID_COLS - 1) // self.GRID_COLS)
        self.selected_pos = (0, 0)
        self["tabs"].setText("  |  ".join(("[%s]" % tab) if index == self.current_tab_index else tab for index, tab in enumerate(self.tabs)))

    def next_tab(self):
        self.current_tab_index = (self.current_tab_index + 1) % len(self.tabs)
        self.apply_tab_filter()
        self.draw_page()

    def previous_tab(self):
        self.current_tab_index = (self.current_tab_index - 1) % len(self.tabs)
        self.apply_tab_filter()
        self.draw_page()
        
    def draw_page(self):
        
        
        for r in range(3):
            for c in range(self.GRID_WIDGET_COLS):
                item_index = r * self.GRID_COLS + c
                logo_widget = self[f"logo_{r}x{c}"]
                if c < self.GRID_COLS and r < self.GRID_ROWS and item_index < len(self.menu_items):
                    logo_widget.instance.setPixmap(self.menu_items[item_index]["pixmap"])
                    logo_widget.show()
                    title = self.menu_items[item_index]["text"]
                    self[f"tile_title_{r}x{c}"].setText(title if len(title) <= 24 else title[:23] + "…")
                    self[f"tile_title_{r}x{c}"].show()
                else:
                    logo_widget.hide()
                    self[f"tile_title_{r}x{c}"].setText("")
                    self[f"tile_title_{r}x{c}"].hide()
        self.update_selection()

    def update_selection(self):
        for r in range(3):
            for c in range(self.GRID_WIDGET_COLS):
                self[f"marker_{r}x{c}"].hide()
        sel_r, sel_c = self.selected_pos
        item_index = sel_r * self.GRID_COLS + sel_c
        if item_index < len(self.menu_items):
            marker_widget = self[f"marker_{sel_r}x{sel_c}"]
            marker_widget.instance.setPixmap(self.markerPixmap)
            marker_widget.show()
            selected_item = self.menu_items[item_index]
            self["selected_title"].setText(f" -  {selected_item['text']}")
            self["description"].setText("")
            self["plugin_info_title"].setText(selected_item["text"])
            self["plugin_info_version"].setText("")
            self["plugin_info_version"].setText("Wersja: dostępna w feedzie Azman")
            self["plugin_info_desc"].setText(selected_item["desc"])
            self["plugin_info_version"].setText("")
        else:
            self["selected_title"].setText("")
            self["description"].setText("Brak elementów w tej kategorii.")
            self["plugin_info_title"].setText("")
            self["plugin_info_version"].setText("")
            self["plugin_info_desc"].setText("")

    def install_selected(self):
        if self.tabs[self.current_tab_index] == "Info":
            self.toggle_main_menu_visibility()
            return
        item_index = self.selected_pos[0] * self.GRID_COLS + self.selected_pos[1]
        if item_index >= len(self.menu_items):
            return
        item = self.menu_items[item_index]
        coming_soon_names = (
            "Bukiety FAST", "Polskie \u017ar\xf3d\u0142a EPG", "Azman Player", "YT Playlist Player",
            "Shelly Control", "MiHome Control", "Karcher Radio Control", "Kalendarz Ogrodnika",
        )
        if item["text"] in coming_soon_names:
            self.show_coming_soon(item["text"])
            return
        if self.get_item_category(item) != "Pluginy":
            self.session.open(MessageBox, "Przycisk Instaluj dotyczy pluginów z zakładki Pluginy.", type=MessageBox.TYPE_INFO)
            return
        
        
        if item["text"] == "Monitor Burz":
            self.start_monitoringburz_install()
            return
        if item["text"] == "Stacja Meteo MMz":
            self.start_stacjameteommz_install()
            return
        if item["text"] == "IMGW Meteo":
            self.start_imgwmeteo_install()
            return
        keyword = item["text"].lower().replace(" ", "")
        self._open_package_manager("Instalowanie - " + item["text"], filter_keywords=[keyword])

    def toggle_main_menu_visibility(self):
        config.plugins.AzmanPanel.main_menu_visible.value = not config.plugins.AzmanPanel.main_menu_visible.value
        save_config()
        state = "wlaczona" if config.plugins.AzmanPanel.main_menu_visible.value else "wylaczona"
        self.apply_tab_filter()
        self.draw_page()
        self.session.open(
            MessageBox,
            "Widocznosc Azman Panel w glownym menu Enigma2: %s.\n\nZrestartuj GUI, aby zastosowac zmiane." % state,
            MessageBox.TYPE_INFO,
            timeout=8,
        )

    def move(self, d_row, d_col):
        if not self.menu_items:
            return
        current_index = self.selected_pos[0] * self.GRID_COLS + self.selected_pos[1]
        if d_col:
            step = 1 if d_col > 0 else -1
        else:
            step = self.GRID_COLS if d_row > 0 else -self.GRID_COLS
        new_index = (current_index + step) % len(self.menu_items)
        self.selected_pos = (new_index // self.GRID_COLS, new_index % self.GRID_COLS)
        self.update_selection()

    def run_selected_item(self):
        item_index = self.selected_pos[0] * self.GRID_COLS + self.selected_pos[1]
        if item_index < len(self.menu_items):
            try:
                self.menu_items[item_index]["func"]()
            except Exception as e:
                utils.log_error(e, f"run_selected_item: {self.menu_items[item_index]['text']}")
                self.session.open(MessageBox, f"Wystąpił błąd:\n{e}", type=MessageBox.TYPE_ERROR)

    def show_work_in_progress(self):
        self.session.open(MessageBox, "Ta funkcja jest obecnie w budowie.\nZapraszamy wkrótce!", type=MessageBox.TYPE_INFO, title="Informacja")

    def show_coming_soon(self, feature_name):
        self.session.open(
            MessageBox,
            "%s bedzie dostepny w Azman Panel wkrotce." % feature_name,
            type=MessageBox.TYPE_INFO,
            title="Wkrotce",
        )

    def _open_package_manager(self, title, filter_keywords=None):
        if os.path.exists(constants.FEED_CONF_TARGET_PATH):
            self.session.open(AzmanFeedScreen, title=title, filter_keywords=filter_keywords)
        else:
            self.params_for_screen_after_install = {'title': title, 'filter_keywords': filter_keywords}
            message = "Repozytorium Azman Feed nie jest zainstalowane.\n\nCzy chcesz zainstalować je teraz?"
            self.session.openWithCallback(self._proceed_with_feed_install, MessageBox, message, MessageBox.TYPE_YESNO, default=True)

    def open_e2k_addons_manager(self):
        self.session.open(
            MessageBox,
            "Dodatki do E2Kodi będą dostępne wkrótce.",
            type=MessageBox.TYPE_INFO,
            title="Dodatki do E2Kodi"
        )

    def _proceed_with_feed_install(self, confirmed):
        if not confirmed:
            self.session.open(MessageBox, "Instalacja anulowana.", type=MessageBox.TYPE_INFO)
            return
        command = (f"curl -s --insecure -o {constants.FEED_CONF_TARGET_PATH} {constants.FEED_CONF_URL} && opkg update")
        title = "Instalowanie Azman Feed"
        self.session.openWithCallback(self.on_feed_install_finished, OpkgCommandScreen, title=title, command=command)

    def on_feed_install_finished(self, *args):
        if os.path.exists(constants.FEED_CONF_TARGET_PATH):
            def open_target_screen(confirmed):
                if self.params_for_screen_after_install:
                    self.session.open(AzmanFeedScreen, **self.params_for_screen_after_install)
                    self.params_for_screen_after_install = None
            message = "Repozytorium Azman Feed zostało dodane!\n\nZostaniesz teraz przeniesiony do menedżera pakietów."
            self.session.openWithCallback(open_target_screen, MessageBox, message, type=MessageBox.TYPE_INFO, timeout=5)
        else:
            message = "Wystąpił błąd podczas instalacji feeda.\n\nSprawdź połączenie z internetem i spróbuj ponownie."
            self.session.open(MessageBox, message, type=MessageBox.TYPE_ERROR)
            
    def open_picon_manager(self):
        saved_path = config.plugins.AzmanPanel.picon_path.value
        parent_dir = os.path.dirname(saved_path)
        if os.path.exists(parent_dir) and os.access(parent_dir, os.W_OK):
            self.on_picon_path_selected(saved_path)
        else:
            self.session.openWithCallback(self.on_picon_path_selected, PiconPathSelectionScreen)
            
    def on_picon_path_selected(self, target_dir):
        if not target_dir: return
        config.plugins.AzmanPanel.picon_path.value = target_dir
        save_config()
        self.picon_target_dir = target_dir
        self._open_picon_selection_screen()
        
    def _open_picon_selection_screen(self, *args):
        self.current_worker = PiconZipListWorker(callback_finished=self.on_picon_list_downloaded)
        self.current_worker.start()
        
    def on_picon_list_downloaded(self, error_message, picon_zip_filenames):
        self.current_worker = None
        if error_message or not picon_zip_filenames:
            msg = error_message or "Nie znaleziono plików *.zip na serwerze."
            self.session.open(MessageBox, msg, MessageBox.TYPE_ERROR)
            return
        item_list = [(filename, urllib.parse.unquote(filename)) for filename in picon_zip_filenames]
        def open_select_list_screen():
            self.session.open(
                PackageTileSelectionScreen,
                item_list,
                "Lokalizacja instalacji: %s" % self.picon_target_dir,
                self.on_picons_selected,
                icon_name="icon_picon_package.png",
            )
        
        self.open_timer.stop()
        self.open_timer.callback.clear()
        self.open_timer.callback.append(open_select_list_screen)
        self.open_timer.start(1, True)

    def on_picons_selected(self, selected_zips):
        if not selected_zips: return
        self._defer_action(lambda: self._open_picon_confirmation(list(selected_zips)))

    def _open_picon_confirmation(self, selected_zips):
        names = "\n".join(urllib.parse.unquote(name) for name in selected_zips)
        message = (
            "Wybrane paczki picon zostaną zainstalowane w:\n"
            "%s\n\n"
            "Istniejące pliki picon o tych samych nazwach zostaną nadpisane.\n\n"
            "Czy kontynuować?\n\n%s"
        ) % (self.picon_target_dir, names)
        self.session.openWithCallback(
            lambda confirmed: confirmed and self._defer_picons_install(selected_zips),
            MessageBox, message, MessageBox.TYPE_YESNO, default=True
        )

    def _defer_picons_install(self, selected_zips):
        self._pending_picon_install = selected_zips
        self.open_timer.stop()
        self.open_timer.callback.clear()
        self.open_timer.callback.append(self._open_picons_install)
        self.open_timer.start(1, True)

    def _open_picons_install(self):
        selected_zips = getattr(self, "_pending_picon_install", None)
        self._pending_picon_install = None
        if selected_zips:
            self._start_picons_install(selected_zips)

    def _start_picons_install(self, selected_zips):
        self.progress_screen = self.session.open(DownloadProgressScreen, title="Instalowanie picon...")
        self.current_worker = PiconInstallationWorker(selected_zips=selected_zips, target_dir=self.picon_target_dir, callback_progress=self.progress_screen.setProgress, callback_finished=self.on_picon_installation_finished)
        self.progress_screen.parent_worker = self.current_worker
        self.current_worker.start()
        
    def on_picon_installation_finished(self, final_message):
        self.current_worker = None
        def after_messagebox_callback(result):
            if hasattr(self, 'progress_screen') and self.progress_screen:
                self.progress_screen.close()
            self._open_picon_selection_screen()
        self.session.openWithCallback(after_messagebox_callback, MessageBox, f"Zakończono instalację picon.\n\n{final_message}", type=MessageBox.TYPE_INFO)

    def start_satellites_xml_update(self):
        choices = [(label, (label, url)) for _key, label, url in constants.SATELLITES_XML_SOURCES]
        self.session.openWithCallback(
            self._select_satellites_xml_source,
            ChoiceBox,
            title="Wybierz źródło satellites.xml",
            list=choices,
        )

    def _select_satellites_xml_source(self, choice):
        if not choice:
            return
        source_name, source_url = choice[1]
        choices = (
            ("/etc/tuxbox/satellites.xml", ["/etc/tuxbox/satellites.xml"]),
            ("/etc/enigma2/satellites.xml", ["/etc/enigma2/satellites.xml"]),
            ("Obie lokalizacje", ["/etc/tuxbox/satellites.xml", "/etc/enigma2/satellites.xml"]),
        )
        self.session.openWithCallback(
            lambda target: self._select_satellites_xml_target(source_name, source_url, target),
            ChoiceBox,
            title="Wybierz lokalizację zapisu",
            list=choices,
        )

    def _select_satellites_xml_target(self, source_name, source_url, choice):
        if not choice:
            return
        target_paths = choice[1]
        message = (
            "Pobrać satellites.xml ze źródła %s?\n\n"
            "Przed zapisem zostanie wykonana kopia istniejącego pliku.\n"
            "Plik XML zostanie sprawdzony przed zapisem."
        ) % source_name
        self.session.openWithCallback(
            lambda confirmed: confirmed and self._start_satellites_xml_update(source_name, source_url, target_paths),
            MessageBox,
            message,
            MessageBox.TYPE_YESNO,
            default=True,
        )

    def _start_satellites_xml_update(self, source_name, source_url, target_paths):
        self.progress_screen = self.session.open(DownloadProgressScreen, title="Aktualizacja satellites.xml...")
        self.current_worker = SatellitesXmlUpdateWorker(source_name, source_url, target_paths, self._on_satellites_xml_update_finished)
        self.progress_screen.parent_worker = self.current_worker
        self.current_worker.start()

    def _on_satellites_xml_update_finished(self, error_message, final_message):
        self.current_worker = None
        if getattr(self, "progress_screen", None):
            self.progress_screen.close()
        self._defer_action(lambda: self._show_satellites_xml_update_result(error_message, final_message))

    def _show_satellites_xml_update_result(self, error_message, final_message):
        self.session.open(
            MessageBox,
            error_message or final_message or "Operacja zakończona.",
            MessageBox.TYPE_ERROR if error_message else MessageBox.TYPE_INFO,
        )

    def start_myradioonline_bouquet(self):
        self.session.openWithCallback(
            self._confirm_myradioonline_bouquet,
            MessageBox,
            "Pobrać aktualną listę stacji MyRadioOnline i utworzyć bukiet radiowy?\n\n"
            "Dla każdej stacji zostanie wybrany automatycznie najlepszy dostępny bitrate.",
            MessageBox.TYPE_YESNO,
            default=True,
        )

    def _confirm_myradioonline_bouquet(self, confirmed):
        if not confirmed:
            return
        self._defer_action(lambda: self._start_radio_bouquet("MyRadioOnline", MyRadioOnlineBouquetWorker))

    def on_myradioonline_bouquet_finished(self, error_message, final_message):
        self._on_radio_bouquet_finished(error_message, final_message)

    def _show_bouquet_result(self, error_message, final_message):
        self.session.open(MessageBox, error_message or final_message or "Operacja zakończona.", MessageBox.TYPE_ERROR if error_message else MessageBox.TYPE_INFO, timeout=10)

    def start_polskieradio_bouquet(self):
        self.session.openWithCallback(
            self._confirm_polskieradio_bouquet,
            MessageBox,
            "Utworzyć bukiet oficjalnych stacji Polskiego Radia?",
            MessageBox.TYPE_YESNO,
            default=True,
        )

    def _confirm_polskieradio_bouquet(self, confirmed):
        if not confirmed:
            return
        self._defer_action(lambda: self._start_radio_bouquet("Polskie Radio", PolskieRadioBouquetWorker))

    def start_rmfon_bouquet(self):
        self.session.openWithCallback(self._confirm_rmfon_bouquet, MessageBox,
            "Pobrać aktualną listę stacji RMF ON i utworzyć bukiet radiowy?",
            MessageBox.TYPE_YESNO, default=True)

    def _confirm_rmfon_bouquet(self, confirmed):
        if not confirmed: return
        self._defer_action(lambda: self._start_radio_bouquet("RMF ON", RmfonBouquetWorker))

    def on_rmfon_bouquet_finished(self, error_message, final_message):
        self._on_radio_bouquet_finished(error_message, final_message)

    def start_eurozet_bouquet(self):
        self.session.openWithCallback(self._confirm_eurozet_bouquet, MessageBox,
            "Pobrać aktualne stacje Eurozet i utworzyć bukiet radiowy?",
            MessageBox.TYPE_YESNO, default=True)

    def _confirm_eurozet_bouquet(self, confirmed):
        if not confirmed: return
        self._defer_action(lambda: self._start_radio_bouquet("Eurozet", EurozetBouquetWorker))

    def on_eurozet_bouquet_finished(self, error_message, final_message):
        self._on_radio_bouquet_finished(error_message, final_message)

    def _start_radio_bouquet(self, bouquet_name, worker_class):
        self.progress_screen = self.session.open(BouquetGenerationScreen, bouquet_name)
        self.current_worker = worker_class(self._on_radio_bouquet_finished)
        self.current_worker.start()

    def _on_radio_bouquet_finished(self, error_message, final_message):
        self.current_worker = None
        if hasattr(self, "progress_screen") and self.progress_screen:
            self.progress_screen.close()
        self._defer_action(lambda: self._show_bouquet_result(error_message, final_message))

    def on_polskieradio_bouquet_finished(self, error_message, final_message):
        self._on_radio_bouquet_finished(error_message, final_message)

    def open_iptv_bouquet_manager(self, *args):
        self.current_worker = PrivateBouquetListWorker(callback_finished=self.on_iptv_bouquet_list_downloaded)
        self.current_worker.start()

    def on_iptv_bouquet_list_downloaded(self, error_message, bouquet_filenames):
        self.current_worker = None
        if error_message or not bouquet_filenames:
            self.session.open(MessageBox, error_message or "Nie znaleziono bukietów na serwerze.", MessageBox.TYPE_ERROR)
            return
        item_list = [(fn, utils.panel_bouquet_filename(fn).replace("userbouquet.azmanpanel_", "").replace(".tv", "").replace("_", " ").title()) for fn in bouquet_filenames]
        def open_select_list_screen():
            self.session.open(
                PackageTileSelectionScreen,
                item_list,
                "Bukiety zostaną zapisane w /etc/enigma2 i dodane do bouquets.tv.",
                self.on_iptv_bouquets_selected_for_install,
                title="Wybierz bukiety IPTV PL",
                icon_name="icon_bouquet_package.png",
                on_uninstall_callback=self.on_iptv_bouquets_selected_for_uninstall,
            )
        
        self.open_timer.stop()
        self.open_timer.callback.clear()
        self.open_timer.callback.append(open_select_list_screen)
        self.open_timer.start(1, True)
    
    def on_iptv_bouquets_selected_for_install(self, selected_bouquets):
        if not selected_bouquets: return
        self._defer_action(lambda: self._start_iptv_bouquet_install(selected_bouquets))

    def _start_iptv_bouquet_install(self, selected_bouquets):
        self.progress_screen = self.session.open(DownloadProgressScreen, title="Instalowanie bukietów...")
        self.current_worker = PrivateBouquetInstallWorker(selected_bouquets, self.progress_screen.setProgress, self.on_iptv_bouquet_installation_finished)
        self.progress_screen.parent_worker = self.current_worker
        self.current_worker.start()

    def on_iptv_bouquets_selected_for_uninstall(self, selected_bouquets):
        if not selected_bouquets: return
        self._defer_action(lambda: self._start_iptv_bouquet_uninstall(selected_bouquets))

    def _start_iptv_bouquet_uninstall(self, selected_bouquets):
        self.progress_screen = self.session.open(DownloadProgressScreen, title="Odinstalowywanie bukietów...")
        self.current_worker = IptvBouquetUninstallWorker(selected_bouquets, self.progress_screen.setProgress, self.on_iptv_bouquet_installation_finished)
        self.progress_screen.parent_worker = self.current_worker
        self.current_worker.start()

    def on_iptv_bouquet_installation_finished(self, final_message):
        self.current_worker = None
        def after_messagebox_callback(result):
            if hasattr(self, 'progress_screen') and self.progress_screen:
                self.progress_screen.close()
            self.open_iptv_bouquet_manager()
        self.session.openWithCallback(after_messagebox_callback, MessageBox, final_message, type=MessageBox.TYPE_INFO)

        
        
        
        

        
        
        
    def start_monitoringburz_install(self):
        package_name = "enigma2-plugin-extensions--azman-monitoringburz-py313"
        try:
            installed = subprocess.run(
                ["opkg", "list-installed"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False
            ).stdout.decode("utf-8", errors="ignore")
        except Exception:
            installed = ""
        if any(line.startswith(package_name + " ") or line.startswith(package_name + " -")
               for line in installed.splitlines()):
            self.session.openWithCallback(
                self._confirm_monitoringburz_reinstall,
                MessageBox,
                "Monitoring Burz jest już zainstalowany.\n\nCzy chcesz go przeinstalować?",
                MessageBox.TYPE_YESNO,
                default=False
            )
            return
        self._begin_monitoringburz_download()

    def _confirm_monitoringburz_reinstall(self, confirmed):
        if confirmed:
            self._begin_monitoringburz_download()

    def _begin_monitoringburz_download(self):
        message = ("Monitoring Burz jest pobierany z prywatnego, niepublicznego feeda autora.\n\n"
                   "Pobrany pakiet zostanie sprawdzony przez SHA-256 przed instalacją.\n\n"
                   "Czy chcesz kontynuować?")
        self.session.openWithCallback(
            self._confirm_monitoringburz_install,
            MessageBox, message, MessageBox.TYPE_YESNO, default=True
        )

    def _confirm_monitoringburz_install(self, confirmed):
        if not confirmed:
            return
        self._manifest_install_title = "Monitoring Burz"
        self.current_worker = ManifestPackageDownloadWorker(
            "monitoringburz", self._on_manifest_package_ready
        )
        self.download_messagebox = self.session.open(
            MessageBox,
            "Pobieranie i weryfikacja pakietu...",
            type=MessageBox.TYPE_INFO
        )
        self.current_worker.start()

    def start_stacjameteommz_install(self):
        package_name = "enigma2-plugin-extensions--azman-stacjameteommz-py313"
        try:
            installed = subprocess.run(
                ["opkg", "list-installed"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=15, check=False
            ).stdout.decode("utf-8", errors="ignore")
        except Exception:
            installed = ""
        if any(line.startswith(package_name + " ") or line.startswith(package_name + " -")
               for line in installed.splitlines()):
            self.session.openWithCallback(
                self._confirm_stacjameteommz_reinstall,
                MessageBox,
                "Stacja Meteo MMz jest już zainstalowana.\n\nCzy chcesz ją przeinstalować?",
                MessageBox.TYPE_YESNO, default=False
            )
            return
        self._begin_stacjameteommz_download()

    def _confirm_stacjameteommz_reinstall(self, confirmed):
        if confirmed:
            self._begin_stacjameteommz_download()

    def _begin_stacjameteommz_download(self):
        message = (
            "Stacja Meteo MMz jest pobierana z prywatnego, niepublicznego feeda autora.\n\n"
            "Pobrany pakiet zostanie sprawdzony przez SHA-256 przed instalacją.\n\n"
            "Czy chcesz kontynuować?"
        )
        self.session.openWithCallback(
            self._confirm_stacjameteommz_install,
            MessageBox, message, MessageBox.TYPE_YESNO, default=True
        )

    def _confirm_stacjameteommz_install(self, confirmed):
        if not confirmed:
            return
        self._manifest_install_title = "Stacja Meteo MMz"
        self.current_worker = ManifestPackageDownloadWorker(
            "stacjameteommz", self._on_manifest_package_ready
        )
        self.download_messagebox = self.session.open(
            MessageBox, "Pobieranie i weryfikacja pakietu...", type=MessageBox.TYPE_INFO
        )
        self.current_worker.start()

    def start_imgwmeteo_install(self):
        package_name = "enigma2-plugin-extensions--azman-imgwmeteo-py313"
        try:
            installed = subprocess.run(
                ["opkg", "list-installed"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=15, check=False
            ).stdout.decode("utf-8", errors="ignore")
        except Exception:
            installed = ""
        if any(line.startswith(package_name + " ") or line.startswith(package_name + " -")
               for line in installed.splitlines()):
            self.session.openWithCallback(
                self._confirm_imgwmeteo_reinstall,
                MessageBox,
                "IMGW Meteo jest już zainstalowany.\n\nCzy chcesz go przeinstalować?",
                MessageBox.TYPE_YESNO, default=False
            )
            return
        self._begin_imgwmeteo_download()

    def _confirm_imgwmeteo_reinstall(self, confirmed):
        if confirmed:
            self._begin_imgwmeteo_download()

    def _begin_imgwmeteo_download(self):
        message = (
            "IMGW Meteo jest pobierany z prywatnego, niepublicznego feeda autora.\n\n"
            "Pobrany pakiet zostanie sprawdzony przez SHA-256 przed instalacją.\n\n"
            "Czy chcesz kontynuować?"
        )
        self.session.openWithCallback(
            self._confirm_imgwmeteo_install,
            MessageBox, message, MessageBox.TYPE_YESNO, default=True
        )

    def _confirm_imgwmeteo_install(self, confirmed):
        if not confirmed:
            return
        self._manifest_install_title = "IMGW Meteo"
        self.current_worker = ManifestPackageDownloadWorker(
            "imgwmeteo", self._on_manifest_package_ready
        )
        self.download_messagebox = self.session.open(
            MessageBox, "Pobieranie i weryfikacja pakietu...", type=MessageBox.TYPE_INFO
        )
        self.current_worker.start()

    def start_airly_install(self):
        message = (
            "Airly jest pobierany z prywatnego, niepublicznego feeda autora.\n\n"
            "Pobrany pakiet zostanie sprawdzony przez SHA-256 przed instalacją.\n\n"
            "Czy chcesz kontynuować?"
        )
        self.session.openWithCallback(
            self._confirm_airly_install,
            MessageBox, message, MessageBox.TYPE_YESNO, default=True
        )

    def _confirm_airly_install(self, confirmed):
        if not confirmed:
            return
        self._manifest_install_title = "Airly"
        self.current_worker = ManifestPackageDownloadWorker(
            "airly", self._on_manifest_package_ready
        )
        self.download_messagebox = self.session.open(
            MessageBox,
            "Pobieranie i weryfikacja pakietu...",
            type=MessageBox.TYPE_INFO
        )
        self.current_worker.start()

    def _on_manifest_package_ready(self, error_message, package_path):
        self.current_worker = None
        if getattr(self, "download_messagebox", None):
            self.download_messagebox.close()
            self.download_messagebox = None
        self._pending_manifest_result = (error_message, package_path)
        self.open_timer.stop()
        self.open_timer.callback.clear()
        self.open_timer.callback.append(self._open_manifest_result)
        self.open_timer.start(1, True)
        return
        if error_message:
            self.session.open(MessageBox, "Nie udało się przygotować instalacji:\n%s" % error_message, type=MessageBox.TYPE_ERROR)
            return
        if not package_path or not os.path.isfile(package_path):
            self.session.open(MessageBox, "Nie znaleziono pobranego pakietu.", type=MessageBox.TYPE_ERROR)
            return
        self._handle_install_with_restart(
            "Instalowanie %s" % getattr(self, "_manifest_install_title", "pakietu"),
            "opkg --force-reinstall install %s" % shlex.quote(package_path),
            callback=lambda: self._remove_temporary_package(package_path)
        )

    def _open_manifest_result(self):
        error_message, package_path = getattr(self, "_pending_manifest_result", (None, None))
        self._pending_manifest_result = None
        if error_message:
            self.session.open(MessageBox, "Nie udaĹ‚o siÄ™ przygotowaÄ‡ instalacji:\n%s" % error_message, type=MessageBox.TYPE_ERROR)
            return
        if not package_path or not os.path.isfile(package_path):
            self.session.open(MessageBox, "Nie znaleziono pobranego pakietu.", type=MessageBox.TYPE_ERROR)
            return
        self._handle_install_with_restart(
            "Instalowanie %s" % getattr(self, "_manifest_install_title", "pakietu"),
            "opkg --force-reinstall install %s" % shlex.quote(package_path),
            callback=lambda: self._remove_temporary_package(package_path)
        )

    def _remove_temporary_package(self, package_path):
        try:
            if package_path and os.path.isfile(package_path):
                os.unlink(package_path)
        except OSError as error:
            utils.log_error(error, "remove temporary package", path=package_path)

    def _handle_install_with_restart(self, title, command, callback=None):
        self.session.open(
            OpkgCommandScreen, 
            title=title, 
            command=command,
            callback=callback,
            restart_gui=True
        )

    def _defer_action(self, action):
        self.open_timer.stop()
        self.open_timer.callback.clear()
        self.open_timer.callback.append(action)
        self.open_timer.start(1, True)



    def start_iptv_org_install(self):
        message = ("Ta funkcja pobierze listę polskich kanałów z serwisu IPTV.ORG i utworzy z niej nowy bukiet.\n\n"
                   "Istniejący bukiet 'IPTV.ORG Poland' zostanie nadpisany.\n\nCzy chcesz kontynuować?")
        self.session.openWithCallback(
            self._proceed_with_iptv_org_install,
            MessageBox, message, MessageBox.TYPE_YESNO, default=True
        )

    def _proceed_with_iptv_org_install(self, confirmed):
        if not confirmed:
            self.session.open(MessageBox, "Operacja anulowana.", type=MessageBox.TYPE_INFO)
            return
        
        self.current_worker = IptvOrgWorker(callback_finished=self._on_iptv_org_finished)
        self.current_worker.start()
        self.session.open(MessageBox, "Rozpoczęto tworzenie bukietu IPTV.ORG...\nProszę czekać.", type=MessageBox.TYPE_INFO, timeout=3)
        
    def _on_iptv_org_finished(self, error_message, final_message):
        self.current_worker = None
        message = final_message or error_message
        msg_type = MessageBox.TYPE_ERROR if error_message else MessageBox.TYPE_INFO
        self.session.open(MessageBox, message, type=msg_type)

    def start_archivczsk_install(self):
        message = ("Czy na pewno chcesz pobrać i zainstalować plugin ArchivCZSK?\n\n"
                   "Zostanie wykonana zewnętrzna komenda, która pobierze i uruchomi skrypt instalacyjny.")
        self.session.openWithCallback(
            lambda c: c and self._defer_action(lambda: self._handle_install_with_restart("Instalowanie ArchivCZSK", constants.ARCHIVCZSK_INSTALL_CMD)),
            MessageBox, message, MessageBox.TYPE_YESNO, default=False
        )

    def start_ajpanel_install(self):
        message = ("Czy na pewno chcesz pobrać i zainstalować plugin AJPanel?\n\n"
                   "Zostanie wykonana zewnętrzna komenda, która pobierze i uruchomi skrypt instalacyjny.")
        self.session.openWithCallback(
            lambda c: c and self._defer_action(lambda: self._handle_install_with_restart("Instalowanie AJPanel", constants.AJPANEL_INSTALL_CMD)),
            MessageBox, message, MessageBox.TYPE_YESNO, default=False
        )
        
    def start_m3uiptv_install(self):
        message = ("Czy na pewno chcesz pobrać i zainstalować plugin M3U to Bouquet Converter?\n\n"
                   "Zostanie wykonana zewnętrzna komenda, która pobierze i zainstaluje plugin z GitHub.")
        self.session.openWithCallback(
            lambda c: c and self._defer_action(lambda: self._handle_install_with_restart("Instalowanie M3U to Bouquet Converter", constants.M3UIPTV_INSTALL_CMD)),
            MessageBox, message, MessageBox.TYPE_YESNO, default=False
        )
