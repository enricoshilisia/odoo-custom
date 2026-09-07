# -*- coding: utf-8 -*-
"""Microsoft Graph API service.

App-only (client credentials) authentication. Tokens are cached in
ir.config_parameter and refreshed automatically shortly before expiry.

Usage from another module:

    graph = self.env['cps.graph.service']
    if graph._is_configured():
        data = graph._request('GET', '/users/someone@example.com')
"""
import logging
from datetime import timedelta

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GRAPH_ROOT = 'https://graph.microsoft.com/v1.0'
LOGIN_ROOT = 'https://login.microsoftonline.com'
DEFAULT_TIMEOUT = 30

P_TENANT = 'cps_ms_graph.tenant_id'
P_CLIENT_ID = 'cps_ms_graph.client_id'
P_CLIENT_SECRET = 'cps_ms_graph.client_secret'
P_ORGANIZER = 'cps_ms_graph.organizer_upn'
P_TOKEN = 'cps_ms_graph.access_token'
P_TOKEN_EXP = 'cps_ms_graph.access_token_expiry'

# Header required for evolvable enums such as the 'coorganizer' meeting role.
PREFER_UNKNOWN_ENUMS = 'include-unknown-enum-members'


class CpsGraphService(models.AbstractModel):
    _name = 'cps.graph.service'
    _description = 'Microsoft Graph API Service'

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @api.model
    def _get_settings(self):
        """Return the stored Graph credentials as a dict."""
        icp = self.env['ir.config_parameter'].sudo()
        return {
            'tenant_id': (icp.get_param(P_TENANT) or '').strip(),
            'client_id': (icp.get_param(P_CLIENT_ID) or '').strip(),
            'client_secret': (icp.get_param(P_CLIENT_SECRET) or '').strip(),
            'organizer_upn': (icp.get_param(P_ORGANIZER) or '').strip(),
        }

    @api.model
    def _is_configured(self):
        """True when tenant, client id and secret are all present."""
        cfg = self._get_settings()
        return bool(cfg['tenant_id'] and cfg['client_id'] and cfg['client_secret'])

    @api.model
    def _get_organizer_upn(self):
        upn = self._get_settings()['organizer_upn']
        if not upn:
            raise UserError(_(
                'No Graph organizer account is configured. '
                'Set it in Settings > CPS Graph.'
            ))
        return upn

    # ------------------------------------------------------------------
    # Token handling
    # ------------------------------------------------------------------

    @api.model
    def _fetch_token(self, tenant_id, client_id, client_secret):
        """Low-level token fetch. Returns (access_token, expires_in_seconds).

        Credentials are passed explicitly so the settings screen can test
        values that have not been saved yet.
        """
        if not (tenant_id and client_id and client_secret):
            raise UserError(_('Tenant ID, Client ID and Client Secret are all required.'))

        url = '%s/%s/oauth2/v2.0/token' % (LOGIN_ROOT, tenant_id)
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials',
        }
        try:
            resp = requests.post(url, data=payload, timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.RequestException as err:
            _logger.warning('Graph token request failed: %s', err)
            raise UserError(_('Could not reach Microsoft login endpoint: %s') % err)

        if resp.status_code != 200:
            detail = self._describe_error(resp)
            _logger.warning('Graph token rejected (%s): %s', resp.status_code, detail)
            raise UserError(_('Microsoft rejected the credentials.\n\n%s') % detail)

        body = resp.json()
        token = body.get('access_token')
        if not token:
            raise UserError(_('Microsoft returned no access token.'))
        return token, int(body.get('expires_in') or 3600)

    @api.model
    def _get_token(self, force_refresh=False):
        """Return a cached access token, fetching a new one when needed."""
        icp = self.env['ir.config_parameter'].sudo()

        if not force_refresh:
            token = icp.get_param(P_TOKEN)
            expiry = icp.get_param(P_TOKEN_EXP)
            if token and expiry:
                try:
                    expiry_dt = fields.Datetime.from_string(expiry)
                except (ValueError, TypeError):
                    expiry_dt = None
                # Refresh two minutes early to avoid edge-of-expiry failures.
                if expiry_dt and expiry_dt > fields.Datetime.now() + timedelta(seconds=120):
                    return token

        cfg = self._get_settings()
        token, expires_in = self._fetch_token(
            cfg['tenant_id'], cfg['client_id'], cfg['client_secret'])

        icp.set_param(P_TOKEN, token)
        icp.set_param(
            P_TOKEN_EXP,
            fields.Datetime.to_string(fields.Datetime.now() + timedelta(seconds=expires_in)))
        return token

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    @api.model
    def _request(self, method, path, payload=None, params=None,
                 prefer_unknown_enums=False, expected=None, _retried=False):
        """Call Graph and return the decoded JSON body (or None for 204).

        :param method: HTTP verb, e.g. 'GET', 'POST', 'PATCH'
        :param path:   path below the Graph root, e.g. '/users/a@b.com'
        :param prefer_unknown_enums: send the Prefer header needed for the
               'coorganizer' role and other evolvable enum values
        :param expected: iterable of acceptable status codes
        """
        if not self._is_configured():
            raise UserError(_(
                'Microsoft Graph is not configured. '
                'Add the tenant, client ID and secret in Settings > CPS Graph.'
            ))

        url = path if path.startswith('http') else GRAPH_ROOT + path
        headers = {
            'Authorization': 'Bearer %s' % self._get_token(),
            'Content-Type': 'application/json',
        }
        if prefer_unknown_enums:
            headers['Prefer'] = PREFER_UNKNOWN_ENUMS

        try:
            resp = requests.request(
                method, url, headers=headers, json=payload, params=params,
                timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.RequestException as err:
            _logger.warning('Graph %s %s failed: %s', method, path, err)
            raise UserError(_('Could not reach Microsoft Graph: %s') % err)

        # A stale cached token gives 401; refresh once and retry.
        if resp.status_code == 401 and not _retried:
            _logger.info('Graph returned 401, refreshing token and retrying.')
            self._get_token(force_refresh=True)
            return self._request(
                method, path, payload=payload, params=params,
                prefer_unknown_enums=prefer_unknown_enums,
                expected=expected, _retried=True)

        ok = expected or (200, 201, 202, 204)
        if resp.status_code not in ok:
            detail = self._describe_error(resp)
            _logger.warning('Graph %s %s -> %s: %s',
                            method, path, resp.status_code, detail)
            raise UserError(_(
                'Microsoft Graph request failed (%(code)s).\n\n%(detail)s'
            ) % {'code': resp.status_code, 'detail': detail})

        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    @api.model
    def _describe_error(self, resp):
        """Turn a Graph error response into something readable."""
        try:
            body = resp.json()
        except ValueError:
            return (resp.text or '')[:500]

        err = body.get('error')
        if isinstance(err, dict):
            code = err.get('code') or ''
            msg = err.get('message') or ''
            return ('%s\n%s' % (code, msg)).strip()
        if isinstance(err, str):
            desc = body.get('error_description') or ''
            return ('%s\n%s' % (err, desc)).strip()
        return str(body)[:500]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _resolve_user_id(self, upn):
        """Return the Entra object ID for a user principal name."""
        if not upn:
            return False
        data = self._request('GET', '/users/%s' % upn,
                             params={'$select': 'id,displayName,mail,userPrincipalName'})
        return data.get('id') if data else False

    @api.model
    def _test_connection(self, tenant_id=None, client_id=None,
                         client_secret=None, organizer_upn=None):
        """Validate credentials end to end. Returns a human-readable message."""
        cfg = self._get_settings()
        tenant_id = tenant_id or cfg['tenant_id']
        client_id = client_id or cfg['client_id']
        client_secret = client_secret or cfg['client_secret']
        organizer_upn = organizer_upn or cfg['organizer_upn']

        token, expires_in = self._fetch_token(tenant_id, client_id, client_secret)
        lines = [_('Token acquired (valid for %s minutes).') % (expires_in // 60)]

        if organizer_upn:
            url = '%s/users/%s' % (GRAPH_ROOT, organizer_upn)
            try:
                resp = requests.get(
                    url,
                    headers={'Authorization': 'Bearer %s' % token},
                    params={'$select': 'id,displayName,userPrincipalName'},
                    timeout=DEFAULT_TIMEOUT)
            except requests.exceptions.RequestException as err:
                raise UserError(_('Token worked but Graph was unreachable: %s') % err)

            if resp.status_code == 200:
                user = resp.json()
                lines.append(_('Organizer resolved: %(name)s (%(upn)s)') % {
                    'name': user.get('displayName') or '?',
                    'upn': user.get('userPrincipalName') or organizer_upn,
                })
            else:
                lines.append(_('Organizer lookup failed (%(code)s): %(detail)s') % {
                    'code': resp.status_code,
                    'detail': self._describe_error(resp),
                })
                lines.append(_(
                    'Check that User.Read.All application permission is granted '
                    'and admin consent has been given.'))
        else:
            lines.append(_('No organizer account set, so the lookup was skipped.'))

        return '\n'.join(lines)
