==============================
Using accelerators with Cyborg
==============================

Starting from microversion 2.82, nova supports creating servers with
accelerators provisioned with the Cyborg service, which provides lifecycle
management for accelerators.

To launch servers with accelerators, the administrator (or an user with
appropriate privileges) must do the following:

* Create a device profile in Cyborg, which specifies what accelerator
  resources need to be provisioned. (See `Cyborg device profiles API`_.)

  .. _`Cyborg device profiles API`: https://docs.openstack.org/api-ref/accelerator/v2/index.html#device-profiles

* Set the device profile name as an extra spec in a chosen flavor,
  with this syntax:

  .. code::

    accel:device_profile=$device_profile_name

  The chosen flavor may be a newly created one or an existing one.

* Use that flavor to create a server:

  .. code::

    openstack server create --flavor $myflavor --image $myimage $servername

Nova supports only specific operations for instances with accelerators.
The lists of supported and unsupported operations are as below:

* Supported operations.

  * Creation and deletion.
  * Reboots (soft and hard).
  * Pause and unpause.
  * Stop and start.
  * Take a snapshot.
  * Backup.
  * Rescue and unrescue.
  * Rebuild.
  * Evacuate.
  * Shelve and unshelve.

* Unsupported operations

  * Resize.
  * Suspend and resume.
  * Cold migration.
  * Live migration.

.. versionchanged:: 22.0.0(Victoria)

   Added support for rebuild and evacuate operations.

.. versionchanged:: 23.0.0(Wallaby)

   Added support for shelve and unshelve operations.

Some operations, such as lock and unlock, work as they are effectively
no-ops for accelerators.

Caveats
-------

.. note::

   This information is correct as of the 21.0.0 Ussuri release. Where
   improvements have been made or issues fixed, they are noted per item.

For nested resource providers:

* Creating servers with accelerators provisioned with the Cyborg service, if
  a flavor asks for resources that are provided by nested Resource Provider
  inventories (e.g. vGPU) and the user wants multi-create (i.e. say --max 2)
  then the scheduler could be returning a NoValidHosts exception even if each
  nested Resource Provider can support at least one specific instance, if the
  total wanted capacity is not supported by only one nested Resource Provider.
  (See `bug 1874664 <https://bugs.launchpad.net/nova/+bug/1874664>`_.)

  For example, creating servers with accelerators provisioned with the Cyborg
  service, if two children RPs have 4 vGPU inventories each:

  * You can ask for a device profile in the flavor with 2 vGPU with --max 2.
  * But you can't ask for a device profile in the flavor with 4 vGPU and
    --max 2.

=======================
Using SRIOV with Cyborg
=======================

Starting from Xena release, nova supports creating servers with
SRIOV provisioned with the Cyborg service.

To launch servers with accelerators, the administrator (or an user with
appropriate privileges) must do the following:

* Create a device profile in Cyborg, which specifies what accelerator
  resources need to be provisioned. (See `Cyborg device profiles API`_,
  `Cyborg SRIOV Test Report`_.)

  .. _`Cyborg device profiles API`: https://docs.openstack.org/api-ref/accelerator/v2/index.html#device-profiles
  .. _`Cyborg SRIOV Test Report`: https://wiki.openstack.org/wiki/Cyborg/TestReport/IntelNic

* create a 'accelerator-direct' vnic type port with the device-profile name
  set as cyborg device profile with this syntax:

  .. code::

    openstack port create $port_name --network $network_name --vnic-type=accelerator-direct --device-profile $device_profile_name

* create a server with that port:

  .. code::

    openstack server create --flavor $myflavor --image $myimage $servername --nic port-id=$port-ID

Nova supports only specific operations for instances with accelerators.
The lists of supported and unsupported operations are as below:

* Supported operations.

  * Creation and deletion.
  * Reboots (soft and hard).
  * Pause and unpause.
  * Stop and start.
  * Rebuild.
  * Rescue and unrescue.
  * Take a snapshot.
  * Backup.

* Unsupported operations

  * Resize.
  * Suspend and resume.
  * Cold migration.
  * Live migration.
  * Shelve and unshelve.
  * Evacuate.
  * Attach/detach a port with device profile.
