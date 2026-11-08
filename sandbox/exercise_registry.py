"""Supported exercise IDs and their execution modes."""

PYTHON_EXERCISES = frozenset({'orders-cents', 'daily-revenue'})
WORKFLOW_EXERCISES = frozenset({
    'inventory', 'stock-reorder', 'inventory-brief', 'order-explainer'
})
EXERCISE_MODES = {
    **{exercise: 'python' for exercise in PYTHON_EXERCISES},
    **{exercise: 'workflow' for exercise in WORKFLOW_EXERCISES},
}
EXERCISES = frozenset(EXERCISE_MODES)
