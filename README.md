# TypeFix

This is the tool released in the ICSE'24 paper: "[Domain Knowledge Matters: Improving Prompts with Fix Templates for Repairing Python Type Errors](https://arxiv.org/abs/2306.01394)".

## Dataset

**Benchmarks:**

We adopt the two benchmarks used in previous work: BugsInPy and TypeBugs. 

For more details, please access the `benchmarks/` directory.

**Training Set:**

We collect 10981 merged pull requests that contains "type error fix" in the titles as our training set. It is used to mine fix templates and train baselines.

For more details, please check `final_combined_commits.json`.

## Code

All source code is included in the `typefix/` directory.

### Step 1: Mining Fix Template

```
python fix_miner.py
```

The above command will start the fix template mining process based on the collected `final_combined_commits.json`. This process generally takes several hours and require at least 128GB RAM. It will generate a file `large_mined_templates.json` that contains all mined fix templates.

### Step 2: Generating Code Prompts

```
python patch_generator.py
```

The above command will generate code prompts and store them as several python files under directory `patches/{benchmark_name}` based on the mined fix templates from `large_mined_templates.json` , for both `BugsInPy` and `TypeBugs` benchmarks.

### Step 3: Generating Candidate Patches

```
python repair.py
```

The above command will invoke the original `codet5-base` model from HuggingFace to fill the masks in code prompts and generate candidate patches. The generated candidate patches are stored in `prompt_patches/{benchmark_name}`.

### Step 4: Validating Candidate Patches

**Template Coverage:**

```python
evaluate_template_coverage('benchmarks/all_bug_info_typebugs.json', 'benchmarks/typebugs', 'large_mined_templates.json', benchmark = 'typebugs', remove_comment = True)
evaluate_template_coverage('benchmarks/all_bug_info_bugsinpy.json', 'benchmarks/bugsinpy', 'large_mined_templates.json', benchmark = 'bugsinpy', remove_comment = True)
```

You can run the above two function calls in `evaluate.py` to evaluate the template coverage of mined fix templates. For the definition of template coverage, please refer to Section 4.3 of the paper.

**Exact Match:**

```python
evaluate_exactmatch('prompt_patches/typebugs', 'patches/typebugs', 'benchmarks/typebugs', 'benchmarks/all_bug_info_typebugs.json', mask_all = False, benchmark = 'typebugs')
evaluate_exactmatch('prompt_patches/bugsinpy', 'patches/bugsinpy', 'benchmarks/bugsinpy', 'benchmarks/all_bug_info_bugsinpy.json', mask_all = False, benchmark = 'bugsinpy')
```

You can run the above two function calls in `evaluate.py` to evaluate in how many cases that TypeFix can generate exactly the same patches (i.e., with the same ASTs) with developer patches. Note that this result is neither the **Correct** metirc nor the **Plausible** metric, which require human inspection or test case validation. This step is to speed up the validation process of generated patches since patches exactly matched to developer patches are both correct and plausible and no further validation is required. For the definition of correct and plausible patches, please refer to Section 3.2.2 of the paper.

**Check Plausible Patches:**

```python
gen_test_script('prompt_patches/typebugs/correctness_failed_cases.json', split = 5, benchmark = "typebugs")
gen_test_script('prompt_patches/bugsinpy/correctness_failed_cases.json', split = 5, benchmark = "bugsinpy")
```

You can run the above two function calls in `evaluate.py` to generate test scripts and then follow the instructions in [PyTER](https://github.com/kupl/PyTER/blob/main/INSTALL.md) to build dockers and run test cases. Patches that pass all the test cases are considered plausible patches.

**Check Correct Patches:**

Based on the identified plausible patches, identify the correct patches that maintain the same functionality with developer patches via manual analysis. Correct patches may not be exactly the same with developer patches.

## Results

We release the evaluation results of TypeFix and baselines in `results/eval.pdf`.
We also display the mined fix templates from TypeFix in `results/samples/` directory.

We can find all intermediate result files mentioned above in the release of this repo.

## Citation

If you use TypeFix in your research, please cite us:
```
@misc{peng2023domain,
      title={Domain Knowledge Matters: Improving Prompts with Fix Templates for Repairing Python Type Errors}, 
      author={Yun Peng and Shuzheng Gao and Cuiyun Gao and Yintong Huo and Michael R. Lyu},
      year={2023},
      eprint={2306.01394},
      archivePrefix={arXiv},
      primaryClass={cs.SE}
}
```

## Contact

If you have any question, please contact [research@yunpeng.work](mailto:research@yunpeng.work).
