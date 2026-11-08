"""Trusted reference for a concise evidence-backed inventory brief."""


def solve(payload, available):
    if (not isinstance(payload, dict) or set(payload) != {'sku', 'quantity'}
            or payload['sku'] not in {'apple', 'pear'}
            or type(payload['quantity']) is not int or not 0 <= payload['quantity'] <= 100
            or type(available) is not int or available < 0):
        raise ValueError('input')
    accepted = payload['quantity'] <= available
    return {'sku': payload['sku'], 'quantity': payload['quantity'],
            'available': available, 'accepted': accepted,
            'summary': f'{payload["sku"]}: requested {payload["quantity"]}; '
                       f'{available} available; {"sufficient" if accepted else "short"}.'}