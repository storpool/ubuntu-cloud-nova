Understanding Nova Policies
===========================

.. warning::

   JSON formatted policy file is deprecated since Nova 22.0.0(Victoria).
   Use YAML formatted file. Use `oslopolicy-convert-json-to-yaml`__ tool
   to convert the existing JSON to YAML formatted policy file in backward
   compatible way.

.. __: https://docs.openstack.org/oslo.policy/latest/cli/oslopolicy-convert-json-to-yaml.html

Nova supports a rich policy system that has evolved significantly over its
lifetime. Initially, this took the form of a large, mostly hand-written
``policy.yaml`` file but, starting in the Newton (14.0.0) release, policy
defaults have been defined in the codebase, requiring the ``policy.yaml``
file only to override these defaults.

In the Ussuri (21.0.0) release, further work was undertaken to address some
issues that had been identified:

#. No global vs project admin. The ``admin_only`` role is used for the global
   admin that is able to make almost any change to Nova, and see all details
   of the Nova system. The rule passes for any user with an admin role, it
   doesn’t matter which project is used.

#. No read-only roles. Since several APIs tend to share a single policy rule
   for read and write actions, they did not provide the granularity necessary
   for read-only access roles.

#. The ``admin_or_owner`` role did not work as expected. For most APIs with
   ``admin_or_owner``, the project authentication happened in a separate
   component than API in Nova that did not honor changes to policy. As a
   result, policy could not override hard-coded in-project checks.

Keystone comes with ``admin``, ``member`` and ``reader`` roles by default.
Please refer to :keystone-doc:`this document </admin/service-api-protection.html>`
for more information about these new defaults. In addition, keystone supports
a new "system scope" concept that makes it easier to protect deployment level
resources from project or system level resources. Please refer to
:keystone-doc:`this document </admin/tokens-overview.html#authorization-scopes>`
and `system scope specification <https://specs.openstack.org/openstack/keystone-specs/specs/keystone/queens/system-scope.html>`_ to understand the scope concept.

In the Nova 25.0.0 (Yoga) release, Nova policies implemented
the scope concept and default roles provided by keystone (admin, member,
and reader). Using common roles from keystone reduces the likelihood of
similar, but different, roles implemented across projects or deployments
(e.g., a role called ``observer`` versus ``reader`` versus ``auditor``).
With the help of the new defaults it is easier to understand who can do
what across projects, reduces divergence, and increases interoperability.

The below sections explain how these new defaults in the Nova can solve the
first two issues mentioned above and extend more functionality to end users
in a safe and secure way.

More information is provided in the `nova specification <https://specs.openstack.org/openstack/nova-specs/specs/ussuri/approved/policy-defaults-refresh.html>`_.

Scope
-----

OpenStack Keystone supports different scopes in tokens.
These are described :keystone-doc:`here </admin/tokens-overview.html#authorization-scopes>`.
Token scopes represent the layer of authorization. Policy ``scope_types``
represent the layer of authorization required to access an API.

.. note::

     The ``scope_type`` of each policy is hardcoded and is not
     overridable via the policy file.

Nova policies have implemented the scope concept by defining the ``scope_type``
in policies. To know each policy's ``scope_type``, please refer to the
:doc:`Policy Reference </configuration/policy>` and look for ``Scope Types`` or
``Intended scope(s)`` in :doc:`Policy Sample File </configuration/sample-policy>`
as shown in below examples.

.. rubric:: ``system`` scope

Policies with a ``scope_type`` of ``system`` means a user with a
``system-scoped`` token has permission to access the resource. This can be
seen as a global role. All the system-level operation's policies
have defaulted to ``scope_type`` of ``['system']``.

For example, consider the ``GET /os-hypervisors`` API.

.. code::

    # List all hypervisors.
    # GET  /os-hypervisors
    # Intended scope(s): system
    #"os_compute_api:os-hypervisors:list": "rule:system_reader_api"

.. rubric:: ``project`` scope

Policies with a ``scope_type`` of ``project`` means a user with a
``project-scoped`` token has permission to access the resource. Project-level
only operation's policies are defaulted to ``scope_type`` of ``['project']``.

For example, consider the ``POST /os-server-groups`` API.

.. code::

    # Create a new server group
    # POST  /os-server-groups
    # Intended scope(s): project
    #"os_compute_api:os-server-groups:create": "rule:project_member_api"

.. rubric:: ``system and project`` scope

Policies with a ``scope_type`` of ``system and project`` means a user with a
``system-scoped`` or ``project-scoped`` token has permission to access the
resource. All the system and project level operation's policies have defaulted
to ``scope_type`` of ``['system', 'project']``.

For example, consider the ``GET /flavors/{flavor_id}/os-extra_specs/{flavor_extra_spec_key}``
API.

.. code::

    # Show an extra spec for a flavor
    # GET /flavors/{flavor_id}/os-extra_specs/{flavor_extra_spec_key}
    # Intended scope(s): system, project
    #"os_compute_api:os-flavor-extra-specs:show": "rule:project_reader_or_admin"

These scope types provide a way to differentiate between system-level and
project-level access roles. You can control the information with scope of the
users. This means you can control that none of the project level role can get
the hypervisor information.

Policy scope is disabled by default to allow operators to migrate from
the old policy enforcement system in a graceful way. This can be
enabled by configuring the :oslo.config:option:`oslo_policy.enforce_scope`
option to ``True``.

.. note::

  [oslo_policy]
  enforce_scope=True


Roles
-----

You can refer to :keystone-doc:`this </admin/service-api-protection.html>`
document to know about all available defaults from Keystone.

Along with the ``scope_type`` feature, Nova policy defines new
defaults for each policy.

.. rubric:: ``reader``

This provides read-only access to the resources within the ``system`` or
``project``. Nova policies are defaulted to below rules:

.. code::

   system_reader_api
      Default
         role:reader and system_scope:all

   system_or_project_reader
      Default
         (rule:system_reader_api) or (role:reader and project_id:%(project_id)s)

.. rubric:: ``member``

This role is to perform the project level write operation with combination
to the system admin. Nova policies are defaulted to below rules:

.. code::

   project_member_api
      Default
         role:member and project_id:%(project_id)s

   system_admin_or_owner
      Default
         (role:admin and system_scope:all) or (role:member and project_id:%(project_id)s)

.. rubric:: ``admin``

This role is to perform the admin level write operation at system as well
as at project-level operations. Nova policies are defaulted to below rules:

.. code::

   system_admin_api
      Default
         role:admin and system_scope:all

   project_admin_api
      Default
         role:admin and project_id:%(project_id)s

   system_admin_or_owner
      Default
         (role:admin and system_scope:all) or (role:member and project_id:%(project_id)s)

With these new defaults, you can solve the problem of:

#. Providing the read-only access to the user. Polices are made more granular
   and defaulted to reader rules. For exmaple: If you need to let someone audit
   your deployment for security purposes.

#. Customize the policy in better way. For example, you will be able
   to provide access to project level user to perform live migration for their
   server or any other project with their token.

Nova supported scope & Roles
-----------------------------

Nova supports the below combination of scopes and roles where roles can be
overridden in the policy.yaml file but scope is not override-able.

#. ADMIN: ``admin`` role on ``system`` scope. This is System Administrator to
   perform the system level resource operations. Example: enable/disable compute
   services.

#. PROJECT_ADMIN: ``admin`` role on ``project`` scope. This is used to perform
   admin level operation within project. For example: Live migrate server.

   .. note::

      PROJECT_ADMIN has the limitation for the below policies

      * ``os_compute_api:servers:create:forced_host``
      * ``os_compute_api:servers:compute:servers:create:requested_destination``

      To create a server on specific host via force host or requested
      destination, you need to pass the hostname in ``POST /servers``
      API request but there is no way for PROJECT_ADMIN to get the hostname
      via API. This limitation will be addressed in a future release.


#. PROJECT_MEMBER: ``member`` role on ``project`` scope. This is used to perform
   resource owner level operation within project. For example: Pause a server.


#. PROJECT_READER: ``reader`` role on ``project`` scope. This is used to perform
   read-only operation within project. For example: Get server.


#. PROJECT_READER_OR_ADMIN: ``admin`` role on ``system`` scope
   or ``reader`` role on ``project`` scope. Such policy rules are scoped
   as both ``system`` as well as ``project``. Example: to allow system
   admin and project reader to list flavor extra specs.

   .. note:: As of now, only ``system`` and ``project`` scopes are supported in Nova.

Backward Compatibility
----------------------

Backward compatibility with versions prior to 21.0.0 (Ussuri) is maintained by
supporting the old defaults and disabling the ``scope_type`` feature by default.
This means the old defaults and deployments that use them will keep working
as-is. However, we encourage every deployment to switch to new policy.
Scope checks are disabled by default and will be enabled by default starting
Nova 26.0.0 (OpenStack Zed release) and the old defaults will be removed
starting in the Nova 27.0.0 release.

To implement the new default reader roles, some policies needed to become
granular. They have been renamed, with the old names still supported for
backwards compatibility.

Migration Plan
--------------

To have a graceful migration, Nova provides two flags to switch to the new
policy completely. You do not need to overwrite the policy file to adopt the
new policy defaults.

Here is step wise guide for migration:

#. Create scoped token:

   You need to create the new token with scope knowledge via below CLI:

   - :keystone-doc:`Create System Scoped Token </admin/tokens-overview.html#operation_create_system_token>`.
   - :keystone-doc:`Create Project Scoped Token </admin/tokens-overview.html#operation_create_project_scoped_token>`.

#. Create new default roles in keystone if not done:

   If you do not have new defaults in Keystone then you can create and re-run
   the :keystone-doc:`Keystone Bootstrap </admin/bootstrap.html>`. Keystone
   added this support in 14.0.0 (Rocky) release.

#. Enable Scope Checks

   The :oslo.config:option:`oslo_policy.enforce_scope` flag is to enable the
   ``scope_type`` features. The scope of the token used in the request is
   always compared to the ``scope_type`` of the policy. If the scopes do not
   match, one of two things can happen. If :oslo.config:option:`oslo_policy.enforce_scope`
   is True, the request will be rejected. If  :oslo.config:option:`oslo_policy.enforce_scope`
   is False, an warning will be logged, but the request will be accepted
   (assuming the rest of the policy passes). The default value of this flag
   is False.

   .. note:: Before you enable this flag, you need to audit your users and make
             sure everyone who needs system-level access has a system role
             assignment in keystone.

#. Enable new defaults

   The :oslo.config:option:`oslo_policy.enforce_new_defaults` flag switches
   the policy to new defaults-only. This flag controls whether or not to use
   old deprecated defaults when evaluating policies. If True, the old
   deprecated defaults are not evaluated. This means if any existing
   token is allowed for old defaults but is disallowed for new defaults,
   it will be rejected. The default value of this flag is False.

   .. note:: Before you enable this flag, you need to educate users about the
             different roles they need to use to continue using Nova APIs.


#. Check for deprecated policies

   A few policies were made more granular to implement the reader roles. New
   policy names are available to use. If old policy names which are renamed
   are overwritten in policy file, then warning will be logged. Please migrate
   those policies to new policy names.

Below table show how legacy rules are mapped to new rules:

+--------------------+----------------------------------+-----------------+-------------------+
| Legacy Rules       |    New Rules                     |                 |                   |
+====================+==================================+=================+===================+
|                    |                                  | *Roles*         | *Scope*           |
|                    +----------------------------------+-----------------+-------------------+
|                    | ADMIN                            | admin           | system            |
| Project Admin      +----------------------------------+-----------------+                   |
| Role               | PROJECT_ADMIN                    | admin           | project           |
|                    |                                  |                 |                   |
+--------------------+----------------------------------+-----------------+-------------------+
|                    | PROJECT_ADMIN                    | admin           | project           |
|                    +----------------------------------+-----------------+                   |
|                    | PROJECT_MEMBER                   | member          |                   |
|                    +----------------------------------+-----------------+                   |
| Project admin or   | PROJECT_READER                   | reader          |                   |
| owner role         +----------------------------------+-----------------+-------------------+
|                    | PROJECT_READER_OR_ADMIN          | admin on system | system            |
|                    |                                  | or reader on    | OR                |
|                    |                                  | project         | project           |
+--------------------+----------------------------------+-----------------+-------------------+

We expect all deployments to migrate to new policy by 27.0.0 release so that
we can remove the support of old policies.
