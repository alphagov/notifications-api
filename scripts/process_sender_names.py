# ruff: noqa: T201
import csv
import sys

print("Processing header names")


reader = csv.reader(sys.stdin)
headers = next(reader)
column_for_vertical = headers.index("Vertical:")
column_for_sender_id = headers.index("SenderID:")

sender_ids = []

for line in reader:
    # We don't want to forbid people using government sender ids
    if line[column_for_vertical] != "Government and Healthcare":
        if len(line[column_for_sender_id].split(",")[0]) > 0:
            # Sender_ids are comma seperated in the spreadsheet so split them
            new_sender_ids = line[column_for_sender_id].lower().split(",")
            # Do the split/join dance to remove whitespace
            new_sender_ids = ("".join(x.split()) for x in new_sender_ids)
            # Sometimes there are trailing commas remove them
            new_sender_ids = filter(lambda x: x != "", new_sender_ids)
            sender_ids = sender_ids + list(new_sender_ids)


joined_sender_ids = "'),('".join(sender_ids)
print(f"INSERT INTO protected_sender_ids VALUES ('{ joined_sender_ids}') ON CONFLICT DO NOTHING;")
