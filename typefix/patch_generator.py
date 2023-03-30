import json
import os
import ast
from fix_template import FixTemplate, TemplateTree, Context, TemplateNode
from ast_operation import ASTNodeGenerator, ASTVisitor, ASTTransformer
from change_tree import ChangeTree, ChangePair
from fix_miner import ASTCompare, FixMiner
from bug_locator import FunctionLocator
from __init__ import logger
import traceback
import random
from tqdm import tqdm
from copy import deepcopy


class PatchGenerator(object):
    def __init__(self, template_file, remove_comment = False):
        self.id2template = {}
        self.load_templates(template_file, min_instance_num = 5)
        self.format_templates()
        self.remove_comment = remove_comment
        self.benchmark = 'bugsinpy'


    
    def load_templates(self, jsonfile, min_instance_num = 5):
        mined_info = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
        ori_num = len(self.id2template)

        for i in mined_info["templates"]:
            try:
                self.id2template[int(i)] = FixTemplate.load(mined_info["templates"][i])
                self.id2template[int(i)].concat_within_context()
                self.id2template[int(i)].clean_invalid_reference()
            except Exception as e:
                #traceback.print_exc()
                #with open('error_json.json', 'w', encoding = 'utf-8') as ef:
                #    ef.write(json.dumps(mined_info["templates"][i], sort_keys=True, indent=4, separators=(',', ': ')))
                continue
        
        if isinstance(mined_info["mined"], list):
            self.top_templates = []
            instance_num = {}
            for i in mined_info["mined"]:
                num = len(self.id2template[i].instances)
                if num not in instance_num:
                    instance_num[num] = [i]
                else:
                    instance_num[num].append(i)
            sorted_instance_num = sorted(instance_num.items(), key = lambda item: item[0], reverse = True)
            for s in sorted_instance_num:
                self.top_templates += s[1]
        elif isinstance(mined_info["mined"], dict):
            self.top_templates = {}
            for k in mined_info["mined"]:
                self.top_templates[k] = []
                instance_num = {}
                for i in mined_info["mined"][k]:
                    num = len(self.id2template[i].instances)
                    if num not in instance_num:
                        instance_num[num] = [i]
                    else:
                        instance_num[num].append(i)
                sorted_instance_num = sorted(instance_num.items(), key = lambda item: item[0], reverse = True)
                for s in sorted_instance_num:
                    self.top_templates[k] += s[1]

        # Reduce templates
        if min_instance_num != None:
            for k in self.top_templates:
                removed = []
                for t in self.top_templates[k]:
                    if len(self.id2template[t].instances) < min_instance_num:
                        removed.append(t)
                for r in removed:
                    self.top_templates[k].remove(r)
                    children = self.id2template[r].get_all_child_templates(self.id2template)
                    for c in children:
                        del self.id2template[c]
                    del self.id2template[r]
                self.reduce_templates([self.id2template[j] for j in self.top_templates[k]], min_instance_num = min_instance_num)
            
                

        cur_num = len(self.id2template)

        if isinstance(self.top_templates, list):
            num = len(self.top_templates)
        elif isinstance(self.top_templates, dict):
            num = {}
            for k in self.top_templates:
                num[k] = len(self.top_templates[k])
        
        print(f'Load {cur_num - ori_num} templates and {num} template trees.')
    
    def reduce_templates(self, templates, min_instance_num = 10):
        for t in templates:
            removed = []
            check = []
            for i in t.child_templates:
                if i not in self.id2template:
                    removed.append(i)
                elif len(self.id2template[i].instances) < min_instance_num:
                    removed.append(i)
                else:
                    check.append(self.id2template[i])
            for r in removed:
                t.child_templates.remove(r)
                children = self.id2template[r].get_all_child_templates(self.id2template)
                for c in children:
                    del self.id2template[c]
                del self.id2template[r]
            self.reduce_templates(check)

    def format_templates(self):
        # Change all End_Expr in after trees to Expr cause these two make no difference in patch generation
        for i in self.id2template:
            if self.id2template[i].after:
                self.id2template[i].after.replace('End_Expr', 'Expr', change_base_type = True, change_value = True)
                self.id2template[i].after.replace('Identifier', 'Expr', change_base_type = True, change_value = True)


    def save_templates(self, filename):
        mined_info = {"templates": {}, "mined": {}}
        for i in self.id2template:
            self.id2template[i].before_within = None
            mined_info["templates"][i] = self.id2template[i].dump()
        
        for k in self.top_templates:
            mined_info["mined"][k] = self.top_templates[k]
        
        with open(filename, 'w', encoding = 'utf-8') as f:
            f.write(json.dumps(mined_info, sort_keys=True, indent=4, separators=(',', ': ')))

    def draw_templates(self, filerepo, templates = None):
        if templates == None:
            for i in self.id2template:
                self.id2template[i].draw(self.id2template, filerepo = filerepo, draw_instance = True, draw_contexts = True, dump_attributes = False)
        else:
            for t in templates:
                self.id2template[t.id].draw(self.id2template, filerepo = filerepo, draw_instance = True, draw_contexts = True, dump_attributes = False)
    

    def draw_location(self, parsed_info, filerepo):
        if parsed_info['before_tree']:
            parsed_info['before_tree'].draw('before_tree', filerepo = filerepo)
        
        if parsed_info['before_contexts']:
            parsed_info['before_contexts'].context_tree.draw('before_contexts', filerepo = filerepo)

        if parsed_info['after_contexts']:
            parsed_info['after_contexts'].context_tree.draw('after_contexts', filerepo = filerepo)


    def locate_bug(self):
        pass

    def get_top_templates(self):
        top_templates = {}
        for k in self.top_templates:
            num = {}
            top_templates[k] = []
            for i in self.top_templates[k]:
                child_ids = self.id2template[i].get_child_template_ids(self.id2template)
                for j in child_ids + [i]:
                    instance_num = len(self.id2template[j].instances)
                    if instance_num not in num:
                        num[instance_num] = []
                    num[instance_num].append(j)
            sorted_num = sorted(num.items(), key = lambda item: item[0], reverse = True)
            for s in sorted_num:
                top_templates[k] += s[1]
        
        with open("top_templates.json", "w", encoding = "utf-8") as tf:
            tf.write(json.dumps(top_templates, indent=4, separators=(',', ': ')))






    def parse_locations(self, remove_import = False, raw_buglines = None):
        if self.buglines == None:
            raise ValueError('Missing bug location before parsing locations.')
        parsed_info = []
        # Split multiple lines into single locations according to function bodies
        visitor = ASTVisitor(self.buglines, remove_import = remove_import)
        locations = visitor.run(self.buggy_root)
        added = []
        for loc in locations:
            add = []
            for l in loc:
                add.append(self.added[self.buglines.index(l)])
            added.append(add)
        
        # Parse each location into a single before tree
        for index, loc in enumerate(locations):
            add = added[index]
            added_lines = []      
            for index, a in enumerate(add):
                if a:
                    added_lines.append(loc[index])
            if len(added_lines) == len(loc):
                all_added = True
            else:
                all_added = False
            if all_added:
                buglines = loc
                compare = ASTCompare()
                trees = compare.build_change_tree(self.buggy_root, True, buglines, raw_buglines if raw_buglines else buglines, always_add = True)
                changed_stmts = []
                linemap = {}
                for t in trees:
                    for s in t.uppest_totally_changed_stmts:
                        changed_stmts.append(s)
                        if s.lineno not in linemap:
                            linemap[s.lineno] = []
                        linemap[s.lineno].append(len(changed_stmts) - 1)
                    for s in t.deepest_partially_changed_stmts:
                        changed_stmts.append(s)
                        if s.lineno not in linemap:
                            linemap[s.lineno] = []
                        linemap[s.lineno].append(len(changed_stmts) - 1)
                orders = sorted(linemap.items(), key = lambda item:item[0])
                locs = []
                for line, loc in orders:
                    locs += loc
                new_changed_stmts = []
                for i in locs:
                    new_changed_stmts.append(changed_stmts[i])
                changed_stmts = new_changed_stmts
                if len(changed_stmts) > 0:
                    parent_ast = changed_stmts[0].parent.node
                    parent_relation = changed_stmts[0].parent_relation
                    body = getattr(changed_stmts[0].parent.node, changed_stmts[0].parent_relation)
                    if not self.remove_comment:
                        parent_index = body.index(changed_stmts[0].node)
                    else:
                        temp_index = body.index(changed_stmts[0].node)
                        parent_index = temp_index
                        for n in body[:temp_index]:
                            if type(n) == ast.Expr and type(n.value) == ast.Constant and isinstance(n.value.value, str):
                                parent_index -= 1
                else:
                    locator = FunctionLocator()
                    parent_ast, parent_index, parent_relation = locator.run(self.buggy_root, buglines, find_body_index = True, remove_comment = self.remove_comment)
                    if type(parent_ast) == ast.Module:
                        logger.debug('Adding global statements.')
                        continue
                before_stmts, after_stmts = ChangeTree.build_before_and_after_contexts(changed_stmts)
                after_stmts = changed_stmts + after_stmts
                before_contexts = []
                after_contexts = []
                for s in before_stmts:
                    temp_tree = TemplateTree()
                    temp_tree.build([s])
                    before_contexts.append(temp_tree)
                for s in after_stmts:
                    temp_tree = TemplateTree()
                    temp_tree.build([s])
                    after_contexts.append(temp_tree)
                before_contexts = Context.build_external_context(before_contexts, 'Before')
                after_contexts = Context.build_external_context(after_contexts, 'After')
                source = FixTemplate(None, None, None)
                source.before_contexts = before_contexts
                source.after_contexts = after_contexts
                source.id = 0
                source.set_node_ids()
                source.cal_self_reference()
                parsed_info.append({
                    "change_stmts": [],
                    "source": source,
                    "before_tree": None,
                    "before_contexts": before_contexts,
                    "after_contexts": after_contexts,
                    "all_added": all_added,
                    "buglines": buglines,
                    "added": add,
                    "loc": loc,
                    "parent": [parent_ast, parent_relation, parent_index]
                })
            else:
                buglines = []
                for i in loc:
                    if i not in added_lines:
                        buglines.append(i)
                compare = ASTCompare()
                trees = compare.build_change_tree(self.buggy_root, True, buglines, raw_buglines if raw_buglines else buglines, always_add = True)
                changed_stmts = []  
                for t in trees:
                    changed_stmts += t.uppest_totally_changed_stmts
                    for k in t.deepest_partially_changed_stmts:
                        k.partial = True
                    changed_stmts += t.deepest_partially_changed_stmts
                linemap = {}
                for s in changed_stmts:
                    if s.lineno not in linemap:
                        linemap[s.lineno] = [s]
                    else:
                        linemap[s.lineno].append(s)
                changed_stmts = []
                sorted_linemap = sorted(linemap.items(), key = lambda item: item[0])
                for s in sorted_linemap:
                    changed_stmts += s[1]
                before_tree = TemplateTree()
                before_tree.build(changed_stmts, record_astnode = True)
                TemplateTree.assign_dfsid(before_tree.root)
                miner = FixMiner()
                before_contexts, after_contexts = miner.build_before_and_after_contexts(changed_stmts, before_tree, None)
                source = FixTemplate(None, before_tree, None)
                source.before_contexts = before_contexts
                source.after_contexts = after_contexts
                source.id = 0
                source.set_node_ids()
                source.cal_self_reference()
                parsed_info.append({
                    "change_stmts": changed_stmts,
                    "source": source,
                    "before_tree": before_tree,
                    "before_contexts": before_contexts,
                    "after_contexts": after_contexts,
                    "all_added": all_added,
                    "buglines": buglines,
                    "added": add,
                    "loc": loc,
                    "parent": None
                })
        
        return parsed_info

    def match_template(self, source, target, added = False):
        # Return True or False for whether source template matches target template
        # Matching before tree of source template to within context and before tree of target template
        if not added:
            if target.before_within != None and source.before != None:
                if target.before_within.cal_abstract_ratio() == 1.0:
                    if len(source.before.root.children['body']) == 1 and len(source.before.root.children['body']) > len(target.before_within.root.children['body']):
                        return False, None
                    elif len(source.before.root.children['body']) > 1 and len(source.before.root.children['body']) != len(target.before_within.root.children['body']):
                        return False, None
                if len(target.before_within.root.children['body']) < len(source.before.root.children['body']):
                    
                    return False, None
                subtrees = TemplateNode.subtrees_match(target.before_within.root, source.before.root)
                if not subtrees or not isinstance(subtrees, dict):
                    #logger.debug('Before matching failed.')
                    return False, None
            elif (source.before != None and target.before_within == None) or (source.before == None and target.before_within != None):
                #logger.debug('Before matching failed, one is None.')
                return False, None

        # Matching before and after contexts
        if target.before_contexts != None and not Context.match(source.before_contexts, target.before_contexts):
            #logger.debug('Before contexts matching failed.')
            return False, None
        if target.after_contexts != None and not Context.match(source.after_contexts, target.after_contexts):
            #logger.debug('After contexts matching failed.')
            return False, None
        
        if not added:
            return True, subtrees
        else:
            return True, None

    def validate_template(self, subtrees, target):
        if target.before != None and target.after != None and target.within_context == None:
            if len(target.after.root.children['body']) != len(target.before.root.children['body']) and target.action != 'Insert':
                return False
        if target.after != None and target.action == 'Insert':
            all_reference = True
            for n in target.after.root.children['body']:
                if len(n.refer_to) > 1:
                    return False
                if n.type != 'Reference':
                    all_reference = False
                    break
            if all_reference:
                return False
            all_referred = True
            for n in target.after.root.children['body']:
                children = n.get_all_children()
                found = False
                for n in children:
                    if n.type == 'Reference':
                        if len(n.refer_to) > 1:
                            return False
                        found = True
                        break
                if not found:
                    all_referred = False
            if not all_referred:
                return False
        
        return True

    def select_template(self, source, target, added = False):
        templates = []
        if len(target.instances) == 1:
            return templates
        if not added:
            success, subtrees = self.match_template(source, target)
            if success:
                for i in target.child_templates:
                    if TemplateTree.compare(self.id2template[i].before_within, target.before_within) and target.after and self.id2template[i].after and TemplateNode.value_abstract_compare(self.id2template[i].after.root, target.after.root):
                        if target not in templates:
                            templates.append(target)
                        continue
                    templates += self.select_template(source, self.id2template[i], added = added)
                if len(templates) == 0 and self.validate_template(subtrees, target):
                    templates.append(target)
        else:
            if target.before_within != None:
                return templates
            success, subtrees = self.match_template(source, target, added = True)
            if success:
                if len(target.child_templates) > 0:
                    for i in target.child_templates:
                        templates += self.select_template(source, self.id2template[i], added = added)
                else:
                    templates.append(target)

        return templates

    def group_templates(self, templates, added = False):
        new_templates = []
        for t in templates:
            found = False
            for k in new_templates:
                if FixTemplate.compare(t, k):
                    found = True
                    break
            if not found:
                new_templates.append(t)
        removed = []
        for t in new_templates:
            for k in new_templates:
                if t != k and FixTemplate.is_include(t, k):
                    removed.append(t)
        for r in removed:
            if r in new_templates:
                new_templates.remove(r)
        templates = new_templates
        if added:
            groups = []
            selected = {}
            for i, t in enumerate(templates):
                if t in selected:
                    continue
                group = [t]
                selected[t] = 1
                for j in range(i + 1, len(templates)):
                    if templates[j] in selected:
                        continue
                    if TemplateTree.root_node_compare(t.after, templates[j].after):
                        selected[templates[j]] = 1
                        group.append(templates[j])
                groups.append(group)
            return groups
        distances = {}
        for i, t in enumerate(templates):
            if t not in distances:
                distances[t] = {}
            for j in range(i + 1, len(templates)):
                if templates[j] not in distances:
                    distances[templates[j]] = {}
                if t.before_within and templates[j].before_within:
                    distances[t][templates[j]] = TemplateTree.get_distance(t.before_within, templates[j].before_within)
                else:
                    distances[t][templates[j]] = 1.0
                distances[templates[j]][t] = distances[t][templates[j]]
        groups = []
        selected = {}
        for t in templates:
            if t in selected:
                continue
            group = []
            for k in templates:
                if k == t or k in selected:
                    continue
                if distances[t][k] == 1.0:
                    selected[k] = 1
                    group.append(k)
            if len(group) > 0:
                selected[t] = 1
                group.append(t)
                groups.append(group)
        
        for t in templates:
            if t not in selected:
                groups.append([t])
        
        return groups

    def rank_templates(self, templates, mode = 'frequency', added = False, cutting_threshold = 5):
        if mode == 'nodenum':
            nummap = {}
            for t in templates:
                if t.before_within:
                    num = t.before_within.get_node_num()
                else:
                    num = 0
                if num not in nummap:
                    nummap[num] = []
                nummap[num].append(t)
            
            for i in nummap:
                sortedlist = sorted(nummap[i], key = lambda item: len(item.instances), reverse = True)
                nummap[i] = sortedlist
            
            sortedmap = sorted(nummap.items(), key = lambda item: item[0], reverse = True)
            rankedlist = []
            for i in sortedmap:
                rankedlist += i[1]
        elif mode == 'frequency':
            new_templates = []
            for group in templates:
                if len(group) > 1:
                    newgroup = []
                    scoremap = {}
                    for t in group:
                        score = len(t.instances)
                        if score not in scoremap:
                            scoremap[score] = []
                        scoremap[score].append(t)
                    sortedmap = sorted(scoremap.items(), key = lambda item: item[0], reverse = True)
                    for i in sortedmap:
                        newgroup += i[1]
                    new_templates.append(newgroup)
                else:
                    new_templates.append(group)
            templates = new_templates
            
            if not added:
                nummap = {}
                for group in templates:
                    ratio = group[0].before_within.cal_abstract_ratio() if group[0].before_within else 0.0
                    if ratio not in nummap:
                        nummap[ratio] = []
                    nummap[ratio].append(group)
                sortedmap = sorted(nummap.items(), key = lambda item: item[0])
                rankedlist= []
                for i in sortedmap:
                    rankedlist += i[1]
            else:
                nummap = {}
                for group in templates:
                    ratio = group[0].after.get_node_num()
                    if ratio not in nummap:
                        nummap[ratio] = []
                    nummap[ratio].append(group)
                sortedmap = sorted(nummap.items(), key = lambda item: item[0], reverse = True)
                rankedlist= []
                for i in sortedmap:
                    rankedlist += i[1]
        elif mode == 'abstract_score':
            new_templates = []
            for group in templates:
                if len(group) > 1:
                    newgroup = []
                    scoremap = {}
                    for t in group:
                        if t.after:
                            score = t.after.cal_abstract_score()
                        else:
                            score = 0
                        if score not in scoremap:
                            scoremap[score] = []
                        scoremap[score].append(t)
                    sortedmap = sorted(scoremap.items(), key = lambda item: item[0])
                    for i in sortedmap:
                        newgroup += i[1]
                    new_templates.append(newgroup)
                else:
                    new_templates.append(group)
            templates = new_templates
            nummap = {}
            for group in templates:
                max_num = -999
                for t in group:
                    if len(t.instances) > max_num:
                        max_num = len(t.instances)
                nummap[max_num] = group
            
            sortedmap = sorted(nummap.items(), key = lambda item: item[0], reverse = True)
            rankedlist= []
            for i in sortedmap:
                rankedlist.append(i[1])

        if cutting_threshold != None:
            newlist = []
            for l in rankedlist:
                newlist.append(l[:cutting_threshold * 2])
            if not added:
                rankedlist = newlist[:cutting_threshold * 2]
            else:
                rankedlist = newlist
        
        return rankedlist

    def select_templates(self, parsed_info):
        if len(parsed_info) == 0:
            raise ValueError('Cannot get parsed location info.')
        for i in parsed_info:
            selected_templates = {}
            source = i["source"]
            # Only Add templates will be matched
            if i['all_added']:
                selected_templates['Add'] = []
                for t in self.top_templates['Add']:
                    if self.id2template[t].before_within == None:
                        selected_templates['Add'] += self.select_template(source, self.id2template[t], added = True)
                selected_templates['Add'] = self.group_templates(selected_templates['Add'], added = True)
                selected_templates['Add'] = self.rank_templates(selected_templates['Add'], added = True)
            else:
                for k in self.top_templates:
                    selected_templates[k] = []
                    for t in self.top_templates[k]:
                        selected_templates[k] += self.select_template(source, self.id2template[t])
                for k in selected_templates:
                    selected_templates[k] = self.group_templates(selected_templates[k])
                    selected_templates[k] = self.rank_templates(selected_templates[k])
                
            i["selected_templates"] = selected_templates
        return parsed_info

    def print_matched_nodes(self, nodes, nodemaps, parsed_info):
        #os.system('rm -rf figures2/*')
        logger.debug('All matched cases:')
        #self.draw_location(parsed_info, 'figures2')
        for i, l in enumerate(nodes):
            logger.debug('Matched Case #{}'.format(i))
            logger.debug('    Matched nodes:{}'.format([(n.id, n.type) for n in l]))
            string = '    Matched node map:'
            for m in nodemaps[i]:
                string += f'{(m.id, m.type)}->{(nodemaps[i][m].id, nodemaps[i][m].type)} '
            logger.debug(string)

    def print_ast_changes(self, ori2news):
        logger.debug('AST changes for all matched cases:')
        for i, ori2new in enumerate(ori2news):
            logger.debug(f'Case #{i}:')
            for o in ori2new:
                logger.debug('    From: {} to {}'.format(ast.dump(o), ast.dump(ori2new[o]) if ori2new[o] else None))
        
    def dump_patches(self, patches, filerepo):
        for i, p in enumerate(patches):
            with open(os.path.join(filerepo, 'Patch_{}_from_{}.py'.format(i, patches[p][1])), 'w', encoding = 'utf-8') as pf:
                pf.write(ast.unparse(patches[p][0]))

        
            
    def implement_template(self, p, t):
        patches = {}
        index = 0
        if t.before_within != None:
            matched_subtrees, nodemaps = TemplateNode.subtrees_match_all(t.before_within.root, p["source"].before.root)
            if len(matched_subtrees) > 20:
                logger.debug('Too many matched cases, select the first 20 cases.')
                matched_subtrees = matched_subtrees[:20]
                nodemaps = nodemaps[:20]
            self.print_matched_nodes(matched_subtrees, nodemaps, p)
            ori2news = []
            opnodes = []
            for i, sub in enumerate(matched_subtrees):
                try:
                    ast_generator = ASTNodeGenerator(sub, nodemaps[i], t)
                    ori2new, opnode = ast_generator.gen()
                    ori2news += ori2new
                    opnodes.append(opnode)
                except Exception as e:
                    logger.debug(f'Patch generation failed, reason: {e}, skipped.')
        else:
            ori2news = []
            opnodes = []
            try:
                if int(p["added"][0]) == 1:
                    after = False
                else:
                    after = True
                ast_generator = ASTNodeGenerator(None, None, t, parent = p["parent"])
                ori2new, opnode = ast_generator.gen(after = after)
                ori2news += ori2new
                opnodes.append(opnode)
            except Exception as e:
                traceback.print_exc()
                logger.debug(f'Patch generation failed, reason: {e}, skipped.')
        #self.print_ast_changes(ori2news)
        for i, ori2new in enumerate(ori2news):
            logger.debug(f'Applying AST change #{i}')
            transformer = ASTTransformer(ori2new, opnodes[i], remove_comment = self.remove_comment)
            source, new_root = transformer.run(self.buggy_root)
            if source != None and source != self.formatted_buggy_source:
                #patches[source] = [new_root, t.id, t.action]
                patches[index] = [new_root, t.id, t.action, source]
                index += 1
        return patches




    def implement_templates(self, parsed_info):
        patches = {}
        index = 0
        for p in parsed_info:
            #if 1838 not in p["buglines"]:
            #    continue
            templates = p["selected_templates"]
            for k in templates:
                #if k != 'Add':
                #    continue
                for group in templates[k]:
                    for t in group:
                        #if t.id != 13226:
                        #    continue
                        logger.debug(f'-----------------Implementing template #{t.id}----------------')
                        if t.before_within != None:
                            matched_subtrees, nodemaps = TemplateNode.subtrees_match_all(t.before_within.root, p["source"].before.root)
                            self.print_matched_nodes(matched_subtrees, nodemaps, p)
                            ori2news = []
                            opnodes = []
                            for i, sub in enumerate(matched_subtrees):
                                try:
                                    ast_generator = ASTNodeGenerator(sub, nodemaps[i], t)
                                    ori2new, opnode = ast_generator.gen()
                                    ori2news += ori2new
                                    opnodes.append(opnode)
                                except Exception as e:
                                    logger.debug(f'Patch generation failed, reason: {e}, skipped.')
                                    continue
                        else:
                            ori2news = []
                            opnodes = []
                            try:
                                if int(p["added"][0]) == 1:
                                    after = False
                                else:
                                    after = True
                                ast_generator = ASTNodeGenerator(None, None, t, parent = p["parent"])
                                ori2new, opnode = ast_generator.gen(after = after)
                                ori2news += ori2new
                                opnodes.append(opnode)
                            except Exception as e:
                                traceback.print_exc()
                                logger.debug(f'Patch generation failed, reason: {e}, skipped.')
                                continue
                        #self.print_ast_changes(ori2news)
                        cur_num = 0
                        for i, ori2new in enumerate(ori2news):
                            if cur_num > 20:
                                logger.debug('Too many patches generated, select the first 20.')
                                break
                            logger.debug(f'Applying AST change #{i}')
                            transformer = ASTTransformer(ori2new, opnodes[i], remove_comment = self.remove_comment)
                            source, new_root = transformer.run(self.buggy_root)
                            if source != None and source != self.formatted_buggy_source:
                                #patches[source] = [new_root, t.id, t.action]
                                patches[index] = [new_root, t.id, t.action, source]
                                index += 1
                                if 'VALUE_MASK VALUE_MASK VALUE_MASK' in source:
                                    newsource = source.replace('VALUE_MASK VALUE_MASK VALUE_MASK', 'VALUE_MASK')
                                    patches[index] = [new_root, t.id, t.action, newsource]
                                    index += 1
                                cur_num += 1
        self.dump_patches(patches, 'patches/{}'.format(self.benchmark))
        return patches



    def print_info(self, parsed_info):
        logger.debug('Selected Templates:')
        for p in parsed_info:
            logger.debug('{} at line #{}'.format(self.buggy_file, p["buglines"]))
            for k in p["selected_templates"]:
                logger.debug('{} {} groups:'.format(k, len(p["selected_templates"][k])))
                for g in p["selected_templates"][k]:
                    logger.debug("{}".format([(t.id, round(t.before_within.cal_abstract_ratio(), 2) if t.before_within else 0, len(t.instances)) for t in g]))

    def run_one(self, buggy_file, buglines = None, added = None):
        #os.system('rm -rf figures2/*')
        logger.info('Generating patches for buggy file {}'.format(buggy_file))
        self.buggy_file = buggy_file
        try:
            self.buggy_source = open(self.buggy_file, "r", encoding = "utf-8").read()
            self.buggy_root = ast.parse(self.buggy_source)
            self.formatted_buggy_source = ast.unparse(self.buggy_root)
        except Exception as e:
            logger.error('Cannot parse buggy file {}, reason: {}, skipped.'.format(self.buggy_file, e))
            return None
        self.buglines = buglines
        self.added = added
        if self.buglines == None:
            pass
        parsed_info = self.parse_locations()
        #for p in parsed_info:
        #    self.draw_location(p, 'figures2')
        
        if len(parsed_info) > 0:
            parsed_info = self.select_templates(parsed_info)
            self.print_info(parsed_info)
            patches = self.implement_templates(parsed_info)
            return patches
        else:
            return {}
        

    def run_all(self, metafile, benchmark_path, benchmark = 'bugsinpy'):
        self.benchmark = benchmark
        metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
        if benchmark == 'bugsinpy':
            for r in metadata:
                for i in metadata[r]:
                    path = os.path.join(benchmark_path, r, f'{r}-{i}')
                    for f in metadata[r][i]['code_files']:
                        if not f.endswith('.py'):
                            continue
                        buggy_file = os.path.join(path, f)
                        patch_file = self.run_one(buggy_file, buglines = metadata[r][i]['buglines'][f], added = metadata[r][i]['added'][f])
                        if patch_file == None:
                            logger.error('Cannot generate patch files for buggy file {}.'.format(buggy_file))
                            continue
        elif benchmark == 'typebugs':
            for r in metadata:
                if r != 'numpy/numpy-9999':
                    continue
                path = os.path.join(benchmark_path, r)
                for f in metadata[r]['code_files']:
                    if not f.endswith('.py'):
                        continue
                    buggy_file = os.path.join(path, f)
                    patches = self.run_one(buggy_file, buglines = metadata[r]['buglines'][f], added = metadata[r]['added'][f])

    def test_one(self, metadata, template):
        for index, i in enumerate(template.instances):
            if isinstance(i, ChangePair):
                i = i.metadata
            commit = metadata[i['repo']][i['commit']][i['file']][i['loc']]
            for c in commit:
                if c['content'] == i['content']:
                    lines = c['lines']
                    break
            buggy_file = metadata[i['repo']][i['commit']][i['file']]['files'][0]
            before_index = lines[0]
            before_change_lines = []
            raw_before_change_lines = []
            content = i['content']
            for line in content.splitlines():
                if not line.startswith('-') and not line.startswith('+'):
                    before_index += 1
                elif line.startswith('-'):
                    if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                        before_change_lines.append(before_index)
                    raw_before_change_lines.append(before_index)
                    before_index += 1
            if before_index != lines[0] + lines[1]:
                logger.error('Line information does not match the change content.')
                return False
            logger.info('Generating patches for buggy file {}'.format(buggy_file))
            self.buggy_file = buggy_file
            try:
                self.buggy_root = ast.parse(open(self.buggy_file, "r", encoding = "utf-8").read())
            except Exception as e:
                logger.error('Cannot parse buggy file {}, reason: {}, skipped.'.format(self.buggy_file, e))
                return None
            self.buglines = before_change_lines
            self.added = [False for i in self.buglines]
            parsed_info = self.parse_locations(remove_import = True, raw_buglines = raw_before_change_lines)
            if len(parsed_info) > 1:
                logger.info('Skip inter-context instances, buglines: {}, parsed_info: {}'.format(self.buglines, parsed_info))
                return True
            for p in parsed_info:
                source = FixTemplate(None, p['before_tree'], None)
                source.before_contexts = p['before_contexts']
                source.after_contexts = p['after_contexts']
                source.cal_self_reference()
                if not self.match_template(source, template)[0]:
                    self.draw_location(p, 'figures2')
                    template.draw(self.id2template, filerepo = 'figures2', draw_instance = True, draw_contexts = True, dump_attributes = False)
                    print(self.buglines)
                    print(p)
                    logger.error('Instance #{} in template #{} matching failed.'.format(index, template.id))
                    return False
        
        return True
            

    def test_all(self, metafile):
        metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
        os.system('rm -rf figures2/*')
        failed = []
        for i in tqdm(self.id2template, desc = 'Testing Templates'):
            #if i in [1257, 3196, 3490]:
            #    continue
            #if i != 3490:
            #    continue
            success = self.test_one(metadata, self.id2template[i])
            if not success:
                failed.append(i)
                print('Test Failed.')
        print(failed)




        



if __name__ == "__main__":
    generator = PatchGenerator('/Users/py/workspace/typefix/large_mined_templates.json')
    #generator = PatchGenerator('/Users/py/workspace/typefix/large_min5_templates.json')
    #generator.get_top_templates()
    #generator.save_templates('large_min5_templates.json')
    
    #generator.draw_templates('figures3')
    #print(generator.id2template[2889].instances[0])
    generator.run_all('all_bug_info_bugsinpy.json', 'benchmarks/bugsinpy')
    #generator.test_all('combined_commits_contents.json')
    #generator.run_one('/Users/py/workspace/typefix/TypeErrorFix/benchmarks/typebugs/airflow/airflow-4674/airflow/configuration.py', buglines = [263, 264, 267, 269], added = [False, False, False, False])
    generator.run_all('all_bug_info_typebugs.json', 'benchmarks/typebugs', benchmark = 'typebugs')
