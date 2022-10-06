import json
import os
import ast



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
        self.status = 'New'
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
        



class ChangeTree(object):
    def __init__(self, root, change_lines):
        self.root = root
        self.change_lines = change_lines
        self.totally_changed_stmts = []
        self.deepest_changed_stmts = []

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
                self.totally_changed_stmts.append(node)
            else:
                nodes += node.stmt_children



class ChangePair(object):
    def __init__(self, before, after, before_lines, after_lines, status):
        self.before = before
        self.after = after
        self.before_lines = before_lines
        self.after_lines = after_lines
        self.status = status

            




class ASTCompare(object):
    def __init__(self):
        self.stmtchanges = []
        self.beforeroot = None
        self.afterroot = None
    

    def is_same_node(self, a, b):
        return ast.unparse(a.node) == ast.unparse(b.node)

    def is_similar_node(self, a, b):
        if type(a) != type(b):
            return False
        else:



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
        change_status = {'before': {}, 'after': {}}
        if len(before_trees) == 0:
            
        elif len(after_trees) == 0:
            pass

        for b_index, b in enumerate(before_trees):
            for a_index, a in enumerate(after_trees):
                if self.is_same_node(b, a):
                    if b_index not in change_status['before'] and a_index not in change_status['after']:
                        change_status['before'][b_index] = a_index
                        b.status = 'Same'
                        a.status = 'Same'
                        change_status['after'][a_index] = b_index
                else:
                    
        
        
        



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
        

    
    def compare_commit(self, commitinfo):
        for f in commitinfo:
            beforefile, afterfile = commitinfo[f]['files']
            self.beforeroot = ast.parse(open(beforefile, 'r').read())
            self.afterroot = ast.parse(open(afterfile, 'r').read())




class FixMiner(object):
    def __init__(self):
        pass


        
        
                

                





    