"""Trusted example only. Amounts are integer cents, never binary floats."""
def solve(orders):
    if not isinstance(orders,list) or len(orders)>1000: raise ValueError('orders must be bounded list')
    totals = {}
    for order in orders:
        if not isinstance(order,dict) or set(order) != {'sku','quantity','unit_cents'}: raise ValueError('order')
        sku,q,p = order['sku'],order['quantity'],order['unit_cents']
        if not isinstance(sku,str) or sku not in {'apple','pear'} or type(q) is not int or type(p) is not int or not 0 <= q <=100 or not 0 <= p <=100000: raise ValueError('order')
        totals[sku] = totals.get(sku,0)+q*p
    return {'by_sku':dict(sorted(totals.items())),'total_cents':sum(totals.values())}
