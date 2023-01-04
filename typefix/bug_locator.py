import os
import ast





class FunctionLocator(ast.NodeVisitor):
    def __init__(self):
        self.curnode = None
        self.relation = None
        self.find_body_index = False
    
    def visit_ClassDef(self, node):
        for l in self.lines:
            if l in range(node.lineno, node.end_lineno + 1):
                self.curnode = node
                break
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for l in self.lines:
            if l in range(node.lineno, node.end_lineno + 1):
                self.curnode = node
                break
        self.generic_visit(node)
        
    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_For(self, node):
        if self.find_body_index:
            found = True
            for l in self.lines:
                if l not in range(node.lineno, node.end_lineno + 1):
                    found = False
                    break
            if found:
                self.curnode = node
        self.generic_visit(node)
    
    def visit_AsyncFor(self, node):
        self.visit_For(node)
    
    def visit_If(self, node):
        if self.find_body_index:
            found = True
            for l in self.lines:
                if l not in range(node.lineno, node.end_lineno + 1):
                    found = False
                    break
            if found:
                self.curnode = node
        self.generic_visit(node)
    
    def visit_With(self, node):
        if self.find_body_index:
            found = True
            for l in self.lines:
                if l not in range(node.lineno, node.end_lineno + 1):
                    found = False
                    break
            if found:
                self.curnode = node
        self.generic_visit(node)
    
    def visit_AsyncWith(self, node):
        self.visit_With(node)
    
    def visit_Try(self, node):
        if self.find_body_index:
            found = True
            for l in self.lines:
                if l not in range(node.lineno, node.end_lineno + 1):
                    found = False
                    break
            if found:
                self.curnode = node
        self.generic_visit(node)
    
    def visit_TryStar(self, node):
        if self.find_body_index:
            found = True
            for l in self.lines:
                if l not in range(node.lineno, node.end_lineno + 1):
                    found = False
                    break
            if found:
                self.curnode = node
        self.generic_visit(node)


    def run(self, root, lines, find_body_index = False):
        self.lines = lines
        self.curnode = root
        self.find_body_index = find_body_index
        self.visit(root)
        if not find_body_index:
            return self.curnode
        else:
            index = -1
            if len(lines) > 1:
                raise ValueError('Only one line is supported when find_body_index is True.')
            relation = None
            for name, value in ast.iter_fields(self.curnode):
                if isinstance(value, list) and len(value) > 0 and value[0].lineno < lines[0] and values[-1].lineno > lines[0]:
                    for i, n in enumerate(value):
                        if n.lineno > lines[0]:
                            index = i-1
                            relation = name
                            break
            return self.curnode, index, relation








class BugLocator(object):
    def __init__(self, buglines = None):
        pass