import pytest


@pytest.mark.asyncio
async def test_login_success(client):
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"
    assert body["email"] == "admin@brokerbridge.local"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_login_failure(client):
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "wrong"},
    )
    assert r.status_code == 401
    body = r.json()
    assert body["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_providers_require_auth(client):
    r = await client.get("/api/v1/admin/providers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_openapi_documents_admin_providers_auth_errors(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = spec["paths"]

    list_op = paths["/api/v1/admin/providers"]["get"]
    assert "401" in list_op["responses"]
    assert "403" in list_op["responses"]
    assert list_op["security"] == [{"OAuth2PasswordBearer": []}]
    assert "OAuth2PasswordBearer" in spec["components"]["securitySchemes"]

    get_op = paths["/api/v1/admin/providers/{kind}"]["get"]
    assert "401" in get_op["responses"]
    assert "403" in get_op["responses"]
    assert "404" in get_op["responses"]

    put_op = paths["/api/v1/admin/providers/{kind}"]["put"]
    assert "401" in put_op["responses"]
    assert "403" in put_op["responses"]
    assert "404" in put_op["responses"]
    assert "422" in put_op["responses"]

    token_op = paths["/api/v1/auth/token"]["post"]
    assert "401" in token_op["responses"]


def _json_media(response: dict) -> dict:
    return response["content"]["application/json"]


def _json_example(response: dict) -> dict | list:
    return _json_media(response)["example"]


def _assert_not_type_placeholder(value: object) -> None:
    """Swagger falls back to type samples like \"string\" when examples are missing."""
    assert value != "string"
    assert value != "integer"
    assert value != "boolean"


@pytest.mark.asyncio
async def test_openapi_response_examples_are_realistic(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    schemas = r.json()["components"]["schemas"]

    list_media = _json_media(paths["/api/v1/admin/providers"]["get"]["responses"]["200"])
    assert "example" in list_media
    assert "examples" in list_media
    list_200 = list_media["example"]
    assert isinstance(list_200, list)
    assert list_200[0]["kind"] == "infrastructure"
    _assert_not_type_placeholder(list_200[0]["kind"])
    assert list_200[0]["config"]["api_key"] == "***"
    assert "additionalProp1" not in list_200[0]["config"]
    assert list_200[1]["kind"] == "broker_default"
    assert list_media["examples"]["success"]["value"][0]["kind"] == "infrastructure"

    list_401 = _json_example(paths["/api/v1/admin/providers"]["get"]["responses"]["401"])
    assert list_401["error_code"] == "UNAUTHORIZED"
    _assert_not_type_placeholder(list_401["error_code"])
    assert list_401["message"] == "Not authenticated"
    assert list_401["request_id"]
    assert "additionalProp1" not in list_401.get("details", {})

    list_403 = _json_example(paths["/api/v1/admin/providers"]["get"]["responses"]["403"])
    assert list_403["error_code"] == "FORBIDDEN"
    _assert_not_type_placeholder(list_403["error_code"])

    get_404 = _json_example(paths["/api/v1/admin/providers/{kind}"]["get"]["responses"]["404"])
    assert get_404["error_code"] == "NOT_FOUND"

    put_422 = _json_example(paths["/api/v1/admin/providers/{kind}"]["put"]["responses"]["422"])
    assert put_422["error_code"] == "PROVIDER_VALIDATION_FAILED"

    token_200 = _json_example(paths["/api/v1/auth/token"]["post"]["responses"]["200"])
    assert token_200["token_type"] == "bearer"
    assert token_200["role"] == "admin"
    assert token_200["email"] == "admin@brokerbridge.local"

    live_200 = _json_example(paths["/health/live"]["get"]["responses"]["200"])
    assert live_200 == {"status": "ok"}

    ready_200 = _json_example(paths["/health/ready"]["get"]["responses"]["200"])
    assert ready_200["status"] == "ok"
    assert "postgres" in ready_200["checks"]

    app_422 = _json_example(paths["/api/v1/admin/providers"]["get"]["responses"]["422"])
    assert app_422["error_code"] == "VALIDATION_ERROR"
    app_500 = _json_example(paths["/api/v1/admin/providers"]["get"]["responses"]["500"])
    assert app_500["error_code"] == "INTERNAL_ERROR"

    # Component schemas must expose singular example (not type-only samples).
    assert schemas["ErrorResponse"]["example"]["error_code"] == "UNAUTHORIZED"
    _assert_not_type_placeholder(schemas["ErrorResponse"]["example"]["error_code"])
    assert schemas["ProviderConfigResponse"]["example"]["kind"] == "infrastructure"
    _assert_not_type_placeholder(schemas["ProviderConfigResponse"]["example"]["kind"])
