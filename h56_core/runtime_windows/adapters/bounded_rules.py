"""Three-valued, bounded expression interpreter over an actual K1 subject state."""
from ..assembly.contracts import AssemblyError

OPERATORS = {'FIELD', 'CONST', 'EQUALS', 'IN_SET', 'EXISTS', 'STRICT_INT_LE', 'ALL', 'ANY', 'NOT'}


def evaluate(expression, state, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > 4 or counter[0] > 32 or type(expression) is not dict or len(expression) != 1:
        raise AssemblyError('BOUNDED_RULE_LIMIT', 'MAPPING')
    op, operand = next(iter(expression.items()))
    if op not in OPERATORS:
        raise AssemblyError('UNREGISTERED_RULE_OPERATOR', 'MAPPING')
    if op == 'FIELD':
        if type(operand) is not str or operand not in state:
            raise AssemblyError('UNREGISTERED_STATE_FIELD', 'MAPPING')
        return state[operand]
    if op == 'CONST':
        if type(operand) not in (str, int, bool, list) or (type(operand) is list and
            (len(operand) > 16 or any(type(v) not in (str, int, bool) for v in operand))):
            raise AssemblyError('BOUNDED_LITERAL_REQUIRED', 'MAPPING')
        return operand
    arity = 1 if op in ('NOT', 'EXISTS') else 2
    if type(operand) is not list or (op not in ('ALL', 'ANY') and len(operand) != arity) or not 1 <= len(operand) <= 16:
        raise AssemblyError('RULE_ARITY', 'MAPPING')
    values = [evaluate(v, state, depth + 1, counter) for v in operand]
    if op in ('ALL', 'ANY', 'NOT'):
        if any(v is not None and type(v) is not bool for v in values):
            raise AssemblyError('BOOLEAN_RULE_OPERANDS_REQUIRED', 'MAPPING')
        if op == 'ALL':
            return False if False in values else (None if None in values else True)
        if op == 'ANY':
            return True if True in values else (None if None in values else False)
        return None if values[0] is None else not values[0]
    if any(v is None for v in values):
        return None
    if op == 'EXISTS':
        return True
    left, right = values
    if op == 'EQUALS':
        return type(left) is type(right) and left == right
    if op == 'IN_SET':
        if type(right) is not list:
            raise AssemblyError('BOUNDED_SET_REQUIRED', 'MAPPING')
        return any(type(left) is type(item) and left == item for item in right)
    if type(left) is not int or type(right) is not int:
        raise AssemblyError('STRICT_INTEGER_RULE_OPERANDS_REQUIRED', 'MAPPING')
    return left <= right
