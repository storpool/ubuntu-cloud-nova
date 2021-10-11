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

from nova import test
from nova.tests import fixtures as nova_fixtures
from nova.tests.functional import fixtures as func_fixtures
from nova.tests.functional import integrated_helpers


class RegressionTest1835822(
    test.TestCase, integrated_helpers.InstanceHelperMixin,
):

    def setUp(self):
        super(RegressionTest1835822, self).setUp()
        # Use the standard fixtures.
        self.useFixture(nova_fixtures.RealPolicyFixture())
        self.useFixture(nova_fixtures.GlanceFixture(self))
        self.useFixture(nova_fixtures.NeutronFixture(self))
        self.useFixture(func_fixtures.PlacementFixture())

        self.api = self.useFixture(nova_fixtures.OSAPIFixture(
            api_version='v2.1')).api
        self.start_service('conductor')
        self.start_service('scheduler')
        self.start_service('compute')

        images = self.api.get_images()
        self.image_ref_0 = images[0]['id']
        self.image_ref_1 = images[1]['id']

        self.notifier = self.useFixture(
            nova_fixtures.NotificationFixture(self))

    def _create_active_server(self, server_args=None):
        basic_server = {
            'flavorRef': 1,
            'name': 'RegressionTest1835822',
            'networks': [{
                'uuid': nova_fixtures.NeutronFixture.network_1['id']
            }],
            'imageRef': self.image_ref_0
        }
        if server_args:
            basic_server.update(server_args)
        server = self.api.post_server({'server': basic_server})
        return self._wait_for_state_change(server, 'ACTIVE')

    def test_create_server_with_config_drive(self):
        """Verify that we can create a server with a config drive.
        """
        active_server = self._create_active_server(
            server_args={'config_drive': True})
        self.assertTrue(active_server['config_drive'])

    def test_create_server_without_config_drive(self):
        """Verify that we can create a server without
        a config drive.
        """
        self.flags(force_config_drive=False)
        active_server = self._create_active_server()
        self.assertEqual('', active_server['config_drive'])

    def test_create_server_with_forced_config_drive(self):
        """Verify that we can create a server with a forced
        config drive.
        """
        self.flags(force_config_drive=True)
        active_server = self._create_active_server()
        self.assertTrue(active_server['config_drive'])

    def test_create_server_with_forced_config_drive_reboot(self):
        """Verify that we can create a server with a forced
        config drive and it survives reboot.
        """
        self.flags(force_config_drive=True)
        active_server = self._create_active_server()
        self.assertTrue(active_server['config_drive'])
        active_server = self._reboot_server(active_server, hard=True)
        self.assertTrue(active_server['config_drive'])

    def test_create_server_config_drive_reboot_after_conf_change(self):
        """Verify that we can create a server with or without a forced
        config drive it does not change across a reboot.
        """
        # NOTE(sean-k-mooney): we do not need to restart the compute
        # service because of the way self.flags overrides the config
        # values.
        self.flags(force_config_drive=True)
        with_config_drive = self._create_active_server()
        self.assertTrue(with_config_drive['config_drive'])
        self.flags(force_config_drive=False)
        without_config_drive = self._create_active_server()
        self.assertEqual('', without_config_drive['config_drive'])

        # this server was created with force_config_drive=true
        # so assert now that force_config_drive is false it does
        # not override the value it was booted with.
        with_config_drive = self._reboot_server(with_config_drive, hard=True)
        self.assertTrue(with_config_drive['config_drive'])

        # this server was booted with force_config_drive=False so
        # assert that it's config drive setting is not overridden
        self.flags(force_config_drive=True)
        without_config_drive = self._reboot_server(
            without_config_drive, hard=True)
        self.assertEqual('', without_config_drive['config_drive'])

    def test_create_server_config_drive_rebuild_after_conf_change(self):
        """Verify that we can create a server with or without a forced
        config drive it does not change across a rebuild.
        """
        self.flags(force_config_drive=True)
        with_config_drive = self._create_active_server()
        self.assertTrue(with_config_drive['config_drive'])
        self.flags(force_config_drive=False)
        without_config_drive = self._create_active_server()
        self.assertEqual('', without_config_drive['config_drive'])

        # this server was created with force_config_drive=true
        # so assert now that force_config_drive is false it does
        # not override the value it was booted with.
        with_config_drive = self._rebuild_server(
            with_config_drive, self.image_ref_1)
        self.assertTrue(with_config_drive['config_drive'])

        # this server was booted with force_config_drive=False so
        # assert that it's config drive setting is not overridden
        self.flags(force_config_drive=True)
        without_config_drive = self._rebuild_server(
            without_config_drive, self.image_ref_1)
        self.assertEqual('', without_config_drive['config_drive'])

    def test_create_server_config_drive_shelve_unshelve_conf_change(self):
        """Verify that we can create a server with or without a forced
        config drive it does not change across a shelve and unshelve.
        """
        self.flags(force_config_drive=True)
        with_config_drive = self._create_active_server()
        self.assertTrue(with_config_drive['config_drive'])
        self.flags(force_config_drive=False)
        without_config_drive = self._create_active_server()
        self.assertEqual('', without_config_drive['config_drive'])

        # this server was created with force_config_drive=true
        # so assert now that force_config_drive is false it does
        # not override the value it was booted with.
        with_config_drive = self._shelve_server(with_config_drive)
        with_config_drive = self._unshelve_server(with_config_drive)
        self.assertTrue(with_config_drive['config_drive'])

        # this server was booted with force_config_drive=False so
        # assert that it's config drive setting is not overridden
        self.flags(force_config_drive=True)
        without_config_drive = self._shelve_server(without_config_drive)
        without_config_drive = self._unshelve_server(without_config_drive)
        self.assertEqual('', without_config_drive['config_drive'])
