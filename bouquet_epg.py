"""Assign EPG through the shared mapper to bouquets installed by this Panel."""
import os

from .epg_mapper import PanelEpgMapper
from .epg_validation import valid_reference
from . import utils

PROVIDERS_BY_TSID = {
    "A33A": "azman", "A44A": "tvpvod", "A55A": "sweettv", "A66A": "rakuten",
    "A77A": "lgchannels", "A88A": "playerpl", "A99A": "polsatboxgo", "B11B": "xiaomi",
    "B22B": "avios", "B33B": "channelbox", "B44B": "eurozet", "B55B": "magentatv",
    "B66B": "megogo", "B77B": "miamitv", "B88B": "myradioonline", "B99B": "pilotwp",
    "C11C": "playerpl", "C22C": "playnow", "C33C": "plex", "C44C": "polsatboxgo",
    "C55C": "polskieradio", "C66C": "rmfon", "C77C": "tclstream", "C88C": "telewizjaonline",
    "C99C": "titan", "D11D": "truthplus", "D22D": "vidaa", "D33D": "waipu",
    "D44D": "wedotv", "D55D": "whale",
}


def assign_bouquet_epg(path, mapper_factory=None):
    """Preserve stream URLs and existing references when no mapping is returned."""
    mapper_factory = mapper_factory or (lambda provider: PanelEpgMapper(provider_id=provider))
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()
    scope = os.path.basename(path).removeprefix("userbouquet.azmanpanel_").rsplit(".", 1)[0]
    rows = []
    mappers = {}
    for index, line in enumerate(lines):
        if not line.startswith("#SERVICE "):
            continue
        fields = line[len("#SERVICE "):].rstrip("\r\n").split(":", 10)
        if len(fields) != 11 or fields[0] not in ("4097", "5002"):
            continue
        name = fields[10].partition(":")[2].strip()
        if index + 1 < len(lines) and lines[index + 1].startswith("#DESCRIPTION "):
            name = lines[index + 1][len("#DESCRIPTION "):].strip() or name
        if not name:
            continue
        provider = PROVIDERS_BY_TSID.get(fields[4].upper(), scope)
        if provider not in mappers:
            mappers[provider] = mapper_factory(provider)
        rows.append((index, fields, name, provider))
    for provider, mapper in mappers.items():
        mapper.prefetch([name for _, _, name, selected in rows if selected == provider])
    changed = 0
    for index, fields, name, provider in rows:
        reference = mappers[provider].reference(name)
        if valid_reference(reference) and reference != ":".join(fields[1:10]):
            lines[index] = "#SERVICE " + fields[0] + ":" + reference + ":" + fields[10] + "\n"
            changed += 1
    for mapper in mappers.values():
        mapper.save_report()
    if changed:
        utils.atomic_write_lines(path, lines)
    return changed
