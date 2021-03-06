=================================
Using ports with resource request
=================================

Starting from microversion 2.72 nova supports creating servers with neutron
ports having resource request visible as a admin-only port attribute
``resource_request``. For example a neutron port has resource request if it has
a QoS minimum bandwidth rule attached.

The :neutron-doc:`Quality of Service (QoS): Guaranteed Bandwidth <admin/config-qos-min-bw.html>`
document describes how to configure neutron to use this feature.

Resource allocation
~~~~~~~~~~~~~~~~~~~

Nova collects and combines the resource request from each port in a boot
request and sends one allocation candidate request to placement during
scheduling so placement will make sure that the resource request of the ports
are fulfilled. At the end of the scheduling nova allocates one candidate in
placement. Therefore the requested resources for each port from a single boot
request will be allocated under the server's allocation in placement.


Resource Group policy
~~~~~~~~~~~~~~~~~~~~~

Nova represents the resource request of each neutron port as a separate
:placement-doc:`Granular Resource Request group <usage/provider-tree.html#granular-resource-requests>`
when querying placement for allocation candidates. When a server create request
includes more than one port with resource requests then more than one group
will be used in the allocation candidate query. In this case placement requires
to define the ``group_policy``. Today it is only possible via the
``group_policy`` key of the :nova-doc:`flavor extra_spec <user/flavors.html>`.
The possible values are ``isolate`` and ``none``.

When the policy is set to ``isolate`` then each request group and therefore the
resource request of each neutron port will be fulfilled from separate resource
providers. In case of neutron ports with ``vnic_type=direct`` or
``vnic_type=macvtap`` this means that each port will use a virtual function
from different physical functions.

When the policy is set to ``none`` then the resource request of the neutron
ports can be fulfilled from overlapping resource providers. In case of neutron
ports with ``vnic_type=direct`` or ``vnic_type=macvtap`` this means the ports
may use virtual functions from the same physical function.

For neutron ports with ``vnic_type=normal`` the group policy defines the
collocation policy on OVS bridge level so ``group_policy=none`` is a reasonable
default value in this case.

If the ``group_policy`` is missing from the flavor then the server create
request will fail with 'No valid host was found' and a warning describing the
missing policy will be logged.


Virt driver support
~~~~~~~~~~~~~~~~~~~

Supporting neutron ports with ``vnic_type=direct`` or ``vnic_type=macvtap``
depends on the capability of the virt driver. For the supported virt drivers
see the :nova-doc:`Support matrix <user/support-matrix.html#operation_port_with_resource_request>`

If the virt driver on the compute host does not support the needed capability
then the PCI claim will fail on the host and re-schedule will be triggered. It
is suggested not to configure bandwidth inventory in the neutron agents on
these compute hosts to avoid unnecessary reschedule.


Extended resource request
~~~~~~~~~~~~~~~~~~~~~~~~~

It is expected that neutron 20.0.0 (Yoga) will implement an extended resource
request format via the the ``port-resource-request-groups`` neutron API
extension. As of nova 24.0.0 (Xena), nova already supports this extension if
every nova-compute service is upgraded to Xena version and the
:oslo.config:option:`upgrade_levels.compute` configuration does not prevent
the computes from using the latest RPC version.

The extended resource request allows a single Neutron port to request
resources in more than one request groups. This also means that using just one
port in a server create request would require a group policy to be provided
in the flavor. Today the only case when a single port generates more than one
request groups is when that port has QoS policy with both minimum bandwidth
and minimum packet rate rules. Due to the placement resource model of these
features in this case the two request groups will always be fulfilled from
separate resource providers and therefore neither the ``group_policy=none``
nor the ``group_policy=isolate`` flavor extra specs will result in any
additional restriction on the placement of the resources. In the multi port
case the Resource Group policy section above still applies.

