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

class ASTCompare(object):
    def __init__(self):
        self.beforeroot = None
        self.afterroot = None

    def build_change_tree(self, root, before, change_lines, raw_change_lines):
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
            if not c_tree.build():
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
            logger.warning('Empty commit.')
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
                logger.info(f'+++++++Handling location {l}')
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
                logger.info(f'Handling commit {c} in {r}')
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
                logger.info(f'Handling commit {c} in {r}')
                change_pairs[r][c] = self.compare_commit(data[r][c], r, c)
        
        return change_pairs


class FixMiner(object):
    def __init__(self):
        self.fix_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.ori_template = {'Add': [], 'Remove': [], 'Insert': [], 'Shuffle': [], 'Replace': []}
        self.id2template = {}
        self.index = 0
        self.fixed_id2template = {}

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
                    if TemplateNode.compare(an, bn) and TemplateTree.compare_leaf_path(before_leaf_paths[bn], after_leaf_paths[an]):
                        if bn.parent != None and bn.parent.type == 'Root' and order != None:
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
                        if an.parent != None and an.parent.type == 'Root' and order != None:
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
                before_tree.collect_special_nodes()
                partial_after_tree.collect_special_nodes()
                before_tree.set_treetype('Before')
                partial_after_tree.set_treetype('After')
                template = FixTemplate('Remove', before_tree, partial_after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, partial_after_tree)
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
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    before_tree.collect_special_nodes()
                    after_tree.collect_special_nodes()
                    before_tree.set_treetype('Before')
                    after_tree.set_treetype('After')
                    template = FixTemplate('Insert', before_tree, after_tree)
                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, after_tree)
                    template.before_contexts = before_contexts
                    template.after_contexts = after_contexts
                    template.add_instance(pair)
                    return template
                else:
                    if partial_before_tree != None:
                        before_tree = TemplateTree.merge(partial_before_tree, totally_before_tree, pair.status['order']['before'])
                    else:
                        before_tree = totally_before_tree
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                    before_tree.collect_special_nodes()
                    after_tree.collect_special_nodes()
                    before_tree.set_treetype('Before')
                    after_tree.set_treetype('After')
                    template = FixTemplate('Replace', before_tree, after_tree)
                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, after_tree)
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
                if partial_after_tree != None:
                    after_tree = TemplateTree.merge(partial_after_tree, totally_after_tree, pair.status['order']['after'])
                else:
                    after_tree = totally_after_tree
                before_tree.collect_special_nodes()
                after_tree.collect_special_nodes()
                before_tree.set_treetype('Before')
                after_tree.set_treetype('After')
                template = FixTemplate('Replace', before_tree, after_tree)
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Partially'] + pair.status['Replaced']['before']['Totally'], before_tree, after_tree)
                template.before_contexts = before_contexts
                template.after_contexts = after_contexts
                template.add_instance(pair)
                return template
        else:
            before_tree = TemplateTree()
            before_tree.build(pair.status['Replaced']['before']['Totally'])
            after_tree = TemplateTree()
            after_tree.build(pair.status['Replaced']['after']['Totally'])
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
                    before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Totally'], before_tree, after_tree)
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
                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Totally'], before_tree, after_tree)
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
            before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Replaced']['before']['Totally'], before_tree, after_tree)
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
            for t in templates:
                if t.before != None and t.after != None:
                    context = TemplateTree.get_same_subtree(t.before, t.after)
                    if context != None:
                        t.before, before_context_relations = TemplateTree.subtract_subtree(context, t.before)
                        t.after, after_context_relations = TemplateTree.subtract_subtree(context, t.after)
                        context.set_treetype('Within_Context')
                        t.before.set_treetype('Before')
                        t.after.set_treetype('After')
                        t.within_context = Context(context, [before_context_relations, after_context_relations], 'Within')
            self.fix_template[c] = templates


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
                        if TemplateNode.self_compare(v, bv):
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
                        if TemplateNode.self_compare(v, av):
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
        
        for ac in after_contexts:
            exist = False
            for c in final_after_contexts:
                if TemplateTree.compare(ac, c):
                    exist = True
                    break
            if not exist:
                final_after_contexts.append(ac)

        before_contexts = Context.build_external_context(final_before_contexts, 'Before')
        before_contexts.context_tree.set_treetype('Before_Context')
        after_contexts = Context.build_external_context(final_after_contexts, 'After')
        after_contexts.context_tree.set_treetype('After_Context')

        return before_contexts, after_contexts

    def build_templates(self, change_pairs):
        for r in tqdm(change_pairs, desc = 'Initializing Fix Templates'):
            for c in change_pairs[r]:
                for f in change_pairs[r][c]:
                    for l in change_pairs[r][c][f]:
                        for pair in change_pairs[r][c][f][l]:
                            logger.info('++++++Handling {}/{}/{}/{} change pair'.format(r, c, f, l))
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
                                    else:
                                        after_tree = partial_after_tree
                                after_tree.collect_special_nodes()
                                template = FixTemplate('Add', None, after_tree)
                                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Added']['Totally'] + pair.status['Added']['Partially'], None, after_tree)
                                template.before_contexts = before_contexts
                                template.after_contexts = after_contexts
                                template.add_instance(pair)
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
                                    else:
                                        before_tree = partial_before_tree
                                before_tree.collect_special_nodes()
                                template = FixTemplate('Remove', before_tree, None)
                                before_contexts, after_contexts = self.build_before_and_after_contexts(pair.status['Removed']['Totally'] + pair.status['Removed']['Partially'], before_tree, None)
                                template.before_contexts = before_contexts
                                template.after_contexts = after_contexts
                                template.add_instance(pair)
                                self.fix_template['Remove'].append(template)
                                continue
                            if len(pair.status['Replaced']['before']['Totally']) + len(pair.status['Replaced']['after']['Totally']) > 0 or \
                            len(pair.status['Replaced']['before']['Partially']) + len(pair.status['Replaced']['after']['Partially']) > 0:
                                if len(pair.status['Replaced']['before']['Partially']) != len(pair.status['Replaced']['after']['Partially']) and\
                                len(pair.status['Replaced']['before']['Partially']) > 0 and len(pair.status['Replaced']['after']['Partially']) > 0:
                                    logger.error('Inconsistent number of partially changed statements before and after the commit.')
                                    continue
                                template = self._process_replaced(pair)
                                if template != None:
                                    self.fix_template[template.action].append(template)
        self.clean()
        self.abstract_templates()
        self.split_context()
        self.assign_ids()
        for i in self.id2template:
            self.fixed_id2template[i] = deepcopy(self.id2template[i])


    def assign_ids(self):
        for c in self.fix_template:
            for t in self.fix_template[c]:
                t.id = self.index
                self.id2template[self.index] = t
                self.index += 1   

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

    def initialize_distances(self, templates):
        distances = {
            'accurate': {
                'pattern': {}, 'within': {}, 'before': {}, 'after': {}, 'external': {}
            },
            'structural': {
                'pattern': {}, 'within': {}, 'before': {}, 'after': {}, 'external': {}
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
        for i, t in enumerate(templates):
            for j in range(i+1, len(templates)):
                if t not in distances['accurate']['pattern']:
                    for k in distances:
                        for ik in distances[k]:
                            distances[k][ik][t] = {}
                if templates[j] not in distances['accurate']['pattern']:
                    for k in distances:
                        for ik in distances:
                            distances[k][ik][templates[j]] = {}
                if self.is_pattern_mergable(t, templates[j]):
                    d = FixTemplate.get_distance_for_pattern(t, templates[j])
                    structural_d = FixTemplate.get_structural_distance_for_pattern(t, templates[j])
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
                    distances['accurate']['within'][t][templates[j]] = d[k]
                    distances['accurate']['within'][templates[j]][t] = d[k]
                    distances['structural']['within'][t][templates[j]] = structural_d[k]
                    distances['structural']['within'][templates[j]][t] = structural_d[k]
                    pairs['accurate']['within'][t][templates[j]] = p[k]
                    pairs['accurate']['within'][templates[j]][t] = p[k]
                    pairs['structural']['within'][t][templates[j]] = structural_p[k]
                    pairs['structural']['within'][templates[j]][t] = structural_p[k]
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
                    pairs['accurate'][k][templates[j]][t] = p[k]
                for k in ['before', 'after']:
                    pairs['structural'][k][t][templates[j]] = structural_p[k]
                    pairs['structural'][k][templates[j]][t] = structural_p[k]

        return distances, pairs

    def add_distances(self, distances, pairs, template, templates):
        for k in distances:
            distances[k][template] = {}
        for k in pairs:
            pairs[k][template] = {}
        for t in templates:
            if self.is_pattern_mergable(t, template):
                d = FixTemplate.get_distance_for_pattern(t, template)
                structural_d = FixTemplate.get_structural_distance_for_pattern(t, template)
                distances['pattern'][t][template] = d
                distances['pattern'][template][t] = d
                distances['structural']['pattern'][t][templates[j]] = structural_d
                distances['structural']['pattern'][templates[j]][t] = structural_d
            else:
                distances['pattern'][t][template] = -9999
                distances['pattern'][template][t] = -9999
                distances['structural']['pattern'][t][templates[j]] = -9999
                distances['structural']['pattern'][templates[j]][t] = -9999

            d, p = FixTemplate.get_distance_for_context(t, template)
            structural_d, structural_p = FixTemplate.get_structural_distance_for_context(t, template)
            
            if self.is_within_context_mergable(t, template):
                distances['accurate']['within'][t][template] = d[k]
                distances['accurate']['within'][template][t] = d[k]
                distances['structural']['within'][t][template] = structural_d[k]
                distances['structural']['within'][template][t] = structural_d[k]
                pairs['accurate']['within'][t][template] = p[k]
                pairs['accurate']['within'][template][t] = p[k]
                pairs['structural']['within'][t][template] = structural_p[k]
                pairs['structural']['within'][template][t] = structural_p[k]
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
                pairs['accurate'][k][template][t] = p[k]
            for k in ['before', 'after']:
                pairs['structural'][k][t][template] = structural_p[k]
                pairs['structural'][k][template][t] = structural_p[k]

        return distances, pairs

    def get_max_distance(self, distances, templates):
        max_distance = -9999
        max_pair = []
        for i, t in enumerate(templates):
            for j in range(i+1, len(templates)):
                if distances[t][templates[j]] > max_distance:
                    max_distance = distances[t][templates[j]]
                    max_pair = [t, templates[j]]
        return *max_pair, max_distance

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

    def is_pattern_mergable(self, a, b):
        if (a.before == None and b.before != None) or\
        (a.before != None and b.before == None) or\
        (a.after == None and b.after != None) or\
        (a.after != None and b.after == None):
            return False
        
        score = 0
        if a.before and b.before:
            score += 1
            if len(a.before.root.children['body']) != len(b.before.root.children['body']):
                score -= 1
            else:
                found = False
                for index, n in enumerate(a.before.root.children['body']):
                    if TemplateNode.compare(n, a.before.root.children['body'][index]):
                        continue
                    elif n.type != b.before.root.children['body'][index].type:
                        continue
                    else:
                        found = True
                        break
                if not found:
                    score -= 1

        if a.after and b.after:
            score += 1
            if len(a.after.root.children['body']) != len(b.after.root.children['body']):
                score -= 1
            else:
                found = False
                for index, n in enumerate(a.after.root.children['body']):
                    if TemplateNode.compare(n, a.after.root.children['body'][index]):
                        continue
                    elif n.type != b.after.root.children['body'][index].type:
                        continue
                    else:
                        found = True
                        break
                if not found:
                    score -= 1
        
        if score == 0:
            return False
        else:
            return True

        return True

    def is_within_context_mergable(self, a, b):
        if (a.within_context == None and b.within_context != None) or\
            (a.within_context != None and b.within_context == None):
            return False
        
        if a.within_context and b.within_context:
            a_leaf_nodes = a.within_context.context_tree.get_leaf_nodes()
            b_leaf_nodes = b.within_Context.context_tree.get_leaf_nodes()

            for index, n in enumerate(a_leaf_nodes):
                if n.type != b_leaf_nodes[index].type:
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

    def draw_templates(self, templates, path, dump_instances = True, dump_contexts = False):
        for t in templates:
            t.draw(filerepo = path, draw_contexts = True)
            if dump_contexts:
                text = ""
                for c in t.contexts:
                    text += '=======================================================================\n#Contexts:\n'
                    text += '\n'.join(c.dump())
                    text += '\n#Context Relations:\n'
                    text += 'Before: {}\nAfter: {}\n'.format(','.join(t.context_relations[c][0]) if t.context_relations[c][0] != None else None, ','.join(t.context_relations[c][1])if t.context_relations[c][1] != None else None)
                with open(os.path.join(path, 'FIX_TEMPLATE_{}_CONTEXTS.txt'.format(t.id)), 'w', encoding = 'utf-8') as f:
                    f.write(text)
            if dump_instances:
                text = ""
                for i in t.instances:
                    text += '========================{}:{}========================\n{}\n=================================================================\n'.format(i.metadata['repo'], i.metadata['commit'], i.metadata['content'])
                with open(os.path.join(path, 'FIX_TEMPLATE_{}_INSTANCES.txt'.format(t.id)), 'w', encoding = 'utf-8') as f:
                    f.write(text)


    def is_set_identical(self, a, b):
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
                n.refer_to.remove(node)
            node.referred_from = []
        if len(node.refer_to) > 0 and mode in ['all', 'refer_to']:
            for n in node.refer_to:
                n.referred_from.remove(node)
            node.refer_to = []
        if len(node.context_refer) > 0 and mode in ['all', 'context_refer']:
            for n in node.context_refer:
                n.refer_to.remove(node)
            node.context_refer = []
        if len(node.self_refer) > 0 and mode in ['all', 'self_refer']:
            for n in node.self_refer:
                n.self_refer.remove(node)
            node.self_refer = []



    def abstract_values_for_nodes(self, a, b):
        if isinstance(a, TemplateNode) and isinstance(b, TemplateNode) and a.type == b.type:
            newnode = a.soft_copy()
            newnode.ori_nodes = [a, b]
            if a.value != b.value:
                if a.base_type in ['Variable', 'Attribute']:
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
                    if len(a.context_refer) > 0 and self.is_set_identical(a.context_refer, b.context_refer):
                        newnode.value = 'REFERRED'
                    else:
                        newnode.ori_context_refer = []
                        self.clean_reference(a, mode = 'context_refer')
                        self.clean_reference(b, mode = 'context_refer')
                    if len(a.self_refer) > 0 and self.is_set_identical(a.self_refer, b.self_refer):
                        newnode.value = 'REFERRED'
                    else:
                        newnode.ori_self_refer = []
                        self.clean_reference(a, mode = 'self_refer')
                        self.clean_reference(b, mode = 'self_refer')
                elif a.base_type == 'Literal' and type(a.value) == type(b.value):
                    newnode.value = type(a.value).__name__
                    self.clean_reference(a)
                    self.clean_reference(b)
                elif a.base_type == 'Op' and op2cat[a.value] == op2cat[b.value]:
                    newnode.value = op2cat[a.value]
                    self.clean_reference(a)
                    self.clean_reference(b)
                else:
                    newnode.value = 'ABSTRACTED'
                    newnode.value_abstracted = True
                    self.clean_reference(a)
                    self.clean_reference(b)
            else:
                newnode.value = a.value
                if a.base_type in ['Variable', 'Attribute']:
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

    def abstract_values_for_trees(self, a, b):
        if isinstance(a, TemplateTree) and isinstance(b, TemplateTree):
            newtree = TemplateTree()
            newtree.root = self.abstract_values_for_nodes(a.root, b.root)
            newtree.collect_special_nodes()
            return newtree
        else:
            raise ValueError('Cannot abstract the values of two structurally non-identical trees.')

    def abstract_structures_for_contexts(self, a, b, pair):
        if isinstance(a, TemplateTree) and isinstance(b, TemplateTree):
            newtree = TemplateTree()
            a_leaf_nodes = a.get_leaf_nodes()
            b_leaf_nodes = b.get_leaf_nodes()
            if len(pair) != min(len(a_leaf_nodes), len(b_leaf_nodes)):
                raise ValueError('The length of leaf node pair should match the length of leaf node lists in one tree.')
            a_nodes = []
            b_nodes = []
            node_map = {}
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
                b_node = p[1]
                b_leaf_path = [b_node]
                if b_node not in b_nodes:
                    b_nodes.append(b_node)
                for i in range(1, p[2]):
                    b_node = b_node.parent
                    if b_node not in b_nodes:
                        b_nodes.append(b_node)
                    b_leaf_path.append(b_node)
                for i in range(0, len(a_leaf_path)):
                    node_map[a_leaf_path[i]] = b_leaf_path[i]
            
            node_map[a.root] = b.root
            
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
                
            
            # Align two trees
            for n in a.iter_nodes():
                bn = node_map[n]
                for c in n.children:
                    bn.children[c] = []
                    for nn in n.children[c]:
                        bn.children[c].append(node_map[nn])
            
            newtree.root = self.abstract_values_for_nodes(a.root, b.root)
            newtree.collect_special_nodes()
            return newtree
        else:
            raise ValueError('Input a and b must be TemplateTree objects.')

    def abstract_structures_for_node(self, a, b):
        if isinstance(a, TemplateNode) and isinstance(b, TemplateNode):
            if a.type == b.type:
                pass
            else:
                if a.base_type == b.base_type and a.base_type == 'Expr':
                    return TemplateNode('Expr'), TemplateNode('Expr')
                else:
                    return TemplateNode('Stmt'), TemplateNode('Stmt')
        else:
            ValueError('Input a and b must be TemplateNode objects.')

    def abstract_structures_for_patterns(self, a, b):
        if isinstance(a, TemplateTree) and isinstance(b, TemplateTree):
            pass
        else:
            raise ValueError('Input a and b must be TemplateTree objects.')

    def merge_external_contexts(self, distances, pairs, clusters, templates):
        new_templates = []
        merged = {}
        for i in range(0, len(clusters)):
            merged[i] = 0
        # Step 1: Merge structurally identical trees
        for index, cluster in enumerate(clusters):
            candidates = []
            max_distance = -9999
            for i, t in cluster:
                for j in range(i + 1, len(cluster)):
                    if distances['structural']['external'][t][templates[j]] == 1.0 and distances['accurate']['external'][t][templates[j]] > max_distance:
                        candidates = [t, templates[j]]
            if len(candidates) > 0:
                merged[index] = 1
                template = FixTemplate(candidates[0].action, candidates[0].before, candidates[0].after)
                template.within_context = candidates[0].within_context
                template.before_contexts = Context(self.abstract_values_for_trees(candidates[0].before_contexts.context_tree, candidates[1].before_contexts.context_tree), None, 'Before')
                template.after_contexts = Context(self.abstract_values_for_trees(candidates[0].after_contexts.context_tree, candidates[1].after_contexts.context_tree), None, 'After')
                template.merge(candidates)
                template.recover_reference()
                template.set_treetype()
                template.id = self.index
                self.index += 1
                self.id2template[template.id] = template
                self.fixed_id2template[template.id] = deepcopy(template)
                new_templates.append(template)
        
        # Step 2: Merge structurally non-identical trees
        for index, cluster in enumerate(clusters):
            if index in merged:
                continue
            candidates = []
            max_distance = -9999
            for i, t in cluster:
                for j in range(i + 1, len(cluster)):
                    if distances['accurate']['external'][t][templates[j]] > max_distance:
                        candidates = [t, templates[j]]
            if len(candidates) > 0:
                merged[index] = 1
                template = FixTemplate(candidates[0].action, candidates[0].before, candidates[0].after)
                template.within_context = candidates[0].within_context
                template.before_contexts = Context(self.abstract_structures_for_contexts(candidates[0].before_contexts.context_tree, candidates[1].before_contexts.context_tree, pairs['structural']['before'][candidates[0]][candidates[1]]), None, 'Before')
                template.before_contexts = Context(self.abstract_structures_for_contexts(candidates[0].after_contexts.context_tree, candidates[1].after_contexts.context_tree, pairs['structural']['after'][candidates[0]][candidates[1]]), None, 'After')
                template.merge(candidates)
                template.recover_reference()
                template.set_treetype()
                template.id = self.index
                self.index += 1
                self.id2template[template.id] = template
                self.fixed_id2template[template.id] = deepcopy(template)
                new_templates.append(template)
        
        # Register new templates, remove old templates
        templates += new_templates
        for t in new_templates:
            for tt in t.former_templates:
                templates.remove(self.id2template[tt])
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)

        return distances, pairs, templates

    def abstract_within_contexts(self, distances, pairs, clusters, templates):
        new_templates = []
        abstracted = {}
        for i in range(0, len(clusters)):
            abstracted[i] = 0
        # Step 1: Abstract structurally identical trees
        for index, cluster in enumerate(clusters):
            candidates = []
            max_distance = -9999
            for i, t in cluster:
                for j in range(i + 1, len(cluster)):
                    if distances['structural']['within'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] > max_distance:
                        candidates = [t, templates[j]]
            if len(candidates) > 0:
                abstracted[index] = 1
                for i in range(0, len(candidates)):
                    template = FixTemplate(candidates[i].action, deepcopy(candidates[i].before), deepcopy(candidates[i].after))
                    template.within_context = Context(self.abstract_values_for_trees(candidates[0].within_context.context_tree, candidates[1].within_context.context_tree), candidates[i].within_context.relationship, 'Within')
                    template.before_contexts = deepcopy(candidates[i].before_contexts)
                    template.after_contexts = deepcopy(candidates[i].after_contexts)
                    template.merge([candidates[i]])
                    template.recover_reference()
                    template.set_treetype()
                    template.id = self.index
                    self.index += 1
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    new_templates.append(template)
        
        # Step 2: Abstract structurally non-identical trees
        for index, cluster in enumerate(clusters):
            if index in merged:
                continue
            candidates = []
            max_distance = -9999
            for i, t in cluster:
                for j in range(i + 1, len(cluster)):
                    if distances['accurate']['external'][t][templates[j]] > max_distance:
                        candidates = [t, templates[j]]
            if len(candidates) > 0:
                abstracted[index] = 1
                for i in range(0, len(candidates)):
                    template = FixTemplate(candidates[i].action, deepcopy(candidates[i].before), deepcopy(candidates[i].after))
                    template.within_context = Context(self.abstract_structures_for_contexts(candidates[0].within_context.context_tree, candidates[1].within_context.context_tree, pairs['structural']['within'][candidates[0]][candidates[1]]), candidates[i].within_context.relationship, 'Within')
                    template.before_contexts = deepcopy(candidates[i].before_contexts)
                    template.after_contexts = deepcopy(candidates[i].after_contexts)
                    template.merge(candidates)
                    template.recover_reference()
                    template.set_treetype()
                    template.id = self.index
                    self.index += 1
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    new_templates.append(template)
        
        # Register new templates, remove old templates
        templates += new_templates
        for t in new_templates:
            for tt in t.former_templates:
                templates.remove(self.id2template[tt])
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)

        return distances, pairs, templates

    def abstract_patterns(self, distances, pairs, templates, clusters = None):
        new_templates = []
        changed = False
        # Step 1: Abstract structurally identical trees
        if clusters:
            for index, cluster in enumerate(clusters):
                candidates = []
                max_distance = -9999
                for i, t in cluster:
                    for j in range(i + 1, len(cluster)):
                        if distances['accurate']['pattern'][t][templates[j]] > max_distance:
                            candidates = [t, templates[j]]
                if len(candidates) > 0:
                    for i in range(0, len(candidates)):
                        template = FixTemplate(candidates[i].action, self.abstract_values_for_trees(candidates[0].before, candidates[1].before), self.abstract_values_for_trees(candidates[0].after, candidates[1].after))
                        template.within_context = deepcopy(candidates[i].within_context)
                        template.before_contexts = deepcopy(candidates[i].before_contexts)
                        template.after_contexts = deepcopy(candidates[i].after_contexts)
                        template.merge([candidates[i]])
                        template.recover_reference()
                        template.set_treetype()
                        template.id = self.index
                        self.index += 1
                        self.id2template[template.id] = template
                        self.fixed_id2template[template.id] = deepcopy(template)
                        new_templates.append(template)
                        changed = True
                else:
                    raise ValueError('Less than two templates in the cluster.')
        # Step 2: Abstract structurally non-identical trees
        else:
            a, b, max_d = self.get_max_distance(distances['accurate']['pattern'], templates)
            if max_d == -9999:
                changed = False
                return changed, distances, pairs, templates
            else:
                candidates = [a, b]
                for i in range(0, len(candidates)):
                    template = FixTemplate(candidates[i].action, self.abstract_structures_for_patterns(candidates[0].before, candidates[1].before), self.abstract_structures_for_patterns(candidates[0].after, candidates[1].after))
                    template.within_context = deepcopy(candidates[i].within_context)
                    template.before_contexts = deepcopy(candidates[i].before_contexts)
                    template.after_contexts = deepcopy(candidates[i].after_contexts)
                    template.merge([candidates[i]])
                    template.recover_reference()
                    template.set_treetype()
                    template.id = self.index
                    self.index += 1
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    new_templates.append(template)
                    changed = True
    
        # Register new templates, remove old templates
        templates += new_templates
        for t in new_templates:
            for tt in t.former_templates:
                templates.remove(self.id2template[tt])
        for t in new_templates:
            distances, pairs = self.add_distances(distances, pairs, t, templates)

        return changed, distances, pairs, templates
                

    def mining(self, distances, pairs, templates):
        changed = False

        # Step 1: Merge same tamplates
        inner_changed = True
        while(inner_changed):
            inner_changed = False
            new_templates = []
            for i, t in enumerate(templates):
                same = []
                for j in range(i + 1, len(templates)):
                    if distances['accurate']['pattern'][t][templates[j]] == 1.0 and distances['accurate']['within'][t][templates[j]] == 1.0 and distances['accurate']['external'][t][templates[j]] == 1.0:
                        same.append(templates[j])
                if len(same) > 0:
                    template = FixTemplate(t.action, t.before, t.after)
                    template.within_context = t.within_context
                    template.before_contexts = t.before_contexts
                    template.after_contexts = t.after_contexts
                    template.merge([k for k in same + [t]])
                    template.id = self.index
                    self.id2template[template.id] = template
                    self.fixed_id2template[template.id] = deepcopy(template)
                    self.index += 1
                    new_templates.append(template)
                    inner_changed = True
                    break
            templates += new_templates
            for t in new_templates:
                for tt in t.former_templates:
                    templates.remove(self.id2template[tt])
            for t in new_templates:
                distances, pairs = self.add_distances(distances, pairs, t, templates)
            if inner_changed:
                changed = True
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
            changed = True
            inner_changed = True
            distances, pairs, templates = self.merge_external_contexts(distances, pairs, clusters, templates)
        if inner_changed:
            return changed, distances, pairs, templates
        
        # Step 3: Fix pattern, clustering and abstracting within context, generate new templates for step 2 but not merge any, return immediately if any change happens
        clusters = []
        selected = []
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
                if distances['accurate']['pattern'][t][templates[j]] == 1.0:
                    clsuter.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        if len(clusters) > 0:
            changed = True
            inner_changed = True
            distances, pairs, templates = self.abstract_within_contexts(distances, pairs, clusters, templates)
        if inner_changed:
            return changed, distances, pairs, templates

        # Step 4: Clustering and abstracting pattern, generate new templates for step 2 but not merge any, return immediately if any change happens
        clusters = []
        selected = []
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
                if distances['structural']['pattern'][t][templates[j]] == 1.0:
                    cluster.append(templates[j])
                    selected[templates[j]] = 1
            if len(cluster) > 0:
                cluster.append(t)
                selected[t] = 1
                clusters.append(cluster)
        if len(clusters) > 0:
            inner_changed, distances, pairs, templates = self.abstract_patterns(distances, templates, clusters = clusters)
        else:
            inner_changed, distances, pairs, templates = self.abstract_patterns(distances, templates)
        
        if inner_changed:
            changed = True

        return changed, distances, pairs, templates


    def mine(self, n):
        # n - Number of templates finally left
        for c in self.fix_template:
            if c != 'Insert':
                continue
            templates = self.fix_template[c]
            distances, pairs = self.initialize_distances(templates)
            changed = True
            while(changed):
                changed, distances, pairs, templates = self.mining(distances, pairs, templates)
            self.fix_template[c] = [self.fixed_id2template[t.id] for t in templates]



def test_one():
    sig = 'AnimeKaizoku/SaitamaRobot:6ef20330aae3508fe5c9b63ab8b7db3bf9ce86ec'
    a = ASTCompare()
    change_pairs = a.compare_one('combined_commits_contents.json', sig.split(':')[0], sig.split(':')[1])
    miner = FixMiner()
    miner.build_templates(change_pairs)
    miner.print_info()
    for i in miner.id2template:
        miner.id2template[i].draw(filerepo = 'figures', draw_contexts = True)


def main():
    a = ASTCompare()
    change_pairs = a.compare_projects('combined_commits_contents.json')
    miner = FixMiner()
    miner.build_templates(change_pairs)
    miner.print_info()
    miner.draw_templates(miner.fix_template['Add'], 'figures')
    #miner.mine(10)

        
        



if __name__ == '__main__':
    #test_one()
    main()
    #print(FixTemplate.get_distance(miner.fix_template['Add'][0], miner.fix_template['Add'][1]), FixTemplate.get_distance(miner.fix_template['Add'][1], miner.fix_template['Add'][0]))
    


        
        
                

                





    