import json
import os
import ast
from graphviz import Digraph
import logging



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
    ast.Attribute, ast.Subscript, ast.Starred, ast.Name, ast.List, ast.Tuple, ast.Slice
]

elem_types = {
    ast.And: 'And', ast.Or: 'Or', ast.Add: 'Add', ast.Sub: 'Sub', ast.Mult: 'Mult', ast.MatMult: 'MatMult', ast.Div: 'Div', ast.Mod: 'Mod',
    ast.Pow: 'Pow', ast.LShift: 'LShift', ast.RShift: 'RShift', ast.BitOr: 'BitOr', ast.BitXor: 'BitXor', ast.BitAnd: 'BitAnd', ast.FloorDiv: 'FloorDiv',
    ast.Invert: 'Invert', ast.Not: 'Not', ast.UAdd: 'UAdd', ast.USub: 'USub', ast.Eq: 'Eq', ast.NotEq: 'NotEq', ast.Lt: 'Lt', ast.LtE: 'LtE',
    ast.Gt: 'Gt', ast.GtE: 'GtE', ast.Is: 'Is', ast.IsNot: 'IsNot', ast.In: 'In', ast.NotIn: 'NotIn'
}





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
            field += ' {}:{}'.format(n, str(self.field_children[n]))

        if not self.totally_changed:
            name = '{}-({},{}) | {}'.format(str(type(self.node).__name__), self.lineno, self.end_lineno, self.change_lines)
        else:
            name = '{}-({},{})'.format(str(type(self.node).__name__), self.lineno, self.end_lineno)
        if len(field) > 0:
            name += f'\n{field}'
        return name


        



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
        self.stmtchanges = []
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
            return None
        
        return self.compare_change_tree(before_trees, after_trees)
        

    
    def compare_commit(self, commitinfo):
        for f in commitinfo:
            beforefile, afterfile = commitinfo[f]['files']
            try:
                self.beforeroot = ast.parse(open(beforefile, 'r').read())
                self.afterroot = ast.parse(open(afterfile, 'r').read())
            except Exception as e:
                print(f'Cannot parse the source files, reason:{e}')
                continue
            for l in commitinfo[f]:
                if l == 'files':
                    continue
                print(f'+++++++Handling location {l}')
                for commit in commitinfo[f][l]:
                    change_pair = self.compare_loc(commit['lines'], commit['content'])
                    if change_pair:
                        change_pair.draw()
                    


    def compare_projects(self, datafile):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        for r in data:
            for c in data[r]:
                print(f'Handling commit {c} in {r}')
                self.compare_commit(data[r][c])
                





class FixMiner(object):
    def __init__(self):
        pass



if __name__ == '__main__':
    a = ASTCompare()
    a.compare_projects('popular_github_projects_with_commits_v2_contents.json')


        
        
                

                





    