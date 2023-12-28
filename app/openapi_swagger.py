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
<script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.1.1/crypto-js.min.js"></script>
<script>
    function base64url(source) {
        // Encode in classical base64
        let encodedSource = CryptoJS.enc.Base64.stringify(source);

        // Remove padding equal characters
        encodedSource = encodedSource.replace(/=+$/, '');

        // Replace characters according to base64url specifications
        encodedSource = encodedSource.replace(/\\+/g, '-');
        encodedSource = encodedSource.replace(/\\//g, '_');

        return encodedSource;
    }

    function createNotifyJWT(service_id, secret) {
        // Set headers for JWT
        let header = {
            'typ': 'JWT',
            'alg': 'HS256'
        };

        // Prepare timestamp in seconds
        let currentTimestamp = Math.floor(Date.now() / 1000);

        let data = {
            'iss': service_id,
            'iat': currentTimestamp
        };

        // encode header
        let stringifiedHeader = CryptoJS.enc.Utf8.parse(JSON.stringify(header));
        let encodedHeader = base64url(stringifiedHeader);

        // encode data
        let stringifiedData = CryptoJS.enc.Utf8.parse(JSON.stringify(data));
        let encodedData = base64url(stringifiedData);

        // build token
        let token = `${encodedHeader}.${encodedData}`;

        // sign token
        let signature = CryptoJS.HmacSHA256(token, secret);
        signature = base64url(signature);

        return `${token}.${signature}`;
    }

    function overrideAuthenticationHeader(request)
    {
        let authHeader = request.headers.Authorization;
        if (authHeader !== undefined && authHeader.startsWith('Basic ')) {
            let base64_username_and_password = authHeader.substring(6);
            let [username, password] = atob(base64_username_and_password).split(':');
            let jwt = createNotifyJWT(username, password);
            request.headers.Authorization = `Bearer ${jwt}`;
        } else if (authHeader && authHeader.startsWith('Bearer ')) {
            let apiKey = authHeader.substring(7);
            let serviceUuid = apiKey.substring(apiKey.length - (36 + 1 + 36), apiKey.length - (36 + 1));
            let secretUuid = apiKey.substring(apiKey.length - 36, apiKey.length);
            let jwt = createNotifyJWT(serviceUuid, secretUuid);
            request.headers.Authorization = `Bearer ${jwt}`;
        }
        return request;
    }

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
            showCommonExtensions: true,
            requestInterceptor: overrideAuthenticationHeader,
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
