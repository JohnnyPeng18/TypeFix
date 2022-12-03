import json
import os
import ast
import re
import copy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings
from change_tree import ChangeNode, ChangeTree, ChangePair


class TemplateNode(object):
    def __init__(self, nodetype):
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
        # Expr - Node representing expressions
        # Stmt - Node representing statements
        self.base_type = nodetype
        if self.base_type not in ['Stmt', 'Expr']:
            self.type = self.base_type
        else:
            self.type = None

        # Tree Types:
        # Before - The before tree
        # After - The after tree
        # Context - The context tree
        self.tree_type = None

        # Used in nodes in after parts indicating the same nodes in before parts
        self.refer_to = []
        # Used in nodes in before parts indicating the same nodes in after parts
        self.referred_from = []
        # Used in nodes in both before and after parts indicating the same nodes in contexts
        self.context_refer = []

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

        self.value_abstracted = False
        self.type_abstracted = False
        self.partial = False
        self.asname = None
        self.ctx = None

        self.parent = None
        self.parent_relation = None
    
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
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type or len(a.children) != len(b.children):
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
        name = f'{self.type}'
        if self.ctx != None:
            name += ' ({})'.format(str(self.ctx))
        if self.value != None or self.type == 'Literal':
            name += '\n{}'.format(str(self.value))
        return name

    @staticmethod
    def get_same_subnode(a, b):
        if not isinstance(a, TemplateNode) or not isinstance(b, TemplateNode):
            return None
        if TemplateNode.self_compare(a, b):
            node = TemplateNode(a.base_type)
            node.type = a.type
            node.value = a.value
            node.ast_type = a.ast_type
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
            len(self.attribute_refer_to) == 0 and len(self.attribute_referred_from) == 0:
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
            
    
    @staticmethod
    def get_same_node_num(a, b):
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
                            num += TemplateTree.get_same_node_num(a.children[c][i], b.children[c][i])
                
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

        self.prune_stmt_nodes()


    def prune_stmt_nodes(self):
        curnode = self.context_tree.root.children['body'][0]
        while True:
            if curnode.base_type == 'Stmt' and len(curnode.children) == 1 and len(curnode.children[list(curnode.children.keys())[0]]) == 1:
                curnode = curnode.children[list(curnode.children.keys())[0]][0]
            else:
                break
        self.context_tree.root.children['body'] = [curnode]
        
                    







            
        
        



                

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
        self.before_contexts = []
        # Contexts after change
        self.after_contexts = []
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
    
    def add_instance(self, instance):
        if instance not in self.instances and isinstance(instance, ChangePair):
            self.instances.append(instance)

    def merge(self, fix_templates):
        for t in fix_templates:
            if not isinstance(t, FixTemplate):
                continue
            if t.abstracted:
                self.abstracted = True
            self.former_templates.append(t.id)
            for i in t.instances:
                if not isinstance(i, ChangePair):
                    continue
                if i not in self.instances:
                    self.instances.append(i)
            
            for c in t.contexts:
                if not TemplateTree.exist_same(c, self.contexts):
                    self.contexts.append(c)
                    self.context_relations[c] = t.context_relations[c]


    @staticmethod
    def get_distance(a, b):
        same_node_num = 0
        if a.before != None and b.before != None:
            same_node_num += TemplateTree.get_same_node_num(a.before.root, b.before.root)
        if a.after != None and b.after != None:
            same_node_num += TemplateTree.get_same_node_num(a.after.root, b.after.root)

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
        

    def draw(self, filerepo = None, draw_contexts = False, draw_instance = False):
        filename = 'FIX_TEMPLATE_{}'.format(self.id)
        if filerepo:
            filename = os.path.join(filerepo, filename)
        nodemap = {}
        index = 0
        f = Digraph("Fix Template", filename = filename)
        if self.before:
            f.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled, dashed')
            f.node(f'node{index}', label = self.before.root.resolve_name())
            nodemap[self.before.root] = f'node{index}'
            index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'none', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled, dashed')
            for n in self.before.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.referred_from) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.before.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        f.edge(nodemap[n], nodemap[cn], label = c)
        if self.after:
            f.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
            f.node(f'node{index}', label = self.after.root.resolve_name())
            nodemap[self.after.root] = f'node{index}'
            index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'ellipse', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type not in ['Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'none', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) > 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            f.attr('node', shape = 'box', fillcolor = 'darkorange', style = 'filled')
            for n in self.after.iter_nodes():
                if n.base_type in ['Root', 'Stmt', 'Expr']:
                    continue
                elif len(n.refer_to) == 0:
                    continue
                f.node(f'node{index}', label = n.resolve_name())
                nodemap[n] = f'node{index}'
                index += 1
            for n in self.after.iter_nodes():
                for c in n.children:
                    for cn in n.children[c]:
                        f.edge(nodemap[n], nodemap[cn], label = c)
        
        f.attr(label = f'Template Category: {self.action}; Instances: {len(self.instances)}')
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
            if len(self.before_contexts) > 0:
                bc = Digraph("cluster_Before_Contexts")
                bc.attr(label = f'Before Contexts')
                bc.attr(fontsize = '15')
                bc.attr(color = 'lightsteelblue')
                for context in self.before_contexts:
                    bc.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
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
            if len(self.after_contexts) > 0:
                ac = Digraph("cluster_After_Contexts")
                ac.attr(label = f'After Contexts')
                ac.attr(fontsize = '15')
                ac.attr(color = 'lightskyblue3')
                for context in self.after_contexts:
                    ac.attr('node', shape = 'circle', fillcolor = 'none', style = 'filled')
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
        
        f.render(filename = filename, view = False)

        if draw_instance:
            for i in range(0, len(self.instances)):
                filename = os.path.join(filerepo, 'FIX_TEMPLATE_{}_INSTANCE_{}'.format(self.id, i))
                self.instances[i].draw(filename = filename)
