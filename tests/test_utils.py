"""Tests for utility functions."""

import base64
import json
import time

from custom_components.inpost_paczkomaty.utils import (
    camel_to_snake,
    convert_keys_to_snake_case,
    decode_jwt_payload,
    get_language_code,
    haversine,
    is_token_expiring_soon,
)


class TestCamelToSnake:
    """Tests for camel_to_snake function."""

    def test_simple_camel_case(self):
        """Test simple camelCase conversion."""
        assert camel_to_snake("camelCase") == "camel_case"

    def test_multiple_words(self):
        """Test multiple words in camelCase."""
        assert camel_to_snake("thisIsATest") == "this_is_a_test"

    def test_with_numbers(self):
        """Test camelCase with numbers."""
        assert camel_to_snake("test123Value") == "test123_value"

    def test_pascal_case(self):
        """Test PascalCase conversion."""
        assert camel_to_snake("PascalCase") == "pascal_case"

    def test_already_snake_case(self):
        """Test string already in snake_case."""
        assert camel_to_snake("already_snake") == "already_snake"

    def test_single_word_lowercase(self):
        """Test single lowercase word."""
        assert camel_to_snake("word") == "word"

    def test_acronyms(self):
        """Test strings with acronyms."""
        assert camel_to_snake("shipmentNumber") == "shipment_number"
        assert camel_to_snake("pickUpPoint") == "pick_up_point"


class TestConvertKeysToSnakeCase:
    """Tests for convert_keys_to_snake_case function."""

    def test_simple_dict(self):
        """Test simple dictionary conversion."""
        data = {"camelCase": "value", "anotherKey": 123}
        result = convert_keys_to_snake_case(data)
        assert result == {"camel_case": "value", "another_key": 123}

    def test_nested_dict(self):
        """Test nested dictionary conversion."""
        data = {"outerKey": {"innerKey": "value", "anotherInner": {"deepKey": "deep"}}}
        result = convert_keys_to_snake_case(data)
        assert result == {
            "outer_key": {"inner_key": "value", "another_inner": {"deep_key": "deep"}}
        }

    def test_list_of_dicts(self):
        """Test list of dictionaries conversion."""
        data = [{"firstName": "John"}, {"lastName": "Doe"}]
        result = convert_keys_to_snake_case(data)
        assert result == [{"first_name": "John"}, {"last_name": "Doe"}]

    def test_dict_with_list(self):
        """Test dictionary containing a list."""
        data = {"parcels": [{"shipmentNumber": "123"}, {"shipmentNumber": "456"}]}
        result = convert_keys_to_snake_case(data)
        assert result == {
            "parcels": [{"shipment_number": "123"}, {"shipment_number": "456"}]
        }

    def test_primitive_values(self):
        """Test that primitive values are returned unchanged."""
        assert convert_keys_to_snake_case("string") == "string"
        assert convert_keys_to_snake_case(123) == 123
        assert convert_keys_to_snake_case(None) is None
        assert convert_keys_to_snake_case(True) is True

    def test_empty_structures(self):
        """Test empty dict and list."""
        assert convert_keys_to_snake_case({}) == {}
        assert convert_keys_to_snake_case([]) == []

    def test_inpost_api_response_structure(self):
        """Test with structure similar to InPost API response."""
        data = {
            "updatedUntil": "2025-12-30T08:42:55.488Z",
            "more": False,
            "parcels": [
                {
                    "shipmentNumber": "695080086580180027785172",
                    "shipmentType": "parcel",
                    "openCode": "689756",
                    "pickUpPoint": {
                        "name": "GDA117M",
                        "addressDetails": {"postCode": "80-180", "city": "Gdańsk"},
                    },
                    "status": "DELIVERED",
                }
            ],
        }
        result = convert_keys_to_snake_case(data)

        assert result["updated_until"] == "2025-12-30T08:42:55.488Z"
        assert result["more"] is False
        assert len(result["parcels"]) == 1
        assert result["parcels"][0]["shipment_number"] == "695080086580180027785172"
        assert result["parcels"][0]["pick_up_point"]["name"] == "GDA117M"
        assert (
            result["parcels"][0]["pick_up_point"]["address_details"]["post_code"]
            == "80-180"
        )


class TestGetLanguageCode:
    """Tests for get_language_code function."""

    def test_polish(self):
        """Test Polish language code."""
        assert get_language_code("pl") == "pl-PL"

    def test_english(self):
        """Test English language code."""
        assert get_language_code("en") == "en-US"

    def test_unknown_language(self):
        """Test unknown language defaults to English."""
        assert get_language_code("de") == "en-US"
        assert get_language_code("fr") == "en-US"

    def test_none(self):
        """Test None defaults to English."""
        assert get_language_code(None) == "en-US"

    def test_empty_string(self):
        """Test empty string defaults to English."""
        assert get_language_code("") == "en-US"


class TestHaversine:
    """Tests for haversine function."""

    def test_same_point(self):
        """Test distance between same point is zero."""
        result = haversine(18.58508, 54.3188, 18.58508, 54.3188)
        assert result == 0.0

    def test_known_distance(self):
        """Test known distance between two cities (Gdańsk to Warsaw approx 300km)."""
        # Gdańsk coordinates
        gdansk_lon, gdansk_lat = 18.6466, 54.3520
        # Warsaw coordinates
        warsaw_lon, warsaw_lat = 21.0122, 52.2297

        result = haversine(gdansk_lon, gdansk_lat, warsaw_lon, warsaw_lat)

        # Distance should be approximately 280-320 km
        assert 280 < result < 320

    def test_short_distance(self):
        """Test short distance calculation."""
        # Two points in Gdańsk (GDA117M and GDA08M)
        result = haversine(18.58508, 54.3188, 18.58358, 54.32854)

        # Should be around 1-2 km
        assert 0.5 < result < 2.0


def _create_jwt_token(payload: dict) -> str:
    """Helper to create a JWT token for testing."""
    # JWT consists of header.payload.signature
    header = {"alg": "RS256", "kid": "test-key"}
    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    # Signature doesn't matter for our tests
    signature = "fake_signature"
    return f"{header_b64}.{payload_b64}.{signature}"


class TestDecodeJwtPayload:
    """Tests for decode_jwt_payload function."""

    def test_decode_valid_token(self):
        """Test decoding a valid JWT token."""
        payload = {"sub": "user123", "exp": 1234567890, "iat": 1234560690}
        token = _create_jwt_token(payload)

        result = decode_jwt_payload(token)

        assert result is not None
        assert result["sub"] == "user123"
        assert result["exp"] == 1234567890
        assert result["iat"] == 1234560690

    def test_decode_token_with_special_chars(self):
        """Test decoding a token with special characters in payload."""
        payload = {"name": "Jan Kowalski", "email": "test@example.com"}
        token = _create_jwt_token(payload)

        result = decode_jwt_payload(token)

        assert result is not None
        assert result["name"] == "Jan Kowalski"
        assert result["email"] == "test@example.com"

    def test_decode_invalid_token_format(self):
        """Test decoding an invalid token format."""
        assert decode_jwt_payload("invalid") is None
        assert decode_jwt_payload("only.two") is None
        assert decode_jwt_payload("") is None

    def test_decode_token_with_invalid_base64(self):
        """Test decoding a token with invalid base64."""
        result = decode_jwt_payload("header.!!!invalid!!!.signature")
        assert result is None

    def test_decode_token_with_invalid_json(self):
        """Test decoding a token with invalid JSON in payload."""
        # Create a token with non-JSON payload
        header_b64 = base64.urlsafe_b64encode(b'{"alg":"RS256"}').decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(b"not json").decode().rstrip("=")
        token = f"{header_b64}.{payload_b64}.signature"

        result = decode_jwt_payload(token)
        assert result is None


class TestIsTokenExpiringSoon:
    """Tests for is_token_expiring_soon function."""

    def test_token_not_expiring(self):
        """Test token that is not expiring soon."""
        # Token expires in 2 hours
        exp = int(time.time()) + 7200
        token = _create_jwt_token({"exp": exp})

        result = is_token_expiring_soon(token)

        assert result is False

    def test_token_expiring_within_buffer(self):
        """Test token expiring within buffer period."""
        # Token expires in 5 minutes (less than 10 minute buffer)
        exp = int(time.time()) + 300
        token = _create_jwt_token({"exp": exp})

        result = is_token_expiring_soon(token)

        assert result is True

    def test_token_already_expired(self):
        """Test already expired token."""
        # Token expired 5 minutes ago
        exp = int(time.time()) - 300
        token = _create_jwt_token({"exp": exp})

        result = is_token_expiring_soon(token)

        assert result is True

    def test_token_expiring_exactly_at_buffer(self):
        """Test token expiring exactly at buffer boundary."""
        # Token expires exactly at buffer time
        exp = int(time.time()) + 600
        token = _create_jwt_token({"exp": exp})

        result = is_token_expiring_soon(token)

        assert result is True

    def test_token_expiring_just_after_buffer(self):
        """Test token expiring just after buffer period."""
        # Token expires 1 second after buffer
        exp = int(time.time()) + 600 + 1
        token = _create_jwt_token({"exp": exp})

        result = is_token_expiring_soon(token)

        assert result is False

    def test_custom_buffer_seconds(self):
        """Test with custom buffer seconds."""
        # Token expires in 30 minutes
        exp = int(time.time()) + 1800
        token = _create_jwt_token({"exp": exp})

        # With 10 minute buffer (default), should not be expiring
        assert is_token_expiring_soon(token, buffer_seconds=600) is False

        # With 60 minute buffer, should be expiring
        assert is_token_expiring_soon(token, buffer_seconds=3600) is True

    def test_token_without_exp_claim(self):
        """Test token without expiration claim."""
        token = _create_jwt_token({"sub": "user123"})

        result = is_token_expiring_soon(token)

        # Should return True (fail-safe) when no exp claim
        assert result is True

    def test_invalid_token_returns_true(self):
        """Test invalid token returns True (fail-safe behavior)."""
        result = is_token_expiring_soon("invalid.token")

        # Should return True to trigger refresh attempt
        assert result is True

    def test_empty_token_returns_true(self):
        """Test empty token returns True (fail-safe behavior)."""
        result = is_token_expiring_soon("")

        assert result is True

    def test_real_jwt_token_format(self):
        """Test with a token similar to real InPost JWT."""
        # Real InPost token structure
        payload = {
            "market": "Poland",
            "sub": "0631cf03-38ff-4302-8200-9c47a8ccd680",
            "aud": "inpost-mobile",
            "nbf": int(time.time()),
            "phone": "123456789",
            "azp": "inpost-mobile",
            "scope": ["openid"],
            "iss": "https://account.inpost-group.com",
            "exp": int(time.time()) + 7200,  # 2 hours from now
            "iat": int(time.time()),
            "jti": "b3293dbc-cd39-44aa-ba88-3886fe5d641b",
            "phone_prefix": "+48",
        }
        token = _create_jwt_token(payload)

        result = is_token_expiring_soon(token)

        assert result is False
