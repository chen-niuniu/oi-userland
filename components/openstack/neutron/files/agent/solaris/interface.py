# Copyright (c) 2013, 2015, Oracle and/or its affiliates. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Girish Moodalbail, Oracle, Inc.

from oslo.config import cfg

from neutron.agent.linux import utils
from neutron.agent.solaris import net_lib


OPTS = [
    cfg.StrOpt('evs_controller', default='ssh://evsuser@localhost',
               help=_("An URI that specifies an EVS controller"))
]


class SolarisVNICDriver(object):
    """Driver used to manage Solaris EVS VNICs.

    This class provides methods to create/delete an EVS VNIC and
    plumb/unplumb ab IP interface and addresses on the EVS VNIC.
    """

    # TODO(gmoodalb): dnsmasq uses old style `ifreq', so 16 is the maximum
    # length including the NUL character. If we change it to use new style
    # `lifreq', then we will be able to extend the length to 32 characters.
    VNIC_NAME_MAXLEN = 15
    VNIC_NAME_PREFIX = 'dh'
    VNIC_NAME_SUFFIX = '_0'
    VNIC_NAME_LEN_WO_SUFFIX = VNIC_NAME_MAXLEN - \
        len(VNIC_NAME_SUFFIX)

    def __init__(self, conf):
        self.conf = conf
        # Since there is no connect_uri() yet, we need to do this ourselves
        # parse ssh://user@hostname
        suh = self.conf.evs_controller.split('://')
        if len(suh) != 2 or suh[0] != 'ssh' or not suh[1].strip():
            raise SystemExit(_("Specified evs_controller is invalid"))
        uh = suh[1].split('@')
        if len(uh) != 2 or not uh[0].strip() or not uh[1].strip():
            raise SystemExit(_("'user' and 'hostname' need to be specified "
                               "for evs_controller"))

        # set the controller property for this host
        cmd = ['/usr/sbin/evsadm', 'show-prop', '-co', 'value', '-p',
               'controller']
        stdout = utils.execute(cmd)
        if conf.evs_controller != stdout.strip():
            cmd = ['/usr/sbin/evsadm', 'set-prop', '-p',
                   'controller=%s' % (conf.evs_controller)]
            utils.execute(cmd)

    def fini_l3(self, device_name):
        ipif = net_lib.IPInterface(device_name)
        ipif.delete_ip()

    def init_l3(self, device_name, ip_cidrs):
        """Set the L3 settings for the interface using data from the port.
           ip_cidrs: list of 'X.X.X.X/YY' strings
        """
        ipif = net_lib.IPInterface(device_name)
        for ip_cidr in ip_cidrs:
            ipif.create_address(ip_cidr)

    # TODO(gmoodalb): - probably take PREFIX?? for L3
    def get_device_name(self, port):
        vnicname = (self.VNIC_NAME_PREFIX +
                    port.id)[:self.VNIC_NAME_LEN_WO_SUFFIX]
        vnicname += self.VNIC_NAME_SUFFIX
        return vnicname.replace('-', '_')

    def plug(self, tenant_id, network_id, port_id, datalink_name,
             namespace=None, prefix=None, protection=False):
        """Plug in the interface."""

        evs_vport = ('%s/%s') % (network_id, port_id)
        dl = net_lib.Datalink(datalink_name)

        # This is to handle HA when the 1st DHCP/L3 agent is down and
        # the second DHCP/L3 agent tries to connect its VNIC to EVS, we will
        # end up in "vport in use" error. So, we need to reset the vport
        # before we connect the VNIC to EVS.
        cmd = ['/usr/sbin/evsadm', 'show-vport', '-f',
               'vport=%s' % port_id, '-co', 'evs,vport,status']
        stdout = utils.execute(cmd)
        evsname, vportname, status = stdout.strip().split(':')
        if status == 'used':
            cmd = ['/usr/sbin/evsadm', 'reset-vport', '-T', tenant_id,
                   '%s/%s' % (evsname, vportname)]
            utils.execute(cmd)

        dl.connect_vnic(evs_vport, tenant_id)

        if not protection:
            cmd = ['/usr/sbin/evsadm', 'set-vportprop', '-T', tenant_id,
                   '-p', 'protection=none', evs_vport]
            utils.execute(cmd)

    def unplug(self, device_name, namespace=None, prefix=None):
        """Unplug the interface."""

        dl = net_lib.Datalink(device_name)
        dl.delete_vnic()
