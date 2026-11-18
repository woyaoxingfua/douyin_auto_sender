from core.config import normalize_config, normalize_friend


def test_normalize_friend_supports_legacy_city_field():
    friend = normalize_friend(
        {
            "nickname": "Alice",
            "city": "101010100",
            "avatar_image": "friend_avatars/alice.png",
        }
    )

    assert friend["location_id"] == "101010100"
    assert friend["city_name"] == "ID:101010100"


def test_normalize_config_filters_invalid_friends_and_reports_warning():
    config, warnings = normalize_config(
        {
            "api_host": "https://example.com/",
            "api_key": "abc",
            "friends": [
                {"nickname": "", "location_id": "123"},
                {"nickname": "Bob", "location_id": "456", "city_name": "上海", "avatar_image": "friend_avatars/bob.png"},
            ],
        }
    )

    assert config["api_host"] == "example.com"
    assert len(config["friends"]) == 1
    assert config["friends"][0]["nickname"] == "Bob"
    assert warnings

