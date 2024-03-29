import json
import os
import ast
import re
from copy import deepcopy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings, cat2op
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
        # Identifier - Set of Variable, Builtin, Type, Attribute
        # Expr - Node representing expressions
        # Stmt - Node representing statements
        # Reference - Node representing the whole subtree in before tree
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
        self.dfsid = None

        self.within_context_relation = {'before': [], 'after': []}

        self.parent = None
        self.parent_relation = None

        self.id = None
        self.template_id = None

        # Only used in patch generation, not template mining
        self.ast_node = None
        self.before_index = None
        self.after_index = None
    
    def build_from_stmt(self, stmt, partial = False, record_astnode = True):
        self.base_type = 'Stmt'
        self.ast_type = type(stmt.node)
        if record_astnode:
            self.ast_node = stmt.node
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
            node.build_from_stmt(s, partial = partial, record_astnode = record_astnode)
            node.parent = self
            node.parent_relation = s.parent_relation
            if s.parent_relation not in self.children:
                self.children[s.parent_relation] = [node]
            else:
                self.children[s.parent_relation].append(node)
        
        for e in stmt.expr_children:
            if type(e.node) != ast.arguments:
                node = TemplateNode('Expr')
                node.build_from_expr(e, partial = partial, record_astnode = record_astnode)
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
                        node.build_from_expr(arg, partial = partial, record_astnode = record_astnode)
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
                        node.build_from_expr(arg, partial = partial, record_astnode = record_astnode)
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
    

    def build_from_expr(self, expr, partial = False, record_astnode = True):
        self.base_type = 'Expr'
        self.ast_type = type(expr.node)
        if record_astnode:
            self.ast_node = expr.node
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
            if record_astnode:
                node.ast_node = expr.node.op
            self.children['op'] = [node]
        elif type(expr.node) == ast.Compare:
            if isinstance(expr.field_children['ops'], list):
                for i, o in enumerate(expr.field_children['ops']):
                    node = TemplateNode('Op')
                    node.value = o
                    node.partial = partial
                    node.parent = self
                    node.parent_relation = 'op'
                    if record_astnode:
                        node.ast_node = expr.node.ops[i]
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
                if record_astnode:
                    node.ast_node = expr.node.ops[0]
                self.children['op'] = [node]
        elif type(expr.node) == ast.keyword:
            node = TemplateNode('Expr')
            node.build_from_expr(expr.expr_children[0], partial = partial, record_astnode = record_astnode)
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
                node.build_from_expr(e, partial = partial, record_astnode = record_astnode)
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
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type or a.asname != b.asname or len(a.children) != len(b.children):
            return False
        if len(a.children) != len(b.children):
            return False
        if not Context.compare_within_context(a.within_context_relation, b.within_context_relation):
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
        if not TemplateNode.is_type_compatible(a, b):
            return False
        if len(a.children) != len(b.children):
            return False
        if not Context.compare_within_context(a.within_context_relation, b.within_context_relation):
            return False
        for c in a.children:
            if c not in b.children or len(a.children[c]) != len(b.children[c]):
                return False
            for i in range(0, len(a.children[c])):
                if not TemplateNode.value_abstract_compare(a.children[c][i], b.children[c][i]):
                    return False
        return True
    
    @staticmethod
    def is_set_identical(a, b):
        if len(a) == len(b) and len(a) == 0:
            return True
        if len(a) != len(b) or len(a) == 0:
            return False
        if isinstance(a[0], TemplateNode):
            checked = {}
            for t in a:
                for it in b:
                    if TemplateNode.value_abstract_compare(t, it) and t.parent.type == it.parent.type:
                        checked[t] = 1
                        checked[it] = 1
                        break
            for t in b:
                for it in a:
                    if TemplateNode.value_abstract_compare(t, it) and t.parent.type == it.parent.type:
                        checked[t] = 1
                        checked[it] = 1
            for t in a:
                if t not in checked:
                    return False
            for t in b:
                if t not in checked:
                    return False
            
            return True
        
        return False

    @staticmethod
    def self_compare(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return False
        if a.value == 'REFERRED' and b.value == 'REFERRED' and a.type == b.type and a.base_type == b.base_type and a.ast_type == b.ast_type:
            if TemplateNode.is_set_identical(a.referred_from, b.referred_from) and TemplateNode.is_set_identical(a.refer_to, b.refer_to) and TemplateNode.is_set_identical(a.self_refer, b.self_refer):
                return True
            else:
                return False
        if not Context.compare_within_context(a.within_context_relation, b.within_context_relation):
            return False
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type or a.base_type != b.base_type:
            return False
        return True

    def resolve_name(self, dump_attributes = False):
        name = f'{self.type} ({self.template_id}-{self.id})'
        if self.ctx != None:
            name += ' ({})'.format(str(self.ctx))
        if self.value != None or self.type == 'Literal':
            name += '\n{}'.format(str(self.value)[:1000])
        if self.dfsid != None:
            name += '\n DFSID: {}'.format(self.dfsid)
        if self.ast_node != None:
            name += '\n AST Node: {}'.format(self.ast_node)
        if len(self.within_context_relation['before']) > 0 or len(self.within_context_relation['after']) > 0:
            name += '\nwithin_relation: before - {}, after - {}'.format(self.within_context_relation['before'], self.within_context_relation['after'])
        if len(self.ori_nodes) > 0 and dump_attributes:
            name += '\n[ori_nodes:'
            for n in self.ori_nodes:
                name += f'{n},'
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
        if dump_attributes:
            name += '\n' + self.dump_attributes()

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

    def has_refer_to_for_self(self):
        if len(self.refer_to) == 0:
            return False
        else:
            return True

    def has_refer_to_for_all_children(self):
        reference = False
        for c in self.children:
            for n in self.children[c]:
                if n.has_refer_to_for_self() or n.has_refer_to_for_all_children():
                    reference = True
                    break
            if reference:
                break
        return reference

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

    def prune_no_refer_to_children(self):
        if not self.has_refer_to_for_self() and not self.has_refer_to_for_all_children():
            raise ValueError('This node has no reference for itself and its children, should be pruned before calling this API.')
        removed_key = []
        for c in self.children:
            new_children = []
            for n in self.children[c]:
                if n.has_refer_to_for_self() or n.has_refer_to_for_all_children():
                    n.prune_no_refer_to_children()
                    new_children.append(n)
            if len(new_children) == 0:
                removed_key.append(c)
            else:
                self.children[c] = new_children
        
        for k in removed_key:
            del self.children[k]


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

    def get_all_children(self):
        children = []
        for c in self.children:
            for n in self.children[c]:
                children.append(n)
                children += n.get_all_children()
        
        return children

    def get_largest_dfsid(self):
        children = self.get_all_children()
        largest = self.dfsid
        for n in children:
            if n.dfsid > largest:
                largest = n.dfsid
        
        return largest

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

    @staticmethod
    def is_type_compatible(a, b):
        if a.type == b.type:
            return True
        if a.type in ['Variable', 'Attribute', 'Type', 'Builtin', 'Identifier'] and b.type in ['Variable', 'Attribute', 'Type', 'Builtin', 'Identifier']:
            return True
        
        return False

    def dump_attributes(self):
        a = f'base_type:{self.base_type};type:{self.type};value:{self.value};ast_type:{self.ast_type};asname:{self.asname};tree_type:{self.tree_type};ctx:{self.ctx};within_context_relation:{self.within_context_relation}'
        return a

    @staticmethod
    def match(a, b, record_map = False, thres = None):
        # Indicate whether a matches to b
        if (a == None and b != None) or (a != None and b == None):
            if not record_map:
                return False
            else:
                return False, {}
        type_match = False
        value_match = False
        if a.type == b.type:
            type_match = True
        elif b.type == 'Stmt': #and a.base_type == b.type and not a.partial
            type_match = True
            value_match = True
        elif b.type =='Expr' and a.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Expr', 'End_Expr', 'Identifier'] and (len(a.children) == 0 or a.type in ['Subscript', 'Compare', 'BoolOp', 'BinOp', 'Call', 'keyword', 'UnaryOp']):
            type_match = True
            value_match = True
        elif b.type == 'End_Expr' and a.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Identifier'] and (len(a.children) == 0 or a.type in ['Subscript', 'Compare', 'BoolOp', 'BinOp', 'Call', 'keyword', 'UnaryOp']):
            type_match = True
            value_match = True
        elif b.type == 'Identifier' and a.base_type in ['Variable', 'Attribute', 'Type', 'Builtin'] and (len(a.children) == 0 or a.type in ['Subscript', 'Compare', 'BoolOp', 'BinOp', 'Call', 'keyword', 'UnaryOp']):
            type_match = True
            value_match = True
        else:
            type_match = False
        
        
        if a.value == b.value:
            value_match = True
        elif b.value in ['ABSTRACTED', 'REFERRED']:
            value_match = True
        elif b.value_abstracted and type(a.value).__name__ == b.value:
            value_match = True
        elif b.type == 'Op' and a.value in op2cat and op2cat[a.value] == b.value:
            value_match = True
        elif not value_match:
            value_match = False
        
        reference_match = True
        if len(b.self_refer) > 0:
            if len(b.self_refer) > len(a.self_refer):
                reference_match = False
            else:
                selected = {}
                for i, bn in enumerate(b.self_refer):
                    ori = len(selected)
                    for an in a.self_refer:
                        if an in selected:
                            continue
                        #print(bn.parent.type, an.parent.type, bn.parent_relation, an.parent_relation)
                        if (bn.parent_relation == an.parent_relation and TemplateNode.self_match(bn.parent, an.parent)) or (bn.parent.base_type == 'Root'):
                            selected[an] = 1
                            break
                    cur = len(selected)
                    if cur <= ori:
                        reference_match = False
                        break
        
        if type_match and value_match and reference_match:
            if record_map:
                nodemap = {a: b}
            for c in b.children:
                if c not in a.children:
                    if not record_map:
                        return False
                    else:
                        return False, {}
                if len(b.children[c]) > len(a.children[c]):
                    if not record_map:
                        return False
                    else:
                        return False, {}
                else:
                    a_index = 0
                    for bn in b.children[c]:
                        found = False
                        for index in range(a_index, len(a.children[c])):
                            if not record_map:
                                if (thres == None or a.children[c][index].get_largest_dfsid() > thres) and TemplateNode.match(a.children[c][index], bn, thres = thres):
                                    a_index = index + 1
                                    found = True
                                    break
                            elif thres == None or a.children[c][index].get_largest_dfsid() > thres:
                                success, submap = TemplateNode.match(a.children[c][index], bn, record_map = True, thres = thres)
                                if success:
                                    for n in submap:
                                        nodemap[n] = submap[n]
                                    a_index = index + 1
                                    found = True
                                    break
                        if not found:
                            if not record_map:
                                return False
                            else:
                                return False, {}
            if not record_map:
                return True
            else:
                return True, nodemap
        else:
            #print(type_match, value_match, reference_match)
            #print(a.type, b.type)
            if not record_map:
                return False
            else:
                return False, {}

    @staticmethod
    def self_match(a, b):
        # Indicate whether a self matches to b
        if (a == None and b != None) or (a != None and b == None):
            return False
        type_match = False
        value_match = False
        if a.type == b.type:
            type_match = True
        elif b.type == 'Stmt' and a.base_type == b.type and not a.partial:
            type_match = True
            value_match = True
        elif b.type =='Expr' and a.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Expr', 'End_Expr', 'Identifier']  and len(a.children) == 0:
            type_match = True
            value_match = True
        elif b.type == 'End_Expr' and a.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Identifier']  and len(a.children) == 0:
            type_match = True
            value_match = True
        elif b.type == 'Identifier' and a.base_type in ['Variable', 'Attribute', 'Type', 'Builtin'] and len(a.children) == 0:
            type_match = True
            value_match = True
        else:
            type_match = False
        
        
        if a.value == b.value:
            value_match = True
        elif b.value in ['ABSTRACTED', 'REFERRED']:
            value_match = True
        elif b.value_abstracted and type(a.value).__name__ == b.value:
            value_match = True
        elif b.type == 'Op' and a.value in op2cat and op2cat[a.value] == b.value:
            value_match = True
        elif not value_match:
            value_match = False
        
        reference_match = True
        if len(b.self_refer) > 0:
            if len(b.self_refer) > len(a.self_refer):
                reference_match = False
            else:
                selected = {}
                for i, bn in enumerate(b.self_refer):
                    ori = len(selected)
                    for an in a.self_refer:
                        if an in selected:
                            continue
                        if (bn.parent_relation == an.parent_relation and TemplateNode.self_match(bn.parent, an.parent)) or (bn.parent.base_type == 'Root'):
                            selected[an] = 1
                            break
                    cur = len(selected)
                    if cur <= ori:
                        reference_match = False
                        break
        
        if type_match and value_match and reference_match:
            return True
        else:
            return False

    @staticmethod
    def subtree_match(a, b, thres = None):
        # Indicate whether a matches to a subtree of b
        matched = None
        #print(b.dfsid)
        if TemplateNode.match(b, a) and (thres == None or (thres != None and b.dfsid > thres)):
            matched = b
        for c in b.children:
            found = False
            for n in b.children[c]:
                #print(n.type, n.dfsid, thres, a.type)
                sub_n = TemplateNode.subtree_match(a, n, thres = thres)
                if sub_n != None and (thres == None or (thres != None and sub_n.dfsid > thres)):
                    matched = sub_n
                    found = True
                    break
            if found:
                break
        return matched

    @staticmethod
    def subtrees_match(a, b):
        # Indicate whether the subtrees of a matches to the subtree of subtrees of b
        if len(a.children) != len(b.children):
            return None
        subtrees = {}
        cur_dfsid = None
        for c in a.children:
            if c not in b.children:
                return None
            subtrees[c] = []
            for an in a.children[c]:
                #print([t.dfsid for t in subtrees[c]])
                ori_num = len(subtrees[c])
                for bn in b.children[c]:
                    sub_n = TemplateNode.subtree_match(an, bn, cur_dfsid)
                    if sub_n != None:
                        subtrees[c].append(sub_n)
                        cur_dfsid = sub_n.get_largest_dfsid()
                        break
                cur_num = len(subtrees[c])
                if cur_num <= ori_num:
                    return None
        return subtrees
    
    @staticmethod
    def subtrees_match_all_single_match(a, b, thres = None):
        # Indicate whether a matches to a subtree of b
        matched = None
        success, nodemap = TemplateNode.match(b, a, record_map = True, thres = thres)
        if success:
            largest_dfsid = -9999
            for n in nodemap:
                if n.dfsid > largest_dfsid:
                    largest_dfsid = n.dfsid
            if (thres == None or (thres != None and largest_dfsid > thres)):
                if len(nodemap) != len(a.get_all_children()) + 1:
                    raise ValueError('Inconsistent node num: nodemap - {}, a - {}'.format(len(nodemap), len(a.get_all_children()) + 1))
                return b, nodemap
        for c in b.children:
            found = False
            for n in b.children[c]:
                sub_n, nodemap = TemplateNode.subtrees_match_all_single_match(a, n, thres = thres)
                if sub_n != None:
                    largest_dfsid = -9999
                    for n in nodemap:
                        if n.dfsid > largest_dfsid:
                            largest_dfsid = n.dfsid
                    if (thres == None or (thres != None and largest_dfsid > thres)):
                        matched = sub_n
                        found = True
                        break
            if found:
                break
        return matched, nodemap

    @staticmethod
    def subtrees_match_all_single_step(a, b, thres = None):
        if not isinstance(a, list) or not isinstance(b, list):
            raise ValueError('a and b must be lists.')
        an = a[0]
        a = a[1:]
        cur_thres = thres
        trees = {}
        while True:
            found = False
            for bn in b:
                sub_n, nodemap = TemplateNode.subtrees_match_all_single_match(an, bn, thres = cur_thres)
                if sub_n != None:
                    found = True
                    subtree = {'nodemap': nodemap}
                    if sub_n in trees:
                        trees[sub_n].append(subtree)
                    else:
                        trees[sub_n] = [subtree]
                    largest_dfsid = -9999
                    for n in nodemap:
                        if n.dfsid > largest_dfsid:
                            largest_dfsid = n.dfsid
                    cur_dfsid = largest_dfsid
                    if len(a) > 0:
                        sub_ns = TemplateNode.subtrees_match_all_single_step(a, b, thres = sub_n.get_largest_dfsid())
                        if sub_ns != None and len(sub_ns) != 0:
                            subtree['subtree'] = sub_ns
                            break
                        else:
                            trees[sub_n].remove(subtree)
                            if len(trees[sub_n]) == 0:
                                del trees[sub_n]
                            break
            if not found:
                break
            cur_thres = cur_dfsid
        
        if len(trees) == 0:
            return None
        return trees

    @staticmethod
    def unwrap_trees(trees):
        if not isinstance(trees, dict):
            raise ValueError('trees must be dicts instead of {}'.format(trees))
        unwrapped = []
        nodemaps = []
        for t in trees:
            for subtree in trees[t]:
                if 'subtree' in subtree:
                    subtrees, subnodemaps = TemplateNode.unwrap_trees(subtree['subtree'])
                    for s in subtrees:
                        unwrapped.append([t] + s)
                    for m in subnodemaps:
                        newmap = {}
                        for n in subtree['nodemap']:
                            newmap[n] = subtree['nodemap'][n]
                        for n in m:
                            newmap[n] = m[n]
                        nodemaps.append(newmap)
                else:
                    unwrapped.append([t])
                    nodemaps.append(deepcopy(subtree['nodemap']))                
        
        return unwrapped, nodemaps

    @staticmethod
    def validate_nodemap(trees, nodemaps, thres):
        new_trees = []
        new_nodemaps = []

        for i, nodemap in enumerate(nodemaps):
            invalid = False
            hit = {}
            for i in range(0, len(thres) - 1):
                hit[i] = 0
            for n in nodemap:
                if nodemap[n].type == 'Stmt' and n.base_type != 'Stmt':
                    invalid = True
                    break
                if len(thres) > 1:
                    for i in range(0, len(thres) - 1):
                        if n.dfsid in range(thres[i], thres[i+1]):
                            hit[i] += 1
                    for i in hit:
                        if hit[i] == 0:
                            invalid = True
                            break
            if not invalid:
                new_trees.append(trees[i])
                new_nodemaps.append(nodemaps[i])
        
        return new_trees, new_nodemaps




    @staticmethod
    def subtrees_match_all(a, b):
        # Find all match cases of subtrees_match
        if a.base_type != 'Root' or b.base_type != 'Root':
            raise ValueError('a and b must be root nodes.')
        trees = TemplateNode.subtrees_match_all_single_step(a.children['body'], b.children['body'])
        unwrapped_trees, nodemaps = TemplateNode.unwrap_trees(trees)
        unwrapped_trees, nodemaps = TemplateNode.validate_nodemap(unwrapped_trees, nodemaps, [n.dfsid for n in b.children['body']])
        for t in unwrapped_trees:
            if len(t) != len(a.children['body']):
                raise ValueError('Inconsistent subtrees and template nodes: {} and {}'.format(len(t), len(a.children['body'])))

        return unwrapped_trees, nodemaps

    @staticmethod
    def is_include(a, b):
        #indicate whether node a is a subset of node b for patch generation
        if a.type == b.type or (b.type == 'Expr' and b.type_abstracted and a.type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Expr', 'End_Expr', 'Identifier']) \
            or (b.type == 'End_Expr' and b.type_abstracted and a.type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Identifier'])\
            or (b.type == 'Identifier' and b.type_abstracted and a.type in ['Variable', 'Attribute', 'Type', 'Builtin']):
            if len(a.children) != len(b.children):
                return False
            for c in b.children:
                if c not in a.children:
                    return False
                if len(b.children[c]) != len(a.children[c]):
                    return False
                for i, bn in enumerate(b.children[c]):
                    if not TemplateNode.is_include(a.children[c][i], bn):
                        return False
            
            return True

        else:
            return False




    def dump(self):
        referred_from = []
        for n in self.referred_from:
            if n.template_id == None:
                continue
            #if n.template_id != self.template_id:
            #    raise ValueError('Inconsistent template id {} and {}.'.format(n.template_id, self.template_id))
            referred_from.append(n.id)
        refer_to = []
        for n in self.refer_to:
            if n.template_id == None:
                continue
            #if n.template_id != self.template_id:
            #    raise ValueError('Inconsistent template id {} and {}.'.format(n.template_id, self.template_id))
            refer_to.append(n.id)
        context_refer = []
        for n in self.context_refer:
            if n.template_id == None:
                continue
            #if n.template_id != self.template_id:
            #    raise ValueError('Inconsistent template id {} and {}.'.format(n.template_id, self.template_id))
            context_refer.append(n.id)
        self_refer = []
        for n in self.self_refer:
            if n.template_id == None:
                continue
            #if n.template_id != self.template_id:
            #    raise ValueError('Inconsistent template id {} and {}.'.format(n.template_id, self.template_id))
            self_refer.append(n.id)
        '''
        attribute_referred_from = []
        for n in self.attribute_referred_from:
            if n.template_id == None:
                continue
            if n.template_id != self.template_id:
                raise ValueError('Inconsistent template id {} and {}.'.format(n.template_id, self.template_id))
            attribute_referred_from.append(n.id)
        attribute_refer_to = {}
        for k in self.attribute_refer_to:
            attribute_refer_to[k] = []
            for n in self.attribute_refer_to[k]:
                attribute_refer_to[k].append(n.id)
        '''
        children = {}
        for c in self.children:
            children[c] = []
            for n in self.children[c]:
                children[c].append(n.id)
        if isinstance(self.value, bytes):
            value = self.value.decode('UTF-8')
        elif type(self.value).__name__ == 'ellipsis':
            value = None
        else:
            value = self.value
        info = {
            "base_type": self.base_type,
            "type": self.type,
            "value": value,
            "value_type": type(self.value).__name__,
            "ast_type": type(self.ast_type).__name__,
            "asname": self.asname,
            "tree_type": self.tree_type,
            "ctx": self.ctx,
            "within_context_relation": self.within_context_relation,
            "id": self.id,
            "template_id": self.template_id,
            "parent": self.parent.id if self.parent else None,
            "parent_relation": self.parent_relation,
            "value_abstracted": self.value_abstracted,
            "type_abstracted": self.type_abstracted,
            "optional": self.optional,
            "partial": self.partial,
            "referred_from": referred_from,
            "refer_to": refer_to,
            "context_refer": context_refer,
            "self_refer": self_refer,
            "ori_nodes": self.ori_nodes,
            #"attribute_referred_from": attribute_referred_from,
            #"attribute_refer_to": attribute_refer_to,
            "attribute_referred_from": [],
            "attribute_refer_to": {},
            "children": children,
            "dfsid": self.dfsid
        }
        try:
            for k in info:
                json.dumps(info[k])
        except Exception as e:
            print(e)
            print(k)
            exit()
        return info

    @staticmethod
    def load(info):
        node = TemplateNode(info["base_type"])
        for k in info:
            if k not in ["value", "value_type", "parent", "referred_from", "refer_to", "context_refer", "self_refer", "attribute_referred_from", "attribute_refer_to", "children"]:
                setattr(node, k, info[k])
            elif k == "value":
                if info["value_type"] == "bytes":
                    setattr(node, k, bytes(info[k], encoding = 'utf-8'))
                elif info["value_type"] == "ellipsis":
                    setattr(node, k, ast.Ellipsis().value)
                else:
                    setattr(node, k, info[k])


        return node


    def load_reference(self, info, nodemap):
        if info["parent"] != None:
            self.parent = nodemap[info["parent"]]
        else:
            self.parent = None
        for i in info["referred_from"]:
            self.referred_from.append(nodemap[i])
        for i in info["refer_to"]:
            self.refer_to.append(nodemap[i])
        for i in info["context_refer"]:
            if i in nodemap:
                self.context_refer.append(nodemap[i])
            else:
                logger.warning(f'Undefined node {i} found in context refer when loading reference in template {self.template_id}, skipped.')
        for i in info["self_refer"]:
            self.self_refer.append(nodemap[i])
        '''
        for i in info["attribute_referred_from"]:
            self.attribute_referred_from.append(nodemap[i])
        for k in info["attribute_refer_to"]:
            for i in info["attribute_refer_to"][k]:
                self.attribute_refer_to[k].append(nodemap[i])
        '''
        for c in info["children"]:
            self.children[c] = []
            for i in info["children"][c]:
                self.children[c].append(nodemap[i])


            





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
        self.references = []

        self.same_node_abstraction = {}


    def build(self, changetrees, partial = False, record_astnode = True):
        self.root = TemplateNode('Root')
        for c in changetrees:
            node = TemplateNode('Stmt')
            if c.partial:
                partial = True
            node.build_from_stmt(c, partial = partial, record_astnode = record_astnode)
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
        self.references = []
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
            elif node.base_type == 'Reference':
                self.references.append(node)
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
    
    @staticmethod
    def get_topest_within_relation_node_depth(leafpath):
        num = 0
        topest = 0
        for i in leafpath:
            if isinstance(i, TemplateNode):
                num += 1
                if len(i.within_context_relation['before']) > 0 or len(i.within_context_relation['after']) > 0:
                    topest = num
        
        return topest


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
                        if a_leaf_paths[a_leaf][i].tree_type == 'Within_Context' and Context.compare_within_context(a_leaf_paths[a_leaf][i].within_context_relation, b_leaf_paths[b_leaf][i].within_context_relation) and TemplateNode.is_type_compatible(a_leaf_paths[a_leaf][i], b_leaf_paths[b_leaf][i]) and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        elif a_leaf_paths[a_leaf][i].tree_type != 'Within_Context' and TemplateNode.is_type_compatible(a_leaf_paths[a_leaf][i], b_leaf_paths[b_leaf][i]) and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        else:
                            break
                    elif isinstance(a_leaf_paths[a_leaf][i], str) and isinstance(b_leaf_paths[b_leaf][i], str) and a_leaf_paths[a_leaf][i] != b_leaf_paths[b_leaf][i]:
                        break
                if a_leaf_paths[a_leaf][0].tree_type == 'Within_Context' and num >= max(TemplateTree.get_topest_within_relation_node_depth(a_leaf_paths[a_leaf]), TemplateTree.get_topest_within_relation_node_depth(b_leaf_paths[b_leaf])):
                    same_node_map[a_leaf][b_leaf] = num
                elif a_leaf_paths[a_leaf][0].tree_type != 'Within_Context':
                    same_node_map[a_leaf][b_leaf] = num
                else:
                    same_node_map[a_leaf][b_leaf] = 0
        
        reserved_a = list(a_leaf_paths.keys())
        reserved_b = list(b_leaf_paths.keys())
        match_num = 0
        pairs = []
        in_path = {}
        while(len(reserved_a) > 0 and len(reserved_b) > 0):
            max_num = 0
            max_a = None
            max_b = None
            for a_leaf in reserved_a:
                for b_leaf in reserved_b:
                    if same_node_map[a_leaf][b_leaf] > max_num:
                        max_num = same_node_map[a_leaf][b_leaf]
                        max_a = a_leaf
                        max_b = b_leaf
            if max_num > 0 and max_a != None and max_b != None:
                n = max_a
                m = max_b
                for i in range(1, max_num):
                    n = max_a.parent
                    m = max_b.parent
                    if n not in in_path and m not in in_path:
                        in_path[n] = [max_a]
                        in_path[m] = [max_b]
                    elif n in in_path and m in in_path:
                        if len(in_path[n]) != len(in_path[m]):
                            max_num = i
                            break
                        for index in range(0, len(in_path[n])):
                            if not TemplateNode.is_type_compatible(in_path[n][index], in_path[m][index]):
                                max_num = i
                                break
                    else:
                        max_num = i
                        break
                pairs.append([max_a, max_b, max_num])
                match_num += max_num
                reserved_a.remove(max_a)
                reserved_b.remove(max_b)
            else:
                break

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
                        if a_leaf_paths[a_leaf][i].tree_type == 'Within_Context' and Context.compare_within_context(a_leaf_paths[a_leaf][i].within_context_relation, b_leaf_paths[b_leaf][i].within_context_relation) and TemplateNode.self_compare(a_leaf_paths[a_leaf][i], b_leaf_paths[b_leaf][i]) and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        elif a_leaf_paths[a_leaf][i].tree_type != 'Within_Context' and TemplateNode.self_compare(a_leaf_paths[a_leaf][i], b_leaf_paths[b_leaf][i]) and a_leaf_paths[a_leaf][i].type != 'Root':
                            num += 1
                        else:
                            break
                    elif isinstance(a_leaf_paths[a_leaf][i], str) and isinstance(b_leaf_paths[b_leaf][i], str) and a_leaf_paths[a_leaf][i] != b_leaf_paths[b_leaf][i]:
                        break
                if a_leaf_paths[a_leaf][0].tree_type == 'Within_Context' and num >= max(TemplateTree.get_topest_within_relation_node_depth(a_leaf_paths[a_leaf]), TemplateTree.get_topest_within_relation_node_depth(b_leaf_paths[b_leaf])):
                    same_node_map[a_leaf][b_leaf] = num
                elif a_leaf_paths[a_leaf][0].tree_type != 'Within_Context':
                    same_node_map[a_leaf][b_leaf] = num
                else:
                    same_node_map[a_leaf][b_leaf] = 0
        reserved_a = list(a_leaf_paths.keys())
        reserved_b = list(b_leaf_paths.keys())
        match_num = 0
        pairs = []
        in_path = {}
        while(len(reserved_a) > 0 and len(reserved_b) > 0):
            max_num = 0
            max_a = None
            max_b = None
            for a_leaf in reserved_a:
                for b_leaf in reserved_b:
                    if same_node_map[a_leaf][b_leaf] > max_num:
                        max_num = same_node_map[a_leaf][b_leaf]
                        max_a = a_leaf
                        max_b = b_leaf
            if max_num > 0 and max_a != None and max_b != None:
                n = max_a
                m = max_b
                for i in range(1, max_num):
                    n = max_a.parent
                    m = max_b.parent
                    if n not in in_path and m not in in_path:
                        in_path[n] = [max_a]
                        in_path[m] = [max_b]
                    elif n in in_path and m in in_path:
                        if len(in_path[n]) != len(in_path[m]):
                            max_num = i
                            break
                        for index in range(0, len(in_path[n])):
                            if not TemplateNode.self_compare(in_path[n][index], in_path[m][index]):
                                max_num = i
                                break
                    else:
                        max_num = i
                        break
                pairs.append([max_a, max_b, max_num])
                match_num += max_num
                reserved_a.remove(max_a)
                reserved_b.remove(max_b)
            else:
                break

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
        if TemplateNode.is_type_compatible(a, b):
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
            if not TemplateNode.self_compare(a, b):
                return 0
            if len(a.children) == len(b.children) and len(a.children) == 0:
                if TemplateNode.self_compare(a, b):
                    return 2
                else:
                    return 0
            elif len(a.children) == 0 and len(b.children) != 0:
                if TemplateNode.self_compare(a, b):
                    return 2
                else:
                    return 0
            elif len(a.children) != 0 and len(b.children) == 0:
                if TemplateNode.self_compare(a, b):
                    return 2
                else:
                    return 0
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

    def get_path_to_root(self, node):
        path = []
        cur_node = node
        while(cur_node.type != 'Root'):
            path += [cur_node, cur_node.parent_relation, cur_node.parent.children[cur_node.parent_relation].index(cur_node)]
            cur_node = cur_node.parent
            if cur_node == None:
                raise ValueError('Parents of some nodes are None.')
        path.append(cur_node)
        return path
    
    @staticmethod
    def get_path_to_root2(node):
        path = []
        cur_node = node
        while(cur_node.type != 'Root'):
            path += [cur_node, cur_node.parent_relation]
            cur_node = cur_node.parent
            if cur_node == None:
                raise ValueError('Parents of some nodes are None.')
        path.append(cur_node)
        return path


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

    @staticmethod
    def match_leaf_path(a, b):
        # Indicate whether leaf path a matches to b
        if len(a) < len(b):
            return False
        for i, na in enumerate(a):
            if type(na) != type(b[i]):
                return False
            elif isinstance(na, TemplateNode):
                if b[i].base_type == 'Root':
                    break
                if not TemplateNode.self_match(na, b[i]):
                    return False
            elif isinstance(na, str) and na != b[i] and b[i+2].base_type != 'Root':
                return False

        return True

    @staticmethod
    def match_leaf_path2(a, b):
        # Indicate whether leaf path a matches to b
        if len(a) < len(b):
            return False
        for i, na in enumerate(a):
            if type(na) != type(b[i]):
                return False
            elif isinstance(na, TemplateNode):
                if b[i].base_type == 'Root':
                    break
                if not TemplateNode.self_match(na, b[i]):
                    return False
            elif isinstance(na, str) and na != b[i] and b[i+1].base_type != 'Root':
                return False

        return True

    @staticmethod
    def print_leaf_path(path):
        p = []
        for i in path:
            if isinstance(i, TemplateNode):
                p.append(i.type)
            else:
                p.append(i)
        print(p)

    def remove(self, node):
        if node.parent == None or node.base_type == 'Root':
            pass
        else:
            if node in node.parent.children[node.parent_relation]:
                node.parent.children[node.parent_relation].remove(node)
            if len(node.parent.children[node.parent_relation]) == 0:
                del node.parent.children[node.parent_relation]

    def remove_path(self, node):
        if node.parent == None or node.base_type == 'Root':
            pass
        else:
            node.parent.children[node.parent_relation].remove(node)
            if len(node.parent.children[node.parent_relation]) == 0:
                del node.parent.children[node.parent_relation]
            if len(node.parent.children) == 0:
                self.remove_path(node.parent)

    def reorder(self, order, mode):
        newlist = [None for i in self.root.children['body']]
        for index, i in enumerate(order):
            if i.startswith(mode):
                loc = int(i.replace(f'{mode}-', ''))
                newlist[index] = self.root.children['body'][loc]
        
        for i in newlist:
            if i == None:
                raise ValueError('Inconsistent order and children: {} and {}'.format(order, self.root.children['body']))
        
        self.root.children['body'] = newlist



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
    def subtract_subtree(a, b, mode = 'before'):
        # Subtract a subtree a from tree b
        tree = b
        removed_nodes = []
        nodemap = {}
        a_leafpaths = a.get_leaf_paths()
        for n in a_leafpaths:
            path = a_leafpaths[n][::-1]
            curnode = tree.root
            nodemap[curnode] = path[0]
            for i in path:
                if isinstance(i, TemplateNode):
                    relation = None
                    index = None
                    nodemap[curnode] = i
                if isinstance(i, str):
                    relation = i
                    if curnode not in removed_nodes and curnode.base_type != 'Root':
                        removed_nodes.append(curnode)
                    curnode = curnode.children[relation][index]
                if isinstance(i, int):
                    index = i
            if curnode not in removed_nodes and curnode.base_type != 'Root':
                removed_nodes.append(curnode)   
        
        old_parents = {}
        old_parent_relation = {}
        for n in tree.iter_nodes():
            old_parents[n] = n.parent
            old_parent_relation[n] = n.parent_relation
        context_relations = []
        for n in removed_nodes:
            if n.base_type == 'Root':
                continue
            n.parent.children[n.parent_relation].remove(n)
            for c in n.children:
                if n.parent.base_type != 'Root':
                    if c in n.parent.children:
                        n.parent.children[c] += n.children[c]
                    else:
                        n.parent.children[c] = n.children[c]
                else:
                    n.parent.children['body'] += n.children[c]
                for nn in n.children[c]:
                    old_parent = nn.parent
                    nn.parent = n.parent
                    if n.parent.base_type == 'Root':
                        nn.parent_relation = 'body'
        
        for index, n in enumerate(tree.root.children['body']):
            nodemap[old_parents[n]].within_context_relation[mode].append([old_parent_relation[n], index])
            context_relations.append(old_parent_relation[n])
        
        newbody = []
        relation_nodes = Context.get_within_relation_nodes_dfs(a.root, mode = mode)
        for n in relation_nodes:
            for c in n.within_context_relation[mode]:
                newbody.append(tree.root.children['body'][c[1]])
                c[1] = len(newbody) - 1
        
        tree.root.children['body'] = newbody
        
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

    def remove_empty_children(self):
        for n in self.iter_nodes():
            removed = []
            for c in n.children:
                if len(n.children[c]) == 0:
                    removed.append(c)
            
            for r in removed:
                del n.children[r]

    def recover_parent(self):
        nodes = [self.root]
        while(len(nodes) > 0):
            n = nodes[0]
            nodes = nodes[1:]
            for c in n.children:
                for nn in n.children[c]:
                    nn.parent = n
                    nn.parent_relation = c
                    nodes.append(nn)
    
    @staticmethod
    def assign_dfsid(node, index = 0):
        node.dfsid = index
        index += 1
        for c in node.children:
            for n in node.children[c]:
                index = TemplateTree.assign_dfsid(n, index = index)
        
        return index


        


    def draw(self, name, filerepo = None, dump_attributes = False):
        filename = 'TEMPLATE_TREE_{}'.format(name)
        if filerepo:
            filename = os.path.join(filerepo, filename)
        p = Digraph('Templare Tree', filename)
        p.attr(fontsize = '20')
        index = 0
        nodemap = {}
        p.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
        p.node(f'node{index}', label = self.root.resolve_name(dump_attributes = dump_attributes))
        nodemap[self.root] = f'node{index}'
        index += 1
        p.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
        for n in self.iter_nodes():
            if n.base_type not in ['Stmt', 'Expr']:
                continue
            elif len(n.referred_from) > 0 or len(n.refer_to) > 0:
                continue
            p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
            nodemap[n] = f'node{index}'
            index += 1
        p.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled')
        for n in self.iter_nodes():
            if n.base_type not in ['Stmt', 'Expr']:
                continue
            elif len(n.referred_from) == 0 and len(n.refer_to) == 0:
                continue
            p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
            nodemap[n] = f'node{index}'
            index += 1
        p.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
        for n in self.iter_nodes():
            if n.base_type in ['Root', 'Stmt', 'Expr']:
                continue
            elif len(n.referred_from) > 0 or len(n.refer_to) > 0:
                continue
            p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
            nodemap[n] = f'node{index}'
            index += 1
        p.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
        for n in self.iter_nodes():
            if n.base_type in ['Root', 'Stmt', 'Expr']:
                continue
            elif len(n.referred_from) == 0 and len(n.refer_to) == 0:
                continue
            p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
            nodemap[n] = f'node{index}'
            index += 1
        for n in self.iter_nodes():
            for c in n.children:
                for cn in n.children[c]:
                    p.edge(nodemap[n], nodemap[cn], label = c)
        p.render(filename = filename, view = False)
    
    def dump(self):
        nodes = {}

        for n in self.iter_nodes():
            nodes[n.id] = n.dump()
        
        info = {
            "root": self.root.id,
            "nodes": nodes
        }

        return info

    @staticmethod
    def load(info, nodemap, infomap):
        for i in info["nodes"]:
            nodemap[int(i)] = TemplateNode.load(info["nodes"][i])
            infomap[int(i)] = info["nodes"][i]
        
        tree = TemplateTree()
        tree.root = nodemap[info["root"]]
        tree.collect_special_nodes()

        return tree

    @staticmethod
    def concat(a, b, relations, mode = 'before'):
        #concat a to b
        new_a = deepcopy(a)
        new_b = deepcopy(b)


        relation_nodes = Context.get_within_relation_nodes_dfs(new_b.root)
        #for k in relations[0]:
        #    print(k.keys(), TemplateTree.print_leaf_path(list(k.values())[0]))

        

        num = 0
        for n in relation_nodes:
            num += len(n.within_context_relation[mode])
        
        if num != len(new_a.root.children['body']) or (mode == 'before' and num != len(relations[0])) or (mode == 'after' and num != len(relations[1])):
            raise ValueError('Inconsistent concat nodes: relation nodes - {}, before tree nodes - {}, relations - {}'.format(num, len(new_a.root.children['body']), len(relations[0])))

        '''
        selected = {}
        new_relation_nodes = []
        for i in range(0, len(relations[0])):
            for n in relation_nodes:
                if n in selected:
                    continue
                found = True
                for j, c in enumerate(n.within_context_relation['before']):
                    if c != list(relations[0][i+j].keys())[0] or not TemplateTree.match_leaf_path2(TemplateTree.get_path_to_root2(n), list(relations[0][i+j].values())[0]):
                        found = False
                        break

                if found:
                    selected[n] = 1
                    new_relation_nodes.append(n)
                    i += len(n.within_context_relation['before']) 
                    i -=1
                    break
        '''

        for n in relation_nodes:
            for c in n.within_context_relation[mode]:
                if c[0] not in n.children:
                    n.children[c[0]] = []
                n.children[c[0]].append(new_a.root.children['body'][c[1]])
                new_a.root.children['body'][c[1]].parent = n
                if mode == 'before':
                    new_a.root.children['body'][c[1]].before_index = c[1]
                elif mode == 'after':
                    new_a.root.children['body'][c[1]].after_index = c[1]
                new_a.root.children['body'][c[1]].parent_relation = c[0]
        
        return new_b

    @staticmethod
    def root_node_compare(a, b):
        if len(a.root.children['body']) != len(b.root.children['body']):
            return False
        for i, an in enumerate(a.root.children['body']):
            if not TemplateNode.self_compare(an, b.root.children['body'][i]):
                return False

        return True

    def replace(self, a, b, change_base_type = False, change_value = False):
        #change all nodes with type a to type b
        for n in self.iter_nodes():
            if n.type == a:
                n.type = b
                if change_base_type:
                    n.base_type = b
                if change_value:
                    n.value = None


    def cal_abstract_score(self):
        score = 0
        for n in self.iter_nodes():
            if n.type_abstracted and n.type != 'Reference':
                if n.type == 'Identifier':
                    score += 10
                elif n.type == 'End_Expr':
                    score += 20
                elif n.type == 'Expr':
                    score += 40
                elif n.type == 'Stmt':
                    score += 80
            elif n.value_abstracted:
                if n.value == 'ABSTRACTED':
                    score += 5
                elif n.value == 'REFERRED':
                    score += 3
                else:
                    score += 1
        
        return score
    
    def cal_abstract_ratio(self):
        num = self.get_node_num() - 1
        abstracted = 0
        for n in self.iter_nodes():
            if n.base_type == 'Root':
                continue
            if n.type_abstracted and n.type != 'Reference':
                abstracted += 1
        
        return abstracted/num if num > 0 else 0.0



    @staticmethod
    def get_distance(a, b):
        if (a == None and b != None) or (a != None and b == None):
            return -9999
        same_node_num = TemplateTree.get_same_node_num_top_down(a.root, b.root)
        node_num = 0
        if a != None:
            node_num += a.get_node_num()
        if b != None:
            node_num += b.get_node_num()
        
        distance = same_node_num / node_num if node_num > 0 else 1.0

        return distance

            




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


    def get_within_relation_nodes(self):
        nodes = []
        for n in self.context_tree.iter_nodes():
            if len(n.within_context_relation['before']) != 0 or len(n.within_context_relation['after']) != 0:
                nodes.append(n)

        return nodes

    @staticmethod
    def get_within_relation_nodes_dfs(node, mode = 'before'):
        nodes = []
        if (mode in ['before', 'all'] and len(node.within_context_relation['before']) != 0) or (mode in ['after', 'all'] and len(node.within_context_relation['after']) != 0):
            nodes.append(node)
        for c in node.children:
            for n in node.children[c]:
                nodes += Context.get_within_relation_nodes_dfs(n, mode = mode)
        
        return nodes


    @staticmethod
    def compare_within_context(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            if len(a['before']) == len(b['before']):
                for index in range(0, len(a['before'])):
                    if a['before'][index][0] != b['before'][index][0] or a['before'][index][1] != b['before'][index][1]:
                        return False
            else:
                return False
            if len(a['after']) == len(b['after']):
                for index in range(0, len(a['after'])):
                    if a['after'][index][0] != b['after'][index][0] or a['after'][index][1] != b['after'][index][1]:
                        return False
            else:
                return False
            return True
        else:
            return False

    @staticmethod
    def match(a, b):
        # Indicate whether a matches to b
        if (a == None and b != None) or (a != None and b == None):
            return False
        a_leaf_paths = a.context_tree.get_leaf_paths()
        b_leaf_paths = b.context_tree.get_leaf_paths()
        if len(a_leaf_paths) < len(b_leaf_paths):
            return False
        selected = {}
        for b_leaf in b_leaf_paths:
            ori = len(selected)
            candidates = []
            for a_leaf in a_leaf_paths:
                if a_leaf in selected:
                    continue
                if TemplateNode.self_match(a_leaf, b_leaf):
                    if len(a_leaf.refer_to) < len(b_leaf.refer_to):
                        continue
                    found = {}
                    invalid_num = 0
                    for br in b_leaf.refer_to:
                        if br.value != b_leaf.value:
                            invalid_num += 1
                            continue
                        ori_num = len(found)
                        for ar in a_leaf.refer_to:
                            if ar in found:
                                continue
                            #print(br.parent_relation, ar.parent_relation, ar.parent.type, br.parent.type)
                            if (br.parent_relation == ar.parent_relation and TemplateNode.self_match(ar.parent, br.parent)) or (br.parent.base_type == 'Root'):
                                found[ar] = 1
                                break
                        cur_num = len(found)
                        if cur_num <= ori_num:
                            break
                    if len(found) == len(b_leaf.refer_to) - invalid_num:
                        if TemplateTree.match_leaf_path(a_leaf_paths[a_leaf], b_leaf_paths[b_leaf]):
                            candidates.append(a_leaf)
            min_len = 9999
            min_one = None
            for c in candidates:
                if abs(len(a_leaf_paths[c]) - len(b_leaf_paths[b_leaf])) < min_len:
                    min_one = c
                    min_len = abs(len(a_leaf_paths[c]) - len(b_leaf_paths[b_leaf]))
            selected[min_one] = 1
            cur = len(selected)
            if cur <= ori:
                #print(b_leaf_paths[b_leaf])
                return False
        return True

    def dump(self):
        info = {
            "context_tree": self.context_tree.dump(),
            "relationship": self.relationship,
            "type": self.type
        }

        return info

    @staticmethod
    def load(info, nodemap, infomap):
        context_tree = TemplateTree.load(info["context_tree"], nodemap, infomap)
        
        context = Context(context_tree, info["relationship"], info["type"])

        return context

        
        
        
                    







            
        
        



                

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

        # Concatenated before tree and within_contexts
        self.before_within = None

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
                if isinstance(i, ChangePair):
                    self.instances.append(i.metadata)
                elif isinstance(i, dict):
                    self.instances.append(i)
        return fixed_id2template

    def clean_context(self):
        # Remove the context tree paths without any reference
        if self.before_contexts:
            if not self.before_contexts.context_tree.root.has_refer_to_for_self() and not self.before_contexts.context_tree.root.has_refer_to_for_all_children():
                self.before_contexts = None
            else:
                self.before_contexts.context_tree.root.prune_no_refer_to_children()
        if self.after_contexts:
            if not self.after_contexts.context_tree.root.has_refer_to_for_self() and not self.after_contexts.context_tree.root.has_refer_to_for_all_children():
                self.after_contexts = None
            else:
                self.after_contexts.context_tree.root.prune_no_refer_to_children()


    def recover_reference(self):
        old2new = {}
        all_nodes = {}
        if self.before:
            for n in self.before.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n] = n
                all_nodes[n.get_id()] = n
            self.before.recover_parent()
        if self.after:
            for n in self.after.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n] = n
                all_nodes[n.get_id()] = n
            self.after.recover_parent()
        if self.within_context:
            for n in self.within_context.context_tree.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n] = n
                all_nodes[n.get_id()] = n
            self.within_context.context_tree.recover_parent()
        if self.before_contexts:
            for n in self.before_contexts.context_tree.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n] = n
                all_nodes[n.get_id()] = n
            self.before_contexts.context_tree.recover_parent()
        if self.after_contexts:
            for n in self.after_contexts.context_tree.iter_nodes():
                for old_n in n.ori_nodes:
                    old2new[old_n] = n
                all_nodes[n.get_id()] = n
            self.after_contexts.context_tree.recover_parent()
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
        self.clean_context()

    @staticmethod
    def compare(a, b):
        if not isinstance(a, FixTemplate) or not isinstance(b, FixTemplate):
            return False
        if a.before != b.before and not TemplateTree.compare(a.before, b.before):
            return False
        if a.after != b.after and not TemplateTree.compare(a.after, b.after):
            return False
        if a.within_context != b.within_context:
            if a.within_context == None or b.within_context == None:
                return False
            elif not TemplateTree.compare(a.within_context.context_tree, b.within_context.context_tree):
                return False
        if a.before_contexts != b.before_contexts:
            if a.before_contexts == None or b.before_contexts == None:
                return False
            elif not TemplateTree.compare(a.before_contexts.context_tree, b.before_contexts.context_tree):
                return False
        if a.after_contexts != b.after_contexts:
            if a.after_contexts == None or b.after_contexts == None:
                return False
            elif not TemplateTree.compare(a.after_contexts.context_tree, b.after_contexts.context_tree):
                return False
        
        return True

    @staticmethod
    def is_include(a, b):
        #indicate whether template a is a subset of template b in patch generation
        if not TemplateTree.compare(a.after, b.after):
            return False
        if a.before_within != None and b.before_within != None and TemplateNode.is_include(a.before_within.root, b.before_within.root):
            return True
        elif a.before_within == None and b.before_within == None:
            return True

        return False



    @staticmethod
    def exist_same(a, listb):
        for b in listb:
            if FixTemplate.compare(a, b):
                return True
        
        return False

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
        before_same_node_num = 0
        after_same_node_num = 0
        if a.before != None and b.before != None:
            before_same_node_num = TemplateTree.get_same_node_num_top_down(a.before.root, b.before.root)
            same_node_num += before_same_node_num
        if a.after != None and b.after != None:
            after_same_node_num = TemplateTree.get_same_node_num_top_down(a.after.root, b.after.root)
            same_node_num += after_same_node_num

        node_num = 0
        before_node_num = 0
        after_node_num = 0
        if a.before != None:
            before_node_num += a.before.get_node_num()
        if b.before != None:
            before_node_num += b.before.get_node_num()
        if a.after != None:
            after_node_num += a.after.get_node_num()
        if b.after != None:
            after_node_num += b.after.get_node_num()
        
        node_num = before_node_num + after_node_num 
        
        distance = same_node_num / node_num
        before_distance = before_same_node_num / before_node_num if before_node_num > 0 else 1.0
        after_distance = after_same_node_num / after_node_num if after_node_num > 0 else 1.0

        return distance, before_distance, after_distance

    @staticmethod
    def get_structural_distance_for_pattern(a, b):
        same_node_num = 0
        before_same_node_num = 0
        after_same_node_num = 0
        if a.before != None and b.before != None:
            before_same_node_num = TemplateTree.get_similar_node_num_top_down(a.before.root, b.before.root)
            same_node_num += before_same_node_num
        if a.after != None and b.after != None:
            after_same_node_num = TemplateTree.get_similar_node_num_top_down(a.after.root, b.after.root)
            same_node_num += after_same_node_num

        node_num = 0
        before_node_num = 0
        after_node_num = 0
        if a.before != None:
            before_node_num += a.before.get_node_num()
        if b.before != None:
            before_node_num += b.before.get_node_num()
        if a.after != None:
            after_node_num += a.after.get_node_num()
        if b.after != None:
            after_node_num += b.after.get_node_num()
        
        node_num = before_node_num + after_node_num 
        
        distance = same_node_num / node_num
        before_distance = before_same_node_num / before_node_num if before_node_num > 0 else 1.0
        after_distance = after_same_node_num / after_node_num if after_node_num > 0 else 1.0

        return distance, before_distance, after_distance

    @staticmethod
    def get_distance_for_context(a, b):
        distance = {'within': 0.0, 'before': 0.0, 'after': 0.0, 'external': 0.0}
        pairs = {'within': [], 'before': [], 'after': []}
        if a.within_context != None and b.within_context != None:
            match_num, total_num, pair = TemplateTree.get_same_node_num_down_top(a.within_context.context_tree, b.within_context.context_tree)
            if len(pair) > 0:
                distance['within'] = match_num * 2 / total_num
            else:
                distance['within'] = -9999
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
            if len(pair) > 0:
                distance['within'] = match_num * 2 / total_num
            else:
                distance['within'] = -9999
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


    def get_all_child_templates(self, id2template):
        child_templates = []
        for i in self.child_templates:
            child_templates.append(i)
            child_templates += id2template[i].get_all_child_templates(id2template)
        
        return child_templates

    def concat_within_context(self):
        if self.within_context == None:
            self.before_within = deepcopy(self.before)
            if self.before_within:
                for i, n in enumerate(self.before_within.root.children['body']):
                    n.before_index = i
        elif self.before == None:
            self.before_within = deepcopy(self.within_context.context_tree)
        else:
            self.before_within = TemplateTree.concat(self.before, self.within_context.context_tree, self.within_context.relationship)
        self.set_node_ids()

    def clean_invalid_reference(self):
        patterns = [self.before, self.after, self.before_within]
        contexts = [self.within_context, self.before_contexts, self.after_contexts]
        for p in patterns:
            if p:
                for n in p.iter_nodes():
                    if len(n.self_refer) > 0:
                        new_self_refer = []
                        for nn in n.self_refer:
                            if nn.type == n.type and nn.value == n.value:
                                new_self_refer.append(nn)
                        n.self_refer = new_self_refer
        for c in contexts:
            if c:
                for n in c.context_tree.iter_nodes():
                    if len(n.self_refer) > 0:
                        new_self_refer = []
                        for nn in n.self_refer:
                            if nn.type == n.type and nn.value == n.value:
                                new_self_refer.append(nn)
                        n.self_refer = new_self_refer
                    if len(n.refer_to) > 0:
                        new_refer_to = []
                        for nn  in n.refer_to:
                            if nn.type == n.type and nn.value == n.value:
                                new_refer_to.append(nn)
                        n.refer_to = new_refer_to


    def dump(self):
        instances = []
        for i in self.instances:
            if isinstance(i, ChangePair):
                instances.append(i.metadata)
            elif isinstance(i, dict):
                instances.append(i)
        info = {
            "action": self.action,
            "before": self.before.dump() if self.before else None,
            "after": self.after.dump() if self.after else None,
            "within_context": self.within_context.dump() if self.within_context else None,
            "before_contexts": self.before_contexts.dump() if self.before_contexts else None,
            "after_contexts": self.after_contexts.dump() if self.after_contexts else None,
            "before_within": self.before_within.dump() if self.before_within else None,
            "child_templates": self.child_templates,
            "parent_template": self.parent_template,
            "id": self.id,
            "abstracted": self.abstracted,
            "node_index": self.node_index,
            "instances": instances
        }

        return info

    @staticmethod
    def load(info):
        nodemap = {}
        infomap = {}
        template = FixTemplate(info["action"], TemplateTree.load(info["before"], nodemap, infomap) if info["before"] else None, TemplateTree.load(info["after"], nodemap, infomap) if info["after"] else None)
        for k in info:
            if k in ["child_templates", "parent_template", "id", "abstracted", "node_index"]:
                setattr(template, k, info[k])
            if k in ["within_context", "before_contexts", "after_contexts"]:
                if info[k] != None:
                    setattr(template, k, Context.load(info[k], nodemap, infomap))
                else:
                    setattr(template, k, None)
        for i in nodemap:
            nodemap[i].load_reference(infomap[i], nodemap)
        for m in info["instances"]:
            template.instances.append(m)
        
        return template
        

    def draw(self, id2template, filerepo = None, draw_contexts = False, draw_instance = False, dump_attributes = False):
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
            p.node(f'node{index}', label = self.before.root.resolve_name(dump_attributes = dump_attributes))
            nodemap[self.before.root] = f'node{index}'
            index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.before.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        p.edge(nodemap[n], nodemap[cn], label = c)
        if self.after:
            p.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
            p.node(f'node{index}', label = self.after.root.resolve_name(dump_attributes = dump_attributes))
            nodemap[self.after.root] = f'node{index}'
            index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                nodemap[n] = f'node{index}'
                index += 1
            p.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                p.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
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
                    c.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                c.attr('node', shape = 'ellipse', fillcolor = 'cadetblue1', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                c.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                c.attr('node', shape = 'box', fillcolor = 'cadetblue1', style = 'filled')
                for n in self.within_context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    c.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                for n in self.within_context.context_tree.iter_nodes():
                    for cc in n.children:
                        for cn in n.children[cc]:
                            c.edge(nodemap[n], nodemap[cn], label = cc)
            if self.before_within:
                bw = Digraph("cluster_Before_Within")
                bw.attr(label = f'Before Within')
                bw.attr(fontsize = '15')
                bw.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled, dashed')
                bw.node(f'node{index}', label = self.before_within.root.resolve_name(dump_attributes = dump_attributes))
                nodemap[self.before_within.root] = f'node{index}'
                index += 1
                bw.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled, dashed')
                for n in self.before_within.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    bw.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                bw.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled, dashed')
                for n in self.before_within.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    bw.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                bw.attr('node', shape = 'box', fillcolor = 'none', style = 'filled, dashed')
                for n in self.before_within.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    bw.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                bw.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
                for n in self.before_within.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    bw.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                for n in self.before_within.iter_nodes():
                    for cc in n.children:
                        for cn in n.children[cc]:
                            bw.edge(nodemap[n], nodemap[cn], label = cc)
                c.subgraph(bw)
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
                    bc.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                bc.attr('node', shape = 'ellipse', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                bc.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                bc.attr('node', shape = 'box', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    bc.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
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
                    ac.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                ac.attr('node', shape = 'ellipse', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type not in ['Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                ac.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) > 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
                    nodemap[n] = f'node{index}'
                    index += 1
                ac.attr('node', shape = 'box', fillcolor = 'cadetblue1', style = 'filled')
                for n in context.context_tree.iter_nodes():
                    if n.base_type in ['Root', 'Stmt', 'Expr']:
                        continue
                    elif len(n.refer_to) == 0:
                        continue
                    ac.node(f'node{index}', label = n.resolve_name(dump_attributes = dump_attributes))
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

        try:
            f.render(filename = filename, view = False)
        except Exception as e:
            logger.error(f'Cannot render template {self.id}, reason: {e}, skpping.')

        if draw_instance:
            text = ""
            for i in self.instances:
                if isinstance(i, ChangePair):
                    text += '========================{}:{}========================\n{}\n=================================================================\n'.format(i.metadata['repo'], i.metadata['commit'], i.metadata['content'])
                else:
                    text += '========================{}:{}========================\n{}\n=================================================================\n'.format(i['repo'], i['commit'], i['content'])
            if self.parent_template != None:
                filename = os.path.join(filerepo, 'FIX_TEMPLATE_{}_INSTANCES.txt'.format(self.id))
            else:
                filename = os.path.join(filerepo, 'FINAL_FIX_TEMPLATE_{}_INSTANCES.txt'.format(self.id))
            with open(filename, 'w', encoding = 'utf-8') as f:
                f.write(text)
