"""Trusted reference for inventory reorder quantity calculations."""


def solve(payload, available):
    if (not isinstance(payload, dict) or set(payload) != {'sku', 'target_quantity'}
            or payload['sku'] not in {'apple', 'pear'}
            or type(payload['target_quantity']) is not int
            or not 0 <= payload['target_quantity'] <= 100
            or type(available) is not int or available < 0):
        raise ValueError('input')
    reorder = max(0, payload['target_quantity'] - available)
    return {'sku': payload['sku'], 'target_quantity': payload['target_quantity'],
            'available': available, 'reorder_quantity': reorder,
            'explanation': f'Reorder {reorder} units to reach {payload["target_quantity"]}.'}