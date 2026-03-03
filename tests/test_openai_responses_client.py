from openai_responses_client import extract_output_text


def test_extract_output_text_from_message_content() -> None:
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "hello "},
                    {"type": "output_text", "text": "world"},
                ],
            }
        ]
    }
    assert extract_output_text(response) == "hello world"
