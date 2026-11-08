"""Actual LangGraph reference: graph state, not arbitrary Python process persistence."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

class State(TypedDict, total=False):
    sku: str
    quantity: int
    available: int
    accepted: bool
    explanation: str


def solve(payload, available):
    if (not isinstance(payload, dict) or set(payload) != {'sku', 'quantity'}
            or payload['sku'] not in {'apple', 'pear'}
            or type(payload['quantity']) is not int or not 0 <= payload['quantity'] <= 100
            or type(available) is not int or available < 0):
        raise ValueError('input')
    accepted = payload['quantity'] <= available
    return {'sku': payload['sku'], 'quantity': payload['quantity'],
            'available': available, 'accepted': accepted,
            'explanation': f"Requested {payload['quantity']}; available {available}; accepted {accepted}."}

def build(broker_call, checkpointer=None):
    def validate(s):
        if s['sku'] not in {'apple','pear'} or type(s['quantity']) is not int or not 0 <= s['quantity'] <=100: raise ValueError('input')
        return {}
    def lookup(s):
        return {'available':broker_call(s['sku'])['available']}
    def explain(s):
        accepted=s['quantity'] <= s['available']
        return {'accepted':accepted,'explanation':f"Requested {s['quantity']}; available {s['available']}; accepted {accepted}."}
    g=StateGraph(State)
    g.add_node('validate',validate); g.add_node('lookup',lookup); g.add_node('explain',explain)
    g.add_edge(START,'validate'); g.add_edge('validate','lookup'); g.add_edge('lookup','explain'); g.add_edge('explain',END)
    return g.compile(checkpointer=checkpointer or InMemorySaver(),interrupt_after=['lookup'])
