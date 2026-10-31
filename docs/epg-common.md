# Shared EPG mechanism based on FTVP

All three plugins use the same EPG engine. Each plugin ships its own copy,
so installing the other two plugins is not required. epg_profile.py defines
only the bouquet prefix, report filenames and provider exclusions.

Shared source files: epg_access.py, epg_events.py, epg_jobs.py,
epg_validation.py, epg_reports.py, epg_http_transport.py, private_storage.py.
The FTVP epg_mapper.py is copied as epg_mapper_base.py in Panel and Player.
Their epg_mapper.py files are small adapters for existing plugin interfaces.
The cross-plugin regression test rejects accidental engine drift.

Access and registration use /etc/AzmanPanel/epg_access.json and a common lock.
Registration obtains one box identity and token, reused by all three plugins.
Private API redirects are refused. A rejected token can be re-registered.
The registration filter key already present in FTVP is not a DRM credential.

Names are mapped in batches when writing a bouquet. Mapping caches are in
memory, with no persistent mapping file. Panel preserves its radio aliases;
Player removes known provider labels and copies the complete DVB identity
without changing the playback URL or backend service type.

Events are requested by DVB reference, up to 25 per request. Each plugin
scans only its own TV/radio bouquets and recognizes 4097 and 5002 service
entries, including names on a separate DESCRIPTION line. Unmapped zero
references are skipped. FTVP retains its provider exclusions.

Import runs after a bouquet is written, at GUI startup and every 12 hours.
A single-bouquet import does not overwrite reports for other providers.
Queues coalesce work and serialize imports across plugins. HTTP fetches run
in background threads; native eEPGCache.importEvents calls run on Enigma's
main thread. Failed transport is not classified as missing guide data.
Reports preserve previous successful scopes when a fetch fails.

Report prefixes in /tmp:
- Panel: azmanpanel_epg
- FTVP: azmanfreetv_epg
- Player: azmanplayer_epg
Each has _missing_mappings.json, _missing_events.json and _status.json.

The removed Panel external-IPTV audit stays disabled. No arbitrary external
bouquets are scanned or rewritten by this unification. DRM logic is not
shared with the public plugins. No server-side changes are required.

Installation: update complete plugin source sets, not just plugin.py, and
restart GUI once. Existing bouquets with zero DVB references need to be
regenerated to receive mappings; event import cannot invent a mapping.
Actual event availability still depends on the private API source coverage.
