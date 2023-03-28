import os
import json
import torch
import ast
from tqdm import tqdm
from transformers import RobertaTokenizer, RobertaForMaskedLM, T5ForConditionalGeneration
from beam_search import BeamSearch
from __init__ import logger
import timeout_decorator
import traceback


from patch_generator import PatchGenerator
os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"

DEVICE = "cuda:1" if torch.cuda.is_available() else "cpu"


class Prompt(object):
    def __init__(self):
        #self.model = RobertaForMaskedLM.from_pretrained("microsoft/codebert-base-mlm", cache_dir = './transformers').to(DEVICE)
        #self.tokenizer = RobertaTokenizer.from_pretrained("microsoft/codebert-base-mlm", cache_dir = './transformers')
        self.model = T5ForConditionalGeneration.from_pretrained("Salesforce/codet5-base", cache_dir = './transformers').to(DEVICE)
        #self.model = torch.load("/data/pengyun/typefix/models/typefix_3.bin", map_location = "cuda:1")
        self.tokenizer = RobertaTokenizer.from_pretrained("Salesforce/codet5-base", cache_dir = './transformers')
        self.mask_token = '<mask>'
        self.model_type = "codet5"

    def process_file(self, patch_source, buggy_lines = None, added = None):
        if buggy_lines == None:
            patch_lines = patch_source.splitlines()
            buggy_line_indexes = []
            for i, line in enumerate(patch_lines):
                if 'VALUE_MASK' in line:
                    buggy_line_indexes.append(i)
            
            min_index = min(buggy_line_indexes)
            max_index = max(buggy_line_indexes)
        else:
            patch_lines = patch_source
            min_index = min(buggy_lines) - 1
            max_index = max(buggy_lines) - 1

        pre_code = []
        post_code = []
        for i in range(0, len(patch_lines)):
            if i < min_index:
                pre_code.append(patch_lines[i])
            elif i > max_index:
                post_code.append(patch_lines[i])
        
        if buggy_lines != None and added != None:
            if added[0] == True:
                post_code = [patch_lines[buggy_lines[0] - 1]] + post_code
            elif added[0] == 2:
                pre_code += [patch_lines[buggy_lines[0] - 1]]
        
        masked_code = [patch_lines[i] for i in range(min_index, max_index + 1)]

        
        return {
            "pre_code": pre_code,
            "masked_code": masked_code,
            "post_code": post_code
        }

    
    def build_prompt(self, code, buggy_code, max_mask_size, added = False, mask_all = False):
        inputs = {}
        if self.model_type == "codebert":
            for i in range(1, max_mask_size):
                inputs[i] = {}
                linesize = 50
                masked_lines = []
                for x in code["masked_code"]:
                    line = x
                    if "VALUE_MASK___VALUE_MASK" in x:
                        line = x.replace("VALUE_MASK___VALUE_MASK", self.mask_token * i * 5)
                    line = line.replace("VALUE_MASK", self.mask_token * i)
                    masked_lines.append(line)
                masked_input = " ".join([x.strip() for x in masked_lines]).strip()
                linesize = 50
                input_line = None
                while linesize > 0:
                    pre_code_input = "</s> " + " ".join([x.strip() for x in code["pre_code"][-linesize: ]])
                    post_code_input = " ".join([x.strip() for x in code["post_code"][:linesize]]).strip()
                    input_line = pre_code_input + " " + masked_input + " " + post_code_input
                    if self.tokenizer(input_line, return_tensors='pt')['input_ids'].size()[1] < 490:
                        break
                    linesize -= 1
                if linesize <= 0:
                    return None
                else:
                    inputs[i]["input"] = input_line
                    inputs[i]["masked_lines"] = masked_lines
        elif self.model_type == "codet5":
            mask_id = 0
            if not mask_all:
                masked_lines = []
                max_len = 10
                min_len = 2
                for x in code["masked_code"]:
                    line = x
                    while True:
                        stmt_index = line.find("VALUE_MASK___VALUE_MASK")
                        expr_index = line.find("VALUE_MASK")
                        if stmt_index == -1 and expr_index == -1:
                            break
                        if stmt_index != -1 and stmt_index <= expr_index:
                            line = line.replace("VALUE_MASK___VALUE_MASK", f"<extra_id_{mask_id}>", 1)
                            max_len += 15
                            min_len += 1
                        elif expr_index != -1 and (stmt_index == -1 or stmt_index > expr_index):
                            line = line.replace("VALUE_MASK", f"<extra_id_{mask_id}>", 1)
                            max_len += 5
                            min_len += 1
                        mask_id += 1
                    masked_lines.append(line)
            else:
                masked_lines = []
                if not added:
                    for i in range(0, len(buggy_code)):
                        masked_lines.append(f"<extra_id_{mask_id}>")
                        mask_id += 1
                else:
                    for i in range(0, 2):
                        masked_lines.append(f"<extra_id_{mask_id}>")
                        mask_id += 1
                max_len = 128
                min_len = 2
            masked_input = " ".join([x.strip() for x in masked_lines]).strip()
            linesize = 50
            input_line = None
            buggy_line = "\"\"\"" + " ".join([x.strip() for x in buggy_code]) + "\"\"\""
            while linesize > 0:
                pre_code_input = " ".join([x.strip() for x in code["pre_code"][-linesize: ]])
                post_code_input = " ".join([x.strip() for x in code["post_code"][:linesize]]).strip()
                input_line = " ".join([buggy_line, pre_code_input, masked_input, post_code_input])
                if (not mask_all and self.tokenizer(input_line, return_tensors='pt')['input_ids'].size()[1] < 490) or (mask_all and self.tokenizer(input_line, return_tensors='pt')['input_ids'].size()[1] < 390):
                    break
                linesize -= 1
            if linesize <= 0:
                return None
            else:
                inputs["input"] = input_line
                #print(masked_lines)
                inputs["masked_lines"] = masked_lines
                inputs["max_mask_id"] = mask_id
                inputs["max_len"] = max_len
                inputs["min_len"] = min_len
        
        return inputs
    
    def validate_patch(self, patch_data, predictions, mask_all = False):

        if self.model_type == "codebert":
            patch = None
            masked_lines = patch_data["prompt"]["masked_lines"]
            mask_index = 0
            patch_lines = []
            for line in masked_lines:
                while self.mask_token in line:
                    line = line.replace(self.mask_token, predictions[mask_index], 1)
                    mask_index += 1
                patch_lines.append(line)
            
            if mask_index != len(predictions):
                raise ValueError('Inconsistent mask index and prediction length: {} and {}'.format(mask_index, len(predictions)))
        elif self.model_type == "codet5":
            pred_code = []
            for pred in predictions:
                #print(pred)
                curpred = pred
                pred_map = {}
                failed = False
                for i in range(0, patch_data["prompt"]["max_mask_id"]):
                    if f"<extra_id_{i}>" not in curpred:
                        failed = True
                        break
                    else:
                        items = curpred.split(f"<extra_id_{i}>")
                        if len(items) != 2:
                            failed = True
                            break
                        prefix, curpred = items
                        if i != 0:
                            pred_map[i-1] = prefix
                if failed:
                    continue
                if "<extra_id" not in curpred:
                    pred_map[patch_data["prompt"]["max_mask_id"] - 1] = curpred
                else:
                    pred_map[patch_data["prompt"]["max_mask_id"] - 1] = curpred.split("<extra_id_{}>".format(patch_data["prompt"]["max_mask_id"]))[0]
                if not mask_all:
                    masked_code = "\n".join(patch_data["prompt"]["masked_lines"])
                    for i in pred_map:
                        masked_code = masked_code.replace(f"<extra_id_{i}>", pred_map[i])
                    patch = "\n".join(patch_data["code"]["pre_code"]) + "\n" + masked_code + "\n" + "\n".join(patch_data["code"]["post_code"])
                    try:
                        ast.parse(patch)
                        pred_code.append(masked_code)
                    except Exception as e:
                        #print(e)
                        pass
                else:
                    masked_code = [""]
                    for p in pred_map:
                        new_masked_code = []
                        for i in range(0, 4):
                            if i > 0:
                                for c in masked_code:
                                    if len(c) != 0:
                                        new_masked_code.append(c + "\n" + "    " * i + pred_map[p])
                                    else:
                                        new_masked_code.append(c + "    " * i + pred_map[p])
                            else:
                                for c in masked_code:
                                    if len(c) != 0:
                                        new_masked_code.append(c + "\n" + pred_map[p])
                                    else:
                                        new_masked_code.append(c + pred_map[p])
                        masked_code = new_masked_code
                        new_masked_code = [""]

                    masked_code = list(set(masked_code))
                    for c in masked_code:
                        patch = "\n".join(patch_data["code"]["pre_code"]) + "\n" + c + "\n" + "\n".join(patch_data["code"]["post_code"])
                        try:
                            ast.parse(patch)
                            pred_code.append(c)
                        except Exception as e:
                            #print(e)
                            pass

                #with open("patch.py", "w", encoding = "utf-8") as pf:
                #    pf.write(patch)
                #exit()
            return pred_code
            

    def get_prediction(self, patch_data, mask_all = False):
        if self.model_type == "codebert":
            for i in patch_data["prompt"]:
                if i != 2:
                    continue
                beam_engine = BeamSearch(self.model, self.tokenizer, patch_data["prompt"][i]["input"], DEVICE,
                                        beam_width=25, re_rank=True)
                beam_list, masked_index = beam_engine.generate_beam()
                ret = []
                for i, beam in enumerate(beam_list):
                    print("".join(beam[2]))
                    ret.append(("".join(beam[2]), beam[2], beam[0], prompt))
        elif self.model_type == 'codet5':
            inputs = self.tokenizer(patch_data["prompt"]["input"], return_tensors = "pt").to(DEVICE)
            input_ids = inputs["input_ids"]
            attention_mask = inputs["attention_mask"]
            patches = {}
            for i in range(patch_data["prompt"]["min_len"], patch_data["prompt"]["max_len"]):
                outputs = self.model.generate(input_ids, max_length = i, num_beams = 50, num_return_sequences = 50)
                predictions = self.tokenizer.batch_decode(outputs)
                sub_patches = self.validate_patch(patch_data, predictions, mask_all = mask_all)
                for p in sub_patches:
                    if p not in patches:
                        patches[p] = 2
            return patches
        
            
        
        
            
    @timeout_decorator.timeout(7200)
    def run_one(self, patch_path, buggy_file, buggy_lines, added, mask_all = False):
        old_code = open(buggy_file, 'r').read().splitlines()
        buggy_code = [old_code[int(i)-1] for i in buggy_lines]
        if not mask_all:
            patch_files = []
            for f in os.listdir(patch_path):
                if f.endswith('.py'):
                    patch_files.append(f)
            patch_data = {"buggy_code": buggy_code}
            num = 0
            for f in patch_files:
                #if f != "102_from_23371.py":
                #    continue
                patch_data[f] = {}
                patch_source = open(os.path.join(patch_path, f)).read()
                if 'VALUE_MASK' in patch_source:
                    patch_data[f]["code"] = self.process_file(patch_source)
                    patch_data[f]["prompt"] = self.build_prompt(patch_data[f]["code"], patch_data["buggy_code"], 10)
                    if patch_data[f]["prompt"] != None:
                        patch_data[f]["patches"] = self.get_prediction(patch_data[f])
                    else:
                        patch_data[f]["patches"] = {}
                else:
                    patch_data[f]["patches"] = {patch_source: 1}
                num += len(patch_data[f]["patches"])
        else:
            patch_data = {"buggy_code": buggy_code}
            patch_data["code"] = self.process_file(old_code, buggy_lines = buggy_lines, added = added)
            patch_data["prompt"] = self.build_prompt(patch_data["code"], patch_data["buggy_code"], 10, added = True if added[0] else False, mask_all = True)
            
            if patch_data["prompt"] != None:
                patch_data["patches"] = self.get_prediction(patch_data, mask_all = True)
            else:
                patch_data["patches"] = {}
            

        
        #print("Totally {} patches.".format(num))
        return patch_data
        
        


        


    def run_all(self, metafile, patch_path, benchmark_path, final_patch_path, benchmark = 'bugsinpy', mask_all = False):
        metadata = json.loads(open(metafile, 'r', encoding = 'utf-8').read())
        if benchmark == 'bugsinpy':
            failed_cases = []
            for r in tqdm(metadata, desc = 'Generate prompt for instances'):
                for i in metadata[r]:
                    for f in metadata[r][i]["code_files"]:
                        if not f.endswith(".py"):
                            continue
                        try:
                            prefix = f.replace(".py", "-")
                            buggy_files = []
                            for bf in metadata[r][i]["buglines"]:
                                if bf.startswith(prefix):
                                    buggy_files.append(bf)
                            if len(buggy_files) == 0:
                                buggy_files.append(f)
                            for bf in buggy_files:
                                logger.debug('Handling File#{} in Case#{}'.format(bf, f'{r}-{i}'))
                                final_patch_file_path = os.path.join(final_patch_path, r, f'{r}-{i}', bf.replace('/', '_').replace('.py', '.json'))
                                if os.path.exists(final_patch_file_path):
                                    continue
                                path = os.path.join(patch_path, r, i, ('TypeErrorFix/benchmarks/bugsinpy/' + r + '/' + f'{r}-{i}' + '/' + bf).replace('/', '_'))
                                buggy_file = os.path.join(benchmark_path, r, f'{r}-{i}', bf)
                                try:
                                    patch_data = self.run_one(path, buggy_file, metadata[r][i]["buglines"][bf], metadata[r][i]["added"][bf], mask_all = mask_all)
                                    if not os.path.exists(os.path.join(final_patch_path, r, f'{r}-{i}')):
                                        os.system('mkdir -p {}'.format(os.path.join(final_patch_path, r, f'{r}-{i}')))
                                    with open(final_patch_file_path, 'w', encoding = 'utf-8') as pf:
                                        pf.write(json.dumps(patch_data, sort_keys=True, indent=4, separators=(',', ': ')))
                                except Exception as e:
                                    traceback.print_exc()
                                    logger.error(f'Error occurred: {e}')
                                    failed_cases.append([f'{r}/{r}-{i}', f, bf, f"{e}"])
                        except Exception as e:
                            traceback.print_exc()
                            logger.error(f'Error occurred: {e}')
                            failed_cases.append([f'{r}/{r}-{i}', f, f"{e}"])
        elif benchmark == 'typebugs':
            failed_cases = []
            for r in tqdm(metadata, desc = 'Generate prompt for instances'):
                if r in ["core/core-8065", "salt/salt-56381"]:
                    continue
                #if r != "pandas/pandas-22378":
                #    continue
                for f in metadata[r]["code_files"]:
                    if not f.endswith(".py"):
                        continue
                    try:
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
                            logger.debug('Handling File#{} in Case#{}'.format(bf, r))
                            final_patch_file_path = os.path.join(final_patch_path, r, bf.replace('/', '_').replace('.py', '.json'))
                            if os.path.exists(final_patch_file_path):
                                continue
                            path = os.path.join(patch_path, r, ('TypeErrorFix/benchmarks/typebugs/' + r + '/' + bf).replace('/', '_'))
                            buggy_file = os.path.join(benchmark_path, r, bf)
                            try:
                                patch_data = self.run_one(path, buggy_file, metadata[r]["buglines"][bf], metadata[r]["added"][bf], mask_all = mask_all)
                                if not os.path.exists(os.path.join(final_patch_path, r)):
                                    os.system('mkdir -p {}'.format(os.path.join(final_patch_path, r)))
                                with open(final_patch_file_path, 'w', encoding = 'utf-8') as pf:
                                    pf.write(json.dumps(patch_data, sort_keys=True, indent=4, separators=(',', ': ')))
                            except Exception as e:
                                traceback.print_exc()
                                logger.error(f'Error occurred: {e}')
                                failed_cases.append([r, f, bf, f"{e}"])
                    except Exception as e:
                        traceback.print_exc()
                        logger.error(f'Error occurred: {e}')
                        failed_cases.append([r, f, f"{e}"])
        
        with open(os.path.join(final_patch_path, "failed_cases.json"), "w", encoding = "utf-8") as ff:
            ff.write(json.dumps(failed_cases, sort_keys=True, indent=4, separators=(',', ': ')))
        


if __name__ == "__main__":
    prompt = Prompt()
    #prompt.run_all("TypeErrorFix/benchmarks/all_bug_info_typebugs.json", "patches_v2/typebugs", "TypeErrorFix/benchmarks/typebugs", "prompt_patches_v2_base_mask_all/typebugs", benchmark = "typebugs", mask_all = True)
    prompt.run_all("TypeErrorFix/benchmarks/all_bug_info_bugsinpy.json", "patches_v2/bugsinpy", "TypeErrorFix/benchmarks/bugsinpy", "prompt_patches_v2_base_mask_all/bugsinpy", benchmark = "bugsinpy", mask_all = True)