import os


def load_example_csv(file):
    file_path = os.path.join("test_csv_files", f"{file}.csv")
    with open(file_path) as f:
        return f.read()
