from bs4 import BeautifulSoup


def cap_xml_to_dict(cap_xml):
    # This function assumes that it’s being passed valid CAP XML
    cap = BeautifulSoup(cap_xml, "xml")
    return {
        "reference": cap.alert.identifier.text,
        "category": cap.alert.info.category.text,
        "expires": cap.alert.info.expires.text,
        "content": cap.alert.info.description.text,
        "areas": [
            {
                "name": area.areaDesc.text,
                "polygons": [
                    cap_xml_polygon_to_list(polygon.text)
                    for polygon in area.find_all('polygon')
                ]
            }
            for area in cap.alert.info.find_all('area')
        ]
    }


def cap_xml_polygon_to_list(polygon_string):
    return [
        [
            float(coordinate) for coordinate in pair.split(',')
        ]
        for pair in polygon_string.split(' ')
    ]
