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
module: gandi_iface
version_added: "2.2"
short_description: create, attach, detach or delete Gandi network interfaces
description:
     - Manage Gandi network interfaces
options:
  state:
    description:
      - desired state of the resource
    required: false
    default: "created"
    choices: ["created", "deleted"]
    aliases: []
  datacenter:
    description:
     - datacenter location for servers
     required: true
     choices: ["Saint Denis", "Bissen"]
  bandwith:
     description:
       - bandwith ot the interface in bits/s (float)
       required: false
  vlan:
    description:
      - private vlan name the interface belongs to (str)
      required: false
      default: null
  ip_address:
    description:
      - CIDR IPv4|IPv6 address ot the interface on the vlan (str)
      required: false
      default: null
  ip_version:
    description:
      - ip version of the interface (str)
      required: false
      default: null

requirements: [ "libcloud" ]
author: Eric Garrigues <eric@gandi.net>
'''

EXAMPLES = '''
# Basic provisioning example.  Create a new iface on vlan mypvlan
# Luxembourg datacenter
- gandi_iface:
    vlan: mypvlan
    datacenter: "Bissen"
    ip_address: 192.168.0.1
    ip_version: 4
    bandwidth: 50000.0
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


# Load in the libcloud secrets file
try:
    import secrets
except ImportError:
    secrets = None


ARGS = getattr(secrets, 'GANDI_PARAMS', ())

if not ARGS:
    print("failed=True " +
          "msg='Missing Gandi connection in libcloud secrets file.'")
    sys.exit(1)


def unexpected_error_msg(error):
    """Create an error string based on passed in error."""
    # XXX : better error management
    return error


def _get_by_name(name, entities):
    find = [x for x in entities if x.name == name]
    return find[0] if find else None


def _get_by_id(id, entities):
    find = [x for x in entities if x.id == id]
    return find[0] if find else None


def get_datacenter(driver, name):
    """Get datacenter by name
    """
    dcs = driver.list_locations()
    return _get_by_name(name, dcs)


def get_pvlan(driver, name):
    pvlans = driver.ex_list_pvlans()
    return _get_by_name(name, pvlans)


def get_iface(driver, id):
    ifaces = driver.ex_list_ifaces()
    return _get_by_id(id, ifaces)


def get_iface_info(iface):
    """Retrieves interface information from an interace object and returns it
    as a dictionary.

    """
    return({
        'vlan': not iface.vlan is None and iface.vlan.name or None,
        'bandwidth': iface.extra.get('bandwidth'),
        'datacenter_id': iface.extra.get('datacenter_id')
    })


def create_iface(module, driver):
    """Creates a new pvlan.

    module : AnsibleModule object
    driver: authenticated libcloud driver on Gandi provider

    Returns:
        A Dictionary with information about the vlan that was created.

    """

    iface = {}

    ip_address = module.params.get('ip_address')
    ip_version = module.params.get('ip_version')
    pvlan_name = module.params.get('vlan')
    bandwidth = module.params.get('bandwidth')
    datacenter = module.params.get('datacenter')

    changed = False

    lc_location = get_datacenter(driver, datacenter)

    if not lc_location:
        module.fail_json(msg='Invalid datacenter %s' % datacenter,
                         changed=False)

    pvlan = get_pvlan(driver, pvlan_name)
    # module.fail_json(msg=pvlan, changed=False)

    if not pvlan and not ip_version:
        module.fail_json(msg='ip_version is mandatory when not a vlan',
                         changed=False)
    try:
        iface = driver.ex_create_iface(location=lc_location,
                                       ip_version=ip_version,
                                       ip_address=ip_address,
                                       vlan=pvlan,
                                       bandwitdh=bandwidth)

        changed = True
    except GandiException as e:
        module.fail_json(msg='Unexpected error attempting to create iface')

    iface_json_data = get_iface_info(iface)

    return (changed, iface_json_data)


def delete_iface(module, driver, iface_id):
    """Delete an interface.

    module: Ansible module object
    driver: authenticated Gandi connection object
    iface_id: int id of the interface

    Returns a dictionary of with operation status.

    """
    changed = False
    pvlan = None

    try:
        iface = get_iface(driver, iface_id)
    except Exception as e:
        module.fail_json(msg=unexpected_error_msg(e), changed=False)

    if iface:
        driver.ex_delete_iface(iface)
        changed = True

    return (changed, iface_id)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(choices=['created', 'deleted'],
                       default='created'),
            datacenter=dict(default='Bissen'),
            ip_version=dict(),
            ip_address=dict(),
            vlan=dict(),
            bandwidth=dict()
        )
    )

    ip_version = module.params.get('ip_version')
    ip_address = module.params.get('ip_address')
    vlan_name = module.params.get('vlan')
    bandwidth = module.params.get('bandwidth')
    state = module.params.get('state')
    dc = module.params.get('datacenter')
    changed = False

    try:
        gandi = get_driver(Provider.GANDI)(*ARGS)
        gandi.connection.user_agent_append("%s/%s" % (
            USER_AGENT_PRODUCT, USER_AGENT_VERSION))
    except Exception as e:
        module.fail_json(msg=unexpected_error_msg(e), changed=False)

    if not dc and state in ['created']:
        module.fail_json(msg='Must specify a "datacenter"', changed=False)

    json_output = {'datacenter': dc}

    if state in ['deleted']:
        json_output['state'] = 'deleted'
        (changed, iface_id) = delete_iface(module, gandi, iface_id)
        json_output['iface_id'] = iface_id

    elif state in ['created']:
        json_output['state'] = 'created'
        (changed, iface_data) = create_iface(module, gandi)

        json_output['iface_data'] = iface_data

    json_output['changed'] = changed
    print json.dumps(json_output)
    sys.exit(0)

from ansible.module_utils.basic import *
main()
