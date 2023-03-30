# Benchmark

The two benchmarks under this repo are different from the original ones. We remove some cases that involves code change of more than 10 lines and that are not related to type errors.

## Usage

In the json file of bug information:

`buglines` indicate the exact lines that needs to be modified to fix the type error.

The True values in `added` indicate the corresponding line in `buglines` should not be modified and we should add new lines before the location to fix the type error.

**Before you run one testcase:**

1. Clone the GitHub repo and switch the commit to `fixed_pr_id`
2. Copy the `requirements.txt` file to the GitHub repo, run `pip install -r requirements.txt` to install required dependencies
3. Install the GitHub using `dependency_setup.sh`
4. Copy the buggy file from this repo to the GitHub repo
5. If you are using TypeBugs benchmark, also copy the test file
6. Run `test.sh`

**New!**

We split one buggy file into multiple buggy files if it contains multiple bugs.
If there exist `{name}.py` and `{name}-{line}.py` in the `buglines`, `{name}-{line}.py` files are the splitted files containing single bugs. If you want to test one single bug each time, you should use `{name}-{line}.py` files  instead of `{name}.py`  files.

## BugsInPy

Currently it contains 54 testcases.

For information about all testcases, please see `all_bug_info_bugsinpy.json`

For the metadata of each testcase, please see the folder `bugsinpy/`

## TypeBugs

Currently it contains 109 testcases.

For information about all testcases, please see `all_bug_info_typebugs.json`

For the metadata of each testcase, please see the folder `typebugs/`