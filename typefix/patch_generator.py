import json
import os
import ast
from fix_template import FixTemplate, TemplateTree, Context, TemplateNode
from change_tree import ChangeTree, ChangePair
from fix_miner import ASTCompare, FixMiner
from __init__ import logger
import traceback
import random
from tqdm import tqdm



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

        return self.locations






class PatchGenerator(object):
    def __init__(self, template_file):
        self.id2template = {}
        self.load_templates(template_file)


    
    def load_templates(self, jsonfile):
        mined_info = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
        ori_num = len(self.id2template)

        for i in mined_info["templates"]:
            try:
                self.id2template[int(i)] = FixTemplate.load(mined_info["templates"][i])
                self.id2template[int(i)].concat_within_context()
                self.id2template[int(i)].clean_invalid_reference()
            except Exception as e:
                traceback.print_exc()
                with open('error_json.json', 'w', encoding = 'utf-8') as ef:
                    ef.write(json.dumps(mined_info["templates"][i], sort_keys=True, indent=4, separators=(',', ': ')))
                exit()
        
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
                

        cur_num = len(self.id2template)

        if isinstance(self.top_templates, list):
            num = len(self.top_templates)
        elif isinstance(self.top_templates, dict):
            num = {}
            for k in self.top_templates:
                num[k] = len(self.top_templates[k])
        
        print(f'Load {cur_num - ori_num} templates and {num} template trees.')
    

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
                trees = compare.build_change_tree(self.buggy_root, True, buglines, raw_buglines if raw_buglines else buglines)
                changed_stmts = []
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
                source.before_contexts = before_contexts
                source.after_contexts = after_contexts
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
                    "loc": loc
                })
            else:
                buglines = []
                for i in loc:
                    if i not in added_lines:
                        buglines.append(i)
                compare = ASTCompare()
                trees = compare.build_change_tree(self.buggy_root, True, buglines, raw_buglines if raw_buglines else buglines)
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
                    "loc": loc
                })
        
        return parsed_info

    def match_template(self, source, target):
        # Return True or False for whether source template matches target template
        # Matching before tree of source template to within context and before tree of target template
        if target.before_within != None and source.before != None:
            subtrees = TemplateNode.subtrees_match(target.before_within.root, source.before.root)
            if not subtrees or not isinstance(subtrees, dict):
                logger.debug('Before matching failed.')
                return False, None
        elif (source.before != None and target.before_within == None) or (source.before == None and target.before_within != None):
            logger.debug('Before matching failed, one is None.')
            return False, None

        # Matching before and after contexts
        if target.before_contexts != None and not Context.match(source.before_contexts, target.before_contexts):
            logger.debug('Before contexts matching failed.')
            return False, None
        if target.after_contexts != None and not Context.match(source.after_contexts, target.after_contexts):
            logger.debug('After contexts matching failed.')
            return False, None
        
        return True, subtrees

    def validate_template(self, subtrees, target):
        if target.before != None and target.after != None and target.within_context == None:
            if len(target.after.root.children['body']) != len(target.before.root.children['body']):
                return False
        
        return True

    def select_template(self, source, target):
        templates = []
        if len(target.instances) == 1:
            return templates
        success, subtrees = self.match_template(source, target)
        if success:
            for i in target.child_templates:
                templates += self.select_template(source, self.id2template[i])
            if len(templates) == 0 and self.validate_template(subtrees, target):
                templates.append(target)
        return templates

    def group_templates(self, templates):
        new_templates = []
        for t in templates:
            found = False
            for k in new_templates:
                if FixTemplate.compare(t, k):
                    found = True
                    break
            if not found:
                new_templates.append(t)
        templates = new_templates
        distances = {}
        for i, t in enumerate(templates):
            if t not in distances:
                distances[t] = {}
            for j in range(i + 1, len(templates)):
                if templates[j] not in distances:
                    distances[templates[j]] = {}
                distances[t][templates[j]] = TemplateTree.get_distance(t.before_within, templates[j].before_within)
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

    def rank_templates(self, templates, mode = 'abstract_score'):
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
            nummap = {}
            for t in templates:
                num = len(t.instances)
                if num not in nummap:
                    nummap[num] = []
                nummap[num].append(t)
            
            for i in nummap:
                sortedlist = sorted(nummap[i], key = lambda item: item.before_within.get_node_num() if item.before_within else 0, reverse = True)
                nummap[i] = sortedlist

            sortedmap = sorted(nummap.items(), key = lambda item: item[0], reverse = True)
            rankedlist = []
            for i in sortedmap:
                rankedlist += i[1]
        elif mode == 'abstract_score':
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
                    group = newgroup
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
        
        return rankedlist

    def select_templates(self, parsed_info):
        if len(parsed_info) == 0:
            raise ValueError('Cannot get parsed location info.')
        for i in parsed_info:
            selected_templates = {}
            source = i["source"]
            # Only Add templates will be matched
            if i['all_added']:
                for t in self.top_templates['Add']:
                    selected_templates['Add'] = self.select_template(source, self.id2template[t])
                selected_templates['Add'] = self.rank_templates(selected_templates['Add'])
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

    def print_matched_nodes(self, nodes, parsed_info):
        self.draw_location(parsed_info, 'figures2')
        for i, l in enumerate(nodes):
            print('Matched Case #{}'.format(i))
            print([(n.id, n.type) for n in l])


    def implement_templates(self, parsed_info):
        for p in parsed_info:
            templates = p["selected_templates"]
            for k in templates:
                for group in templates[k]:
                    for t in group:
                        matched_subtrees = TemplateNode.subtrees_match_all(t, p["source"])



    def print_info(self, parsed_info):
        for p in parsed_info:
            print('Parsed Info for {} at line #{}'.format(self.buggy_file, p["buglines"]))
            print('Selected Templates:')
            for k in p["selected_templates"]:
                print(k, '{} groups:'.format(len(p["selected_templates"][k])))
                for g in p["selected_templates"][k]:
                    print([t.id for t in g])

    def run_one(self, buggy_file, buglines = None, added = None):
        os.system('rm -rf figures2/*')
        logger.info('Generating patches for buggy file {}'.format(buggy_file))
        self.buggy_file = buggy_file
        try:
            self.buggy_root = ast.parse(open(self.buggy_file, "r", encoding = "utf-8").read())
        except Exception as e:
            logger.error('Cannot parse buggy file {}, reason: {}, skipped.'.format(self.buggy_file, e))
            return None
        self.buglines = buglines
        self.added = added
        if self.buglines == None:
            pass
        parsed_info = self.parse_locations()
        parsed_info = self.select_templates(parsed_info)
        self.print_info(parsed_info)

    def run_all(self, metafile, benchmark_path, benchmark = 'bugsinpy'):
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
                if r != 'requests/requests-3179':
                    continue
                path = os.path.join(benchmark_path, r)
                for f in metadata[r]['code_files']:
                    if not f.endswith('.py'):
                        continue
                    buggy_file = os.path.join(path, f)
                    patch_file = self.run_one(buggy_file, buglines = metadata[r]['buglines'][f], added = metadata[r]['added'][f])

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
    #generator = PatchGenerator('/Users/py/workspace/typefix/mined_templates.json')
    generator = PatchGenerator('/Users/py/workspace/typefix/large_mined_templates.json')
    
    generator.draw_templates('figures', templates = [generator.id2template[t] for t in generator.top_templates['Insert']])
    #print(generator.id2template[2889].instances[0])
    #generator.run_all('all_bug_info_bugsinpy.json', '/Users/py/workspace/typefix/benchmarks/bugsinpy/info')
    #generator.test_all('combined_commits_contents.json')
    #generator.run_one('/Users/py/workspace/typefix/TypeErrorFix/benchmarks/typebugs/airflow/airflow-4674/airflow/configuration.py', buglines = [263, 264, 267, 269], added = [False, False, False, False])
    #generator.run_all('all_bug_info_typebugs.json', '/Users/py/workspace/typefix/TypeErrorFix/benchmarks/typebugs', benchmark = 'typebugs')
