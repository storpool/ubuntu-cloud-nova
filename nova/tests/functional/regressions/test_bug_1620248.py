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

from nova import test
from nova.tests import fixtures as nova_fixtures


class TestServerUpdate(test.TestCase):
    REQUIRES_LOCKING = True

    def setUp(self):
        super(TestServerUpdate, self).setUp()
        self.useFixture(nova_fixtures.RealPolicyFixture())
        self.useFixture(nova_fixtures.NeutronFixture(self))
        self.useFixture(nova_fixtures.GlanceFixture(self))
        # Simulate requests coming in before the instance is scheduled by
        # using a no-op for conductor build_instances
        self.useFixture(nova_fixtures.NoopConductorFixture())
        api_fixture = self.useFixture(nova_fixtures.OSAPIFixture(
            api_version='v2.1'))

        self.api = api_fixture.api

        self.useFixture(nova_fixtures.CastAsCallFixture(self))

        self.image_id = self.api.get_images()[0]['id']
        self.flavor_id = self.api.get_flavors()[0]['id']

    def test_update_name_before_scheduled(self):
        server = dict(name='server0',
                      imageRef=self.image_id,
                      flavorRef=self.flavor_id)
        server_id = self.api.post_server({'server': server})['id']
        server = {'server': {'name': 'server-renamed'}}
        self.api.api_put('/servers/%s' % server_id, server)
        server_name = self.api.get_server(server_id)['name']
        self.assertEqual('server-renamed', server_name)
