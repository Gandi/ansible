#!/usr/bin/env python

import os
import sys
import argparse

try:
    import json
except ImportError:
    import simplejson as json

try:
    from libcloud.compute.types import Provider
    from libcloud.compute.providers import get_driver
    _ = Provider.GANDI
except ImportError:
    print("failed=True " +
          "msg='libcloud with Gandi support required for inventory script'")
    sys.exit(1)


class GandiInventory(object):

    def __init__(self):

        self.inventory = self.empty_inventory()
        self.driver = get_driver(Provider.GANDI)(gandi_api_key)

        self.parse_cli_args()
        self.inventory = self.group_nodes()

        if self.args.host:
            data = self.json_format_dict(
                self.inventory['_meta']['hostvars'][self.args.host], True)

        elif self.args.list:
            data = self.json_format_dict(self.inventory, True)

        print(data)

    def loc_to_dict(self, location):
        '''Converts a location object to a dictionary'''
        return {
            'dc_id': location.id,
            'country': location.country
        }

    def node_metadata_to_dict(self, node):
        '''Converts a node object to a dictionary'''
        return {
            'node_id': node.id,
            'state': node.state,
            'public_ips': node.public_ips,
            'private_ips': node.private_ips,
            'ai_active': node.extra['ai_active'],
            'description': node.extra['description']
        }

    def vlan_to_dict(self, vlan):
        '''Converts a vlan object to a dictionary'''
        return {
            'vlan_id': vlan.id,
            'subnet': vlan.subnet,
            'gateway': vlan.gateway
        }

    def group_nodes(self):
        '''Groups nodes by farm, datacenter and private vlan'''
        groups = {}
        meta = {'hostvars': {}}

        nodes = self.driver.list_nodes()
        locations = self.driver.list_locations()
        ifaces = self.driver.ex_list_interfaces()
        vlans = self.driver.ex_list_vlans()

        for node in nodes:

            name = node.name
            farm = node.extra['farm']
            location = next(loc for loc in locations if
                int(loc.id) == node.extra['datacenter_id'])
            node_vlans = [iface.extra['vlan'] for iface in ifaces if
                ('vlan' in iface.extra) & (int(node.id) == iface.node_id)]

            meta['hostvars'][name] = self.node_metadata_to_dict(node)

            if farm in groups:
                groups[farm].append(name)
            else:
                groups[farm] = [name]

            if location.name not in groups:
                groups[location.name] = {'hosts':[], 'vars':{}}
                groups[location.name]['vars'] = self.loc_to_dict(location)
                groups[location.name]['hosts'] = [name]
            else:
                groups[location.name]['hosts'].append(name)

            for vlan in node_vlans:
                vlan_info = next(x for x in vlans if vlan == x.name)
                if vlan not in groups:
                    groups[vlan] = {'hosts':[], 'vars':{}}
                    groups[vlan]['vars'] = self.vlan_to_dict(vlan_info)
                    groups[vlan]['hosts'] = [name]
                else:
                    groups[vlan]['hosts'].append(name)

        groups['_meta'] = meta
        return groups

    def parse_cli_args(self):
        parser = argparse.ArgumentParser(description=
            'Produce an Ansible Inventory file based on Gandi')
        parser.add_argument('--list', action='store_true', help='List nodes')
        parser.add_argument('--host', action='store', help='Get info related to a node')
        self.args = parser.parse_args()

    def empty_inventory(self):
        return {'_meta': {'hostvars': {}}}

    def json_format_dict(self, data, pretty=False):
        ''' Converts a dict to a JSON object and dumps it as a formatted
        string '''

        if pretty:
            return json.dumps(data, sort_keys=False, indent=4)
        else:
            return json.dumps(data)

if __name__ == '__main__':
    GandiInventory()
