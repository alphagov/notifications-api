def test_all_routes_have_authentication(client):
    # This tests that each blueprint registered on the application has a before_request function registered.
    # The None row is removed from the comparison as that is not blueprint specific but app specific.
    before_req_funcs = set(x for x in client.application.before_request_funcs if x is not None)

    blueprint_names = set(client.application.blueprints.keys())
    assert blueprint_names == before_req_funcs

    routes_blueprint_names = set([x.split('.')[0] for x in client.application.view_functions.keys()])

    # The static route is always available by default for a Flask app to serve anything in the static folder.
    routes_blueprint_names.remove('static')

    # The metrics route is not protected by auth as it's available to be scraped by Prometheus
    routes_blueprint_names.remove('metrics')
    assert sorted(blueprint_names) == sorted(routes_blueprint_names)
