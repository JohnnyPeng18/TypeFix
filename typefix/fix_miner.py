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
        self.metadata = None

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
        if self.metadata:
            f.attr(label = 'Repo: {}; Commit: {}; File: {}; Loc:{}\n Content: {}'.format(self.metadata['repo'], self.metadata['commit'], self.metadata['file'], self.metadata['loc'], self.metadata['content']))
            f.attr(fontsize = '25')
        
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
        

    
    def compare_commit(self, commitinfo, r, c):
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
                #if l != 'def validate_args(args)':
                #    continue
                if l == 'files':
                    continue
                logger.info(f'+++++++Handling location {l}')
                change_pairs[f][l] = []
                for commit in commitinfo[f][l]:
                    change_pair = self.compare_loc(commit['lines'], commit['content'])
                    if change_pair != None:
                        change_pairs[f][l].append(change_pair)
                        change_pair.metadata = {'repo': r, 'commit': c, 'file': f, 'loc': l, 'content': commit['content']}
                    #if change_pair:
                    #    change_pair.draw()
        
        return change_pairs
                    


    def compare_projects(self, datafile):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        change_pairs = {}
        for r in tqdm(data, desc = 'Generating Change Pairs'):
            #if r != 'AMWA-TV/nmos-testing':
            #    continue
            change_pairs[r] = {}
            for c in data[r]:
                #if c != '3a6957d662a3d8ff5fd2a0be045be763347f935c':
                #    continue
                logger.info(f'Handling commit {c} in {r}')
                change_pairs[r][c] = self.compare_commit(data[r][c], r, c)
        
        return change_pairs


    def compare_one(self, datafile, repo, commit):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        change_pairs = {}
        for r in tqdm(data, desc = 'Generating Change Pairs'):
            if r != repo:
                continue
            change_pairs[r] = {}
            for c in data[r]:
                if c != commit:
                    continue
                logger.info(f'Handling commit {c} in {r}')
                change_pairs[r][c] = self.compare_commit(data[r][c], r, c)
        
        return change_pairs


class TemplateNode(object):
    def __init__(self, nodetype):
        # Base Types:
        # Root - The root node of a template tree
        # Variable - Nodes representing variables
        # Op - Nodes representing operations
        # Literal - Node representing literals
        # Builtin - Node representing builtin keywords and names
        # Attribute - Node representing the attributes of a variable or literal
        # Module - Node representing imported modules
        # Expr - Node representing expressions
        # Stmt - Node representing statements
        self.base_type = nodetype
        if self.base_type not in ['Stmt', 'Expr']:
            self.type = self.base_type
        else:
            self.type = None
        self.refer_to = []
        self.referred_from = []
        if self.type == 'Root':
            self.children = {'body': []}
        else:
            self.children = {}
        # Value must be None if there is any children
        self.value = None
        self.ast_type = None
        self.value_abstracted = False
        self.type_abstracted = False
        self.partial = False
        self.asname = None
        self.parent = None
        self.parent_relation = None
    
    def build_from_stmt(self, stmt, partial = False):
        self.base_type = 'Stmt'
        self.ast_type = type(stmt.node)
        self.type = self.ast_type.__name__
        self.partial = partial
        if self.ast_type in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
            node = TemplateNode('Variable')
            node.value = stmt.field_children['name']
            node.partial = partial
            node.parent = self
            node.parent_relation = 'name'
            if 'name' not in self.children:
                self.children['name'] = [node]
            else:
                self.children['name'].append(node)
        elif self.ast_type in [ast.Global, ast.Nonlocal]:
            for n in stmt.node.names:
                node = TemplateNode('Variable')
                node.value = n
                node.partial = partial
                node.parent = self
                node.parent_relation = 'name'
                if 'name' not in self.children:
                    self.children['name'] = [node]
                else:
                    self.children['name'].append(node)
        elif self.ast_type == ast.Import:
            for a in stmt.node.names:
                node = TemplateNode('Module')
                node.value = a.name
                node.partial = partial
                node.parent = self
                node.parent_relation = 'names'
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
            node.parent = self
            node.parent_relation = 'module'
            if 'module' not in self.children:
                self.children['module'] = [node]
            else:
                self.children['module'].append(node)
            for a in stmt.node.names:
                node = TemplateNode('Module')
                node.value = a.name
                node.partial = partial
                node.parent = self
                node.parent_relation = 'names'
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
            node.parent = self
            node.parent_relation = 'name'
            if 'name' not in self.children:
                self.children['name'] = [node]
            else:
                self.children['name'].append(node)
        for s in stmt.stmt_children:
            node = TemplateNode('Stmt')
            node.build_from_stmt(s, partial = partial)
            node.parent = self
            node.parent_relation = s.parent_relation
            if s.parent_relation not in self.children:
                self.children[s.parent_relation] = [node]
            else:
                self.children[s.parent_relation].append(node)
        
        for e in stmt.expr_children:
            if type(e.node) != ast.arguments:
                node = TemplateNode('Expr')
                node.build_from_expr(e, partial = partial)
                node.parent = self
                node.parent_relation = e.parent_relation
                if e.parent_relation not in self.children:
                    self.children[e.parent_relation] = [node]
                else:
                    self.children[e.parent_relation].append(node)
            else:
                args = []
                arg_defaults = []
                kwonlyargs = []
                kwonlyarg_defaults = []
                for arg in e.expr_children:
                    if arg.parent_relation in ['args', 'kwonlyargs', 'vararg', 'kwarg']:
                        node = TemplateNode('Expr')
                        node.build_from_expr(arg, partial = partial)
                        node.parent = self
                        node.parent_relation = arg.parent_relation
                        if arg.parent_relation == 'args':
                            args.append(node)
                        elif arg.parent_relation == 'kwonlyargs':
                            kwonlyargs.append(node)
                        if arg.parent_relation not in self.children:
                            self.children[arg.parent_relation] = [node]
                        else:
                            self.children[arg.parent_relation].append(node)
                    if arg.parent_relation in ['kw_defaults', 'defaults']:
                        node = TemplateNode('Expr')
                        node.build_from_expr(arg, partial = partial)
                        if arg.parent_relation == 'kw_defaults':
                            kwonlyarg_defaults.append(node)
                        elif arg.parent_relation == 'defaults':
                            arg_defaults.append(node)
                if len(arg_defaults) > 0:
                    for i in range(0, len(arg_defaults)):
                        args[len(args) - 1 - i].children['default'] = [arg_defaults[len(arg_defaults) - 1 - i]]
                        arg_defaults[len(arg_defaults) - 1 - i].parent = args[len(args) - 1 - i]
                        arg_defaults[len(arg_defaults) - 1 - i].parent_relation = 'default'
                if len(kwonlyarg_defaults) > 0:
                    for i in range(0, len(kwonlyarg_defaults)):
                        kwonlyargs[i].children['default'] = [kwonlyarg_defaults[i]]
                        kwonlyarg_defaults[i].parent = kwonlyargs[i]
                        kwonlyarg_defaults[i].parent_relation = 'default'
    

    def build_from_expr(self, expr, partial = False):
        self.base_type = 'Expr'
        self.ast_type = type(expr.node)
        self.type = self.ast_type.__name__
        self.partial = partial
        if type(expr.node) == ast.Name:
            if expr.field_children['id'] not in (builtins + stdtypes):
                self.type = 'Variable'
                self.base_type = 'Variable'
                self.value = expr.field_children['id']
            else:
                self.type = 'Builtin'
                self.base_type = 'Builtin'
                self.value = expr.field_children['id']

        elif type(expr.node) == ast.arg:
            self.type = 'Variable'
            self.base_type = 'Variable'
            self.value = expr.field_children['arg']
            
        elif type(expr.node) == ast.Attribute:
            #self.type = 'Attribute'
            #self.base_type = 'Attribute'
            self.type = 'Variable'
            self.base_type = 'Variable'
            self.value = ast.unparse(expr.node)

        elif type(expr.node) == ast.Constant:
            self.type = 'Literal'
            self.base_type = 'Literal'
            self.value = expr.field_children['value']
        elif type(expr.node) in [ast.BoolOp, ast.BinOp, ast.UnaryOp]:
            node = TemplateNode('Op')
            node.value = expr.field_children['op']
            node.partial = partial
            node.parent = self
            node.parent_relation = 'op'
            self.children['op'] = [node]
        elif type(expr.node) == ast.Compare:
            if isinstance(expr.field_children['ops'], list):
                for o in expr.field_children['ops']:
                    node = TemplateNode('Op')
                    node.value = o
                    node.partial = partial
                    node.parent = self
                    node.parent_relation = 'op'
                    if 'op' not in self.children:
                        self.children['op'] = [node]
                    else:
                        self.children['op'].append(node)
            else:
                node = TemplateNode('Op')
                node.value = expr.field_children['ops']
                node.partial = partial
                node.parent = self
                node.parent_relation = 'op'
                self.children['op'] = [node]
    
        if type(expr.node) != ast.Attribute:
            for e in expr.expr_children:
                node = TemplateNode('Expr')
                node.build_from_expr(e, partial = partial)
                node.parent = self
                node.parent_relation = e.parent_relation
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
        if len(a.children) != len(b.children):
            return False
        for c in a.children:
            if c not in b.children or len(a.children[c]) != len(b.children[c]):
                return False
            for i in range(0, len(a.children[c])):
                if not TemplateNode.compare(a.children[c][i], b.children[c][i]):
                    return False
        return True

    @staticmethod
    def value_abstract_compare(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return False
        if a.type != b.type:
            return False
        if len(a.children) != len(b.children):
            return False
        for c in a.children:
            if c not in b.children or len(a.children[c]) != len(b.children[c]):
                return False
            for i in range(0, len(a.children[c])):
                if not TemplateNode.value_abstract_compare(a.children[c][i], b.children[c][i]):
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
            node.parent = self.root
            node.parent_relation = 'body'
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
        for n in tree.root.children['body']:
            n.parent = tree.root
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
    
    def get_node_num(self):
        num = 0
        nodes = [self.root]
        while(len(nodes) > 0):
            node = nodes[0]
            nodes = nodes[1:]
            num += 1
            for c in node.children:
                nodes += node.children[c]
        
        return num

    @staticmethod
    def compare(a, b):
        if not isinstance(a, TemplateTree) or not isinstance(b, TemplateTree):
            return False
        else:
            if len(a.root.children['body']) != len(b.root.children['body']):
                return False
            else:
                for i in range(0, len(a.root.children['body'])):
                    if not TemplateNode.compare(a.root.children['body'][i], b.root.children['body'][i]):
                        return False
        

        return True
            
    
    @staticmethod
    def get_same_node_num(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return False
        if a.type == b.type:
            if len(a.children) == len(b.children) and len(a.children) == 0:
                if not a.type_abstracted and not b.type_abstracted and a.value != b.value:
                    return 1
                else:
                    return 2
            elif len(a.children) == 0 and len(b.children) != 0:
                if not a.type_abstracted:
                    return 0
                else:
                    return 2
            elif len(a.children) != 0 and len(b.children) == 0:
                if not b.type_abstracted:
                    return 0
                else:
                    return 2
            else:
                num = 2
                for c in a.children:
                    if c in b.children and len(a.children[c]) == len(b.children[c]):
                        for i in range(0, len(a.children[c])):
                            num += TemplateTree.get_same_node_num(a.children[c][i], b.children[c][i])
                
                return num                      
        else:
            return 0

    def check_abstracted(self):
        for n in self.iter_nodes():
            if n.value_abstracted or n.type_abstracted:
                return True

        return False

    def get_abstracted_num(self):
        num = 0
        for n in self.iter_nodes():
            if n.type_abstracted:
                num += 2
            elif n.value_abstracted:
                num += 1

        return num

    def get_leaf_nodes(self):
        leaf_nodes = []
        for n in self.iter_nodes():
            if len(n.children) == 0:
                leaf_nodes.append(n)
        
        return leaf_nodes


    def get_leaf_paths(self):
        # Leaf Path: <TemplateNode> parent_relation index <TemplateNode> parent_relation index ...
        paths = {}
        leaf_nodes = self.get_leaf_nodes()
        for n in leaf_nodes:
            cur_node = n
            path = []
            while(cur_node.type != 'Root'):
                path += [cur_node, cur_node.parent_relation, cur_node.parent.children[cur_node.parent_relation].index(cur_node), cur_node.parent]
                cur_node = cur_node.parent
                if cur_node == None:
                    raise ValueError('Parents of some nodes are None.')
            paths[n] = path
        
        return paths

    @staticmethod
    def compare_leaf_path(a, b):
        if len(a) != len(b):
            return False
        for i, na in enumerate(a):
            if type(na) != type(b[i]):
                return False
            elif isinstance(na, TemplateNode):
                if na.value != b[i].value or na.type != b[i].type or na.ast_type != b[i].ast_type:
                    return False
            elif na != b[i]:
                return False
        
        return True

    def remove(self, node):
        if node.parent == None or node.base_type == 'Root':
            pass
        else:
            node.parent.children[node.parent_relation].remove(node)
            if len(node.parent.children[node.parent_relation]) == 0:
                del node.parent.children[node.parent_relation]

        
        



                

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
        self.former_templates = []
        self.id = None
        self.abstracted = False
    
    def add_instance(self, instance):
        if instance not in self.instances and isinstance(instance, ChangePair):
            self.instances.append(instance)

    def merge(self, fix_templates):
        for t in fix_templates:
            if not isinstance(t, FixTemplate):
                continue
            if t.abstracted:
                self.abstracted = True
            self.former_templates.append(t.id)
            for i in t.instances:
                if not isinstance(i, ChangePair):
                    continue
                if i not in self.instances:
                    self.instances.append(i)

    @staticmethod
    def get_distance(a, b):
        same_node_num = 0
        if a.before != None and b.before != None:
            same_node_num += TemplateTree.get_same_node_num(a.before.root, b.before.root)
        if a.after != None and b.after != None:
            same_node_num += TemplateTree.get_same_node_num(a.after.root, b.after.root)

        node_num = 0
        if a.before != None:
            node_num += a.before.get_node_num()
        if b.before != None:
            node_num += b.before.get_node_num()
        if a.after != None:
            node_num += a.after.get_node_num()
        if b.after != None:
            node_num += b.after.get_node_num()
        
        distance = same_node_num / node_num

        return distance
        

    def draw(self, filerepo = None, draw_instance = False):
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
        
        f.attr(label = f'Template Category: {self.action}; Instances: {len(self.instances)}')
        f.attr(fontsize = '25')
        
        f.render(filename = filename, view = False)

        if draw_instance:
            for i in range(0, len(self.instances)):
                filename = os.path.join(filerepo, 'FIX_TEMPLATE_{}_INSTANCE_{}'.format(self.id, i))
                self.instances[i].draw(filename = filename)









class FixMiner(object):
    def __init__(self):
        self.fix_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.ori_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.id2template = {}
        self.index = 0


    def abstract_variables(self, fix_template, level = 1, keeporder = False):
        # Levels:
        # 1 - Abstract variables into tokens VAR
        # keeporder: generate abstract tokens VAR_1, VAR_2, ... that indicate different variables
        if level == 1:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.variables:
                    v.abstracted = True
                    if v.value not in name_map:
                        name_map[v.value] = index
                        index += 1
                    if len(v.referred_from) != 0:
                        for r in v.referred_from:
                            r.value = f'VAR_{name_map[v.value]}'
                            r.abstracted = True
                    v.value = f'VAR_{name_map[v.value]}'
                for v in after.variables:
                    v.abstracted = True
                    if len(v.refer_to) > 0:
                        continue
                    if v.value not in name_map:
                        name_map[v.value] = index
                        index += 1
                    v.value = f'VAR_{name_map[v.value]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.variables:
                    v.abstracted = True
                    v.value = 'VAR'
                for v in after.variables:
                    v.abstracted = True
                    v.value = 'VAR'



    def abstract_attributes(self, fix_template, lebel = 1, keeporder = False):
        # Levels:
        # 1 - Abstract attributes into tokens ATTR
        # 2 - Abstract attributes into tokens VAR
        # keeporder: generate abstract tokens ATTR_1/VAR_1, ATTR_2/VAR_2, ... that indicate different attributes
        if level == 1:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.attributes:
                    v.abstracted = True
                    if v.value not in name_map:
                        name_map[v.value] = index
                        index += 1
                    if len(v.referred_from) != 0:
                        for r in v.referred_from:
                            r.value = f'ATTR_{name_map[v.value]}'
                            r.abstracted = True
                    v.value = f'ATTR_{name_map[v.value]}'
                for v in after.attributes:
                    v.abstracted = True
                    if len(v.refer_to) > 0:
                        continue
                    if v.value not in name_map:
                        name_map[v.value] = index
                        index += 1
                    v.value = f'ATTR_{name_map[v.value]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.attributes:
                    v.abstracted = True
                    v.value = 'ATTR'
                for v in after.attributes:
                    v.abstracted = True
                    v.value = 'ATTR'
        elif level == 2:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.attributes:
                    v.abstracted = True
                    if v.value not in name_map:
                        name_map[v.value] = index
                        index += 1
                    if len(v.referred_from) != 0:
                        for r in v.referred_from:
                            r.value = f'VAR_{name_map[v.value]}'
                            r.abstracted = True
                    v.value = f'VAR_{name_map[v.value]}'
                for v in after.attributes:
                    v.abstracted = True
                    if len(v.refer_to) > 0:
                        continue
                    if v.value not in name_map:
                        name_map[v.value] = index
                        index += 1
                    v.value = f'VAR_{name_map[v.value]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.attributes:
                    v.abstracted = True
                    v.value = 'VAR'
                for v in after.attributes:
                    v.abstracted = True
                    v.value = 'VAR'

    def abstract_literals(self, fix_template, level = 1):
        # Levels:
        # 1 - Abstract literals into its type INT, FLOAT, STR, ...
        # 2 - Abstract literals into LITERAL
        if level == 1:
            before = fix_template.before
            after = fix_template.after
            for v in before.literals:
                v.abstracted = True
                if v.value == None:
                    v.value = 'None'
                else:
                    v.value = type(v.value).__name__
            for v in after.literals:
                v.abstracted = True
                if v.value == None:
                    v.value = 'None'
                else:
                    v.value = type(v.value).__name__
        elif level == 2:
            before = fix_template.before
            after = fix_template.after
            for v in before.literals:
                v.abstracted = True
                v.value = 'LITERAL'
            for v in after.literals:
                v.abstracted = True
                v.value = 'LITERAL'

    def abstract_ops(self, fix_template, level = 1):
        # Levels:
        # 1 - Abstract operations into larger category CMP_OP, BIN_OP, ...
        # 2 - Abstract operations into OP
        if level == 1:
            before = fix_template.before
            after = fix_template.after
            for v in before.ops:
                v.abstracted = True
                v.value = op2cat[v.value]
            for v in after.ops:
                v.abstracted = True
                v.value = op2cat[v.value]
        elif level == 2:
            before = fix_template.before
            after = fix_template.after
            for v in before.ops:
                v.abstracted = True
                v.value = 'OP'
            for v in after.ops:
                v.abstracted = True
                v.value = 'OP'

    def abstract_builtins(self, fix_template, level = 1):
        # Levels:
        # 1 - Abstract builtins into tokens VAR
        if level == 1:
            before = fix_template.before
            after = fix_template.after
            for v in before.builtins:
                v.abstracted = True
                v.value = 'VAR'
            for v in after.builtins:
                v.abstracted = True
                v.value = 'VAR'

    def abstract_modules(self, fix_template, level = 1):
        # Levels:
        # 1 - Abstract modules into tokens MODULE
        # 2 - Abstract modules into tokens VAR
        if level == 1:
            before = fix_template.before
            after = fix_template.after
            for v in before.modules:
                v.abstracted = True
                v.value = 'MODULE'
            for v in after.modules:
                v.abstracted = True
                v.value = 'MODULE'
        elif level == 2:
            before = fix_template.before
            after = fix_template.after
            for v in before.modules:
                v.abstracted = True
                v.value = 'VAR'
            for v in after.modules:
                v.abstracted = True
                v.value = 'VAR'

    def abstract_exprs(self, fix_template, level = 1, keeporder = False):
        # Levels:
        # 1 - Abstract exprs into its type Lambda, Yield, ...
        # 2 - Abstract exprs into EXPR
        # keeporder: generate abstract tokens that indicate different exprs
        if level == 1:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.exprs:
                    found = False
                    for n in name_map:
                        if TemplateNode.abstract_compare(v, n):
                            for r in v.referred_from:
                                r.abstracted = True
                                r.value = f'{r.ast_type.__name__}_{name_map[n]}'
                            v.value = f'{v.ast_type.__name__}_{name_map[n]}'
                            found = True
                    if not found:
                        name_map[v] = index
                        index += 1
                        for r in v.referred_from:
                            r.abstracted = True
                            r.value = f'{r.ast_type.__name__}_{name_map[v]}'
                        v.value = f'{v.ast_type.__name__}_{name_map[v]}'
                for v in after.exprs:
                    if len(refer_to) > 0:
                        continue
                    else:
                        found = False
                        for n in name_map:
                            if TemplateNode.abstract_compare(v, n):
                                v.value = f'{v.ast_type.__name__}_{name_map[n]}'
                                found = True
                        if not found:
                            name_map[v] = index
                            index += 1
                            v.value = f'{v.ast_type.__name__}_{name_map[v]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.exprs:
                    v.abstracted = True
                    v.value = v.ast_type.__name__
                for v in after.exprs:
                    v.abstracted = True
                    v.value = v.ast_type.__name__
        elif level == 2:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.exprs:
                    found = False
                    for n in name_map:
                        if TemplateNode.abstract_compare(v, n):
                            for r in v.referred_from:
                                r.abstracted = True
                                r.value = f'EXPR_{name_map[n]}'
                            v.value = f'EXPR_{name_map[n]}'
                            found = True
                    if not found:
                        name_map[v] = index
                        index += 1
                        for r in v.referred_from:
                            r.abstracted = True
                            r.value = f'EXPR_{name_map[v]}'
                        v.value = f'EXPR_{name_map[v]}'
                for v in after.exprs:
                    if len(refer_to) > 0:
                        continue
                    else:
                        found = False
                        for n in name_map:
                            if TemplateNode.abstract_compare(v, n):
                                v.value = f'EXPR_{name_map[n]}'
                                found = True
                        if not found:
                            name_map[v] = index
                            index += 1
                            v.value = f'EXPR_{name_map[v]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.exprs:
                    v.abstracted = True
                    v.value = 'EXPR'
                for v in after.exprs:
                    v.abstracted = True
                    v.value = 'EXPR'

    def abstract_stmts(self, fix_template, level = 1, keeporder = False):
        # Levels:
        # 1 - Abstract stmts into its type Assign, If, ...
        # 2 - Abstract stmts into STMT
        # keeporder: generate abstract tokens that indicate different stmts
        if level == 1:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.stmts:
                    found = False
                    for n in name_map:
                        if TemplateNode.abstract_compare(v, n):
                            for r in v.referred_from:
                                r.abstracted = True
                                r.value = f'{r.ast_type.__name__}_{name_map[n]}'
                            v.value = f'{v.ast_type.__name__}_{name_map[n]}'
                            found = True
                    if not found:
                        name_map[v] = index
                        index += 1
                        for r in v.referred_from:
                            r.abstracted = True
                            r.value = f'{r.ast_type.__name__}_{name_map[v]}'
                        v.value = f'{v.ast_type.__name__}_{name_map[v]}'
                for v in after.stmts:
                    if len(refer_to) > 0:
                        continue
                    else:
                        found = False
                        for n in name_map:
                            if TemplateNode.abstract_compare(v, n):
                                v.value = f'{v.ast_type.__name__}_{name_map[n]}'
                                found = True
                        if not found:
                            name_map[v] = index
                            index += 1
                            v.value = f'{v.ast_type.__name__}_{name_map[v]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.stmts:
                    v.abstracted = True
                    v.value = v.ast_type.__name__
                for v in after.stmts:
                    v.abstracted = True
                    v.value = v.ast_type.__name__
        elif level == 2:
            if keeporder:
                name_map = {}
                index = 0
                before = fix_template.before
                after = fix_template.after
                for v in before.stmts:
                    found = False
                    for n in name_map:
                        if TemplateNode.abstract_compare(v, n):
                            for r in v.referred_from:
                                r.abstracted = True
                                r.value = f'STMT_{name_map[n]}'
                            v.value = f'STMT_{name_map[n]}'
                            found = True
                    if not found:
                        name_map[v] = index
                        index += 1
                        for r in v.referred_from:
                            r.abstracted = True
                            r.value = f'STMT_{name_map[v]}'
                        v.value = f'STMT_{name_map[v]}'
                for v in after.stmts:
                    if len(refer_to) > 0:
                        continue
                    else:
                        found = False
                        for n in name_map:
                            if TemplateNode.abstract_compare(v, n):
                                v.value = f'STMT_{name_map[n]}'
                                found = True
                        if not found:
                            name_map[v] = index
                            index += 1
                            v.value = f'STMT_{name_map[v]}'
            else:
                before = fix_template.before
                after = fix_template.after
                for v in before.stmts:
                    v.abstracted = True
                    v.value = 'STMT'
                for v in after.stmts:
                    v.abstracted = True
                    v.value = 'STMT'

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
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type:
            return False
        for ca in a.children:
            if ca not in b.children:
                return False
            for an in a.children[ca]:
                found = False
                paired_b = []
                for bi, bn in enumerate(b.children[ca]):
                    if bi in paired_b:
                        continue
                    if an.base_type not in ['Variable', 'Op', 'Builtin', 'Module', 'Literal', 'Attribute'] and self.include_compare(an, bn):
                        found = True
                        paired_b.append(bi)
                        break
                if not found:
                    return False
        return True


    def _cut_same_nodes(self, before_tree, after_tree, order):
        if before_tree == None or after_tree == None:
            return before_tree, after_tree, order
        changed = True
        while(changed):
            changed = False
            before_leaf_paths = before_tree.get_leaf_paths()
            after_leaf_paths = after_tree.get_leaf_paths()
            for bn in before_leaf_paths:
                if bn.base_type == 'Root':
                    continue
                for an in after_leaf_paths:
                    if an.base_type == 'Root':
                        continue
                    if TemplateNode.compare(an, bn) and TemplateTree.compare_leaf_path(before_leaf_paths[bn], after_leaf_paths[an]):
                        if bn.parent != None and bn.parent.type == 'Root' and order != None:
                            index = bn.parent.children['body'].index(bn)
                            new_order = []
                            for o in order['before']:
                                if o.startswith('Partially') and int(o.replace('Partially-', '')) > index:
                                    new_order.append('Partially-{}'.format(int(o.replace('Partially-', '')) - 1))
                                elif o.startswith('Partially') and int(o.replace('Partially-', '')) == index:
                                    pass
                                else:
                                    new_order.append(o)
                            order['before'] = new_order
                        if an.parent != None and an.parent.type == 'Root' and order != None:
                            index = an.parent.children['body'].index(an)
                            new_order = []
                            for o in order['after']:
                                if o.startswith('Partially') and int(o.replace('Partially-', '')) > index:
                                    new_order.append('Partially-{}'.format(int(o.replace('Partially-', '')) - 1))
                                elif o.startswith('Partially') and int(o.replace('Partially-', '')) == index:
                                    pass
                                else:
                                    new_order.append(o)
                            order['after'] = new_order
                        before_tree.remove(bn)
                        after_tree.remove(an)
                        changed = True
                        break
        
        if 'body' not in before_tree.root.children or len(before_tree.root.children['body']) == 0:
            before_tree = None
        if 'body' not in after_tree.root.children or len(after_tree.root.children['body']) == 0:
            after_tree = None



        return before_tree, after_tree, order

    


    def _process_replaced(self, pair):
        # In case the two partial trees are totally the same
        if len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0:
            partial_before_tree = TemplateTree()
            partial_before_tree.build(pair.status['Replaced']['before']['Partially'], partial = True)
            partial_after_tree = TemplateTree()
            partial_after_tree.build(pair.status['Replaced']['after']['Partially'], partial = True)
            partial_before_tree, partial_after_tree, pair.status['order'] = self._cut_same_nodes(partial_before_tree, partial_after_tree, pair.status['order'])
            if partial_before_tree == None and partial_after_tree == None:
                partial_empty = True
            else:
                partial_empty = False

        # Classify change pairs into Inserted, Shuffle and Replaced templates
        # Shuffle templates require no partially changed statements
        if len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0 and not partial_empty:
            # Check Insert, Add, Remove pattern
            if len(pair.status['Replaced']['before']['Partially']) > 0 and len(pair.status['Replaced']['after']['Partially']) > 0 and partial_before_tree != None and partial_after_tree != None:
                added = True
                removed = True
                for i, an in enumerate(partial_after_tree.root.children['body']):
                    if not self.include_compare(partial_before_tree.root.children['body'][i], an):
                        added = False
                    if not self.include_compare(an, partial_before_tree.root.children['body'][i]):
                        removed = False
                    if not added and not removed:
                        break
            elif partial_before_tree == None and partial_after_tree != None:
                added = True
                removed = False
            elif partial_after_tree == None and partial_before_tree != None:
                added = False
                removed = True
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
                    if partial_before_tree != None:
                        before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    else:
                        before_tree = totally_before_tree
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    template = FixTemplate('Insert', before_tree, after_tree)
                    template.add_instance(pair)
                    return template
                else:
                    if partial_before_tree != None:
                        before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    else:
                        before_tree = totally_before_tree
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
                if partial_before_tree != None:
                    before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                else:
                    before_tree = totally_before_tree
                if partial_after_tree != None:
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                else:
                    after_tree = totally_after_tree
                template = FixTemplate('Replace', before_tree, after_tree)
                template.add_instance(pair)
                return template
        else:
            before_tree = TemplateTree()
            before_tree.build(pair.status['Replaced']['before']['Totally'])
            after_tree = TemplateTree()
            after_tree.build(pair.status['Replaced']['after']['Totally'])
            if TemplateTree.compare(before_tree, after_tree):
                return None
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


    def abstract_node(self, a, b):
        if a.type == b.type and a.value == b.value and a.ast_type == b.ast_type:
            if a.value != None:
                a.value = 'ABSTRACTED'
                b.value = 'ABSTRACTED'
                a.value_abstracted = True
                b.value_abstracted = True
                
            for c in a.children:
                if c in b.children:
                    for i, n in enumerate(a.children[c]):
                        if i < len(b.children[c]):
                            a.children[c][i], b.children[c][i] = self.abstract_node(n, b.children[c][i])


        return a, b

    def abstract_templates(self):
        for c in self.fix_template:
            templates = self.fix_template[c]
            new_templates = []
            for t in templates:
                t.before, t.after, _ = self._cut_same_nodes(t.before, t.after, None)
                if t.before == None and t.after == None:
                    pass
                elif t.before == None or t.after == None:
                    new_templates.append(t)
                else:
                    for i, bn in enumerate(t.before.root.children['body']):
                        if i < len(t.after.root.children['body']):
                            t.before.root.children['body'][i], t.after.root.children['body'][i] = self.abstract_node(bn, t.after.root.children['body'][i])
                    new_templates.append(t)
            self.fix_template[c] = new_templates
    

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
                                if template != None:
                                    self.fix_template[template.action].append(template)
        self.clean()
        self.abstract_templates()
        self.assign_ids()
        #self.ori_template = copy.deepcopy(self.fix_template)


    def assign_ids(self):
        for c in self.fix_template:
            for t in self.fix_template[c]:
                t.id = self.index
                self.id2template[self.index] = t
                self.index += 1   

    def clean(self):
        # Remove those could not be fix templates
        num = 0 
        # Case 1: Only add/remove a whole function or class
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
        # Case 2: Before and After tree are totally the same
        for c in self.fix_template:
            removed = []
            for t in self.fix_template[c]:
                if TemplateTree.compare(t.before, t.after):
                    removed.append(t)
            for r in removed:
                self.fix_template[c].remove(r)
            num += len(removed)
        # Case 3: Only contain import statements
        for c in self.fix_template:
            removed = []
            for t in self.fix_template[c]:
                found = True
                if t.before != None:
                    for n in t.before.root.children['body']:
                        if n.type not in ['ImportFrom', 'Import']:
                            found = False
                            break
                if found and t.after != None:
                    for n in t.after.root.children['body']:
                        if n.type not in ['ImportFrom', 'Import']:
                            found = False
                            break
                if found:
                    removed.append(t)
            for r in removed:
                self.fix_template[c].remove(r)
            num += len(removed)

        print('Cleaned {} templates.'.format(num))


    def print_info(self, templates = None):
        if templates == None:
            print('Information of fix templates:')
            for c in self.fix_template:
                print(c, len(self.fix_template[c]))

            print('Total: {} templates.'.format(len(self.id2template)))     
        else:
            num = {}
            for t in templates:
                if len(t.instances) not in num:
                    num[len(t.instances)] = 1
                else:
                    num[len(t.instances)] += 1

            sorted_num = sorted(list(num.keys()), reverse = True)
            
            print('Information of clustered fix templates:')
            for n in sorted_num:
                print('{} instances: {}'.format(n, num[n]))

    def value_abstract_from_nodes(self, a, b):
        if a.type == b.type:
            newnode = TemplateNode(a.base_type)
            newnode.type = a.type
            if a.value != b.value:
                newnode.value = 'ABSTRACTED'
                newnode.value_abstracted = True
            else:
                newnode.value = a.value
            for c in a.children:
                newnode.children[c] = []
                for i, an in enumerate(a.children[c]):
                    child = self.value_abstract_from_nodes(a.children[c][i], b.children[c][i])
                    child.parent = newnode
                    child.parent_relation = c
                    newnode.children[c].append(child)
            return newnode
        else:
            raise ValueError('Cannot abstract the values of two nodes with different types.')
            

    def abstract_from_nodes(self, a, b):
        if a.type == b.type and not a.type_abstracted and not b.type_abstracted:
            newnode = TemplateNode(a.base_type)
            newnode.type = a.type
            if len(a.children) == len(b.children) and len(a.children) == 0:
                if a.value == b.value and not a.value_abstracted and not b.value_abstracted:
                    newnode.value = a.value
                else:
                    newnode.value = 'ABSTRACTED'
                    newnode.value_abstracted = True
                return newnode
            else:
                if a.value != b.value:
                    newnode.value = 'ABSTRACTED'
                    newnode.value_abstracted = True
                for c in a.children:
                    if c not in b.children or len(a.children[c]) != len(b.children[c]):
                        newnode.type_abstracted = True
                        return newnode
                for c in a.children:
                    newnode.children[c] = []
                    for i in range(0, len(a.children[c])):
                        newnode.children[c].append(self.abstract_from_nodes(a.children[c][i], b.children[c][i])) 
                return newnode
        elif a.type == b.type:
            if a.type_abstracted:
                newnode = copy.deepcopy(a)
                return newnode
            elif b.type_abstracted:
                newnode = copy.deepcopy(b)
                return newnode
        elif a.base_type == b.base_type and a.base_type not in ['Expr', 'Stmt']:
            newnode = TemplateNode(a.base_type)
            newnode.type = a.base_type
            newnode.type_abstracted = True
            return newnode
        else:
            if a.type != 'Stmt'and b.type != 'Stmt':
                newnode = TemplateNode('Expr')
                newnode.type = 'Expr'
                newnode.type_abstracted = True
                return newnode
            else:
                newnode = TemplateNode('Stmt')
                mewnode.type = 'Stmt'
                newnode.type_abstracted = True
                return newnode


    def merge(self, a, b):
        newbefore = None
        newafter = None
        # Handle Before tree
        if TemplateTree.compare(a.before, b.before):
            newbefore = copy.deepcopy(a.before)
        elif a.before == None and b.before == None:
            newbefore = None
        else:
            newbefore = TemplateTree()
            newbefore.root = self.abstract_from_nodes(a.before.root, b.before.root)
            newbefore.collect_special_nodes()
        
        # Hanle After tree
        if TemplateTree.compare(a.after, b.after):
            newafter = copy.deepcopy(a.after)
        elif a.after == None and b.after == None:
            newafter = None
        else:
            newafter = TemplateTree()
            newafter.root = self.abstract_from_nodes(a.after.root, b.after.root)
            newafter.collect_special_nodes()
        
        template = FixTemplate(a.action, newbefore, newafter)
        template.merge([a, b])
        if (newbefore != None and newbefore.check_abstracted()) or (newafter != None and newafter.check_abstracted()):
            template.abstracted = True
        template.id = self.index
        self.index += 1
        self.id2template[template.id] = template
        return template

    def initialize_distances(self, templates):
        distances = {}
        for i, t in enumerate(templates):
            for j in range(i+1, len(templates)):
                if t not in distances:
                    distances[t] = {}
                if templates[j] not in distances:
                    distances[templates[j]] = {}
                if not self.is_mergable(t, templates[j]):
                    distances[t][templates[j]] = -9999
                    distances[templates[j]][t] = -9999
                else:
                    distances[t][templates[j]] = FixTemplate.get_distance(t, templates[j])
                    distances[templates[j]][t] = distances[t][templates[j]]

        return distances

    def add_distances(self, distances, template, templates):
        distances[template] = {}
        for t in templates:
            if not self.is_mergable(t, template):
                distances[t][template] = -9999
                distances[template][t] = -9999
            else:
                distances[t][template] = FixTemplate.get_distance(t, template)
                distances[template][t] = distances[t][template]

        return distances

    def get_max_distance(self, distances, templates):
        max_distance = -1
        max_pair = []
        for i, t in enumerate(templates):
            for j in range(i+1, len(templates)):
                if distances[t][templates[j]] > max_distance:
                    max_distance = distances[t][templates[j]]
                    max_pair = [t, templates[j]]
        return *max_pair, max_distance

    def select_most_abstracted_tree(self, trees):
        max_num = -9999
        max_tree = None
        for t in trees:
            if t == None:
                continue
            abs_num = t.get_abstracted_num()
            if abs_num > max_num:
                max_num = abs_num
                max_tree = t

        return max_tree

    def merge_same_templates(self, distances, templates):
        changed = True
        while(changed):
            changed = False
            merged = {}
            for i in range(0, len(templates)):
                if i in merged:
                    continue
                same = []
                for j in range(i+1, len(templates)):
                    if distances[templates[i]][templates[j]] == 1:
                        same.append(j)
                if len(same) > 0:
                    merged[i] = 1
                    for k in same:
                        merged[k] = 1
                    template = FixTemplate(templates[i].action, self.select_most_abstracted_tree([templates[k].before for k in same + [i]]), self.select_most_abstracted_tree([templates[k].after for k in same + [i]]))
                    template.merge([templates[k] for k in same + [i]])
                    template.id = self.index
                    self.id2template[template.id] = template
                    self.index += 1
                    for t in template.former_templates:
                        templates.remove(self.id2template[t])
                    distances = self.add_distances(distances, template, templates)
                    templates.append(template)
                    changed = True
                    break
        
        return distances, templates

    def merge_same_structure_templates(self, distances, templates):
        changed = True
        while(changed):
            changed = False
            merged = {}
            for i in range(0, len(templates)):
                if i in merged:
                    continue
                same = []
                for j in range(i+1, len(templates)):
                    if self.is_same_structure(templates[i], templates[j]):
                        same.append(j)
                if len(same) > 0:
                    merged[i] = 1
                    for k in same:
                        merged[k] = 1
                    if templates[i].before != None:
                        newbefore_root = templates[i].before.root
                    else:
                        newbefore_root = None
                    if templates[i].after != None:
                        newafter_root = templates[i].after.root
                    else:
                        newafter_root = None
                    for k in same:
                        if newbefore_root != None:
                            newbefore_root = self.value_abstract_from_nodes(newbefore_root, templates[k].before.root)
                        if newafter_root != None:
                            newafter_root = self.value_abstract_from_nodes(newafter_root, templates[k].after.root)
                    if newbefore_root != None:
                        newbefore = TemplateTree()
                        newbefore.root = newbefore_root
                        newbefore.collect_special_nodes()
                    else:
                        newbefore = None
                    if newafter_root != None:
                        newafter = TemplateTree()
                        newafter.root = newafter_root
                        newafter.collect_special_nodes()
                    else:
                        newafter = None
                    template = FixTemplate(templates[i].action, newbefore, newafter)
                    template.merge([templates[k] for k in same + [i]])
                    template.id = self.index
                    self.id2template[template.id] = template
                    self.index += 1
                    for t in template.former_templates:
                        templates.remove(self.id2template[t])
                    distances = self.add_distances(distances, template, templates)
                    templates.append(template)
                    changed = True
                    break
        
        return distances, templates


    def is_same_structure(self, a, b):
        if not self.is_mergable(a, b):
            return False
        if (a.before == b.before or TemplateNode.value_abstract_compare(a.before.root, b.before.root)) and (a.after == b.after or TemplateNode.value_abstract_compare(a.after.root, b.after.root)):
            return True
        else:
            return False


    def is_mergable(self, a, b):
        if (a.before == None and b.before != None) or\
        (a.before != None and b.before == None) or\
        (a.after == None and b.after != None) or\
        (a.after != None and b.after == None):
            return False

        return True


    def get_topn_templates(self, topn, templates):
        num = {}
        for t in templates:
            if len(t.instances) not in num:
                num[len(t.instances)] = [t]
            else:
                num[len(t.instances)].append(t)
        
        nums = sorted(list(num.keys()), reverse = True)
        results = []
        total = 0
        for n in nums:
            for t in num[n]:
                results.append(t)
                total += 1
                if total >= topn:
                    return results
        
        return results

    def draw_templates(self, templates, path, dump_instances = True):
        for t in templates:
            t.draw(filerepo = path)
            if dump_instances:
                text = ""
                for i in t.instances:
                    text += '========================{}:{}========================\n{}\n=================================================================\n'.format(i.metadata['repo'], i.metadata['commit'], i.metadata['content'])
                with open(os.path.join(path, 'FIX_TEMPLATE_{}_INSTANCES.txt'.format(t.id)), 'w', encoding = 'utf-8') as f:
                    f.write(text)


    def mine(self, n):
        # n - Number of templates finally left
        for c in self.fix_template:
            if c != 'Replace':
                continue
            templates = self.fix_template[c]
            distances = self.initialize_distances(templates)
            print('Original:', len(templates))
            distances, templates = self.merge_same_templates(distances, templates)
            print('After merge same:', len(templates))
            distances, templates = self.merge_same_structure_templates(distances, templates)
            print('After merge same structure:', len(templates))
            self.print_info(templates)
            top_templates = self.get_topn_templates(n, templates)
            self.draw_templates(top_templates, '/data/project/ypeng/typeerror/figures')
            exit()
            '''
            while (len(templates) > n):
                print('Before merging: {}'.format(len(templates)))
                distances, templates = self.merge_same_templates(distances, templates)
                print('After merging: {}'.format(len(templates)))
                a, b, max_distance = self.get_max_distance(distances, templates)
                if max_distance < 0.5:
                    break
                new = self.merge(a, b)
                templates.remove(a)
                templates.remove(b)
                distances = self.add_distances(distances, new, templates)
                templates.append(new)
            self.print_info(templates)
            top_templates = self.get_topn_templates(n, templates)
            self.draw_templates(top_templates, '/data/project/ypeng/typeerror/figures')
            #a.draw(filerepo = '/data/project/ypeng/typeerror/figures', draw_instance = True)
            #b.draw(filerepo = '/data/project/ypeng/typeerror/figures', draw_instance = True)
            #new.draw(filerepo = '/data/project/ypeng/typeerror/figures', draw_instance = True)
            #print('{} templates remain after clustering.'.format(len(templates)))
            exit()
            '''



def test_one():
    sig = 'Rapptz/discord.py:8d52ddaff6345507b965559c7913d575a4aad020'
    a = ASTCompare()
    change_pairs = a.compare_one('combined_commits_contents.json', sig.split(':')[0], sig.split(':')[1])
    miner = FixMiner()
    miner.build_templates(change_pairs)
    miner.print_info()
    for i in miner.id2template:
        miner.id2template[i].draw(filerepo = '/data/project/ypeng/typeerror/figures')


def main():
    a = ASTCompare()
    change_pairs = a.compare_projects('combined_commits_contents.json')
    miner = FixMiner()
    miner.build_templates(change_pairs)
    miner.print_info()
    miner.mine(10)

        
        



if __name__ == '__main__':
    #test_one()
    main()
    #print(FixTemplate.get_distance(miner.fix_template['Add'][0], miner.fix_template['Add'][1]), FixTemplate.get_distance(miner.fix_template['Add'][1], miner.fix_template['Add'][0]))
    


        
        
                

                





    