# ruff: noqa: T201
import csv
import sys

print("Processing header names")


reader = csv.reader(sys.stdin)
headers = [header.replace("\ufeff", "") for header in next(reader)]
column_for_sender_id = headers.index("Sender ID")

sender_ids: list[str] = []

for line in reader:
    if len(line[column_for_sender_id]) > 0:
        # Do the split/join dance to remove whitespace
        sender_id = "".join(line[column_for_sender_id].lower().split())
        if sender_id != "":
            sender_ids.append(sender_id)


joined_sender_ids = "'),('".join(sender_ids)
print(f"INSERT INTO protected_sender_ids VALUES ('{joined_sender_ids}') ON CONFLICT DO NOTHING;")
