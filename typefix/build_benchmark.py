import json
import os
import pandas as pd
from tqdm import tqdm
from git.repo import Repo
from commit_processor import clone_repos, fetch_pr_branch
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


    

        




    





if __name__ == "__main__":
    #download_repos('benchmark_repos', 'benchmark.csv')
    #create_repos('benchmark', 'benchmark.csv')
    #fetch_branch('benchmark_repos', 'benchmark.csv')
    #gen_bug_info('benchmark', 'benchmark.csv')
    #get_test_file('benchmark_repos', 'benchmark', 'all_bug_info.json')
    gen_test_script('benchmark', 'all_bug_info.json')
    #gen_training_set('final_combined_commits.json')
    #gen_cure_class_file('/Users/py/Desktop/git/API-Recommendation/API/pythonFunctionIndex.json')
