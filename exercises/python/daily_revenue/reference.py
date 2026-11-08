"""Trusted reference for daily revenue aggregation using integer cents."""


def solve(payload):
    if not isinstance(payload, dict) or set(payload) != {'sales'}:
        raise ValueError('payload')
    sales = payload['sales']
    if not isinstance(sales, list) or len(sales) > 1000:
        raise ValueError('sales must be a bounded list')
    by_day = {}
    for sale in sales:
        if not isinstance(sale, dict) or set(sale) != {'day', 'amount_cents'}:
            raise ValueError('sale')
        day, amount = sale['day'], sale['amount_cents']
        if (not isinstance(day, str) or len(day) != 10 or type(amount) is not int
                or not 0 <= amount <= 100000000):
            raise ValueError('sale')
        by_day[day] = by_day.get(day, 0) + amount
    return {'by_day': dict(sorted(by_day.items())),
            'total_cents': sum(by_day.values())}