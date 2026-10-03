"""Server-owned gateway profiles; discovery never includes credentials."""
import os
import re


def load_profiles(demo=False):
    ids = [item.strip() for item in os.getenv('JASMIN_GATEWAYS', '').split(',') if item.strip()]
    named = bool(ids)
    ids = ids or ['default']
    if len(ids) != len(set(ids)):
        raise ValueError('JASMIN_GATEWAYS contains duplicate IDs.')
    profiles = {}
    for gid in ids:
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', gid):
            raise ValueError('Gateway IDs must use lowercase letters, numbers and underscores.')
        prefix = f'JASMIN_{gid.upper()}_' if named else ''
        settings = {}
        for service, port, username in [('ROUTER', '8988', 'radmin'), ('SMPP', '8989', 'cmadmin')]:
            for key, default in [('HOST', '127.0.0.1'), ('PORT', port), ('USERNAME', username),
                                 ('PASSWORD', ''), ('AUTHENTICATION', 'true')]:
                setting = f'{service}_{key}'
                settings[setting] = os.getenv(prefix + setting, default)
            auth = settings[f'{service}_AUTHENTICATION'].strip().lower()
            if auth not in ('true', 'false'):
                raise ValueError(f'{prefix}{service}_AUTHENTICATION must be true or false.')
            if not 1 <= int(settings[f'{service}_PORT']) <= 65535:
                raise ValueError(f'{prefix}{service}_PORT must be between 1 and 65535.')
            if not demo and auth == 'true' and not settings[f'{service}_PASSWORD']:
                raise ValueError(f'{prefix}{service}_PASSWORD is required when authentication is enabled.')
        profiles[gid] = dict(id=gid, name=os.getenv(prefix+'NAME', 'Demo gateway' if demo else gid.title()),
                             host=settings['ROUTER_HOST'], settings=settings)
    default = os.getenv('JASMIN_DEFAULT_GATEWAY', ids[0])
    if default not in profiles:
        raise ValueError('JASMIN_DEFAULT_GATEWAY must name a configured gateway.')
    return profiles, default
