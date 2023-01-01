import os
import ast





class FunctionLocator(ast.NodeVisitor):
    def __init__(self):
        self.curnode = None
    
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


    def run(self, root, lines, find_body_index = False):
        self.lines = lines
        self.curnode = root
        self.visit(root)
        if not find_body_index:
            return self.curnode
        else:
            index = -1
            if len(lines) > 1:
                raise ValueError('Only one line is supported when find_body_index is True.')
            for i, n in enumerate(self.curnode.body):
                if n.lineno > lines[0]:
                    index = i-1
                    break
            return self.curnode, index








class BugLocator(object):
    def __init__(self, buglines = None):
        pass