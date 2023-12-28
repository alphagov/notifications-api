swagger_html_string = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Swagger UI</title>
    <link rel="shortcut icon" href="static/images/swagger.svg">
    <link rel="stylesheet" type="text/css" href="static/css/swagger-ui.css">
    <style>
        html {
            box-sizing: border-box;
            overflow: -moz-scrollbars-vertical;
            overflow-y: scroll;
        }

        *, *:before, *:after {
            box-sizing: inherit;
        }

        body {
            margin: 0;
            background: #fafafa;
        }
    </style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="static/js/swagger-ui-bundle.js"></script>
<script src="static/js/swagger-ui-standalone-preset.js"></script>
<script>
    window.onload = function () {
        // Begin Swagger UI call region
        window.ui = SwaggerUIBundle({
            url: "{{api_doc_url}}",
            dom_id: "#swagger-ui",
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIStandalonePreset
            ],
            plugins: [
                SwaggerUIBundle.plugins.DownloadUrl
            ],
            layout: "StandaloneLayout",
            docExpansion: "{{ doc_expansion }}",
            showExtensions: true,
            showCommonExtensions: true
        })
        // End Swagger UI call region
        const oauthConfig = JSON.parse(`{{ oauth_config|tojson }}`);
        if (oauthConfig != null) {
            window.ui.initOAuth({
                clientId: oauthConfig.clientId,
                clientSecret: oauthConfig.clientSecret,
                realm: oauthConfig.realm,
                appName: oauthConfig.appName,
                scopeSeparator: oauthConfig.scopeSeparator,
                scopes: oauthConfig.scopes,
                additionalQueryStringParams: oauthConfig.additionalQueryStringParams,
                usePkceWithAuthorizationCodeGrant: oauthConfig.usePkceWithAuthorizationCodeGrant
            })
        }
        const prefix = "flask-openapi3&"
        // authorize
        const old_authorize = window.ui.authActions.authorize;
        window.ui.authActions.authorize = function (security) {
            old_authorize(security)
            for (const key in security) {
                window.localStorage.setItem(prefix + key, JSON.stringify(security[key]))
            }
        }
        // logout
        const old_logout = window.ui.authActions.logout;
        window.ui.authActions.logout = function (security) {
            old_logout(security)
            for (const key of security) {
                window.localStorage.removeItem(prefix + key)
            }
        }
        // reload authorizations
        for (let i = 0; i < localStorage.length; i++) {
            let key = localStorage.key(i)
            const value = JSON.parse(localStorage.getItem(key))
            key = key.replace(prefix, "")
            const security = {}
            security[key] = value
            old_authorize(security)
        }
    }
</script>
</body>
</html>
"""
