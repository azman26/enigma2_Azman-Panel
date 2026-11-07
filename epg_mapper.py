"""Panel adapter for the FTVP EPG mapper."""
from .epg_mapper_base import FreeTvEpgMapper, EPG_EXCLUDED_PROVIDERS
from . import utils


class PanelEpgMapper(FreeTvEpgMapper):
    def __init__(self, provider_id=None):
        super(PanelEpgMapper, self).__init__(logger=utils.log_event, provider_id=provider_id)

    def _candidates(self, name):
        text = str(name or "").strip()
        values = super(PanelEpgMapper, self)._candidates(text)
        if text:
            values.extend(("Polskie Radio " + text, "PolskieRadio" + text))
        return list(dict.fromkeys(values))
