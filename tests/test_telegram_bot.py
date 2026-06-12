from unittest.mock import MagicMock
from marketbot.telegram_bot import split_message, send_message


def test_split_message_under_limit_single_chunk():
    chunks = split_message("hello", limit=4096)
    assert chunks == ["hello"]


def test_split_message_splits_on_newlines():
    text = "\n".join("line%d" % i for i in range(1000))
    chunks = split_message(text, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_send_message_posts_to_each_chat():
    session = MagicMock()
    resp = MagicMock(); resp.status_code = 200; resp.json.return_value = {"ok": True}
    session.post.return_value = resp
    send_message("TOKEN", ["111", "222"], "hi", session=session, parse_mode="HTML")
    assert session.post.call_count == 2
    url = session.post.call_args_list[0].args[0]
    assert "botTOKEN/sendMessage" in url


def test_send_message_retries_on_failure():
    session = MagicMock()
    bad = MagicMock(); bad.status_code = 500; bad.json.return_value = {"ok": False}
    good = MagicMock(); good.status_code = 200; good.json.return_value = {"ok": True}
    session.post.side_effect = [bad, good]
    send_message("TOKEN", ["111"], "hi", session=session, retries=2, backoff=0)
    assert session.post.call_count == 2
