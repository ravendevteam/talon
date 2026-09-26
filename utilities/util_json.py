import json


def load_json_file(path):
    with open(path, "rb") as source:
        return json.load(source)
