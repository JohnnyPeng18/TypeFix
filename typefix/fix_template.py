import json
import os
import ast
import re
from copy import deepcopy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings
from change_tree import ChangeNode, ChangeTree, ChangePair


class TemplateNode(object):
    def __init__(self, basetype, optional = False, t = None):
        # Base Types:
        # Root - The root node of a template tree
        # Variable - Nodes representing variables
        # Op - Nodes representing operations
        # Literal - Node representing literals
        # Builtin - Node representing builtin keywords and names
        # Type - Node representing standard types
        # Attribute - Node representing the attributes of a variable or literal
        # Module - Node representing imported modules
        # Keyword - Node representing keyword used in function calls
        # End_Expr - Node representing the set of Variable, Op, Builtin, Type, Attribute, Module, Keyword
        # Expr - Node representing expressions
        # Stmt - Node representing statements
        self.base_type = basetype
        if self.base_type not in ['Stmt', 'Expr', 'End_Expr']:
            self.type = self.base_type
        else:
            self.type = t

        # Tree Types:
        # Before - The before tree
        # After - The after tree
        # Within_Context - The within context tree
        # Before_Context - The before context tree
        # After_Context - The after context tree
        self.tree_type = None

        # Used in nodes in after parts indicating the same nodes in before parts
        self.refer_to = []
        # Used in nodes in before parts indicating the same nodes in after parts
        self.referred_from = []
        # Used in nodes in both before and after parts indicating the same nodes in contexts
        self.context_refer = []
        # Used in nodes in the same tree
        self.self_refer = []

        # Used in attribute nodes indicating attribute or variable nodes with a prefix name of this node
        self.attribute_refer_to = {}
        # Used in nodes that are referred to by an attribute nodes
        self.attribute_referred_from = []

        if self.type == 'Root':
            self.children = {'body': []}
        else:
            self.children = {}
        # Value must be None if there is any children, except for variable with an annotation
        self.value = None
        self.ast_type = None

        self.ori_nodes = []
        self.ori_refer_to = []
        self.ori_referred_from = []
        self.ori_context_refer = []
        self.ori_self_refer = []

        self.value_abstracted = False
        self.type_abstracted = False
        self.partial = False
        self.asname = None
        self.ctx = None
        self.optional = optional

        self.within_context_relation = []

        self.parent = None
        self.parent_relation = None

        self.id = None
        self.template_id = None
    
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
                self.ctx = expr.ctx
                self.value = expr.field_children['id']
            elif expr.field_children['id'] in stdtypes:
                self.type = 'Type'
                self.base_type = 'Type'
                self.ctx = expr.ctx
                self.value = expr.field_children['id']
            else:
                self.type = 'Builtin'
                self.base_type = 'Builtin'
                self.ctx = expr.ctx
                self.value = expr.field_children['id']

        elif type(expr.node) == ast.arg:
            self.type = 'Variable'
            self.base_type = 'Variable'
            self.value = expr.field_children['arg']
            
        elif type(expr.node) == ast.Attribute:
            self.type = 'Attribute'
            self.ctx = expr.ctx
            self.base_type = 'Attribute'
            #self.type = 'Variable'
            #self.base_type = 'Variable'
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
        elif type(expr.node) == ast.keyword:
            node = TemplateNode('Expr')
            node.build_from_expr(expr.expr_children[0], partial = partial)
            node.partial = partial
            node.parent = self
            node.parent_relation = 'value'
            self.children['value'] = [node]
            if 'arg' in expr.field_children:
                node = TemplateNode('Keyword')
                node.value = expr.field_children['arg']
                node.partial = partial
                node.parent = self
                node.parent_relation = 'arg'
                self.children['arg'] = [node]
        if type(expr.node) not in [ast.Attribute, ast.keyword]:
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
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type or a.asname != b.asname or a.tree_type != b.tree_type or \
        a.ctx != b.ctx or a.within_context_relation != b.within_context_relation or len(a.children) != len(b.children):
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

    @staticmethod
    def self_compare(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return False
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type or a.base_type != b.base_type:
            return False
        return True

    def resolve_name(self):
        name = f'{self.type} ({self.template_id}-{self.id})'
        if self.ctx != None:
            name += ' ({})'.format(str(self.ctx))
        if self.value != None or self.type == 'Literal':
            name += '\n{}'.format(str(self.value))
        if len(self.ori_nodes) > 0:
            name += '\n[ori_nodes:'
            for n in self.ori_nodes:
                name += f'{n.template_id}-{n.id},'
            name = name[:-1]
            name += ']'
        if len(self.refer_to) > 0:
            name += '\n[refer_to:'
            for n in self.refer_to:
                name += f'{n.template_id}-{n.id},'
            name = name[:-1]
            name += ']'
        if len(self.referred_from) > 0:
            name += '\n[referred_from:'
            for n in self.referred_from:
                name += f'{n.template_id}-{n.id},'
            name = name[:-1]
            name += ']'
        if len(self.context_refer) > 0:
            name += '\n[context_refer:'
            for n in self.context_refer:
                name += f'{n.template_id}-{n.id},'
            name = name[:-1]
            name += ']'
        if len(self.self_refer) > 0:
            name += '\n[self_refer:'
            for n in self.self_refer:
                name += f'{n.template_id}-{n.id},'
            name = name[:-1]
            name += ']'

        return name

    def soft_copy(self):
        newnode = TemplateNode(self.base_type)
        newnode.type = self.type
        newnode.tree_type = self.tree_type
        newnode.value = self.value
        newnode.ast_type = self.ast_type
        newnode.value_abstracted = self.value_abstracted
        newnode.type_abstracted = self.type_abstracted
        newnode.asname = self.asname
        newnode.partial = self.partial
        newnode.ctx = self.ctx
        newnode.within_context_relation = self.within_context_relation
        return newnode


    def get_id(self):
        return f'{self.template_id}-{self.id}'

    @staticmethod
    def get_same_subnode(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return None
        if TemplateNode.self_compare(a, b):
            node = a.soft_copy()
            for c in a.children:
                if c in b.children and len(a.children[c]) == len(b.children[c]):
                    fail = False
                    for i in range(0, len(a.children[c])):
                        child = TemplateNode.get_same_subnode(a.children[c][i], b.children[c][i])
                        if child != None:
                            if c not in node.children:
                                node.children[c] = []
                            node.children[c].append(child)
                            child.parent = node
                            child.parent_relation = c
                        else:
                            fail = True
                            break
                    if fail and c in node.children:
                        del node.children[c]
            if node.type == 'Root' and ('body' not in node.children or len(node.children['body']) == 0):
                return None
            return node
        else:
            return None
        
    def has_reference_for_self(self):
        if len(self.refer_to) == 0 and len(self.referred_from) == 0 and len(self.context_refer) == 0 and\
            len(self.attribute_refer_to) == 0 and len(self.attribute_referred_from) == 0 and len(self.self_refer) == 0:
            return False
        else:
            return True

    def has_reference_for_all_children(self):
        reference = False
        for c in self.children:
            for n in self.children[c]:
                if n.has_reference_for_self() or n.has_reference_for_all_children():
                    reference = True
                    break
            if reference:
                break
        return reference


    def prune_no_ref_children(self):
        # Cut the children whose subtree has no reference
        if not self.has_reference_for_self() and not self.has_reference_for_all_children():
            raise ValueError('This node has no reference for itself and its children, should be pruned before calling this API.')
        removed_key = []
        for c in self.children:
            new_children = []
            for n in self.children[c]:
                if n.has_reference_for_self() or n.has_reference_for_all_children():
                    n.prune_no_ref_children()
                    new_children.append(n)
            if len(new_children) == 0:
                removed_key.append(c)
            else:
                self.children[c] = new_children
        
        for k in removed_key:
            del self.children[k]

    @staticmethod
    def get_children_node_num(node):
        nodes = [node]
        num = 0
        while(len(nodes) > 0):
            n = nodes[0]
            nodes = nodes[1:]
            num += 1
            for c in n.children:
                nodes += n.children[c]
        
        return num

    @staticmethod
    def exist_same(a, listb):
        for b in listb:
            if TemplateNode.compare(a, b):
                return True
        
        return False

            





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

        self.same_node_abstraction = {}


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
        self.variables = []
        self.literals = []
        self.ops = []
        self.attributes = []
        self.builtins = []
        self.modules = []
        self.exprs = []
        self.stmts = []
        nodes = self.root.children['body']
        while(len(nodes) > 0):
            node = nodes[0]
            nodes = nodes[1:]
            if node.base_type == 'Variable':
                self.variables.append(node)
            elif node.base_type == 'Attribute':
                self.attributes.append(node)
            elif node.base_type == 'Builtin':
                self.builtins.append(node)
            elif node.base_type == 'Literal':
                self.literals.append(node)
            elif node.base_type == 'Module':
                self.modules.append(node)
            elif node.base_type == 'Op':
                self.ops.append(node)
            elif node.base_type == 'Expr':
                self.ops.append(node)
            elif node.base_type == 'Stmt':
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


    def set_treetype(self, tree_type):
        for n in self.iter_nodes():
            n.tree_type = tree_type

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

    def prune_no_ref_subtree(self):
        self.root.prune_no_ref_children()
        self.collect_special_nodes()

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

    '''
    Get the number of node with the same type from the leaf to the root
    '''
    @staticmethod
    def get_similar_node_num_down_top(a, b):
        if not isinstance(a, TemplateTree) or not isinstance(b, TemplateTree):
            raise TypeError('Input must be two TemplateTree objects, but get {} and {}'.format(type(a), type(b)))
        a_leaf_paths = a.get_leaf_paths()
        b_leaf_paths = b.get_leaf_paths()
        same_node_map = {}
        total_num = 0
        for a_leaf in a_leaf_paths:
            same_node_map[a_leaf] = {}
            for b_leaf in b_leaf_paths:
                num = 0
                for i in range(0, min(len(a_leaf_paths[a_leaf]), len(b_leaf_paths[b_leaf]))):
                    if isinstance(a_leaf_paths[a_leaf][i], TemplateNode) and isinstance(b_leaf_paths[b_leaf][i], TemplateNode):
                        if a_leaf_paths[a_leaf][i].tree_type == 'Within_Context' and set(a_leaf_paths[a_leaf][i].within_context_relation) == set(b_leaf_paths[b_leaf][i].within_context_relation) and a_leaf_paths[a_leaf][i].type == b_leaf_paths[b_leaf][i].type and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        elif a_leaf_paths[a_leaf][i].tree_type != 'Within_Context' and a_leaf_paths[a_leaf][i].type == b_leaf_paths[b_leaf][i].type and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        else:
                            break
                    elif isinstance(a_leaf_paths[a_leaf][i], str) and isinstance(b_leaf_paths[b_leaf][i], str) and a_leaf_paths[a_leaf][i] != b_leaf_paths[b_leaf][i]:
                        break
                same_node_map[a_leaf][b_leaf] = num
        
        reserved_a = list(a_leaf_paths.keys())
        reserved_b = list(b_leaf_paths.keys())
        match_num = 0
        pairs = []
        while(len(reserved_a) > 0 and len(reserved_b) > 0):
            max_num = -9999
            max_a = None
            max_b = None
            for a_leaf in reserved_a:
                for b_leaf in reserved_b:
                    if same_node_map[a_leaf][b_leaf] > max_num:
                        max_num = same_node_map[a_leaf][b_leaf]
                        max_a = a_leaf
                        max_b = b_leaf
            pairs.append([max_a, max_b, max_num])
            match_num += max_num
            reserved_a.remove(max_a)
            reserved_b.remove(max_b)

        total_num += a.get_node_num_for_leaf_paths()
        total_num += b.get_node_num_for_leaf_paths()

        #print('similar: {}/{}.'.format(match_num, total_num))
        return match_num, total_num, pairs

    '''
    Get the number of totally same node from the leaf to the root
    '''
    @staticmethod
    def get_same_node_num_down_top(a, b):
        if not isinstance(a, TemplateTree) or not isinstance(b, TemplateTree):
            raise TypeError('Input must be two TemplateTree objects, but get {} and {}'.format(type(a), type(b)))
        a_leaf_paths = a.get_leaf_paths()
        b_leaf_paths = b.get_leaf_paths()
        same_node_map = {}
        total_num = 0
        for a_leaf in a_leaf_paths:
            same_node_map[a_leaf] = {}
            for b_leaf in b_leaf_paths:
                num = 0
                for i in range(0, min(len(a_leaf_paths[a_leaf]), len(b_leaf_paths[b_leaf]))):
                    if isinstance(a_leaf_paths[a_leaf][i], TemplateNode) and isinstance(b_leaf_paths[b_leaf][i], TemplateNode):
                        if a_leaf_paths[a_leaf][i].tree_type == 'Within_Context' and set(a_leaf_paths[a_leaf][i].within_context_relation) == set(b_leaf_paths[b_leaf][i].within_context_relation) and TemplateNode.self_compare(a_leaf_paths[a_leaf][i], b_leaf_paths[b_leaf][i]) and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        elif a_leaf_paths[a_leaf][i].tree_type != 'Within_Context' and TemplateNode.self_compare(a_leaf_paths[a_leaf][i], b_leaf_paths[b_leaf][i]) and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        else:
                            break
                    elif isinstance(a_leaf_paths[a_leaf][i], str) and isinstance(b_leaf_paths[b_leaf][i], str) and a_leaf_paths[a_leaf][i] != b_leaf_paths[b_leaf][i]:
                        break
                same_node_map[a_leaf][b_leaf] = num
        reserved_a = list(a_leaf_paths.keys())
        reserved_b = list(b_leaf_paths.keys())
        match_num = 0
        pairs = []
        while(len(reserved_a) > 0 and len(reserved_b) > 0):
            max_num = -9999
            max_a = None
            max_b = None
            for a_leaf in reserved_a:
                for b_leaf in reserved_b:
                    if same_node_map[a_leaf][b_leaf] > max_num:
                        max_num = same_node_map[a_leaf][b_leaf]
                        max_a = a_leaf
                        max_b = b_leaf
            pairs.append([max_a, max_b, max_num])
            match_num += max_num
            reserved_a.remove(max_a)
            reserved_b.remove(max_b)

        total_num += a.get_node_num_for_leaf_paths()
        total_num += b.get_node_num_for_leaf_paths()

        #print('same: {}/{}.'.format(match_num, total_num))

        return match_num, total_num, pairs

    '''
    Get the number of node with the same type from the root to the leaf
    '''
    @staticmethod
    def get_similar_node_num_top_down(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return False
        if a.type == b.type:
            if len(a.children) == len(b.children) and len(a.children) == 0:
                return 2
            elif len(a.children) == 0 and len(b.children) != 0:
                return 2
            elif len(a.children) != 0 and len(b.children) == 0:
                return 2
            else:
                num = 2
                for c in a.children:
                    if c in b.children and len(a.children[c]) == len(b.children[c]):
                        for i in range(0, len(a.children[c])):
                            num += TemplateTree.get_similar_node_num_top_down(a.children[c][i], b.children[c][i])
                return num   
        else:
            return 0   

    '''
    Get the number of totally same node from the root to the leaf
    '''
    @staticmethod
    def get_same_node_num_top_down(a, b):
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
                            num += TemplateTree.get_same_node_num_top_down(a.children[c][i], b.children[c][i])
                
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
                path += [cur_node, cur_node.parent_relation, cur_node.parent.children[cur_node.parent_relation].index(cur_node)]
                cur_node = cur_node.parent
                if cur_node == None:
                    raise ValueError('Parents of some nodes are None.')
            path.append(cur_node)
            paths[n] = path
        
        return paths
    
    def get_node_num_for_leaf_paths(self):
        leaf_paths = self.get_leaf_paths()
        num = 0
        for leaf in leaf_paths:
            for n in leaf_paths[leaf]:
                if isinstance(n, TemplateNode) and n.type != 'Root':
                    num += 1
        
        return num


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

    @staticmethod
    def get_same_subtree(a, b):
        if a == None or b == None:
            return None
        node = TemplateNode.get_same_subnode(a.root, b.root)
        if node == None:
            return None
        else:
            tree = TemplateTree()
            tree.root = node
            tree.collect_special_nodes()
            return tree

    @staticmethod
    def subtract_subtree(a, b):
        # Subtract a subtree a from tree b
        tree = TemplateTree()
        tree.root = TemplateNode('Root')
        a_leafpaths = a.get_leaf_paths()
        for n in a_leafpaths:
            path = a_leafpaths[n][::-1]
            curnode = b.root
            for i in path:
                if isinstance(i, TemplateNode):
                    relation = None
                    index = None
                if isinstance(i, str):
                    relation = i
                    curnode = curnode.children[relation][index]
                if isinstance(i, int):
                    index = i   
            body = []
            for c in curnode.children:
                body += curnode.children[c]
            tree.root.children['body'] += body

        context_relations = []
        
        for n in tree.root.children['body']:
            context_relations.append(n.parent_relation)
            n.parent.within_context_relation.append(n.parent_relation)
            n.parent = tree.root
            n.parent_relation = 'body'
        
        if len(tree.root.children['body']) == 0:
            return None, None

        return tree, context_relations

    @staticmethod
    def exist_same(a, listb):
        for b in listb:
            if TemplateTree.compare(a, b):
                return True

        return False

    def dump(self):
        leaf_paths = self.get_leaf_paths()
        texts = []
        for n in leaf_paths:
            path = leaf_paths[n][::-1]
            text = ""
            for i in path:
                if isinstance(i, TemplateNode):
                    if i.value != None:
                        text += '({} | {})'.format(i.type, i.value)
                    else:
                        text += f'({i.type})'
                elif isinstance(i, str):
                    text += f'{i}->'
                else:
                    text += '->'
            texts.append(text)

        return texts




class Context(object):
    def __init__(self, context_tree, relationship, context_type):
        self.context_tree = context_tree

        # Only within context have relationship
        self.relationship = relationship
        # Type:
        # Before - contexts before the changed location
        # After - contexts after the changed location
        # Within - contexts in the changed location, i.e., the part in the statement that does not change
        self.type = context_type

        if self.type != 'Within':
            self.prune_stmt_nodes()
            self.prune_same_stmts()


    def prune_stmt_nodes(self):
        newbody = []
        for i in range(0, len(self.context_tree.root.children['body'])):
            curnode = self.context_tree.root.children['body'][i]
            while True:
                if curnode.base_type == 'Stmt' and len(curnode.children) == 1 and len(curnode.children[list(curnode.children.keys())[0]]) == 1 and curnode.children[list(curnode.children.keys())[0]][0].base_type == 'Stmt':
                    curnode = curnode.children[list(curnode.children.keys())[0]][0]
                else:
                    break
            newbody.append(curnode)
            curnode.parent = self.context_tree.root
            curnode.parent_relation = 'body'
        self.context_tree.root.children['body'] = newbody


    @staticmethod
    def build_external_context(template_trees, context_type):
        if len(template_trees) == 0:
            return None
        for t in  template_trees:
            if not isinstance(t, TemplateTree):
                raise ValueError('Context object must be built from TemplateTree lists.')
        context_tree = TemplateTree()
        context_tree.root = TemplateNode('Root')
        for t in template_trees:
            context_tree.root.children['body'] += t.root.children['body']
        
        return Context(context_tree, None, context_type)

    def prune_same_stmts(self):
        newbody = []
        oldbody = []
        for n in self.context_tree.root.children['body']:
            if not TemplateNode.exist_same(n, newbody):
                newbody.append(n)
            else:
                oldbody.append(n)
        
        nodes = oldbody
        while(len(nodes) > 0):
            n = nodes[0]
            nodes = nodes[1:]
            for nn in n.refer_to:
                nn.context_refer.remove(n)
            for c in n.children:
                nodes += n.children[c]
        
        self.context_tree.root.children['body'] = newbody


        
        
        
                    







            
        
        



                

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

        # Contexts before change
        self.before_contexts = None
        # Contexts after change
        self.after_contexts = None
        # Contexts within change
        self.within_context = None

        # ChangePair instances belonging to this template
        self.instances = []

        # Fix templates generalized to this template
        self.child_templates = []
        # Fix template that this template generalized to
        self.parent_template = None

        self.id = None
        self.abstracted = False

        self.node_index = 1
    
    def add_instance(self, instance):
        if instance not in self.instances and isinstance(instance, ChangePair):
            self.instances.append(instance)

    def cal_self_reference(self):
        if self.before:
            self.before.collect_special_nodes()
            clusters = []
            checked = {}
            for i, n in enumerate(self.before.variables):
                if i in checked:
                    continue
                cluster = []
                for j in range(i + 1, len(self.before.variables)):
                    if TemplateNode.self_compare(n, self.before.variables[j]) and j not in checked:
                        checked[j] = 1
                        cluster.append(self.before.variables[j])
                if len(cluster) > 0:
                    clusters.append(cluster + [n])
                    checked[i] = 1
            for c in clusters:
                for n in c:
                    for nn in c:
                        if n == nn:
                            continue
                        else:
                            n.self_refer.append(nn)

        if self.after:
            self.after.collect_special_nodes()
            clusters = []
            checked = {}
            for i, n in enumerate(self.after.variables):
                if i in checked:
                    continue
                cluster = []
                for j in range(i + 1, len(self.after.variables)):
                    if TemplateNode.self_compare(n, self.after.variables[j]) and j not in checked:
                        checked[j] = 1
                        cluster.append(self.after.variables[j])
                if len(cluster) > 0:
                    clusters.append(cluster + [n])
                    checked[i] = 1
            for c in clusters:
                for n in c:
                    for nn in c:
                        if n == nn:
                            continue
                        else:
                            n.self_refer.append(nn)

    def set_node_ids(self):
        if self.before:
            for n in self.before.iter_nodes():
                n.template_id = self.id
                n.id = self.node_index
                self.node_index += 1
        if self.after:
            for n in self.after.iter_nodes():
                n.template_id = self.id
                n.id = self.node_index
                self.node_index += 1
        if self.within_context:
            for n in self.within_context.context_tree.iter_nodes():
                n.template_id = self.id
                n.id = self.node_index
                self.node_index += 1
        if self.before_contexts:
            for n in self.before_contexts.context_tree.iter_nodes():
                n.template_id = self.id
                n.id = self.node_index
                self.node_index += 1
        if self.after_contexts:
            for n in self.after_contexts.context_tree.iter_nodes():
                n.template_id = self.id
                n.id = self.node_index
                self.node_index += 1


    def merge(self, fix_templates, fixed_id2template):
        for t in fix_templates:
            if not isinstance(t, FixTemplate):
                continue
            if t.abstracted:
                self.abstracted = True
                fixed_id2template[t.id].abstracted = True
            self.child_templates.append(t.id)
            fixed_id2template[t.id].parent_template = self.id
            for i in t.instances:
                if not isinstance(i, ChangePair):
                    continue
                if i not in self.instances:
                    self.instances.append(i)
        return fixed_id2template

    def recover_reference(self):
        old2new = {}
        all_nodes = {}
        if self.before:
            for n in self.before.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n.get_id()] = n
                all_nodes[n.get_id()] = n
        if self.after:
            for n in self.after.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n.get_id()] = n
                all_nodes[n.get_id()] = n
        if self.within_context:
            for n in self.within_context.context_tree.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n.get_id()] = n
                all_nodes[n.get_id()] = n
        if self.before_contexts:
            for n in self.before_contexts.context_tree.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n.get_id()] = n
                all_nodes[n.get_id()] = n
        if self.after_contexts:
            for n in self.after_contexts.context_tree.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n.get_id()] = n
                all_nodes[n.get_id()] = n
        if self.before:
            for n in self.before.iter_nodes():
                old_referred_from = n.referred_from
                n.referred_from = []
                for old_n in n.ori_referred_from + old_referred_from:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.referred_from:
                        n.referred_from.append(new_n)
                n.ori_referred_from = []
                old_refer_to = n.refer_to
                n.refer_to = []
                for old_n in n.ori_refer_to + old_refer_to:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id()in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.refer_to:
                        n.refer_to.append(new_n)
                n.ori_refer_to = []
                old_context_refer = n.context_refer
                n.context_refer = []
                for old_n in n.ori_context_refer + old_context_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id()in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.context_refer:
                        n.context_refer.append(new_n)
                    if new_n.value != n.value:
                        new_n.value = n.value
                n.ori_context_refer = []
                old_self_refer = n.self_refer
                n.self_refer = []
                for old_n in n.ori_self_refer + old_self_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id()in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.self_refer:
                        n.self_refer.append(new_n)
                n.ori_context_refer = []
        if self.after:
            for n in self.after.iter_nodes():
                old_referred_from = n.referred_from
                n.referred_from = []
                for old_n in n.ori_referred_from + old_referred_from:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.referred_from:
                        n.referred_from.append(new_n)
                n.ori_referred_from = []
                old_refer_to = n.refer_to
                n.refer_to = []
                for old_n in n.ori_refer_to + old_refer_to:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.refer_to:
                        n.refer_to.append(new_n)
                n.ori_refer_to = []
                old_context_refer = n.context_refer
                n.context_refer = []
                for old_n in n.ori_context_refer + old_context_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.context_refer:
                        n.context_refer.append(new_n)
                    if new_n.value != n.value:
                        new_n.value = n.value
                n.ori_context_refer = []
                old_self_refer = n.self_refer
                n.self_refer = []
                for old_n in n.ori_self_refer + old_self_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.self_refer:
                        n.self_refer.append(new_n)
                n.ori_context_refer = []
        if self.within_context:
            for n in self.within_context.context_tree.iter_nodes():
                old_refer_to = n.refer_to
                n.refer_to = []
                for old_n in n.ori_refer_to + old_refer_to:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.refer_to:
                        n.refer_to.append(new_n)
                pairs = []
                for old_n in n.refer_to:
                    if old_n in old2new:
                        pairs.append([old_n, old2new[old_n]])
                for p in pairs:
                    n.refer_to.remove(p[0])
                    n.refer_to.append(p[1])
                    if p[1].value != n.value:
                        n.value = p[1].value
                n.ori_refer_to = []
                old_self_refer = n.self_refer
                n.self_refer = []
                for old_n in n.ori_self_refer + old_self_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.self_refer:
                        n.self_refer.append(new_n)
                n.ori_self_refer = []
        if self.before_contexts:
            for n in self.before_contexts.context_tree.iter_nodes():
                old_refer_to = n.refer_to
                n.refer_to = []
                for old_n in n.ori_refer_to + old_refer_to:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.refer_to:
                        n.refer_to.append(new_n)
                pairs = []
                for old_n in n.refer_to:
                    if old_n in old2new:
                        pairs.append([old_n, old2new[old_n]])
                for p in pairs:
                    n.refer_to.remove(p[0])
                    n.refer_to.append(p[1])
                    if p[1].value != n.value:
                        n.value = p[1].value
                n.ori_refer_to = []
                old_self_refer = n.self_refer
                n.self_refer = []
                for old_n in n.ori_self_refer + old_self_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.self_refer:
                        n.self_refer.append(new_n)
                n.ori_self_refer = []
        if self.after_contexts:
            for n in self.after_contexts.context_tree.iter_nodes():
                old_refer_to = n.refer_to
                n.refer_to = []
                for old_n in n.ori_refer_to + old_refer_to:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.refer_to:
                        n.refer_to.append(new_n)
                pairs = []
                for old_n in n.refer_to:
                    if old_n in old2new:
                        pairs.append([old_n, old2new[old_n]])
                for p in pairs:
                    n.refer_to.remove(p[0])
                    n.refer_to.append(p[1])
                    if p[1].value != n.value:
                        n.value = p[1].value
                n.ori_refer_to = []
                old_self_refer = n.self_refer
                n.self_refer = []
                for old_n in n.ori_self_refer + old_self_refer:
                    if old_n.get_id() not in old2new and old_n.get_id() not in all_nodes:
                        continue
                    new_n = old2new[old_n.get_id()] if old_n.get_id() in old2new else all_nodes[old_n.get_id()]
                    if new_n not in n.self_refer:
                        n.self_refer.append(new_n)
                n.ori_self_refer = []

    def set_treetype(self):
        if self.before:
            self.before.set_treetype('Before')
        if self.after:
            self.after.set_treetype('After')
        if self.within_context:
            self.within_context.context_tree.set_treetype('Within_Context')
        if self.before_contexts:
            self.before_contexts.context_tree.set_treetype('Before_Context')
        if self.after_contexts:
            self.after_contexts.context_tree.set_treetype('After_Context')
    
    def get_child_template_ids(self, id2template):
        ids = []
        templates = self.child_templates
        while(len(templates) > 0):
            i = templates[0]
            templates = templates[1:]
            ids.append(i)
            templates += id2template[i].child_templates

        return ids


    @staticmethod
    def get_distance_for_pattern(a, b):
        same_node_num = 0
        if a.before != None and b.before != None:
            same_node_num += TemplateTree.get_same_node_num_top_down(a.before.root, b.before.root)
        if a.after != None and b.after != None:
            same_node_num += TemplateTree.get_same_node_num_top_down(a.after.root, b.after.root)

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

    @staticmethod
    def get_structural_distance_for_pattern(a, b):
        same_node_num = 0
        if a.before != None and b.before != None:
            same_node_num += TemplateTree.get_similar_node_num_top_down(a.before.root, b.before.root)
        if a.after != None and b.after != None:
            same_node_num += TemplateTree.get_similar_node_num_top_down(a.after.root, b.after.root)

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

    @staticmethod
    def get_distance_for_context(a, b):
        distance = {'within': 0.0, 'before': 0.0, 'after': 0.0, 'external': 0.0}
        pairs = {'within': [], 'before': [], 'after': []}
        if a.within_context != None and b.within_context != None:
            match_num, total_num, pair = TemplateTree.get_same_node_num_down_top(a.within_context.context_tree, b.within_context.context_tree)
            distance['within'] = match_num * 2 / total_num
            pairs['within'] = pair
        elif a.within_context != b.within_context:
            distance['within'] = -9999
        elif a.within_context == None and b.within_context == None:
            distance['within'] = 1.0
        if a.before_contexts != None and b.before_contexts != None:
            before_match_num, before_total_num, before_pair = TemplateTree.get_same_node_num_down_top(a.before_contexts.context_tree, b.before_contexts.context_tree)
            pairs['before'] = before_pair
        else:
            before_total_num = 0
            if a.before_contexts:
                before_total_num += a.before_contexts.context_tree.get_node_num_for_leaf_paths()
            if b.before_contexts:
                before_total_num += b.before_contexts.context_tree.get_node_num_for_leaf_paths()
            before_match_num = 0
        distance['before'] = (before_match_num * 2 + 1) / (before_total_num + 1)
        if a.after_contexts != None and b.after_contexts != None:
            after_match_num, after_total_num, after_pair = TemplateTree.get_same_node_num_down_top(a.after_contexts.context_tree, b.after_contexts.context_tree)
            pairs['after'] = after_pair
        else:
            after_match_num = 0
            after_total_num = 0
            if a.after_contexts:
                after_total_num += a.after_contexts.context_tree.get_node_num_for_leaf_paths()
            if b.after_contexts:
                after_total_num += b.after_contexts.context_tree.get_node_num_for_leaf_paths()
        distance['after'] = (after_match_num * 2 + 1) / (after_total_num + 1)
        if before_total_num + after_total_num > 0:
            distance['external'] = ((before_match_num + after_match_num) * 2 + 1) / (before_total_num + after_total_num + 1)
        else:
            distance['external'] = 1.0

        return distance, pairs

    @staticmethod
    def get_structural_distance_for_context(a, b):
        distance = {'within': 0.0, 'before': 0.0, 'after': 0.0, 'external': 0.0}
        pairs = {'within': [], 'before': [], 'after': []}
        if a.within_context != None and b.within_context != None:
            match_num, total_num, pair = TemplateTree.get_similar_node_num_down_top(a.within_context.context_tree, b.within_context.context_tree)
            distance['within'] = match_num * 2 / total_num
            pairs['within'] = pair
        elif a.within_context != b.within_context:
            distance['within'] = -9999
        elif a.within_context == None and b.within_context == None:
            distance['within'] = 1.0
        if a.before_contexts != None and b.before_contexts != None:
            before_match_num, before_total_num, before_pair = TemplateTree.get_similar_node_num_down_top(a.before_contexts.context_tree, b.before_contexts.context_tree)
            pairs['before'] = before_pair
        else:
            before_total_num = 0
            if a.before_contexts:
                before_total_num += a.before_contexts.context_tree.get_node_num_for_leaf_paths()
            if b.before_contexts:
                before_total_num += b.before_contexts.context_tree.get_node_num_for_leaf_paths()
            before_match_num = 0
        distance['before'] = (before_match_num * 2 + 1) / (before_total_num + 1)
        if a.after_contexts != None and b.after_contexts != None:
            after_match_num, after_total_num, after_pair = TemplateTree.get_similar_node_num_down_top(a.after_contexts.context_tree, b.after_contexts.context_tree)
            pairs['after'] = after_pair
        else:
            after_match_num = 0
            after_total_num = 0
            if a.after_contexts:
                after_total_num += a.after_contexts.context_tree.get_node_num_for_leaf_paths()
            if b.after_contexts:
                after_total_num += b.after_contexts.context_tree.get_node_num_for_leaf_paths()
        distance['after'] = (after_match_num * 2 + 1) / (after_total_num + 1)
        if before_total_num + after_total_num > 0:
            distance['external'] = ((before_match_num + after_match_num) * 2 + 1) / (before_total_num + after_total_num + 1)
        else:
            distance['external'] = 1.0

        return distance, pairs
        

    def draw(self, id2template, filerepo = None, draw_contexts = False, draw_instance = False):
        if self.parent_template == None:
            filename = 'FINAL_FIX_TEMPLATE_{}'.format(self.id)
        else:
            filename = 'FIX_TEMPLATE_{}'.format(self.id)
        if filerepo:
            filename = os.path.join(filerepo, filename)
        nodemap = {}
        index = 0
        f = Digraph("Fix Template", filename = filename)
        p = Digraph('cluster_Pattern', filename)
        p.attr(label = 'Pattern', style = 'filled', color = 'lightgrey')
        p.attr(fontsize = '20')
        if self.before:
            p.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled, dashed')
            p.node(f'node{index}', label = self.before.root.resolve_name())
            nodemap[self.before.root] = f'node{index}'
            index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.before.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        p.edge(nodemap[n], nodemap[cn], label = c)
        if self.after:
            p.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
            p.node(f'node{index}', label = self.after.root.resolve_name())
            nodemap[self.after.root] = f'node{index}'
            index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.after.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        p.edge(nodemap[n], nodemap[cn], label = c)
        f.subgraph(p)
        if self.parent_template == None:
            f.attr(label = f'FINAL - Template ID: {self.id}; Template Category: {self.action}; Instances: {len(self.instances)}')
        else:
            f.attr(label = f'Template ID: {self.id}; Template Category: {self.action}; Instances: {len(self.instances)}')
        f.attr(fontsize = '25')
        
        if draw_contexts:
            c = Digraph("cluster_Context", filename)
            c.attr(label = 'Contexts', style = 'filled', color = 'lightgrey')
            c.attr(fontsize = '20')
            if self.within_context != None:
                c.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
                c.node(f'node{index}', label = self.within_context.context_tree.root.resolve_name())
                nodemap[self.within_context.context_tree.root] = f'node{index}'
                index += 1
                c.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                c.attr('node', shape = 'ellipse', fillcolor = 'cadetblue1', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                c.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                c.attr('node', shape = 'box', fillcolor = 'cadetblue1', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                for n in self.within_context.context_tree.iter_nodes():
                    for cc in n.children:
                        for cn in n.children[cc]:
                            c.edge(nodemap[n], nodemap[cn], label = cc)
            if self.before_contexts:
                bc = Digraph("cluster_Before_Contexts")
                bc.attr(label = f'Before Contexts')
                bc.attr(fontsize = '15')
                bc.attr(color = 'lightsteelblue')
                bc.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
                context = self.before_contexts
                bc.node(f'node{index}', label = context.context_tree.root.resolve_name())
                nodemap[context.context_tree.root] = f'node{index}'
                index += 1
                bc.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                bc.attr('node', shape = 'ellipse', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                bc.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                bc.attr('node', shape = 'box', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                for n in context.context_tree.iter_nodes():
                    for cc in n.children:
                        for cn in n.children[cc]:
                            bc.edge(nodemap[n], nodemap[cn], label = cc)
                c.subgraph(bc)
            if self.after_contexts:
                ac = Digraph("cluster_After_Contexts")
                ac.attr(label = f'After Contexts')
                ac.attr(fontsize = '15')
                ac.attr(color = 'lightskyblue3')
                ac.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
                context = self.after_contexts
                ac.node(f'node{index}', label = context.context_tree.root.resolve_name())
                nodemap[context.context_tree.root] = f'node{index}'
                index += 1
                ac.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                ac.attr('node', shape = 'ellipse', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                ac.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                ac.attr('node', shape = 'box', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name())
                    nodemap[n] = f'node{index}'
                    index += 1
                for n in context.context_tree.iter_nodes():
                    for cc in n.children:
                        for cn in n.children[cc]:
                            ac.edge(nodemap[n], nodemap[cn], label = cc)
                
                c.subgraph(ac)
            
            f.subgraph(c)
        
        l = Digraph('cluster_Clustering', filename)
        l.attr(label = 'Hierarchical Clustering Tree')
        l.attr(fontsize = '20')
        l.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
        template2index = {}
        template_ids = [self.id]
        while(len(template_ids) > 0):
            t = template_ids[0]
            template_ids = template_ids[1:]
            if t not in template2index:
                l.node(f'node{index}', label = str(t))
                template2index[t] = index
                index += 1
            template_ids += id2template[t].child_templates

        template_ids = [self.id]
        while(len(template_ids) > 0):
            t = template_ids[0]
            template_ids = template_ids[1:]
            if id2template[t].parent_template != None and t != self.id:
                l.edge(f'node{template2index[id2template[t].parent_template]}',f'node{template2index[t]}')
            template_ids += id2template[t].child_templates
        
        f.subgraph(l)

        f.render(filename = filename, view = False)

        if draw_instance:
            for i in range(0, len(self.instances)):
                filename = os.path.join(filerepo, 'FIX_TEMPLATE_{}_INSTANCE_{}'.format(self.id, i))
                self.instances[i].draw(filename = filename)
