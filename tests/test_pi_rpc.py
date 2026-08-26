import pytest

from socratic_partner.pi_rpc import PiRpcError, _raise_for_assistant_error


def test_rejects_settled_assistant_error() -> None:
    data = {
        "messages": [
            {
                "role": "assistant",
                "stopReason": "error",
                "errorMessage": "402 available credits exhausted",
                "content": [{"type": "text", "text": "Error: 402"}],
            }
        ]
    }

    with pytest.raises(PiRpcError, match="available credits"):
        _raise_for_assistant_error(data)


def test_accepts_successful_assistant_message() -> None:
    _raise_for_assistant_error(
        {
            "messages": [
                {
                    "role": "assistant",
                    "stopReason": "stop",
                    "content": [{"type": "text", "text": "A valid response"}],
                }
            ]
        }
    )
