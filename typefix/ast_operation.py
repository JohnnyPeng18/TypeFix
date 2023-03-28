import json
import os
import ast
import re
from copy import deepcopy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings, cat2op, op2code
from change_tree import ChangeNode, ChangeTree, ChangePair
from fix_template import FixTemplate, TemplateTree, Context, TemplateNode
from difflib import Differ



class ASTDiffer(object):
    def __init__(self):
        pass

    @staticmethod
    def has_mask(node):
        for n in ast.iter_child_nodes(node):
            if type(n) == ast.Name and n.id in ['VALUE_MASK', 'VALUE_MASK___VALUE_MASK']:
                return True

    @staticmethod
    def value_abstract_compare(a, b, stmt_sensitive = True):
        if (type(a) == ast.Name and a.id == 'VALUE_MASK' and type(b) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp, ast.BoolOp, ast.Subscript]) or (type(b) == ast.Name and b.id == 'VALUE_MASK' and type(a) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp, ast.BoolOp,  ast.Subscript]):
            return True
        elif (type(a) in [ast.Compare, ast.BoolOp, ast.UnaryOp] and ASTDiffer.has_mask(a) and type(b) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp, ast.BoolOp]) or (type(b) in [ast.Compare, ast.BoolOp, ast.UnaryOp] and ASTDiffer.has_mask(b) and type(a) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp, ast.BoolOp]):
            return True
        elif (type(a) == ast.Name and a.id == 'VALUE_MASK' and type(b) == ast.Call and ((type(b.func) == ast.Name and b.func.id.endswith('Error')) or (len(b.args) + len(b.keywords)) < 3)) or (type(b) == ast.Name and b.id == 'VALUE_MASK' and type(a) == ast.Call and ((type(a.func) == ast.Name and a.func.id.endswith('Error')) or (len(a.args) + len(a.keywords)) < 3)):
            return True
        elif (type(a) == ast.Name and a.id == 'VALUE_MASK' and type(b) == ast.BinOp and type(b.left) == ast.Constant and type(b.op) == ast.Mod) or (type(b) == ast.Name and b.id == 'VALUE_MASK' and type(a) == ast.BinOp and type(a.left) == ast.Constant and type(a.op) == ast.Mod):
            return True
        elif (type(a) == ast.Name and a.id == 'VALUE_MASK' and type(b) in [ast.Dict] and len(b.keys) == 0 and len(b.values) == 0) or (type(b) == ast.Name and b.id == 'VALUE_MASK' and type(a) in [ast.Dict] and len(a.keys) == 0 and len(a.values) == 0):
            return True 
        elif type(a) in elem_types and type(b) in elem_types:
            return True
        elif not stmt_sensitive and (type(a) == ast.Expr and type(a.value) == ast.Name and a.value.id == 'VALUE_MASK___VALUE_MASK' and type(b) in stmt_types) or (type(b) == ast.Expr and type(b.value) == ast.Name and b.value.id == 'VALUE_MASK___VALUE_MASK'and type(a) in stmt_types):
            return True
        elif type(a) == type(b) and isinstance(a, ast.AST) and isinstance(b, ast.AST):
            visited_names = []
            for name, value in ast.iter_fields(a):
                if name in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment']:
                    continue
                else:
                    debug = False
                    visited_names.append(name)
                    if isinstance(value, list):
                        if not hasattr(b, name):
                            if debug:
                                print(name, 1)
                            return False
                        nodes = getattr(b, name)
                        if len(value) != len(nodes):
                            if debug:
                                print(name, 2)
                                print(value)
                                print(nodes)
                            return False
                        for i in range(0, len(value)):
                            if not ASTDiffer.value_abstract_compare(value[i], nodes[i], stmt_sensitive = stmt_sensitive):
                                if debug:
                                    #print(ast.dump(value[i]))
                                    #print(ast.dump(nodes[i]))
                                    print(name, 10)
                                return False
                    elif isinstance(value, ast.AST):
                        if not hasattr(b, name):
                            if debug:
                                print(name, 3)
                            return False
                        node = getattr(b, name)
                        if (type(value) == ast.Name and value.id == 'VALUE_MASK' and type(node) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp]) or (type(node) == ast.Name and node.id == 'VALUE_MASK' and type(value) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp]):
                            pass
                        elif (type(value) == ast.Name and value.id == 'VALUE_MASK' and type(node) == ast.Call and ((type(node.func) == ast.Name and node.func.id.endswith('Error')) or (len(node.args) + len(node.keywords)) < 3)) or (type(node) == ast.Name and node.id == 'VALUE_MASK' and type(value) == ast.Call and ((type(value.func) == ast.Name and value.func.id.endswith('Error')) or (len(value.args) + len(value.keywords)) < 3)):
                            pass
                        elif not ASTDiffer.value_abstract_compare(value, node, stmt_sensitive = stmt_sensitive):
                            if debug:
                                print(name, 4)
                                print(ast.dump(value))
                                print(ast.dump(node))
                            return False
                    elif hasattr(b, name) and (isinstance(getattr(b, name), list) or isinstance(getattr(b, name), ast.AST)):
                        return False
            for name, value in ast.iter_fields(b):
                if name in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment']:
                    continue
                elif name in visited_names:
                    continue
                else:
                    visited_names.append(name)
                    if isinstance(value, list):
                        if not hasattr(a, name):
                            #print(name, 5)
                            return False
                        nodes = getattr(a, name)
                        if len(value) != len(nodes):
                            #print(name, 6)
                            return False
                        for i in range(0, len(value)):
                            if not ASTDiffer.value_abstract_compare(value[i], nodes[i], stmt_sensitive = stmt_sensitive):
                                #print(name, 7)
                                return False
                    elif isinstance(value, ast.AST):
                        if not hasattr(a, name):
                            #print(name, 8)
                            return False
                        node = getattr(a, name)
                        if (type(value) == ast.Name and value.id == 'VALUE_MASK' and type(node) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp]) or (type(node) == ast.Name and node.id == 'VALUE_MASK' and type(value) in [ast.Name, ast.Constant, ast.Attribute, ast.Compare, ast.UnaryOp]):
                            pass
                        elif (type(value) == ast.Name and value.id == 'VALUE_MASK' and type(node) == ast.Call and ((type(node.func) == ast.Name and node.func.id.endswith('Error')) or (len(node.args) + len(node.keywords)) < 3)) or (type(node) == ast.Name and node.id == 'VALUE_MASK' and type(value) == ast.Call and ((type(value.func) == ast.Name and value.func.id.endswith('Error')) or (len(value.args) + len(value.keywords)) < 3)):
                            pass
                        elif not ASTDiffer.value_abstract_compare(value, node, stmt_sensitive = stmt_sensitive):
                            #print(name, 9)
                            return False
                    elif hasattr(a, name) and (isinstance(getattr(a, name), list) or isinstance(getattr(a, name), ast.AST)):
                        return False
            return True
        elif a == b:
            return True
        else:
            return False

    @staticmethod
    def extract_mask_content(a, b):
        nodemap = {}
        if not ASTDiffer.has_mask(a):
            return nodemap
        if type(a) == type(b) and isinstance(a, ast.AST) and isinstance(b, ast.AST):
            for name, value in ast.iter_fields(a):
                if not hasattr(b, name):
                    return None
                if name in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment']:
                    continue
                else:
                    if isinstance(value, list):
                        nodes = getattr(b, name)
                        if len(value) != len(nodes):
                            return None
                        for i in range(0, len(value)):
                            submap = ASTDiffer.extract_mask_content(value[i], nodes[i])
                            if submap == None:
                                return None
                            else:
                                for n in submap:
                                    nodemap[n] = submap[n]
                    elif isinstance(value, ast.AST):
                        node = getattr(b, name)
                        submap = ASTDiffer.extract_mask_content(node, value)
                        if submap == None:
                            return None
                        else:
                            for n in submap:
                                nodemap[n] = submap[n]
            return nodemap
        elif type(a) == ast.Name and a.id in ['VALUE_MASK___VALUE_MASK', 'VALUE_MASK']:
            nodemap[a] = b
            return nodemap
        else:
            return None

    @staticmethod
    def compare(a, b):
        if type(a) == type(b) and isinstance(a, ast.AST):
            visited_names = []
            debug = False
            for name, value in ast.iter_fields(a):
                if name in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment']:
                    continue
                if not hasattr(b, name):
                    if debug:
                        print(1, name)
                    return False
                visited_names.append(name)
                if isinstance(value, list):
                    node = getattr(b, name)
                    if len(node) != len(value):
                        if debug:
                            print(2, name)
                            print(node)
                            print(value)
                        return False
                    for i, n in enumerate(value):
                        if not ASTDiffer.compare(n, node[i]):
                            if debug:
                                print(3, name)
                            return False
                elif isinstance(value, ast.AST):
                    node = getattr(b, name)
                    if not ASTDiffer.compare(node, value):
                        if debug:
                            print(4, name)
                        return False
                else:
                    node = getattr(b, name)
                    if node != value:
                        if debug:
                            print(5, name)
                        return False
            for name, value in ast.iter_fields(b):
                if name in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment']:
                    continue
                if name in visited_names:
                    continue
                if not hasattr(a, name):
                    if debug:
                        print(6, name)
                    return False
            return True
        elif type(a) == type(b) and a == b:
            return True
        else:
            return False
        

class ASTVisitor(ast.NodeVisitor):
    def __init__(self, buglines, remove_import = False):
        self.buglines = buglines
        self.locations = []
        self.selected = {}
        self.remove_import = remove_import

    def visit_Import(self, node):
        location = []
        for l in self.buglines:
            if l in self.selected:
                continue
            elif l in range(node.lineno, node.end_lineno + 1):
                location.append(l)
                self.selected[l] = 1
        if len(location) > 0 and not self.remove_import:
            self.locations.append(location)
    
    def visit_ImportFrom(self, node):
        self.visit_Import(node)


    def visit_FunctionDef(self, node):
        location = []
        for l in self.buglines:
            if l in self.selected:
                continue
            elif l in range(node.lineno, node.end_lineno + 1):
                location.append(l)
                self.selected[l] = 1
        if len(location) > 0:
            self.locations.append(location)
        
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        location = []
        for l in self.buglines:
            if l in self.selected:
                continue
            elif l in range(node.lineno, node.end_lineno + 1):
                location.append(l)
        
        self.generic_visit(node)
        new_location = []
        for l in location:
            if l not in self.selected:
                new_location.append(l)
                self.selected[l] = 1
        if len(new_location) > 0:
            self.locations.append(new_location)
    
    def run(self, root):
        if len(self.buglines) == 1:
            return [self.buglines]
        self.visit(root)
        locs = []
        for l in self.buglines:
            if l not in self.selected:
                locs.append(l)
                self.selected[l] = 1
        
        if len(locs) > 0:
            self.locations.append(locs)
        

        change = {}

        for index, loc in enumerate(self.locations):
            if len(loc) == 1:
                continue
            split_index = []
            for i in range(0, len(loc) - 1):
                if loc[i+1] - loc[i] > 10:
                    split_index.append(i)
            if len(split_index) > 0:
                new_loc = []
                cur_loc = []
                for i in range(0, len(loc)):
                    if i not in split_index:
                        cur_loc.append(loc[i])
                    else:
                        cur_loc.append(loc[i])
                        if len(cur_loc) > 0:
                            new_loc.append(cur_loc)
                        cur_loc = []
                if len(cur_loc) > 0:
                    new_loc.append(cur_loc)
                change[index] = new_loc
        
        newlocations = []
        for i in range(0, len(self.locations)):
            if i not in change:
                newlocations.append(self.locations[i])
            else:
                newlocations += change[i]

        self.locations = newlocations

        #split the lines that are not together
        newlocations = []
        for loc in self.locations:
            prev = 0
            for i in range(0, len(loc) - 1):
                if loc[i] != loc[i+1] - 1:
                    newlocations.append(loc[prev:i+1])
                    prev = i+1
            if prev < len(loc):
                newlocations.append(loc[prev:])
        self.locations = newlocations


        return self.locations

class CommentRemover(ast.NodeTransformer):
    def __init__(self):
        pass
    
    def visit_Expr(self, node):
        self.generic_visit(node)
        if type(node.value) == ast.Constant and isinstance(node.value.value, str):
            return None
        else:
            return node
    
    def run(self, root):
        self.visit(root)
        ast.fix_missing_locations(root)
        return root


class ASTTransformer(ast.NodeTransformer):
    def __init__(self, nodes_map, opnodes, remove_comment = False):
        self.nodes_map = nodes_map
        self.opnodes = opnodes
        self.lines = []
        self.replaced = {}
        self.remove_comment = remove_comment
        for n in self.nodes_map:
            for l in range(n.lineno, n.end_lineno + 1):
                if l not in self.lines:
                    self.lines.append(l)
        
        for n in ast.__dict__:
            if isinstance(n, str):
                try:
                    if issubclass(getattr(ast, n), ast.AST):
                        setattr(self, 'visit_'+n, lambda node: self.modify(node))
                except:
                    continue
        
    def compare(self, a, b):
        loc = ['lineno', 'end_lineno', 'col_offset', 'end_col_offset']
        matched = True
        if type(a) != type(b):
            matched = False
        else:
            for l in loc:
                if getattr(a, l) != getattr(b, l):
                    matched = False
                    break
        return matched


    def modify(self, node):
        self.generic_visit(node)
        if hasattr(node, 'lineno'):
            found = False
            for l in range(node.lineno, node.end_lineno + 1):
                if l in self.lines:
                    found = True
                    break
            if found:
                for n in self.nodes_map:
                    if n not in self.replaced and self.compare(node, n):
                        self.replaced[n] = 1
                        #print('From:', ast.dump(n))
                        #print('To:', ast.dump(self.nodes_map[n]))
                        return self.nodes_map[n]
        return node

    def replace_ops(self, source, old_source):
        if len(self.opnodes) == 0:
            return source
        replace_ops = []
        for n in self.opnodes:
            replace_ops += [op2code[type(k)] for k in self.opnodes[n]]
        d = Differ()
        source_lines = source.splitlines()
        res = '\n'.join(d.compare(source_lines, old_source.splitlines()))
        changed_lines = []
        for l in res.splitlines():
            if l.startswith('-'):
                changed_lines.append(l[2:])
        for l in changed_lines:
            for o in replace_ops:
                logger.debug(f'Handled Op {o}')
                changed_l = l.replace(f' {o} ', ' VALUE_MASK ')
            source_lines[source_lines.index(l)] = changed_l
        
        source = '\n'.join(source_lines)


        return source


    def run(self, root):
        if self.remove_comment:
            remover = CommentRemover()
            root = remover.run(root)
        new_root = deepcopy(root)
        self.visit(new_root)
        ast.fix_missing_locations(new_root)
        try:
            source = ast.unparse(new_root)
            ast.parse(source)
            old_source = ast.unparse(ast.parse(root))
            source = self.replace_ops(source, old_source)
            return source, new_root
        except Exception as e:
            logger.debug('Source generated failed, reason: {}'.format(e))
            return None, None



class ASTNodeGenerator(object):
    def __init__(self, nodes, nodemap, template, parent = None):
        if nodes != None and len(nodes) != len(template.before_within.root.children['body']):
            raise ValueError('Inconsistent number between before tree and matched AST nodes: {} and {}.'.format(len(template.before.root.children['body']), len(nodes)))

        self.nodes = nodes
        self.nodemap = nodemap
        self.template = template
        self.parent = parent
        self.before2source = {}
        self.before_change_nodes = {}
        self.changes = self.map_nodes(nodes, nodemap, template)
        self.referred = {}
        self.morenodes = {}
        self.indexed_reference = []
        self.mask = 'VALUE_MASK'
        self.attr_mask = 'VALUE_MASK.VALUE_MASK'
        #self.expr_mask = 'VALUE_MASK__VALUE_MASK'
        self.expr_mask = 'VALUE_MASK'
        self.stmt_mask = 'VALUE_MASK___VALUE_MASK'

    def map_nodes(self, nodes, nodemap, template):
        if nodes != None and nodemap != None:
            source2before = nodemap
            before2source = {}
            for n in nodemap:
                before2source[nodemap[n].id] = n
            before_change_nodes = {}
            for n in template.before_within.root.children['body']:
                if n.before_index != None:
                    before_change_nodes[n.before_index] = n.id
                children = n.get_all_children()
                for c in children:
                    if c.before_index != None:
                        before_change_nodes[c.before_index] = c.id
            if template.before:
                for i in range(0, len(template.before.root.children['body'])):
                    if i not in before_change_nodes:
                        raise ValueError('Cannot find before node #{}'.format(i))
            
            if template.action == 'Insert' and len(template.before.root.children['body']) != len(template.after.root.children['body']):
                reference_map = {}
                for n in template.after.root.children['body']:
                    reference_map[n] = []
                    children = n.get_all_children()
                    for c in children:
                        if c.type == 'Reference':
                            reference_map[n].append(before2source[before_change_nodes[template.before.root.children['body'].index(c.refer_to[0])]])
                
                changes = {'Insert': reference_map}
            elif template.within_context == None and template.after != None:
                source2after = {}
                if len(template.before.root.children['body']) != len(template.after.root.children['body']):
                    raise ValueError('Template must have exactly same node num of before and after trees when within context is None')
                for i in range(0, len(template.before.root.children['body'])):
                    source2after[before2source[before_change_nodes[i]]] = template.after.root.children['body'][i]
                changes = {'Replace': source2after}
            elif template.within_context == None and template.after == None:
                changes = {'OnlyRemove': []}
                leaf_nodes = template.before_within.get_leaf_nodes()
                for n in leaf_nodes:
                    changes['OnlyRemove'].append(before2source[n.id])
            else:
                relation_nodes = Context.get_within_relation_nodes_dfs(template.before_within.root, mode='all')
                remove = {}
                add = {}
                for n in relation_nodes:
                    if len(n.within_context_relation['before']) > 0:
                        remove[before2source[n.id]] = []
                        for c in n.within_context_relation['before']:
                            if n.type == 'Compare' and c[0] == 'op':
                                relation = 'ops'
                            else:
                                relation = c[0]
                            remove[before2source[n.id]].append([relation, before2source[before_change_nodes[c[1]]]])
                    if len(n.within_context_relation['after']) > 0:
                        add[before2source[n.id]] = []
                        for c in n.within_context_relation['after']:
                            if n.type == 'Compare' and c[0] == 'op':
                                relation = 'ops'
                            else:
                                relation = c[0]
                            add[before2source[n.id]].append([relation, template.after.root.children['body'][c[1]]]) 
                changes = {'Remove': remove, 'Add': add}
            self.before2source = before2source
            self.before_change_nodes = before_change_nodes
        else:
            changes = {'OnlyAdd': []}
            for n in template.after.root.children['body']:
                changes['OnlyAdd'].append(n)
        return changes

    def init_node(self, nodetype):
        if not hasattr(ast, nodetype):
            raise ValueError(f'Unrecognized node type {nodetype}')
        node = getattr(ast, nodetype)()
        if nodetype == 'FunctionType':
            node.argtypes = []
            node.returns = Name(id = self.mask)
        if nodetype == 'Name':
            node.id = self.mask
        if nodetype in ['FunctionDef', 'AsyncFunctionDef', 'ClassDef']:
            node.name = self.mask
            node.decorator_list = []
        if nodetype in ['FunctionDef', 'AsyncFunctionDef', 'Lambda']:
            node.args = ast.arguments(posonlyargs = [], args = [], vararg = None, kwonlyargs = [], kw_defaults = [], kwarg = None, defaults = [])
        if nodetype in ['FunctionDef', 'AsyncFunctionDef']:
            node.returns = None
        if nodetype == 'ClassDef':
            node.bases = []
            node.keywords = []
        if nodetype in ['FunctionDef', 'AsyncFunctionDef', 'ClassDef', 'Module', 'Interactive', 'Expression', 'For', 'AsyncFor', 'While', 'If', 'With', 'AsyncWith', 'Try', 'TryStar']:
            node.body = []
        if nodetype in ['For', 'AsyncFor', 'While', 'If', 'Try', 'TryStar']:
            node.orelse = []
        if nodetype in ['While', 'If', 'Assert', 'IfExp']:
            node.test = ast.Name(id = self.mask)
        if nodetype in ['FunctionDef', 'AsyncFunctionDef', 'Assign', 'For', 'AsyncFor', 'With', 'AsyncWith', 'arg']:
            node.type_comment = None
        if nodetype in ['Return', 'AnnAssign', 'Yield']:
            node.value = None
        if nodetype in ['Assign', 'AugAssign', 'Expr', 'NamedExpr', 'Await', 'YieldFrom', 'FormattedValue', 'Attribute', 'Subscript', 'Starred', 'keyword']:
            node.value = None
        if nodetype in ['Delete', 'Assign']:
            node.targets = []
        if nodetype in ['AnnAssign', 'AugAssign', 'For', 'AsyncFor', 'NamedExpr']:
            node.target = ast.Name(id = self.mask)
        if nodetype == 'AugAssign':
            node.op = ast.Add()
        if nodetype == 'AnnAssign':
            node.annotation = ast.Name(id = self.mask)
            node.simple = 0
        if nodetype in ['For', 'AsyncFor']:
            node.iter = ast.Name(id = self.mask)
        if nodetype in ['With', 'AsyncWith']:
            node.items = []
        if nodetype == 'Match':
            node.subject = ast.Name(id = self.mask)
            node.cases = []
        if nodetype == 'Raise':
            node.exc = None
            node.cause = None
        if nodetype in ['Try', 'TryStar']:
            node.finalbody = []
            node.handlers = []
        if nodetype == 'Assert':
            node.msg = None
        if nodetype in ['Import', 'ImportFrom']:
            node.names = []
        if nodetype == 'ImportFrom':
            node.module = self.mask
            node.level = 0
        if nodetype in ['Global', 'Nonlocal']:
            node.names = [self.mask]
        if nodetype == 'Expr':
            node.value = ast.Constant(value = self.expr_mask)
        if nodetype == 'BoolOp':
            node.op = ast.And()
        if nodetype in ['BoolOp', 'Dict', 'JoinedStr']:
            node.values = []
        if nodetype in ['BinOp', 'UnaryOp']:
            node.op = ast.Add()
        if nodetype == 'BinOp':
            node.left = ast.Name(id = self.mask)
            node.right = ast.Name(id = self.mask)
        if nodetype == 'UnaryOp':
            node.operand = ast.Name(id = self.mask)
        if nodetype in ['Lambda', 'IfExp']:
            node.body = ast.Constant(value = self.mask)
        if nodetype == 'IfExp':
            node.orelse = None
        if nodetype == 'Dict':
            node.keys = []
        if nodetype == 'Set':
            node.elts = []
        if nodetype in ['ListComp', 'SetCom', 'GeneratorExp']:
            node.elt = ast.Name(id = self.mask)
        if nodetype == 'DictComp':
            node.key = ast.Name(id = self.mask)
            node.value = ast.Name(id = self.mask)
        if nodetype in ['ListComp', 'SetCom', 'GeneratorExp', 'DictComp']:
            node.generators = []
        if nodetype == 'Compare':
            node.left = ast.Name(id = self.mask)
            node.ops = []
            node.comparators = []
        if nodetype == 'Call':
            node.func = ast.Name(id = self.mask)
            node.args = []
            node.keywords = []
        if nodetype == 'FormattedValue':
            node.value = ast.Name(id = self.mask)
            node.conversion = -1
            node.format_spec = None
        if nodetype == 'Attribute':
            node.attr = self.mask
        if nodetype == 'Subscript':
            node.slice = ast.Name(id = self.mask)
        if nodetype in ['List', 'Tuple']:
            node.elts = []
        if nodetype == 'Slice':
            node.lower = ast.Constant(value = 0)
            node.higher = ast.Constant(value = 0)
        if nodetype == 'comprehension':
            node.target = ast.Name(id = self.mask)
            node.iter = ast.Name(id = self.mask)
            node.is_async = 0
            node.ifs = []
        if nodetype == 'ExceptHandler':
            node.type = ast.Name(id = self.mask)
            node.body = []
            node.name = None
        if nodetype == 'arguments':
            node.posonlyargs = []
            node.args = [] 
            node.vararg = None 
            node.kwonlyargs = [] 
            node.w_defaults = []
            node.kwarg = None 
            node.defaults = []
        if nodetype == 'arg':
            node.arg = self.mask
            node.annotation = None
        if nodetype == 'alias':
            node.name = self.mask
            node.asname = None
        if nodetype == 'withitem':
            node.context_expr = ast.Name(id = self.mask)
        if nodetype == 'match_case':
            node.pattern = ast.MatchValue(value = ast.Constant(value = self.mask))
            node.body = []
        if nodetype == 'MatchValue':
            node.value = ast.Constant(value = self.mask)
        if nodetype == 'MatchSingleton':
            node.value = self.mask
        if nodetype == 'MatchSequence':
            node.patterns = []
        if nodetype == 'MatchMapping':
            node.keys = []
            node.patterns = []
            node.rest = None
        if nodetype == 'MatchClass':
            node.cls = ast.Name(id = self.mask)
            node.patterns = []
            node.kwd_attrs = []
            node.kwd_patterns = []
        if nodetype == 'MatchStar':
            node.name = self.mask
        if nodetype == 'MatchAs':
            node.pattern = None
            node.name = self.mask
        if nodetype == 'MatchOr':
            node.patterns = []

        return node

    def build_ast_node(self, node, parent_ast_node, modify_parent = False):
        ast_node = None
        if modify_parent:
            parent_ast_node = deepcopy(parent_ast_node)
        if hasattr(ast, node.type) and not (node.type == 'Expr' and node.type_abstracted):
            if node.type == 'Attribute':
                ast_node = self.init_node('Name')
                if node.value not in ['ABSTRACTED', 'REFERRED']:
                    ast_node.id = node.value
                else:
                    ast_node.id = self.attr_mask
            else:
                ast_node = self.init_node(node.type)
        elif node.type == 'Variable':
            if node.value not in ['ABSTRACTED', 'REFERRED']:
                value = node.value
            else:
                value = self.mask
            if node.parent_relation == 'name':
                if node.parent.type in ['ClassDef', 'FunctionDef', 'AsyncFunctionDef', 'ExceptHandler']:
                    parent_ast_node.name = value
                elif node.parent.type in ['Global', 'Nonlocal']:
                    parent_ast_node.names.append(value)
            elif node.parent_relation == 'args':
                ast_node = self.init_node('arg')
                ast_node.arg = value
                parent_ast_node.args.append(ast_node)
            elif node.parent_relation == 'kwonlyargs':
                ast_node = self.init_node('arg')
                ast_node.arg = value
                parent_ast_node.kwonlyargs.append(ast_node)
            elif node.parent_relation == 'vararg':
                ast_node = self.init_node('arg')
                ast_node.arg = value
                parent_ast_node.vararg = ast_node
            elif node.parent_relation == 'kwarg':
                ast_node = self.init_node('arg')
                ast_node.arg = value
                parent_ast_node.kwarg = ast_node
            elif node.parent_relation == 'arg' and parent_ast_node.type == ast.keyword:
                parent_ast_node.arg = value
            else:
                ast_node = self.init_node('Name')
                ast_node.id = value
                if node.parent_relation != None and hasattr(parent_ast_node, node.parent_relation):
                    if isinstance(getattr(parent_ast_node, node.parent_relation), list):
                        l = getattr(parent_ast_node, node.parent_relation)
                        l.append(ast_node)
                        setattr(parent_ast_node, node.parent_relation, l)
                    else:
                        setattr(parent_ast_node, node.parent_relation, ast_node)
        elif node.type == 'Op':
            if node.value in op2cat:
                ast_node = self.init_node(node.value)
            elif node.value.endswith('OP'):
                nodes = []
                for op in cat2op[node.value]:
                    ast_node = self.init_node(op)
                    nodes.append(ast_node)
                self.morenodes[nodes[-1]] = [nodes[:-1], parent_ast_node, 'ops' if type(parent_ast_node) == ast.Compare else 'op']
            else:
                nodes = []
                if type(parent_ast_node) == ast.BoolOp:
                    for op in cat2op['BOOL_OP']:
                        ast_node = self.init_node(op)
                        nodes.append(ast_node)
                elif type(parent_ast_node) == ast.BinOp:
                    for op in cat2op['MATH_OP']:
                        ast_node = self.init_node(op)
                        nodes.append(ast_node)
                elif type(parent_ast_node) == ast.UnaryOp:
                    for op in cat2op['UNARY_OP']:
                        ast_node = self.init_node(op)
                        nodes.append(ast_node)
                elif type(parent_ast_node) == ast.Compare:
                    for op in cat2op['CMP_OP']:
                        ast_node = self.init_node(op)
                        nodes.append(ast_node)
                elif parent_ast_node == None:
                    for op in cat2op['BOOL_OP']:
                        ast_node = self.init_node(op)
                        nodes.append(ast_node)
                self.morenodes[nodes[-1]] = [nodes[:-1], parent_ast_node, 'ops' if type(parent_ast_node) == ast.Compare else 'op']
            if modify_parent and type(parent_ast_node) in [ast.BoolOp, ast.BinOp, ast.UnaryOp]:
                parent_ast_node.op = ast_node
            elif modify_parent and type(parent_ast_node) in [ast.Compare]:
                parent_ast_node.ops.append(ast_node)
        elif node.type == 'Literal':
            if node.value in ['ABSTRACTED', 'REFERRED']:
                ast_node = self.init_node('Name')
                ast_node.id = self.mask
            elif node.value_abstracted and node.value == 'str':
                ast_node = self.init_node('Constant')
                ast_node.value = self.mask
            else:
                ast_node = self.init_node('Constant')
                ast_node.value = node.value
        elif node.type == 'Keyword':
            if node.value in ['ABSTRACTED', 'REFERRED']:
                parent_ast_node.arg = self.mask
            else:
                parent_ast_node.arg = node.value
        elif node.type == 'Builtin':
            #nodes = []
            ast_node = self.init_node('Name')
            ast_node.id = self.mask
            if node.value in ['ABSTRACTED', 'REFERRED']:
                '''
                for v in builtins:
                    ast_node = self.init_node('Name')
                    ast_node.id = v
                    nodes.append(ast_node)
                self.morenodes[nodes[-1]] = [nodes[:-1], parent_ast_node, node.parent_relation]
                '''
            else:
                ast_node = self.init_node('Name')
                ast_node.id = node.value
        elif node.type == 'Type':
            nodes = []
            if node.value in ['ABSTRACTED', 'REFERRED']:
                '''
                for v in ["int", "float", "complex", "bool", "list", "tuple", "range", "str", "bytes", "bytearray", "memoryview", "set", "frozenset", "dict"]:
                    ast_node = self.init_node('Name')
                    ast_node.id = v
                    nodes.append(ast_node)
                self.morenodes[nodes[-1]] = [nodes[:-1], parent_ast_node, node.parent_relation]
                '''
                ast_node = self.init_node('Name')
                ast_node.id = self.mask
            else:
                ast_node = self.init_node('Name')
                ast_node.id = node.value
        elif node.type == 'Identifier':
            ast_node = self.init_node('Name')
            ast_node.id = self.expr_mask
        elif node.type == 'End_Expr':
            ast_node = self.init_node('Name')
            ast_node.id = self.expr_mask
        elif node.type == 'Expr':
            ast_node = self.init_node('Name')
            ast_node.id = self.expr_mask
        elif node.type == 'Stmt':
            ast_node = self.init_node('Expr')
            ast_node.value = self.init_node('Name')
            ast_node.value.id = self.stmt_mask
        elif node.type == 'Reference':
            if len(node.refer_to) == 1:
                ast_node = deepcopy(self.before2source[self.before_change_nodes[self.template.before.root.children['body'].index(node.refer_to[0])]].ast_node)
            else:
                ast_node = None
                for n in node.refer_to:
                    index = self.template.before.root.children['body'].index(n)
                    if index not in self.indexed_reference:
                        ast_node = deepcopy(self.before2source[self.before_change_nodes[index]].ast_node)
                        self.indexed_reference.append(index)
                        break
                if not ast_node:
                    raise ValueError('Cannot find reference nodes.')

        nodetype = node.type if node.type != 'Reference' else self.before2source[self.before_change_nodes[self.template.before.root.children['body'].index(node.refer_to[0])]].type

        if (nodetype not in ['Variable', 'Op', 'Keyword'] or (node.type == 'Reference' and nodetype == 'Variable')) and node.parent_relation != None and hasattr(parent_ast_node, node.parent_relation) and parent_ast_node != None and node.parent.base_type != 'Root':
            if isinstance(getattr(parent_ast_node, node.parent_relation), list):
                l = getattr(parent_ast_node, node.parent_relation)
                l.append(ast_node)
                setattr(parent_ast_node, node.parent_relation, l)
            else:
                setattr(parent_ast_node, node.parent_relation, ast_node)
        elif nodetype == 'Op' and not modify_parent and parent_ast_node != None and node.parent.base_type != 'Root':
            if hasattr(parent_ast_node, node.parent_relation):
                relation = node.parent_relation
            elif node.parent_relation == 'op' and type(parent_ast_node) == ast.Compare:
                relation = 'ops'
            else:
                raise ValueError('{}-{}, {}'.format(node.parent_relation, node.type, ast.dump(parent_ast_node)))
            if isinstance(getattr(parent_ast_node, relation), list):
                l = getattr(parent_ast_node, relation)
                l.append(ast_node)
                setattr(parent_ast_node, relation, l)
            else:
                setattr(parent_ast_node, relation, ast_node)


        for c in node.children:
            for n in node.children[c]:
                self.build_ast_node(n, ast_node, modify_parent = modify_parent)
        if modify_parent and node.type in ['Variable', 'Op']:
            return parent_ast_node
        else:
            return ast_node
    
    def compare(self, a, b):
        loc = ['lineno', 'end_lineno', 'col_offset', 'end_col_offset']
        matched = True
        if type(a) != type(b):
            matched = False
        else:
            for l in loc:
                if getattr(a, l) != getattr(b, l):
                    matched = False
                    break
        #print(ast.dump(a), ast.dump(b), matched, a.end_col_offset, b.end_col_offset)
        return matched
        
    
    def complete_attributes(self, new_ast_node, old_ast_node, after, before):
        pass

    def replace_one(self, root, case, morenodes):
        new_root = deepcopy(root)
        for i, n in enumerate(morenodes):
            if case[i] == 0:
                continue
            else:
                newnode = morenodes[n][0][case[i] - 1]
                for nn in ast.walk(new_root):
                    if hasattr(nn, 'lineno') and self.compare(nn, morenodes[n][1]):
                        k = getattr(nn, morenodes[n][2])
                        if isinstance(k, list):
                            k[self.find_index(k, n)] = newnode
                            setattr(nn, morenodes[n][2], k)
                        else:
                            setattr(nn, morenodes[n][2], newnode)
        return new_root
                            

    def gen_index(self, max_index, extra = True):
        if len(max_index) == 1:
            if extra:
                return [[i] for i in range(0, max_index[0] + 1)]
            else:
                return [[i] for i in range(0, max_index[0])]
        else:
            cases = []
            if extra:
                for i in range(0, max_index[0] + 1):
                    sub_cases = self.gen_index(max_index[1:], extra = extra)
                    for c in sub_cases:
                        cases.append([i] + c)
            else:
                for i in range(0, max_index[0]):
                    sub_cases = self.gen_index(max_index[1:], extra = extra)
                    for c in sub_cases:
                        cases.append([i] + c)
            return cases


    def replace_all(self, root, morenodes):
        max_index = []
        for n in morenodes:
            max_index.append(len(morenodes[n][0]))
        
        cases = self.gen_index(max_index)
        roots = []
        for c in cases:
            roots.append(self.replace_one(root, c, morenodes))
        
        return roots

    def mutate(self, ori2new, morenodes):
        mutated_ori2new = {}
        for o in ori2new:
            if len(morenodes[o]) == 0:
                mutated_ori2new[o] = [ori2new[o]]
            else:
                mutated_ori2new[o] = self.replace_all(ori2new[o], morenodes[o])
        
        return mutated_ori2new

    def print_morenodes(self, morenodes):
        print('=======More Nodes============')
        for s in morenodes:
            print(ast.dump(s))
            for n in morenodes[s]:
                print('{} -> {}'.format(ast.dump(n), [ast.dump(k) for k in morenodes[s][n][0]]))

    def find_index(self, nodelist, node):
        if hasattr(node, 'lineno'):
            for index, n in enumerate(nodelist):
                if hasattr(n, 'lineno') and self.compare(n, node):
                    return index
        else:
            for index, n in enumerate(nodelist):
                if type(n) == type(node):
                    return index
        
        print('Cannot find index.')
        print('List:')
        for n in nodelist:
            print(ast.dump(n))
        print('Node:')
        print(ast.dump(node))
        return None

    def handle_ops(self, morenodes):
        op_nodes = {}
        removed = []
        for s in morenodes:
            for n in morenodes[s]:
                if type(n) in elem_types:
                    if morenodes[s][n][1] not in op_nodes:
                        op_nodes[morenodes[s][n][1]] = []
                    op_nodes[morenodes[s][n][1]].append(n)
                    removed.append(n)
            for r in removed:
                if r in morenodes[s]:
                    del morenodes[s][r]
        
        return morenodes, op_nodes



    def gen(self, after = False):
        if 'Replace' in self.changes:
            source2after = self.changes['Replace']
            ori2new = {}
            morenodes = {}
            for s in source2after:
                #print('Source: {}-{}'.format(s.type, s.id))
                after = source2after[s]
                if s.ast_node == None:
                    parent_ast_node_old = deepcopy(s.parent.ast_node)
                    parent_ast_node_new = deepcopy(s.parent.ast_node)
                    if parent_ast_node_old == None:
                        raise ValueError('Cannot find the AST node.')
                    self.morenodes = {}
                    ast_node = self.build_ast_node(after, parent_ast_node_new, modify_parent = True)
                    morenodes[parent_ast_node_old] = self.morenodes
                    ast.fix_missing_locations(ast_node)
                    ori2new[parent_ast_node_old] = ast_node
                elif not hasattr(s.ast_node, 'lineno'):
                    parent_ast_node = deepcopy(s.parent.ast_node)
                    if parent_ast_node == None:
                        raise ValueError('Cannot find the AST node.')
                    self.morenodes = {}
                    ast_node = self.build_ast_node(after, None)
                    relation = s.parent_relation
                    if s.parent.type == 'Compare' and s.type == 'Op':
                        relation = 'ops'
                    node = getattr(parent_ast_node, relation)
                    if isinstance(node, list):
                        node[self.find_index(node, s.ast_node)] = ast_node
                        setattr(parent_ast_node, relation, node)
                    else:
                        setattr(parent_ast_node, relation, ast_node)
                    morenodes[s.parent.ast_node] = self.morenodes
                    ast.fix_missing_locations(parent_ast_node)
                    ori2new[s.parent.ast_node] = parent_ast_node
                else:
                    self.morenodes = {}
                    ast_node = self.build_ast_node(after, None)
                    ori2new[s.ast_node] = ast_node    
                    ast.fix_missing_locations(ast_node)
                    morenodes[s.ast_node] = self.morenodes
            #self.print_morenodes(morenodes)
            morenodes, opnodes = self.handle_ops(morenodes)
            mutated_ori2new = self.mutate(ori2new, morenodes)
            max_index = []
            for n in mutated_ori2new:
                max_index.append(len(mutated_ori2new[n]))
            cases = self.gen_index(max_index, extra = False)
            ori2news = []
            for c in cases:
                temp = {}
                for i, o in enumerate(mutated_ori2new):
                    temp[o] = mutated_ori2new[o][c[i]]
                ori2news.append(temp)

            return ori2news, opnodes
        elif 'Add' in self.changes:
            remove = self.changes['Remove']
            add = self.changes['Add']
            replaced = {}
            morenodes = {}
            ori2new = {}
            for s in remove:
                if s not in replaced:
                    replaced[s] = {}
                removed = remove[s]
                for l in removed:
                    if l[0] not in replaced[s]:
                        replaced[s][l[0]] = {'before': [], 'after': []}
                    replaced[s][l[0]]['before'].append(l[1])
            for s in add:
                if s not in replaced:
                    replaced[s] = {}
                added = add[s]
                for l in added:
                    if l[0] not in replaced[s]:
                        replaced[s][l[0]] = {'before': [], 'after': []}
                    replaced[s][l[0]]['after'].append(l[1])
            for s in replaced:
                ast_node = deepcopy(s.ast_node)
                morenodes[s.ast_node] = {}
                for k in replaced[s]:
                    if not hasattr(ast_node, k):
                        raise ValueError(f'Cannot find relation {k} in AST node: {ast.dump(ast_node)}')
                    if len(replaced[s][k]['before']) > 0 and len(replaced[s][k]['after']) > 0:
                        node = getattr(ast_node, k)
                        if isinstance(node, list):
                            new_ast_nodes = []
                            for n in replaced[s][k]['after']:
                                self.morenodes = {}
                                new_node = self.build_ast_node(n, ast_node)
                                for j in self.morenodes:
                                    morenodes[s.ast_node][j] = self.morenodes[j]
                                #self.print_morenodes(morenodes)
                                new_ast_nodes.append(new_node)
                            old_ast_nodes = []
                            for n in replaced[s][k]['before']:
                                if n.ast_node == None:
                                    raise ValueError('Template Node within a field must have an AST node.')
                                old_ast_nodes.append(n.ast_node)
                            '''
                            print('Old:')
                            for n in old_ast_nodes:
                                print(ast.dump(n))
                            print('New:')
                            for n in new_ast_nodes:
                                print(ast.dump(n))
                            '''
                            for i in range(0, min(len(new_ast_nodes), len(old_ast_nodes))):
                                node[self.find_index(node, old_ast_nodes[i])] = new_ast_nodes[i]
                            if len(old_ast_nodes) > len(new_ast_nodes):
                                for i in range(len(new_ast_nodes), len(old_ast_nodes)):
                                    index = self.find_index(node, old_ast_nodes[i])
                                    node.pop(index)
                            elif len(new_ast_nodes) > len(old_ast_nodes):
                                for i in range(len(old_ast_nodes), len(new_ast_nodes)):
                                    node.append(new_ast_nodes[i])
                            setattr(ast_node, k, node)
                        elif isinstance(node, ast.AST):
                            if len(replaced[s][k]['after']) > 1:
                                raise ValueError('Single node field cannot have more than one new nodes.')
                            self.morenodes = {}
                            new_node = self.build_ast_node(replaced[s][k]['after'][0], ast_node)
                            for j in self.morenodes:
                                morenodes[s.ast_node][j] = self.morenodes[j]
                            setattr(ast_node, k, new_node)
                        else:
                            if len(replaced[s][k]['after']) > 1:
                                raise ValueError('String attributes cannot have more than one new nodes.')
                            if replaced[s][k]['after'][0].value in [None, 'ABSTRACTED', 'REFERRED'] or replaced[s][k]['after'][0].value_abstracted:
                                setattr(ast_node, k, self.mask)
                            elif not replaced[s][k]['after'][0].value_abstracted:
                                setattr(ast_node, k, replaced[s][k]['after'][0].value)
                    elif len(replaced[s][k]['before']) > 0:
                        node = getattr(ast_node, k)
                        if isinstance(node, list):
                            for n in replaced[s][k]['before']:
                                if n.ast_node == None:
                                    raise ValueError('Template Node within a field must have an AST node.')
                                index = self.find_index(node, n.ast_node)
                                node.pop(index)
                            setattr(ast_node, k, node)
                        else:
                            setattr(ast_node, k, None)
                    elif len(replaced[s][k]['after']) > 0:
                        node = getattr(ast_node, k)
                        if isinstance(node, list):
                            new_ast_nodes = []
                            for n in replaced[s][k]['after']:
                                self.morenodes = {}
                                new_node = self.build_ast_node(n, ast_node)
                                for j in self.morenodes:
                                    morenodes[s.ast_node][j] = self.morenodes[j]
                                new_ast_nodes.append(new_node)
                            for n in new_ast_nodes:
                                node.append(n)
                            setattr(ast_node, k, node)
                        elif isinstance(node, ast.AST):
                            if type(node) != ast.arguments:
                                if len(replaced[s][k]['after']) > 1:
                                    raise ValueError('String attributes cannot have more than one new nodes.')
                                self.morenodes = {}
                                new_node = self.build_ast_node(replaced[s][k]['after'][0], ast_node)
                                for j in self.morenodes:
                                    morenodes[s.ast_node][j] = self.morenodes[j]
                                setattr(ast_node, k, new_node)
                            else:
                                for n in replaced[s][k]['after']:
                                    if len(n.children) == 0:
                                        self.morenodes = {}
                                        new_node = self.build_ast_node(n, node)
                                        for j in self.morenodes:
                                            morenodes[s.ast_node][j] = self.morenodes[j]
                                        nodelist = getattr(node, k)
                                        if isinstance(nodelist, list):
                                            nodelist.append(new_node)
                                            setattr(node, k, nodelist)
                                        else:
                                            setattr(node, k, new_node)
                                        setattr(ast_node, k, node)
                                    elif len(n.children) == 1 and "default" in n.children:
                                        new_node = ast.Name(id=self.mask)
                                        node.defaults.append(new_node)
                                        setattr(ast_node, k, node)
                        else:
                            if len(replaced[s][k]['after']) > 1:
                                raise ValueError('String attributes cannot have more than one new nodes.')
                            if replaced[s][k]['after'][0].value in [None, 'ABSTRACTED', 'REFERRED'] or replaced[s][k]['after'][0].value_abstracted:
                                setattr(ast_node, k, self.mask)
                            elif not replaced[s][k]['after'][0].value_abstracted:
                                setattr(ast_node, k, replaced[s][k]['after'][0].value)
                ast.fix_missing_locations(ast_node)
                ori2new[s.ast_node] = ast_node
            #self.print_morenodes(morenodes)
            morenodes, opnodes = self.handle_ops(morenodes)
            mutated_ori2new = self.mutate(ori2new, morenodes)
            max_index = []
            for n in mutated_ori2new:
                max_index.append(len(mutated_ori2new[n]))
            cases = self.gen_index(max_index, extra = False)
            ori2news = []
            for c in cases:
                temp = {}
                for i, o in enumerate(mutated_ori2new):
                    temp[o] = mutated_ori2new[o][c[i]]
                ori2news.append(temp)

            return ori2news, opnodes
        elif 'OnlyRemove' in self.changes:
            ori2new = {}
            parents = {}
            for n in self.changes['OnlyRemove']:
                if n.ast_node == None:
                    if n.parent not in parents:
                        parents[n.parent] = []
                    parents[n.parent].append(n)
            for n in self.changes['OnlyRemove']:
                if n.parent in parents and n not in parents[n.parent]:
                    parents[n.parent].append(n)
            
            for n in parents:
                ast_node = deepcopy(n.ast_node)
                for c in parents[n]:
                    if c.ast_node == None and hasattr(ast_node, c.parent_relation):
                        setattr(ast_node, c.parent_relation, None)
                    elif c.ast_node != None and hasattr(ast_node, c.parent_relation):
                        node = getattr(ast_node, c.parent_relation)
                        if isinstance(node, list):
                            index = self.find_index(node, c.ast_node)
                            node.pop(index)
                        else:
                            node = None
                        setattr(ast_node, c.parent_relation, node)
                if hasattr(n.ast_node, 'lineno'):
                    ori2new[n.ast_node] = ast_node
            
            for n in self.changes['OnlyRemove']:
                if n.parent not in parents:
                    if n.parent.type == 'keyword' and n.parent_relation == 'value':
                        call = n.parent.parent
                        ast_node = deepcopy(call.ast_node)
                        keyword = n.parent.ast_node
                        node = getattr(ast_node, 'keywords')
                        remove_node = None
                        for n in node:
                            if ASTDiffer.compare(n, keyword):
                                remove_node = n
                                break
                        node.remove(remove_node)
                        setattr(ast_node, 'keywords', node)
                        node = getattr(ast_node, 'args')
                        index = 0
                        for i, n in enumerate(node):
                            if n.lineno > keyword.lineno or n.col_offset > keyword.col_offset:
                                index = i
                                break
                        node = node[:index] + [ast.Name(id = keyword.arg)] + node[index:]
                        setattr(ast_node, 'args', node)
                        ori2new[call.ast_node] = ast_node
                    elif hasattr(n.ast_node, 'lineno'):  
                        ori2new[n.ast_node] = None
            
            return [ori2new], {}
        elif 'OnlyAdd' in self.changes:
            ori2new = {}
            ast_node = deepcopy(self.parent[0])
            morenodes = {}
            new_nodes = []
            for n in self.changes['OnlyAdd']:
                self.morenodes = {}
                new_node = self.build_ast_node(n, None)
                morenodes[self.parent[0]] = self.morenodes
                new_nodes.append(new_node)
            node = getattr(ast_node, self.parent[1])
            if not after:
                if self.parent[2] != -1:
                    node = node[:self.parent[2]] + new_nodes + node[self.parent[2]:]
                else:
                    node = node + new_nodes
            else:
                if self.parent[2] != -1:
                    temp = node[:self.parent[2] + 1] + new_nodes
                    if self.parent[2] + 1 < len(node):
                        temp += node[self.parent[2] + 1:]
                    node = temp
                else:
                    node = node + new_nodes
            setattr(ast_node, self.parent[1], node)
            ori2new[self.parent[0]] = ast_node
            ast.fix_missing_locations(ast_node)
            morenodes, opnodes = self.handle_ops(morenodes)
            mutated_ori2new = self.mutate(ori2new, morenodes)
            max_index = []
            for n in mutated_ori2new:
                max_index.append(len(mutated_ori2new[n]))
            cases = self.gen_index(max_index, extra = False)
            ori2news = []
            for c in cases:
                temp = {}
                for i, o in enumerate(mutated_ori2new):
                    temp[o] = mutated_ori2new[o][c[i]]
                ori2news.append(temp)

            return ori2news, opnodes
        elif 'Insert' in self.changes:
            replaced = self.changes['Insert']
            ori2new = {}
            morenodes = {}
            for n in replaced:
                self.morenodes = {}
                new_node = self.build_ast_node(n, None)
                morenodes[replaced[n][0].ast_node] = self.morenodes
                ast.fix_missing_locations(new_node)
                ori2new[replaced[n][0].ast_node] = new_node
                if len(replaced[n]) > 1:
                    for i in range(1, len(replaced[n])):
                        ori2new[replaced[n][i].ast_node] = None
                        morenodes[replaced[n][i].ast_node] = {}
            morenodes, opnodes = self.handle_ops(morenodes)
            mutated_ori2new = self.mutate(ori2new, morenodes)
            max_index = []
            for n in mutated_ori2new:
                max_index.append(len(mutated_ori2new[n]))
            cases = self.gen_index(max_index, extra = False)
            ori2news = []
            for c in cases:
                temp = {}
                for i, o in enumerate(mutated_ori2new):
                    temp[o] = mutated_ori2new[o][c[i]]
                ori2news.append(temp)

            return ori2news, opnodes









            

                

