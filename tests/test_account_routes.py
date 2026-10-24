"""The Account screen has canonical endpoints and hidden bookmark/API aliases."""

import pytest

from sibyl.api.routes import router


@pytest.mark.parametrize("suffix", ["", "/accounts"])
def test_account_routes_share_implementation_with_legacy_alias(client, suffix):
    canonical = f"/api/v1/account{suffix}"
    legacy = f"/api/v1/portfolio{suffix}"
    routes = {"/api/v1" + route.path: route for route in router.routes}
    assert routes[canonical].endpoint is routes[legacy].endpoint
    assert routes[canonical].include_in_schema
    assert not routes[legacy].include_in_schema
    assert client.get(canonical).status_code == 200
    assert client.get(legacy).status_code == 200
