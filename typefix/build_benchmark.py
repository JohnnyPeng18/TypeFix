import json
import os
import pandas as pd
from tqdm import tqdm
from git.repo import Repo
from commit_processor import clone_repos, fetch_pr_branch
from patch_generator import PatchGenerator
from fix_miner import ASTCompare, FixMiner
from evaluate import compare_file
from ast_operation import ASTDiffer, CommentRemover, ASTTransformer
from bug_locator import FunctionLocator
from change_tree import ChangePair
from __init__ import logger, stmt_types, expr_types, elem_types, op2cat, stdtypes, builtins, errors, warnings, cat2op, op2code
from difflib import Differ
import ast
from copy import deepcopy





def download_repos(repopath, csvfile):
    df = pd.read_csv(csvfile)
    repos = []
    for index, row in df.iterrows():
        repo = row['URL'].replace('https://github.com/', '').split('/commit')[0]
        if repo not in repos:
            repos.append(repo)
    
    for r in tqdm(repos, desc='Cloning repos'):
        path = os.path.join(repopath, r)
        clone_url = 'https://github.com/{}.git'.format(r)
        if (not os.path.exists(path) or len(os.listdir(path)) == 0):
            os.system(f"mkdir -p {path}")
            Repo.clone_from(clone_url, to_path = path)


def create_repos(repopath, csvfile):
    df = pd.read_csv(csvfile)
    for index, row in df.iterrows():
        repo = row['URL'].replace('https://github.com/', '').split('/commit')[0].split('/')[-1]
        path = os.path.join(repopath, repo)
        if row.astype(str)['PR'] == 'nan':
            path = os.path.join(path, repo)
            os.system(f'mkdir -p {path}')
        else:
            path = os.path.join(path, '{}-{}'.format(repo, int(row['PR'])))
            os.system(f'mkdir -p {path}')

def fetch_branch(repopath, csvfile):
    df = pd.read_csv(csvfile)
    for index, row in df.iterrows():
        repo = row['URL'].replace('https://github.com/', '').split('/commit')[0]
        path = os.path.join(repopath, repo)
        if row.astype(str)['PR'] == 'nan':
            continue
        else:
            p = int(row['PR'])
            git_repo = Repo(path)
            try:
                git_repo.git.fetch('origin', 'pull/{}/head:{}'.format(p, f'pr{p}'))
            except Exception as e:
                print(e)
                print(index)
                exit()


def gen_bug_info(benchmark_path, csvfile):
    df = pd.read_csv(csvfile)
    index = {}
    total = {}
    for ind, row in df.iterrows():
        repo, commit = row['URL'].replace('https://github.com/', '').split('/commit/')
        reponame = repo.split('/')[-1]
        git_url = 'https://github.com/{}.git'.format(repo)
        if row.astype(str)['Python'] == 'nan':
            py_version = '3'
        else:
            py_version = row['Python']
        bug_file = row['Bugfile']
        if row.astype(str)['Testfile'] == 'nan':
            continue
        else:
            test_file = row['Testfile']
        if row.astype(str)['Testfunc'] == 'nan':
            continue
        info = {
            "py_version": str(py_version),
            "repo": reponame,
            "git": git_url,
            "fixed_pr_id": commit,
            "code_files": [bug_file],
            "test_files": [test_file]
        }
        if row.astype(str)['PR'] == 'nan':
            p = None
            name = reponame
        else:
            p = int(row['PR'])
            name = '{}-{}'.format(reponame, p)
        if name not in index:
            index[name] = 1
            if os.path.exists(os.path.join(benchmark_path,reponame, name)):
                path = os.path.join(benchmark_path,reponame, name, 'bug_info.json')
            else:
                path = os.path.join(benchmark_path,reponame, '{}-{}-{}'.format(reponame, p, index[name]), 'bug_info.json')
        else:
            index[name] += 1
            path = os.path.join(benchmark_path,reponame, '{}-{}-{}'.format(reponame, p, index[name]), 'bug_info.json')

        with open(path, 'w', encoding = 'utf-8') as pf:
            pf.write(json.dumps(info, sort_keys=True, indent=4, separators=(',', ': ')))
        
        
        if row.astype(str)['Testclass'] != 'nan':
            info['test_class'] = row['Testclass'].split(';')
        else:
            info['test_class'] = []
        info['test_func'] = row['Testfunc'].split(';')
        info['pr'] = p
        total[path.replace('/bug_info.json', '').replace(f'{benchmark_path}/', '')] = info
            
        

    
    

    
    
    with open('all_bug_info.json', 'w', encoding = 'utf-8') as af:
        af.write(json.dumps(total, sort_keys=True, indent=4, separators=(',', ': ')))


def get_test_file(gitrepo_path, benchmark_path, buginfo):
    buginfo = json.loads(open(buginfo, 'r', encoding = 'utf-8').read())
    for r in buginfo:
        repo = buginfo[r]['git'].replace('https://github.com/', '').replace('.git', '')
        repo_path = os.path.join(gitrepo_path, repo)
        git_repo = Repo(repo_path)
        try:
            if buginfo[r]['pr'] != None:
                git_repo.git.checkout('pr{}'.format(buginfo[r]['pr']))
        except:
            git_repo.git.checkout('--', '*')
            git_repo.git.checkout('pr{}'.format(buginfo[r]['pr']))
        git_repo.git.checkout(buginfo[r]['fixed_pr_id'])
        test_repo = buginfo[r]['test_files'][0].split('/')
        if len(test_repo) > 1:
            test_reponame = '/'.join(test_repo[:-1])
            os.system('mkdir -p {}/{}'.format(os.path.join(benchmark_path, r), test_reponame))
        os.system('cp {}/{} {}/{}'.format(repo_path, buginfo[r]['test_files'][0], os.path.join(benchmark_path, r), buginfo[r]['test_files'][0]))

class Visitor(ast.NodeVisitor):
    def __init__(self, classes, funcs):
        self.classes = classes
        self.funcs = funcs
        self.paths = []
        self.cur_path = []
    
    def visit_FunctionDef(self, node):
        self.cur_path.append(node.name)
        if node.name in self.funcs:
            self.paths.append(deepcopy(self.cur_path))
        self.generic_visit(node)
        self.cur_path = self.cur_path[:-1]
        

    def visit_ClassDef(self, node):
        self.cur_path.append(node.name)
        self.generic_visit(node)
        self.cur_path = self.cur_path[:-1]


    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def run(self, root):
        self.visit(root)
        if len(self.classes) > 0:
            removed = []
            for p in self.paths:
                found = False
                for c in self.classes:
                    if c in p:
                        found = True
                        break
                if not found:
                    removed.append(p)
            for r in removed:
                self.paths.remove(r)
        return self.paths




def gen_test_script(benchmark_path, buginfo):
    buginfo = json.loads(open(buginfo, 'r', encoding = 'utf-8').read())
    for r in buginfo:
        testfile = os.path.join(benchmark_path, r, buginfo[r]['test_files'][0])
        if not os.path.exists(testfile):
            print('Cannot find test file: {}'.format(testfile))
            continue
        root = ast.parse(open(testfile, 'r', encoding = 'utf-8').read())
        visitor = Visitor(buginfo[r]['test_class'], buginfo[r]['test_func'])
        paths = visitor.run(root)
        cmds = []
        for p in paths:
            cmd = 'pytest {}'.format(buginfo[r]['test_files'][0])
            for i in p:
                cmd = cmd + f'::{i}'
            cmds.append(cmd)
        script_path = os.path.join(benchmark_path, r, 'test.sh')
        with open(script_path, 'w', encoding = 'utf-8') as sf:
            sf.write('\n'.join(cmds))


def add_dependency(benchmark_path, buginfo):
    pass




def handle_bugsinpy(info_path, metadata_path, benchmark_path):
    dirs = os.listdir(metadata_path)
    repos = {}
    info = {}
    for d in dirs:
        if '-' in d:
            r, i = d.split('-')
            if r == 'youtubedl':
                r = 'youtube-dl'
            if r not in repos:
                repos[r] = [i]
            else:
                repos[r].append(i)
    
    for r in repos:
        info[r] = {}
        for i in repos[r]:
            repo_path = os.path.join(benchmark_path, r, f'{r}-{i}')
            os.system(f'mkdir -p {repo_path}')
            info[r][i] = {}
            bug_path = os.path.join(info_path, r, f'bugs/{i}')
            pj_path = os.path.join(info_path, r, 'project.info')
            with open(pj_path, 'r', encoding = 'utf-8') as pf:
                for line in pf.readlines():
                    if line.startswith('github_url='):
                        info[r][i]['git'] = line.replace('github_url=', '').replace('\"', '').replace('\n', '') + '.git'
                        break
            with open(os.path.join(bug_path, 'bug.info'), 'r', encoding = 'utf-8') as bf:
                for line in bf.readlines():
                    line = line.replace(' ', '')
                    if line.startswith('python_version='):
                        info[r][i]['py_version'] = line.replace('python_version=', '').replace('\"', '').replace('\n', '')
                    if line.startswith('buggy_commit_id='):
                        info[r][i]['buggy_id'] = line.replace('buggy_commit_id=', '').replace('\"', '').replace('\n', '')
                    if line.startswith('fixed_commit_id='):
                        info[r][i]['fixed_pr_id'] = line.replace('fixed_commit_id=', '').replace('\"', '').replace('\n', '')
                    if line.startswith('test_file='):
                        info[r][i]['test_files'] = [line.replace('test_file=', '').replace('\"', '').replace('\n', '')]
            with open(os.path.join(bug_path, 'bug_patch.txt'), 'r', encoding = 'utf-8') as bf:
                first_add_line = None
                buglines = {}
                added = {}
                cur_file = None
                lineno = None
                count = False
                for line in bf.readlines():
                    if line.startswith('--- a/'):
                        if cur_file != None:
                            if len(buglines[cur_file]) == 0:
                                buglines[cur_file].append(first_add_line)
                                added[cur_file].append(True)
                            else:
                                for j in buglines[cur_file]:
                                    added[cur_file].append(False)
                        cur_file = line.replace('--- a/', '').replace('\n', '')
                        count = False
                        info[r][i]['code_files'] = [line.replace('--- a/', '').replace('\n', '')]
                        buglines[cur_file] = []
                        added[cur_file] = []
                    if line.startswith('@@ '):
                        count = True
                        lineno = int(line.split(',')[0].replace('@@ -', '')) - 1
                    if count and cur_file:
                        if line.startswith('-'):
                            buglines[cur_file].append(lineno)
                            lineno += 1
                        elif line.startswith('+'):
                            if first_add_line == None:
                                first_add_line = lineno
                            continue
                        else:
                            lineno += 1
                if cur_file != None:
                    if len(buglines[cur_file]) == 0:
                        buglines[cur_file].append(first_add_line)
                        added[cur_file].append(True)
                    else:
                        for j in buglines[cur_file]:
                            added[cur_file].append(False)
                info[r][i]['buglines'] = buglines
                info[r][i]['added'] = added
            with open(os.path.join(bug_path, 'run_test.sh'), 'r', encoding = 'utf-8') as bf:
                info[r][i]['test_class'] = []
                info[r][i]['test_func'] = []
                for line in bf.readlines():
                    if len(line.replace('\n', '')) == 0:
                        continue
                    elif line.startswith('pytest') or line.startswith('python3 -m pytest') or line.startswith('py.test'):
                        items = line.replace('\n','').split('::')
                        if len(items) == 2:
                            if items[1] not in info[r][i]['test_func']:
                                info[r][i]['test_func'].append(items[1].strip())
                        elif len(items) == 3:
                            if items[1] not in info[r][i]['test_class']:
                                info[r][i]['test_class'].append(items[1].strip())
                            if items[2] not in info[r][i]['test_func']:
                                info[r][i]['test_func'].append(items[2].strip())
                        else:
                            raise ValueError(f'Unrecognized line: {line}')
                    elif line.startswith('python -m unittest -q'):
                        items = line.replace('\n','').split('.')
                        if items[-1] not in info[r][i]['test_func']:
                            info[r][i]['test_func'].append(items[-1].strip())
                        if items[-2].istitle() and items[-2] not in info[r][i]['test_class']:
                            info[r][i]['test_class'].append(items[-2].strip())
                    else:
                        raise ValueError(f'Unrecognized line: {line}')
            os.system(f'cp {bug_path}/requirements.txt {repo_path}/requirements.txt')
            if not os.path.exists(f'{bug_path}/setup.sh'):
                os.system(f'echo > {repo_path}/dependency_setup.sh')
            else:
                os.system(f'cp {bug_path}/setup.sh {repo_path}/dependency_setup.sh')
            os.system(f'cp {bug_path}/run_test.sh {repo_path}/test.sh')
            with open(os.path.join(repo_path, 'bug_info.json'), 'w', encoding = 'utf-8') as rf:
                rf.write(json.dumps(info[r][i], sort_keys=True, indent=4, separators=(',', ': ')))
    


    with open('all_bug_info_bugsinpy.json', 'w', encoding = 'utf-8') as af:
        af.write(json.dumps(info, sort_keys=True, indent=4, separators=(',', ': ')))


def build_bugsinpy(infofile, benchmark_path):
    info = json.loads(open(infofile, 'r', encoding = 'utf-8').read())
    '''
    for r in tqdm(info, desc = 'Cloning Repos'):
        for i in info[r]:
            path = os.path.join(benchmark_path, 'github_projects', r)
            if (not os.path.exists(path) or len(os.listdir(path)) == 0):
                os.system(f"mkdir -p {path}")
                Repo.clone_from(info[r][i]['git'], to_path = path)
            break
    '''
    '''
    for r in tqdm(info, desc = 'Acquiring Buggy Files'):
        path = os.path.join(benchmark_path, 'github_projects', r)
        git_repo = Repo(path)
        for i in info[r]:
            info_path = os.path.join(benchmark_path, 'info', r, f'{r}-{i}')
            git_repo.git.checkout(info[r][i]['buggy_id'])
            for f in info[r][i]['code_files']:
                items = f.split('/')
                if len(items) > 1:
                    repo = '/'.join(items[:-1])
                    os.system(f'mkdir -p {info_path}/{repo}')
                os.system(f'cp {path}/{f} {info_path}/{f}')
    '''
    '''
    for r in tqdm(info, desc = 'Acquiring Correct Files'):
        path = os.path.join(benchmark_path, 'github_projects', r)
        git_repo = Repo(path)
        for i in info[r]:
            info_path = os.path.join(benchmark_path, 'info', r, f'{r}-{i}')
            try:
                git_repo.git.checkout(info[r][i]['fixed_pr_id'])
            except:
                git_repo.git.checkout('--', '*')
                git_repo.git.checkout(info[r][i]['fixed_pr_id'])
            for f in info[r][i]['code_files']:
                items = f.split('/')
                if len(items) > 1:
                    repo = '/'.join(items[:-1])
                    os.system(f'mkdir -p {info_path}/correct/{repo}')
                os.system(f'cp {path}/{f} {info_path}/correct/{f}')
    '''
    pass
    
    
    
            

def handle_typebugs(info_path, benchmark_path):
    dirs = os.listdir(info_path)
    info = {}
    num = 0
    for d in dirs:
        repos = os.listdir(os.path.join(info_path, d))
        for r in repos:
            check = False
            if os.path.isdir(os.path.join(info_path, d, r)):
                info[f'{d}/{r}'] = json.loads(open(os.path.join(info_path, d, r, 'bug_info.json')).read())
                items = r.replace(d, '').split('-')
                info[f'{d}/{r}']['pr'] = int(items[1])
                git_repo = Repo(os.path.join(benchmark_path, 'github_projects', d))
                commit = git_repo.git.show(info[f'{d}/{r}']['fixed_pr_id'])
                if 'diff' in commit:
                    with open(os.path.join(info_path, d, r, 'patch.txt'), 'w', encoding = 'utf-8') as pf:
                        pf.write(commit)
                else:
                    os.system('wget {} -O {}'.format(info[f'{d}/{r}']['git'].replace('.git', '') + '/pull/{}.patch'.format(info[f'{d}/{r}']['pr']), os.path.join(info_path, d, r, 'patch.txt')))
                    check = True
                    num += 1
                codefiles = []
                for f in info[f'{d}/{r}']['code_files']:
                    if f.endswith('.py'):
                        codefiles.append(f)
                buglines = {}
                added = {}
                for f in codefiles:
                    buglines[f] = []
                    added[f] = []
                    first_add_line = None
                    with open(os.path.join(info_path, d, r, 'patch.txt'), 'r', encoding = 'utf-8') as pf:
                        found = False
                        count = False
                        for line in pf.readlines():
                            if line.startswith('diff --git'):
                                found = False
                            if line.startswith('--- a/{}'.format(f)):
                                found = True
                            if found and line.startswith('@@ '):
                                lineno = int(line.split(',')[0].replace('@@ -', '')) - 1
                                count = True
                            if count and found:
                                if line.startswith('-'):
                                    buglines[f].append(lineno)
                                    lineno += 1
                                elif line.startswith('+'):
                                    if first_add_line == None:
                                        first_add_line = lineno
                                    continue
                                else:
                                    lineno += 1
                    if len(buglines[f]) == 0:
                        buglines[f].append(first_add_line)
                        added[f].append(True)
                    else:
                        for i in buglines[f]:
                            added[f].append(False)


                info[f'{d}/{r}']['buglines'] = buglines
                info[f'{d}/{r}']['added'] = added
                info[f'{d}/{r}']['needs_check'] = check

    print(f'Totally {num} instances needs further check.')
                                
    with open('all_bug_info_typebugs.json', 'w', encoding = 'utf-8') as af:
        af.write(json.dumps(info, sort_keys=True, indent=4, separators=(',', ': ')))




def build_typebugs(info_file, benchmark_path):
    info = json.loads(open(info_file, 'r', encoding = 'utf-8').read())
    '''
    downloaded = {}
    for r in tqdm(info, desc = 'Cloning Repos'):
        repo = r.split('/')[0]
        if repo in downloaded:
            continue
        else:
            downloaded[repo] = 1
        path = os.path.join(benchmark_path, 'github_projects', repo)
        if (not os.path.exists(path) or len(os.listdir(path)) == 0):
            os.system(f"mkdir -p {path}")
            Repo.clone_from(info[r]['git'], to_path = path)
    '''
    '''
    for r in tqdm(info, desc = 'Acquring Buggy Files'):
        path = os.path.join(benchmark_path, 'github_projects', r.split('/')[0])
        git_repo = Repo(path)
        git_repo.git.fetch('origin', 'pull/{}/head:{}'.format(info[r]['pr'], 'pr{}'.format(info[r]['pr'])))
        try:
            git_repo.git.checkout('pr{}'.format(info[r]['pr']))
        except:
            git_repo.git.checkout('--', '*')
            git_repo.git.checkout('pr{}'.format(info[r]['pr']))
        try:
            git_repo.git.checkout(info[r]['fixed_pr_id'])
        except:
            git_repo.git.checkout('--', '*')
            git_repo.git.checkout(info[r]['fixed_pr_id'])
        info_path = os.path.join(benchmark_path, 'info', r)
        for f in info[r]['code_files']:
            if not f.endswith('.py'):
                continue
            git_repo.git.checkout('HEAD~1', f)
            items = f.split('/')
            if len(items) > 1:
                repo = '/'.join(items[:-1])
                os.system(f'mkdir -p {info_path}/{repo}')
            os.system(f'cp {path}/{f} {info_path}/{f}')
            git_repo.git.reset('HEAD', f)
    '''
    '''
    for r in tqdm(info, desc = 'Acquring Correct Files'):
        path = os.path.join(benchmark_path, 'github_projects', r.split('/')[0])
        git_repo = Repo(path)
        try:
            git_repo.git.checkout(info[r]['fixed_pr_id'])
        except:
            git_repo.git.checkout('--', '*')
            git_repo.git.checkout(info[r]['fixed_pr_id'])
        info_path = os.path.join(benchmark_path, 'info', r)
        for f in info[r]['code_files']:
            if not f.endswith('.py'):
                continue
            items = f.split('/')
            if len(items) > 1:
                repo = '/'.join(items[:-1])
                os.system(f'mkdir -p {info_path}/correct/{repo}')
            os.system(f'cp {path}/{f} {info_path}/correct/{f}')
    '''

    

def update_info(info_file, benchmark_path):
    info = json.loads(open(info_file, 'r', encoding = 'utf-8').read())
    removed = []
    checked = {}
    for r in info:
        repo = r.split('/')[0]
        if repo not in checked:
            repo_path = os.path.join(benchmark_path, 'info', repo)
            cases = os.listdir(repo_path)
            for c in cases:
                if os.path.isdir(os.path.join(repo_path, c)) and f'{repo}/{c}' not in info:
                    removed.append(f'{repo}/{c}')
            checked[repo] = 1
        repo_path = os.path.join(benchmark_path, 'info', r)
        sub_info = info[r]
        del sub_info['needs_check']
        with open(os.path.join(repo_path, 'bug_info.json'), 'w', encoding = 'utf-8') as bf:
            bf.write(json.dumps(sub_info, sort_keys=True, indent=4, separators=(',', ': ')))
    
    print(f'Will remove {len(removed)} repos')
    for r in removed:
        os.system('rm -rf {}'.format(os.path.join(benchmark_path, 'info', r)))

    print('Totally {} instances.'.format(len(info)))


def update_info2(info_file, benchmark_path):
    info = json.loads(open(info_file, 'r', encoding = 'utf-8').read())
    for r in info:
        for i in info[r]:
            sub_info = info[r][i]
            path = os.path.join(benchmark_path, r, f'{r}-{i}', 'bug_info.json')
            with open(path, 'w', encoding = 'utf-8') as bf:
                bf.write(json.dumps(sub_info, sort_keys=True, indent=4, separators=(',', ': ')))
            

    


            


class FuncFinder(ast.NodeVisitor):
    def __init__(self, lines):
        self.lines = lines
        self.candidate = None

    def visit_FunctionDef(self, node):
        found = True
        for l in self.lines:
            if l not in range(node.lineno, node.end_lineno + 1):
                found = False
                break
        if found:
            if self.candidate and node.end_lineno - node.lineno < self.candidate.end_lineno - self.candidate.lineno:
                self.candidate = node
            elif not self.candidate:
                self.candidate = node


    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def run(self, root):
        self.visit(root)
        if self.candidate:
            return ast.unparse(self.candidate)
        else:
            return None


def gen_training_set(datafile):
    data = json.loads(open(datafile, 'r', encoding = 'utf-8').read())
    dataset = []
    for r in tqdm(data, desc = 'Generate Training Instances'):
        for c in data[r]:
            commitinfo = data[r][c]
            for f in commitinfo:
                    beforefile, afterfile = commitinfo[f]['files']
                    try:
                        if beforefile:
                            beforeroot = ast.parse(open(beforefile, 'r').read())
                        else:
                            continue
                    except Exception as e:
                        print(f'Cannot parse the source files, reason:{e}')
                        continue
                    for l in commitinfo[f]:
                        if l == 'files':
                            continue
                        for commit in commitinfo[f][l]:
                            lines = commit["lines"]
                            content = commit["content"]
                            if len(lines) != 4:
                                raise ValueError('Incorrect line information: {}'.format(line))
                            if '\ No newline at end of file' in content:
                                print('Illegal commit, skipped.')
                                continue
                            before_index = lines[0]
                            after_index = lines[2]
                            before_change_lines = []
                            raw_before_change_lines = []
                            after_change_lines = []
                            raw_after_change_lines = []
                            new_lines = []
                            old_lines = []
                            for line in content.splitlines():
                                if not line.startswith('-') and not line.startswith('+'):
                                    before_index += 1
                                    after_index += 1
                                elif line.startswith('-'):
                                    if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                                        before_change_lines.append(before_index)
                                        old_lines.append(line[1:].strip())
                                    raw_before_change_lines.append(before_index)
                                    before_index += 1
                                elif line.startswith('+'):
                                    if not line[1:].strip().startswith('#') and not len(line[1:].strip()) == 0:
                                        after_change_lines.append(after_index)
                                        new_lines.append(line[1:].strip())
                                    raw_after_change_lines.append(after_index)
                                    after_index += 1
                            if before_index != lines[0] + lines[1] or after_index != lines[2] + lines[3]:
                                print('Line information does not match the change content.')
                                continue
                            if len(old_lines) == 0 or len(new_lines) == 0:
                                continue
                            finder = FuncFinder(raw_before_change_lines)
                            func = finder.run(beforeroot)
                            if func == None:
                                continue
                            dataset.append([" ".join(old_lines), func.replace('\n', ''), " ".join(new_lines)])
                            
    
    with open('training_set.json', 'w', encoding = 'utf-8') as tf:
        tf.write(json.dumps(dataset, sort_keys=True, indent=4, separators=(',', ': ')))
    
    with open('training_src.txt', 'w', encoding = 'utf-8') as tf:
        text = ''
        for d in dataset:
            text += '{} <CTX> {}\t{}\n'.format(d[0], d[1], d[2])
        tf.write(text)


    print('Totally {} instances.'.format(len(dataset)))

    
def copy_patch_file(metafile, benchmark_path, source_path):
    metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
    for r in metadata:
        for i in metadata[r]:
            source = os.path.join(source_path, r, 'bugs', i, 'bug_patch.txt')
            benchmark = os.path.join(benchmark_path, f'{r}/{r}-{i}', 'patch.txt')
            os.system('cp {} {}'.format(source, benchmark))
    
                            


def gen_cure_class_file(apiindex):
    apiindex = json.loads(open(apiindex, 'r', encoding = 'utf-8').read())
    classdict = {}
    for i in apiindex:
        for api in apiindex[i]:
            items = api.split('.')
            if len(items) >= 2:
                if items[0] not in classdict:
                    classdict[items[0]] = []
                classdict[items[0]].append(items[1].replace('()', ''))
    
    with open('python_class.json', 'w', encoding = 'utf-8') as pf:
        pf.write(json.dumps(classdict, sort_keys=True, indent=4, separators=(',', ': ')))


'''
def build_prompt_trainset(template_file, metadata_file):
    metadata = json.loads(open(metadata_file, 'r', encoding = 'utf-8').read())
    generator = PatchGenerator(template_file, remove_comment = True)
    instance2template = {}
    id2instance = {}
    instance_id = 0
    for i in generator.id2template:
        if generator.id2template[i].action == 'Remove':
            continue
        for m in generator.id2template[i].instances:
            if isinstance(m, dict):
                id2instance[instance_id] = m
                if instance_id not in instance2template:
                    instance2template[instance_id] = []
                instance2template[instance_id].append(i)
                instance_id += 1
            elif isinstance(m, ChangePair):
                id2instance[instance_id] = m.metadata
                if instance_id not in instance2template:
                    instance2template[instance_id] = []
                instance2template[instance_id].append(i)
                instance_id += 1
    compare = ASTCompare()
    for i in id2instance:
        data = id2instance[i]
        if "{}:{}:{}:{}".format(data["repo"], data["commit"], data["file"], data["loc"]) != "django/django:bf3e8227a902ca0828c9a66130064a23d5f75163:django/urls/resolvers.py@@@@@@django/urls/resolvers.py:def _route_to_regex(route, is_endpoint=False)":
            continue
        logger.info("Handling Instance #{}:{}:{}:{}".format(data["repo"], data["commit"], data["file"], data["loc"]))
        logger.info("Commit Context:\n {}".format(data["content"]))
        commits = metadata[data["repo"]][data["commit"]][data["file"]][data["loc"]]
        files = metadata[data["repo"]][data["commit"]][data["file"]]["files"]
        buggy_file = files[0]
        try:
            buggy_root = ast.parse(open(buggy_file, "r").read())
        except:
            logger.debug("Cannot parse buggy file, skipped.")
            continue
        commit = None
        for c in commits:
            if c["content"] == data["content"]:
                commit = c
                break
        if commit == None:
            logger.debug("Cannot find commit, skipped.")
            continue
        content = commit["content"]
        lines = commit["lines"]
        if '\ No newline at end of file' in content:
            logger.debug("Invalid commit, skipped.")
            continue
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
            continue
        before_trees = compare.build_change_tree(buggy_root, True, before_change_lines, raw_before_change_lines)
        if len(before_trees) == 0:
            buglines = after_change_lines[0]
            raw_buglines = buglines
            added = [True]
        else:
            buglines = before_change_lines
            raw_buglines = raw_before_change_lines 
            added = [False for i in buglines]
        generator.buglines = buglines
        generator.added = added
        generator.buggy_root = buggy_root
        generator.formatted_buggy_source = ast.unparse(buggy_root)
        parsed_info = generator.parse_locations(raw_buglines = raw_buglines)
        if len(parsed_info) > 1:
            logger.debug("Multiple locations, skipped.")
            continue
        correct = open(files[1], "r").read()
        locator = FunctionLocator()
        correct_node = locator.run(ast.parse(correct), raw_after_change_lines)
        remover = CommentRemover()
        correct_node = remover.run(correct_node)
        for t in instance2template[i]:
            logger.debug('Implementing template #{}'.format(t))
            patches = generator.implement_template(parsed_info[0], generator.id2template[t])
            candidate_roots = []
            candidate_sources = []
            for j in patches:
                if "VALUE_MASK" not in patches[j][3]:
                    continue
                mask_lines = []
                for i, line in enumerate(patches[j][3].splitlines()):
                    if "VALUE_MASK" in line:
                        mask_lines.append(i + 1)
                locator = FunctionLocator()
                patch_node = locator.run(patches[j][0], mask_lines)
                candidate_sources.append(patches[j][3])
                
                nodemap = ASTDiffer.extract_mask_content(patch_node, correct_node)
                if nodemap != None:
                    candidate_sources.append(patches[j][3])
                    candidate_roots.append(patches[j][0])
                
            for i, s in enumerate(candidate_sources):
                with open(f"tests/test_{i}.py", "w", encoding = "utf-8") as tf:
                    tf.write(s)
            #if len(candidate_sources) > 0:
            #    exit()
'''     

def handle_one_node(ast_node, mask_id, should_not_mask = None):
    new_node = deepcopy(ast_node)
    mask2gt = {}
    not_mask = {}
    if should_not_mask != None:
        for n in should_not_mask:
            if n.ast_node == None:
                not_mask[n.parent_relation] = [n.value]
            else:
                if n.parent_relation not in not_mask:
                    not_mask[n.parent_relation] = []
                not_mask[n.parent_relation].append(n.ast_node)
    for name, value in ast.iter_fields(new_node):
        if name in ['ctx', 'lineno', 'end_lienno', 'col_offset', 'end_col_offset', 'type_comment']:
            continue
        if isinstance(value, list):
            new_value = []
            for v in value:
                if name in not_mask:
                    not_mask_value = not_mask[name]
                    found = False
                    for k in not_mask_value:
                        if ASTDiffer.compare(k, v):
                            found = True
                            break
                    if found:
                        new_value.append(v)
                        continue
                if type(v) in elem_types:
                    new_value.append(v)
                if len(ast.unparse(v).replace(" ","")) > 0:
                    new_value.append(ast.Expr(value=ast.Name(id=f'MASK_{mask_id}')))
                    mask2gt[f'MASK_{mask_id}'] = ast.unparse(v)
                    mask_id += 1
            setattr(new_node, name, new_value)
        elif isinstance(value, ast.AST) and type(value) not in elem_types and len(ast.unparse(value).replace(" ","")) > 0 and name not in not_mask:
            new_value = ast.Name(id=f'MASK_{mask_id}')
            mask2gt[f'MASK_{mask_id}'] = ast.unparse(value)
            mask_id += 1
            setattr(new_node, name, new_value)
        elif name not in not_mask and type(value) not in elem_types:
            if value == None and name != 'value':
                continue
            new_value = f'MASK_{mask_id}'
            mask2gt[new_value] = str(value)
            mask_id += 1
            setattr(new_node, name, new_value)
    return new_node, mask2gt, mask_id

def generate_masks(t):
    ori2news = []
    mask2gt = {}
    buggy_lines = []
    mask_id = 0
    if t.action == 'Add':
        for depth in range(1, 3):
            ori2new = {}
            if depth == 1:
                for n in t.after.root.children['body']:
                    ast_node = n.ast_node
                    if ast_node == None and t.within_context == None:
                        return None
                    elif ast_node == None and t.within_context != None:
                        continue
                    if type(ast_node) in elem_types:
                        continue
                    new_node, mask_gt, mask_id = handle_one_node(ast_node, mask_id)
                    for n in mask_gt:
                        mask2gt[n] = mask_gt[n]
                    ori2new[ast_node] = new_node
                if len(ori2new) > 0:
                    ori2news.append(ori2new)
            elif depth == 2:
                children = []
                for n in t.after.root.children['body']:
                    for c in n.children:
                        for nn in n.children[c]:
                            if nn.ast_node != None:
                                children.append(nn)
                for c in children:
                    ast_node = c.ast_node
                    if ast_node == None:
                        continue
                    if type(ast_node) in elem_types:
                        continue
                    new_node, mask_gt, mask_id = handle_one_node(ast_node, mask_id)
                    for n in mask_gt:
                        mask2gt[n] = mask_gt[n]
                    ori2new[ast_node] = new_node
                if len(ori2new) > 0:
                    ori2news.append(ori2new)
    elif t.action == 'Insert':
        for n in t.before.root.children['body']:
            ast_node = n.ast_node
            if ast_node == None:
                return None
            for l in range(ast_node.lineno, ast_node.end_lineno + 1):
                buggy_lines.append(l)
        if len(buggy_lines) == 0:
            return None
        reference_nodes = []
        for n in t.after.iter_nodes():
            if n.type == 'Reference':
                reference_nodes.append(n)
        parent2reference = {}
        reference_parents = []
        for n in reference_nodes:
            if n.parent != None and n.parent.base_type != 'Root':
                reference_parents.append(n.parent)
                if n.parent not in parent2reference:
                    parent2reference[n.parent] = []
                parent2reference[n.parent].append(n)
        removed = []
        for n in reference_parents:
            children = n.get_all_children()
            for m in reference_parents:
                if m != n and m in children and n not in removed:
                    removed.append(n)
        for r in removed:
            reference_parents.remove(r)
        for depth in range(1, 4):
            ori2new = {}
            if depth == 1:
                for n in reference_parents:
                    ast_node = n.ast_node
                    if ast_node == None:
                        return None
                    if type(ast_node) in elem_types:
                        continue
                    new_node, mask_gt, mask_id = handle_one_node(ast_node, mask_id, should_not_mask = parent2reference[n])
                    for n in mask_gt:
                        mask2gt[n] = mask_gt[n]
                    ori2new[ast_node] = new_node
                ori2news.append(ori2new)
            else:
                children = reference_parents
                for i in range(1, depth):
                    p = children
                    children = []
                    for n in p:
                        for c in n.children:
                            for nn in n.children[c]:
                                if nn.ast_node != None and nn.type != "Reference":
                                    children.append(nn)
                for n in children:
                    ast_node = n.ast_node
                    if ast_node == None:
                        continue
                    if type(ast_node) in elem_types:
                        continue
                    new_node, mask_gt, mask_id = handle_one_node(ast_node, mask_id)
                    for n in mask_gt:
                        mask2gt[n] = mask_gt[n]
                    ori2new[ast_node] = new_node
                if len(ori2new) > 0:
                    ori2news.append(ori2new)
    elif t.action == 'Replace':
        for n in t.before.root.children['body']:
            ast_node = n.ast_node
            if ast_node == None and t.within_context == None:
                return None
            elif ast_node == None and t.within_context != None:
                leaf_nodes = t.within_context.context_tree.get_leaf_nodes()
                for n in leaf_nodes:
                    if n.ast_node != None:
                        for l in range(n.ast_node.lineno, n.ast_node.end_lineno + 1):
                            buggy_lines.append(l)
            elif ast_node != None:
                for l in range(ast_node.lineno, ast_node.end_lineno + 1):
                    buggy_lines.append(l)
        if len(buggy_lines) == 0:
            return None
        for depth in range(1, 4):
            ori2new = {}
            if depth == 1:
                for n in t.after.root.children['body']:
                    ast_node = n.ast_node
                    if ast_node == None:
                        return None
                    if type(ast_node) in elem_types:
                        continue
                    new_node, mask_gt, mask_id = handle_one_node(ast_node, mask_id)
                    for n in mask_gt:
                        mask2gt[n] = mask_gt[n]
                    ori2new[ast_node] = new_node
                ori2news.append(ori2new)
            else:
                children = t.after.root.children['body']
                for i in range(1, depth):
                    p = children
                    children = []
                    for n in p:
                        for c in n.children:
                            for nn in n.children[c]:
                                if nn.ast_node != None:
                                    children.append(nn)
                for n in children:
                    ast_node = n.ast_node
                    if ast_node == None:
                        continue
                    if type(ast_node) in elem_types:
                        continue
                    new_node, mask_gt, mask_id = handle_one_node(ast_node, mask_id)
                    for n in mask_gt:
                        mask2gt[n] = mask_gt[n]
                    ori2new[ast_node] = new_node
                if len(ori2new) > 0:
                    ori2news.append(ori2new)
    return ori2news, mask2gt, buggy_lines
                



                    


                    
def validate_template(target):
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

def transform_masks(source, mask2gt):
    mask_id = 0
    masks = {}
    gts = []
    for i in range(0, len(mask2gt)):
        if f'MASK_{i}' in source:
            index = source.index(f'MASK_{i}')
            masks[index] = f'MASK_{i}'
            mask_id += 1
    sorted_masks = sorted(masks.items(), key = lambda item: item[0])
    masks = []
    for s in sorted_masks:
        masks.append(s[1])
    for i, m in enumerate(masks):
        source = source.replace(m, f'<extra_id_{i}>')
        gts.append(mask2gt[m])

    if len(gts) == 0:
        logger.debug('Cannot find GTs.')
        return None, None
    label = '<extra_id_0>'
    for i, g in enumerate(gts):
        label += ' '
        label += g
        label += ' '
        label += f'<extra_id_{i+1}>'

    return source, label

def get_instances(template_file, metadata_file):
    generator = PatchGenerator("/Users/py/workspace/typefix/large_min5_templates.json")
    metadata = json.loads(open(metadata_file, 'r', encoding = 'utf-8').read())
    data = {}
    num = 0
    for i in generator.id2template:
        if generator.id2template[i].action == 'Remove':
            continue
        for instance in generator.id2template[i].instances:
            if isinstance(instance, ChangePair):
                instance = instance.metadata
            repo = instance["repo"] 
            commit = instance["commit"]
            files = instance["file"]
            loc = instance["loc"]
            content = instance["content"]
            if repo not in data:
                data[repo] = {}
            if commit not in data[repo]:
                data[repo][commit] = {}
            if files not in data[repo][commit]:
                data[repo][commit][files] = {"files": metadata[repo][commit][files]["files"]}
            if loc not in data[repo][commit][files]:
                data[repo][commit][files][loc] = []
            for c in metadata[repo][commit][files][loc]:
                if c["content"] == content and c not in data[repo][commit][files][loc]:
                    data[repo][commit][files][loc].append(c)
                    num += 1
                    break
    
    print("Totally {} instances are selected.".format(num))
    
    with open("min5_commits.json", "w", encoding = "utf-8") as mf:
        mf.write(json.dumps(data, sort_keys=True, indent=4, separators=(',', ': ')))
            
            





        
def build_prompt_trainset(metadata_file):
    metadata = json.loads(open(metadata_file, 'r', encoding = 'utf-8').read())
    a = ASTCompare()
    #sig = 'makeabilitylab/makeabilitylabwebsite:16f78d71f163e8f32f9cec1c1ab2af35f075d20a'
    #change_pairs = a.compare_one(metadata_file, sig.split(':')[0], sig.split(':')[1])
    #change_pairs = a.compare_projects(metadata_file)
    miner = FixMiner()
    miner.build_templates(change_pairs)
    trainset = {}
    for k in miner.fix_template:
        if k == 'Remove':
            continue
        else:
            for t in miner.fix_template[k]:
                instance = t.instances[0]
                if isinstance(instance, ChangePair):
                    instance = instance.metadata
                buggy_file, fix_file = metadata[instance["repo"]][instance["commit"]][instance["file"]]["files"]
                logger.debug("Handling {}:{}:{}:{}".format(instance["repo"], instance["commit"], instance["file"], instance["loc"]))
                try:
                    source = open(fix_file, "r").read()
                    buggy_source = open(buggy_file, "r").read()
                    buggy_sourcelines = buggy_source.splitlines()
                    root = ast.parse(source)
                except Exception as e:
                    logger.error("Cannot parse fix file #{}".format(fix_file))
                try:
                    value = generate_masks(t)
                    if value == None:
                        #t.after.draw('AfterTree', filerepo = 'figures2')
                        #if t.within_context:
                        #    t.within_context.context_tree.draw('Within', filerepo = 'figures2')
                        logger.error('Cannot generate masks for file #{}'.format(fix_file))
                        continue
                    ori2news, mask2gt, buggy_lines = value
                    buggy_code = []
                    for l in buggy_lines:
                        buggy_code.append(buggy_sourcelines[l-1])
                    for ori2new in ori2news:
                        transformer = ASTTransformer(ori2new, [], remove_comment = True)
                        new_source, new_root = transformer.run(root)
                        if new_source != None:
                            new_source, label = transform_masks(new_source, mask2gt)
                            if new_source != None and new_source not in trainset:
                                trainset[new_source] = [label, buggy_code]
                            elif new_source == None:
                                logger.error('Cannot transform masks for file #{}'.format(fix_file))
                except Exception as e:
                    logger.error("Cannot generate masks for file #{}".format(fix_file))
    
    with open("prompt_trainset.json", "w", encoding = "utf-8") as pf:
        pf.write(json.dumps(trainset, sort_keys=True, indent=4, separators=(',', ': ')))

                            

    

        




    



