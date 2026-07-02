import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _post(client, body="", from_="+14165559050", num_media=0, media_type=""):
    data = {"Body": body, "From": f"whatsapp:{from_}", "NumMedia": str(num_media)}
    if num_media > 0:
        data["MediaContentType0"] = media_type
        data["MediaUrl0"] = "https://api.twilio.com/fake-media"
    return client.post("/whatsapp", data=data)


def test_voice_note_gets_text_only_reply(client) -> None:
    rv = _post(client, num_media=1, media_type="audio/ogg")
    assert rv.status_code == 200
    assert b"text messages" in rv.data


def test_image_no_caption_gets_text_only_reply(client) -> None:
    rv = _post(client, num_media=1, media_type="image/jpeg")
    assert rv.status_code == 200
    assert b"text messages" in rv.data


def test_sticker_gets_text_only_reply(client) -> None:
    rv = _post(client, num_media=1, media_type="image/webp")
    assert rv.status_code == 200
    assert b"text messages" in rv.data


def test_image_with_caption_processes_normally(client) -> None:
    # Photo + caption: Body has the caption text so it should go through the normal path
    rv = _post(client, body="What classes do you offer?", from_="+14165550100", num_media=1, media_type="image/jpeg")
    assert rv.status_code == 200
    assert b"text messages" not in rv.data


def test_normal_text_message_processes_normally(client) -> None:
    rv = _post(client, body="Hi", from_="+14165559060")
    assert rv.status_code == 200
    assert b"text messages" not in rv.data
