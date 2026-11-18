from services import weather as weather_service


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_get_weather_data_with_invalid_template_falls_back(monkeypatch):
    payload = {
        "code": "200",
        "daily": [
            {
                "textDay": "晴",
                "textNight": "多云",
                "tempMax": "30",
                "tempMin": "20",
                "windDirDay": "东风",
                "windScaleDay": "3",
            }
        ],
    }

    monkeypatch.setattr(weather_service.requests, "get", lambda *args, **kwargs: DummyResponse(payload))

    message = weather_service.get_weather_data(
        city_name="北京",
        nickname="小明",
        api_key="k",
        api_host="example.com",
        location_id="101010100",
        message_template="Hi {nickname} {missing_var}",
    )

    assert message is not None
    assert "小明" in message


def test_get_weather_data_returns_none_for_invalid_payload(monkeypatch):
    payload = {"code": "200", "daily": []}
    monkeypatch.setattr(weather_service.requests, "get", lambda *args, **kwargs: DummyResponse(payload))

    message = weather_service.get_weather_data(
        city_name="北京",
        nickname="小明",
        api_key="k",
        api_host="example.com",
        location_id="101010100",
    )

    assert message is None

