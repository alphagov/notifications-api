from flask import url_for


def pagination_links(pagination, endpoint, **kwargs):
    if 'page' in kwargs:
        kwargs.pop('page', None)
    links = {}
    if pagination.has_prev:
        links['prev'] = url_for(endpoint, page=pagination.prev_num, **kwargs)
    if pagination.has_next:
        links['next'] = url_for(endpoint, page=pagination.next_num, **kwargs)
        links['last'] = url_for(endpoint, page=pagination.pages, **kwargs)
    return links


def url_with_token(data, url, config):
    from notifications_utils.url_safe_token import generate_token
    token = generate_token(data, config['SECRET_KEY'], config['DANGEROUS_SALT'])
    base_url = config['ADMIN_BASE_URL'] + url
    return base_url + token
