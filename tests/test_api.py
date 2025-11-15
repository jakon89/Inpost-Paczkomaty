import pytest
import pytest_socket

from custom_components.inpost_paczkomaty.api import InPostApi


@pytest.fixture()
def _allow_inpost_requests():
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["inpost.pl"])


@pytest.mark.parametrize("expected_lingering_timers", [True])
@pytest.mark.api
async def test_parcel_lockers_list(hass, _allow_inpost_requests):
    response = await InPostApi(hass).get_parcel_lockers_list()
    assert response is not None
