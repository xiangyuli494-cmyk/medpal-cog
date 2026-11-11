# eval_s1.py
import jsonlines

dataset_path = "eval/asset/s1_asset_eval.jsonl"

if __name__ == "__main__":
    with jsonlines.open(dataset_path, "r") as reader:
        for item in reader:
            print(item)
