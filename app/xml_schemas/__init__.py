from pathlib import Path

from lxml import etree


def validate_xml(document, schema_file_name):

    path = Path(__file__).resolve().parent / schema_file_name
    contents = path.read_text()

    schema_root = etree.XML(contents.encode('utf-8'))
    schema = etree.XMLSchema(schema_root)
    parser = etree.XMLParser(schema=schema)

    try:
        etree.fromstring(document, parser)
    except etree.XMLSyntaxError:
        return False

    return True
