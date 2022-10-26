import json
import os
import ast
import re
from graphviz import Digraph
from __init__ import logger



stmt_types = [
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Return, ast.Delete, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For,
    ast.AsyncFor, ast.While, ast.If, ast.With, ast.AsyncWith, ast.Raise, ast.Try, ast.Assert, ast.Import, ast.ImportFrom,
    ast.Global, ast.Nonlocal, ast.Expr, ast.Pass, ast.Continue, ast.Break, ast.ExceptHandler
]
if hasattr(ast, 'Match'):
    stmt_types.append(ast.Match)

expr_types = [
    ast.BoolOp, ast.NamedExpr, ast.BinOp, ast.UnaryOp, ast.Lambda, ast.IfExp, ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.Await, ast.Yield, ast.YieldFrom, ast.Compare, ast.Call, ast.FormattedValue, ast.JoinedStr, ast.Constant,
    ast.Attribute, ast.Subscript, ast.Starred, ast.Name, ast.List, ast.Tuple, ast.Slice, ast.arguments, ast.arg, ast.keyword, ast.withitem,
    ast.alias, ast.comprehension
]
if hasattr(ast, 'Macth'):
    expr_types += [
        ast.match_case, ast.MatchValue, ast.MatchSingleton, ast.MatchSequence, ast.MatchMapping, ast.MatchClass, ast.MatchStar, ast.MatchAs, ast.MatchOr
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





class ChangeNode(object):
    def __init__(self, node, lineno, end_lineno, change_lines):
        self.node = node
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.change_lines = change_lines
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
            if i not in self.change_lines:
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
    def __init__(self, root, before, change_lines):
        self.root = root
        self.change_lines = change_lines
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
                if len(lines) != 0:
                    c_node = ChangeNode(n, lineno, end_lineno, lines)
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
            if len(node.stmt_children) == 0 and node.type == 'stmt':
                self.deepest_changed_stmts.append(node)
            elif node.type == 'stmt' and len(node.stmt_children) > 0:
                nodes += node.stmt_children

        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
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
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
        else:
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
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

    def build_change_tree(self, root, before, change_lines):
        nodes = {}
        change_trees = []
        for l in change_lines:
            for n in root.body:
                if l in range(n.lineno, n.end_lineno + 1):
                    if n not in nodes:
                        nodes[n] = []
                    nodes[n].append(l)
        
        for n in nodes:
            c_node = ChangeNode(n, n.lineno, n.end_lineno, nodes[n])
            c_tree = ChangeTree(c_node, before, nodes[n])
            c_tree.build()
            change_trees.append(c_tree)
        
        return change_trees


    def compare_change_tree(self, before_trees, after_trees):
        change_status = {'Added': {'Totally': [], 'Partially': []}, 'Removed': {'Totally': [], 'Partially': []}, 'Replaced': {'before': {'Totally': [], 'Partially': []}, 'after': {'Totally': [], 'Partially': []}}}
        if len(before_trees) == 0 and len(after_trees) == 0:
            raise ValueError('Change trees before and after the commit are both empty.')
        if len(before_trees) == 0:
            for a in after_trees:
                for s in a.uppest_totally_changed_stmts:
                    s.set_status('Added')
                    s.set_status_for_childrens('Added')
                    s.set_status_for_parent('Added_Parent')
                    change_status['Added']['Totally'].append(s)
                for s in a.deepest_partially_changed_stmts:
                    logger.warning('Unexpected partially added statements found.')
                    s.set_status('Added_Parent')
                    s.set_status_for_parent('Added_Parent')
                    change_status['Added']['Partially'].append(s)

        elif len(after_trees) == 0:
            for b in before_trees:
                for s in b.uppest_totally_changed_stmts:
                    s.set_status('Removed')
                    s.set_status_for_childrens('Removed')
                    s.set_status_for_parent('Removed_Parent')
                    change_status['Removed']['Totally'].append(s)
                for s in b.deepest_partially_changed_stmts:
                    logger.warning('Unexpected partially removed statements found.')
                    s.set_status('Removed_Parent')
                    s.set_status_for_parent('Removed_Parent')
                    change_status['Removed']['Partially'].append(s)
        
        else:
            for b in before_trees:
                for s in b.uppest_totally_changed_stmts:
                    s.set_status('Replaced')
                    s.set_status_for_childrens('Replaced')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['before']['Totally'].append(s)
                for s in b.deepest_partially_changed_stmts:
                    s.set_status('Replaced_Parent')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['before']['Partially'].append(s)
            for a in after_trees:
                for s in a.uppest_totally_changed_stmts:
                    s.set_status('Replaced')
                    s.set_status_for_childrens('Replaced')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['after']['Totally'].append(s)
                for s in a.deepest_partially_changed_stmts:
                    s.set_status('Replaced_Parent')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['after']['Partially'].append(s)
        
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
        after_change_lines = []
        for line in content.splitlines():
            if not line.startswith('-') and not line.startswith('+'):
                before_index += 1
                after_index += 1
            elif line.startswith('-'):
                before_change_lines.append(before_index)
                before_index += 1
            elif line.startswith('+'):
                after_change_lines.append(after_index)
                after_index += 1
        if before_index != lines[0] + lines[1] or after_index != lines[2] + lines[3]:
            raise ValueError('Line information does not match the change content.')
        before_trees = self.build_change_tree(self.beforeroot, True, before_change_lines)
        after_trees = self.build_change_tree(self.afterroot, False, after_change_lines)

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
                self.beforeroot = ast.parse(open(beforefile, 'r').read())
                self.afterroot = ast.parse(open(afterfile, 'r').read())
            except Exception as e:
                logger.error(f'Cannot parse the source files, reason:{e}')
                continue
            for l in commitinfo[f]:
                if l == 'files':
                    continue
                logger.info(f'+++++++Handling location {l}')
                change_pairs[f][l] = []
                for commit in commitinfo[f][l]:
                    change_pair = self.compare_loc(commit['lines'], commit['content'])
                    change_pairs[f][l].append(change_pair)
                    #if change_pair:
                    #    change_pair.draw()
        
        return change_pairs
                    


    def compare_projects(self, datafile):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        change_pairs = {}
        for r in tqdm(data, desc = 'Generating Change Pairs'):
            change_pairs[r] = {}
            for c in data[r]:
                logger.info(f'Handling commit {c} in {r}')
                change_pair[r][c] = self.compare_commit(data[r][c])
        
        return change_pairs


class TemplateNode(object):
    def __init__(self, nodetype):
        # Types:
        # Root - The root node of a template tree
        # Variable - Nodes representing variables
        # Op - Nodes representing operations
        # Literal - Node representing literals
        # Expr - Node representing expressions
        # Stmt - Node representing statements
        self.type = nodetype
        self.refer_to = []
        self.referred_from = []
        self.children = {}
        # Value must be None if there is any children
        self.value = None
        self.ast_type = None
    
    def build_from_stmt(self, stmt):
        self.type = 'Stmt'
        self.ast_type = type(stmt.node)
        for s in stmt.stmt_children:
            node = TemplateNode('Stmt')
            node.build_from_stmt(s)
            if s.parent_relation not in self.children:
                self.children[s.parent_relation] = [node]
            else:
                self.children[s.parent_relation].append(node)
        
        for e in stmt.expr_children:
            if type(e.node) != ast.arguments:
                node = TemplateNode('Expr')
                node.build_from_expr(e)
                if e.parent_relation not in self.children:
                    self.children[e.parent_relation] = [node]
                else:
                    self.children[e.parent_relation].append(node)
            else:
                for arg in e.expr_children:
                    node = TemplateNode('Expr')
                    node.build_from_expr(arg)
                    if arg.parent_relation not in self.children:
                        self.children[arg.parent_relation] = [node]
                    else:
                        self.children[arg.parent_relation].append(node)
    

    def build_from_expr(self, expr):
        self.type = 'Expr'
        self.ast_type = type(expr)
        if type(expr.node) == ast.Name:
            self.type = 'Variable'
            self.value = expr.field_children['id']

        elif type(expr.node) == ast.arg:
            self.type = 'Variable'
            self.value = expr.field_children['arg']
            
        elif type(expr.node) == ast.Attribute:
            self.type = 'Variable'

        elif type(expr.node) == ast.Constant:
            self.type = 'Literal':
            self.value = expr.field_children['value']
        elif type(expr) in [ast.BoolOp, ast.BinOp, ast.UnaryOp]:
            node = TemplateNode('Op')
            node.value = expr.field_children['op']
            self.children['op'] = [node]
        elif type(expr) == ast.Compare:
            if isinstance(expr.field_children['ops'], list):
                for o in expr.field_children['ops']:
                    node = TemplateNode('Op')
                    node.value = o
                    if 'op' not in self.children:
                        self.children['op'] = [node]
                    else:
                        self.children['op'].append(node)
            else:
                node = TemplateNode('Op')
                node.value = expr.field_children['ops']
                self.children['op'] = [node]
        
        for e in expr.expr_children:
            node = TemplateNode('Expr')
            node.build_from_expr(e)
            if e.parent_relation not in self.children:
                self.children[e.parent_relation] = [node]
            else:
                self.children[e.parent_relation].append(node)




class TemplateTree(object):
    def __init__(self, root):
        self.root = root
        self.variables = []
        self.literals = []
        self.ops = []
        self.exprs = []
        self.stmts = []

                

class FixTemplate(object):
    def __init__(self, action, before, after):
        # Actions:
        # Add - All original statements remains the same and only new statements added
        # Remove - No new statements added and some original code statements removed
        # Insert - All original statements remains with different locations and some new statements added
        # Shuffle - No new statements added but the order of original statements changed
        # Replace - Some original statements removed and new statements added
        self.action = action
        self.before = before
        self.after = after
        self.instances = []
    
    def add_instance(self, instance):
        if instance not in self.instances:
            self.instances.append(instance)

    def merge(self, fix_template):
        if isinstance(fix_template, FixTemplate) and self.action == fix_template.action and\
        ChangeNode.compare(self.before, fix_template.before) and ChangeNode.compare(self.after, fix_template.after):
            for i in fix_template.instances:
                if i not in self.instances:
                    self.instances.append(i)






class FixMiner(object):
    def __init__(self):
        self.fix_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}


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

    def _process_replaced(self, status, pair, mode = 'Totally'):
        pass

    def build_templates(self, change_pairs):
        for r in change_pairs:
            for c in change_pairs[r]:
                for f in change_pairs[r][c]:
                    for l in change_pairs[r][c][f]:
                        for pair in change_pairs[r][c][f][l]:
                            if len(pair.status['Added']['Totally']) > 0:
                                root = TemplateNode('Root')

                            if len(pair.status['Removed']['Totally']) > 0:
                                pass
                            if len(pair.status['Replaced']['Totally']) > 0:
                                pass
                            if len(pair.status['Replaced']['Partially']) > 0:
                                pass
                            



    def mine(self, change_pairs):
        pass



if __name__ == '__main__':
    a = ASTCompare()
    a.compare_projects('popular_github_projects_with_commits_v2_contents.json')


        
        
                

                





    