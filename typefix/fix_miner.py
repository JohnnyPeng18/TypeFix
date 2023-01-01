import json
import os
import ast
import re
from copy import deepcopy
from graphviz import Digraph
from tqdm import tqdm
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings
from change_tree import ChangeNode, ChangeTree, ChangePair
from fix_template import TemplateNode, TemplateTree, Context, FixTemplate
import traceback
import time

MAX_ITERATION = 10000

class ASTCompare(object):
    def __init__(self):
        self.beforeroot = None
        self.afterroot = None

    def build_change_tree(self, root, before, change_lines, raw_change_lines, always_add = False):
        nodes = {}
        change_trees = []
        for l in change_lines:
            for n in root.body:
                if l in range(n.lineno, n.end_lineno + 1):
                    if n not in nodes:
                        nodes[n] = []
                    nodes[n].append(l)
        
        raw_nodes = {}
        for l in raw_change_lines:
            for n in root.body:
                if l in range(n.lineno, n.end_lineno + 1):
                    if n not in raw_nodes:
                        raw_nodes[n] = []
                    raw_nodes[n].append(l)
        
        for n in nodes:
            c_node = ChangeNode(n, n.lineno, n.end_lineno, nodes[n], raw_nodes[n])
            c_tree = ChangeTree(c_node, before, nodes[n], raw_nodes[n])
            if always_add:
                c_tree.build()
                change_trees.append(c_tree)
            if not always_add and not c_tree.build():
                change_trees.append(c_tree)
        return change_trees


    def compare_change_tree(self, before_trees, after_trees):
        change_status = {'Added': {'Totally': [], 'Partially': []}, 'Removed': {'Totally': [], 'Partially': []}, 'Replaced': {'before': {'Totally': [], 'Partially': []}, 'after': {'Totally': [], 'Partially': []}}, 'order': {'before': [], 'after': []}}
        if len(before_trees) == 0 and len(after_trees) == 0:
            raise ValueError('Change trees before and after the commit are both empty.')
        linemap = {}
        if len(before_trees) == 0:
            linemap = {}
            for a in after_trees:
                for s in a.uppest_totally_changed_stmts:
                    s.set_status('Added')
                    s.set_status_for_childrens('Added')
                    s.set_status_for_parent('Added_Parent')
                    change_status['Added']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Added']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Added']['Totally']) - 1))
                for s in a.deepest_partially_changed_stmts:
                    s.set_status('Added_Parent')
                    s.set_status_for_parent('Added_Parent')
                    change_status['Added']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Added']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Added']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['after'] += loc

        elif len(after_trees) == 0:
            linemap = {}
            for b in before_trees:
                for s in b.uppest_totally_changed_stmts:
                    s.set_status('Removed')
                    s.set_status_for_childrens('Removed')
                    s.set_status_for_parent('Removed_Parent')
                    change_status['Removed']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Removed']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Removed']['Totally']) - 1))
                for s in b.deepest_partially_changed_stmts:
                    s.set_status('Removed_Parent')
                    s.set_status_for_parent('Removed_Parent')
                    change_status['Removed']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Removed']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Removed']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['before'] += loc
        
        else:
            linemap = {}
            for b in before_trees:
                for s in b.uppest_totally_changed_stmts:
                    s.set_status('Replaced')
                    s.set_status_for_childrens('Replaced')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['before']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Replaced']['before']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Replaced']['before']['Totally']) - 1))
                for s in b.deepest_partially_changed_stmts:
                    s.set_status('Replaced_Parent')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['before']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Replaced']['before']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Replaced']['before']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['before'] += loc
            linemap = {}
            for a in after_trees:
                for s in a.uppest_totally_changed_stmts:
                    s.set_status('Replaced')
                    s.set_status_for_childrens('Replaced')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['after']['Totally'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Totally-{}'.format(len(change_status['Replaced']['after']['Totally']) - 1)]
                    else:
                        linemap[s.lineno].append('Totally-{}'.format(len(change_status['Replaced']['after']['Totally']) - 1))
                for s in a.deepest_partially_changed_stmts:
                    s.set_status('Replaced_Parent')
                    s.set_status_for_parent('Replaced_Parent')
                    change_status['Replaced']['after']['Partially'].append(s)
                    if s.lineno not in linemap:
                        linemap[s.lineno] = ['Partially-{}'.format(len(change_status['Replaced']['after']['Partially']) - 1)]
                    else:
                        linemap[s.lineno].append('Partially-{}'.format(len(change_status['Replaced']['after']['Partially']) - 1))
            orders = sorted(linemap.items(), key = lambda item:item[0])
            for line, loc in orders:
                change_status['order']['after'] += loc
            if len(change_status['Replaced']['before']['Partially']) != len(change_status['Replaced']['after']['Partially']):
                logger.warning('Inconsistent number of partially changed statements before ({}) and after ({}) the commit'.format(len(change_status['Replaced']['before']['Partially']), len(change_status['Replaced']['after']['Partially'])))
        return ChangePair(before_trees, after_trees, change_status)


    def compare_loc(self, lines, content):
        if len(lines) != 4:
            raise ValueError('Incorrect line information: {}'.format(line))
        if '\ No newline at end of file' in content:
            logger.warning('Illegal commit, skipped.')
            return None
        before_index = lines[0]
        after_index = lines[2]
        before_change_lines = []
        raw_before_change_lines = []
        after_change_lines = []
        raw_after_change_lines = []
        for line in content.splitlines():
            if not line.startswith('-') and not line.startswith('+'):
                before_index += 1
                after_index += 1
            elif line.startswith('-'):
                if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                    before_change_lines.append(before_index)
                raw_before_change_lines.append(before_index)
                before_index += 1
            elif line.startswith('+'):
                if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                    after_change_lines.append(after_index)
                raw_after_change_lines.append(after_index)
                after_index += 1
        if before_index != lines[0] + lines[1] or after_index != lines[2] + lines[3]:
            logger.error('Line information does not match the change content.')
            return None
        if self.beforeroot:
            before_trees = self.build_change_tree(self.beforeroot, True, before_change_lines, raw_before_change_lines)
        else:
            before_trees = []
        if self.afterroot:
            after_trees = self.build_change_tree(self.afterroot, False, after_change_lines, raw_after_change_lines)
        else:
            after_trees = []

        if len(before_trees) == 0 and len(after_trees) == 0:
            #logger.warning('Empty commit, skipped.')
            return None
        
        return self.compare_change_tree(before_trees, after_trees)
        

    
    def compare_commit(self, commitinfo, r, c):
        change_pairs = {}
        for f in commitinfo:
            change_pairs[f] = {}
            beforefile, afterfile = commitinfo[f]['files']
            try:
                if beforefile:
                    self.beforeroot = ast.parse(open(beforefile, 'r').read())
                else:
                    self.beforeroot = None
                if afterfile:
                    self.afterroot = ast.parse(open(afterfile, 'r').read())
                else:
                    self.afterroot = None
            except Exception as e:
                logger.error(f'Cannot parse the source files, reason:{e}')
                continue
            for l in commitinfo[f]:
                #if l != 'def validate_args(args)':
                #    continue
                if l == 'files':
                    continue
                change_pairs[f][l] = []
                for commit in commitinfo[f][l]:
                    change_pair = self.compare_loc(commit['lines'], commit['content'])
                    if change_pair != None:
                        change_pairs[f][l].append(change_pair)
                        change_pair.metadata = {'repo': r, 'commit': c, 'file': f, 'loc': l, 'content': commit['content']}
                    #if change_pair:
                    #    change_pair.draw()
        
        return change_pairs
                    


    def compare_projects(self, datafile):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        change_pairs = {}
        for r in tqdm(data, desc = 'Generating Change Pairs'):
            #if r != 'AMWA-TV/nmos-testing':
            #    continue
            change_pairs[r] = {}
            for c in data[r]:
                #if c != '3a6957d662a3d8ff5fd2a0be045be763347f935c':
                #    continue
                change_pairs[r][c] = self.compare_commit(data[r][c], r, c)
        
        return change_pairs


    def compare_one(self, datafile, repo, commit):
        data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        change_pairs = {}
        for r in tqdm(data, desc = 'Generating Change Pairs'):
            if r != repo:
                continue
            change_pairs[r] = {}
            for c in data[r]:
                if c != commit:
                    continue
                change_pairs[r][c] = self.compare_commit(data[r][c], r, c)
        
        return change_pairs


class FixMiner(object):
    def __init__(self):
        self.fix_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.ori_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.id2template = {}
        self.index = 0
        self.fixed_id2template = {}
        self.category = None

    def subtree_compare(self, a, b):
        # Check whether a is a subtree of b
        if TemplateNode.compare(a, b):
            return b
        for c in b.children:
            for n in b.children[c]:
                sub_n = self.subtree_compare(a, n)
                if sub_n != None:
                    return sub_n
        return None

    def add_reference(self, ori, now):
        for c in ori.children:
            for on in ori.children[c]:
                if len(on.referred_from) > 0:
                    continue
                for nn in now.children[c]:
                    if len(nn.refer_to) > 0:
                        continue
                    if TemplateNode.compare(on, nn):
                        on.referred_from.append(nn)
                        nn.refer_to.append(on)
                        self.add_reference(on, nn)

    def include_compare(self, a, b):
        # Check whether b includes all nodes of a
        if TemplateNode.compare(a, b):
            return True
        if a.type != b.type or a.value != b.value or a.ast_type != b.ast_type:
            return False
        for ca in a.children:
            if ca not in b.children:
                return False
            for an in a.children[ca]:
                found = False
                paired_b = []
                for bi, bn in enumerate(b.children[ca]):
                    if bi in paired_b:
                        continue
                    if an.base_type not in ['Variable', 'Op', 'Builtin', 'Module', 'Literal', 'Attribute'] and self.include_compare(an, bn):
                        found = True
                        paired_b.append(bi)
                        break
                if not found:
                    return False
        return True


    def _cut_same_nodes(self, before_tree, after_tree, order):
        if before_tree == None or after_tree == None:
            return before_tree, after_tree, order
        changed = True
        while(changed):
            changed = False
            before_leaf_paths = before_tree.get_leaf_paths()
            after_leaf_paths = after_tree.get_leaf_paths()
            for bn in before_leaf_paths:
                if bn.base_type == 'Root':
                    continue
                for an in after_leaf_paths:
                    if an.base_type == 'Root':
                        continue
                    if TemplateNode.self_compare(an, bn) and TemplateTree.compare_leaf_path(before_leaf_paths[bn], after_leaf_paths[an]):
                        if bn.parent != None and bn.parent.base_type == 'Root' and order != None:
                            index = bn.parent.children['body'].index(bn)
                            new_order = []
                            for o in order['before']:
                                if o.startswith('Partially') and int(o.replace('Partially-', '')) > index:
                                    new_order.append('Partially-{}'.format(int(o.replace('Partially-', '')) - 1))
                                elif o.startswith('Partially') and int(o.replace('Partially-', '')) == index:
                                    pass
                                else:
                                    new_order.append(o)
                            order['before'] = new_order
                        if an.parent != None and an.parent.base_type == 'Root' and order != None:
                            index = an.parent.children['body'].index(an)
                            new_order = []
                            for o in order['after']:
                                if o.startswith('Partially') and int(o.replace('Partially-', '')) > index:
                                    new_order.append('Partially-{}'.format(int(o.replace('Partially-', '')) - 1))
                                elif o.startswith('Partially') and int(o.replace('Partially-', '')) == index:
                                    pass
                                else:
                                    new_order.append(o)
                            order['after'] = new_order
                        before_tree.remove(bn)
                        after_tree.remove(an)
                        changed = True
                        break
        
        if 'body' not in before_tree.root.children or len(before_tree.root.children['body']) == 0:
            before_tree = None
        if 'body' not in after_tree.root.children or len(after_tree.root.children['body']) == 0:
            after_tree = None



        return before_tree, after_tree, order

    


    def _process_replaced(self, pair):
        # In case the two partial trees are totally the same
        if len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0:
            partial_before_tree = TemplateTree()
            partial_before_tree.build(pair.status['Replaced']['before']['Partially'], partial = True)
            partial_after_tree = TemplateTree()
            partial_after_tree.build(pair.status['Replaced']['after']['Partially'], partial = True)
            partial_before_tree, partial_after_tree, pair.status['order'] = self._cut_same_nodes(partial_before_tree, partial_after_tree, pair.status['order'])
            if partial_before_tree == None and partial_after_tree == None:
                partial_empty = True
            else:
                partial_empty = False

        # Classify change pairs into Inserted, Shuffle and Replaced templates
        # Shuffle templates require no partially changed statements
        if len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0 and not partial_empty:
            # Check Insert, Add, Remove pattern
            if len(pair.status['Replaced']['before']['Partially']) > 0 and len(pair.status['Replaced']['after']['Partially']) > 0 and partial_before_tree != None and partial_after_tree != None:
                added = True
                removed = True
                for i, an in enumerate(partial_after_tree.root.children['body']):
                    if not self.include_compare(partial_before_tree.root.children['body'][i], an):
                        added = False
                    if not self.include_compare(an, partial_before_tree.root.children['body'][i]):
                        removed = False
                    if not added and not removed:
                        break
            elif partial_before_tree == None and partial_after_tree != None:
                added = True
                removed = False
            elif partial_after_tree == None and partial_before_tree != None:
                added = False
                removed = True
            else:
                added = False
                removed = False
            # Check Add pattern
            if added and len(pair.status['Replaced']['before']['Totally']) == 0:
                totally_after_tree = TemplateTree()
                totally_after_tree.build(pair.status['Replaced']['after']['Totally'])
                after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                partial_before_tree.reorder(pair.status['order']['before'], 'Partially')
                partial_before_tree.collect_special_nodes()
                after_tree.collect_special_nodes()
                partial_before_tree.set_treetype('Before')
                after_tree.set_treetype('After')
                template = FixTemplate('Add', partial_before_tree, after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['after']['Partially'] + pair.status['Replaced']['after']['Totally'], partial_before_tree, after_tree)
                template.before_contexts = before_contexts
                template.after_contexts = after_contexts
                template.add_instance(pair)
                return template
            # Check Remove pattern
            elif removed and len(pair.status['Replaced']['after']['Totally']) == 0:
                totally_before_tree = TemplateTree()
                totally_before_tree.build(pair.status['Replaced']['before']['Totally'])
                before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                partial_after_tree.reorder(pair.status['order']['after'], 'Partially')
                before_tree.collect_special_nodes()
                partial_after_tree.collect_special_nodes()
                before_tree.set_treetype('Before')
                partial_after_tree.set_treetype('After')
                template = FixTemplate('Remove', before_tree, partial_after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, None)
                template.before_contexts = before_contexts
                template.after_contexts = after_contexts
                template.add_instance(pair)
                return template
            # Check Insert pattern
            elif added:
                totally_before_tree = TemplateTree()
                totally_before_tree.build(pair.status['Replaced']['before']['Totally'])
                totally_after_tree = TemplateTree()
                totally_after_tree.build(pair.status['Replaced']['after']['Totally'])
                for bn in totally_before_tree.root.children['body']:
                    if len(bn.referred_from) == 0:
                        for an in totally_after_tree.root.children['body']:
                            sub_n = self.subtree_compare(bn, an)
                            if sub_n != None:
                                bn.referred_from.append(sub_n)
                                sub_n.refer_to.append(bn)
                                self.add_reference(bn, sub_n)
                all_referred = True
                for bn in totally_before_tree.root.children['body']:
                    if len(bn.referred_from) == 0:
                        all_referred = False
                        break
                if all_referred:
                    if partial_before_tree != None:
                        before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    else:
                        before_tree = totally_before_tree
                        before_tree.reorder(pair.status['order']['before'], 'Totally')
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    before_tree.collect_special_nodes()
                    after_tree.collect_special_nodes()
                    before_tree.set_treetype('Before')
                    after_tree.set_treetype('After')
                    template = FixTemplate('Insert', before_tree, after_tree)
                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, None)
                    template.before_contexts = before_contexts
                    template.after_contexts = after_contexts
                    template.add_instance(pair)
                    return template
                else:
                    if partial_before_tree != None:
                        before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    else:
                        before_tree = totally_before_tree
                        before_tree.reorder(pair.status['order']['before'], 'Totally')
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    before_tree.collect_special_nodes()
                    after_tree.collect_special_nodes()
                    before_tree.set_treetype('Before')
                    after_tree.set_treetype('After')
                    template = FixTemplate('Replace', before_tree, after_tree)
                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, None)
                    template.before_contexts = before_contexts
                    template.after_contexts = after_contexts
                    template.add_instance(pair)
                    return template
            #Remains are Replace patterns
            else:
                totally_before_tree = TemplateTree()
                totally_before_tree.build(pair.status['Replaced']['before']['Totally'])
                totally_after_tree = TemplateTree()
                totally_after_tree.build(pair.status['Replaced']['after']['Totally'])
                if partial_before_tree != None:
                    before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                else:
                    before_tree = totally_before_tree
                    before_tree.reorder(pair.status['order']['before'], 'Totally')
                if partial_after_tree != None:
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                else:
                    after_tree = totally_after_tree
                    after_tree.reorder(pair.status['order']['after'], 'Totally')
                before_tree.collect_special_nodes()
                after_tree.collect_special_nodes()
                before_tree.set_treetype('Before')
                after_tree.set_treetype('After')
                template = FixTemplate('Replace', before_tree, after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, None)
                template.before_contexts = before_contexts
                template.after_contexts = after_contexts
                template.add_instance(pair)
                return template
        else:
            before_tree = TemplateTree()
            before_tree.build(pair.status['Replaced']['before']['Totally'])
            before_tree.reorder(pair.status['order']['before'], 'Totally')
            after_tree = TemplateTree()
            after_tree.build(pair.status['Replaced']['after']['Totally'])
            after_tree.reorder(pair.status['order']['after'], 'Totally')
            if TemplateTree.compare(before_tree, after_tree):
                return None
            # Check Shuffle pattern
            if len(before_tree.root.children['body']) == len(after_tree.root.children['body']):
                before2after = {}
                after2before = {}
                for bi, bn in enumerate(before_tree.root.children['body']):
                    for ai, an in enumerate(after_tree.root.children['body']):
                        if TemplateNode.compare(bn, an) and ai not in after2before:
                            before2after[bi] = ai
                            after2before[ai] = bi
                for i in before2after:
                    before_tree.root.children['body'][i].referred_from.append(after_tree.root.children['body'][before2after[i]])
                    after_tree.root.children['body'][before2after[i]].refer_to.append(before_tree.root.children['body'][i])
                if len(before2after) == len(before_tree.root.children['body']) and len(after2before) == len(after_tree.root.children['body']):
                    before_tree.collect_special_nodes()
                    after_tree.collect_special_nodes()
                    before_tree.set_treetype('Before')
                    after_tree.set_treetype('After')
                    template = FixTemplate('Shuffle', before_tree, after_tree)
                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Totally'], before_tree, None)
                    template.before_contexts = before_contexts
                    template.after_contexts = after_contexts
                    template.add_instance(pair)
                    return template
            # Check Insert and Add pattern
            for bn in before_tree.root.children['body']:
                if len(bn.referred_from) == 0:
                    for an in after_tree.root.children['body']:
                        sub_n = self.subtree_compare(bn, an)
                        if sub_n != None:
                            bn.referred_from.append(sub_n)
                            sub_n.refer_to.append(bn)
                            self.add_reference(bn, sub_n)
            all_referred = True
            all_root_referred = True
            for bn in before_tree.root.children['body']:
                if len(bn.referred_from) == 0:
                    all_referred = False
                    all_root_referred = False
                    break
                elif len(bn.referred_from) > 0:
                    for n in bn.referred_from:
                        if n.parent.base_type != 'Root':
                            all_root_referred = False
            
            if all_root_referred:
                # Add patterns
                for bn in before_tree.root.children['body']:
                    for n in bn.referred_from:
                        after_tree.remove(n)
                after_tree.collect_special_nodes()
                after_tree.set_treetype('After')
                template = FixTemplate('Add', None, after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['after']['Totally'], None, after_tree)
                template.before_contexts = before_contexts
                template.after_contexts = after_contexts
                template.add_instance(pair)
                return template
            elif all_referred:
                # Insert patterns
                before_tree.collect_special_nodes()
                after_tree.collect_special_nodes()
                before_tree.set_treetype('Before')
                after_tree.set_treetype('After')
                template = FixTemplate('Insert', before_tree, after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Totally'], before_tree, None)
                template.before_contexts = before_contexts
                template.after_contexts = after_contexts
                template.add_instance(pair)
                return template
            # Remains are Replace patterns
            before_tree.collect_special_nodes()
            after_tree.collect_special_nodes()
            before_tree.set_treetype('Before')
            after_tree.set_treetype('After')
            template = FixTemplate('Replace', before_tree, after_tree)
            before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Totally'], before_tree, None)
            template.before_contexts = before_contexts
            template.after_contexts = after_contexts
            template.add_instance(pair)
            return template


    def abstract_node(self, a, b):
        if a.type == b.type and a.value == b.value and a.ast_type == b.ast_type:
            if a.value != None:
                a.value = 'ABSTRACTED'
                b.value = 'ABSTRACTED'
                a.value_abstracted = True
                b.value_abstracted = True
                
            for c in a.children:
                if c in b.children:
                    for i, n in enumerate(a.children[c]):
                        if i < len(b.children[c]):
                            a.children[c][i], b.children[c][i] = self.abstract_node(n, b.children[c][i])


        return a, b

    def abstract_templates(self):
        for c in self.fix_template:
            templates = self.fix_template[c]
            new_templates = []
            for t in templates:
                t.before, t.after, _ = self._cut_same_nodes(t.before, t.after, None)
                if t.before == None and t.after == None:
                    pass
                elif t.before == None or t.after == None:
                    new_templates.append(t)
                else:
                #    for i, bn in enumerate(t.before.root.children['body']):
                #        if i < len(t.after.root.children['body']):
                #            t.before.root.children['body'][i], t.after.root.children['body'][i] = self.abstract_node(bn, t.after.root.children['body'][i])
                    new_templates.append(t)
            self.fix_template[c] = new_templates

    def split_context(self):
        for c in self.fix_template:
            templates = self.fix_template[c]
            new_templates = []
            for t in templates:
                try:
                    old_t = deepcopy(t)
                    if t.before != None and t.after != None:
                        context = TemplateTree.get_same_subtree(t.before, t.after)
                        if context != None:
                            t.before, before_context_relations = TemplateTree.subtract_subtree(context, t.before, mode = 'before')
                            t.after, after_context_relations = TemplateTree.subtract_subtree(context, t.after, mode = 'after')
                            context.set_treetype('Within_Context')
                            if t.before:
                                t.before.set_treetype('Before')
                            if t.after:
                                t.after.set_treetype('After')
                            t.within_context = Context(context, [before_context_relations, after_context_relations], 'Within')
                        if t.before == None and t.after == None:
                            old_t.before.draw('old_t_before', filerepo = 'figures2')
                            old_t.after.draw('old_t_after', filerepo = 'figures2')
                            t.within_context.context_tree.draw('new_t_within', filerepo = 'figures2')
                            raise ValueError('Both before tree and after tree are empty after spliting context.')
                    new_templates.append(t)
                except Exception:
                    logger.error('Error occurred when spliting context, skipped.')
                    continue
            self.fix_template[c] = new_templates


    def build_before_and_after_contexts(self, changed_statements, before_tree, after_tree):
        # Only the following statements are included:
        # 1. Those have the same parent with the changed statements
        # 2. Those share same variables/attributes/literal with the changed statements
        before_contexts = []
        after_contexts = []
        index_map = {}
        before_statements, after_statements = ChangeTree.build_before_and_after_contexts(changed_statements)
        for s in before_statements:
            index_map[s] = 'before'
        for s in after_statements:
            index_map[s] = 'after'
        for cs in before_statements + after_statements:
            temp_tree = TemplateTree()
            temp_tree.build([cs])
            reserve = False
            if before_tree:
                for v in temp_tree.variables:
                    for bv in before_tree.variables:
                        if TemplateNode.self_compare(v, bv):
                            reserve = True
                            v.refer_to.append(bv)
                            bv.context_refer.append(v)
                for v in temp_tree.literals:
                    for bv in before_tree.literals:
                        if TemplateNode.self_compare(v, bv) and v.value not in [None, True, False]:
                            reserve = True
                            v.refer_to.append(bv)
                            bv.context_refer.append(v)
            if after_tree:
                for v in temp_tree.variables:
                    for av in after_tree.variables:
                        if TemplateNode.self_compare(v, av):
                            reserve = True
                            v.refer_to.append(av)
                            av.context_refer.append(v)
                for v in temp_tree.literals:
                    for av in after_tree.literals:
                        if TemplateNode.self_compare(v, av) and v.value not in [None, True, False]:
                            reserve = True
                            v.refer_to.append(av)
                            av.context_refer.append(v)
            for v in temp_tree.attributes:
                if before_tree:
                    for bv in before_tree.attributes:
                        if TemplateNode.self_compare(v, bv):
                            reserve = True
                            v.refer_to.append(bv)
                            bv.context_refer.append(v)
                        elif v.value.startswith(bv.value):
                            reserve = True
                            if bv.value not in v.attribute_refer_to:
                                v.attribute_refer_to[bv.value] = []
                            v.attribute_refer_to[bv.value].append(bv)
                            bv.attribute_referred_from.append(v)
                    for bv in before_tree.variables:
                        if v.value.startswith(bv.value):
                            reserve = True
                            if bv.value not in v.attribute_refer_to:
                                v.attribute_refer_to[bv.value] = []
                            v.attribute_refer_to[bv.value].append(bv)
                            bv.attribute_referred_from.append(v)
                if after_tree:
                    for av in after_tree.attributes:
                        if TemplateNode.self_compare(v, av):
                            reserve = True
                            v.refer_to.append(av)
                            av.context_refer.append(v)
                        elif v.value.startswith(av.value):
                            reserve = True
                            if av.value not in v.attribute_refer_to:
                                v.attribute_refer_to[av.value] = []
                            v.attribute_refer_to[av.value].append(av)
                            av.attribute_referred_from.append(v)
                    for av in after_tree.variables:
                        if v.value.startswith(av.value):
                            reserve = True
                            if av.value not in v.attribute_refer_to:
                                v.attribute_refer_to[av.value] = []
                            v.attribute_refer_to[av.value].append(av)
                            av.attribute_referred_from.append(v)
            if index_map[cs] == 'before' and reserve and type(cs.node) not in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
                temp_tree.prune_no_ref_subtree()
                before_contexts.append(temp_tree)
            elif index_map[cs] == 'after' and reserve and type(cs.node) not in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
                temp_tree.prune_no_ref_subtree()
                after_contexts.append(temp_tree)
            else:
                for n in temp_tree.iter_nodes():
                    for nn in n.refer_to:
                        nn.context_refer.remove(n)
        
        final_before_contexts = []
        final_after_contexts = []
        for bc in before_contexts:
            exist = False
            for c in final_before_contexts:
                if TemplateTree.compare(bc, c):
                    exist = True
                    break
            if not exist:
                final_before_contexts.append(bc)
            else:
                for n in bc.iter_nodes():
                    for nn in n.refer_to:
                        nn.context_refer.remove(n)
        
        for ac in after_contexts:
            exist = False
            for c in final_after_contexts:
                if TemplateTree.compare(ac, c):
                    exist = True
                    break
            if not exist:
                final_after_contexts.append(ac)
            else:
                for n in ac.iter_nodes():
                    for nn in n.refer_to:
                        nn.context_refer.remove(n)

        before_contexts = Context.build_external_context(final_before_contexts, 'Before')
        if before_contexts:
            before_contexts.context_tree.set_treetype('Before_Context')
        after_contexts = Context.build_external_context(final_after_contexts, 'After')
        if after_contexts:
            after_contexts.context_tree.set_treetype('After_Context')

        return before_contexts, after_contexts

    def build_templates(self, change_pairs):
        for r in tqdm(change_pairs, desc = 'Initializing Fix Templates'):
            for c in change_pairs[r]:
                for f in change_pairs[r][c]:
                    for l in change_pairs[r][c][f]:
                        for pair in change_pairs[r][c][f][l]:
                            try:
                                if len(pair.status['Added']['Totally']) + len(pair.status['Added']['Partially']) > 0:
                                    totally_after_tree = None
                                    partial_after_tree = None
                                    if len(pair.status['Added']['Totally']) > 0:
                                        totally_after_tree = TemplateTree()
                                        totally_after_tree.build(pair.status['Added']['Totally'])
                                    if len(pair.status['Added']['Partially']) > 0:
                                        partial_after_tree = TemplateTree()
                                        partial_after_tree.build(pair.status['Added']['Partially'])
                                    if totally_after_tree != None and partial_after_tree != None:
                                        after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                                    else:
                                        if totally_after_tree:
                                            after_tree = totally_after_tree
                                            after_tree.reorder(pair.status['order']['after'], 'Totally')
                                        else:
                                            after_tree = partial_after_tree
                                            after_tree.reorder(pair.status['order']['after'], 'Partially')
                                    after_tree.collect_special_nodes()
                                    template = FixTemplate('Add', None, after_tree)
                                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Added']['Totally'] + pair.status['Added']['Partially'], None, after_tree)
                                    template.before_contexts = before_contexts
                                    template.after_contexts = after_contexts
                                    template.add_instance(pair)
                                    template.set_treetype()
                                    self.fix_template['Add'].append(template)
                                    continue
                                if len(pair.status['Removed']['Totally']) + len(pair.status['Removed']['Partially']) > 0:
                                    totally_before_tree = None
                                    partial_before_tree = None
                                    if len(pair.status['Removed']['Totally']) > 0:
                                        totally_before_tree = TemplateTree()
                                        totally_before_tree.build(pair.status['Removed']['Totally'])
                                    if len(pair.status['Removed']['Partially']) > 0:
                                        partial_before_tree = TemplateTree()
                                        partial_before_tree.build(pair.status['Removed']['Partially'])
                                    if totally_before_tree != None and partial_before_tree != None:
                                        before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                                    else:
                                        if totally_before_tree:
                                            before_tree = totally_before_tree
                                            before_tree.reorder(pair.status['order']['before'], 'Totally')
                                        else:
                                            before_tree = partial_before_tree
                                            before_tree.reorder(pair.status['order']['before'], 'Partially')
                                    before_tree.collect_special_nodes()
                                    template = FixTemplate('Remove', before_tree, None)
                                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Removed']['Totally'] + pair.status['Removed']['Partially'], before_tree, None)
                                    template.before_contexts = before_contexts
                                    template.after_contexts = after_contexts
                                    template.add_instance(pair)
                                    template.set_treetype()
                                    self.fix_template['Remove'].append(template)
                                    continue
                                if len(pair.status['Replaced']['before']['Totally']) + len(pair.status['Replaced']['after']['Totally']) > 0 or \
                                len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0:
                                    if len(pair.status['Replaced']['before']['Partially']) != len(pair.status['Replaced']['after']['Partially']) and\
                                    len(pair.status['Replaced']['before']['Partially']) > 0 and len(pair.status['Replaced']['after']['Partially']) > 0:
                                        logger.error('Inconsistent number of partially changed statements before and after the commit, skipped this commit.')
                                        continue
                                    template = self._process_replaced(pair)
                                    if template != None:
                                        template.set_treetype()
                                        self.fix_template[template.action].append(template)
                            except Exception as e:
                                logger.error('Error occurred when initializing template, skipped.')
                                continue
        self.clean()
        self.abstract_templates()
        print('Splitting within contexts...')
        self.split_context()
        self.reclassify_templates()
        self.clean_insert_reference()
        self.assign_ids()
        self.clean_external_contexts()
        for i in tqdm(self.id2template, desc = 'Copying Tempaltes'):
            self.fixed_id2template[i] = deepcopy(self.id2template[i])

    
    def reclassify_templates(self):
        replace = []
        remove = []
        for t in self.fix_template['Add']:
            if t.before != None and t.after != None:
                replace.append(t)
            if t.before == None and t.after != None:
                remove.append(t)
        for t in replace:
            self.fix_template['Add'].remove(t)
            self.fix_template['Replace'].append(t)
            t.action = 'Replace'
        for t in remove:
            self.fix_template['Add'].remove(t)
            self.fix_template['Remove'].append(t)
            t.action = 'Remove'
        replace = []
        add = []
        for t in self.fix_template['Remove']:
            if t.before != None and t.after != None:
                replace.append(t)
            if t.before == None and t.after != None:
                add.append(t)
        for t in replace:
            self.fix_template['Remove'].remove(t)
            self.fix_template['Replace'].append(t)
            t.action = 'Replace'
        for t in add:
            self.fix_template['Remove'].remove(t)
            self.fix_template['Add'].append(t)
            t.action = 'Add'
        add = []
        remove = []
        replace = []
        for t in self.fix_template['Insert']:
            if t.before != None and t.after != None:
                replace.append(t)
            if t.before == None and t.after != None:
                add.append(t)
            if t.before != None and t.after == None:
                remove.append(t)
        for t in replace:
            self.fix_template['Insert'].remove(t)
            self.fix_template['Replace'].append(t)
            t.action = 'Replace'
        for t in add:
            self.fix_template['Insert'].remove(t)
            self.fix_template['Add'].append(t)
            t.action = 'Add'
        for t in remove:
            self.fix_template['Insert'].remove(t)
            self.fix_template['Remove'].append(t)
            t.action = 'Remove'
        add = []
        remove = []
        for t in self.fix_template['Replace']:
            if t.before == None and t.after != None:
                add.append(t)
            if t.before != None and t.after == None:
                remove.append(t)
        for t in add:
            self.fix_template['Replace'].remove(t)
            self.fix_template['Add'].append(t)
            t.action = 'Add'
        for t in remove:
            self.fix_template['Replace'].remove(t)
            self.fix_template['Remove'].append(t)
            t.action = 'Remove'

        #check insert and shuffle patterns in replace templates again
        insert = []
        shuffle = []
        for t in self.fix_template['Replace']:
            for bn in t.before.root.children['body']:
                if len(bn.referred_from) == 0:
                    for an in t.after.root.children['body']:
                        sub_n = self.subtree_compare(bn, an)
                        if sub_n != None:
                            bn.referred_from.append(sub_n)
                            sub_n.refer_to.append(bn)
                            self.add_reference(bn, sub_n)
            all_referred = True
            for bn in t.before.root.children['body']:
                if len(bn.referred_from) == 0:
                    all_referred = False
                    break
            if all_referred:
                all_after_referred = False
                for an in t.after.root.children['body']:
                    if len(an.refer_to) == 0:
                        all_after_referred = False
                        break
                if not all_after_referred:
                    insert.append(t)
                else:
                    shuffle.append(t)
        
        for t in insert:
            self.fix_template['Replace'].remove(t)
            self.fix_template['Insert'].append(t)
            t.action = 'Insert'
        
        for t in shuffle:
            self.fix_template['Replace'].remove(t)
            self.fix_template['Shuffle'].append(t)
            t.action = 'Shuffle'

    def clean_insert_reference(self):
        for t in self.fix_template['Insert']:
            for bn in t.before.root.children['body']:
                for an in bn.referred_from:
                    an.type = 'Reference'
                    an.base_type = 'Reference'
                    an.ast_type = None
                    an.context_refer = []
                    an.attribute_refer_to = {}
                    an.attribute_referred_from = []
                    an.value = None
                    an.ctx = None
                    for c in an.children:
                        for nn in an.children[c]:
                            self.clean_subtree_reference(nn)
                            nn.parent = None
                            nn.parent_relation = None
                    an.children = {}
                for c in bn.children:
                    for nn in bn.children[c]:
                        self.clean_subtree_reference(nn, mode = 'referred_from')


    def clean_external_contexts(self):
        for c in self.fix_template:
            for t in self.fix_template[c]:
                if t.before_contexts:
                    leaf_nodes = t.before_contexts.context_tree.get_leaf_nodes()
                    removed = []
                    for n in leaf_nodes:
                        remove = True
                        for nn in n.refer_to:
                            if nn.id != None:
                                remove = False
                                break
                        if remove:
                            removed.append(n)
                    for r in removed:
                        t.before_contexts.context_tree.remove_path(r)
                    if len(t.before_contexts.context_tree.root.children) == 0 or len(t.before_contexts.context_tree.root.children['body']) == 0:
                        t.before_contexts = None

                if t.after_contexts:
                    leaf_nodes = t.after_contexts.context_tree.get_leaf_nodes()
                    removed = []
                    for n in leaf_nodes:
                        remove = True
                        for nn in n.refer_to:
                            if nn.id != None:
                                remove = False
                                break
                        if remove:
                            removed.append(n)
                    for r in removed:
                        t.after_contexts.context_tree.remove_path(r)
                    if len(t.after_contexts.context_tree.root.children) == 0 or len(t.after_contexts.context_tree.root.children['body']) == 0:
                        t.after_contexts = None

    def assign_ids(self):
        for c in self.fix_template:
            for t in self.fix_template[c]:
                t.id = self.index
                self.id2template[self.index] = t
                self.index += 1   
                t.set_node_ids()
                t.cal_self_reference()

    def clean(self):
        # Remove those could not be fix templates
        num = 0 
        # Case 1: Only add/remove a whole function or class
        removed = []
        for t in self.fix_template['Add']:
            if t.before != None:
                continue
            remove = True
            for n in t.after.root.children['body']:
                if n.ast_type not in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
                    remove = False
                    break
            if remove:
                removed.append(t)
        for t in removed:
            self.fix_template['Add'].remove(t)
        num += len(removed)
        removed = []
        for t in self.fix_template['Remove']:
            if t.after != None:
                continue
            remove = True
            for n in t.before.root.children['body']:
                if n.ast_type not in [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
                    remove = False
                    break
            if remove:
                removed.append(t)
        for t in removed:
            self.fix_template['Remove'].remove(t)
        num += len(removed)
        # Case 2: Before and After tree are totally the same
        for c in self.fix_template:
            removed = []
            for t in self.fix_template[c]:
                if TemplateTree.compare(t.before, t.after):
                    removed.append(t)
            for r in removed:
                self.fix_template[c].remove(r)
            num += len(removed)
        # Case 3: Only contain import statements
        for c in self.fix_template:
            removed = []
            for t in self.fix_template[c]:
                found = True
                if t.before != None:
                    for n in t.before.root.children['body']:
                        if n.type not in ['ImportFrom', 'Import']:
                            found = False
                            break
                if found and t.after != None:
                    for n in t.after.root.children['body']:
                        if n.type not in ['ImportFrom', 'Import']:
                            found = False
                            break
                if found:
                    removed.append(t)
            for r in removed:
                self.fix_template[c].remove(r)
            num += len(removed)
        # Case 4: Only contains strs
        removed = []
        for t in self.fix_template['Replace']:
            found = True
            if t.before != None and t.after != None and TemplateNode.value_abstract_compare(t.before.root, t.after.root):
                for n in t.before.root.children['body']:
                    if n.type != 'Expr':
                        found = False
                        break
                    inner_found = True
                    for c in n.children:
                        for innode in n.children[c]:
                            if innode.base_type != 'Literal':
                                inner_found = False
                                break
                            if type(innode.value) != str:
                                inner_found = False
                                break
                    if not inner_found:
                        found = False
                        break
                for n in t.after.root.children['body']:
                    if n.type != 'Expr':
                        found = False
                        break
                    inner_found = True
                    for c in n.children:
                        for innode in n.children[c]:
                            if innode.base_type != 'Literal':
                                inner_found = False
                                break
                            if type(innode.value) != str:
                                inner_found = False
                                break
                    if not inner_found:
                        found = False
                        break
            else:
                found = False
            if found:
                removed.append(t)
        for r in removed:
            self.fix_template['Replace'].remove(r)
        num += len(removed)

        print('Cleaned {} templates.'.format(num))


    def print_info(self, templates = None):
        if templates == None:
            print('Information of fix templates:')
            for c in self.fix_template:
                print(c, len(self.fix_template[c]))

            print('Total: {} templates.'.format(len(self.id2template)))     
        else:
            num = {}
            for t in templates:
                if len(t.instances) not in num:
                    num[len(t.instances)] = 1
                else:
                    num[len(t.instances)] += 1

            sorted_num = sorted(list(num.keys()), reverse = True)
            
            print('Information of clustered fix templates:')
            for n in sorted_num:
                print('{} instances: {}'.format(n, num[n]))

    def adjust_pair(self, pair):
        new_pair = []
        for p in pair:
            new_pair.append([p[1], p[0], p[2]])
        
        return new_pair

    def initialize_distances(self, templates):
        distances = {
            'accurate': {
                'pattern': {}, 'before_pattern': {}, 'after_pattern': {}, 'within': {}, 'before': {}, 'after': {}, 'external': {}
            },
            'structural': {
                'pattern': {}, 'before_pattern': {}, 'after_pattern': {}, 'within': {}, 'before': {}, 'after': {}, 'external': {}
            }
        }
        pairs = {
            'accurate': {
                'within': {}, 'before': {}, 'after': {}
            },
            'structural': {
                'within': {}, 'before': {}, 'after': {}
            }
        }
        for i, t in tqdm(enumerate(templates), desc = 'Initializing Distances between Templates'):
            for j in range(i+1, len(templates)):
                if t not in distances['accurate']['pattern']:
                    for k in distances:
                        for ik in distances[k]:
                            distances[k][ik][t] = {}
                    for k in pairs:
                        for ik in pairs[k]:
                            pairs[k][ik][t] = {}
                if templates[j] not in distances['accurate']['pattern']:
                    for k in distances:
                        for ik in distances[k]:
                            distances[k][ik][templates[j]] = {}
                    for k in pairs:
                        for ik in pairs[k]:
                            pairs[k][ik][templates[j]] = {}
                d, before_d, after_d = FixTemplate.get_distance_for_pattern(t, templates[j])
                structural_d, structural_before_d, structural_after_d = FixTemplate.get_structural_distance_for_pattern(t, templates[j])

                if self.is_before_mergable(t, templates[j]):
                    distances['accurate']['before_pattern'][t][templates[j]] = before_d
                    distances['accurate']['before_pattern'][templates[j]][t] = before_d
                    distances['structural']['before_pattern'][t][templates[j]] = structural_before_d
                    distances['structural']['before_pattern'][templates[j]][t] = structural_before_d
                else:
                    distances['accurate']['before_pattern'][t][templates[j]] = -9999
                    distances['accurate']['before_pattern'][templates[j]][t] = -9999
                    distances['structural']['before_pattern'][t][templates[j]] = -9999
                    distances['structural']['before_pattern'][templates[j]][t] = -9999

                if self.is_after_mergable(t, templates[j]):
                    distances['accurate']['after_pattern'][t][templates[j]] = after_d
                    distances['accurate']['after_pattern'][templates[j]][t] = after_d
                    distances['structural']['after_pattern'][t][templates[j]] = structural_after_d
                    distances['structural']['after_pattern'][templates[j]][t] = structural_after_d
                else:
                    distances['accurate']['after_pattern'][t][templates[j]] = -9999
                    distances['accurate']['after_pattern'][templates[j]][t] = -9999
                    distances['structural']['after_pattern'][t][templates[j]] = -9999
                    distances['structural']['after_pattern'][templates[j]][t] = -9999

                if (self.category == 'Replace' and self.is_pattern_mergable(t, templates[j], mode = 'num')) or (self.category in ['Add', 'Remove', 'Insert'] and self.is_pattern_mergable(t, templates[j], mode = 'num')):
                    distances['accurate']['pattern'][t][templates[j]] = d
                    distances['accurate']['pattern'][templates[j]][t] = d
                    distances['structural']['pattern'][t][templates[j]] = structural_d
                    distances['structural']['pattern'][templates[j]][t] = structural_d
                else:
                    distances['accurate']['pattern'][t][templates[j]] = -9999
                    distances['accurate']['pattern'][templates[j]][t] = -9999
                    distances['structural']['pattern'][t][templates[j]] = -9999
                    distances['structural']['pattern'][templates[j]][t] = -9999

                d, p = FixTemplate.get_distance_for_context(t, templates[j])
                structural_d, structural_p = FixTemplate.get_structural_distance_for_context(t, templates[j])
                
                if self.is_within_context_mergable(t, templates[j]):
                    distances['accurate']['within'][t][templates[j]] = d['within']
                    distances['accurate']['within'][templates[j]][t] = d['within']
                    distances['structural']['within'][t][templates[j]] = structural_d['within']
                    distances['structural']['within'][templates[j]][t] = structural_d['within']
                    pairs['accurate']['within'][t][templates[j]] = p['within']
                    pairs['accurate']['within'][templates[j]][t] = self.adjust_pair(p['within'])
                    pairs['structural']['within'][t][templates[j]] = structural_p['within']
                    pairs['structural']['within'][templates[j]][t] = self.adjust_pair(structural_p['within'])
                else:
                    distances['accurate']['within'][t][templates[j]] = -9999
                    distances['accurate']['within'][templates[j]][t] = -9999
                    distances['structural']['within'][t][templates[j]] = -9999
                    distances['structural']['within'][templates[j]][t] = -9999
                    pairs['accurate']['within'][t][templates[j]] = []
                    pairs['accurate']['within'][templates[j]][t] = []
                    pairs['structural']['within'][t][templates[j]] = []
                    pairs['structural']['within'][templates[j]][t] = []
                
                for k in ['before', 'after', 'external']:
                    distances['accurate'][k][t][templates[j]] = d[k]
                    distances['accurate'][k][templates[j]][t] = d[k]
                for k in ['before', 'after', 'external']:
                    distances['structural'][k][t][templates[j]] = structural_d[k]
                    distances['structural'][k][templates[j]][t] = structural_d[k]
                for k in ['before', 'after']:
                    pairs['accurate'][k][t][templates[j]] = p[k]
                    pairs['accurate'][k][templates[j]][t] = self.adjust_pair(p[k])
                for k in ['before', 'after']:
                    pairs['structural'][k][t][templates[j]] = structural_p[k]
                    pairs['structural'][k][templates[j]][t] = self.adjust_pair(structural_p[k])

        return distances, pairs

    def add_distances(self, distances, pairs, template, templates):
        for k in distances:
            for ik in distances[k]:
                distances[k][ik][template] = {}
        for k in pairs:
            for ik in pairs[k]:
                pairs[k][ik][template] = {}
        for t in templates:
            d, before_d, after_d = FixTemplate.get_distance_for_pattern(t, template)
            structural_d, structural_before_d, structural_after_d = FixTemplate.get_structural_distance_for_pattern(t, template)

            if self.is_before_mergable(t, template):
                distances['accurate']['before_pattern'][t][template] = before_d
                distances['accurate']['before_pattern'][template][t] = before_d
                distances['structural']['before_pattern'][t][template] = structural_before_d
                distances['structural']['before_pattern'][template][t] = structural_before_d
            else:
                distances['accurate']['before_pattern'][t][template] = -9999
                distances['accurate']['before_pattern'][template][t] = -9999
                distances['structural']['before_pattern'][t][template] = -9999
                distances['structural']['before_pattern'][template][t] = -9999

            if self.is_after_mergable(t, template):
                distances['accurate']['after_pattern'][t][template] = after_d
                distances['accurate']['after_pattern'][template][t] = after_d
                distances['structural']['after_pattern'][t][template] = structural_after_d
                distances['structural']['after_pattern'][template][t] = structural_after_d
            else:
                distances['accurate']['after_pattern'][t][template] = -9999
                distances['accurate']['after_pattern'][template][t] = -9999
                distances['structural']['after_pattern'][t][template] = -9999
                distances['structural']['after_pattern'][template][t] = -9999

            if (self.category == 'Replace' and self.is_pattern_mergable(t, template, mode = 'num')) or (self.category in ['Add', 'Remove', 'Insert'] and self.is_pattern_mergable(t, template, mode = 'num')):
                distances['accurate']['pattern'][t][template] = d
                distances['accurate']['pattern'][template][t] = d
                distances['structural']['pattern'][t][template] = structural_d
                distances['structural']['pattern'][template][t] = structural_d
            else:
                distances['accurate']['pattern'][t][template] = -9999
                distances['accurate']['pattern'][template][t] = -9999
                distances['structural']['pattern'][t][template] = -9999
                distances['structural']['pattern'][template][t] = -9999

            d, p = FixTemplate.get_distance_for_context(t, template)
            structural_d, structural_p = FixTemplate.get_structural_distance_for_context(t, template)
            
            if self.is_within_context_mergable(t, template):
                distances['accurate']['within'][t][template] = d['within']
                distances['accurate']['within'][template][t] = d['within']
                distances['structural']['within'][t][template] = structural_d['within']
                distances['structural']['within'][template][t] = structural_d['within']
                pairs['accurate']['within'][t][template] = p['within']
                pairs['accurate']['within'][template][t] = self.adjust_pair(p['within'])
                pairs['structural']['within'][t][template] = structural_p['within']
                pairs['structural']['within'][template][t] = self.adjust_pair(structural_p['within'])
            else:
                distances['accurate']['within'][t][template] = -9999
                distances['accurate']['within'][template][t] = -9999
                distances['structural']['within'][t][template] = -9999
                distances['structural']['within'][template][t] = -9999
                pairs['accurate']['within'][t][template] = []
                pairs['accurate']['within'][template][t] = []
                pairs['structural']['within'][t][template] = []
                pairs['structural']['within'][template][t] = []
            
            for k in ['before', 'after', 'external']:
                distances['accurate'][k][t][template] = d[k]
                distances['accurate'][k][template][t] = d[k]
            for k in ['before', 'after', 'external']:
                distances['structural'][k][t][template] = structural_d[k]
                distances['structural'][k][template][t] = structural_d[k]
            for k in ['before', 'after']:
                pairs['accurate'][k][t][template] = p[k]
                pairs['accurate'][k][template][t] = self.adjust_pair(p[k])
            for k in ['before', 'after']:
                pairs['structural'][k][t][template] = structural_p[k]
                pairs['structural'][k][template][t] = self.adjust_pair(structural_p[k])

        return distances, pairs

    def get_max_distance(self, distances, valid_distances, templates, validate = True, extra_distances = None):
        max_distance = -9999
        max_pair = []
        for i, t in enumerate(templates):
            for j in range(i+1, len(templates)):
                if distances[t][templates[j]] > max_distance:
                    if validate and valid_distances[t][templates[j]] != -9999:
                        if extra_distances != None and extra_distances[t][templates[j]] != -9999:
                            max_distance = distances[t][templates[j]]
                            max_pair = [t, templates[j]]
                        elif extra_distances == None:
                            max_distance = distances[t][templates[j]]
                            max_pair = [t, templates[j]]
                    elif not validate:
                        max_distance = distances[t][templates[j]]
                        max_pair = [t, templates[j]]
        if len(max_pair) == 2:
            return *max_pair, max_distance
        else:
            return None, None, max_distance

    def print_distances(self, distances, templates, category = None):
        if category:
            lines = []
            line = ''
            for t in templates:
                line = ',' + str(t.id)
            lines.append(line)
            for t in templates:
                line = str(t.id)
                for tt in templates:
                    line += ','
                    if t.id != tt.id:
                        line += '{};{}'.format(distances['accurate'][category][t][tt], distances['structural'][category][t][tt])
                lines.append(line)
            with open('distances_{}.csv'.format(category), 'w', encoding = 'utf-8') as cf:
                cf.write('\n'.join(lines))
        else:
            for category in ['pattern', 'within', 'before', 'after', 'external', 'before_pattern', 'after_pattern']:
                lines = []
                line = ''
                for t in templates:
                    line += ',' + str(t.id)
                lines.append(line)
                for t in templates:
                    line = str(t.id)
                    for tt in templates:
                        line += ','
                        if t.id != tt.id:
                            line += '{};{}'.format(distances['accurate'][category][t][tt], distances['structural'][category][t][tt])
                    lines.append(line)
                with open('distances_{}.csv'.format(category), 'w', encoding = 'utf-8') as cf:
                    cf.write('\n'.join(lines))



    def select_most_abstracted_tree(self, trees):
        max_num = -9999
        max_tree = None
        for t in trees:
            if t == None:
                continue
            abs_num = t.get_abstracted_num()
            if abs_num > max_num:
                max_num = abs_num
                max_tree = t

        return max_tree

    def is_pattern_mergable(self, a, b, mode = 'exact'):
        if (a.before == None and b.before != None) or\
        (a.before != None and b.before == None) or\
        (a.after == None and b.after != None) or\
        (a.after != None and b.after == None):
            return False
        
        before = True
        if a.before and b.before:
            if len(a.before.root.children['body']) != len(b.before.root.children['body']):
                before = False
            elif mode == 'num':
                for index, n in enumerate(a.before.root.children['body']):
                    if n.type != b.before.root.children['body'][index].type and n.type in ['Stmt', 'Expr', 'End_Expr'] and b.before.root.children['body'][index].type in ['Stmt', 'Expr', 'End_Expr']:
                        before = False
                        break
            elif mode == 'exact':
                for index, n in enumerate(a.before.root.children['body']):
                    if not TemplateNode.is_type_compatible(n, b.before.root.children['body'][index]):
                        before = False
                        break

        after = True
        if a.after and b.after:
            if len(a.after.root.children['body']) != len(b.after.root.children['body']):
                after = False
            elif mode == 'num':
                for index, n in enumerate(a.after.root.children['body']):
                    if n.type != b.after.root.children['body'][index].type and n.type in ['Stmt', 'Expr', 'End_Expr'] and b.after.root.children['body'][index].type in ['Stmt', 'Expr', 'End_Expr']:
                        before = False
                        break
            elif mode == 'exact':
                for index, n in enumerate(a.after.root.children['body']):
                    if not TemplateNode.is_type_compatible(n, b.after.root.children['body'][index]):
                        after = False
                        break
        
        
        if before and after:
            return True
        else:
            return False

    def is_before_mergable(self, a, b):
        before = True
        if a.before and b.before:
            if len(a.before.root.children['body']) != len(b.before.root.children['body']):
                before = False
            else:
                for index, n in enumerate(a.before.root.children['body']):
                    if n.type != b.before.root.children['body'][index].type and n.type in ['Stmt', 'Expr', 'End_Expr'] and b.before.root.children['body'][index].type in ['Stmt', 'Expr', 'End_Expr']:
                        before = False
                        break
        elif (a.before == None and b.before != None) or (a.before != None and b.before == None):
            before = False
        return before


    def is_after_mergable(self, a, b):
        after = True
        if a.after and b.after:
            if len(a.after.root.children['body']) != len(b.after.root.children['body']):
                after = False
            else:
                for index, n in enumerate(a.after.root.children['body']):
                    if not TemplateNode.is_type_compatible(n, b.after.root.children['body'][index]):
                        after = False
                        break
            a.after.collect_special_nodes()
            b.after.collect_special_nodes()
            if len(a.after.references) != len(b.after.references):
                after = False
            else:
                for index, r in enumerate(a.after.references):
                    a_path = a.after.get_path_to_root(r)
                    b_path = b.after.get_path_to_root(b.after.references[index])
                    if not TemplateTree.compare_leaf_path(a_path, b_path):
                        after = False
                        break
        elif (a.after == None and b.after != None) or (a.after != None and b.after == None):
            after = False
        return after


    def is_within_context_mergable(self, a, b):
        if (a.within_context == None and b.within_context != None) or\
            (a.within_context != None and b.within_context == None):
            return False
        
        if a.within_context and b.within_context:
            a_nodes = a.within_context.get_within_relation_nodes()
            b_nodes = b.within_context.get_within_relation_nodes()
            if len(a_nodes) != len(b_nodes):
                return False

            for index, n in enumerate(a_nodes):
                if not TemplateNode.self_compare(n, b_nodes[index]):
                    return False

        return True


    def get_topn_templates(self, topn, templates):
        num = {}
        for t in templates:
            if len(t.instances) not in num:
                num[len(t.instances)] = [t]
            else:
                num[len(t.instances)].append(t)
        
        nums = sorted(list(num.keys()), reverse = True)
        results = []
        total = 0
        for n in nums:
            for t in num[n]:
                results.append(t)
                total += 1
                if total >= topn:
                    return results
        
        return results

    def draw_templates(self, templates, path, dump_instances = True, draw_contexts = True, draw_children = False, dump_attributes = False):
        child_templates = []
        if draw_children:
            for t in templates:
                child_templates += [self.fixed_id2template[i] for i in t.get_child_template_ids(self.fixed_id2template)]
            
        for t in templates + child_templates:
            try:
                t.draw(self.fixed_id2template, filerepo = path, draw_contexts = draw_contexts, dump_attributes = dump_attributes)
            except:
                pass
            if dump_instances:
                text = ""
                for i in t.instances:
                    if isinstance(i, ChangePair):
                        text += '========================{}:{}========================\n{}\n=================================================================\n'.format(i.metadata['repo'], i.metadata['commit'], i.metadata['content'])
                    else:
                        text += '========================{}:{}========================\n{}\n=================================================================\n'.format(i['repo'], i['commit'], i['content'])
                if t.parent_template != None:
                    filename = os.path.join(path, 'FIX_TEMPLATE_{}_INSTANCES.txt'.format(t.id))
                else:
                    filename = os.path.join(path, 'FINAL_FIX_TEMPLATE_{}_INSTANCES.txt'.format(t.id))
                with open(filename, 'w', encoding = 'utf-8') as f:
                    f.write(text)


    def is_set_identical(self, a, b):
        if len(a) == len(b) and len(a) == 0:
            return True
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

    def clean_reference(self, node, mode = 'all'):
        if len(node.referred_from) > 0 and mode in ['all', 'referred_from']:
            for n in node.referred_from:
                if node in n.refer_to:
                    n.refer_to.remove(node)
            node.referred_from = []
        if len(node.refer_to) > 0 and mode in ['all', 'refer_to']:
            for n in node.refer_to:
                if node in n.referred_from:
                    n.referred_from.remove(node)
            node.refer_to = []
        if len(node.context_refer) > 0 and mode in ['all', 'context_refer']:
            for n in node.context_refer:
                if node in n.refer_to:
                    n.refer_to.remove(node)
            node.context_refer = []
        if len(node.self_refer) > 0 and mode in ['all', 'self_refer']:
            for n in node.self_refer:
                if node in n.self_refer:
                    n.self_refer.remove(node)
            node.self_refer = []

    def clean_subtree_reference(self, node, mode = 'all'):
        if len(node.referred_from) > 0 and mode in ['all', 'referred_from']:
            for n in node.referred_from:
                if node in n.refer_to:
                    n.refer_to.remove(node)
            node.referred_from = []
            for c in node.children:
                for n in node.children[c]:
                    self.clean_subtree_reference(n, mode = mode)
        if len(node.refer_to) > 0 and mode in ['all', 'refer_to']:
            for n in node.refer_to:
                if node in n.referred_from:
                    n.referred_from.remove(node)
            node.refer_to = []
            for c in node.children:
                for n in node.children[c]:
                    self.clean_subtree_reference(n, mode = mode)
        if len(node.context_refer) > 0 and mode in ['all', 'context_refer']:
            for n in node.context_refer:
                if node in n.refer_to:
                    n.refer_to.remove(node)
            node.context_refer = []
            for c in node.children:
                for n in node.children[c]:
                    self.clean_subtree_reference(n, mode = mode)
        if len(node.self_refer) > 0 and mode in ['all', 'self_refer']:
            for n in node.self_refer:
                if node in n.self_refer:
                    n.self_refer.remove(node)
            node.self_refer = []
            for c in node.children:
                for n in node.children[c]:
                    self.clean_subtree_reference(n, mode = mode)

    def set_ori_nodes(self, new, old_list):
        if isinstance(new, TemplateTree):
            new_nodes = []
            for n in new.iter_nodes():
                new_nodes.append(n)
            for old in old_list:
                if not TemplateTree.compare(new, old):
                    new.draw('new', filerepo = 'figures')
                    old.draw('old', filerepo = 'figures')
                    raise ValueError('new tree and old tree must be identical.')
                old_nodes = []
                for n in old.iter_nodes():
                    old_nodes.append(n)
                for i, n in enumerate(new_nodes):
                    n.ori_nodes.append(old_nodes[i].get_id())
        elif isinstance(new, Context):
            new_nodes = []
            for n in new.context_tree.iter_nodes():
                new_nodes.append(n)
            for old in old_list:
                if not TemplateTree.compare(new.context_tree, old.context_tree):
                    new.context_tree.draw('new', filerepo = 'figures')
                    old.context_tree.draw('old', filerepo = 'figures')
                    raise ValueError('new tree and old tree must be identical.')
                old_nodes = []
                for n in old.context_tree.iter_nodes():
                    old_nodes.append(n)
                for i, n in enumerate(new_nodes):
                    n.ori_nodes.append(old_nodes[i].get_id())
            
        return new
        

    def set_ori_nodes_for_trees(self, new_list, old_list):
        new = []
        for i in range(0, len(new_list)):
            if new_list[i] != None:
                new.append(self.set_ori_nodes(new_list[i], old_list[i]))
            else:
                new.append(None)

        return new
        




    def abstract_values_for_nodes(self, a, b):
        if isinstance(a, TemplateNode) and isinstance(b, TemplateNode):
            if a.type == b.type:
                newnode = a.soft_copy()
                if a.type in ['Expr', 'End_Expr', 'Stmt']:
                    newnode.ori_nodes = [a.get_id(), b.get_id()] + a.ori_nodes + b.ori_nodes
                else:
                    newnode.ori_nodes = [a.get_id(), b.get_id()]
                if a.ctx != b.ctx:
                    newnode.ctx = None
                if a.value != b.value or a.value == 'REFERRED' or b.value == 'REFERRED':
                    newnode.value_abstracted = True
                    if a.base_type in ['Variable', 'Attribute', 'Type', 'Builtin', 'Keyword']:
                        newnode.ori_referred_from = a.referred_from + b.referred_from
                        newnode.ori_refer_to = a.refer_to + b.refer_to
                        newnode.ori_context_refer = a.context_refer + b.context_refer
                        newnode.ori_self_refer = a.self_refer + b.self_refer
                        newnode.value = 'ABSTRACTED'
                        if len(a.referred_from) > 0 and self.is_set_identical(a.referred_from, b.referred_from):
                            newnode.value = 'REFERRED'
                        else:
                            newnode.ori_referred_from = []
                            self.clean_reference(a, mode = 'referred_from')
                            self.clean_reference(b, mode = 'referred_from')
                        if len(a.refer_to) > 0 and self.is_set_identical(a.refer_to, b.refer_to):
                            newnode.value = 'REFERRED'
                        else:
                            newnode.ori_refer_to = []
                            self.clean_reference(a, mode = 'refer_to')
                            self.clean_reference(b, mode = 'refer_to')
                        if len(a.self_refer) > 0 and self.is_set_identical(a.self_refer, b.self_refer):
                            newnode.value = 'REFERRED'
                        else:
                            newnode.ori_self_refer = []
                            self.clean_reference(a, mode = 'self_refer')
                            self.clean_reference(b, mode = 'self_refer')
                        if newnode.value == 'REFERRED':
                            pass
                        else:
                            newnode.ori_context_refer = []
                            self.clean_reference(a, mode = 'context_refer')
                            self.clean_reference(b, mode = 'context_refer')
                    elif a.base_type == 'Reference':
                        newnode.ori_refer_to = a.refer_to + b.refer_to
                    elif a.base_type == 'Literal' and type(a.value) == type(b.value) and not ((a.value in ['ABSTRACTED', 'REFERRED'] and a.value_abstracted) or (b.value == ['ABSTRACTED', 'REFERRED'] and b.value_abstracted)):
                        newnode.ori_context_refer = a.context_refer + b.context_refer
                        newnode.value = type(a.value).__name__
                        self.clean_reference(a)
                        self.clean_reference(b)
                    elif a.base_type == 'Op' and a.value in op2cat and b.value in op2cat and op2cat[a.value] == op2cat[b.value]:
                        newnode.value = op2cat[a.value]
                        self.clean_reference(a)
                        self.clean_reference(b)
                    else:
                        newnode.value = 'ABSTRACTED'
                        self.clean_reference(a)
                        self.clean_reference(b)
                else:
                    newnode.value = a.value
                    if a.base_type in ['Variable', 'Attribute', 'Type', 'Builtin', 'Keyword']:
                        newnode.ori_referred_from = a.referred_from + b.referred_from
                        newnode.ori_refer_to = a.refer_to + b.refer_to
                        newnode.ori_context_refer = a.context_refer + b.context_refer
                        newnode.ori_self_refer = a.self_refer + b.self_refer
                        if not (len(a.referred_from) > 0 and self.is_set_identical(a.referred_from, b.referred_from)):
                            newnode.ori_referred_from = []
                            self.clean_reference(a, mode = 'referred_from')
                            self.clean_reference(b, mode = 'referred_from')
                        if not(len(a.refer_to) > 0 and self.is_set_identical(a.refer_to, b.refer_to)):
                            newnode.ori_refer_to = []
                            self.clean_reference(a, mode = 'refer_to')
                            self.clean_reference(b, mode = 'refer_to')
                        if not (len(a.context_refer) > 0 and self.is_set_identical(a.context_refer, b.context_refer)):
                            newnode.ori_context_refer = []
                            self.clean_reference(a, mode = 'context_refer')
                            self.clean_reference(b, mode = 'context_refer')
                        if not (len(a.self_refer) > 0 and self.is_set_identical(a.self_refer, b.self_refer)):
                            newnode.ori_self_refer = []
                            self.clean_reference(a, mode = 'self_refer')
                            self.clean_reference(b, mode = 'self_refer')
                    elif a.base_type == 'Reference':
                        newnode.ori_refer_to = a.refer_to + b.refer_to
                    elif a.base_type == 'Literal':
                        newnode.ori_context_refer = a.context_refer + b.context_refer
                    elif a.base_type in ['Stmt', 'Expr', 'End_Expr']:
                        newnode.ori_refer_to = a.refer_to + b.refer_to
                        newnode.ori_referred_from = a.referred_from + b.referred_from
                for c in a.children:
                    newnode.children[c] = []
                    for i, an in enumerate(a.children[c]):
                        child = self.abstract_values_for_nodes(a.children[c][i], b.children[c][i])
                        child.parent = newnode
                        child.parent_relation = c
                        newnode.children[c].append(child)
                return newnode
            elif TemplateNode.is_type_compatible(a, b):
                newnode = a.soft_copy()
                newnode.type_abstracted = True
                newnode.value_abstracted = True
                if a.type in ['Expr', 'End_Expr', 'Stmt'] or b.type in ['Expr', 'End_Expr', 'Stmt']:
                    newnode.ori_nodes = [a.get_id(), b.get_id()] + a.ori_nodes + b.ori_nodes
                else:
                    newnode.ori_nodes = [a.get_id(), b.get_id()]
                if a.ctx != b.ctx:
                    newnode.ctx = None
                newnode.type = 'Identifier'
                newnode.base_type = 'Identifier'
                newnode.value = 'ABSTRACTED'
                newnode.ori_referred_from = a.referred_from + b.referred_from
                newnode.ori_refer_to = a.refer_to + b.refer_to
                newnode.ori_context_refer = a.context_refer + b.context_refer
                newnode.ori_self_refer = a.self_refer + b.self_refer
                if len(a.referred_from) > 0 and self.is_set_identical(a.referred_from, b.referred_from):
                    newnode.value = 'REFERRED'
                else:
                    newnode.ori_referred_from = []
                    self.clean_reference(a, mode = 'referred_from')
                    self.clean_reference(b, mode = 'referred_from')
                if len(a.refer_to) > 0 and self.is_set_identical(a.refer_to, b.refer_to):
                    newnode.value = 'REFERRED'
                else:
                    newnode.ori_refer_to = []
                    self.clean_reference(a, mode = 'refer_to')
                    self.clean_reference(b, mode = 'refer_to')
                if len(a.self_refer) > 0 and self.is_set_identical(a.self_refer, b.self_refer):
                    newnode.value = 'REFERRED'
                else:
                    newnode.ori_self_refer = []
                    self.clean_reference(a, mode = 'self_refer')
                    self.clean_reference(b, mode = 'self_refer')
                if newnode.value == 'REFERRED':
                    pass
                else:
                    newnode.ori_context_refer = []
                    self.clean_reference(a, mode = 'context_refer')
                    self.clean_reference(b, mode = 'context_refer')
                for c in a.children:
                    newnode.children[c] = []
                    for i, an in enumerate(a.children[c]):
                        child = self.abstract_values_for_nodes(a.children[c][i], b.children[c][i])
                        child.parent = newnode
                        child.parent_relation = c
                        newnode.children[c].append(child)
                return newnode
            else:
                raise ValueError('Cannot abstract the values of two nodes with different types.')
        else:
            raise ValueError('Inputs must be two TemplateNode objects.')
            

    def abstract_values_for_trees(self, a, b):
        if isinstance(a, TemplateTree) and isinstance(b, TemplateTree):
            newtree = TemplateTree()
            newtree.root = self.abstract_values_for_nodes(a.root, b.root)
            newtree.collect_special_nodes()
            return newtree
        elif a == None and b == None:
            return None
        else:
            raise ValueError('Cannot abstract the values of two structurally non-identical trees.')

    def abstract_structures_for_contexts(self, a, b, pair):
        if isinstance(a, TemplateTree) and isinstance(b, TemplateTree):
            newtree = TemplateTree()
            a_leaf_nodes = a.get_leaf_nodes()
            b_leaf_nodes = b.get_leaf_nodes()
            if len(pair) == 0:
                return None
            elif len(pair) > min(len(a_leaf_nodes), len(b_leaf_nodes)):
                print(pair)
                print(a_leaf_nodes)
                print(b_leaf_nodes)
                a.draw('a', filerepo = 'figures')
                b.draw('b', filerepo = 'figures')
                raise ValueError('The length of leaf node pair should be smaller than the length of leaf node lists in one tree.')
            a_nodes = []
            b_nodes = []
            node_map = {}
            a_highest_nodes = []
            b_highest_nodes = []
            for p in pair:
                a_node = p[0]
                a_leaf_path = [a_node]
                if a_node not in a_nodes:
                    a_nodes.append(a_node)
                for i in range(1, p[2]):
                    a_node = a_node.parent
                    if a_node not in a_nodes:
                        a_nodes.append(a_node)
                    a_leaf_path.append(a_node)
                a_highest_nodes.append(a_leaf_path[-1])
                b_node = p[1]
                b_leaf_path = [b_node]
                if b_node not in b_nodes:
                    b_nodes.append(b_node)
                for i in range(1, p[2]):
                    b_node = b_node.parent
                    if b_node not in b_nodes:
                        b_nodes.append(b_node)
                    b_leaf_path.append(b_node)
                b_highest_nodes.append(b_leaf_path[-1])
                if len(a_leaf_path) != len(b_leaf_path):
                    raise ValueError(f'Inconsistent length of leaf paths: {len(a_leaf_path)} and {len(b_leaf_path)}.')
                for i in range(0, len(a_leaf_path)):
                    node_map[a_leaf_path[i]] = b_leaf_path[i]
            
            node_map[a.root] = b.root
            #old_a = deepcopy(a)
            #old_b = deepcopy(b)
            
            # Remove the nodes that do not appear in pair
            a_removed_nodes = []
            b_removed_nodes = []
            for n in a.iter_nodes():
                if n not in a_nodes and n.base_type != 'Root':
                    a_removed_nodes.append(n)
            for n in b.iter_nodes():
                if n not in b_nodes and n.base_type != 'Root':
                    b_removed_nodes.append(n)
            
            for n in a_removed_nodes:
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
                        nn.parent = n.parent
                        if n.parent.base_type == 'Root':
                            nn.parent_relation = 'body'
            
            for n in b_removed_nodes:
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
                        nn.parent = n.parent
                        if n.parent.base_type == 'Root':
                            nn.parent_relation = 'body'
            for n in a_highest_nodes:
                if n.parent.base_type != 'Root':
                    n.parent.children[n.parent_relation].remove(n)
                    n.parent = a.root
                    n.parent_relation = 'body'
                    a.root.children['body'].append(n)
            for n in b_highest_nodes:
                if n.parent.base_type != 'Root':
                    n.parent.children[n.parent_relation].remove(n)
                    n.parent = b.root
                    n.parent_relation = 'body'
                    b.root.children['body'].append(n)

            a.remove_empty_children()
            b.remove_empty_children()

            if a.get_node_num() != b.get_node_num():
                #old_a.draw('old_a', filerepo = 'figures')
                #old_b.draw('old_b', filerepo = 'figures')
                a.draw('a', filerepo = 'figures')
                b.draw('b', filerepo = 'figures')
                raise ValueError('Inconsistent node number of two trees before alignment.')
            
            # Align two trees
            new_body = []
            for n in a.root.children['body']:
                for bn in b.root.children['body']:
                    if bn in new_body:
                        continue
                    if TemplateNode.value_abstract_compare(n, bn):
                        new_body.append(bn)
                        break
            b.root.children['body'] = new_body


            if not TemplateNode.value_abstract_compare(a.root, b.root):
                a.draw('a', filerepo = 'figures')
                b.draw('b', filerepo = 'figures')
                raise ValueError('Align failed!')
            
            newtree.root = self.abstract_values_for_nodes(a.root, b.root)
            newtree.collect_special_nodes()
            return newtree
        elif a == None and b == None:
            return None
        else:
            raise ValueError('Input a and b must be TemplateTree objects.')

    def abstract_structures_for_nodes(self, a, b):
        if isinstance(a, TemplateNode) and isinstance(b, TemplateNode):
            if a.type == b.type:
                removed = []
                for c in a.children:
                    if c not in b.children:
                        removed.append(c)
                    else:
                        new_a_children = []
                        new_b_children = []
                        max_len = min(len(a.children[c]), len(b.children[c]))
                        for index, n in enumerate(a.children[c]):
                            if index < len(b.children[c]):
                                new_a, new_b = self.abstract_structures_for_nodes(n, b.children[c][index])
                                new_a_children.append(new_a)
                                new_b_children.append(new_b)
                        a.children[c] = new_a_children
                        b.children[c] = new_b_children
                for c in removed:
                    del a.children[c]
                removed = []
                for c in b.children:
                    if c not in a.children:
                        removed.append(c)
                for c in removed:
                    del b.children[c]
                return a, b
            else:
                if (a.base_type == b.base_type and a.base_type in ['Expr']):
                    new_a = TemplateNode('Expr', t = 'Expr')
                    new_a.ori_nodes = [a.get_id(), b.get_id()]
                    new_a.referred_from = a.referred_from
                    new_a.refer_to = a.refer_to
                    new_b = TemplateNode('Expr', t = 'Expr')
                    new_b.ori_nodes = [a.get_id(), b.get_id()]
                    new_b.referred_from = b.referred_from
                    new_b.refer_to = b.refer_to
                    new_a.type_abstracted = True
                    new_a.value_abstracted = True
                    new_b.type_abstracted = True
                    new_b.value_abstracted = True
                    return new_a, new_b
                elif (a.base_type == b.base_type and a.base_type in ['End_Expr']):
                    new_a = TemplateNode('Expr', t = 'Expr')
                    new_a.ori_nodes = [a.get_id(), b.get_id()]
                    new_a.referred_from = a.referred_from
                    new_a.refer_to = a.refer_to
                    new_b = TemplateNode('Expr', t = 'Expr')
                    new_b.ori_nodes = [a.get_id(), b.get_id()]
                    new_b.referred_from = b.referred_from
                    new_b.refer_to = b.refer_to
                    new_a.type_abstracted = True
                    new_a.value_abstracted = True
                    new_b.type_abstracted = True
                    new_b.value_abstracted = True
                    return new_a, new_b
                elif a.base_type != b.base_type and a.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Identifier'] and b.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Identifier']:
                    new_a = TemplateNode('End_Expr', t = 'End_Expr')
                    new_a.ori_nodes = [a.get_id(), b.get_id()]
                    new_a.referred_from = a.referred_from
                    new_a.refer_to = a.refer_to
                    new_b = TemplateNode('End_Expr', t = 'End_Expr')
                    new_b.ori_nodes = [a.get_id(), b.get_id()]
                    new_b.referred_from = b.referred_from
                    new_b.refer_to = b.refer_to
                    new_a.type_abstracted = True
                    new_a.value_abstracted = True
                    new_b.type_abstracted = True
                    new_b.value_abstracted = True
                    return new_a, new_b
                elif a.base_type != b.base_type and a.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Expr', 'End_Expr', 'Identifier'] and b.base_type in ['Variable', 'Literal', 'Attribute', 'Op', 'Builtin', 'Type', 'Module', 'Keyword', 'Expr', 'End_Expr', 'Identifier']:
                    new_a = TemplateNode('Expr', t = 'Expr')
                    new_a.ori_nodes = [a.get_id(), b.get_id()]
                    new_a.referred_from = a.referred_from
                    new_a.refer_to = a.refer_to
                    new_b = TemplateNode('Expr', t = 'Expr')
                    new_b.ori_nodes = [a.get_id(), b.get_id()]
                    new_b.referred_from = b.referred_from
                    new_b.refer_to = b.refer_to
                    new_a.type_abstracted = True
                    new_a.value_abstracted = True
                    new_b.type_abstracted = True
                    new_b.value_abstracted = True
                    return new_a, new_b
                else:
                    new_a = TemplateNode('Stmt', t = 'Stmt')
                    new_a.ori_nodes = [a.get_id(), b.get_id()]
                    new_a.referred_from = a.referred_from
                    new_a.refer_to = a.refer_to
                    new_b = TemplateNode('Stmt', t = 'Stmt')
                    new_b.ori_nodes = [a.get_id(), b.get_id()]
                    new_b.referred_from = b.referred_from
                    new_b.refer_to = b.refer_to
                    new_a.type_abstracted = True
                    new_a.value_abstracted = True
                    new_b.type_abstracted = True
                    new_b.value_abstracted = True
                    return new_a, new_b
        else:
            ValueError('Input a and b must be TemplateNode objects.')

    def abstract_structures_for_patterns(self, a, b):
        if isinstance(a, TemplateTree) and isinstance(b, TemplateTree):
            newtree = TemplateTree()
            new_a_root, new_b_root = self.abstract_structures_for_nodes(a.root, b.root)
            newtree.root = self.abstract_values_for_nodes(new_a_root, new_b_root)
            newtree.collect_special_nodes()
            return newtree
        elif a == None and b == None:
            return None
        else:
            raise ValueError('Input a and b must be TemplateTree objects.')

    def merge_external_contexts(self, distances, pairs, clusters, templates):
        new_templates = []
        merged = {}
        skipped = []
        for i in range(0, len(clusters)):
            merged[i] = 0
        # Step 1: Merge structurally identical trees
        for index, cluster in enumerate(clusters):
            candidates = []
            max_distance = -9999
            for i, t in enumerate(cluster):
                for j in range(i + 1, len(cluster)):
                    if distances['structural']['external'][t][cluster[j]] == 1.0 and distances['accurate']['external'][t][cluster[j]] > max_distance:
                        candidates = [t, cluster[j]]
                        max_distance = distances['accurate']['external'][t][cluster[j]]
            if len(candidates) > 0:
                logger.debug('Merging structurally identical trees.')
                try:
                    merged[index] = 1
                    template = FixTemplate(candidates[0].action, deepcopy(candidates[0].before), deepcopy(candidates[0].after))
                    template.id = self.index
                    self.index += 1
                    template.within_context = deepcopy(candidates[0].within_context)
                    template.before, template.after, template.within_context = self.set_ori_nodes_for_trees([template.before, template.after, template.within_context], [[candidates[0].before, candidates[1].before], [candidates[0].after, candidates[1].after], [candidates[0].within_context, candidates[1].within_context]])
                    if candidates[0].before_contexts == None or candidates[1].before_contexts == None:
                        template.before_contexts = None
                    else:
                        template.before_contexts = Context(self.abstract_values_for_trees(candidates[0].before_contexts.context_tree, candidates[1].before_contexts.context_tree), None, 'Before')
                    if candidates[0].after_contexts == None or candidates[1].after_contexts == None:
                        template.after_contexts = None
                    else:
                        template.after_contexts = Context(self.abstract_values_for_trees(candidates[0].after_contexts.context_tree, candidates[1].after_contexts.context_tree), None, 'After')
                    template.set_node_ids()
                    template.recover_reference()
                    template.set_treetype()
                    self.fixed_id2template = template.merge(candidates, self.fixed_id2template)
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    new_templates.append(template)
                except Exception as e:
                    logger.warning('Error occurred when merging external contexts, skipped.')
                    skipped += candidates

        
        # Step 2: Merge structurally non-identical trees
        for index, cluster in enumerate(clusters):
            if merged[index] == 1:
                continue
            candidates = []
            max_distance = -9999
            for i, t in enumerate(cluster):
                for j in range(i + 1, len(cluster)):
                    if distances['accurate']['external'][t][cluster[j]] > max_distance:
                        candidates = [t, cluster[j]]
                        max_distance = distances['accurate']['external'][t][cluster[j]]
            if len(candidates) > 0:
                logger.debug('Merging structurally non-identical trees.')
                try:
                    merged[index] = 1
                    template = FixTemplate(candidates[0].action, deepcopy(candidates[0].before), deepcopy(candidates[0].after))
                    template.id = self.index
                    self.index += 1
                    template.within_context = deepcopy(candidates[0].within_context)
                    template.before, template.after, template.within_context = self.set_ori_nodes_for_trees([template.before, template.after, template.within_context], [[candidates[0].before, candidates[1].before], [candidates[0].after, candidates[1].after], [candidates[0].within_context, candidates[1].within_context]])
                    if candidates[0].before_contexts == None or candidates[1].before_contexts == None:
                        template.before_contexts = None
                    else:
                        context_tree = self.abstract_structures_for_contexts(candidates[0].before_contexts.context_tree, candidates[1].before_contexts.context_tree, pairs['structural']['before'][candidates[0]][candidates[1]])
                        if context_tree:
                            template.before_contexts = Context(context_tree, None, 'Before')
                        else:
                            template.before_contexts = None
                    if candidates[0].after_contexts == None or candidates[1].after_contexts == None:
                        template.after_contexts = None
                    else:
                        context_tree = self.abstract_structures_for_contexts(candidates[0].after_contexts.context_tree, candidates[1].after_contexts.context_tree, pairs['structural']['after'][candidates[0]][candidates[1]])
                        if context_tree:
                            template.after_contexts = Context(context_tree, None, 'After')
                        else:
                            template.after_contexts = None
                    template.set_node_ids()
                    template.recover_reference()
                    template.set_treetype()
                    self.fixed_id2template = template.merge(candidates, self.fixed_id2template)
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    new_templates.append(template)
                except Exception as e:
                    logger.warning('Error occurred when merging external contexts, skipped.')
                    skipped += candidates
        
        # Register new templates, remove old templates
        old_templates = []
        for t in new_templates:
            for tt in t.child_templates:
                templates.remove(self.id2template[tt])
                old_templates.append(str(tt))
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)
            templates.append(t)
        
        for t in skipped:
            if t in templates:
                templates.remove(t)

        logger.debug('Removing templates {}, adding templates {}'.format(','.join(old_templates), ','.join([str(t.id) for t in new_templates])))

        return distances, pairs, templates

    def abstract_within_contexts(self, distances, pairs, clusters, templates):
        new_templates = []
        abstracted = {}
        skipped = []
        for i in range(0, len(clusters)):
            abstracted[i] = 0
        # Step 1: Abstract structurally identical trees
        for index, cluster in enumerate(clusters):
            candidates = []
            max_distance = -9999
            for i, t in enumerate(cluster):
                for j in range(i + 1, len(cluster)):
                    if distances['structural']['within'][t][cluster[j]] == 1.0 and distances['accurate']['within'][t][cluster[j]] > max_distance:
                        candidates = [t, cluster[j]]
                        max_distance = distances['accurate']['within'][t][cluster[j]]
            if len(candidates) > 0:
                abstracted[index] = 1
                logger.debug('Abstracting structurally identical trees.')
                try:
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, deepcopy(candidates[i].before), deepcopy(candidates[i].after))
                        template.id = self.index
                        logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                        self.index += 1
                        try:
                            template.within_context = Context(self.abstract_values_for_trees(candidates[0].within_context.context_tree, candidates[1].within_context.context_tree), candidates[i].within_context.relationship, 'Within')
                        except:
                            candidates[0].within_context.context_tree.draw('a', filerepo = 'figures')
                            candidates[1].within_context.context_tree.draw('b', filerepo = 'figures')
                            exit()
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.before, template.after, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.before, template.after, template.before_contexts, template.after_contexts], [[candidates[i].before], [candidates[i].after], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                        template.recover_reference()
                        template.set_treetype()
                        template.set_node_ids()
                        
                        self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                        
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
                except Exception as e:
                    logger.warning('Error occurred when merging internal contexts, skipped.')
                    skipped += candidates
        
        # Step 2: Abstract structurally non-identical trees
        for index, cluster in enumerate(clusters):
            if abstracted[index] == 1:
                continue
            candidates = []
            max_distance = -9999
            for i, t in enumerate(cluster):
                for j in range(i + 1, len(cluster)):
                    if distances['accurate']['within'][t][cluster[j]] > max_distance:
                        candidates = [t, cluster[j]]
                        max_distance = distances['accurate']['within'][t][cluster[j]]
            if len(candidates) > 0:
                logger.debug('Abstracting structurally non-identical trees.')
                abstracted[index] = 1
                try:
                    context_tree = self.abstract_structures_for_contexts(candidates[0].within_context.context_tree, candidates[1].within_context.context_tree, pairs['structural']['within'][candidates[0]][candidates[1]])
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, deepcopy(candidates[i].before), deepcopy(candidates[i].after))
                        template.id = self.index
                        logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                        self.index += 1
                        template.within_context = Context(deepcopy(context_tree), candidates[i].within_context.relationship, 'Within')
                        if template.within_context.context_tree == None:
                            candidates[0].within_context.context_tree.draw('a', filerepo = 'figures')
                            candidates[1].within_context.context_tree.draw('b', filerepo = 'figures')
                            raise ValueError('The context tree of within context cannot be None.')
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.before, template.after, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.before, template.after, template.before_contexts, template.after_contexts], [[candidates[i].before], [candidates[i].after], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                        template.set_treetype()
                        template.set_node_ids()
                        template.recover_reference()
                        self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
                except Exception as e:
                    logger.warning('Error occurred when abstracting internal contexts, skipped.')
                    skipped += candidates
        
        # Register new templates, remove old templates
        old_templates = []
        for t in new_templates:
            for tt in t.child_templates:
                templates.remove(self.id2template[tt])
                old_templates.append(str(tt))
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)
            templates.append(t)
        
        for t in skipped:
            if t in templates:
                templates.remove(t)
        
        logger.debug('Removing templates {}, adding templates {}'.format(','.join(old_templates), ','.join([str(t.id) for t in new_templates])))

        return distances, pairs, templates

    def abstract_patterns(self, distances, pairs, templates, clusters = None, extra = False):
        new_templates = []
        changed = False
        skipped = []
        # Step 1: Abstract structurally identical trees
        if clusters:
            for index, cluster in enumerate(clusters):
                candidates = []
                max_distance = -9999
                for i, t in enumerate(cluster):
                    for j in range(i + 1, len(cluster)):
                        if distances['accurate']['pattern'][t][cluster[j]] > max_distance:
                            candidates = [t, cluster[j]]
                            max_distance = distances['accurate']['pattern'][t][cluster[j]]
                if len(candidates) > 0:
                    logger.debug('Abstracting structurally identical trees.')
                    try:
                        for i in range(0, len(candidates)):
                            template = FixTemplate(candidates[i].action, self.abstract_values_for_trees(candidates[0].before, candidates[1].before), self.abstract_values_for_trees(candidates[0].after, candidates[1].after))
                            template.id = self.index
                            logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                            self.index += 1
                            if not extra:
                                template.within_context = deepcopy(candidates[i].within_context)
                            else:
                                template.within_context = None
                            template.before_contexts = deepcopy(candidates[i].before_contexts)
                            template.after_contexts = deepcopy(candidates[i].after_contexts)
                            template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.within_context, template.before_contexts, template.after_contexts], [[candidates[i].within_context], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                            template.set_treetype()
                            template.set_node_ids()
                            template.recover_reference()
                            self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                            self.id2template[template.id] = template
                            self.fixed_id2template[template.id] = deepcopy(template)
                            new_templates.append(template)
                            changed = True
                    except Exception as e:
                        logger.warning('Error occurred when abstracting patterns, skipped.')
                        skipped += candidates
                        changed = True
                else:
                    raise ValueError('Less than two templates in the cluster.')
        # Step 2: Abstract structurally non-identical trees
        else:
            a, b, max_d = self.get_max_distance(distances['accurate']['pattern'], distances['accurate']['within'], templates, validate = not extra)
            if max_d == -9999:
                changed = False
                return changed, distances, pairs, templates
            else:
                logger.debug('Abstracting structurally non-identical trees.')
                candidates = [a, b]
                try:
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, self.abstract_structures_for_patterns(candidates[0].before, candidates[1].before), self.abstract_structures_for_patterns(candidates[0].after, candidates[1].after))
                        template.id = self.index
                        logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                        self.index += 1
                        if not extra:
                            template.within_context = deepcopy(candidates[i].within_context)
                        else:
                            template.within_context = None
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.within_context, template.before_contexts, template.after_contexts], [[candidates[i].within_context], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                        template.set_treetype()
                        template.set_node_ids()
                        template.recover_reference()
                        self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
                        changed = True
                except Exception as e:
                    logger.warning('Error occurred when abstracting patterns, skipped.')
                    skipped += candidates
                    changed = True
    
        # Register new templates, remove old templates
        old_templates = []
        for t in new_templates:
            for tt in t.child_templates:
                templates.remove(self.id2template[tt])
                old_templates.append(str(tt))
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)
            templates.append(t)
        for t in skipped:
            if t in templates:
                templates.remove(t)
        if len(new_templates) == 2 and distances["accurate"]["pattern"][new_templates[0]][new_templates[1]] != 1.0:
            templates.remove(new_templates[0])
            templates.remove(new_templates[1])
            logger.warning('Failed to abstract the pattern, skipped.')
        logger.debug('Removing templates {}, adding templates {}'.format(','.join(old_templates), ','.join([str(t.id) for t in new_templates])))

        return changed, distances, pairs, templates

    def abstract_insert_patterns(self, distances, pairs, templates, clusters = None, extra = False, mode = 'before'):
        new_templates = []
        changed = False
        if mode == 'before':
            abstracted = {}
            for i in range(0, len(clusters)):
                abstracted[i] = 0
            # Step 1: Abstract structurally identical trees
            for index, cluster in enumerate(clusters):
                candidates = []
                max_distance = -9999
                for i, t in enumerate(cluster):
                    for j in range(i + 1, len(cluster)):
                        if distances['structural']['before_pattern'][t][cluster[j]] == 1.0 and distances['accurate']['before_pattern'][t][cluster[j]] > max_distance and distances['accurate']['after_pattern'][t][cluster[j]] == 1.0 and distances['accurate']['within'][t][cluster[j]] != -9999:
                            candidates = [t, cluster[j]]
                            max_distance = distances['accurate']['before_pattern'][t][cluster[j]]
                if len(candidates) > 0:
                    changed = True
                    abstracted[index] = 1
                    logger.debug('Abstracting structurally identical trees.')
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, self.abstract_values_for_trees(candidates[0].before, candidates[1].before), deepcopy(candidates[i].after))
                        template.id = self.index
                        logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                        self.index += 1
                        template.within_context = deepcopy(candidates[i].within_context)
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.after, template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.after, template.within_context, template.before_contexts, template.after_contexts], [[candidates[i].after], [candidates[i].within_context], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                        template.recover_reference()
                        template.set_treetype()
                        template.set_node_ids()
                        self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
            
            # Step 2: Abstract structurally non-identical trees
            for index, cluster in enumerate(clusters):
                if abstracted[index] == 1:
                    continue
                candidates = []
                max_distance = -9999
                for i, t in enumerate(cluster):
                    for j in range(i + 1, len(cluster)):
                        if distances['accurate']['before_pattern'][t][cluster[j]] > max_distance and distances['accurate']['after_pattern'][t][cluster[j]] == 1.0  and distances['accurate']['within'][t][cluster[j]] != -9999:
                            candidates = [t, cluster[j]]
                            max_distance = distances['accurate']['before_pattern'][t][cluster[j]]
                if len(candidates) > 0:
                    changed = True
                    abstracted[index] = 1
                    logger.debug('Abstracting structurally non-identical trees.')
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, self.abstract_structures_for_patterns(candidates[0].before, candidates[1].before), deepcopy(candidates[i].after))
                        template.id = self.index
                        logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                        self.index += 1
                        template.within_context = deepcopy(candidates[i].within_context)
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.after, template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.after, template.within_context, template.before_contexts, template.after_contexts], [[candidates[i].after], [candidates[i].within_context], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                        template.recover_reference()
                        template.set_treetype()
                        template.set_node_ids()
                        self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
        else:
            # Step 1: Abstract structurally identical trees
            if clusters:
                for index, cluster in enumerate(clusters):
                    candidates = []
                    max_distance = -9999
                    for i, t in enumerate(cluster):
                        for j in range(i + 1, len(cluster)):
                            if distances['accurate']['after_pattern'][t][cluster[j]] > max_distance and distances['accurate']['before_pattern'][t][cluster[j]] != -9999:
                                candidates = [t, cluster[j]]
                                max_distance = distances['accurate']['after_pattern'][t][cluster[j]]
                    if len(candidates) > 0:
                        logger.debug('Abstracting structurally identical trees.')
                        for i in range(0, len(candidates)):
                            template = FixTemplate(candidates[i].action, deepcopy(candidates[i].before), self.abstract_values_for_trees(candidates[0].after, candidates[1].after))
                            template.id = self.index
                            logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                            self.index += 1
                            if not extra:
                                template.within_context = deepcopy(candidates[i].within_context)
                            else:
                                template.within_context = None
                            template.before_contexts = deepcopy(candidates[i].before_contexts)
                            template.after_contexts = deepcopy(candidates[i].after_contexts)
                            template.before, template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.before, template.within_context, template.before_contexts, template.after_contexts], [[candidates[i].before], [candidates[i].within_context], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                            template.set_treetype()
                            template.set_node_ids()
                            template.recover_reference()
                            self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                            self.id2template[template.id] = template
                            self.fixed_id2template[template.id] = deepcopy(template)
                            new_templates.append(template)
                            changed = True
                    else:
                        raise ValueError('Less than two templates in the cluster.')
            # Step 2: Abstract structurally non-identical trees
            else:
                if not extra:
                    a, b, max_d = self.get_max_distance(distances['accurate']['after_pattern'], distances['accurate']['before_pattern'], templates, extra_distances = distances['accurate']['within'])
                else:
                    a, b, max_d = self.get_max_distance(distances['accurate']['after_pattern'], distances['accurate']['before_pattern'], templates)
                if max_d == -9999:
                    changed = False
                    return changed, distances, pairs, templates
                else:
                    logger.debug('Abstracting structurally non-identical trees.')
                    candidates = [a, b]
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, deepcopy(candidates[i].before), self.abstract_structures_for_patterns(candidates[0].after, candidates[1].after))
                        template.id = self.index
                        logger.debug('Template {} -> Template {}.'.format(candidates[i].id, template.id))
                        self.index += 1
                        if not extra:
                            template.within_context = deepcopy(candidates[i].within_context)
                        else:
                            template.within_context = None
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.before, template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.before, template.within_context, template.before_contexts, template.after_contexts], [[candidates[i].before], [candidates[i].within_context], [candidates[i].before_contexts], [candidates[i].after_contexts]])
                        template.set_treetype()
                        template.set_node_ids()
                        template.recover_reference()
                        self.fixed_id2template = template.merge([candidates[i]], self.fixed_id2template)
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
                        changed = True

        # Register new templates, remove old templates
        old_templates = []
        for t in new_templates:
            for tt in t.child_templates:
                templates.remove(self.id2template[tt])
                old_templates.append(str(tt))
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)
            templates.append(t)
        #logger.debug("{}".format([(k, distances["accurate"][k][new_templates[0]][new_templates[1]]) for k in distances["accurate"]]))
        if len(new_templates) == 2 and mode == 'before' and distances["accurate"]["before_pattern"][new_templates[0]][new_templates[1]] != 1.0:
            templates.remove(new_templates[0])
            templates.remove(new_templates[1])
            logger.warning('Failed to abstract the before tree, skipped.')
        elif len(new_templates) == 2 and mode == 'after' and distances["accurate"]["after_pattern"][new_templates[0]][new_templates[1]] != 1.0:
            templates.remove(new_templates[0])
            templates.remove(new_templates[1])
            logger.warning('Failed to abstract the after tree, skipped.')
        logger.debug('Removing templates {}, adding templates {}'.format(','.join(old_templates), ','.join([str(t.id) for t in new_templates])))

        return changed, distances, pairs, templates
                

    def compress_templates(self, templates):
        changed = True
        while(changed):
            changed = False
            for t in templates:
                if len(t.child_templates) == 0:
                    continue
                same = []
                for it in t.child_templates:
                    if FixTemplate.compare(t, self.fixed_id2template[it]):
                        same.append(it)
                if len(same) > 0:
                    changed = True
                    old_children = t.child_templates
                    t.child_templates = []
                    self.fixed_id2template[t.id].child_templates = []
                    for it in old_children:
                        if it not in same:
                            if it not in self.fixed_id2template[t.id].child_templates:
                                self.fixed_id2template[t.id].child_templates.append(it)
                            if it not in t.child_templates:
                                t.child_templates.append(it)
                        else:
                            for iit in self.fixed_id2template[it].child_templates:
                                self.fixed_id2template[iit].parent_template = t.id
                                if iit not in self.fixed_id2template[t.id].child_templates:
                                    self.fixed_id2template[t.id].child_templates.append(iit)
                                if iit not in t.child_templates:
                                    t.child_templates.append(iit)
        child_templates = []
        for t in templates:
            child_templates += t.child_templates
        child_templates = [self.fixed_id2template[t] for t in child_templates]
        if len(child_templates) > 0:
            self.compress_templates(child_templates)
        return templates

    def remove_single_templates(self, templates):
        new_templates = []
        for t in templates:
            if len(t.instances) > 1:
                child_templates = [self.fixed_id2template[i] for i in t.child_templates]
                child_templates = self.remove_single_templates(child_templates)
                t.child_templates = [k.id for k in child_templates]
                self.fixed_id2template[t.id].child_templates = [k.id for k in child_templates]
                new_templates.append(t)
        
        return templates




    def mining_insert(self, distances, pairs, templates):
        changed = False

        # Step 1: Fix after tree, clustering and abstracting before tree, change reference in after tree accordingly, return immediately if any change happens
        clusters = []
        selected = {}
        inner_changed = False
        for t in templates:
            selected[t] = 0
        for i, t in enumerate(templates):
            cluster = []
            if selected[t] == 1:
                continue
            for j in range(i + 1, len(templates)):
                if selected[templates[j]] == 1:
                    continue
                if distances['accurate']['after_pattern'][t][templates[j]] == 1.0 and distances['accurate']['before_pattern'][t][templates[j]] != -9999 and distances['accurate']['within'][t][templates[j]] != -9999:
                    #logger.debug("{}".format([(k, distances["accurate"][k][t][templates[j]]) for k in distances["accurate"]]))
                    cluster.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        if len(clusters) > 0:
            logger.debug(f'Entered Step 4-2-1 - Before Tree Abstraction, {len(clusters)} clusters will be abstracted.')
            changed = True
            ori_num = len(self.fixed_id2template)
            inner_changed, distances, pairs, templates = self.abstract_insert_patterns(distances, pairs, templates, clusters = clusters, mode = 'before')
            cur_num = len(self.fixed_id2template)
            logger.debug(f'Completed Step 4-2-1 - Before Tree Abstraction, {cur_num - ori_num} templates are abstracted.')
        if inner_changed:
            return changed, distances, pairs, templates

        # Step 2: Clustering and abstracting after tree, return immediately if any change happens
        clusters = []
        selected = {}
        inner_changed = False
        for t in templates:
            selected[t] = 0
        for i, t in enumerate(templates):
            cluster = []
            if selected[t] == 1:
                continue
            for j in range(i + 1, len(templates)):
                if selected[templates[j]] == 1:
                    continue
                if distances['structural']['after_pattern'][t][templates[j]] == 1.0 and distances['accurate']['before_pattern'][t][templates[j]] != -9999 and distances['accurate']['within'][t][templates[j]] != -9999:
                    cluster.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        ori_num = len(self.fixed_id2template)
        if len(clusters) > 0:
            logger.debug(f'Entered Step 4-2-2 - After Tree Abstraction, {len(clusters)} clusters will be abstracted.')
            inner_changed, distances, pairs, templates = self.abstract_insert_patterns(distances, pairs, templates, clusters = clusters, mode = 'after', extra = False)
        else:
            logger.debug('Entered Step 4-2-2 - After Tree Abstraction, no cluster found, will choose two mergeable templates.')
            inner_changed, distances, pairs, templates = self.abstract_insert_patterns(distances, pairs, templates, mode = 'after', extra = False)
        cur_num = len(self.fixed_id2template)
        if inner_changed:
            changed = True
            logger.debug(f'Completed Step 4-2-2 - After Tree Abstraction, {cur_num - ori_num} templates are abstracted.')
        else:
            logger.debug(f'Completed Step 4-2-2 - After Tree Abstraction, no template is abstracted.')
        
        if inner_changed:
            return changed, distances, pairs, templates

        # Step 3: Clustering and abstracting after tree for non-mergable within context, set within context to None, return immediately if any change happens
        clusters = []
        selected = {}
        inner_changed = False
        for t in templates:
            selected[t] = 0
        for i, t in enumerate(templates):
            cluster = []
            if selected[t] == 1:
                continue
            for j in range(i + 1, len(templates)):
                if selected[templates[j]] == 1:
                    continue
                if distances['structural']['after_pattern'][t][templates[j]] == 1.0 and distances['accurate']['before_pattern'][t][templates[j]] != -9999 and distances['accurate']['within'][t][templates[j]] == -9999:
                    cluster.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        ori_num = len(self.fixed_id2template)
        if len(clusters) > 0:
            logger.debug(f'Entered Step 4-2-3 - After Tree Abstraction Regardless of Within Context, {len(clusters)} clusters will be abstracted.')
            inner_changed, distances, pairs, templates = self.abstract_insert_patterns(distances, pairs, templates, clusters = clusters, mode = 'after', extra = True)
        else:
            logger.debug('Entered Step 4-2-3 - After Tree Abstraction Regardless of Within Context, no cluster found, will choose two mergeable templates.')
            inner_changed, distances, pairs, templates = self.abstract_insert_patterns(distances, pairs, templates, mode = 'after', extra = True)
        cur_num = len(self.fixed_id2template)
        if inner_changed:
            changed = True
            logger.debug(f'Completed Step 4-2-3 - After Tree Abstraction Regardless of Within Context, {cur_num - ori_num} templates are abstracted.')
        else:
            logger.debug(f'Completed Step 4-2-3 - After Tree Abstraction Regardless of Within Context, no template is abstracted.')
        
        return changed, distances, pairs, templates


    def mining(self, distances, pairs, templates):
        changed = False

        # Step 1: Merge same tamplates
        inner_changed = True
        ori_num = len(templates)
        while(inner_changed):
            inner_changed = False
            new_templates = []
            for i, t in enumerate(templates):
                same = []
                for j in range(i + 1, len(templates)):
                    if distances['accurate']['pattern'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] == 1.0 and distances['accurate']['external'][t][templates[j]] == 1.0:
                        same.append(templates[j])
                if len(same) > 0:
                    template = FixTemplate(t.action, deepcopy(t.before), deepcopy(t.after))
                    template.id = self.index
                    self.index += 1
                    template.within_context = deepcopy(t.within_context)
                    template.before_contexts = deepcopy(t.before_contexts)
                    template.after_contexts = deepcopy(t.after_contexts)
                    template.before, template.after, template.within_context, template.before_contexts, template.after_contexts = self.set_ori_nodes_for_trees([template.before, template.after, template.within_context, template.before_contexts, template.after_contexts], [[temp.before for temp in same + [t]], [temp.after for temp in same + [t]], [temp.within_context for temp in same + [t]], [temp.before_contexts for temp in same + [t]], [temp.after_contexts for temp in same + [t]]])
                    template.set_treetype()
                    template.set_node_ids()
                    template.recover_reference()
                    self.fixed_id2template = template.merge([k for k in same + [t]], self.fixed_id2template)
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    new_templates.append(template)
                    inner_changed = True
                    break
            old_templates = []
            for t in new_templates:
                for tt in t.child_templates:
                    templates.remove(self.id2template[tt])
                    old_templates.append(str(tt))
            for t in new_templates:
                distances, pairs = self.add_distances(distances, pairs, t, templates)
                templates.append(t)
            if inner_changed:
                changed = True
        if changed:
            cur_num = len(templates)
            logger.debug(f'Completed Step 1 - Same Template Merge, original template num: {ori_num}, current template num: {cur_num}')
            logger.debug('Removing templates {}, adding templates {}'.format(','.join(old_templates), ','.join([str(t.id) for t in new_templates])))
        # Step 2: Fix pattern and within context, clustering and abstracting external contexts, merge the external contexts, return immediately if any change happens
        clusters = []
        selected = {}
        inner_changed = False
        for t in templates:
            selected[t] = 0
        for i, t in enumerate(templates):
            cluster = []
            if selected[t] == 1:
                continue
            for j in range(i + 1, len(templates)):
                if selected[templates[j]] == 1:
                    continue
                if distances['accurate']['pattern'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] == 1.0:
                    cluster.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        if len(clusters) > 0:
            logger.debug(f'Entered Step 2 - External Context Merge, {len(clusters)} clusters will be abstracted.')
            changed = True
            inner_changed = True
            ori_num = len(templates)
            distances, pairs, templates = self.merge_external_contexts(distances, pairs, clusters, templates)
            cur_num = len(templates)
            logger.debug(f'Completed Step 2 - External Context Merge, original template num: {ori_num}, current template num: {cur_num}')
        if inner_changed:
            return changed, distances, pairs, templates
        
        # Step 3: Fix pattern, clustering and abstracting within context, generate new templates for step 2 but not merge any, return immediately if any change happens
        clusters = []
        selected = {}
        inner_changed = False
        for t in templates:
            selected[t] = 0
        for i, t in enumerate(templates):
            cluster = []
            if selected[t] == 1:
                continue
            for j in range(i + 1, len(templates)):
                if selected[templates[j]] == 1:
                    continue
                if distances['accurate']['pattern'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] != -9999:
                    cluster.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        if len(clusters) > 0:
            logger.debug(f'Entered Step 3 - Within Context Abstraction, {len(clusters)} clusters will be abstracted.')
            changed = True
            inner_changed = True
            ori_num = len(self.fixed_id2template)
            distances, pairs, templates = self.abstract_within_contexts(distances, pairs, clusters, templates)
            cur_num = len(self.fixed_id2template)
            logger.debug(f'Completed Step 3 - Within Context Abstraction, {cur_num - ori_num} templates are abstracted.')
        if inner_changed:
            return changed, distances, pairs, templates

        # Step 4-1(For Add, Remove and Replace): Clustering and abstracting pattern, generate new templates for step 2 but not merge any, return immediately if any change happens
        if self.category != 'Insert':
            clusters = []
            selected = {}
            inner_changed = False
            for t in templates:
                selected[t] = 0
            for i, t in enumerate(templates):
                cluster = []
                if selected[t] == 1:
                    continue
                for j in range(i + 1, len(templates)):
                    if selected[templates[j]] == 1:
                        continue
                    if distances['structural']['pattern'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] != -9999:
                        cluster.append(templates[j])
                        selected[templates[j]] = 1
                if len(cluster) > 0:
                    cluster.append(t)
                    selected[t] = 1
                    clusters.append(cluster)
            ori_num = len(self.fixed_id2template)
            if len(clusters) > 0:
                logger.debug(f'Entered Step 4 - Pattern Abstraction, {len(clusters)} clusters will be abstracted.')
                inner_changed, distances, pairs, templates = self.abstract_patterns(distances, pairs, templates, clusters = clusters)
            else:
                logger.debug('Entered Step 4 - Pattern Abstraction, no cluster found, will choose two mergeable templates.')
                inner_changed, distances, pairs, templates = self.abstract_patterns(distances, pairs, templates)
            cur_num = len(self.fixed_id2template)
            if inner_changed:
                changed = True
                logger.debug(f'Completed Step 4-1 - Regular Pattern Abstraction, {cur_num - ori_num} templates are abstracted.')
            else:
                logger.debug(f'Completed Step 4-1 - Regular Pattern Abstraction, no template is abstracted.')
            
            if inner_changed or self.category not in ['Remove', 'Replace']:
                return changed, distances, pairs, templates
        else:
            #Step 4-2(For Insert): Fix after tree in pattern, abstract before tree; If before tree cannot be further abstracted, abstract after tree, return immediately if any change happens
            inner_changed = False
            ori_num = len(self.fixed_id2template)
            inner_changed, distances, pairs, templates = self.mining_insert(distances, pairs, templates)
            cur_num = len(self.fixed_id2template)
            if inner_changed:
                changed = True
                logger.debug(f'Completed Step 4-2 - Insert Pattern Abstraction, {cur_num - ori_num} templates are abstracted.')
            else:
                logger.debug(f'Completed Step 4-2 - Insert Pattern Abstraction, no template is abstracted.')
            return changed, distances, pairs, templates

        # Step 5(For Remove and Replace): Clustering and abstracting pattern for non-mergable within context, set within context to None, return immediately if any change happens
        if self.category in ['Remove', 'Replace']:
            clusters = []
            selected = {}
            inner_changed = False
            for t in templates:
                selected[t] = 0
            for i, t in enumerate(templates):
                cluster = []
                if selected[t] == 1:
                    continue
                for j in range(i + 1, len(templates)):
                    if selected[templates[j]] == 1:
                        continue
                    if distances['structural']['pattern'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] == -9999:
                        cluster.append(templates[j])
                        selected[templates[j]] = 1
                if len(cluster) > 0:
                    cluster.append(t)
                    selected[t] = 1
                    clusters.append(cluster)
            ori_num = len(self.fixed_id2template)
            if len(clusters) > 0:
                logger.debug(f'Entered Step 5 - Pattern Abstraction Regardless of Within Context, {len(clusters)} clusters will be abstracted.')
                inner_changed, distances, pairs, templates = self.abstract_patterns(distances, pairs, templates, clusters = clusters, extra = True)
            else:
                logger.debug('Entered Step 5 - Pattern Abstraction Regardless of Within Context, no cluster found, will choose two mergeable templates.')
                inner_changed, distances, pairs, templates = self.abstract_patterns(distances, pairs, templates, extra = True)
            cur_num = len(self.fixed_id2template)
            if inner_changed:
                changed = True
                logger.debug(f'Completed Step 5 - Pattern Abstraction Regardless of Within Context, {cur_num - ori_num} templates are abstracted.')
            else:
                logger.debug(f'Completed Step 5 - Pattern Abstraction Regardless of Within Context, no template is abstracted.')

        return changed, distances, pairs, templates


    def mine(self, n, category = None):
        # n - Number of templates finally left
        for c in self.fix_template:
            try:
                if category != None and c != category:
                    continue
                templates = self.fix_template[c]
                self.category = c
                #templates = [self.id2template[1021], self.id2template[545]]
                distances, pairs = self.initialize_distances(templates)
                self.print_distances(distances, templates)
                #self.draw_templates(self.fix_template[c], 'figures', draw_children = True, dump_attributes = True)
                #exit()
                for i, iteration in tqdm(enumerate(range(0, MAX_ITERATION)), desc = 'Mining Templates'):
                    logger.debug(f'=====Mining iteration: {iteration}=====')
                    changed, distances, pairs, templates = self.mining(distances, pairs, templates)
                    #self.print_distances(distances, templates)
                    if not changed:
                        break
                self.fix_template[c] = [self.fixed_id2template[t.id] for t in templates]
                self.fix_template[c] = self.compress_templates(self.fix_template[c])
                self.fix_template[c] = self.remove_single_templates(self.fix_template[c])
                #self.draw_templates(self.fix_template[c], 'figures', draw_children = True)
                print('Mining Complete for category \'{}\'. {} templates finally generated.'.format(c, len(self.fix_template[c])))
            except KeyboardInterrupt:
                self.draw_templates([self.fixed_id2template[t.id] for t in templates], 'figures', draw_children = True)
        self.dump_templates(templates = self.fix_template)
    
    def load_templates(self, datafile):
        mined_info = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
        for i in mined_info["templates"]:
            try:
                self.id2template[int(i)] = FixTemplate.load(mined_info["templates"][i])
            except Exception as e:
                traceback.print_exc()
                with open('error_json.json', 'w', encoding = 'utf-8') as ef:
                    ef.write(json.dumps(mined_info["templates"][i], sort_keys=True, indent=4, separators=(',', ': ')))
                exit()
        
        for k in mined_info["mined"]:
            self.fix_template[k] = []
            for i in mined_info["mined"][k]:
                if int(i) in self.id2template:
                    self.fix_template[k].append(self.id2template[int(i)])
        
        for i in tqdm(self.id2template, desc = 'Copying Tempaltes'):
            self.fixed_id2template[i] = deepcopy(self.id2template[i])
        
        self.index = max(list(self.fixed_id2template.keys())) + 1



    def dump_templates(self, templates = None):
        if templates:
            if isinstance(templates, list):
                mined = []
                template_map = {}
                child_templates = []
                for t in templates:
                    mined.append(t.id)
                    child_templates += t.get_all_child_templates(self.fixed_id2template)
                for i in mined:
                    template_map[i] = self.fixed_id2template[i].dump()
                for i in child_templates:
                    template_map[i] = self.fixed_id2template[i].dump()
                
                info = {
                    "mined": mined,
                    "templates": template_map
                }

                with open('large_mined_{}_templates.json'.format(self.category), 'w', encoding = 'utf-8') as mf:
                    mf.write(json.dumps(info, indent=4, separators=(',', ': ')))
            elif isinstance(templates, dict):
                mined = {}
                template_map = {}
                child_templates = []
                for k in templates:
                    mined[k] = []
                    for t in templates[k]:
                        mined[k].append(t.id)
                        child_templates += t.get_all_child_templates(self.fixed_id2template)
                for k in mined:
                    for i in mined[k]:
                        try:
                            template_map[i] = self.fixed_id2template[i].dump()
                        except Exception as e:
                            traceback.print_exc()
                            print(e)
                            exit()
                            logger.error('Error occurs when dumping template {}, skipped.'.format(i))
                            continue
                for i in child_templates:
                    try:
                        template_map[i] = self.fixed_id2template[i].dump()
                    except Exception as e:
                        traceback.print_exc()
                        print(e)
                        exit()
                        logger.error('Error occurs when dumping template {}, skipped.'.format(i))
                        continue
                
                info = {
                    "mined": mined,
                    "templates": template_map
                }

                with open('large_mined_templates.json', 'w', encoding = 'utf-8') as mf:
                    mf.write(json.dumps(info, indent=4, separators=(',', ': ')))

        else:
            for c in self.fix_template:
                templates = self.fix_template[c]
                if len(templates) == 0:
                    continue
                self.category = c
                self.dump_templates(templates = templates)



def test_one():
    sig = 'ReactiveX/RxPY:9bb83931566c77abb52fa9a582868d210b746785'
    a = ASTCompare()
    change_pairs = a.compare_one('combined_commits_contents.json', sig.split(':')[0], sig.split(':')[1])
    miner = FixMiner()
    miner.build_templates(change_pairs)
    miner.print_info()
    miner.mine(10)
    #miner.dump_templates(miner.fix_template)
    #for i in miner.id2template:
    #    miner.id2template[i].draw(miner.fixed_id2template, filerepo = 'figures2', draw_contexts = True, dump_attributes = False)


def main():
    start = time.time()
    #a = ASTCompare()
    #change_pairs = a.compare_projects('combined_commits_contents.json')
    #change_pairs = a.compare_projects('final_combined_commits.json')
    miner = FixMiner()
    miner.load_templates('large_mined_templates_initial.json')
    #miner.build_templates(change_pairs)
    miner.print_info()
    #miner.dump_templates(templates = miner.fix_template)
    miner.mine(10)
    end = time.time()
    print('Template mining finished, cost {} seconds.'.format(end - start))
    #miner.draw_templates([miner.id2template[221], miner.id2template[222]], 'figures')
    #miner.draw_templates(miner.fix_template['Insert'], 'figures', draw_children = True)
    

        
        



if __name__ == '__main__':
    #test_one()
    main()
    #print(FixTemplate.get_distance(miner.fix_template['Add'][0], miner.fix_template['Add'][1]), FixTemplate.get_distance(miner.fix_template['Add'][1], miner.fix_template['Add'][0]))
    


        
        
                

                





    