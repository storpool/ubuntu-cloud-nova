# Copyright (c) 2013 Intel, Inc.
# Copyright (c) 2013 OpenStack Foundation
# All Rights Reserved.
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

import copy
import typing as ty

from oslo_config import cfg
from oslo_log import log as logging

from nova import exception
from nova import objects
from nova.objects import fields
from nova.objects import pci_device_pool
from nova.pci import utils
from nova.pci import whitelist

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


# TODO(stephenfin): We might want to use TypedDict here. Refer to
# https://mypy.readthedocs.io/en/latest/kinds_of_types.html#typeddict for
# more information.
Pool = ty.Dict[str, ty.Any]


class PciDeviceStats(object):

    """PCI devices summary information.

    According to the PCI SR-IOV spec, a PCI physical function can have up to
    256 PCI virtual functions, thus the number of assignable PCI functions in
    a cloud can be big. The scheduler needs to know all device availability
    information in order to determine which compute hosts can support a PCI
    request. Passing individual virtual device information to the scheduler
    does not scale, so we provide summary information.

    Usually the virtual functions provided by a host PCI device have the same
    value for most properties, like vendor_id, product_id and class type.
    The PCI stats class summarizes this information for the scheduler.

    The pci stats information is maintained exclusively by compute node
    resource tracker and updated to database. The scheduler fetches the
    information and selects the compute node accordingly. If a compute
    node is selected, the resource tracker allocates the devices to the
    instance and updates the pci stats information.

    This summary information will be helpful for cloud management also.
    """

    pool_keys = ['product_id', 'vendor_id', 'numa_node', 'dev_type']

    def __init__(
        self,
        numa_topology: 'objects.NUMATopology',
        stats: 'objects.PCIDevicePoolList' = None,
        dev_filter: whitelist.Whitelist = None,
    ) -> None:
        self.numa_topology = numa_topology
        self.pools = (
            [pci_pool.to_dict() for pci_pool in stats] if stats else []
        )
        self.pools.sort(key=lambda item: len(item))
        self.dev_filter = dev_filter or whitelist.Whitelist(
            CONF.pci.passthrough_whitelist)

    def _equal_properties(
        self, dev: Pool, entry: Pool, matching_keys: ty.List[str],
    ) -> bool:
        return all(dev.get(prop) == entry.get(prop)
                   for prop in matching_keys)

    def _find_pool(self, dev_pool: Pool) -> ty.Optional[Pool]:
        """Return the first pool that matches dev."""
        for pool in self.pools:
            pool_keys = pool.copy()
            del pool_keys['count']
            del pool_keys['devices']
            if (len(pool_keys.keys()) == len(dev_pool.keys()) and
                self._equal_properties(dev_pool, pool_keys, list(dev_pool))):
                return pool

        return None

    def _create_pool_keys_from_dev(
        self, dev: 'objects.PciDevice',
    ) -> ty.Optional[Pool]:
        """Create a stats pool dict that this dev is supposed to be part of

        Note that this pool dict contains the stats pool's keys and their
        values. 'count' and 'devices' are not included.
        """
        # Don't add a device that doesn't have a matching device spec.
        # This can happen during initial sync up with the controller
        devspec = self.dev_filter.get_devspec(dev)
        if not devspec:
            return None
        tags = devspec.get_tags()
        pool = {k: getattr(dev, k) for k in self.pool_keys}
        if tags:
            pool.update(tags)
        # NOTE(gibi): parent_ifname acts like a tag during pci claim but
        # not provided as part of the whitelist spec as it is auto detected
        # by the virt driver.
        # This key is used for match InstancePciRequest backed by neutron ports
        # that has resource_request and therefore that has resource allocation
        # already in placement.
        if dev.extra_info.get('parent_ifname'):
            pool['parent_ifname'] = dev.extra_info['parent_ifname']
        return pool

    def _get_pool_with_device_type_mismatch(
        self, dev: 'objects.PciDevice',
    ) -> ty.Optional[ty.Tuple[Pool, 'objects.PciDevice']]:
        """Check for device type mismatch in the pools for a given device.

        Return (pool, device) if device type does not match or a single None
        if the device type matches.
        """
        for pool in self.pools:
            for device in pool['devices']:
                if device.address == dev.address:
                    if dev.dev_type != pool["dev_type"]:
                        return pool, device
                    return None

        return None

    def update_device(self, dev: 'objects.PciDevice') -> None:
        """Update a device to its matching pool."""
        pool_device_info = self._get_pool_with_device_type_mismatch(dev)
        if pool_device_info is None:
            return None

        pool, device = pool_device_info
        pool['devices'].remove(device)
        self._decrease_pool_count(self.pools, pool)
        self.add_device(dev)

    def add_device(self, dev: 'objects.PciDevice') -> None:
        """Add a device to its matching pool."""
        dev_pool = self._create_pool_keys_from_dev(dev)
        if dev_pool:
            pool = self._find_pool(dev_pool)
            if not pool:
                dev_pool['count'] = 0
                dev_pool['devices'] = []
                self.pools.append(dev_pool)
                self.pools.sort(key=lambda item: len(item))
                pool = dev_pool
            pool['count'] += 1
            pool['devices'].append(dev)

    @staticmethod
    def _decrease_pool_count(
        pool_list: ty.List[Pool], pool: Pool, count: int = 1,
    ) -> int:
        """Decrement pool's size by count.

        If pool becomes empty, remove pool from pool_list.
        """
        if pool['count'] > count:
            pool['count'] -= count
            count = 0
        else:
            count -= pool['count']
            pool_list.remove(pool)
        return count

    def remove_device(self, dev: 'objects.PciDevice') -> None:
        """Remove one device from the first pool that it matches."""
        dev_pool = self._create_pool_keys_from_dev(dev)
        if dev_pool:
            pool = self._find_pool(dev_pool)
            if not pool:
                raise exception.PciDevicePoolEmpty(
                    compute_node_id=dev.compute_node_id, address=dev.address)
            pool['devices'].remove(dev)
            self._decrease_pool_count(self.pools, pool)

    def get_free_devs(self) -> ty.List['objects.PciDevice']:
        free_devs: ty.List[objects.PciDevice] = []
        for pool in self.pools:
            free_devs.extend(pool['devices'])
        return free_devs

    def consume_requests(
        self,
        pci_requests: 'objects.InstancePCIRequests',
        numa_cells: ty.Optional[ty.List['objects.InstanceNUMACell']] = None,
    ) -> ty.Optional[ty.List['objects.PciDevice']]:

        alloc_devices: ty.List[objects.PciDevice] = []

        for request in pci_requests:
            count = request.count

            pools = self._filter_pools(self.pools, request, numa_cells)

            # Failed to allocate the required number of devices. Return the
            # devices already allocated during previous iterations back to
            # their pools
            if not pools:
                LOG.error("Failed to allocate PCI devices for instance. "
                          "Unassigning devices back to pools. "
                          "This should not happen, since the scheduler "
                          "should have accurate information, and allocation "
                          "during claims is controlled via a hold "
                          "on the compute node semaphore.")
                for d in range(len(alloc_devices)):
                    self.add_device(alloc_devices.pop())
                return None

            for pool in pools:
                if pool['count'] >= count:
                    num_alloc = count
                else:
                    num_alloc = pool['count']
                count -= num_alloc
                pool['count'] -= num_alloc
                for d in range(num_alloc):
                    pci_dev = pool['devices'].pop()
                    self._handle_device_dependents(pci_dev)
                    pci_dev.request_id = request.request_id
                    alloc_devices.append(pci_dev)
                if count == 0:
                    break

        return alloc_devices

    def _handle_device_dependents(self, pci_dev: 'objects.PciDevice') -> None:
        """Remove device dependents or a parent from pools.

        In case the device is a PF, all of it's dependent VFs should
        be removed from pools count, if these are present.
        When the device is a VF, or a VDPA device, it's parent PF
        pool count should be decreased, unless it is no longer in a pool.
        """
        if pci_dev.dev_type == fields.PciDeviceType.SRIOV_PF:
            vfs_list = pci_dev.child_devices
            if vfs_list:
                for vf in vfs_list:
                    self.remove_device(vf)
        elif pci_dev.dev_type in (
            fields.PciDeviceType.SRIOV_VF,
            fields.PciDeviceType.VDPA,
        ):
            try:
                parent = pci_dev.parent_device
                # Make sure not to decrease PF pool count if this parent has
                # been already removed from pools
                if parent in self.get_free_devs():
                    self.remove_device(parent)
            except exception.PciDeviceNotFound:
                return

    def _filter_pools_for_spec(
        self, pools: ty.List[Pool], request: 'objects.InstancePCIRequest',
    ) -> ty.List[Pool]:
        """Filter out pools that don't match the request's device spec.

        Exclude pools that do not match the specified ``vendor_id``,
        ``product_id`` and/or ``device_type`` field, or any of the other
        arbitrary tags such as ``physical_network``, specified in the request.

        :param pools: A list of PCI device pool dicts
        :param request: An InstancePCIRequest object describing the type,
            quantity and required NUMA affinity of device(s) we want.
        :returns: A list of pools that can be used to support the request if
            this is possible.
        """
        request_specs = request.spec
        return [
            pool for pool in pools
            if utils.pci_device_prop_match(pool, request_specs)
        ]

    def _filter_pools_for_numa_cells(
        self,
        pools: ty.List[Pool],
        request: 'objects.InstancePCIRequest',
        numa_cells: ty.Optional[ty.List['objects.InstanceNUMACell']],
    ) -> ty.List[Pool]:
        """Filter out pools with the wrong NUMA affinity, if required.

        Exclude pools that do not have *suitable* PCI NUMA affinity.
        ``numa_policy`` determines what *suitable* means, being one of
        PREFERRED (nice-to-have), LEGACY (must-have-if-available) and REQUIRED
        (must-have). We iterate through the various policies in order of
        strictness. This means that even if we only *prefer* PCI-NUMA affinity,
        we will still attempt to provide it if possible.

        :param pools: A list of PCI device pool dicts
        :param request: An InstancePCIRequest object describing the type,
            quantity and required NUMA affinity of device(s) we want.
        :param numa_cells: A list of InstanceNUMACell objects whose ``id``
            corresponds to the ``id`` of host NUMACells.
        :returns: A list of pools that can, together, provide at least
            ``requested_count`` PCI devices with the level of NUMA affinity
            required by ``numa_policy``, else all pools that can satisfy this
            policy even if it's not enough.
        """
        if not numa_cells:
            return pools

        # we default to the 'legacy' policy for...of course...legacy reasons
        requested_policy = fields.PCINUMAAffinityPolicy.LEGACY
        if 'numa_policy' in request:
            requested_policy = request.numa_policy or requested_policy

        requested_count = request.count
        numa_cell_ids = [cell.id for cell in numa_cells]

        # filter out pools which numa_node is not included in numa_cell_ids
        filtered_pools = [
            pool for pool in pools if any(utils.pci_device_prop_match(
                pool, [{'numa_node': cell}]) for cell in numa_cell_ids)]

        # we can't apply a less strict policy than the one requested, so we
        # need to return if we've demanded a NUMA affinity of REQUIRED.
        # However, NUMA affinity is a good thing. If we can get enough devices
        # with the stricter policy then we will use them.
        if requested_policy == fields.PCINUMAAffinityPolicy.REQUIRED or sum(
                pool['count'] for pool in filtered_pools) >= requested_count:
            return filtered_pools

        # the SOCKET policy is a bit of a special case. It's less strict than
        # REQUIRED (so REQUIRED will automatically fulfil SOCKET, at least
        # with our assumption of never having multiple sockets per NUMA node),
        # but not always more strict than LEGACY: a PCI device with no NUMA
        # affinity will fulfil LEGACY but not SOCKET. If we have SOCKET,
        # process it here and don't continue.
        if requested_policy == fields.PCINUMAAffinityPolicy.SOCKET:
            return self._filter_pools_for_socket_affinity(pools, numa_cells)

        # some systems don't report NUMA node info for PCI devices, in which
        # case None is reported in 'pci_device.numa_node'. The LEGACY policy
        # allows us to use these devices so we include None in the list of
        # suitable NUMA cells.
        numa_cell_ids.append(None)

        # filter out pools which numa_node is not included in numa_cell_ids
        filtered_pools = [
            pool for pool in pools if any(utils.pci_device_prop_match(
                pool, [{'numa_node': cell}]) for cell in numa_cell_ids)]

        # once again, we can't apply a less strict policy than the one
        # requested, so we need to return if we've demanded a NUMA affinity of
        # LEGACY. Similarly, we will also return if we have enough devices to
        # satisfy this somewhat strict policy.
        if requested_policy == fields.PCINUMAAffinityPolicy.LEGACY or sum(
                pool['count'] for pool in filtered_pools) >= requested_count:
            return filtered_pools

        # if we've got here, we're using the PREFERRED policy and weren't able
        # to provide anything with stricter affinity. Use whatever devices you
        # can, folks.
        return sorted(
            pools, key=lambda pool: pool.get('numa_node') not in numa_cell_ids)

    def _filter_pools_for_socket_affinity(
        self,
        pools: ty.List[Pool],
        numa_cells: ty.List['objects.InstanceNUMACell'],
    ) -> ty.List[Pool]:
        host_cells = self.numa_topology.cells
        # bail early if we don't have socket information for all host_cells.
        # This could happen if we're running on an weird older system with
        # multiple sockets per NUMA node, which is a configuration that we
        # explicitly chose not to support.
        if any(cell.socket is None for cell in host_cells):
            LOG.debug('No socket information in host NUMA cell(s).')
            return []

        # get a set of host sockets that the guest cells are in. Since guest
        # cell IDs map to host cell IDs, we can just lookup the latter's
        # socket.
        socket_ids = set()
        for guest_cell in numa_cells:
            for host_cell in host_cells:
                if guest_cell.id == host_cell.id:
                    socket_ids.add(host_cell.socket)

        # now get a set of host NUMA nodes that are in the above sockets
        allowed_numa_nodes = set()
        for host_cell in host_cells:
            if host_cell.socket in socket_ids:
                allowed_numa_nodes.add(host_cell.id)

        # filter out pools that are not in one of the correct host NUMA nodes.
        return [
            pool for pool in pools if any(
                utils.pci_device_prop_match(pool, [{'numa_node': numa_node}])
                for numa_node in allowed_numa_nodes
            )
        ]

    def _filter_pools_for_unrequested_pfs(
        self, pools: ty.List[Pool], request: 'objects.InstancePCIRequest',
    ) -> ty.List[Pool]:
        """Filter out pools with PFs, unless these are required.

        This is necessary in cases where PFs and VFs have the same product_id
        and generally useful elsewhere.

        :param pools: A list of PCI device pool dicts
        :param request: An InstancePCIRequest object describing the type,
            quantity and required NUMA affinity of device(s) we want.
        :returns: A list of pools that can be used to support the request if
            this is possible.
        """
        if all(
            spec.get('dev_type') != fields.PciDeviceType.SRIOV_PF
            for spec in request.spec
        ):
            pools = [
                pool for pool in pools
                if not pool.get('dev_type') == fields.PciDeviceType.SRIOV_PF
            ]
        return pools

    def _filter_pools_for_unrequested_vdpa_devices(
        self,
        pools: ty.List[Pool],
        request: 'objects.InstancePCIRequest',
    ) -> ty.List[Pool]:
        """Filter out pools with VDPA devices, unless these are required.

        This is necessary as vdpa devices require special handling and
        should not be allocated to generic pci device requests.

        :param pools: A list of PCI device pool dicts
        :param request: An InstancePCIRequest object describing the type,
            quantity and required NUMA affinity of device(s) we want.
        :returns: A list of pools that can be used to support the request if
            this is possible.
        """
        if all(
            spec.get('dev_type') != fields.PciDeviceType.VDPA
            for spec in request.spec
        ):
            pools = [
                pool for pool in pools
                if not pool.get('dev_type') == fields.PciDeviceType.VDPA
            ]
        return pools

    def _filter_pools(
        self,
        pools: ty.List[Pool],
        request: 'objects.InstancePCIRequest',
        numa_cells: ty.Optional[ty.List['objects.InstanceNUMACell']],
    ) -> ty.Optional[ty.List[Pool]]:
        """Determine if an individual PCI request can be met.

        Filter pools, which are collections of devices with similar traits, to
        identify those that can support the provided PCI request.

        If ``numa_cells`` is provided then NUMA locality may be taken into
        account, depending on the value of ``request.numa_policy``.

        :param pools: A list of PCI device pool dicts
        :param request: An InstancePCIRequest object describing the type,
            quantity and required NUMA affinity of device(s) we want.
        :param numa_cells: A list of InstanceNUMACell objects whose ``id``
            corresponds to the ``id`` of host NUMACell objects.
        :returns: A list of pools that can be used to support the request if
            this is possible, else None.
        """
        # NOTE(vladikr): This code may be open to race conditions.
        # Two concurrent requests may succeed when called support_requests
        # because this method does not remove related devices from the pools

        # Firstly, let's exclude all devices that don't match our spec (e.g.
        # they've got different PCI IDs or something)
        before_count = sum([pool['count'] for pool in pools])
        pools = self._filter_pools_for_spec(pools, request)
        after_count = sum([pool['count'] for pool in pools])

        if after_count < before_count:
            LOG.debug(
                'Dropped %d device(s) due to mismatched PCI attribute(s)',
                before_count - after_count
            )

        if after_count < request.count:
            LOG.debug('Not enough PCI devices left to satisfy request')
            return None

        # Next, let's exclude all devices that aren't on the correct NUMA node
        # or socket, *assuming* we have devices and care about that, as
        # determined by policy
        before_count = after_count
        pools = self._filter_pools_for_numa_cells(pools, request, numa_cells)
        after_count = sum([pool['count'] for pool in pools])

        if after_count < before_count:
            LOG.debug(
                'Dropped %d device(s) as they are on the wrong NUMA node(s)',
                before_count - after_count
            )

        if after_count < request.count:
            LOG.debug('Not enough PCI devices left to satisfy request')
            return None

        # If we're not requesting PFs then we should not use these.
        # Exclude them.
        before_count = after_count
        pools = self._filter_pools_for_unrequested_pfs(pools, request)
        after_count = sum([pool['count'] for pool in pools])

        if after_count < before_count:
            LOG.debug(
                'Dropped %d device(s) as they are PFs which we have not '
                'requested',
                before_count - after_count
            )

        if after_count < request.count:
            LOG.debug('Not enough PCI devices left to satisfy request')
            return None

        # If we're not requesting VDPA devices then we should not use these
        # either. Exclude them.
        before_count = after_count
        pools = self._filter_pools_for_unrequested_vdpa_devices(pools, request)
        after_count = sum([pool['count'] for pool in pools])

        if after_count < before_count:
            LOG.debug(
                'Dropped %d device(s) as they are VDPA devices which we have '
                'not requested',
                before_count - after_count
            )

        if after_count < request.count:
            LOG.debug('Not enough PCI devices left to satisfy request')
            return None

        return pools

    def support_requests(
        self,
        requests: ty.List['objects.InstancePCIRequest'],
        numa_cells: ty.Optional[ty.List['objects.InstanceNUMACell']] = None,
    ) -> bool:
        """Determine if the PCI requests can be met.

        Determine, based on a compute node's PCI stats, if an instance can be
        scheduled on the node. **Support does not mean real allocation**.

        If ``numa_cells`` is provided then NUMA locality may be taken into
        account, depending on the value of ``numa_policy``.

        :param requests: A list of InstancePCIRequest object describing the
            types, quantities and required NUMA affinities of devices we want.
        :type requests: nova.objects.InstancePCIRequests
        :param numa_cells: A list of InstanceNUMACell objects whose ``id``
            corresponds to the ``id`` of host NUMACells, or None.
        :returns: Whether this compute node can satisfy the given request.
        """
        # NOTE(yjiang5): this function has high possibility to fail,
        # so no exception should be triggered for performance reason.
        return all(
            self._filter_pools(self.pools, r, numa_cells) for r in requests
        )

    def _apply_request(
        self,
        pools: ty.List[Pool],
        request: 'objects.InstancePCIRequest',
        numa_cells: ty.Optional[ty.List['objects.InstanceNUMACell']] = None,
    ) -> bool:
        """Apply an individual PCI request.

        Apply a PCI request against a given set of PCI device pools, which are
        collections of devices with similar traits.

        If ``numa_cells`` is provided then NUMA locality may be taken into
        account, depending on the value of ``request.numa_policy``.

        :param pools: A list of PCI device pool dicts
        :param request: An InstancePCIRequest object describing the type,
            quantity and required NUMA affinity of device(s) we want.
        :param numa_cells: A list of InstanceNUMACell objects whose ``id``
            corresponds to the ``id`` of host NUMACell objects.
        :returns: True if the request was applied against the provided pools
            successfully, else False.
        """
        # NOTE(vladikr): This code maybe open to race conditions.
        # Two concurrent requests may succeed when called support_requests
        # because this method does not remove related devices from the pools

        filtered_pools = self._filter_pools(pools, request, numa_cells)

        if not filtered_pools:
            return False

        count = request.count
        for pool in filtered_pools:
            count = self._decrease_pool_count(pools, pool, count)
            if not count:
                break

        return True

    def apply_requests(
        self,
        requests: ty.List['objects.InstancePCIRequest'],
        numa_cells: ty.Optional[ty.List['objects.InstanceNUMACell']] = None,
    ) -> None:
        """Apply PCI requests to the PCI stats.

        This is used in multiple instance creation, when the scheduler has to
        maintain how the resources are consumed by the instances.

        If ``numa_cells`` is provided then NUMA locality may be taken into
        account, depending on the value of ``numa_policy``.

        :param requests: A list of InstancePCIRequest object describing the
            types, quantities and required NUMA affinities of devices we want.
        :type requests: nova.objects.InstancePCIRequests
        :param numa_cells: A list of InstanceNUMACell objects whose ``id``
            corresponds to the ``id`` of host NUMACells, or None.
        :raises: exception.PciDeviceRequestFailed if this compute node cannot
            satisfy the given request.
        """
        if not all(
            self._apply_request(self.pools, r, numa_cells) for r in requests
        ):
            raise exception.PciDeviceRequestFailed(requests=requests)

    def __iter__(self) -> ty.Iterator[Pool]:
        pools: ty.List[Pool] = []
        for pool in self.pools:
            pool = copy.deepcopy(pool)
            # 'devices' shouldn't be part of stats
            if 'devices' in pool:
                del pool['devices']
            pools.append(pool)
        return iter(pools)

    def clear(self) -> None:
        """Clear all the stats maintained."""
        self.pools = []

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PciDeviceStats):
            return NotImplemented
        return self.pools == other.pools

    def to_device_pools_obj(self) -> 'objects.PciDevicePoolList':
        """Return the contents of the pools as a PciDevicePoolList object."""
        stats = [x for x in self]
        return pci_device_pool.from_pci_stats(stats)
