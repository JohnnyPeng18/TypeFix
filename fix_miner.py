import json
import os
import ast
from graphviz import Digraph



stmt_types = [
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Return, ast.Delete, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For,
    ast.AsyncFor, ast.While, ast.If, ast.With, ast.AsyncWith, ast.Match, ast.Raise, ast.Try, ast.Assert, ast.Import, ast.ImportFrom,
    ast.Global, ast.Nonlocal, ast.Expr, ast.Pass, ast.Continue, ast.Break
]
expr_types = [
    ast.BoolOp, ast.NamedExpr, ast.BinOp, ast.UnaryOp, ast.Lambda, ast.IfExp, ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.Await, ast.Yield, ast.YieldFrom, ast.Compare, ast.Call, ast.FormattedValue, ast.JoinedStr, ast.Constant,
    ast.Attribute, ast.Subscript, ast.Starred, ast.Name, ast.List, ast.Tuple, ast.Slice
]

class ChangeNode(object):
    def __init__(self, node, change_lines):
        self.node = node
        self.change_lines = change_lines
        self.stmt_children = []
        self.expr_children = []
        self.parent = None
        self.set_type()
        self.status = []
        self.changed_fields = []
        self.check_change()

    def check_change(self):
        for i in range(self.node.lineno, self.node.end_lineno + 1):
            if i not in self.change_lines:
                self.totally_changed = False
                return None
        
        self.totally_changed = True


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
        if '_Parent' in status and status.replace('_Parent', '') in self.parent.status:
            pass
        else:
            self.parent.set_status(status)
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

    def get_all_children(self):
        nodes = self.stmt_children
        children = []
        for n in nodes:
            children += n.get_all_children()
        
        return nodes + children

    def resolve_name(self):
        if self.type == 'stmt':
            name = 'STMT:{}-({},{})-{}'.format(str(type(self.node)), self.node.lineno, self.node.end_lineno, self.change_lines)
        else:
            name = 'EXPR:{}-({},{})-{}'.format(str(type(self.node)), self.node.lineno, self.node.end_lineno, self.change_lines)
        return name


        



class ChangeTree(object):
    def __init__(self, root, change_lines):
        self.root = root
        self.change_lines = change_lines
        self.uppest_totally_changed_stmts = []
        self.deepest_changed_stmts = []
        self.deepest_partially_changed_stmts = []

    def build(self):
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            for n in ast.iter_child_nodes(node.node):
                lines = []
                for l in self.change_lines:
                    if l in range(n.lineno, n.end_lineno + 1):
                        lines.append(l)
                if len(lines) != 0:
                    c_node = ChangeNode(n, lines)
                    node.add_children(c_node)
                    c_node.parent = node
                    nodes.append(c_node)

        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            if len(node.stmt_children) == 0 and node.type == 'stmt':
                self.deepest_changed_stmts.append(node)
            elif node.type == 'stmt' and len(node.stmt_children) > 0:
                nodes.append(node)

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
                if n.has_parent(m):
                    included = True
                    break
            if not included:
                self.deepest_partially_changed_stmts(n)

    def draw(self, filename = None):
        if not filename:
            filename = 'CHANGE_TREE'
        f = Digraph("Change Tree", filename = filename)
        added = []

        f.attr('node', shape = 'box', color = 'darkorange')
        for n in self.uppest_totally_changed_stmts:
            f.node(n.resolve_name())
            added.append(n.resolve_name())
        
        f.attr('node', shape = 'box', color = 'darkgoldenrod1')
        for n in self.deepest_partially_changed_stmts:
            f.node(n.resolve_name())
            added.append(n.resolve_name())
        
        f.attr('node', shape = 'box')
        for n in self.uppest_totally_changed_stmts:
            for c in n.get_all_children():
                f.node(c.resolve_name())
                added.append(c.resolve_name())
        
        f.attr('node', shape = 'ellipse')
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            for n in node.expr_children:
                f.node(n.resolve_name())
                added.append(n.resolve_name())
            nodes += node.stmt_children

        f.attr('node', shape = 'note')
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            if node.resolve_name() not in added:
                f.node(node.resolve_name())
                added.append(node.resolve_name())
            nodes += node.stmt_children
        
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            for n in node.stmt_children:
                f.edge(node.resolve_name(), n.resolve_name())
            for n in node.expr_children:
                f.edge(node.resolve_name(), n.resolve_name())
            nodes += node.stmt_children
            nodes += node.expr_children

        f.render(filename = filename, view = False)

class ChangePair(object):
    def __init__(self, before, after, status):
        self.before = before
        self.after = after
        self.status = status

            




class ASTCompare(object):
    def __init__(self):
        self.stmtchanges = []
        self.beforeroot = None
        self.afterroot = None

    def build_change_tree(self, root, change_lines):
        nodes = {}
        change_trees = []
        for l in change_lines:
            for n in root.body:
                if l in range(n.lineno, n.end_lineno + 1):
                    if n not in nodes:
                        nodes[n] = []
                    nodes[n].append(l)
        
        for n in nodes:
            c_node = ChangeNode(n, nodes[n])
            c_tree = ChangeTree(c_node, nodes[n])
            c_tree.build()
            change_trees.append(c_tree)
        
        return change_trees


    def compare_change_tree(self, before_trees, after_trees):
        change_status = {'Added': {'Totally': [], 'Partially': []}, 'Removed': {'Totally': [], 'Partially': []}, 'Replaced': 'before': {'Totally': [], 'Partially': []}, 'after': {'Totally': [], 'Partially': []}}
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
        before_trees = self.build_change_tree(self.beforeroot, before_change_lines)
        after_trees = self.build_change_tree(self.afterroot, after_change_lines)
        
        return self.compare_change_tree(before_trees, after_trees)
        

    
    def compare_commit(self, commitinfo):
        for f in commitinfo:
            beforefile, afterfile = commitinfo[f]['files']
            self.beforeroot = ast.parse(open(beforefile, 'r').read())
            self.afterroot = ast.parse(open(afterfile, 'r').read())




class FixMiner(object):
    def __init__(self):
        pass


        
        
                

                





    