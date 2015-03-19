# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2015, Oracle and/or its affiliates. All rights reserved.
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

"""Generic Solaris iSCSI utilities."""

import os
import time

from cinder.brick import exception
from cinder.openstack.common.gettextutils import _
from cinder.openstack.common import log as logging
from cinder.openstack.common import processutils as putils

LOG = logging.getLogger(__name__)


class SolarisiSCSI(object):
    def __init__(self, *args, **kwargs):
        self.execute = putils.execute

    def disconnect_iscsi(self):
        """Disable the iSCSI discovery method to detach the volume
        from instance_name.
        """
        self.execute('/usr/sbin/iscsiadm', 'modify', 'discovery',
                     '--sendtargets', 'disable')

    def _get_device_path(self, connection_properties):
        """Get the device path from the target info."""
        (out, _err) = self.execute('/usr/sbin/iscsiadm', 'list',
                                   'target', '-S',
                                   connection_properties['target_iqn'])

        for line in [l.strip() for l in out.splitlines()]:
            if line.startswith("OS Device Name:"):
                dev_path = line.split()[-1]
                return dev_path
        else:
            LOG.error(_("No device is found for the target %s.") %
                      connection_properties['target_iqn'])
            raise

    def get_initiator(self):
        """Return the iSCSI initiator node name IQN"""
        out, err = self.execute('/usr/sbin/iscsiadm', 'list', 'initiator-node')

        # Sample first line of command output:
        # Initiator node name: iqn.1986-03.com.sun:01:e00000000000.4f757217
        initiator_name_line = out.splitlines()[0]
        return initiator_name_line.rsplit(' ', 1)[1]

    def _connect_to_iscsi_portal(self, connection_properties):
        # TODO(Strony): handle the CHAP authentication
        target_ip = connection_properties['target_portal'].split(":")[0]
        self.execute('/usr/sbin/iscsiadm', 'add', 'discovery-address',
                     target_ip)
        self.execute('/usr/sbin/iscsiadm', 'modify', 'discovery',
                     '--sendtargets', 'enable')
        (out, _err) = self.execute('/usr/sbin/iscsiadm', 'list',
                                   'discovery-address', '-v',
                                   target_ip)

        lines = out.splitlines()
        if not lines[0].strip().startswith('Discovery Address: ') or \
                lines[1].strip().startswith('Unable to get targets.'):
            msg = _("No iSCSI target is found.")
            LOG.error(msg)
            raise

        target_iqn = connection_properties['target_iqn']
        for line in [l.strip() for l in lines]:
            if line.startswith("Target name:") and \
                    line.split()[-1] == target_iqn:
                return
        else:
            LOG.error(_("No active session is found for the target %s.") %
                      target_iqn)
            raise

    def connect_volume(self, connection_properties, scan_tries):
        """Attach the volume to instance_name.

        connection_properties for iSCSI must include:
        target_portal - ip and optional port
        target_iqn - iSCSI Qualified Name
        target_lun - LUN id of the volume
        """
        device_info = {'type': 'block'}

        # TODO(Strony): support the iSCSI multipath on Solaris.
        self._connect_to_iscsi_portal(connection_properties)

        host_device = self._get_device_path(connection_properties)

        # check if it is a valid device path.
        for i in range(1, scan_tries):
            if os.path.exists(host_device):
                break
            else:
                time.sleep(i ** 2)
        else:
            raise exception.VolumeDeviceNotFound(device=host_device)

        device_info['path'] = host_device
        return device_info
