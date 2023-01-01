import json
import os
import ast
import re
import copy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings



class ChangeNode(object):
    def __init__(self, node, lineno, end_lineno, change_lines, raw_change_lines, ctx = None):
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
        self.ctx = ctx
        self.partial = False

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
    
    def gen_children_as_ast(self):
        for n in ast.iter_child_nodes(self.node):
            lineno, end_lineno = ChangeTree.get_loc(n)
            if type(n) in elem_types:
                for name, value in ast.iter_fields(self.node):
                    if isinstance(value, list) and n in value:
                        self.add_field_children(name, elem_types[type(n)])
                    elif n == value:
                        self.add_field_children(name, elem_types[type(n)])
            elif type(n) not in [ast.Load, ast.Store, ast.Del]:
                c_node = ChangeNode(n, lineno, end_lineno, [], [])
                c_node.gen_children_as_ast()
                self.add_children(c_node)
                c_node.set_parent(self)
        for name, value in ast.iter_fields(self.node):
            if not isinstance(value, list) and not issubclass(type(value), ast.AST) and name not in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment'] and (name == 'value' or (name != 'value' and value != None)):
                self.add_field_children(name, value)
            elif isinstance(value, list):
                for v in value:
                    if not issubclass(type(v), ast.AST) and name not in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment'] and (name == 'value' or (name != 'value' and value != None)):
                        self.add_field_children(name, v)
            elif name == 'ctx':
                if type(value) == ast.Load:
                    self.ctx = 'Read'
                elif type(value) == ast.Store:
                    self.ctx = 'Write'
                elif type(value) == ast.Del:
                    self.ctx = 'Delete'
            
                


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
    def __init__(self, root, before, change_lines, raw_change_lines, context = False):
        self.root = root
        self.change_lines = change_lines
        self.raw_change_lines = raw_change_lines
        self.uppest_totally_changed_stmts = []
        self.deepest_changed_stmts = []
        self.deepest_partially_changed_stmts = []
        self.before = before
    
    @staticmethod
    def get_loc(node):
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

    @staticmethod
    def build_before_and_after_contexts(change_nodes):
        before_contexts = []
        after_contexts = []
        for n in change_nodes:
            if n.parent == None:
                continue
            ast_parent = n.parent.node
            for cn in ast.iter_child_nodes(ast_parent):
                lineno, end_lineno = ChangeTree.get_loc(cn)
                max_line = max(n.raw_change_lines)
                min_line = min(n.raw_change_lines)
                if lineno > max_line and lineno not in n.parent.raw_change_lines:
                    c_node = ChangeNode(cn, lineno, end_lineno, [], [])
                    if c_node.type == 'stmt':
                        c_node.gen_children_as_ast()
                        after_contexts.append(c_node)
                elif end_lineno < min_line and lineno not in n.parent.raw_change_lines:
                    c_node = ChangeNode(cn, lineno, end_lineno, [], [])
                    if c_node.type == 'stmt':
                        c_node.gen_children_as_ast()
                        before_contexts.append(c_node)

        final_before_contexts = []
        final_after_contexts = []
        for c in before_contexts:
            same = False
            for f in final_before_contexts:
                if ChangeNode.compare(c, f):
                    same = True
                    break
            if not same:
                final_before_contexts.append(c)
        for c in after_contexts:
            same = False
            for f in final_after_contexts:
                if ChangeNode.compare(c, f):
                    same = True
                    break
            if not same:
                final_after_contexts.append(c)


        return before_contexts, after_contexts

    def check_comment(self, node):
        if type(node) == ast.Expr and type(node.value) ==ast.Constant and isinstance(node.value.value, str):
            return True
        else:
            return False

    def prune_empty_stmts(self):
        changed = False
        while(changed):
            changed = False
            nodes = [self.root]
            while(len(nodes) > 0):
                node = nodes[0]
                nodes = nodes[1:]
                if node.type != 'stmt':
                    continue
                else:
                    if len(node.stmt_children) == 0 and len(node.expr_children) == 0 and len(node.field_children) == 0:
                        if node.parent != None:
                            node.parent.stmt_children.remove(node)
                            changed = True


    def build(self):
        should_remove = False
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            for n in ast.iter_child_nodes(node.node):
                if self.check_comment(n):
                    continue
                lines = []
                lineno, end_lineno = ChangeTree.get_loc(n)
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
                if not isinstance(value, list) and not issubclass(type(value), ast.AST) and name not in ['ctx', 'lineno', 'end_lineno', 'col_offset', 'end_col_offset', 'type_comment'] and (name == 'value' or (name != 'value' and value != None)):
                    node.add_field_children(name, value)
                elif isinstance(value, list):
                    for v in value:
                        if not issubclass(type(v), ast.AST) and name not in ['ctx', 'lineno', 'end_lineno', 'col_offset', 'end_col_offset', 'type_comment'] and (name == 'value' or (name != 'value' and value != None)):
                            node.add_field_children(name, v)
                elif name == 'ctx':
                    if type(value) == ast.Load:
                        node.ctx = 'Read'
                    elif type(value) == ast.Store:
                        node.ctx = 'Write'
                    elif type(value) == ast.Del:
                        node.ctx = 'Delete'

        self.prune_empty_stmts()
        if len(self.root.stmt_children) > 0:
            self.analyze_statements()
        else:
            self.analyze_statements()
            should_remove = True
        
        return should_remove
        
    def analyze_statements(self):
        nodes = [self.root]
        while(len(nodes) != 0):
            node = nodes[0]
            nodes = nodes[1:]
            if (len(node.stmt_children) == 0 or len(node.expr_children) > 0) and node.type == 'stmt':
                self.deepest_changed_stmts.append(node)
            elif node.type == 'stmt' and not node.totally_changed:
                include = True
                changelines = []
                expr_change_lines = []
                for c in node.stmt_children:
                    if not c.totally_changed:
                        include = False
                        break
                    else:
                        changelines += c.change_lines
                for c in node.expr_children:
                    expr_change_lines += c.change_lines
                if include and len(set(changelines)) < len(set(node.change_lines)) and len(expr_change_lines) > 0:
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