import json
import os
import ast
import re
import copy
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
                        context.set_treetype('Context')
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

        before_contexts = [Context(b, None, 'Before') for b in final_before_contexts]
        after_contexts = [Context(a, None, 'After') for a in final_after_contexts]

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

    def value_abstract_from_nodes(self, a, b):
        if a.type == b.type:
            newnode = TemplateNode(a.base_type)
            newnode.type = a.type
            if a.value != b.value:
                newnode.value = 'ABSTRACTED'
                newnode.value_abstracted = True
            else:
                newnode.value = a.value
            for c in a.children:
                newnode.children[c] = []
                for i, an in enumerate(a.children[c]):
                    child = self.value_abstract_from_nodes(a.children[c][i], b.children[c][i])
                    child.parent = newnode
                    child.parent_relation = c
                    newnode.children[c].append(child)
            return newnode
        else:
            raise ValueError('Cannot abstract the values of two nodes with different types.')
            

    def abstract_from_nodes(self, a, b):
        if a.type == b.type and not a.type_abstracted and not b.type_abstracted:
            newnode = TemplateNode(a.base_type)
            newnode.type = a.type
            if len(a.children) == len(b.children) and len(a.children) == 0:
                if a.value == b.value and not a.value_abstracted and not b.value_abstracted:
                    newnode.value = a.value
                else:
                    newnode.value = 'ABSTRACTED'
                    newnode.value_abstracted = True
                return newnode
            else:
                if a.value != b.value:
                    newnode.value = 'ABSTRACTED'
                    newnode.value_abstracted = True
                for c in a.children:
                    if c not in b.children or len(a.children[c]) != len(b.children[c]):
                        newnode.type_abstracted = True
                        return newnode
                for c in a.children:
                    newnode.children[c] = []
                    for i in range(0, len(a.children[c])):
                        newnode.children[c].append(self.abstract_from_nodes(a.children[c][i], b.children[c][i])) 
                return newnode
        elif a.type == b.type:
            if a.type_abstracted:
                newnode = copy.deepcopy(a)
                return newnode
            elif b.type_abstracted:
                newnode = copy.deepcopy(b)
                return newnode
        elif a.base_type == b.base_type and a.base_type not in ['Expr', 'Stmt']:
            newnode = TemplateNode(a.base_type)
            newnode.type = a.base_type
            newnode.type_abstracted = True
            return newnode
        else:
            if a.type != 'Stmt'and b.type != 'Stmt':
                newnode = TemplateNode('Expr')
                newnode.type = 'Expr'
                newnode.type_abstracted = True
                return newnode
            else:
                newnode = TemplateNode('Stmt')
                mewnode.type = 'Stmt'
                newnode.type_abstracted = True
                return newnode


    def merge(self, a, b):
        newbefore = None
        newafter = None
        # Handle Before tree
        if TemplateTree.compare(a.before, b.before):
            newbefore = copy.deepcopy(a.before)
        elif a.before == None and b.before == None:
            newbefore = None
        else:
            newbefore = TemplateTree()
            newbefore.root = self.abstract_from_nodes(a.before.root, b.before.root)
            newbefore.collect_special_nodes()
        
        # Hanle After tree
        if TemplateTree.compare(a.after, b.after):
            newafter = copy.deepcopy(a.after)
        elif a.after == None and b.after == None:
            newafter = None
        else:
            newafter = TemplateTree()
            newafter.root = self.abstract_from_nodes(a.after.root, b.after.root)
            newafter.collect_special_nodes()
        
        template = FixTemplate(a.action, newbefore, newafter)
        template.merge([a, b])
        if (newbefore != None and newbefore.check_abstracted()) or (newafter != None and newafter.check_abstracted()):
            template.abstracted = True
        template.id = self.index
        self.index += 1
        self.id2template[template.id] = template
        return template

    def initialize_distances(self, templates):
        distances = {}
        for i, t in enumerate(templates):
            for j in range(i+1, len(templates)):
                if t not in distances:
                    distances[t] = {}
                if templates[j] not in distances:
                    distances[templates[j]] = {}
                if not self.is_mergable(t, templates[j]):
                    distances[t][templates[j]] = -9999
                    distances[templates[j]][t] = -9999
                else:
                    distances[t][templates[j]] = FixTemplate.get_distance(t, templates[j])
                    distances[templates[j]][t] = distances[t][templates[j]]

        return distances

    def add_distances(self, distances, template, templates):
        distances[template] = {}
        for t in templates:
            if not self.is_mergable(t, template):
                distances[t][template] = -9999
                distances[template][t] = -9999
            else:
                distances[t][template] = FixTemplate.get_distance(t, template)
                distances[template][t] = distances[t][template]

        return distances

    def get_max_distance(self, distances, templates):
        max_distance = -1
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

    def merge_same_templates(self, distances, templates):
        changed = True
        while(changed):
            changed = False
            merged = {}
            for i in range(0, len(templates)):
                if i in merged:
                    continue
                same = []
                for j in range(i+1, len(templates)):
                    if distances[templates[i]][templates[j]] == 1:
                        same.append(j)
                if len(same) > 0:
                    merged[i] = 1
                    for k in same:
                        merged[k] = 1
                    template = FixTemplate(templates[i].action, self.select_most_abstracted_tree([templates[k].before for k in same + [i]]), self.select_most_abstracted_tree([templates[k].after for k in same + [i]]))
                    template.merge([templates[k] for k in same + [i]])
                    template.id = self.index
                    self.id2template[template.id] = template
                    self.index += 1
                    for t in template.former_templates:
                        templates.remove(self.id2template[t])
                    distances = self.add_distances(distances, template, templates)
                    templates.append(template)
                    changed = True
                    break
        
        return distances, templates

    def merge_same_structure_templates(self, distances, templates):
        changed = True
        while(changed):
            changed = False
            merged = {}
            for i in range(0, len(templates)):
                if i in merged:
                    continue
                same = []
                for j in range(i+1, len(templates)):
                    if self.is_same_structure(templates[i], templates[j]):
                        same.append(j)
                if len(same) > 0:
                    merged[i] = 1
                    for k in same:
                        merged[k] = 1
                    if templates[i].before != None:
                        newbefore_root = templates[i].before.root
                    else:
                        newbefore_root = None
                    if templates[i].after != None:
                        newafter_root = templates[i].after.root
                    else:
                        newafter_root = None
                    for k in same:
                        if newbefore_root != None:
                            newbefore_root = self.value_abstract_from_nodes(newbefore_root, templates[k].before.root)
                        if newafter_root != None:
                            newafter_root = self.value_abstract_from_nodes(newafter_root, templates[k].after.root)
                    if newbefore_root != None:
                        newbefore = TemplateTree()
                        newbefore.root = newbefore_root
                        newbefore.collect_special_nodes()
                    else:
                        newbefore = None
                    if newafter_root != None:
                        newafter = TemplateTree()
                        newafter.root = newafter_root
                        newafter.collect_special_nodes()
                    else:
                        newafter = None
                    template = FixTemplate(templates[i].action, newbefore, newafter)
                    template.merge([templates[k] for k in same + [i]])
                    template.id = self.index
                    self.id2template[template.id] = template
                    self.index += 1
                    for t in template.former_templates:
                        templates.remove(self.id2template[t])
                    distances = self.add_distances(distances, template, templates)
                    templates.append(template)
                    changed = True
                    break
        
        return distances, templates


    def is_same_structure(self, a, b):
        if not self.is_mergable(a, b):
            return False
        if (a.before == b.before or TemplateNode.value_abstract_compare(a.before.root, b.before.root)) and (a.after == b.after or TemplateNode.value_abstract_compare(a.after.root, b.after.root)):
            return True
        else:
            return False


    def is_mergable(self, a, b):
        if (a.before == None and b.before != None) or\
        (a.before != None and b.before == None) or\
        (a.after == None and b.after != None) or\
        (a.after != None and b.after == None):
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


    def mine(self, n):
        # n - Number of templates finally left
        for c in self.fix_template:
            if c != 'Insert':
                continue
            templates = self.fix_template[c]
            distances = self.initialize_distances(templates)
            print('Original:', len(templates))
            distances, templates = self.merge_same_templates(distances, templates)
            print('After merge same:', len(templates))
            distances, templates = self.merge_same_structure_templates(distances, templates)
            print('After merge same structure:', len(templates))
            self.print_info(templates)
            top_templates = self.get_topn_templates(n, templates)
            self.draw_templates(top_templates, 'figures')
            exit()
            '''
            while (len(templates) > n):
                print('Before merging: {}'.format(len(templates)))
                distances, templates = self.merge_same_templates(distances, templates)
                print('After merging: {}'.format(len(templates)))
                a, b, max_distance = self.get_max_distance(distances, templates)
                if max_distance < 0.5:
                    break
                new = self.merge(a, b)
                templates.remove(a)
                templates.remove(b)
                distances = self.add_distances(distances, new, templates)
                templates.append(new)
            self.print_info(templates)
            top_templates = self.get_topn_templates(n, templates)
            self.draw_templates(top_templates, '/data/project/ypeng/typeerror/figures')
            #a.draw(filerepo = '/data/project/ypeng/typeerror/figures', draw_instance = True)
            #b.draw(filerepo = '/data/project/ypeng/typeerror/figures', draw_instance = True)
            #new.draw(filerepo = '/data/project/ypeng/typeerror/figures', draw_instance = True)
            #print('{} templates remain after clustering.'.format(len(templates)))
            exit()
            '''



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
    


        
        
                

                





    