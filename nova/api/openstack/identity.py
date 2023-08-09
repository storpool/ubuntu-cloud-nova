# Copyright 2017 IBM
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from keystoneauth1 import exceptions as kse
from oslo_log import log as logging
import webob

from nova.i18n import _
from nova import utils


LOG = logging.getLogger(__name__)


def verify_project_id(context, project_id):
    """verify that a project_id exists.

    This attempts to verify that a project id exists. If it does not,
    an HTTPBadRequest is emitted. Also HTTPBadRequest is emitted
    if Keystone identity service version 3.0 is not found.

    """
    adap = utils.get_ksa_adapter(
        'identity', ksa_auth=context.get_auth_plugin(),
        min_version=(3, 0), max_version=(3, 'latest'))

    try:
        resp = adap.get('/projects/%s' % project_id)
    except kse.EndpointNotFound:
        LOG.error(
            "Keystone identity service version 3.0 was not found. This "
            "might be caused by Nova misconfiguration or Keystone "
            "problems.")
        msg = _("Nova was unable to find Keystone service endpoint.")
        # TODO(astupnik). It may be reasonable to switch to HTTP 503
        # (HTTP Service Unavailable) instead of HTTP Bad Request here.
        # If proper Keystone servie is inaccessible, then technially
        # this is a server side error and not an error in Nova.
        raise webob.exc.HTTPBadRequest(explanation=msg)
    except kse.ClientException:
        # something is wrong, like there isn't a keystone v3 endpoint,
        # or nova isn't configured for the interface to talk to it;
        # we'll take the pass and default to everything being ok.
        LOG.info("Unable to contact keystone to verify project_id")
        return True

    if resp:
        # All is good with this 20x status
        return True
    elif resp.status_code == 404:
        # we got access, and we know this project is not there
        msg = _("Project ID %s is not a valid project.") % project_id
        raise webob.exc.HTTPBadRequest(explanation=msg)
    elif resp.status_code == 403:
        # we don't have enough permission to verify this, so default
        # to "it's ok".
        LOG.info(
            "Insufficient permissions for user %(user)s to verify "
            "existence of project_id %(pid)s",
            {"user": context.user_id, "pid": project_id})
        return True
    else:
        LOG.warning(
            "Unexpected response from keystone trying to "
            "verify project_id %(pid)s - resp: %(code)s %(content)s",
            {"pid": project_id,
             "code": resp.status_code,
             "content": resp.content})
        # realize we did something wrong, but move on with a warning
        return True
