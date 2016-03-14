import os


def load_example_csv(file):
    file_path = os.path.join("test_csv_files", "{}.csv".format(file))
    with open(file_path) as f:
        return f.read()


def load_example_ses(file):
    file_path = os.path.join("test_ses_responses", "{}.json".format(file))
    with open(file_path) as f:
        return f.read()
