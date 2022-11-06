from git.repo import Repo
import os
import json
from tqdm import tqdm
from copy import deepcopy
import ast
from __init__ import logger



def clone_repos(jsonfile, repopath):
    data = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    for r in tqdm(data, desc='Cloning repos'):
        path = os.path.join(repopath, r)
        clone_url = 'https://github.com/{}.git'.format(r)
        if (not os.path.exists(path) or len(os.listdir(path)) == 0):
            os.system(f"mkdir -p {path}")
            Repo.clone_from(clone_url, to_path = path)


def fetch_pr_branch(jsonfile, repopath):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    for r in tqdm(repos):
        path = os.path.join(repopath, r)
        if os.path.exists(path):
            for p in repos[r]:
                repo = Repo(path)
                try:
                    repo.git.fetch('origin', 'pull/{}/head:{}'.format(p, f'pr{p}'))
                    for c in repos[r][p]:
                        repos[r][p][c]["pr_branch"] = f'pr{p}'
                except Exception as e:
                    print(e)
                    continue
    
    with open(jsonfile, 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(repos, sort_keys=True, indent=4, separators=(',', ': ')))



def process_commit(commit):
    info = {}
    curfile = None
    curloc = None
    changes = []
    lines = []
    passdiff = False
    for line in commit.splitlines():
        if line.startswith('diff --git a/'):
            files = [l[2:] for l in line.replace('diff --git ', '').split()]
            if len(files) != 2:
                logger.error('Cannot recognize modified files in commit: {}, skipping...'.format(line))
            if curfile != None and curloc != None:
                if curloc not in info[curfile]:
                    info[curfile][curloc] = []
                temp = {}
                temp["content"] = "\n".join(changes)
                temp["lines"] = lines
                info[curfile][curloc].append(temp)
            if not files[0].endswith('.py'):
                curfile = None
                curloc = None
                changes = []
                lines = []
                continue
            passdiff = True
            curloc = None
            curfile = None
        elif (line.startswith('---') or line.startswith('+++')) and passdiff:
            if line.startswith('---'):
                item = line.replace('--- ', '').strip()
                if item == '/dev/null':
                    curfile = 'None@@@@@@'
                else:
                    curfile = f'{item[2:]}@@@@@@'
            elif line.startswith('+++'):
                item = line.replace('+++ ', '').strip()
                if item == '/dev/null':
                    curfile += 'None'
                else:
                    curfile += f'{item[2:]}'
                info[curfile] = {}
                curloc = None
                passdiff = False


        elif line.startswith('@@') and curfile:
            if curloc != None:
                if curloc not in info[curfile]:
                    info[curfile][curloc] = []
                temp = {}
                temp["content"] = "\n".join(changes)
                temp["lines"] = lines
                info[curfile][curloc].append(temp)
            curloc = line.split('@@')[-1].strip().replace(':', '')
            changes = []
            items = line.split('@@')[1].strip().split()
            if items[0].startswith('-') and items[1].startswith('+'):
                prevs = items[0][1:].split(',')
                afters = items[1][1:].split(',')
                if len(prevs) == 1:
                    prevs.append('1')
                if len(afters) == 1:
                    afters.append('1')
                lines = [int(prevs[0]), int(prevs[1]), int(afters[0]), int(afters[1])]
            else:
                raise ValueError('Cannot recognize line changes')
        elif curfile != None and curloc != None:
            changes.append(line)
    if curfile != None and curloc != None:
        if curloc not in info[curfile]:
            info[curfile][curloc] = []
        temp = {}
        temp["content"] = "\n".join(changes)
        temp["lines"] = lines
        info[curfile][curloc].append(temp)
    
    numloc = 0
    for f in info:
        for l in info[f]:
            numloc += len(info[f][l])
    
    return info, len(info), numloc


def fecth_commits(jsonfile, repopath):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    commits = {}
    for r in tqdm(repos):
        path = os.path.join(repopath, r)
        if os.path.exists(path):
            try:
                gitrepo = Repo(path)
            except Exception as e:
                logger.error('An error {} occurs in path: {}'.format(e, path))
                continue
            commits[r] = {}
            for c in repos[r]["commits"]:
                commit = gitrepo.git.show(c)
                info, numfile, numloc = process_commit(commit)
                repos[r]["commits"][c]["modified_files"] = numfile
                repos[r]["commits"][c]["modified_locs"] = numloc
                commits[r][c] = info


    with open(jsonfile, 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(repos, sort_keys=True, indent=4, separators=(',', ': ')))
    
    with open(jsonfile.replace('.json', '_contents.json'), 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(commits, sort_keys=True, indent=4, separators=(',', ': ')))


def process_pr_patch(patchfile):
    patch = open(patchfile, "r", encoding = "utf-8")
    commits = {}
    buffer = []
    previous_commit = None
    try:
        for line in patch.readlines():
            if line.startswith("From "):
                items = line.split()
                if len(items) == 7 and len(items[1]) == 40:
                    commits[items[1]] = {}
                    if previous_commit:
                        commits[previous_commit]["content"] = "\n".join(buffer)
                        buffer = []
                    previous_commit = items[1]
            if previous_commit:
                buffer.append(line)
    except Exception as e:
        logger.error("Error occurred when reading patch files: {}".format(e))
        return {}
    if previous_commit:
        commits[previous_commit]["content"] = "\n".join(buffer)

    for c in commits:
        info, numfile, numloc = process_commit(commits[c]["content"])
        commits[c]["modified_files"] = numfile
        commits[c]["modified_locs"] = numloc
        commits[c]["content"] = info

    return commits




def fetch_prs(jsonfile):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    prs = {}
    for r in tqdm(repos):
        prs[r] = {}
        for p in repos[r]:
            prs[r][p] = process_pr_patch(repos[r][p]["patch"])
    
    with open(jsonfile.replace(".json", "_contents.json"), "w", encoding = "utf-8") as jf:
        jf.write(json.dumps(prs, sort_keys=True, indent=4, separators=(',', ': ')))


def filter_multifile_or_automatic_prs(meta_jsonfile, content_jsonfile, threshold = 10):
    repos = json.loads(open(content_jsonfile, "r", encoding = "utf-8").read())
    metadata = json.loads(open(meta_jsonfile, "r", encoding = "utf-8").read())
    new_repos = {}
    new_metadata = {}
    total_prs = 0
    for r in metadata:
        for pr in metadata[r]:
            total_locs = 0
            if metadata[r][pr]["body"] != None and "type" not in metadata[r][pr]["body"].lower() and "error" not in metadata[r][pr]["body"].lower() and metadata[r][pr]["title"] != None and "fix" not in metadata[r][pr]["title"].lower():
                continue
            if metadata[r][pr]["body"] != None and (metadata[r][pr]["body"].startswith("Bumps") or len(metadata[r][pr]["body"].split("\n")) > 20):
                continue
            if r in repos and pr in repos[r]:
                for c in repos[r][pr]:
                    total_locs += repos[r][pr][c]["modified_locs"]
                if total_locs > threshold:
                    continue
            else:
                continue
            if r not in new_metadata:
                new_metadata[r] = {}
            new_metadata[r][pr] = metadata[r][pr]
            if r not in new_repos:
                new_repos[r] = {}
            new_repos[r][pr] = repos[r][pr]
            total_prs += 1
    
    print("Totally {} prs and {} repos.".format(total_prs, len(new_repos)))
    with open(meta_jsonfile, "w", encoding = "utf-8") as jf:
        jf.write(json.dumps(new_metadata, sort_keys=True, indent=4, separators=(',', ': ')))
    
    with open(content_jsonfile, 'w', encoding = 'utf-8') as cf:
        cf.write(json.dumps(new_repos, sort_keys=True, indent=4, separators=(',', ': ')))



def prs2commits(jsonfile):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    newrepos = {}
    for r in repos:
        for p in repos[r]:
            for c in repos[r][p]:
                if r not in newrepos:
                    newrepos[r] = {}
                newrepos[r][c] = repos[r][p][c]['content']
                newrepos[r][c]['pr_branch'] = repos[r][p][c]['pr_branch']
    

    with open(jsonfile.replace('.json', '_commits.json'), 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newrepos, sort_keys=True, indent=4, separators=(',', ': ')))
                
            






def filter_multifile_or_unrelated_commits(jsonfile, threshold = 10):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    new_repos = {}
    total_commits = 0
    for r in repos:
        new_repos[r] = deepcopy(repos[r])
        new_repos[r]["commits"] = {}
        for c in repos[r]["commits"]:
            if "modified_locs" in repos[r]["commits"][c] and repos[r]["commits"][c]["modified_locs"] > 0 and repos[r]["commits"][c]["modified_locs"] < threshold and "type error" in repos[r]["commits"][c]["message"].lower():
                new_repos[r]["commits"][c] = repos[r]["commits"][c]
                total_commits += 1
        if len(new_repos[r]["commits"]) == 0:
            del new_repos[r]

    print("Totally {} commits and {} repos.".format(total_commits, len(new_repos)))

    with open(jsonfile, "w", encoding = "utf-8") as jf:
        jf.write(json.dumps(new_repos, sort_keys=True, indent=4, separators=(',', ': ')))


def manual_check(jsonfile, contentfile):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    contents = json.loads(open(contentfile, "r", encoding = "utf-8").read())
    newrepos = {}
    newcontents = {}
    try:
        for r in repos:
            for c in repos[r]['commits']:
                print('==============================================================\n')
                if repos[r]['commits'][c]['modified_locs'] == 1:
                    print(repos[r]['commits'][c]['message'])
                    data = input('p for pass and f for fail:')
                    if data == 'p':
                        if r not in newrepos:
                            newrepos[r] = deepcopy(repos[r])
                        newrepos[r]['commits'] = {}
                        newrepos[r]['commits'][c] = deepcopy(repos[r]['commits'][c])
                        if r not in newcontents:
                            newcontents[r] = {}
                        newcontents[r][c] = deepcopy(contents[r][c])
                    else:
                        continue
                else:
                    locs = []
                    for f in contents[r][c]:
                        for l in contents[r][c][f]:
                            locs.append([f, l])
                    print(repos[r]['commits'][c]['html_url'].replace('https://', ''))
                    for index, loc in enumerate(locs):
                        print(f'{index}: {loc}')
                    data = input('Please enter the index you choose (or f for failed):')
                    if data == 'f':
                        continue
                    else:
                        data = [int(d.strip()) for d in data.split(',')]
                        if r not in newrepos:
                            newrepos[r] = deepcopy(repos[r])
                        newrepos[r]['commits'] = {}
                        newrepos[r]['commits'][c] = deepcopy(repos[r]['commits'][c])
                        if r not in newcontents:
                            newcontents[r] = {}
                        newcontents[r][c] = {}
                        for index in data:
                            newcontents[r][c][locs[index][0]] = {locs[index][1]: deepcopy(contents[r][c][locs[index][0]][locs[index][1]])}
    except Exception as e:
        print(e)
    except KeyboardInterrupt:
        pass

    
    with open(jsonfile.replace('.json', '_checked.json'), 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newrepos, sort_keys=True, indent=4, separators=(',', ': ')))
    
    with open(contentfile.replace('.json', '_checked.json'), 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newcontents, sort_keys=True, indent=4, separators=(',', ': ')))
    


def remove_duplicated_commits(processed_file, base_file):
    base_repos = json.loads(open(base_file, 'r', encoding = 'utf-8').read())
    processed_repos = json.loads(open(processed_file, 'r', encoding = 'utf-8').read())

    new_repos = {}
    for r in processed_repos:
        if r not in base_repos:
            new_repos[r] = processed_repos[r]
    
    with open(processed_file, 'w', encoding = 'utf-8') as pf:
        pf.write(json.dumps(new_repos, sort_keys=True, indent=4, separators=(',', ': ')))
            
            



def get_modified_files(jsonfile, project_repo, file_repo):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    for r in tqdm(repos):
        for c in repos[r]:
            for f in repos[r][c]:
                if f == 'pr_branch':
                    continue
                try:
                    files = f.split('@@@@@@')
                    before_file = files[0] if files[0] != 'None' else None
                    after_file = files[1]if files[1] != 'None' else None
                    source_path = os.path.join(project_repo, r)
                    repo = Repo(source_path)
                    repo.git.checkout(repos[r][c]['pr_branch'])
                    head = repo.commit('HEAD')
                    os.system('mkdir -p {}'.format(os.path.join(file_repo, r, c)))
                    before_filepath = os.path.join(file_repo, r, c, 'BEFORE_' + before_file.replace('/', '@')) if before_file else None
                    after_filepath = os.path.join(file_repo, r, c, 'AFTER_' + after_file.replace('/', '@')) if after_file else None
                    repo.git.reset('--hard', c)
                    if after_filepath:
                        os.system('cp {} {}'.format(os.path.join(source_path, after_file), after_filepath))
                    repo.git.reset('--hard', 'HEAD~1')
                    if before_filepath:
                        os.system('cp {} {}'.format(os.path.join(source_path, before_file), before_filepath))
                    repo.git.reset('--hard', head)
                    repos[r][c][f]["files"] = [before_filepath, after_filepath]
                except Exception as e:
                    print('Failed when handling {}/{}/{}, reason: {}'.format(r, c, f, e))
    
    with open(jsonfile, 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(repos, sort_keys=True, indent=4, separators=(',', ': ')))

def check_modified_files(jsonfile):
    repos = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
    newrepos = {}
    num = 0
    for r in repos:
        for c in repos[r]:
            for f in repos[r][c]:
                try:
                    a = ast.parse(open(repos[r][c][f]['files'][0], 'r', encoding = 'utf-8').read())
                    b = ast.parse(open(repos[r][c][f]['files'][1], 'r', encoding = 'utf-8').read())
                except Exception as e:
                    num += 1
                    continue
                if r not in newrepos:
                    newrepos[r] = {}
                if c not in newrepos[r]:
                    newrepos[r][c] = {}
                newrepos[r][c][f] = repos[r][c][f]
    
    print('Cleaned {} files that cannot be read.'.format(num))
    with open(jsonfile, 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newrepos, sort_keys=True, indent=4, separators=(',', ': ')))
    

def print_info(jsonfile):
    repos = json.loads(open(jsonfile, "r", encoding = "utf-8").read())
    num = 0
    for r in repos:
        num += len(repos[r])
    
    print('Totally {} repos and {} commits.'.format(len(repos), num))
    




def combine_commits(jsonfile1, jsonfile2):
    repos1 = json.loads(open(jsonfile1, 'r', encoding = 'utf-8').read())
    repos2 = json.loads(open(jsonfile2, 'r', encoding = 'utf-8').read())
    new_repos = deepcopy(repos1)
    for r in repos2:
        if r not in new_repos:
            new_repos[r] = repos2[r]
    


    with open('final_combined_commits.json', 'w', encoding = 'utf-8') as cf:
        cf.write(json.dumps(new_repos, sort_keys=True, indent=4, separators=(',', ': ')))

def remove_too_many_line_commits(jsonfile):
    repos = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
    newrepos = {}
    num = 0
    for r in repos:
        for c in repos[r]:
            for f in repos[r][c]:
                if f == 'pr_branch':
                    continue
                for l in repos[r][c][f]:
                    if l != 'files':
                        for commit in repos[r][c][f][l]:
                            if len(commit['content'].split('\n')) <= 50:
                                if r not in newrepos:
                                    newrepos[r] = {}
                                if c not in newrepos[r]:
                                    newrepos[r][c] = {}
                                if f not in newrepos[r][c]:
                                    newrepos[r][c][f] = {}
                                if l not in newrepos[r][c][f]:
                                    newrepos[r][c][f][l] = []
                                newrepos[r][c][f][l].append(commit)
                            else:
                                num += 1
                try:
                    newrepos[r][c][f]['files'] = repos[r][c][f]['files']
                except Exception as e:
                    pass
                try:
                    newrepos[r][c]['pr_branch'] = repos[r][c]['pr_branch']
                except Exception as e:
                    pass
    print('Removed {} over-long commits.'.format(num))
    with open(jsonfile, 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newrepos, sort_keys=True, indent=4, separators=(',', ': ')))


def get_commits_with_testcases(jsonfile):
    repos = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
    newrepos = {}
    newrepos_with_testcases = {}
    num = 0
    for r in repos:
        for c in repos[r]:
            found = False
            for f in repos[r][c]:
                files = f.split('@@@@@@')
                for ff in files:
                    items = ff.split('/')
                    for i in items:
                        if i == 'tests':
                            found = True
                            break
                    if found:
                        break
            if found:
                if r not in newrepos_with_testcases:
                    newrepos_with_testcases[r] = {}
                newrepos_with_testcases[r][c] = repos[r][c]
                num += 1
            else:
                if r not in newrepos:
                    newrepos[r] = {}
                newrepos[r][c] = repos[r][c]
    
    print('Found {} commits with testcases.'.format(num))
    with open(jsonfile, 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newrepos, sort_keys=True, indent=4, separators=(',', ': ')))
    
    with open(jsonfile.replace('.json', '_with_testcases.json'), 'w', encoding = 'utf-8') as jf:
        jf.write(json.dumps(newrepos_with_testcases, sort_keys=True, indent=4, separators=(',', ': ')))
    
                    



        







if __name__ == "__main__":
    #clone_repos("/data/project/ypeng/typeerror/prs_v2.json", "/data/project/ypeng/typeerror/github_projects")
    #fetch_pr_branch("/data/project/ypeng/typeerror/prs_v2_contents.json", "/data/project/ypeng/typeerror/github_projects")
    #fecth_commits('combined_commits.json', "/data/project/ypeng/typeerror/github_projects")
    #filter_multifile_or_unrelated_commits("combined_commits.json")
    #repo = Repo('/data/project/ypeng/typeerror/github_projects/05bit/peewee-async')
    #repo.git.reset('--hard', 'd30b026b0edb34225ccf1c60edce8036d7f73203')
    #repo.git.reset('--hard', 'HEAD~1')
    get_modified_files('prs_v2_contents_commits.json', 'github_projects', 'github_projects_commits')
    #manual_check('popular_github_projects_with_commits_v2.json', 'popular_github_projects_with_commits_v2_contents.json')
    #remove_duplicated_commits('/data/project/ypeng/typeerror/prs_v2_contents_commits.json', '/data/project/ypeng/typeerror/combined_commits_contents.json')
    #combine_commits('/data/project/ypeng/typeerror/prs_v2_contents_commits.json', '/data/project/ypeng/typeerror/combined_commits_contents.json')
    #fetch_prs("/data/project/ypeng/typeerror/prs_v2.json")
    #filter_multifile_or_automatic_prs('/data/project/ypeng/typeerror/prs_v2.json', '/data/project/ypeng/typeerror/prs_v2_contents.json')
    #remove_too_many_line_commits('/data/project/ypeng/typeerror/prs_v2_contents_commits.json')
    #check_modified_files('/data/project/ypeng/typeerror/combined_commits_contents.json')
    #get_commits_with_testcases('/data/project/ypeng/typeerror/combined_commits_contents.json')
    #prs2commits('/data/project/ypeng/typeerror/prs_v2_contents.json')
    #print_info('/data/project/ypeng/typeerror/prs_v2_contents_commits.json')

