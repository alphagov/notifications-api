import os
import subprocess
from zipfile import ZipFile

import psycopg2


# Step 1: Get DB Connection Details
def get_db_connection_details():
    try:
        print("Running the command to get connection details...")
        result = subprocess.run(
            ["gds", "aws", "notify-prod", "--", "db-connect.sh", "notifydb", "-s"],
            capture_output=True,
            text=True,
            timeout=30,  # Timeout after 30 seconds
        )

        output = result.stdout.strip()
        error_output = result.stderr.strip()

        if output:
            print("Standard Output:", output)
        if error_output:
            print("Error Output:", error_output)

        if not output:
            print("No output from the command.")
            return {}

        connection_details = {}

        for line in output.split("\n"):
            if "Host" in line:
                connection_details["PGHOST"] = line.split(": ")[1].strip()
            if "Port" in line:
                connection_details["PGPORT"] = line.split(": ")[1].strip()
            if "Database" in line:
                connection_details["PGDATABASE"] = line.split(": ")[1].strip()
            if "Username" in line:
                connection_details["PGUSER"] = line.split(": ")[1].strip()
            if "Password" in line:
                connection_details["PGPASSWORD"] = line.split(": ")[1].strip()

        print(f"Extracted connection details: {connection_details}")
        return connection_details

    except subprocess.TimeoutExpired:
        print("Error: The command to get connection details timed out.")
        return {}


# Step 2: Connect to the database
def connect_to_db():
    print("Attempting to get DB connection details...")

    conn_details = get_db_connection_details()
    if not conn_details:
        print("Error: Could not retrieve connection details.")
        return None

    try:
        print("Attempting to establish DB connection...")
        conn = psycopg2.connect(
            host=conn_details.get("PGHOST"),
            port=conn_details.get("PGPORT"),
            user=conn_details.get("PGUSER"),
            password=conn_details.get("PGPASSWORD"),
            dbname=conn_details.get("PGDATABASE"),
        )
        print("DB connection established successfully.")
        return conn
    except Exception as e:
        print(f"Error: Failed to connect to the database. {e}")
        return None


# Step 3: Fetch data in chunks with pagination
def fetch_data_in_chunks(service_id, notification_type, created_at, chunk_size=10000):
    # Establish DB connection
    conn = connect_to_db()

    # Cursor to execute SQL queries
    cur = conn.cursor()

    # # Start the offset and a flag to check if more data exists
    # offset = 0
    # more_data = True
    #
    # # Create file name based on timestamp and service ID
    # timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    # csv_file_path = f'~/Downloads/batch_report_{service_id}_{timestamp}.csv'
    # csv_file_full_path = os.path.expanduser(csv_file_path)
    #
    # # Open the CSV file for writing
    # with open(csv_file_full_path, mode='w', newline='') as csv_file:
    #     csv_writer = csv.writer(csv_file)
    #
    #     # Write the header row
    #     csv_writer.writerow(['Recipient', 'Reference', 'Template', 'Type', 'Sent by', 'Job', 'Status', 'Time', 'API key ID'])
    #
    #     while more_data:
    #         # Query to fetch data in chunks with LIMIT and OFFSET
    #         query = f"""
    #         SELECT
    #             normalised_to,
    #             client_reference,
    #             template_id,
    #             notification_type,
    #             created_by_id,
    #             job_id,
    #             notification_status,
    #             created_at,
    #             api_key_id
    #         FROM notifications
    #         WHERE service_id = '{service_id}'
    #         AND notification_type = '{notification_type}'
    #         AND created_at > '{created_at}'
    #         ORDER BY created_at DESC
    #         LIMIT {chunk_size} OFFSET {offset};
    #         """
    #
    #         # Execute the query
    #         cur.execute(query)
    #
    #         # Fetch the rows
    #         rows = cur.fetchall()
    #
    #         # If no more rows, stop fetching
    #         if not rows:
    #             more_data = False
    #         else:
    #             # Write rows to the CSV file
    #             csv_writer.writerows(rows)
    #             # Update the offset for the next batch
    #             offset += chunk_size

    # Close the DB connection
    cur.close()
    conn.close()

    return

    # return csv_file_full_path


# Step 4: Compress the CSV to .zip
def compress_csv(csv_file_path):
    zip_file_path = csv_file_path.replace(".csv", ".zip")
    with ZipFile(zip_file_path, "w") as zipf:
        zipf.write(csv_file_path, os.path.basename(csv_file_path))
    return zip_file_path


# Step 7: Execute full process
def process_large_data(service_id, notification_type, created_at):
    print("Starting data download to CSV")

    csv_file_path = fetch_data_in_chunks(service_id, notification_type, created_at, chunk_size=10000)

    print("Finished data download to CSV, starting file compression")

    zip_file_path = compress_csv(csv_file_path)

    print(f"Data fetched, CSV saved and compressed to: {zip_file_path}")

    print(f"Please manually send {zip_file_path} via email and delete zip file from your environment.")


# Step 8: Input the dynamic values
service_id_input = "636af21d-ee64-49b5-9ab6-68ce4547b456"
notification_type_input = "sms"
created_at_input = "2024-09-09 23:59:59"  # Retention limit

# process_large_data(service_id_input, notification_type_input, created_at_input)

connect_to_db()
