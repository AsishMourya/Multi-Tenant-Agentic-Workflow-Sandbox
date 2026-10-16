"""Example learner LangGraph program using the single scoped mock tool."""
import json
import sys
from typing import TypedDict

from guest_broker_client import lookup
from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    sku: str
    quantity: int
    available: int
    accepted: bool
    explanation: str


def inventory(state):
    return {'available': lookup(state['sku'])['available']}


def explain(state):
    accepted = state['quantity'] <= state['available']
    return {'accepted': accepted,
            'explanation': f"Requested {state['quantity']}; available {state['available']}; accepted {accepted}."}


graph = StateGraph(State)
graph.add_node('inventory', inventory)
graph.add_node('explain', explain)
graph.add_edge(START, 'inventory')
graph.add_edge('inventory', 'explain')
graph.add_edge('explain', END)
result = graph.compile().invoke(json.load(sys.stdin))
print(json.dumps({'accepted': result['accepted'], 'explanation': result['explanation']}))
