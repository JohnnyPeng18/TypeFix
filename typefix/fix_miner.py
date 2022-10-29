import json
import os
import ast
import re
import copy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger



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





class ChangeNode(object):
    def __init__(self, node, lineno, end_lineno, change_lines, raw_change_lines):
        self.node = node
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.change_lines = change_lines
        self.raw_change_lines = raw_change_lines
        self.stmt_children = []
        self.expr_children = []
        self.field_children = {}
        self.parent = None
        self.parent_relation = 'unknown'
        self.set_type()
        self.status = []
        self.changed_fields = []
        self.check_change()

    def check_change(self):
        for i in range(self.lineno, self.end_lineno + 1):
            if i not in self.raw_change_lines:
                self.totally_changed = False
                return None
        
        self.totally_changed = True

    def set_parent(self, node):
        self.parent = node
        for name, value in ast.iter_fields(node.node):
            if isinstance(value, list) and self.node in value:
                self.parent_relation = name
            elif value == self.node:
                self.parent_relation = name


    def set_type(self):
        if type(self.node) in stmt_types:
            self.type = 'stmt'
        else:
            self.type = 'expr'
    
    def add_children(self, node):
        if node.type == 'stmt':
            self.stmt_children.append(node)
        else:
            self.expr_children.append(node)

    def add_field_children(self, name, value):
        if name in self.field_children:
            self.field_children[name] = [self.field_children[name]]
            self.field_children[name].append(value)
        else:
            self.field_children[name] = value
        '''
        if name not in self.field_children:
            self.field_children[name] = []
        self.field_children[name].append(value)
        '''
    
    def set_status(self, status):
        if status not in self.status:
            self.status.append(status)

    def set_status_for_childrens(self, status):
        for s in self.stmt_children:
            s.set_status(status)
            s.set_status_for_childrens(status)
        
        for e in self.expr_children:
            e.set_status(status)
            e.set_status_for_childrens(status)
        
    def set_status_for_parent(self, status):
        if self.parent == None or ('_Parent' in status and status.replace('_Parent', '') in self.parent.status):
            pass
        else:
            self.parent.set_status(status)
        if self.parent:
            self.parent.set_status_for_parent(status)

    def has_stmt_children(self, node):
        nodes = self.stmt_children
        while(len(nodes) != 0):
            n = nodes[0]
            nodes = nodes[1:]
            if n == node:
                return True
            else:
                nodes += n.stmt_children
        
        return False

    def has_parent(self, node):
        p = self.parent
        while p:
            if p == node:
                return True
            else:
                p = p.parent
        
        return False

    def get_all_stmt_children(self):
        nodes = self.stmt_children
        children = []
        for n in nodes:
            children += n.get_all_stmt_children()
        
        return nodes + children

    def resolve_name(self):
        field = ''
        for n in self.field_children:
            field += ' {}:{}'.format(n, str(repr(self.field_children[n]) if isinstance(self.field_children[n], str) else self.field_children[n]))

        if not self.totally_changed:
            name = '{}-({},{}) | {}'.format(str(type(self.node).__name__), self.lineno, self.end_lineno, self.change_lines)
        else:
            name = '{}-({},{})'.format(str(type(self.node).__name__), self.lineno, self.end_lineno)
        if len(field) > 0:
            name += f'\n{field}'
        return name

    @staticmethod
    def compare(a, b):
        if type(a) == type(b):
            if isinstance(a, list):
                if len(a) != len(b):
                    return False
                for i in a:
                    found = False
                    for j in b:
                        if ChangeNode.compare(i, j):
                            found = True
                            break
                    if not found:
                        return False
            if isinstance(a, ChangeNode):
                if not ChangeNode.compare(a.node, b.node):
                    return False
                if not ChangeNode.compare(a.stmt_children, b.stmt_children):
                    return False
                if not ChangeNode.compare(a.expr_children, b.expr_children):
                    return False
                if len(a.field_children) != len(b.field_children):
                    return False
                for i in a.field_children:
                    if i not in b.field_children or b.field_children[i] != a.field_children[i]:
                        return False
                return True
            elif isinstance(a, ast.AST):
                if ast.unparse(a) == ast.unparse(b):
                    return True
                else:
                    return False
        else:
            return False


        



class ChangeTree(object):
    def __init__(self, root, before, change_lines, raw_change_lines):
        self.root = root
        self.change_lines = change_lines
        self.raw_change_lines = raw_change_lines
        self.uppest_totally_changed_stmts = []
        self.deepest_changed_stmts = []
        self.deepest_partially_changed_stmts = []
        self.before = before
    
    def get_loc(self, node):
        min_lineno = 99999999999
        max_lineno = -1
        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
            return node.lineno, node.end_lineno
        
        nodes = [node]
        while(len(nodes) != 0):
            n = nodes[0]
            nodes = nodes[1:]
            if hasattr(n, 'lineno') and n.lineno < min_lineno:
                min_lineno = n.lineno
            if hasattr(n, 'end_lineno') and n.end_lineno > max_lineno:
                max_lineno = n.end_lineno
            for c in ast.iter_child_nodes(n):
                nodes.append(c)
        
        if min_lineno == 99999999999 or max_lineno == -1:
            return -1, -1
        else:
            return min_lineno, max_lineno
        
                

    def build(self):
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            for n in ast.iter_child_nodes(node.node):
                lines = []
                lineno, end_lineno = self.get_loc(n)
                for l in self.change_lines:
                    if l in range(lineno, end_lineno + 1):
                        lines.append(l)
                raw_lines = []
                for l in self.raw_change_lines:
                    if l in range(lineno, end_lineno + 1):
                        raw_lines.append(l)
                if len(lines) != 0:
                    c_node = ChangeNode(n, lineno, end_lineno, lines, raw_lines)
                    node.add_children(c_node)
                    c_node.set_parent(node)
                    nodes.append(c_node)
                elif type(n) in elem_types:
                    for name, value in ast.iter_fields(node.node):
                        if isinstance(value, list) and n in value:
                            node.add_field_children(name, elem_types[type(n)])
                        elif n == value:
                            node.add_field_children(name, elem_types[type(n)])
            for name, value in ast.iter_fields(node.node):
                if not isinstance(value, list) and not issubclass(type(value), ast.AST) and name not in ['ctx', 'lienno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment'] and (name == 'value' or (name != 'value' and value != None)):
                    node.add_field_children(name, value)
                elif isinstance(value, list):
                    for v in value:
                        if not issubclass(type(v), ast.AST) and name not in ['ctx', 'lienno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment'] and (name == 'value' or (name != 'value' and value != None)):
                            node.add_field_children(name, v)

        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            if (len(node.stmt_children) == 0 or len(node.expr_children) > 0) and node.type == 'stmt':
                self.deepest_changed_stmts.append(node)
            elif node.type == 'stmt' and not node.totally_changed:
                include = True
                changelines = []
                for c in node.stmt_children:
                    if not c.totally_changed:
                        include = False
                        break
                    else:
                        changelines += c.change_lines
                if include and len(set(changelines)) < len(set(node.change_lines)):
                    self.deepest_changed_stmts.append(node)
                else:
                    nodes += node.stmt_children
            elif node.type == 'stmt' and len(node.stmt_children) > 0:
                nodes += node.stmt_children

        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            if node in self.deepest_changed_stmts and not node.totally_changed:
                continue
            if node.totally_changed:
                self.uppest_totally_changed_stmts.append(node)
            else:
                nodes += node.stmt_children
        
        for n in self.deepest_changed_stmts:
            included = False
            for m in self.uppest_totally_changed_stmts:
                if n.has_parent(m) or n == m:
                    included = True
                    break
            if not included:
                self.deepest_partially_changed_stmts.append(n)

    def draw(self, filename = None, graph = None, index = None):
        if not filename:
            filename = 'CHANGE_TREE'
        if not graph:
            f = Digraph("Change Tree", filename = filename)
            index = 0
        else:
            f = graph
            index = index
        added = []
        nodemap = {}

        if not self.before:
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
        else:
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
        for n in self.uppest_totally_changed_stmts:
            f.node(f'node{index}', label = n.resolve_name())
            nodemap[n] = f'node{index}'
            index += 1
            added.append(n)
        
        if not self.before:
            f.attr('node', shape = 'box', fillcolor = 'coral', style = 'filled')
        else:
            f.attr('node', shape = 'box', fillcolor = 'coral', style = 'filled, dashed')
        for n in self.deepest_partially_changed_stmts:
            f.node(f'node{index}', label = n.resolve_name())
            nodemap[n] = f'node{index}'
            index += 1
            added.append(n)
        
        if not self.before:
            f.attr('node', shape = 'box', fillcolor = 'darkgoldenrod1', style = 'filled')
        else:
            f.attr('node', shape = 'box', fillcolor = 'darkgoldenrod1', style = 'filled, dashed')
        for n in self.uppest_totally_changed_stmts:
            for c in n.get_all_stmt_children():
                f.node(f'node{index}', label = c.resolve_name())
                nodemap[c] = f'node{index}'
                index += 1
                added.append(c)
        
        if not self.before:
            f.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
        else:
            f.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled, dashed')
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            for n in node.expr_children:
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
                added.append(n)
            nodes += node.stmt_children
            nodes += node.expr_children

        if not self.before:
            f.attr('node', shape = 'note', fillcolor = 'none', style = 'filled')
        else:
            f.attr('node', shape = 'note', fillcolor = 'none', style = 'filled, dashed')
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            if node not in added:
                f.node(f'node{index}', label = node.resolve_name())
                nodemap[node] = f'node{index}'
                index += 1
                added.append(node)
            nodes += node.stmt_children
        
        try:
            nodes = [self.root]
            while(len(nodes) != 0):
                node = nodes[0]
                nodes = nodes[1:]
                for n in node.stmt_children:
                    f.edge(nodemap[node], nodemap[n], label = n.parent_relation)
                for n in node.expr_children:
                    f.edge(nodemap[node], nodemap[n], label = n.parent_relation)
                nodes += node.stmt_children
                nodes += node.expr_children
        except KeyError as e:
            print(node.resolve_name())
            print(n.resolve_name())
            exit()

        if not graph:
            f.render(filename = filename, view = False)
        else:
            return index

    @staticmethod
    def compare(a, b):
        if type(a) != type(b):
            return False
        else:
            if not ChangeNode.compare(a.root, b.root):
                return False
            if not ChangeNode.compare(a.uppest_totally_changed_stmts, b.uppest_totally_changed_stmts):
                return False
            if not ChangeNode.compare(a.deepest_partially_changed_stmts, b.deepest_partially_changed_stmts):
                return False
            if not ChangeNode.compare(a.deepest_changed_stmts, b.deepest_changed_stmts):
                return False

            return True

class ChangePair(object):
    def __init__(self, before, after, status):
        self.before = before
        self.after = after
        self.status = status

    def draw(self, filename = None):
        if not filename:
            filename = 'CHANGE_PAIR'
        f = Digraph("Change Pair", filename = filename)
        index = 0
        for b in self.before:
            index = b.draw(graph = f, index = index)
            index += 1
        for a in self.after:
            index = a.draw(graph = f, index = index)
            index += 1
        
        f.render(filename = filename, view = False)

            




class ASTCompare(object):
    def __init__(self):
        self.beforeroot = None
        self.afterroot = None

    def build_change_tree(self, root, before, change_lines, raw_change_lines):
        nodes = {}
        change_trees = []
        for l in change_lines:
            for n in root.body:
                if l in range(n.lineno, n.end_lineno + 1):
                    if n not in nodes:
                        nodes[n] = []
                    nodes[n].append(l)
        
        raw_nodes = {}
        for l in raw_change_lines:
            for n in root.body:
                if l in range(n.lineno, n.end_lineno + 1):
                    if n not in raw_nodes:
                        raw_nodes[n] = []
                    raw_nodes[n].append(l)
        
        for n in nodes:
            c_node = ChangeNode(n, n.lineno, n.end_lineno, nodes[n], raw_nodes[n])
            c_tree = ChangeTree(c_node, before, nodes[n], raw_nodes[n])
            c_tree.build()
            change_trees.append(c_tree)
        
        return change_trees


    def compare_change_tree(self, before_trees, after_trees):
        change_status = {'Added': {'Totally': [], 'Partially': []}, 'Removed': {'Totally': [], 'Partially': []}, 'Replaced': {'before': {'Totally': [], 'Partially': []}, 'after': {'Totally': [], 'Partially': []}}, 'order': {'before': [], 'after': []}}
        if len(before_trees) == 0 and len(after_trees) == 0:
            raise ValueError('Change trees before and after the commit are both empty.')
        linemap = {}
        if len(before_trees) == 0:
            linemap = {}
            for a in after_trees:
                for s in a.uppest_totally_changed_stmts:
                    s.set_status('Added')
                    s.set_status_for_childrens('Added')
                    s.set_status_for_parent('Added_Parent')
                    change_status['Added']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Added']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Added']['Totally']) - 1))
                for s in a.deepest_partially_changed_stmts:
                    s.set_status('Added_Parent')
                    s.set_status_for_parent('Added_Parent')
                    change_status['Added']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Added']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Added']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['after'] += loc

        elif len(after_trees) == 0:
            linemap = {}
            for b in before_trees:
                for s in b.uppest_totally_changed_stmts:
                    s.set_status('Removed')
                    s.set_status_for_childrens('Removed')
                    s.set_status_for_parent('Removed_Parent')
                    change_status['Removed']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Removed']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Removed']['Totally']) - 1))
                for s in b.deepest_partially_changed_stmts:
                    s.set_status('Removed_Parent')
                    s.set_status_for_parent('Removed_Parent')
                    change_status['Removed']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Removed']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Removed']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['before'] += loc
        
        else:
            linemap = {}
            for b in before_trees:
                for s in b.uppest_totally_changed_stmts:
                    s.set_status('Replaced')
                    s.set_status_for_childrens('Replaced')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['before']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Replaced']['before']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Replaced']['before']['Totally']) - 1))
                for s in b.deepest_partially_changed_stmts:
                    s.set_status('Replaced_Parent')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['before']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Replaced']['before']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Replaced']['before']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['before'] += loc
            linemap = {}
            for a in after_trees:
                for s in a.uppest_totally_changed_stmts:
                    s.set_status('Replaced')
                    s.set_status_for_childrens('Replaced')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['after']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Replaced']['after']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Replaced']['after']['Totally']) - 1))
                for s in a.deepest_partially_changed_stmts:
                    s.set_status('Replaced_Parent')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['after']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Replaced']['after']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Replaced']['after']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['after'] += loc
            if len(change_status['Replaced']['before']['Partially']) != len(change_status['Replaced']['after']['Partially']):
                logger.warning('Inconsistent number of partially changed statements before ({}) and after ({}) the commit'.format(len(change_status['Replaced']['before']['Partially']), len(change_status['Replaced']['after']['Partially'])))
        return ChangePair(before_trees, after_trees, change_status)


    def compare_loc(self, lines, content):
        if len(lines) != 4:
            raise ValueError('Incorrect line information: {}'.format(line))
        if '\ No newline at end of file' in content:
            logger.warning('Illegal commit, skipped.')
            return None
        before_index = lines[0]
        after_index = lines[2]
        before_change_lines = []
        raw_before_change_lines = []
        after_change_lines = []
        raw_after_change_lines = []
        for line in content.splitlines():
            if not line.startswith('-') and not line.startswith('+'):
                before_index += 1
                after_index += 1
            elif line.startswith('-'):
                if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                    before_change_lines.append(before_index)
                raw_before_change_lines.append(before_index)
                before_index += 1
            elif line.startswith('+'):
                if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                    after_change_lines.append(after_index)
                raw_after_change_lines.append(after_index)
                after_index += 1
        if before_index != lines[0] + lines[1] or after_index != lines[2] + lines[3]:
            raise ValueError('Line information does not match the change content.')
        if self.beforeroot:
            before_trees = self.build_change_tree(self.beforeroot, True, before_change_lines, raw_before_change_lines)
        else:
            before_trees = []
        if self.afterroot:
            after_trees = self.build_change_tree(self.afterroot, False, after_change_lines, raw_after_change_lines)
        else:
            after_trees = []

        if len(before_trees) == 0 and len(after_trees) == 0:
            logger.warning('Empty commit.')
            return None
        
        return self.compare_change_tree(before_trees, after_trees)
        

    
    def compare_commit(self, commitinfo):
        change_pairs = {}
        for f in commitinfo:
            change_pairs[f] = {}
            beforefile, afterfile = commitinfo[f]['files']
            try:
                if beforefile:
                    self.beforeroot = ast.parse(open(beforefile, 'r').read())
                else:
                    self.beforeroot = None
                if afterfile:
                    self.afterroot = ast.parse(open(afterfile, 'r').read())
                else:
                    self.afterroot = None
            except Exception as e:
                logger.error(f'Cannot parse the source files, reason:{e}')
                continue
            for l in commitinfo[f]:
                #if l != 'from cirq import (':
                #    continue
                if l == 'files':
                    continue
                logger.info(f'+++++++Handling location {l}')
                change_pairs[f][l] = []
                for commit in commitinfo[f][l]:
                    change_pair = self.compare_loc(commit['lines'], commit['content'])
                    if change_pair != None:
                        change_pairs[f][l].append(change_pair)
                    #if change_pair:
                    #    change_pair.draw()
        
        return change_pairs
                    


    def compare_projects(self, datafile):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        change_pairs = {}
        for r in tqdm(data, desc = 'Generating Change Pairs'):
            #if r != 'TileDB-Inc/TileDB-Py':
            #    continue
            change_pairs[r] = {}
            for c in data[r]:
                #if c != '3a6957d662a3d8ff5fd2a0be045be763347f935c':
                #    continue
                logger.info(f'Handling commit {c} in {r}')
                change_pairs[r][c] = self.compare_commit(data[r][c])
        
        return change_pairs


class TemplateNode(object):
    def __init__(self, nodetype):
        # Types:
        # Root - The root node of a template tree
        # Variable - Nodes representing variables
        # Op - Nodes representing operations
        # Literal - Node representing literals
        # Builtin - Node representing builtin keywords and names
        # Attribute - Node representing the attributes of a variable or literal
        # Module - Node representing imported modules
        # Expr - Node representing expressions
        # Stmt - Node representing statements
        self.type = nodetype
        self.refer_to = []
        self.referred_from = []
        if self.type == 'Root':
            self.children = {'body': []}
        else:
            self.children = {}
        # Value must be None if there is any children
        self.value = None
        self.ast_type = None
        self.abstracted = False
        self.partial = False
        self.asname = None
    
    def build_from_stmt(self, stmt, partial = False):
        self.type = 'Stmt'
        self.ast_type = type(stmt.node)
        self.partial = partial
        if self.ast_type in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
            node = TemplateNode('Variable')
            node.value = stmt.field_children['name']
            node.partial = partial
            if 'name' not in self.children:
                self.children['name'] = [node]
            else:
                self.children['name'].append(node)
        elif self.ast_type in [ast.Global, ast.Nonlocal]:
            for n in stmt.node.names:
                node = TemplateNode('Variable')
                node.value = n
                node.partial = partial
                if 'name' not in self.children:
                    self.children['name'] = [node]
                else:
                    self.children['name'].append(node)
        elif self.ast_type == ast.Import:
            for a in stmt.node.names:
                node = TemplateNode('Module')
                node.value = a.name
                node.partial = partial
                if a.asname != None:
                    node.asname = a.asname
                if 'names' not in self.children:
                    self.children['names'] = [node]
                else:
                    self.children['names'].append(node)
        elif self.ast_type == ast.ImportFrom:
            node = TemplateNode('Module')
            node.value = stmt.node.module
            node.partial = partial
            if 'module' not in self.children:
                self.children['module'] = [node]
            else:
                self.children['module'].append(node)
            for a in stmt.node.names:
                node = TemplateNode('Module')
                node.name = a.name
                node.partial = partial
                if a.asname != None:
                    node.asname = a.asname
                if 'names' not in self.children:
                    self.children['names'] = [node]
                else:
                    self.children['names'].append(node)
        elif self.ast_type == ast.ExceptHandler and 'name' in stmt.field_children:
            node = TemplateNode('Variable')
            node.value = stmt.field_children['name']
            node.partial = partial
            if 'name' not in self.children:
                self.children['name'] = [node]
            else:
                self.children['name'].append(node)
        for s in stmt.stmt_children:
            node = TemplateNode('Stmt')
            node.build_from_stmt(s, partial = partial)
            if s.parent_relation not in self.children:
                self.children[s.parent_relation] = [node]
            else:
                self.children[s.parent_relation].append(node)
        
        for e in stmt.expr_children:
            if type(e.node) != ast.arguments:
                node = TemplateNode('Expr')
                node.build_from_expr(e, partial = partial)
                if e.parent_relation not in self.children:
                    self.children[e.parent_relation] = [node]
                else:
                    self.children[e.parent_relation].append(node)
            else:
                for arg in e.expr_children:
                    node = TemplateNode('Expr')
                    node.build_from_expr(arg, partial = partial)
                    if arg.parent_relation not in self.children:
                        self.children[arg.parent_relation] = [node]
                    else:
                        self.children[arg.parent_relation].append(node)
    

    def build_from_expr(self, expr, partial = False):
        self.type = 'Expr'
        self.ast_type = type(expr.node)
        self.partial = partial
        if type(expr.node) == ast.Name:
            if expr.field_children['id'] not in (builtins + stdtypes):
                self.type = 'Variable'
                self.value = expr.field_children['id']
            else:
                self.type = 'Builtin'
                self.value = expr.field_children['id']

        elif type(expr.node) == ast.arg:
            self.type = 'Variable'
            self.value = expr.field_children['arg']
            
        elif type(expr.node) == ast.Attribute:
            self.type = 'Attribute'
            self.value = ast.unparse(expr.node)
            node = TemplateNode('Expr')

        elif type(expr.node) == ast.Constant:
            self.type = 'Literal'
            self.value = expr.field_children['value']
        elif type(expr.node) in [ast.BoolOp, ast.BinOp, ast.UnaryOp]:
            node = TemplateNode('Op')
            node.value = expr.field_children['op']
            node.partial = partial
            self.children['op'] = [node]
        elif type(expr.node) == ast.Compare:
            if isinstance(expr.field_children['ops'], list):
                for o in expr.field_children['ops']:
                    node = TemplateNode('Op')
                    node.value = o
                    node.partial = partial
                    if 'op' not in self.children:
                        self.children['op'] = [node]
                    else:
                        self.children['op'].append(node)
            else:
                node = TemplateNode('Op')
                node.value = expr.field_children['ops']
                node.partial = partial
                self.children['op'] = [node]
    
        if type(expr.node) != ast.Attribute:
            for e in expr.expr_children:
                node = TemplateNode('Expr')
                node.build_from_expr(e, partial = partial)
                if e.parent_relation not in self.children:
                    self.children[e.parent_relation] = [node]
                else:
                    self.children[e.parent_relation].append(node)
        if len(expr.expr_children) == 0 and len(expr.field_children) == 1 and self.value == None:
            self.value = list(expr.field_children.values())[0]

    @staticmethod
    def compare(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return False
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type or len(a.children) != len(b.children):
            return False
        for c in a.children:
            if c not in b.children:
                return False
            for n in a.children[c]:
                found = False
                for nn in b.children[c]:
                    if TemplateNode.compare(n, nn):
                        found = True
                        break
                if not found:
                    return False
        
        return True

    def resolve_name(self):
        name = '{} | {}'.format(self.type, self.ast_type.__name__ if self.ast_type else 'none')
        if self.value != None or self.type == 'Literal':
            name += '\n{}'.format(str(self.value))
        return name





class TemplateTree(object):
    def __init__(self):
        self.root = None
        self.variables = []
        self.literals = []
        self.ops = []
        self.attributes = []
        self.builtins = []
        self.modules = []
        self.exprs = []
        self.stmts = []


    def build(self, changetrees, partial = False):
        self.root = TemplateNode('Root')
        for c in changetrees:
            node = TemplateNode('Stmt')
            node.build_from_stmt(c, partial = partial)
            self.root.children['body'].append(node)
        self.collect_special_nodes()

    def collect_special_nodes(self):
        nodes = self.root.children['body']
        while(len(nodes) > 0):
            node = nodes[0]
            nodes = nodes[1:]
            if node.type == 'Variable':
                self.variables.append(node)
            elif node.type == 'Attribute':
                self.attributes.append(node)
            elif node.type == 'Builtin':
                self.builtins.append(node)
            elif node.type == 'Literal':
                self.literals.append(node)
            elif node.type == 'Module':
                self.modules.append(node)
            elif node.type == 'Op':
                self.ops.append(node)
            elif node.type == 'Expr':
                self.ops.append(node)
            elif node.type == 'Stmt':
                self.stmts.append(node)
            for c in node.children:
                nodes += node.children[c]

    @staticmethod
    def merge(partially, totally, order):
        tree = TemplateTree()
        tree.root = TemplateNode('Root')
        if len(order) != len(partially.root.children['body'] + totally.root.children['body']):
            raise ValueError('Provided order list {} ({}) is inconsistent with the actual nodes ({} + {}).'.format(order, len(order), len(partially.root.children['body']), len(totally.root.children['body'])))
        for o in order:
            if o.startswith('Partially-'):
                index = int(o.replace('Partially-', ''))
                tree.root.children['body'].append(partially.root.children['body'][index])
            elif o.startswith('Totally-'):
                index = int(o.replace('Totally-', ''))
                tree.root.children['body'].append(totally.root.children['body'][index])
        if len(tree.root.children['body']) != len(order):
            raise ValueError('Error occurs when sorting the nodes.')
        tree.collect_special_nodes()
        return tree

    def iter_nodes(self):
        nodes = [self.root]
        while(len(nodes) > 0):
            node = nodes[0]
            nodes = nodes[1:]
            yield node
            for c in node.children:
                nodes += node.children[c]
            


                

class FixTemplate(object):
    def __init__(self, action, before, after):
        # Actions:
        # Add - All original statements remains the same and only new statements added
        # Remove - No new statements added and some original code statements removed
        # Insert - All original statements remains with different locations and some new statements added
        # Shuffle - No new statements added but the order of original statements changed
        # Replace - Some original statements removed and new statements added
        self.action = action
        # Before tree for Add templates must be None
        self.before = before
        # After tree for Remove templates must be None
        self.after = after
        self.instances = []
        self.id = None
        self.abstraction_num = 0
    
    def add_instance(self, instance):
        if instance not in self.instances and isinstance(instance, ChangePair):
            self.instances.append(instance)

    def merge(self, fix_template):
        if isinstance(fix_template, FixTemplate) and self.action == fix_template.action and\
        ChangeNode.compare(self.before, fix_template.before) and ChangeNode.compare(self.after, fix_template.after):
            for i in fix_template.instances:
                if i not in self.instances:
                    self.instances.append(i)

    def draw(self, filerepo = None):
        filename = 'FIX_TEMPLATE_{}'.format(self.id)
        if filerepo:
            filename = os.path.join(filerepo, filename)
        nodemap = {}
        index = 0
        f = Digraph("Fix Template", filename = filename)
        if self.before:
            f.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled, dashed')
            f.node(f'node{index}', label = self.before.root.resolve_name())
            nodemap[self.before.root] = f'node{index}'
            index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.before.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        f.edge(nodemap[n], nodemap[cn], label = c)
        if self.after:
            f.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
            f.node(f'node{index}', label = self.after.root.resolve_name())
            nodemap[self.after.root] = f'node{index}'
            index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.after.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        f.edge(nodemap[n], nodemap[cn], label = c)
        
        f.attr(label = f'Template Category: {self.action}; Abstraction Num: {self.abstraction_num}')
        f.attr(fontsize = '25')
        
        f.render(filename = filename, view = False)









class FixMiner(object):
    def __init__(self):
        self.fix_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.ori_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.id2template = {}


    def abstract_variables(self, fix_template, level = 1, keeporder = False):
        # Levels:
        # 1 - Abstract variables into tokens VAR
        # keeporder: generate abstract tokens VAR_1, VAR_2, ... that indicate different variables
        pass

    def abstract_literals(self, fix_template, level = 1):
        # Levels:
        # 1 - Abstract literals into its type INT, FLOAT, STR, ...
        # 2 - Abstract literals into LITERAL
        pass

    def abstract_ops(self, fix_template, level = 1):
        # Levels:
        # 1 - Abstract operations into larger category CMP_OP, BIN_OP, ...
        # 2 - Abstract operations into OP
        pass

    def abstract_exprs(self, fix_template, level = 1, keeporder = False):
        # Levels:
        # 1 - Abstract exprs into its type Lambda, Yield, ...
        # 2 - Abstract exprs into EXPR
        # keeporder: generate abstract tokens that indicate different exprs
        pass

    def abstract_stmts(self, fix_template, level = 1, keeporder = False):
        # Levels:
        # 1 - Abstract stmts into its type Assign, If, ...
        # 2 - Abstract stmts into STMT
        # keeporder: generate abstract tokens that indicate different stmts
        pass

    def subtree_compare(self, a, b):
        # Check whether a is a subtree of b
        if TemplateNode.compare(a, b):
            return b
        for c in b.children:
            for n in b.children[c]:
                sub_n = self.subtree_compare(a, n)
                if sub_n != None:
                    return sub_n
        return None

    def add_reference(self, ori, now):
        for c in ori.children:
            for on in ori.children[c]:
                if len(on.referred_from) > 0:
                    continue
                for nn in now.children[c]:
                    if len(nn.refer_to) > 0:
                        continue
                    if TemplateNode.compare(on, nn):
                        on.referred_from.append(nn)
                        nn.refer_to.append(on)
                        self.add_reference(on, nn)

    def include_compare(self, a, b):
        # Check whether b includes all nodes of a
        if TemplateNode.compare(a, b):
            return True
        for ca in a.children:
            if ca not in b.children:
                return False
            for an in a.children[ca]:
                found = False
                paired_b = []
                for bi, bn in enumerate(b.children[ca]):
                    if bi in paired_b:
                        continue
                    if self.include_compare(an, bn):
                        found = True
                        paired_b.append(bi)
                        break
                if not found:
                    return False
        return True


    def _cut_same_nodes(self, before_tree, after_tree):
        for bi, bn in enumerate(before_tree.root.children['body']):
            for bc in bn.children:
                removed_b = []
                removed_a = []
                if bi < len(after_tree.root.children['body']) and bc in after_tree.root.children['body'][bi].children:
                    for i, n in enumerate(bn.children[bc]):
                        if i < len(after_tree.root.children['body'][bi].children[bc]) and TemplateNode.compare(n, after_tree.root.children['body'][bi].children[bc][i]):
                            removed_b.append(n)
                            removed_a.append(after_tree.root.children['body'][bi].children[bc][i])
                    for n in removed_b:
                        bn.children[bc].remove(n)
                    for n in removed_a:
                        after_tree.root.children['body'][bi].children[bc].remove(n)
        
        return before_tree, after_tree


    def _process_replaced(self, pair):
        # Classify change pairs into Inserted, Shuffle and Replaced templates
        # Shuffle templates require no partially changed statements
        if len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0:
            partial_before_tree = TemplateTree()
            partial_before_tree.build(pair.status['Replaced']['before']['Partially'], partial = True)
            partial_after_tree = TemplateTree()
            partial_after_tree.build(pair.status['Replaced']['after']['Partially'], partial = True)
            partial_before_tree, partial_after_tree = self._cut_same_nodes(partial_before_tree, partial_after_tree)
            # Check Insert, Add, Remove pattern
            if len(pair.status['Replaced']['before']['Partially']) > 0 and len(pair.status['Replaced']['after']['Partially']) > 0:
                added = True
                removed = True
                for i, an in enumerate(partial_after_tree.root.children['body']):
                    if not self.include_compare(partial_before_tree.root.children['body'][i], an):
                        added = False
                    if not self.include_compare(an, partial_before_tree.root.children['body'][i]):
                        removed = False
                    if not added and not removed:
                        break
            else:
                added = False
                removed = False
            # Check Add pattern
            if added and len(pair.status['Replaced']['before']['Totally']) == 0:
                totally_after_tree = TemplateTree()
                totally_after_tree.build(pair.status['Replaced']['after']['Totally'])
                after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                template = FixTemplate('Add', partial_before_tree, after_tree)
                template.add_instance(pair)
                return template
            # Check Remove pattern
            elif removed and len(pair.status['Replaced']['after']['Totally']) == 0:
                totally_before_tree = TemplateTree()
                totally_before_tree.build(pair.status['Replaced']['before']['Totally'])
                before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                template = FixTemplate('Remove', before_tree, partial_after_tree)
                template.add_instance(pair)
                return template
            # Check Insert pattern
            elif added:
                totally_before_tree = TemplateTree()
                totally_before_tree.build(pair.status['Replaced']['before']['Totally'])
                totally_after_tree = TemplateTree()
                totally_after_tree.build(pair.status['Replaced']['after']['Totally'])
                for bn in totally_before_tree.root.children['body']:
                    if len(bn.referred_from) == 0:
                        for an in totally_after_tree.root.children['body']:
                            sub_n = self.subtree_compare(bn, an)
                            if sub_n != None:
                                bn.referred_from.append(sub_n)
                                sub_n.refer_to.append(bn)
                                self.add_reference(bn, sub_n)
                all_referred = True
                for bn in totally_before_tree.root.children['body']:
                    if len(bn.referred_from) == 0:
                        all_referred = False
                        break
                if all_referred:
                    before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    template = FixTemplate('Insert', before_tree, after_tree)
                    template.add_instance(pair)
                    return template
                else:
                    before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    template = FixTemplate('Replace', before_tree, after_tree)
                    template.add_instance(pair)
                    return template
            #Remains are Replace patterns
            else:
                totally_before_tree = TemplateTree()
                totally_before_tree.build(pair.status['Replaced']['before']['Totally'])
                totally_after_tree = TemplateTree()
                totally_after_tree.build(pair.status['Replaced']['after']['Totally'])
                before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                template = FixTemplate('Replace', before_tree, after_tree)
                template.add_instance(pair)
                return template
        else:
            before_tree = TemplateTree()
            before_tree.build(pair.status['Replaced']['before']['Totally'])
            after_tree = TemplateTree()
            after_tree.build(pair.status['Replaced']['after']['Totally'])
            # Check Shuffle pattern
            if len(before_tree.root.children['body']) == len(after_tree.root.children['body']):
                before2after = {}
                after2before = {}
                for bi, bn in enumerate(before_tree.root.children['body']):
                    for ai, an in enumerate(after_tree.root.children['body']):
                        if TemplateNode.compare(bn, an) and ai not in after2before:
                            before2after[bi] = ai
                            after2before[ai] = bi
                for i in before2after:
                    before_tree.root.children['body'][i].referred_from.append(after_tree.root.children['body'][before2after[i]])
                    after_tree.root.children['body'][before2after[i]].refer_to.append(before_tree.root.children['body'][i])
                if len(before2after) == len(before_tree.root.children['body']) and len(after2before) == len(after_tree.root.children['body']):
                    template = FixTemplate('Shuffle', before_tree, after_tree)
                    template.add_instance(pair)
                    return template
            # Check Insert pattern
            for bn in before_tree.root.children['body']:
                if len(bn.referred_from) == 0:
                    for an in after_tree.root.children['body']:
                        sub_n = self.subtree_compare(bn, an)
                        if sub_n != None:
                            bn.referred_from.append(sub_n)
                            sub_n.refer_to.append(bn)
                            self.add_reference(bn, sub_n)
            all_referred = True
            for bn in before_tree.root.children['body']:
                if len(bn.referred_from) == 0:
                    all_referred = False
                    break
            if all_referred:
                template = FixTemplate('Insert', before_tree, after_tree)
                template.add_instance(pair)
                return template
            # Remains are Replace patterns
            template = FixTemplate('Replace', before_tree, after_tree)
            template.add_instance(pair)
            return template

    def build_templates(self, change_pairs):
        for r in tqdm(change_pairs, desc = 'Initializing Fix Templates'):
            for c in change_pairs[r]:
                for f in change_pairs[r][c]:
                    for l in change_pairs[r][c][f]:
                        for pair in change_pairs[r][c][f][l]:
                            logger.info('++++++Handling {}/{}/{}/{} change pair'.format(r, c, f, l))
                            if len(pair.status['Added']['Totally']) + len(pair.status['Added']['Partially']) > 0:
                                totally_after_tree = None
                                partial_after_tree = None
                                if len(pair.status['Added']['Totally']) > 0:
                                    totally_after_tree = TemplateTree()
                                    totally_after_tree.build(pair.status['Added']['Totally'])
                                if len(pair.status['Added']['Partially']) > 0:
                                    partial_after_tree = TemplateTree()
                                    partial_after_tree.build(pair.status['Added']['Partially'])
                                if totally_after_tree != None and partial_after_tree != None:
                                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                                else:
                                    if totally_after_tree:
                                        after_tree = totally_after_tree
                                    else:
                                        after_tree = partial_after_tree
                                template = FixTemplate('Add', None, after_tree)
                                template.add_instance(pair)
                                self.fix_template['Add'].append(template)
                                continue
                            if len(pair.status['Removed']['Totally']) + len(pair.status['Removed']['Partially']) > 0:
                                totally_before_tree = None
                                partial_before_tree = None
                                if len(pair.status['Removed']['Totally']) > 0:
                                    totally_before_tree = TemplateTree()
                                    totally_before_tree.build(pair.status['Removed']['Totally'])
                                if len(pair.status['Removed']['Partially']) > 0:
                                    partial_before_tree = TemplateTree()
                                    partial_before_tree.build(pair.status['Removed']['Partially'])
                                if totally_before_tree != None and partial_before_tree != None:
                                    before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                                else:
                                    if totally_before_tree:
                                        before_tree = totally_before_tree
                                    else:
                                        before_tree = partial_before_tree
                                template = FixTemplate('Remove', before_tree, None)
                                template.add_instance(pair)
                                self.fix_template['Remove'].append(template)
                                continue
                            if len(pair.status['Replaced']['before']['Totally']) + len(pair.status['Replaced']['after']['Totally']) > 0 or \
                            len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0:
                                if len(pair.status['Replaced']['before']['Partially']) != len(pair.status['Replaced']['after']['Partially']) and\
                                len(pair.status['Replaced']['before']['Partially']) > 0 and len(pair.status['Replaced']['after']['Partially']) > 0:
                                    logger.error('Inconsistent number of partially changed statements before and after the commit.')
                                    continue
                                template = self._process_replaced(pair)
                                self.fix_template[template.action].append(template)
        self.clean()
        self.assign_ids()
        #self.ori_template = copy.deepcopy(self.fix_template)


    def assign_ids(self):
        index = 0
        for c in self.fix_template:
            for t in self.fix_template[c]:
                t.id = index
                self.id2template[index] = t
                index += 1   

    def clean(self):
        # Remove those could not be fix templates
        num = 0 
        # Case 1: Only add/remove a whole function
        removed = []
        for t in self.fix_template['Add']:
            if t.before != None:
                continue
            remove = True
            for n in t.after.root.children['body']:
                if n.ast_type not in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
                    remove = False
                    break
            if remove:
                removed.append(t)
        for t in removed:
            self.fix_template['Add'].remove(t)
        num += len(removed)
        removed = []
        for t in self.fix_template['Remove']:
            if t.after != None:
                continue
            remove = True
            for n in t.before.root.children['body']:
                if n.ast_type not in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
                    remove = False
                    break
            if remove:
                removed.append(t)
        for t in removed:
            self.fix_template['Remove'].remove(t)
        num += len(removed)
        print('Cleaned {} templates.'.format(num))


    def print_info(self):
        print('Information of fix templates:')
        for c in self.fix_template:
            print(c, len(self.fix_template[c]))

        print('Total: {} templates.'.format(len(self.id2template)))     

    def mine(self):
        pass



if __name__ == '__main__':
    a = ASTCompare()
    change_pairs = a.compare_projects('combined_commits_contents.json')
    miner = FixMiner()
    miner.build_templates(change_pairs)
    miner.print_info()
    #for i in miner.id2template:
    #    miner.id2template[i].draw(filerepo = '/data/project/ypeng/typeerror/figures')


        
        
                

                





    