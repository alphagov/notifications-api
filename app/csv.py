import csv


def get_recipient_from_csv(file_data):
    numbers = []
    reader = csv.DictReader(
        file_data.splitlines(),
        lineterminator='\n',
        quoting=csv.QUOTE_NONE)
    for i, row in enumerate(reader):
        numbers.append(row['to'].replace(' ', ''))
    return numbers
