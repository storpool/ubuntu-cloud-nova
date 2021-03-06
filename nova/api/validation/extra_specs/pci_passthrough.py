# Copyright 2020 Red Hat, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Validators for ``pci_passthrough`` namespaced extra specs."""

from nova.api.validation.extra_specs import base


EXTRA_SPEC_VALIDATORS = [
    base.ExtraSpecValidator(
        name='pci_passthrough:alias',
        description=(
            'Specify the number of ``$alias`` PCI device(s) to attach to the '
            'instance. '
            'Must be of format ``$alias:$count``, where ``$alias`` '
            'corresponds to a particular PCI device class (as configured in '
            '``nova.conf``) and ``$count`` is the amount of PCI devices of '
            'type ``$alias`` to be assigned to the instance. '
            'Use commas to specify multiple values. '
            'Only supported by the libvirt virt driver.'
        ),
        value={
            'type': str,
            # one or more comma-separated '$alias:$count' values
            'pattern': r'[^:]+:\d+(?:\s*,\s*[^:]+:\d+)*',
        },
    ),
]


def register():
    return EXTRA_SPEC_VALIDATORS
