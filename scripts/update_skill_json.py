# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import shutil
from os.path import dirname, join
from pprint import pprint

from ovos_skills_manager.local_skill import get_skill_data_from_directory
from neon_utils.file_utils import parse_skill_readme_file
from neon_utils.configuration_utils import dict_merge

skill_dir = dirname(dirname(__file__))

_invalid_skill_data_keys = ("appstore", "appstore_url", "credits",
                            "skill_id")
_invalid_readme_keys = ("contact support", "details")

default_skill = {"title": "",
                 "url": "",
                 "summary": "",
                 "short_description": "",
                 "description": "",
                 "examples": [],
                 "desktopFile": False,
                 "warning": "",
                 "systemDeps": False,
                 "requirements": {
                     "python": [],
                     "system": {},
                     "skill": []
                 },
                 "incompatible_skills": [],
                 "platforms": ["i386",
                               "x86_64",
                               "ia64",
                               "arm64",
                               "arm"],
                 "branch": "master",
                 "license": "",
                 "icon": "",
                 "category": "",
                 "categories": [],
                 "tags": [],
                 "credits": [],
                 "skillname": "",
                 "authorname": "",
                 "foldername": None}


def get_skill_license():
    with open(join(skill_dir, "LICENSE.md")) as f:
        contents = f.read()
    if "BSD-3" in contents:
        return "BSD-3-Clause"
    if "Apache License" in contents:
        return "Apache 2.0"
    if "Neon AI Non-commercial Friendly License 2.0" in contents:
        return "Neon 2.0"
    if "Neon AI Non-commercial Friendly License" in contents:
        return "Neon 1.0"


def get_skill_json():
    print(f"skill_dir={skill_dir}")
    skill_json = join(skill_dir, "skill.json")
    backup = join(skill_dir, "skill_json.bak")
    shutil.move(skill_json, backup)
    skill_data = get_skill_data_from_directory(skill_dir)
    shutil.move(backup, skill_json)
    skill_data['foldername'] = None
    for key in _invalid_skill_data_keys:
        if key in skill_data:
            skill_data.pop(key)
    readme_data = parse_skill_readme_file(join(skill_dir, "README.md"))
    for key in _invalid_readme_keys:
        if key in readme_data:
            readme_data.pop(key)
    # readme_data["description"] = readme_data.pop("details")
    readme_data["short_description"] = readme_data.get("summary")
    readme_data["license"] = get_skill_license()
    readme_data["branch"] = "master"
    skill_data = dict_merge(default_skill, skill_data)
    combined = dict_merge(skill_data, readme_data)
    pprint(combined)
    try:
        with open(skill_json) as f:
            current = json.load(f)
    except:
        current = None
    if current != combined:
        print("Skill Updated. Writing skill.json")
        with open(skill_json, 'w+') as f:
            json.dump(combined, f, indent=4)
    else:
        print("No changes to skill.json")


if __name__ == "__main__":
    get_skill_json()
