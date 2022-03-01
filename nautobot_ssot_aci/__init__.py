"""Plugin declaration for nautobot_ssot_aci."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
try:
    from importlib import metadata
except ImportError:
    # Python version < 3.8
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.plugins import PluginConfig

from nautobot_ssot_aci.signals import aci_create_manufacturer, aci_create_site, aci_create_tag, aci_create_custom_field


class NautobotSsotAciConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot_aci plugin."""

    name = "nautobot_ssot_aci"
    verbose_name = "Nautobot SSoT for Cisco ACI"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot SSoT for Cisco ACI."
    base_url = "nautobot-ssot-aci"
    required_settings = []
    min_version = "1.1.0"
    max_version = "1.9999"
    default_settings = {"tag": "ACI", "tag_color": "FF3333", "manufacturer_name": "Cisco", "site": "Data Center"}
    caching_config = {}

    def ready(self):
        super().ready()

        nautobot_database_ready.connect(aci_create_tag, sender=self)
        nautobot_database_ready.connect(aci_create_manufacturer, sender=self)
        nautobot_database_ready.connect(aci_create_site, sender=self)
        nautobot_database_ready.connect(aci_create_custom_field, sender=self)


config = NautobotSsotAciConfig  # pylint:disable=invalid-name