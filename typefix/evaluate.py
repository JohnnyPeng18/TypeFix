import json
import os
import ast
from tqdm import tqdm
from difflib import Differ
from patch_generator import PatchGenerator
from bug_locator import FunctionLocator
from ast_operation import ASTDiffer, CommentRemover
from __init__ import logger
import traceback




def split_lines(buglines, added, metadata):
    if len(buglines) == 1:
        return [buglines], [added]
    else:
        prev = 0
        new_buglines = []
        new_added = []
        for i in range(0, len(buglines) - 1):
            if buglines[i] != buglines[i+1] - 1:
                new_buglines.append(buglines[prev:i+1])
                new_added.append(added[prev:i+1])
                prev = i + 1
            elif buglines[i] == buglines[i+1] - 1:
                for f in metadata["buglines"]:
                    if f.endswith('-{}.py'.format(buglines[i])) and f.endswith('-{}.py'.format(buglines[i+1])):
                        new_buglines.append(buglines[prev:i+1])
                        new_added.append(added[prev:i+1])
                        prev = i + 1
        if prev < len(buglines):
            new_buglines.append(buglines[prev:])
            new_added.append(added[prev:])
        return new_buglines, new_added

def compare_file(patch, correct, stmt_sensitive = False):
    d = Differ()
    try:
        patch_root = ast.parse(patch)
        correct_root = ast.parse(correct)
    except Exception as e:
        raise ValueError('Cannot parse files.')
    patch_lines = patch.splitlines()
    correct_lines = correct.splitlines()
    res = '\n'.join(d.compare(patch_lines, correct_lines))
    patch_changed_lines = []
    correct_changed_lines = []
    patch_lineno = 0
    correct_lineno = 0
    for i, l in enumerate(res.splitlines()):
        if l.startswith('-'):
            patch_lineno += 1
            patch_changed_lines.append(patch_lineno)
        elif l.startswith('+'):
            correct_lineno += 1
            correct_changed_lines.append(correct_lineno)
        elif not l.startswith('?'):
            patch_lineno += 1
            correct_lineno += 1
        elif l.startswith('?'):
            patch_lineno -= 1
            correct_lineno -= 1
    if len(patch_changed_lines) > 20 or len(correct_changed_lines) > 20:
        logger.error('Too many changed lines, skipped.')
        return False
    patch_linenos = patch_changed_lines
    correct_linenos = correct_changed_lines
    locator = FunctionLocator()
    patch_node = locator.run(patch_root, patch_linenos)
    correct_node = locator.run(correct_root, correct_linenos)
    differ = ASTDiffer()
    logger.debug('Patch linenos: {},correct linenos: {}'.format(patch_linenos, correct_linenos))
    '''
    with open('figures2/patch.py', 'w') as ff:
        ff.write(patch)
    with open('figures2/correct.py', 'w') as ff:
        ff.write(correct)
    '''
    if differ.value_abstract_compare(patch_node, correct_node, stmt_sensitive = stmt_sensitive):
        return True
    else:
        return False


def evaluate_template_coverage(metafile, benchmark_path, template_file, benchmark = 'bugsinpy', patch_path = None, remove_comment = False):
    metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
    generator = PatchGenerator(template_file, remove_comment = remove_comment)
    total_count = 0
    matched_count = 0
    nopatch_count = 0
    failed_cases = []
    succeed_cases = []
    success_indexes = []
    if benchmark == 'bugsinpy':
        patches = {}
        for r in tqdm(metadata, desc = 'Evaluating Instances'):
            patches[r] = {}
            for i in metadata[r]:
                #if f'{r}-{i}' != 'scrapy-8':
                #    continue
                logger.debug(f'+++++++++++++++++++++++++++++++++++++++++Evaluating Case #{r}+++++++++++++++++++++++++++++++++++++++++')
                patches[r][i] = {}
                path = os.path.join(benchmark_path, r, f'{r}-{i}')
                for f in metadata[r][i]['code_files']:
                    if not f.endswith('.py'):
                        continue
                    buglines = metadata[r][i]['buglines'][f]
                    added = metadata[r][i]['added'][f]
                    correct = ast.unparse(ast.parse(open(os.path.join(path, f'correct/{f}')).read()))
                    if remove_comment:
                        remover = CommentRemover()
                        correct = ast.unparse(remover.run(ast.parse(correct)))
                    try:
                        correct_root = ast.parse(correct)
                    except Exception as e:
                        logger.error(f'Cannot parse the correct file, reason: {e}, skipped.')
                        continue
                    buggy_files = []
                    prefix = f.replace(".py", "-")
                    for bf in metadata[r][i]["buglines"]:
                        if bf.startswith(prefix):
                            buggy_files.append(bf)
                    if len(buggy_files) == 0:
                        buggy_files.append(f)
                    for bf in buggy_files:
                        total_count += 1
                        buglines = metadata[r][i]["buglines"][bf]
                        added = metadata[r][i]["added"][bf]
                        buggy_file = os.path.join(path, bf)
                        logger.debug(f'------------------------------Evaluating buggy file #{buggy_file}------------------------------')
                        try:
                            patches[r][i][buggy_file] = generator.run_one(buggy_file, buglines = buglines, added = added)
                        except Exception as e:
                            traceback.print_exc()
                            logger.debug('Error occurred when generating patches, reason: {}.'.format(e))
                            nopatch_count += 1
                            continue
                        first_matched_index = None
                        matched_indexes = []
                        if len(patches[r][i][buggy_file]) == 0:
                            nopatch_count += 1
                            logger.debug('No patch generated.')
                            continue
                        for k, p in enumerate(patches[r][i][buggy_file]):
                            logger.debug('Testing Patch #{}'.format(patches[r][i][buggy_file][p][1]))
                            if compare_file(ast.unparse(patches[r][i][buggy_file][p][0]), correct, stmt_sensitive = True if patches[r][i][buggy_file][p][2] == 'Replace' else False):
                                if first_matched_index == None:
                                    first_matched_index = k
                                matched_indexes.append(k)
                        if first_matched_index == None:
                            failed_cases.append([r, i, f, metadata[r][i]['buglines'][f]])
                            logger.info('Failed to find the matched patch.')
                        else:
                            success_indexes.append(first_matched_index + 1)
                            succeed_cases.append([r, i, f, metadata[r][i]['buglines'][f], matched_indexes])
                            matched_count += 1
                            logger.info(f'Found matched patch index #{first_matched_index + 1}.')
        if patch_path != None:
            for r in patches:
                for i in patches[r]:
                    for f in patches[r][i]:
                        path = os.path.join(patch_path, r, i, f.replace('/', '_'))
                        if not os.path.exists(path):
                            os.system(f'mkdir -p {path}')
                        else:
                            os.system(f'rm -f {path}/*')
                        duplicated = {}
                        for k in patches[r][i][f]:
                            if patches[r][i][f][k][-1] in duplicated:
                                continue
                            with open(os.path.join(path, '{}_from_{}.py'.format(k, patches[r][i][f][k][1])), 'w', encoding = 'utf-8') as pf:
                                pf.write(patches[r][i][f][k][-1])
                                duplicated[patches[r][i][f][k][-1]] = 1
            with open(os.path.join(patch_path, 'failed_match_cases.json'), 'w', encoding = 'utf-8') as ff:
                ff.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
            with open(os.path.join(patch_path, 'succeed_match_cases.json'), 'w', encoding = 'utf-8') as ff:
                ff.write(json.dumps(succeed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        logger.info(f'Match Rate: {matched_count/(total_count - nopatch_count)} ({matched_count}/{total_count - nopatch_count}), {nopatch_count} do not have any patch.')
        logger.info('Average Index: {}'.format(sum(success_indexes)/len(success_indexes)))
    elif benchmark == 'typebugs':
        patches = {}
        for r in tqdm(metadata, desc = 'Evaluating Instances'):
            if r in ["core/core-8065", "salt/salt-56381"]:
                continue
            #if r != 'pandas/pandas-28251':
            #    continue
            logger.debug(f'+++++++++++++++++++++++++++++++++++++++++Evaluating Case #{r}+++++++++++++++++++++++++++++++++++++++++')
            patches[r] = {}
            path = os.path.join(benchmark_path, r)
            for f in metadata[r]['code_files']:
                if not f.endswith('.py'):
                    continue
                correct = ast.unparse(ast.parse(open(os.path.join(path, f'correct/{f}')).read()))
                if remove_comment:
                    remover = CommentRemover()
                    correct = ast.unparse(remover.run(ast.parse(correct)))
                try:
                    correct_root = ast.parse(correct)
                except Exception as e:
                    #print(correct)
                    logger.error(f'Cannot parse the correct file, reason: {e}, skipped.')
                    continue
                buggy_files = []
                prefix = f.replace(".py", "-")
                for bf in metadata[r]["buglines"]:
                    if bf.startswith(prefix):
                        buggy_files.append(bf)
                if len(buggy_files) == 0:
                    buggy_files.append(f)
                for bf in buggy_files:
                    buglines = metadata[r]["buglines"][bf]
                    added = metadata[r]["added"][bf]
                    total_count += 1
                    buggy_file = os.path.join(path, bf)
                    logger.debug(f'------------------------------Evaluating buggy file #{buggy_file}------------------------------')
                    try:
                        patches[r][buggy_file] = generator.run_one(buggy_file, buglines = buglines, added = added)
                    except Exception as e:
                        traceback.print_exc()
                        logger.debug('Error occurred when generating patches, reason: {}.'.format(e))
                        nopatch_count += 1
                        continue
                    first_matched_index = None
                    matched_indexes = []
                    if len(patches[r][buggy_file]) == 0:
                        nopatch_count += 1
                        logger.debug('No patch generated.')
                        continue
                    for i, p in enumerate(patches[r][buggy_file]):
                        logger.debug('Testing Patch #{}'.format(patches[r][buggy_file][p][1]))
                        if compare_file(ast.unparse(patches[r][buggy_file][p][0]), correct, stmt_sensitive = True if patches[r][buggy_file][p][2] == 'Replace' else False):
                            if first_matched_index == None:
                                first_matched_index = i
                            matched_indexes.append(i)
                    if first_matched_index == None:
                        failed_cases.append([r, f, metadata[r]['buglines'][f]])
                        logger.info('Failed to find the matched patch.')
                    else:
                        success_indexes.append(first_matched_index + 1)
                        succeed_cases.append([r, f, metadata[r]['buglines'][f], matched_indexes])
                        matched_count += 1
                        logger.info(f'Found matched patch index #{first_matched_index + 1}.')
                    #exit()
        if patch_path != None:
            for r in patches:
                for f in patches[r]:
                    path = os.path.join(patch_path, r, f.replace('/', '_'))
                    if not os.path.exists(path):
                        os.system(f'mkdir -p {path}')
                    else:
                        os.system(f'rm -f {path}/*')
                    duplicated = {}
                    for k in patches[r][f]:
                        if patches[r][f][k][-1] in duplicated:
                            continue
                        with open(os.path.join(path, '{}_from_{}.py'.format(k, patches[r][f][k][1])), 'w', encoding = 'utf-8') as pf:
                            pf.write(patches[r][f][k][-1])
                            duplicated[patches[r][f][k][-1]] = 1
            with open(os.path.join(patch_path, 'failed_match_cases.json'), 'w', encoding = 'utf-8') as ff:
                ff.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
            with open(os.path.join(patch_path, 'succeed_match_cases.json'), 'w', encoding = 'utf-8') as ff:
                ff.write(json.dumps(succeed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        logger.info(f'Match Rate: {matched_count/(total_count - nopatch_count)} ({matched_count}/{total_count - nopatch_count}), {nopatch_count} do not have any patch.')
        logger.info('Average Index: {}'.format(sum(success_indexes)/len(success_indexes)))


def evaluate_plausible(repo, benchmark_file, benchmark = "bugsinpy"):
    metadata = json.loads(open(benchmark_file, "r", encoding = "utf-8").read())
    cases = {}
    fail = 0
    for i in range(1, 6):
        lines = open(os.path.join(repo, f"{i}.txt"), "r", encoding = "utf-8").read().splitlines()
        for l in lines:
            items = l.split('\t')
            if len(items) < 3:
                raise ValueError("Not four entries in a line: {}".format(l))
            if benchmark == "bugsinpy" and (items[0].split('/')[0] not in metadata or items[0].split('/')[-1].split('-')[-1] not in metadata[items[0].split('/')[0]]):
                continue
            if benchmark == "typebugs" and items[0] not in metadata:
                continue
            if items[0] not in cases:
                cases[items[0]] = {}
            if items[1] not in cases[items[0]]:
                cases[items[0]][items[1]] = []
            if items[2] == 'True':
                if items[3] not in cases[items[0]][items[1]]:
                    cases[items[0]][items[1]].append(items[3])
            elif items[2] == 'fail':
                print(l)
                fail += 1
    
    num = 0
    plausible = 0
    for c in cases:
        for f in cases[c]:
            num += 1
            if len(cases[c][f]) > 0:
                plausible += 1
    
    print("Totally {} instances, {} have plausible patches, {} fails to run test cases.".format(num, plausible, fail))

def format_plausible(repo, benchmark = "bugsinpy"):
    for i in range(1, 6):
        path = os.path.join(repo, str(i), benchmark)
        files = os.listdir(path)
        for f in files:
            if f.endswith(".json"):
                data = json.loads(open(os.path.join(path, f), "r").read())
                with open(os.path.join(path, f), "w", encoding = "utf-8") as ff:
                    ff.write(json.dumps(data, sort_keys=True, indent=4, separators=(',', ': ')))


def evaluate_text_plausible(filename, benchmark_file, benchmark = "bugsinpy"):
    data = open(filename, "r", encoding = "utf-8").read().splitlines()
    metadata = json.loads(open(benchmark_file, "r", encoding = "utf-8").read())
    if benchmark == "bugsinpy":
        cases = []
        for l in data:
            if l[0] not in ['+', '-', '>']:
                items = l.split('\t')
                if len(items) != 4:
                    continue
                if items[0].split('/')[0].replace("youtubedl", "youtube-dl") not in metadata or items[0].split('/')[-1].split('-')[-1] not in metadata[items[0].split('/')[0].replace("youtubedl", "youtube-dl")]:
                    print(items[0])
                    continue
                if "{}-{}".format(items[0], items[1]) not in cases:
                    print("{}-{}".format(items[0], items[1]))
                    cases.append("{}-{}".format(items[0], items[1]))
    elif benchmark == "typebugs":
        cases = []
        for l in data:
            if l[0] not in ['+', '-', '>']:
                items = l.split('\t')
                if len(items) != 4:
                    continue
                if items[0] not in metadata:
                    print(items[0])
                    continue
                if "{}-{}".format(items[0], items[1]) not in cases:
                    print("{}-{}".format(items[0], items[1]))
                    cases.append("{}-{}".format(items[0], items[1]))
    
    print("Totally {} plausible cases.".format(len(cases)))

def estimate_pyter(filename, bugsinpy_file, typebugs_file):
    data = open(filename, "r", encoding = "utf-8").read().splitlines()
    bugsinpy_data = json.loads(open(bugsinpy_file, 'r', encoding = 'utf-8').read())
    typebugs_data = json.loads(open(typebugs_file, 'r', encoding = 'utf-8').read())

    bugsinpy_num = 0
    typebugs_num = 0
    for l in data:
        if l.startswith('|'):
            items = l[1:].replace(' ', '').split('|')
            if items[0] == 'bug_id':
                continue
            bug = items[0].replace('-buggy', '')
            if items[1] == 'Ours' and items[2] == 'PLAUSIBLE':
                if '{}/{}'.format(bug.split('-')[0].replace('scikitlearn', 'scikit-learn'), bug.replace('scikitlearn', 'scikit-learn')) not in typebugs_data:
                    print('{}/{}'.format(bug.split('-')[0], bug))
                    continue
                num = len(typebugs_data['{}/{}'.format(bug.split('-')[0].replace('scikitlearn', 'scikit-learn'), bug.replace('scikitlearn', 'scikit-learn'))]['buglines'])
                if num > 1:
                    num -= 1
                typebugs_num += num
            elif items[1] == 'Bugsinpy' and items[2] == 'PLAUSIBLE':
                if bug.split('-')[0].replace('youtubedl', 'youtube-dl') not in bugsinpy_data or bug.split('-')[-1] not in bugsinpy_data[bug.split('-')[0].replace('youtubedl', 'youtube-dl') ]:
                    print(bug)
                    continue
                num = len(bugsinpy_data[bug.split('-')[0].replace('youtubedl', 'youtube-dl') ][bug.split('-')[-1]]['buglines'])
                if num > 1:
                    num -= 1
                bugsinpy_num += num
    

    print("Bugsinpy: {}; TypeBugs: {}".format(bugsinpy_num, typebugs_num))

def get_bug_num(benchmark_file, benchmark = "bugsinpy"):
    metadata = json.loads(open(benchmark_file, "r", encoding = "utf-8").read())
    num = 0
    pj = {}
    text = ""
    if benchmark == "bugsinpy":
        for r in metadata:
            if r not in pj:
                pj[r] = 0
            for i in metadata[r]:
                if len(metadata[r][i]["buglines"]) == 1:
                    num += 1
                    pj[r] += 1
                    for ff in metadata[r][i]["buglines"]:
                        text += "{},{}\n".format(f'{r}-{i}', ff)
                else:
                    for f in metadata[r][i]["code_files"]:
                        if not f.endswith(".py"):
                            continue
                        prefix = f.replace(".py", "-")
                        buggy_files = []
                        for bf in metadata[r][i]["buglines"]:
                            if bf.startswith(prefix):
                                buggy_files.append(bf)
                        if len(buggy_files) == 0:
                            buggy_files.append(f)
                        num += len(buggy_files)
                        pj[r] += len(buggy_files)
                        for ff in buggy_files:
                            text += "{},{}\n".format(f'{r}-{i}', ff)
    elif benchmark == "typebugs":
        for r in metadata:
            if r.split('/')[0] not in pj:
                pj[r.split('/')[0]] = 0
            if len(metadata[r]["buglines"]) == 1:
                num += 1
                pj[r.split('/')[0]] += 1
                for ff in metadata[r]["buglines"]:
                    text += "{},{}\n".format(r, ff)
            else:
                for f in metadata[r]["code_files"]:
                    if not f.endswith(".py"):
                        continue
                    prefix = f.replace(".py", "-")
                    buggy_files= []
                    for bf in metadata[r]["buglines"]:
                        if bf.startswith(prefix):
                            buggy_files.append(bf)
                    if len(buggy_files) == 0:
                        buggy_files.append(f)
                    num += len(buggy_files)
                    pj[r.split('/')[0]] += len(buggy_files)
                    for ff in buggy_files:
                        text += "{},{}\n".format(r, ff)

    
    print(f"Totally {num} bugs, detailed info: {pj}")
    with open(f"{benchmark}.csv", "w", encoding = "utf-8") as bf:
        bf.write(text)

def evaluate_correctness(final_patch_path, ori_patch_path, benchmark_path, metafile, benchmark = "bugsinpy"):
    metadata = json.loads(open(metafile, "r", encoding = "utf-8").read())
    if benchmark == "bugsinpy":
        num = 0
        correct_num = 0
        succeed_cases = []
        failed_cases = []
        for r in tqdm(metadata, desc = 'Evaluating Instances'):
            for i in metadata[r]:
                path = os.path.join(benchmark_path, r, f'{r}-{i}')
                for f in metadata[r][i]['code_files']:
                    if not f.endswith('.py'):
                        continue
                    correct = ast.unparse(ast.parse(open(os.path.join(path, f'correct/{f}')).read()))
                    remover = CommentRemover()
                    correct_root = remover.run(ast.parse(correct))
                    prefix = f.replace(".py", "-")
                    buggy_files = []
                    for bf in metadata[r][i]["buglines"]:
                        if bf.startswith(prefix):
                            buggy_files.append(bf)
                    if len(buggy_files) == 0:
                        buggy_files.append(f)
                    for bf in buggy_files:
                        patch_file_path = os.path.join(final_patch_path, r, f'{r}-{i}', bf.replace('/', '_').replace('.py', '.json'))
                        if not os.path.exists(patch_file_path):
                            continue
                        num += 1
                        patch = json.loads(open(patch_file_path, "r").read())
                        success = False
                        for p in patch:
                            if p == "buggy_code":
                                continue
                            ori_patch_file_path = os.path.join(ori_patch_path, r, str(i), ('TypeErrorFix/benchmarks/bugsinpy/' + r + '/' + f'{r}-{i}' + '/' + bf).replace('/', '_'), p)
                            buggy_source = open(ori_patch_file_path, "r").read()
                            if "code" not in patch[p]:
                                if "patches" in patch[p]:
                                    for index, c in enumerate(patch[p]["patches"]):
                                        try:
                                            patched_root = ast.parse(c)
                                        except Exception as e:
                                            logger.debug(f'Cannot parse patched source, reason: {e}')
                                            continue
                                        if ASTDiffer.compare(patched_root, correct_root):
                                            correct_num += 1
                                            success = True
                                            succeed_cases.append([r, bf, p, index])
                                            break
                                else:
                                    continue
                            else:
                                masked_line = "\n".join(patch[p]["code"]["masked_code"])
                                if masked_line not in buggy_source:
                                    logger.error("Cannot find the masked lines in pre-patch.")
                                    continue
                                for index, c in enumerate(patch[p]["patches"]):
                                    patched_source = buggy_source.replace(masked_line, c)
                                    try:
                                        patched_root = ast.parse(patched_source)
                                    except Exception as e:
                                        logger.debug(f'Cannot parse patched source, reason: {e}')
                                        continue
                                    if ASTDiffer.compare(patched_root, correct_root):
                                        correct_num += 1
                                        success = True
                                        succeed_cases.append([f'{r}-{i}', bf, p, index])
                                        break
                            if success:
                                break
                        if not success:
                            failed_cases.append([f'{r}-{i}', bf])
        with open(os.path.join(final_patch_path, "correctness_succeed_cases.json"), "w", encoding = "utf-8") as cf:
            cf.write(json.dumps(succeed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        with open(os.path.join(final_patch_path, "correctness_failed_cases.json"), "w", encoding = "utf-8") as cf:
            cf.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        logger.info("Totally {} instances, correctly generate patches for {} instances, correct fix rate: {}.".format(num, correct_num, correct_num/num))
    elif benchmark == "typebugs":
        num = 0
        correct_num = 0
        succeed_cases = []
        failed_cases = []
        for r in tqdm(metadata, desc = 'Evaluating Instances'):
            if r in ["core/core-8065", "salt/salt-56381"]:
                continue
            #if r != "Zappa/Zappa-1434":
            #    continue
            path = os.path.join(benchmark_path, r)
            for f in metadata[r]['code_files']:
                if not f.endswith('.py'):
                    continue
                correct = ast.unparse(ast.parse(open(os.path.join(path, f'correct/{f}')).read()))
                remover = CommentRemover()
                correct_root = remover.run(ast.parse(correct))
                prefix = f.replace(".py", "-")
                buggy_files = []
                for bf in metadata[r]["buglines"]:
                    if bf.startswith(prefix):
                        buggy_files.append(bf)
                if len(buggy_files) == 0:
                    buggy_files.append(f)
                for bf in buggy_files:
                    #if bf != "zappa/cli-1838.py":
                    #    continue
                    patch_file_path = os.path.join(final_patch_path, r, bf.replace('/', '_').replace('.py', '.json'))
                    if not os.path.exists(patch_file_path):
                        continue
                    num += 1
                    patch = json.loads(open(patch_file_path, "r").read())
                    success = False
                    for p in patch:
                        #if p != "44_from_18436.py":
                        #    continue
                        if p == "buggy_code":
                            continue
                        ori_patch_file_path = os.path.join(ori_patch_path, r, ('TypeErrorFix/benchmarks/typebugs/' + r + '/' + bf).replace('/', '_'), p)
                        buggy_source = open(ori_patch_file_path, "r").read()
                        if "code" not in patch[p]:
                            if "patches" in patch[p]:
                                for i, c in enumerate(patch[p]["patches"]):
                                    try:
                                        patched_root = ast.parse(c)
                                    except Exception as e:
                                        logger.debug(f'Cannot parse patched source, reason: {e}')
                                        continue
                                    if ASTDiffer.compare(patched_root, correct_root):
                                        correct_num += 1
                                        success = True
                                        succeed_cases.append([r, bf, p, i])
                                        break
                            else:
                                continue
                        else:
                            masked_line = "\n".join(patch[p]["code"]["masked_code"])
                            if masked_line not in buggy_source:
                                logger.error("Cannot find the masked lines in pre-patch.")
                                continue
                            for i, c in enumerate(patch[p]["patches"]):
                                patched_source = buggy_source.replace(masked_line, c)
                                try:
                                    patched_root = ast.parse(patched_source)
                                except Exception as e:
                                    logger.debug(f'Cannot parse patched source, reason: {e}')
                                    continue
                                if ASTDiffer.compare(patched_root, correct_root):
                                    correct_num += 1
                                    success = True
                                    succeed_cases.append([r, bf, p, i])
                                    break
                        if success:
                            break
                    if not success:
                        failed_cases.append([r, bf])
        with open(os.path.join(final_patch_path, "correctness_succeed_cases.json"), "w", encoding = "utf-8") as cf:
            cf.write(json.dumps(succeed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        with open(os.path.join(final_patch_path, "correctness_failed_cases.json"), "w", encoding = "utf-8") as cf:
            cf.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        logger.info("Totally {} instances, correctly generate patches for {} instances, correct fix rate: {}.".format(num, correct_num, correct_num/num))

                

def gen_test_script(failed_file, split = 1, benchmark = "bugsinpy"):
    failed_cases = json.loads(open(failed_file, "r", encoding = "utf-8").read())
    if split > 1:
        n = int(math.ceil(len(failed_cases) / float(split)))
        cases = [failed_cases[i: i + n] for i in range(0, len(failed_cases), n)]
    else:
        cases = [failed_cases]
    for i, case in enumerate(cases):
        text = ""
        for c in case:
            text += "pyenv global {}\n".format(c[0].split("/")[-1].replace("scikit-learn", "scikitlearn").replace("youtube-dl", "youtubedl"))
            if benchmark == "typebugs":
                text += "python test.py  {} {}\n".format(c[0], c[1])
            elif benchmark == "bugsinpy":
                if not c[0].startswith("youtube-dl"):
                    text += "python test.py  {} {}\n".format(c[0].split("-")[0] +"/" + c[0], c[1])
                else:
                    text += "python test.py  {} {}\n".format("youtube-dl/" + c[0], c[1])
        repo = "/".join(failed_file.split("/")[:-1])
        os.system("mkdir -p {}/test_scripts".format(repo))
        with open(f"{repo}/test_scripts/test_{benchmark}_{i}.sh", "w", encoding = "utf-8") as tf:
            tf.write(text)




        





if __name__ == "__main__":
    evaluate_template_coverage('benchmarks/all_bug_info_typebugs.json', 'benchmarks/typebugs', 'large_min5_templates.json', benchmark = 'typebugs', remove_comment = True)#, patch_path = '/Users/py/workspace/typefix/patches_v2/typebugs')
    evaluate_template_coverage('benchmarks/all_bug_info_bugsinpy.json', 'benchmarks/bugsinpy', 'large_min5_templates.json', benchmark = 'bugsinpy', remove_comment = True)#, patch_path = '/Users/py/workspace/typefix/patches_v2/bugsinpy')
    evaluate_correctness('prompt_patches/typebugs', 'patches/typebugs', 'benchmarks/typebugs', 'benchmarks/all_bug_info_typebugs.json', mask_all = False, benchmark = 'typebugs')
    evaluate_correctness('prompt_patches/bugsinpy', 'patches/bugsinpy', 'benchmarks/bugsinpy', 'benchmarks/all_bug_info_bugsinpy.json', mask_all = False, benchmark = 'bugsinpy')
    gen_test_script('prompt_patches/typebugs/correctness_failed_cases.json', split = 5, benchmark = "typebugs")
    gen_test_script('prompt_patches/bugsinpy/correctness_failed_cases.json', split = 5, benchmark = "bugsinpy")



