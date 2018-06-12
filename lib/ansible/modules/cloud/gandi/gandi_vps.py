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
module: gandi_vps
version_added: "2.2"
short_description: create or terminate Gandi servers
description:
     - Manage of Gandi VPS
options:
  image:
    description:
       - image string to use for the instance
    required: false
    default: "Debian 8 64 bits (HVM)"
    aliases: []
  instance_names:
    description:
       - a list of instance names to create or destroy
    required: false
    default: null
    aliases: []
  machine_type:
    description:
       - type of machine to create, default small
    required: false
    default = "Small instance"
  name:
    description:
      - identifier when working with a single instance
    required: false
    aliases: []
  state:
    description:
      - desired state of the resource
    required: false
    default: "created"
    choices: ["created", "running", "halted", "started", "deleted", "rebooted"]
    aliases: []
  datacenter:
    description:
     - datacenter location for servers
     required: true
     choices: ["FR-SD3","FR-SD5","FR-SD6", "LU-BI1"]
  user:
    description:
      - user to create at startup
      required: false
      default: null
  password:
    description:
      - user password
      required: false
      default: null
  sshkey_ids:
    description:
      - a comma-separated list of ssh key ids to deploy on instances
      required: false
      default: null
      aliases: []
  interfaces:
    description:
      - a dict of interfaces for one instance
      required: false
      default: {}
      aliases: {}
  extra_disks:
    description:
      - extra disks to attach to instances
      required: false
      default: []
  farm:
    description:
      - identifier used to group multiple instances
      required: false
      default: null

requirements: [ "libcloud" ]
authors: [Aymeric Barantal <mric@gandi.net>, Eric Garrigues  <eric@gandi.net>]
'''

EXAMPLES = '''
# Basic provisioning example.
# Create a custom Debian 8 instance in the luxembourg datacenter
- gandi_vps:
    gandi_api_key: "MY_API_KEY"
    name: myhost.fqdn
    image: "Debian 8"
    machine_type: custom
    cores: 2
    memory: 2048
    disk: 20
    extra_disks: [{'size': 10}]
    bandwidth: 102400.0
    state: running
    datacenter: LU-BI1
    sshkey_ids: [1, 2]
    interfaces: {'publics': [{'ipv4':'auto'}], 'privates': [{'vlan':'database', 'ipv4': '192.168.1.1'},{'vlan':'vlan1'}]}
    farm: "my_cluster"
  register: host_info
'''

import sys

USER_AGENT_PRODUCT = "Ansible-gandi"
USER_AGENT_VERSION = "v0.1"

try:
    from libcloud.compute.types import Provider
    from libcloud.compute.providers import get_driver
    from libcloud.compute.base import NodeSize
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


def get_pvlan(driver, name):
    pvlans = driver.ex_list_pvlans()
    return _get_by_name(name, pvlans)


def get_pvlans(driver, vlan_names=[]):
    all_pvlans = driver.ex_list_pvlans()
    pvlans = [_get_by_name(name, all_pvlans) for name in vlan_names]

    return pvlans


def get_instance_info(driver, inst):
    """Retrieves instance information from an instance object and returns it
    as a dictionary.
    """

    private_ifaces = []
    public_ifaces = []

    ifaces_count = 0

    host_cname_on = None

    for iface_id in inst.extra.get('ifaces', []):
        iface_name = 'i%s' % ifaces_count
        iface = driver.ex_get_interface(iface_id)
        vlan_name = iface.extra.get('vlan', 'public')

        iface_info = {'id': iface.id,
                      'bandwidth': iface.extra['bandwidth'],
                      'type': iface.extra['type'],
                      'vlan': vlan_name,
                      'iface_name': iface_name,
                      'ips': []}

        for ip in iface.ips:
            if int(ip.version) == 4:
                record_type = 'A'
            else:
                record_type = 'AAAA'
            iface_info['ips'].append({'id': ip.id,
                                      'ip': ip.inet,
                                      'record_type': record_type,
                                      'version': ip.version
                                      })

        if vlan_name == 'public':
            public_ifaces.append(iface_info)
        else:
            private_ifaces.append(iface_info)

        if ifaces_count == 0:
            host_cname_on = '%s.%s' % (iface_name, vlan_name)

        ifaces_count += 1

    return({
        'image': inst.image or None,
        'cores': inst.extra.get('cores'),
        'ram': inst.extra.get('memory'),
        'name': inst.name,
        'datacenter_id': inst.extra.get('datacenter_id'),
        'public_ifaces': public_ifaces,
        'private_ifaces': private_ifaces,
        'cname': host_cname_on,
        'farm': inst.extra.get('farm')
    })


def _get_by_name(name, entities):
    find = [x for x in entities if x.name == name]
    return find[0] if find else None


def get_image(driver, name, datacenter):
    """Get an image by name and datacenter location
    """
    images = driver.list_images(datacenter)
    return _get_by_name(name, images)


def get_volume(driver, name):
    """Get a disk by name and datacenter location
    """
    disks = driver.list_volumes()
    return _get_by_name(name, disks)


def get_datacenter(driver, name):
    """Get datacenter by name
    """
    dcs = driver.list_locations()
    return _get_by_name(name, dcs)


def get_size(driver, name):
    sizes = driver.list_sizes()
    return _get_by_name(name, sizes)


def get_node(driver, name):
    nodes = driver.list_nodes()
    return _get_by_name(name, nodes)

def stop_instances(module, driver, instance_names):
    """Stop instances. Attributes other than instance_names are picked
    up from 'module'

    module : AnsibleModule object
    driver: authenticated libcloud driver on Gandi provider
    instance_names: python list of instance names to create

    Returns:
        Status of the operation and stopped instances names

    """
    changed = False

    for name in instance_names:
        inst = get_node(driver, name)
        if inst:
            try:
                ope_status = driver.stop_node(inst)
                if ope_status:
                    changed = True

            except GandiException as e:
                msg = 'Unexpected error when starting instance %s' % name
                msg = msg + str(e)
                module.fail_json(msg=msg)

    return (changed, instance_names)


def start_instances(module, driver, instance_names):
    """Start instances. Attributes other than instance_names are picked
    up from 'module'

    module : AnsibleModule object
    driver: authenticated libcloud driver on Gandi provider
    instance_names: python list of instance names to create

    Returns:
        Status of the operation and started instances names

    """
    changed = False

    for name in instance_names:
        inst = get_node(driver, name)
        if inst:
            try:
                ope_status = driver.start_node(inst)
                if ope_status:
                    changed = True

            except GandiException as e:
                msg = 'Unexpected error when starting instance %s' % name
                msg = msg + str(e)
                module.fail_json(msg=msg)

    return (changed, instance_names)


def reboot_instances(module, driver, instance_names):
    """Restart instances.

    module : AnsibleModule object
    driver: authenticated libcloud driver on Gandi provider
    instance_names: python list of instance names to create

    Returns:
        Status of the operation and restarted instances names

    """
    changed = False

    for name in instance_names:
        inst = get_node(driver, name)
        if inst:
            try:
                ope_status = driver.reboot_node(inst)
                if ope_status:
                    changed = True

            except GandiException as e:
                msg = 'Unexpected error when starting instance %s' % name
                msg = msg + str(e)
                module.fail_json(msg=msg)

    return (changed, instance_names)


def create_instances(module, driver, instance_names):
    """Creates new instances. Attributes other than instance_names are picked
    up from 'module'

    module : AnsibleModule object
    driver: authenticated libcloud driver on Gandi provider
    instance_names: python list of instance names to create

    Returns:
        A list of dictionaries with instance information
        about the instances that were launched.

    """
    image = module.params.get('image')
    machine_type = module.params.get('machine_type')
    cores = module.params.get('cores')
    memory = module.params.get('memory')
    bandwidth = module.params.get('bandwidth')
    disk = module.params.get('disk')
    extra_disks = module.params.get('extra_disks')
    interfaces = module.params.get('interfaces')
    datacenter = module.params.get('datacenter')
    user = module.params.get('user')
    password = module.params.get('password')
    sshkey_ids = module.params.get('sshkey_ids')
    farm = module.params.get('farm')

    # module.fail_json(msg=interfaces, changed=False)

    new_instances = []
    changed = False

    lc_location = get_datacenter(driver, datacenter)

    if not lc_location:
        module.fail_json(msg='Invalid datacenter %s' % datacenter,
                         changed=False)

    lc_image = get_image(driver, image, lc_location)
    if not lc_image:
        lc_image = get_volume(driver, image)
        if not lc_image:
            module.fail_json(msg='No such image or volume %s on %s' %
                             (image, datacenter),
                             changed=False)

    if machine_type == "custom":

        lc_size = NodeSize(
            id=cores,
            name='%s cores instance' % id,
            ram=memory,
            disk=disk,
            bandwidth=bandwidth,
            price=0,
            driver=driver,
        )

    else:
        lc_size = get_size(driver, machine_type)

    if not lc_size:
        module.fail_json(msg='Invalid machine type %s' % machine_type,
                         changed=False)

    for name in instance_names:
        inst = get_node(driver, name)
        if not inst:
            try:
                lc_size.bandwidth = 102400
                if not sshkey_ids:
                    inst = driver.create_node(name=name,
                                              size=lc_size,
                                              image=lc_image,
                                              location=lc_location,
                                              login=user,
                                              password=password,
                                              interfaces=interfaces,
                                              farm=farm)
                else:
                    inst = driver.create_node(name=name,
                                              size=lc_size,
                                              image=lc_image,
                                              location=lc_location,
                                              keypairs=sshkey_ids,
                                              interfaces=interfaces,
                                              farm=farm)

                changed = True

            except GandiException as e:
                msg = 'Unexpected error when creating instance %s' % name
                msg = msg + str(e)
                module.fail_json(msg=msg)

        if inst:
            if changed:
                if extra_disks:
                    for disk in extra_disks:
                        disk_size = int(disk.get('size'))
                        disk_name = disk.get('name')
                        disk = driver.create_volume(disk_size,
                                                    name=disk_name,
                                                    location=lc_location)

                        disk_attached = driver.attach_volume(inst, disk)

                        if not disk_attached:
                            msg = 'Error when attaching % to %s' % (disk_name,
                                                                    inst.name)
                            msg = msg + str(e)
                            module.fail_json(msg=msg)

            inst_full = driver.ex_get_node(inst.id)
            new_instances.append(inst_full)

    instance_names = []
    instance_json_data = []

    if len(new_instances) > 0:
        if len(new_instances) > 1:
            for inst in new_instances:
                d = get_instance_info(driver,inst)
                instance_names.append(d['name'])
                instance_json_data.append(d)
        else:
            d = get_instance_info(driver,new_instances[0])
            instance_names = d['name']
            instance_json_data = d

    return (changed, instance_json_data, instance_names)


def terminate_instances(module, driver, instance_names):
    """Terminates a list of instances.

    module: Ansible module object
    driver: authenticated Gandi connection object
    instance_names: a list of instance names to terminate

    Returns a dictionary of instance names that were terminated.

    """
    changed = False
    instance_json_data = []
    for name in instance_names:
        try:
            inst = get_node(driver, name)
        except Exception as e:
            module.fail_json(msg=unexpected_error_msg(e), changed=False)
        if inst:
            inst = driver.ex_get_node(inst.id)
            d = get_instance_info(driver,inst)

            instance_json_data.append(d)

            driver.destroy_node(inst, cascade=True)
            instance_names.append(inst.name)
            changed = True
        # else:
        #     module.fail_json(msg="instance not found !", changed=False)

    if instance_json_data != []:
        if len(instance_json_data) == 1:
            terminated_instance_names = instance_names[0]
            terminated_instance_json_data = instance_json_data[0]
        else:
            terminated_instance_names = instance_names
            terminated_instance_json_data = instance_json_data
    else:
        terminated_instance_names = None
        terminated_instance_json_data = None

    return (changed, terminated_instance_json_data, terminated_instance_names)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            gandi_api_key=dict(),
            image=dict(default='Debian 8'),
            instance_names=dict(),
            machine_type=dict(default='Small instance'),
            cores=dict(),
            memory=dict(),
            bandwidth=dict(),
            disk=dict(),
            extra_disks=dict(type='list'),
            name=dict(),
            state=dict(choices=['running', 'halted', 'started',
                                'deleted', 'rebooted'],
                       default='running'),
            datacenter=dict(default='FR-SD5'),
            user=dict(),
            password=dict(),
            sshkey_ids=dict(type='list'),
            domain_name=dict(),
            vlans=dict(type='list'),
            interfaces=dict(type='dict', default={}),
            default_vlan=dict(),
            farm=dict()
        )
    )

    gandi_api_key = module.params.get('gandi_api_key')
    instance_names = module.params.get('instance_names')
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

    inames = []

    if isinstance(instance_names, list):
        inames = instance_names
    elif isinstance(instance_names, str):
        inames = [x.strip() for x in instance_names.split(',')]

    if name:
        inames.append(name)

    if not inames:
        module.fail_json(msg='Must specify a "name" or "instance_names"',
                         changed=False)
    if not dc:
        module.fail_json(msg='Must specify a "datacenter"', changed=False)

    json_output = {'datacenter': dc}

    if state in ['deleted']:
        json_output['state'] = 'deleted'
        (changed, instance_data, terminated_instance_names) = \
            terminate_instances(module, gandi, inames)
        json_output['instance_data'] = instance_data

        # based on what user specified, return the same variable, although
        # value could be different if an instance could not be destroyed
        if instance_names:
            json_output['instance_names'] = terminated_instance_names
        elif name:
            json_output['name'] = name

    elif state in ['running']:
        json_output['state'] = 'running'

        (changed, instance_data, instance_name_list) = \
            create_instances(module, gandi, inames)
        json_output['instance_data'] = instance_data

        if instance_names:
            json_output['instance_names'] = instance_name_list
        elif name:
            json_output['name'] = name

    elif state in ['halted']:
        json_output['state'] = 'halted'

        (changed, instance_name_list) = \
            stop_instances(module, gandi, inames)

        if instance_names:
            json_output['instance_names'] = instance_name_list
        elif name:
            json_output['name'] = name

    elif state in ['started']:
        json_output['state'] = 'started'

        (changed, instance_name_list) = \
            start_instances(module, gandi, inames)

        if instance_names:
            json_output['instance_names'] = instance_name_list
        elif name:
            json_output['name'] = name

    elif state in ['rebooted']:
        json_output['state'] = 'rebooted'

        (changed, instance_name_list) = \
            reboot_instances(module, gandi, inames)

        if instance_names:
            json_output['instance_names'] = instance_name_list
        elif name:
            json_output['name'] = name

    json_output['changed'] = changed
    print json.dumps(json_output)
    sys.exit(0)

from ansible.module_utils.basic import *

main()
