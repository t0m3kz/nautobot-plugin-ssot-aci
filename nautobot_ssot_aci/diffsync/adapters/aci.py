from diffsync import DiffSync
from nautobot_ssot_aci.constant import PLUGIN_CFG
from nautobot_ssot_aci.diffsync.models import NautobotTenant
from nautobot_ssot_aci.diffsync.models import NautobotDeviceType
from nautobot_ssot_aci.diffsync.models import NautobotDeviceRole
from nautobot_ssot_aci.diffsync.models import NautobotDevice
from nautobot_ssot_aci.diffsync.models import NautobotInterfaceTemplate
from nautobot_ssot_aci.diffsync.models import NautobotInterface
from nautobot_ssot_aci.diffsync.models import NautobotIPAddress
from nautobot_ssot_aci.diffsync.models import NautobotPrefix
from nautobot_ssot_aci.diffsync.client import AciApi
from nautobot_ssot_aci.diffsync.utils import load_yamlfile
from ipaddress import IPv4Network
import logging
import os

logger = logging.getLogger("rq.worker")

class AciAdapter(DiffSync):
    """DiffSync adapter for Cisco ACI."""

    tenant = NautobotTenant
    device_type = NautobotDeviceType
    device_role = NautobotDeviceRole
    device = NautobotDevice
    interface_template = NautobotInterfaceTemplate
    ip_address = NautobotIPAddress
    prefix = NautobotPrefix
    interface = NautobotInterface

    top_level = ["tenant", "device_type", "device_role", "interface_template", "device", "prefix", "ip_address", "interface"]

    def __init__(self, *args, job=None, sync=None, **kwargs):
        """Initialize ACI.

        Args:
            job (object, optional): Aci job. Defaults to None.
            sync (object, optional): Aci DiffSync. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = AciApi()
        self.nodes = self.conn.get_nodes()
        logging.info(f'Nodes: {self.nodes}')
        self.controllers = self.conn.get_controllers()
        logging.info(f'Controllers: {self.controllers}')
        self.nodes.update(self.controllers)
        self.devices = self.nodes
        logging.info(f'Devices: {self.devices}')
        

    def load_tenants(self):
        """Load tenants from ACI."""
        tenant_list = self.conn.get_tenants()
        logger.info(f"ACI Tenant List: {tenant_list}")
        for _tenant in tenant_list:
            if not _tenant["name"] in PLUGIN_CFG.get("ignore_tenants"):
                if PLUGIN_CFG.get("tenant_prefix"):
                    tenant_name = f"{PLUGIN_CFG.get('tenant_prefix')}:{_tenant['name']}"
                else:
                    tenant_name = _tenant['name']
                new_tenant = self.tenant(
                    name = tenant_name,
                    description = _tenant["description"],
                    comments = PLUGIN_CFG.get("comments", "")
                )
                self.add(new_tenant)

    def load_ipaddresses(self):
        """Load IPAddresses from ACI. Retrieves controller IPs, OOB Mgmt IP of leaf/spine, and Bridge Domain subnet IPs."""
        node_dict = self.conn.get_nodes()
        logger.info(f"ACI Node List: {node_dict}")
        # Leaf/Spine management IP addresses
        for node in node_dict.values():
            if node['oob_ip'] and not node['oob_ip'] == '0.0.0.0':
                new_ipaddress = self.ip_address(
                    address = f"{node['oob_ip']}/32",
                    device = node['name'],
                    status = 'Active',
                    description = f"ACI {node['role']}: {node['name']}",
                    interface = 'mgmt0'
                )
                self.add(new_ipaddress)
        controller_dict = self.conn.get_controllers()
        # Controller IP addresses
        for controller in controller_dict.values():
            if controller['oob_ip'] and not controller['oob_ip'] == '0.0.0.0':
                new_ipaddress = self.ip_address(
                    address = f"{controller['oob_ip']}/32",
                    device = controller['name'],
                    status = 'Active',
                    description = f"ACI {controller['role']}: {controller['name']}",
                    interface = 'mgmt0'
                )
                self.add(new_ipaddress)
        # Bridge domain subnets
        bd_dict = self.conn.get_bds(tenant='all')
        logger.info(f"ACI BDs: {bd_dict}")
        for bd in bd_dict:
            if bd_dict[bd].get('subnets'):
                if PLUGIN_CFG.get("tenant_prefix"):
                    tenant_name = f"{PLUGIN_CFG.get('tenant_prefix')}:{bd_dict[bd].get('tenant')}"
                else:
                    tenant_name = bd_dict[bd].get('tenant')
                for subnet in bd_dict[bd]['subnets']:
                    new_ipaddress = self.ip_address(
                        address = subnet[0],
                        status = 'Active',
                        description = f"ACI Bridge Domain: {bd}",
                        tenant = tenant_name
                    )
                    self.add(new_ipaddress)

    def load_prefixes(self):
        """Load Bridge domain subnets from ACI."""
        bd_dict = self.conn.get_bds(tenant='all')
        logger.info(f"ACI BDs: {bd_dict}")
        for bd in bd_dict:
            if bd_dict[bd].get('subnets'):
                if PLUGIN_CFG.get("tenant_prefix"):
                    tenant_name = f"{PLUGIN_CFG.get('tenant_prefix')}:{bd_dict[bd].get('tenant')}"
                else:
                    tenant_name = bd_dict[bd].get('tenant')
                for subnet in bd_dict[bd]['subnets']:
                    new_prefix= self.prefix(
                        prefix = str(IPv4Network(subnet[0], strict=False)),
                        status = 'Active',
                        description = f"ACI Bridge Domain: {bd}",
                        tenant = tenant_name,
                    )
                    self.add(new_prefix)

    def load_devicetypes(self):
        """Load device types from ACI device data."""
        device_types = {self.devices[key]["model"] for key in self.devices.keys()}
        for _devicetype in device_types:
            if f'{_devicetype}.yaml' in os.listdir('nautobot_ssot_aci/diffsync/device-types'):
                device_specs = load_yamlfile(os.path.join(os.getcwd(), 'nautobot_ssot_aci', 'diffsync', 'device-types', f"{_devicetype}.yaml"))
                u_height = device_specs["u_height"]
                model = device_specs["model"]
            else:
                u_height = 1
                model = _devicetype
            new_devicetype = self.device_type(
                model=model,
                manufacturer = PLUGIN_CFG.get("manufacturer_name"),
                part_nbr = _devicetype,
                comments = PLUGIN_CFG.get("comments", ""),
                u_height = u_height
            )
            self.add(new_devicetype)

    def load_interfacetemplates(self):
        """Load interface templates from YAML files."""
        device_types = {self.devices[key]["model"] for key in self.devices.keys()}
        for _devicetype in device_types:
            if f'{_devicetype}.yaml' in os.listdir('nautobot_ssot_aci/diffsync/device-types'):
                    device_specs = load_yamlfile(os.path.join(os.getcwd(), 'nautobot_ssot_aci', 'diffsync', 'device-types', f"{_devicetype}.yaml"))
                    logger.info(f'device_specs: {device_specs}')
                    for intf in device_specs["interfaces"]:
                        new_interfacetemplate = self.interface_template(name=intf["name"],
                        device_type=device_specs["model"],
                        type=intf["type"],
                        mgmt_only=intf.get("mgmt_only", False),
                        description=PLUGIN_CFG.get("comments","")
                        )
                        self.add(new_interfacetemplate)
            else:
                self.job.log_info(message=f'No YAML descriptor file for device type {_devicetype}, skipping interface template creation.')

    def load_interfaces(self):
        """Load interfaces from ACI."""
        for node_id in self.devices:
            interfaces = self.conn.get_interfaces(pod_id=1, node_id=node_id, state='all')
            for _interface in interfaces:
                new_interface = self.interface(
                    name = _interface.replace('eth', 'Ethernet'),
                    device = self.devices[node_id]['name'],
                    description = interfaces[_interface]['descr']
                )
                self.add(new_interface)

    def load_deviceroles(self):
        """Load device roles from ACI device data."""
        device_roles = {self.devices[key]["role"] for key in self.devices.keys()}
        for _devicerole in device_roles:
            new_devicerole = self.device_role(
                name = _devicerole,
                description = PLUGIN_CFG.get("comments", "")
            )
            self.add(new_devicerole)

    def load_devices(self):
        """Load devices from ACI device data."""
        for key in self.devices.keys():
            if f"{self.devices[key]['model']}.yaml" in os.listdir('nautobot_ssot_aci/diffsync/device-types'):
                    device_specs = load_yamlfile(os.path.join(os.getcwd(), 'nautobot_ssot_aci', 'diffsync', 'device-types', f"{self.devices[key]['model']}.yaml"))
                    model = device_specs["model"]
            else:
                model = self.devices[key]["model"]
            new_device = self.device(
                name=self.devices[key]["name"], 
                device_type = model,
                device_role = self.devices[key]["role"], 
                serial = self.devices[key]["serial"],
                comments = PLUGIN_CFG.get("comments", ""),
                node_id = int(key)
            )
            self.add(new_device)


    def load(self):
        """Method for one stop shop loading of all models."""
        self.load_tenants()
        self.load_devicetypes()
        self.load_interfacetemplates()
        self.load_deviceroles()
        self.load_devices()
        self.load_prefixes()
        self.load_ipaddresses()
        self.load_interfaces()