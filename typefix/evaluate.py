import json
import os
import ast
from tqdm import tqdm
from difflib import Differ
from patch_generator import PatchGenerator
from bug_locator import FunctionLocator
from ast_operation import ASTDiffer
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


def evaluate_template_coverage(metafile, benchmark_path, template_file, benchmark = 'bugsinpy', patch_path = None):
    metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
    generator = PatchGenerator(template_file)
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
                #if f'{r}-{i}' != 'youtube-dl-16':
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
                    try:
                        correct_root = ast.parse(correct)
                    except Exception as e:
                        logger.error('Cannot parse the correct file, reason: {}, skipped.')
                        continue
                    new_buglines, new_added = split_lines(buglines, added, metadata[r][i])
                    if len(new_buglines) == 1:
                        total_count += 1
                        buggy_file = os.path.join(path, f)
                        try:
                            patches[r][i][buggy_file] = generator.run_one(buggy_file, buglines = metadata[r][i]['buglines'][f], added = metadata[r][i]['added'][f])
                        except Exception as e:
                            traceback.print_exc()
                            logger.debug('Error occurred when generating patches, reason: {}.'.format(e))
                            nopatch_count += 1
                            continue
                        matched_index = None
                        if len(patches[r][i][buggy_file]) == 0:
                            nopatch_count += 1
                            logger.debug('No patch generated.')
                            continue
                        for k, p in enumerate(patches[r][i][buggy_file]):
                            logger.debug('Testing Patch #{}'.format(patches[r][i][buggy_file][p][1]))
                            if compare_file(ast.unparse(patches[r][i][buggy_file][p][0]), correct, stmt_sensitive = True if patches[r][i][buggy_file][p][2] == 'Replace' else False):
                                matched_index = k
                                break
                        if matched_index == None:
                            failed_cases.append([r, f, metadata[r][i]['buglines'][f]])
                            logger.info('Failed to find the matched patch.')
                        else:
                            success_indexes.append(matched_index + 1)
                            succeed_cases.append([r, f, metadata[r][i]['buglines'][f], matched_index + 1])
                            matched_count += 1
                            logger.info(f'Found matched patch index #{matched_index + 1}.')
                    else:
                        for index, lines in enumerate(new_buglines):
                            #if lines[0] != 263:
                            #    continue
                            new_file = f.replace('.py', '-{}.py'.format(lines[0]))
                            buggy_file = os.path.join(path, new_file)
                            total_count += 1
                            if new_file in metadata[r][i]['buglines']:
                                new_lines = metadata[r][i]['buglines'][new_file]
                            else:
                                new_lines = lines
                            logger.debug(f'------------------------------Evaluating lines #{new_lines} of buggy file #{buggy_file}------------------------------')
                            try:
                                patches[r][i][buggy_file] = generator.run_one(buggy_file, buglines = new_lines, added = new_added[index])
                            except Exception as e:
                                traceback.print_exc()
                                logger.debug('Error occurred when generating patches, reason: {}.'.format(e))
                                nopatch_count += 1
                                continue
                            matched_index = None
                            if len(patches[r][i][buggy_file]) == 0:
                                nopatch_count += 1
                                logger.debug('No patch generated.')
                                continue
                            for j, p in enumerate(patches[r][i][buggy_file]):
                                logger.debug('Testing Patch #{}'.format(patches[r][i][buggy_file][p][1]))
                                if compare_file(ast.unparse(patches[r][i][buggy_file][p][0]), correct, stmt_sensitive = True if patches[r][i][buggy_file][p][2] == 'Replace' else False):
                                    matched_index = j
                                    break
                            if matched_index == None:
                                failed_cases.append([r, new_file, new_lines])
                                logger.info('Failed to find the matched patch.')
                            else:
                                success_indexes.append(matched_index + 1)
                                matched_count += 1
                                succeed_cases.append([r, new_file, new_lines, matched_index + 1])
                                logger.info(f'Found matched patch index #{matched_index + 1}.')
                            #exit()
        if patch_path != None:
            for r in patches:
                for i in patches[r]:
                    for f in patches[r][i]:
                        path = os.path.join(patch_path, r, i, f.replace('/', '_'))
                        if not os.path.exists(path):
                            os.system(f'mkdir -p {path}')
                        else:
                            os.system(f'rm -f {path}/*')
                        for k in patches[r][i][f]:
                            with open(os.path.join(path, '{}_from_{}.py'.format(k, patches[r][i][f][k][1])), 'w', encoding = 'utf-8') as pf:
                                pf.write(patches[r][i][f][k][-1])
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
            #if r != 'sanic/sanic-2008-1':
            #    continue
            logger.debug(f'+++++++++++++++++++++++++++++++++++++++++Evaluating Case #{r}+++++++++++++++++++++++++++++++++++++++++')
            patches[r] = {}
            path = os.path.join(benchmark_path, r)
            for f in metadata[r]['code_files']:
                if not f.endswith('.py'):
                    continue
                buglines = metadata[r]['buglines'][f]
                added = metadata[r]['added'][f]
                correct = ast.unparse(ast.parse(open(os.path.join(path, f'correct/{f}')).read()))
                try:
                    correct_root = ast.parse(correct)
                except Exception as e:
                    logger.error('Cannot parse the correct file, reason: {}, skipped.')
                    continue
                new_buglines, new_added = split_lines(buglines, added, metadata[r])
                if len(new_buglines) == 1:
                    total_count += 1
                    buggy_file = os.path.join(path, f)
                    try:
                        patches[r][buggy_file] = generator.run_one(buggy_file, buglines = metadata[r]['buglines'][f], added = metadata[r]['added'][f])
                    except Exception as e:
                        traceback.print_exc()
                        logger.debug('Error occurred when generating patches, reason: {}.'.format(e))
                        nopatch_count += 1
                        continue
                    matched_index = None
                    if len(patches[r][buggy_file]) == 0:
                        nopatch_count += 1
                        logger.debug('No patch generated.')
                        continue
                    for i, p in enumerate(patches[r][buggy_file]):
                        logger.debug('Testing Patch #{}'.format(patches[r][buggy_file][p][1]))
                        if compare_file(ast.unparse(patches[r][buggy_file][p][0]), correct, stmt_sensitive = True if patches[r][buggy_file][p][2] == 'Replace' else False):
                            matched_index = i
                            break
                    if matched_index == None:
                        failed_cases.append([r, f, metadata[r]['buglines'][f]])
                        logger.info('Failed to find the matched patch.')
                    else:
                        success_indexes.append(matched_index + 1)
                        succeed_cases.append([r, f, metadata[r]['buglines'][f], matched_index + 1])
                        matched_count += 1
                        logger.info(f'Found matched patch index #{matched_index + 1}.')
                else:
                    for i, lines in enumerate(new_buglines):
                        #if lines[0] != 263:
                        #    continue
                        new_file = f.replace('.py', '-{}.py'.format(lines[0]))
                        buggy_file = os.path.join(path, new_file)
                        total_count += 1
                        if new_file in metadata[r]['buglines']:
                            new_lines = metadata[r]['buglines'][new_file]
                        else:
                            new_lines = lines
                        logger.debug(f'------------------------------Evaluating lines #{new_lines} of buggy file #{buggy_file}------------------------------')
                        try:
                            patches[r][buggy_file] = generator.run_one(buggy_file, buglines = new_lines, added = new_added[i])
                        except Exception as e:
                            traceback.print_exc()
                            logger.debug('Error occurred when generating patches, reason: {}.'.format(e))
                            nopatch_count += 1
                            continue
                        matched_index = None
                        if len(patches[r][buggy_file]) == 0:
                            nopatch_count += 1
                            logger.debug('No patch generated.')
                            continue
                        for j, p in enumerate(patches[r][buggy_file]):
                            logger.debug('Testing Patch #{}'.format(patches[r][buggy_file][p][1]))
                            if compare_file(ast.unparse(patches[r][buggy_file][p][0]), correct, stmt_sensitive = True if patches[r][buggy_file][p][2] == 'Replace' else False):
                                matched_index = j
                                break
                        if matched_index == None:
                            failed_cases.append([r, new_file, new_lines])
                            logger.info('Failed to find the matched patch.')
                        else:
                            success_indexes.append(matched_index + 1)
                            matched_count += 1
                            succeed_cases.append([r, new_file, new_lines, matched_index + 1])
                            logger.info(f'Found matched patch index #{matched_index + 1}.')
                        #exit()
        if patch_path != None:
            for r in patches:
                for f in patches[r]:
                    path = os.path.join(patch_path, r, f.replace('/', '_'))
                    if not os.path.exists(path):
                        os.system(f'mkdir -p {path}')
                    else:
                        os.system(f'rm -f {path}/*')
                    for k in patches[r][f]:
                        with open(os.path.join(path, '{}_from_{}.py'.format(k, patches[r][f][k][1])), 'w', encoding = 'utf-8') as pf:
                            pf.write(patches[r][f][k][-1])
            with open(os.path.join(patch_path, 'failed_match_cases.json'), 'w', encoding = 'utf-8') as ff:
                ff.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
            with open(os.path.join(patch_path, 'succeed_match_cases.json'), 'w', encoding = 'utf-8') as ff:
                ff.write(json.dumps(succeed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        logger.info(f'Match Rate: {matched_count/(total_count - nopatch_count)} ({matched_count}/{total_count - nopatch_count}), {nopatch_count} do not have any patch.')
        logger.info('Average Index: {}'.format(sum(success_indexes)/len(success_indexes)))


if __name__ == "__main__":
    evaluate_template_coverage('TypeErrorFix/benchmarks/all_bug_info_typebugs.json', 'benchmarks/typebugs/info', '/Users/py/workspace/typefix/large_min5_templates.json', benchmark = 'typebugs', patch_path = '/Users/py/workspace/typefix/patches/typebugs')
    #evaluate_template_coverage('TypeErrorFix/benchmarks/all_bug_info_bugsinpy.json', 'benchmarks/bugsinpy/info', '/Users/py/workspace/typefix/large_min5_templates.json', benchmark = 'bugsinpy', patch_path = '/Users/py/workspace/typefix/patches/bugsinpy')



