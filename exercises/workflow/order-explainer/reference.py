"""Trusted reference for order-cost and stock-availability explanation."""


def solve(payload, available):
    required = {'sku', 'quantity', 'unit_cents'}
    if (not isinstance(payload, dict) or set(payload) != required
            or payload['sku'] not in {'apple', 'pear'}
            or type(payload['quantity']) is not int or not 0 <= payload['quantity'] <= 100
            or type(payload['unit_cents']) is not int or not 0 <= payload['unit_cents'] <= 100000
            or type(available) is not int or available < 0):
        raise ValueError('input')
    subtotal = payload['quantity'] * payload['unit_cents']
    accepted = payload['quantity'] <= available
    return {'sku': payload['sku'], 'quantity': payload['quantity'],
            'unit_cents': payload['unit_cents'], 'available': available,
            'subtotal_cents': subtotal, 'accepted': accepted,
            'explanation': f'{payload["quantity"]} x {payload["unit_cents"]} cents '
                           f'= {subtotal} cents; {available} units available.'}