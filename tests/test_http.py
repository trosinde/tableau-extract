import pytest
import requests
import responses

from tableau_extract.http import DEFAULT_USER_AGENT, HttpError, PoliteClient

URL = "https://tableau.example.org/t/x/views/WB/S"


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(ft: FakeTime) -> PoliteClient:
    return PoliteClient(sleep=ft.sleep, clock=ft.clock)


@responses.activate
def test_user_agent_and_ok_logged() -> None:
    responses.get(URL, body="ok")
    ft = FakeTime()
    c = make_client(ft)
    r = c.get(URL, label="vizql")
    assert r.text == "ok"
    assert responses.calls[0].request.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert c.log[-1].ok and c.log[-1].status == 200


@responses.activate
def test_retry_on_503_with_backoff() -> None:
    responses.get(URL, status=503)
    responses.get(URL, status=503)
    responses.get(URL, body="ok")
    ft = FakeTime()
    r = make_client(ft).get(URL, label="vizql")
    assert r.status_code == 200
    assert len(responses.calls) == 3
    assert ft.sleeps[:1] == [2.0]
    assert 4.0 in ft.sleeps


@responses.activate
def test_retry_gives_up_after_three_retries() -> None:
    for _ in range(4):
        responses.get(URL, status=503)
    ft = FakeTime()
    with pytest.raises(HttpError) as ei:
        make_client(ft).get(URL, label="vizql")
    assert ei.value.attempt.status == 503
    assert len(responses.calls) == 4


@responses.activate
def test_retry_after_header_respected() -> None:
    responses.get(URL, status=429, headers={"Retry-After": "7"})
    responses.get(URL, body="ok")
    ft = FakeTime()
    make_client(ft).get(URL, label="vizql")
    assert 7.0 in ft.sleeps


@responses.activate
def test_no_retry_on_403() -> None:
    responses.get(
        URL,
        status=403,
        body="<HTML><HEAD><TITLE>ERROR: The request could not be satisfied</TITLE></HEAD></HTML>",
        headers={"Server": "CloudFront"},
    )
    ft = FakeTime()
    c = make_client(ft)
    with pytest.raises(HttpError) as ei:
        c.get(URL, label="csv")
    assert len(responses.calls) == 1
    assert ei.value.attempt.status == 403
    assert "CloudFront" in ei.value.attempt.message
    assert "could not be satisfied" in ei.value.attempt.message
    assert c.log[-1].ok is False


@responses.activate
def test_404_missing_view_message() -> None:
    responses.get(URL + ".csv", status=404, json={"type": "missing-view"})
    with pytest.raises(HttpError) as ei:
        make_client(FakeTime()).get(URL + ".csv", label="csv")
    assert "missing-view" in ei.value.attempt.message


@responses.activate
def test_login_redirect_detected() -> None:
    responses.get(URL, status=302, headers={"Location": "/signin?redirect=x"})
    with pytest.raises(HttpError) as ei:
        make_client(FakeTime()).get(URL, label="vizql")
    assert "Anmeldung erforderlich" in ei.value.attempt.message
    assert len(responses.calls) == 1


@responses.activate
def test_normal_redirect_followed() -> None:
    responses.get(URL, status=302, headers={"Location": URL + "?:embed=y"})
    responses.get(URL + "?:embed=y", body="ok")
    r = make_client(FakeTime()).get(URL, label="vizql")
    assert r.text == "ok"


@responses.activate
def test_throttle_one_request_per_second_per_host() -> None:
    responses.get(URL, body="a")
    responses.get(URL, body="b")
    ft = FakeTime()
    c = make_client(ft)
    c.get(URL, label="x")
    ft.now += 0.25
    c.get(URL, label="x")
    assert ft.sleeps == [pytest.approx(0.75)]


@responses.activate
def test_timeout_retried() -> None:
    responses.get(URL, body=requests.Timeout("zu langsam"))
    responses.get(URL, body="ok")
    ft = FakeTime()
    assert make_client(ft).get(URL, label="x").text == "ok"
    assert ft.sleeps[0] == 2.0


def test_min_interval_never_below_one_second() -> None:
    assert PoliteClient(min_interval=0.1).min_interval == 1.0
