from app.aws.s3 import get_list_of_files_by_suffix, get_s3_file


zip_bucket_name = 'development-letters-pdf'
zip_sub_folder = '2018-01-11'
zip_file_name = '2018-01-11/NOTIFY.20180111175007.ZIP'
ack_bucket_name = 'development-letters-pdf'
ack_subfolder = 'root/dispatch'
ack_file_name = 'root/dispatch/NOTIFY.20180111175733.ACK.txt'

# Tests for boto3 and s3, can only perform locally against the Tools aws account and have permissions to access S3.
# The tests are based on the above folders and files already uploaded to S3 Tools aws account (If these are removed or
# renamed, the tests won't pass.


def test_get_zip_files():
    zip_file_list = []
    for key in get_list_of_files_by_suffix(bucket_name=zip_bucket_name, subfolder=zip_sub_folder, suffix='.ZIP'):
        print('File: ' + key)
        zip_file_list.append(key)
    assert zip_file_name in zip_file_list


def test_get_ack_files():
    ack_file_list = []
    for key in get_list_of_files_by_suffix(bucket_name=ack_bucket_name, subfolder=ack_subfolder, suffix='.ACK.txt'):
        print('File: ' + key)
        ack_file_list.append(key)
    assert ack_file_name in ack_file_list


def test_get_file_content():
    ack_file_list = []
    for key in get_list_of_files_by_suffix(bucket_name=ack_bucket_name, subfolder=ack_subfolder, suffix='.ACK.txt'):
        ack_file_list.append(key)
    assert ack_file_name in key

    todaystr = '20180111'
    for key in ack_file_list:
        if todaystr in key:
            content = get_s3_file(ack_bucket_name, key)
            print(content)


def test_letter_ack_file_parse_content_correctly():
    # Test ack files are stripped correctly. In the acknowledgement file, there should be 2 zip files,
    # 'NOTIFY.20180111175007.ZIP','NOTIFY.20180111175008.ZIP'.
    zip_file_list = ['NOTIFY.20180111175007.ZIP', 'NOTIFY.20180111175008.ZIP', 'NOTIFY.20180111175009.ZIP']
    # get acknowledgement file
    ack_file_list = []
    for key in get_list_of_files_by_suffix(bucket_name=ack_bucket_name, subfolder=ack_subfolder, suffix='.ACK.txt'):
        ack_file_list.append(key)

    for key in ack_file_list:
        if '20180111' in key:
            content = get_s3_file(ack_bucket_name, key)
            print(content)
            for zip_file in content.split():  # iterate each line
                s = zip_file.split('|')
                print(s[0])
                for zf in zip_file_list:
                    if s[0] in zf:
                        zip_file_list.remove(zf)

    print('zip_file_list: ' + str(zip_file_list))
    assert zip_file_list == ['NOTIFY.20180111175009.ZIP']
