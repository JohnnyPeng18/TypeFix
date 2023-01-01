import json
import os
import ast
from tqdm import tqdm
from difflib import Differ
from patch_generator import PatchGenerator
from bug_locator import FunctionLocator
from ast_operation import ASTDiffer
from __init__ import logger





def split_lines(buglines, added):
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
        if prev < len(buglines):
            new_buglines.append(buglines[prev:])
            new_added.append(added[prev:])
        return new_buglines, new_added

def compare_file(patch, correct):
    d = Differ()
    try:
        patch_root = ast.parse(patch)
        correct_root = ast.parse(correct)
    except Exception as e:
        raise ValueError('Cannot parse files.')
    correct = ast.unparse(correct_root)
    patch_lines = patch.splitlines()
    correct_lines = correct.splitlines()
    res = '\n'.join(d.compare(patch_lines, correct_lines))
    patch_changed_lines = []
    correct_changed_lines = []
    for l in res.splitlines():
        if l.startswith('-'):
            patch_changed_lines.append(l[2:])
        elif l.startswith('+'):
            correct_changed_lines.append(l[2:])
    if len(patch_changed_lines) > 20 or len(correct_changed_lines) > 20:
        logger.error('Too many changed lines, skipped.')
        return False
    patch_linenos = []
    for l in patch_changed_lines:
        patch_linenos.append(patch_lines.index(l) + 1)
    correct_linenos = []
    for l in correct_changed_lines:
        correct_linenos.append(correct_lines.index(l) + 1)
    locator = FunctionLocator()
    patch_node = locator.run(patch_root, patch_linenos)
    correct_node = locator.run(correct_root, correct_linenos)
    differ = ASTDiffer()
    logger.debug('Patch linenos: {},correct linenos: {}'.format(patch_linenos, correct_linenos))
    if differ.value_abstract_compare(patch_node, correct_node):
        return True
    else:
        return False


def evaluate_template_coverage(metafile, benchmark_path, template_file, benchmark = 'bugsinpy'):
    metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
    generator = PatchGenerator(template_file)
    total_count = 0
    matched_count = 0
    nopatch_count = 0
    failed_cases = []
    success_indexes = []
    if benchmark == 'bugsinpy':
        pass
    elif benchmark == 'typebugs':
        patches = {}
        for r in tqdm(metadata, desc = 'Evaluating Instances'):
            if r in ["core/core-8065"]:
                continue
            if r != 'airflow/airflow-14686':
                continue
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
                new_buglines, new_added = split_lines(buglines, added)
                if len(new_buglines) == 1:
                    total_count += 1
                    buggy_file = os.path.join(path, f)
                    patches[r][buggy_file] = generator.run_one(buggy_file, buglines = metadata[r]['buglines'][f], added = metadata[r]['added'][f])
                    matched_index = None
                    if len(patches[r][buggy_file]) == 0:
                        nopatch_count += 1
                        logger.debug('No patch generated.')
                        continue
                    for i, p in enumerate(patches[r][buggy_file]):
                        logger.debug('Testing Patch #{}'.format(patches[r][buggy_file][p][1]))
                        if compare_file(ast.unparse(patches[r][buggy_file][p][0]), correct):
                            matched_index = i
                            break
                    if matched_index == None:
                        failed_cases.append([r, f, new_buglines])
                        logger.info('Failed to find the matched patch.')
                    else:
                        success_indexes.append(matched_index + 1)
                        matched_count += 1
                        logger.info(f'Found matched patch index #{matched_index + 1}.')
                else:
                    for i, lines in enumerate(new_buglines):
                        #if lines[0] != 2551:
                        #    continue
                        new_file = f.replace('.py', '-{}.py'.format(lines[0]))
                        buggy_file = os.path.join(path, new_file)
                        total_count += 1
                        if new_file in metadata[r]['buglines']:
                            new_lines = metadata[r]['buglines'][new_file]
                        else:
                            new_lines = lines
                        logger.debug(f'------------------------------Evaluating lines #{new_lines} of buggy file #{buggy_file}------------------------------')
                        patches[r][buggy_file] = generator.run_one(buggy_file, buglines = new_lines, added = new_added[i])
                        matched_index = None
                        if len(patches[r][buggy_file]) == 0:
                            nopatch_count += 1
                            logger.debug('No patch generated.')
                            continue
                        for j, p in enumerate(patches[r][buggy_file]):
                            logger.debug('Testing Patch #{}'.format(patches[r][buggy_file][p][1]))
                            if compare_file(ast.unparse(patches[r][buggy_file][p][0]), correct):
                                matched_index = j
                                break
                        if matched_index == None:
                            failed_cases.append([r, new_file, new_lines])
                            logger.info('Failed to find the matched patch.')
                        else:
                            success_indexes.append(matched_index + 1)
                            matched_count += 1
                            logger.info(f'Found matched patch index #{matched_index + 1}.')
        with open('failed_match_cases.json', 'w', encoding = 'utf-8') as ff:
            ff.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        logger.info(f'Match Rate: {matched_count/(total_count - nopatch_count)} ({matched_count}/{total_count - nopatch_count}), {nopatch_count} do not have any patch.')
        logger.info('Average Index: {}'.format(sum(success_indexes)/len(success_indexes)))


if __name__ == "__main__":
    evaluate_template_coverage('TypeErrorFix/benchmarks/all_bug_info_typebugs.json', 'benchmarks/typebugs/info', '/Users/py/workspace/typefix/large_min5_templates.json', benchmark = 'typebugs')



