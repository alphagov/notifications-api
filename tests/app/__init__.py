import os


def load_example_csv(file):
    file_path = os.path.join("test_csv_files", "{}.csv".format(file))
    with open(file_path) as f:
        return f.read()
