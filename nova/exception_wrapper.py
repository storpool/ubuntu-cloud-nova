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

import functools
import inspect

from oslo_utils import excutils

import nova.conf
from nova.notifications.objects import base
from nova.notifications.objects import exception as exception_obj
from nova.objects import fields
from nova import rpc
from nova import safe_utils

CONF = nova.conf.CONF


@rpc.if_notifications_enabled
def _emit_versioned_exception_notification(context, exception, source):
    payload = exception_obj.ExceptionPayload.from_exception(exception)
    publisher = base.NotificationPublisher(host=CONF.host, source=source)
    event_type = base.EventType(
        object='compute',
        action=fields.NotificationAction.EXCEPTION,
    )
    notification = exception_obj.ExceptionNotification(
        publisher=publisher,
        event_type=event_type,
        priority=fields.NotificationPriority.ERROR,
        payload=payload,
    )
    notification.emit(context)


def _emit_legacy_exception_notification(
    context, exception, service, function_name, args,
):
    notifier = rpc.get_notifier(service)
    payload = {'exception': exception, 'args': args}
    notifier.error(context, function_name, payload)


def wrap_exception(service, binary):
    """This decorator wraps a method to catch any exceptions that may
    get thrown. It also optionally sends the exception to the notification
    system.
    """
    def inner(f):
        def wrapped(self, context, *args, **kw):
            # Don't store self or context in the payload, it now seems to
            # contain confidential information.
            try:
                return f(self, context, *args, **kw)
            except Exception as exc:
                with excutils.save_and_reraise_exception():
                    call_dict = _get_call_dict(f, self, context, *args, **kw)
                    function_name = f.__name__

                    _emit_legacy_exception_notification(
                        context, exc, service, function_name, call_dict)
                    _emit_versioned_exception_notification(
                        context, exc, binary)
        return functools.wraps(f)(wrapped)
    return inner


def _get_call_dict(function, self, context, *args, **kw):
    wrapped_func = safe_utils.get_wrapped_function(function)

    call_dict = inspect.getcallargs(wrapped_func, self,
                                    context, *args, **kw)
    # self can't be serialized and shouldn't be in the
    # payload
    call_dict.pop('self', None)
    # NOTE(gibi) remove context as well as it contains sensitive information
    # and it can also contain circular references
    call_dict.pop('context', None)
    return _cleanse_dict(call_dict)


def _cleanse_dict(original):
    """Strip all admin_password, new_pass, rescue_pass keys from a dict."""
    return {k: v for k, v in original.items() if "_pass" not in k}
