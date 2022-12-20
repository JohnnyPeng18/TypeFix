import json
import os



class PatchGenerator(object):
    def __init__(self, template_file):
        self.id2template = {}
        self.top_templates = []

        self.load_templates(template_file)


    
    def load_templates(self, jsonfile):
        mined_info = json.loads(open(jsonfile, 'r', encoding = 'utf-8').read())
        instance_num = {}

        for i in mined_info["templates"]:
            self.id2template[i] = FixTemplate.load(mind_info["templates"][i])

        for i in mined_info["mined"]:
            num = len(self.id2template[i].instances)
            if num not in instance_num:
                instance_num[num] = i
        sorted_instance_num = sorted(instance_num.items(), key = lambda item: item[0])
        for s in sorted_instance_num:
            self.top_templates += s[1]


    def locate_bug(self):
        pass


    def select_template(self, top_template):
        pass


    def select_templates(self):
        pass


    def run_one(self):
        pass


    def run_all(self):
        pass