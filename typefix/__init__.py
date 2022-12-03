import logging
import ast

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s[%(levelname)s][%(filename)s:%(lineno)d] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
fh = logging.FileHandler('typefix.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s[%(levelname)s][%(filename)s:%(lineno)d] %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)



stmt_types = [
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Return, ast.Delete, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For,
    ast.AsyncFor, ast.While, ast.If, ast.With, ast.AsyncWith, ast.Raise, ast.Try, ast.Assert, ast.Import, ast.ImportFrom,
    ast.Global, ast.Nonlocal, ast.Expr, ast.Pass, ast.Continue, ast.Break, ast.ExceptHandler
]
if hasattr(ast, 'Match'):
    stmt_types += [ast.Match, ast.match_case]

expr_types = [
    ast.BoolOp, ast.NamedExpr, ast.BinOp, ast.UnaryOp, ast.Lambda, ast.IfExp, ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.Await, ast.Yield, ast.YieldFrom, ast.Compare, ast.Call, ast.FormattedValue, ast.JoinedStr, ast.Constant,
    ast.Attribute, ast.Subscript, ast.Starred, ast.Name, ast.List, ast.Tuple, ast.Slice, ast.arguments, ast.arg, ast.keyword, ast.withitem,
    ast.comprehension
]
if hasattr(ast, 'Macth'):
    expr_types += [
        ast.MatchValue, ast.MatchSingleton, ast.MatchSequence, ast.MatchMapping, ast.MatchClass, ast.MatchStar, ast.MatchAs, ast.MatchOr
    ]


elem_types = {
    ast.And: 'And', ast.Or: 'Or', ast.Add: 'Add', ast.Sub: 'Sub', ast.Mult: 'Mult', ast.MatMult: 'MatMult', ast.Div: 'Div', ast.Mod: 'Mod',
    ast.Pow: 'Pow', ast.LShift: 'LShift', ast.RShift: 'RShift', ast.BitOr: 'BitOr', ast.BitXor: 'BitXor', ast.BitAnd: 'BitAnd', ast.FloorDiv: 'FloorDiv',
    ast.Invert: 'Invert', ast.Not: 'Not', ast.UAdd: 'UAdd', ast.USub: 'USub', ast.Eq: 'Eq', ast.NotEq: 'NotEq', ast.Lt: 'Lt', ast.LtE: 'LtE',
    ast.Gt: 'Gt', ast.GtE: 'GtE', ast.Is: 'Is', ast.IsNot: 'IsNot', ast.In: 'In', ast.NotIn: 'NotIn'
}

op2cat = {
    'And': 'BOOL_OP', 'Or': 'BOOL_OP', 'Add': 'MATH_OP', 'Sub': 'MATH_OP', 'Mult': 'MATH_OP', 'MatMult': 'MATH_OP', 'Div': 'MATH_OP', 'Mod': 'MATH_OP',
    'Pow': 'MATH_OP', 'LShift': 'MATH_OP', 'RShift': 'MATH_OP', 'BitOr': 'MATH_OP', 'BitXor': 'MATH_OP', 'BitAnd': 'MATH_OP', 'FloorDiv': 'MATH_OP',
    'Invert': 'UNARY_OP', 'Not': 'UNARY_OP', 'UAdd': 'UNARY_OP', 'USub': 'UNARY_OP', 'Eq': 'CMP_OP', 'NotEq': 'CMP_OP', 'Lt': 'CMP_OP', 'LtE': 'CMP_OP',
    'Gt': 'CMP_OP', 'GtE': 'CMP_OP', 'Is': 'CMP_OP', 'IsNot': 'CMP_OP', 'In': 'CMP_OP', 'NotIn': 'CMP_OP'
}

stdtypes = [
    "int", "float", "complex", "bool", "list", "tuple", "range", "str", "bytes", "bytearray", "memoryview", "set", "frozenset", "dict", "dict_keys", "dict_values", "dict_items", "None"
]

builtins = [
    'abs', 'aiter', 'all', 'any', 'anext', 'ascii', 'basestring', 'bin', 'bool', 'breakpoint', 'bytearray', 'bytes', 'callable',
    'chr', 'cmp', 'classmethod', 'compile', 'complex', 'delattr', 'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'execfile',
    'file', 'filter', 'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help', 'hex', 'id', 'input',
    'int', 'isinstance', 'issubclass', 'iter', 'len', 'list', 'locals', 'long', 'map', 'max', 'memoryview', 'min', 'next',
    'object', 'oct', 'open', 'ord', 'pow', 'print', 'property', 'range', 'raw_input', 'reduce', 'reload', 'repr', 'reversed', 
    'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple', 'type', 'unichr', 'unicode',
    'vars', 'xrange', 'zip', '__import__', 'self'
]

errors = [
    "BaseException", "Exception", "ArithmeticError", "BufferError", "LookupError", "AssertionError", "AttributeError", "EOFError", "GeneratorExit", "ImportError",
    "ModuleNotFoundError", "IndexError", "KeyError", "KeyboardInterrupt", "MemoryError", "NameError", "NotImplementedError", "OSError", "OverflowError", "RecursionError",
    "ReferenceError", "RuntimeError", "StopIteration", "StopAsyncIteration", "SyntaxError", "IndentationError", "TabError", "SystemError", "SystemExit", "TypeError",
    "UnboundLocalError", "UnicodeError", "UnicodeEncodeError", "UnicodeTranslateError", "ValueError", "ZeroDivisionError", "EnvironmentError", "IOError", "WindowsError",
    "BlockingIOError", "ChildProcessError", "ConnectionError", "BrokenPipeError", "ConnectionAbortedError", "ConnectionRefusedError", "ConnectionResetError", 
    "FileExistsError", "FileNotFoundError", "InterruptedError", "IsADirectoryError", "NotADirectoryError", "PermissionError", "ProcessLookupError", "TimeoutError"
]

warnings = [
    "Warning", "DeprecationWarning", "PendingDeprecationWarning", "RuntimeWarning", "SyntaxWarning", "UserWarning", "FutureWarning", "ImportWarning", "UnicodeWarning",
    "BytesWarning", "EncodingWarning", "ResourceWarning"
]

builtins += errors + warnings