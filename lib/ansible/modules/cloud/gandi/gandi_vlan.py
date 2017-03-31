#!/usr/bin/python
# Copyright 2017 Gandi SAS
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: gandi_vlan
version_added: "2.2"
short_description: create or terminate Gandi private vlans
description:
     - Manage of Gandi Private Vlans
options:
  name:
    description:
      - identifier of the vlan
    required: true
    aliases: []
  state:
    description:
      - desired state of the resource
    required: false
    default: "present"
    choices: ["created", "deleted"]
    aliases: []
  datacenter:
    description:
     - datacenter location for servers
     required: true
     choices: ["Saint Denis", "Bissen"]
  subnet:
    description:
      - CIDR IPv4 subnet
      required: false
      default: null
  gateway:
    description:
      - IPv4 address of the subnet gateway
      required: false
      default: null

requirements: [ "libcloud" ]
author: Eric Garrigues <eric@gandi.net>
'''

EXAMPLES = '''
# Basic provisioning example.  Create a new vlan at luxembourg
# paris datacenter
- gandi_vlan:
    name: mypvlan
    datacenter: "Bissen"
    subnet: 192.168.0.0./24
    gateway: 192.168.0.254

'''

import sys

USER_AGENT_PRODUCT = "Ansible-gandi"
USER_AGENT_VERSION = "v0.1"


try:
    from libcloud.compute.types import Provider
    from libcloud.compute.providers import get_driver
    from libcloud.common.gandi import GandiException
    _ = Provider.GANDI
except ImportError:
    print("failed=True " +
          "msg='libcloud with Gandi support required for this module'")
    sys.exit(1)


def unexpected_error_msg(error):
    """Create an error string based on passed in error."""
    # XXX : better error management
    return error


def get_pvlan_info(pvlan):
    """Retrieves private vlan information from a pvlan object and returns it
    as a dictionary.

    """

    return({
        'name': pvlan.name,
        'subnet': not pvlan.subnet is None and pvlan.subnet or None,
        'gateway': not pvlan.gateway is None and pvlan.gateway or None,
        'datacenter_id': pvlan.extra.get('datacenter_id'),
    })


def get_pvlan(driver, name):
    pvlans = driver.ex_list_pvlans()
    return _get_by_name(name, pvlans)


def get_pvlans(driver, vlan_names = []):
    all_pvlans = driver.ex_list_pvlans()
    pvlans = [_get_by_name(name, all_pvlans) for name in vlan_names]

    return pvlans


def _get_by_name(name, entities):
    find = [x for x in entities if x.name == name]
    return find[0] if find else None


def get_datacenter(driver, name):
    """Get datacenter by name
    """
    dcs = driver.list_locations()
    return _get_by_name(name, dcs)


def create_pvlan(module, driver, pvlan_name):
    """Creates a new pvlan.

    module : AnsibleModule object
    driver: authenticated libcloud driver on Gandi provider
    pvlan_name: python string of pvlan name to create

    Returns:
        A Dictionary with information about the vlan that was created.

    """
    subnet = module.params.get('subnet')
    gateway = module.params.get('gateway')
    datacenter = module.params.get('datacenter')

    changed = False

    lc_location = get_datacenter(driver, datacenter)

    if not lc_location:
        module.fail_json(msg='Invalid datacenter %s' % datacenter,
                         changed=False)

    pvlan = get_pvlan(driver, pvlan_name)

    if not pvlan:
        try:
            pvlan = driver.ex_create_pvlan(name=pvlan_name,
                                           location=lc_location,
                                           subnet=subnet,
                                           gateway=gateway)
            changed = True
        except GandiException as e:
            msg = 'Unexpected error attempting to create pvlan %s' % pvlan_name
            module.fail_json(msg=msg)

    pvlan_json_data = get_pvlan_info(pvlan)

    return (changed, pvlan_json_data, pvlan_name)


def delete_pvlan(module, driver, pvlan_name):
    """Delete a private vlan.

    module: Ansible module object
    driver: authenticated Gandi connection object
    pvlan_name: python string of pvlan name to delete

    Returns a dictionary of with operation status and pvlan name.

    """
    changed = False
    pvlan = None

    try:
        pvlan = get_pvlan(driver, pvlan_name)
    except Exception as e:
        module.fail_json(msg=unexpected_error_msg(e), changed=False)

    if pvlan:
        driver.ex_delete_pvlan(pvlan)
        changed = True

    return (changed, pvlan_name)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            gandi_api_key=dict(),
            name=dict(),
            state=dict(choices=['created', 'deleted'],
                       default='created'),
            datacenter=dict(default='Bissen'),
            subnet=dict(),
            gateway=dict()
        )
    )

    gandi_api_key = module.params.get('gandi_api_key')
    name = module.params.get('name')
    state = module.params.get('state')
    dc = module.params.get('datacenter')
    changed = False

    try:
        gandi = get_driver(Provider.GANDI)(gandi_api_key)
        gandi.connection.user_agent_append("%s/%s" % (
            USER_AGENT_PRODUCT, USER_AGENT_VERSION))
    except Exception as e:
        module.fail_json(msg=unexpected_error_msg(e), changed=False)

    if not name:
        module.fail_json(msg='Must specify a "name"', changed=False)
    if not dc and state in ['created']:
        module.fail_json(msg='Must specify a "datacenter"', changed=False)

    json_output = {'datacenter': dc}

    if state in ['deleted']:
        json_output['state'] = 'deleted'
        (changed, pvlan_deteted_name) = delete_pvlan(module, gandi, name)
        json_output['name'] = name

    elif state in ['created']:
        json_output['state'] = 'created'
        (changed, pvlan_data, name) = create_pvlan(module, gandi, name)

        json_output['pvlan_data'] = pvlan_data
        json_output['name'] = name

    json_output['changed'] = changed
    print json.dumps(json_output)
    sys.exit(0)

from ansible.module_utils.basic import *
main()
