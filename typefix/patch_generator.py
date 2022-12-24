import json
import os
import ast
from fix_template import FixTemplate, TemplateTree, Context, TemplateNode
from change_tree import ChangeTree, ChangePair
from fix_miner import ASTCompare, FixMiner
from __init__ import logger
import traceback
import random



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
        
        for i in change:
            self.locations[i] = change[i]

        return self.locations






class PatchGenerator(object):
    def __init__(self, template_file):
        self.id2template = {}

        if isinstance(template_file, str):
            self.top_templates = self.load_templates(template_file)
        elif isinstance(template_file, dict):
            self.top_templates = {}
            for k in template_file:
                self.top_templates[k] = self.load_templates(template_file[k])


    
    def load_templates(self, jsonfile):
        mined_info = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
        instance_num = {}
        top_templates = []
        ori_num = len(self.id2template)

        for i in mined_info["templates"]:
            try:
                self.id2template[int(i)] = FixTemplate.load(mined_info["templates"][i])
                self.id2template[int(i)].concat_within_context()
            except Exception as e:
                traceback.print_exc()
                with open('error_json.json', 'w', encoding = 'utf-8') as ef:
                    ef.write(json.dumps(mined_info["templates"][i], sort_keys=True, indent=4, separators=(',', ': ')))
                exit()

        for i in mined_info["mined"]:
            num = len(self.id2template[i].instances)
            if num not in instance_num:
                instance_num[num] = [i]
            else:
                instance_num[num].append(i)
        sorted_instance_num = sorted(instance_num.items(), key = lambda item: item[0])
        for s in sorted_instance_num:
            top_templates += s[1]

        cur_num = len(self.id2template)
        
        print(f'Load {cur_num - ori_num} templates and {len(top_templates)} template trees.')
        
        return top_templates
    

    def draw_templates(self, filerepo):
        for i in self.id2template:
            self.id2template[i].draw(self.id2template, filerepo = filerepo, draw_instance = True, draw_contexts = True, dump_attributes = False)
    

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
                parsed_info.append({
                    "change_stmts": [],
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
                before_tree.build(changed_stmts)
                miner = FixMiner()
                before_contexts, after_contexts = miner.build_before_and_after_contexts(changed_stmts, before_tree, None)
                parsed_info.append({
                    "change_stmts": changed_stmts,
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
            subtree = TemplateNode.subtree_match(target.before_within.root, source.before.root)
            if not subtree:
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
        
        return True, subtree

    def select_template(self, source, target):
        templates = []
        success, subtree = self.match_template(source, target)
        if success:
            for i in target.child_templates:
                templates += self.select_templates(source, self.id2template[i])
            if len(templates) == 0:
                templates.append([target, subtree])
        return templates


    def select_templates(self, parsed_info):
        if len(parsed_info) == 0:
            raise ValueError('Cannot get parsed location info.')
        for i in parsed_info:
            source = FixTemplate(None, i['before_tree'], None)
            source.before_contexts = i['before_contexts']
            source.after_contexts = i['after_contexts']
            source.cal_self_reference()
            selected_templates = {}
            # Only Add templates will be matched
            if i['all_added']:
                for t in self.top_templates['Add']:
                    selected_templates['Add'] = self.select_template(source, self.id2template[t])
            else:
                for k in self.top_templates:
                    for t in self.top_templates[k]:
                        selected_templates[k] = self.select_template(source, self.id2template[t])
            i["selected_templates"] = selected_templates
        return parsed_info

    def implement_templates(self, parsed_info):
        pass

    def run_one(self, buggy_file, buglines = None, added = None):
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

    def run_all(self, metafile, benchmark_path, benchmark = 'bugsinpy'):
        metadata = json.loads(open(metadata, 'r', encoding = 'utf-8').read())
        if benchmark == 'bugsinpy':
            for r in metadata:
                for i in metadata[r]:
                    path = os.path.join(benchmark_path, r, f'{r}-{i}')
                    for f in metadata[r][i]['code_files']:
                        if not f.endswith('.py'):
                            continue
                        buggy_file = os.path.join(path, f)
                        patch_file = self.run_one(buggy_file, buglines = metadata[r][i]['buglines'], added = metadata[r][i]['added'])
                        if patch_file == None:
                            logger.error('Cannot generate patch files for buggy file {}.'.format(buggy_file))
                            continue

    def test_one(self, metadata, template, noise):
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
                if self.match_template(source, noise)[0]:
                    self.draw_location(p, 'figures2')
                    template.draw(self.id2template, filerepo = 'figures2', draw_instance = True, draw_contexts = True, dump_attributes = False)
                    noise.draw(self.id2template, filerepo = 'figures2', draw_instance = True, draw_contexts = True, dump_attributes = False)
                    print(self.buglines)
                    print(p)
                    logger.error('Instance #{} in template #{} can match template #{}.'.format(index, template.id, noise.id))
                    return False
        
        return True
            

    def test_all(self, metafile):
        metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
        os.system('rm -rf figures2/*')
        for i in self.id2template:
            if i in [1257]:
                continue
            #if i != 1141:
            #    continue
            '''
            while(True):
                noise = self.id2template[list(self.id2template.keys())[random.randint(0, len(self.id2template)-1)]]
                if len(noise.child_templates) > 0:
                    continue
                found = False
                for k in noise.instances:
                    if isinstance(k, ChangePair):
                        k = k.metadata
                    for j in self.id2template[i].instances:
                        if isinstance(j, ChangePair):
                            j = j.metadata
                        if j['repo'] == k['repo'] and j['commit'] == k['commit'] and j['loc'] == k['loc'] and j['file'] == k['file']:
                            found = True
                            break
                    if found:
                        break
                if not found:
                    break
            '''
            noise = FixTemplate(None, None, None)
            success = self.test_one(metadata, self.id2template[i], noise)
            if not success:
                print('Test Failed.')
                exit()




        



if __name__ == "__main__":
    generator = PatchGenerator('mined_Replace_templates.json')
    generator.draw_templates('figures')
    #print(generator.id2template[2889].instances[0])
    #generator.run_all('all_bug_info_bugsinpy.json', '/Users/py/workspace/typefix/benchmarks/bugsinpy/info')
    #generator.test_all('combined_commits_contents.json')
