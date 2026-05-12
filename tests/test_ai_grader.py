from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.services.ai_grader import GradingResult, RubricItem, grade_homework

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_hw_details(prompt="Explain recursion", accepted_formats=None):
    m = MagicMock()
    m.prompt = prompt
    m.reference_answer = "A function that calls itself"
    m.grading_criteria = "Clarity and correctness"
    return m


def _make_assignment(max_score=10):
    m = MagicMock()
    m.max_score = max_score
    return m


def _make_submission(text="My answer", attachments=None):
    return {
        "assignment_id": 1,
        "widget_id": 1,
        "payload": {
            "text": text,
            "markdown": "",
            "attachments": attachments or [],
        },
    }


def _fake_grading_result():
    return GradingResult(
        score=7,
        feedback="Good explanation, but missing examples",
        rubric_breakdown=[
            RubricItem(criterion="Clarity", points=4, max_points=5, comment="Clear"),
            RubricItem(criterion="Correctness", points=3, max_points=5, comment="Mostly correct"),
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_grade_homework_text_only():
    fake_result = _fake_grading_result()
    mock_response = MagicMock()
    mock_response.parsed = fake_result

    with patch("app.services.ai_grader.get_genai_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = await grade_homework(
            _make_submission("Recursion is when a function calls itself"),
            _make_hw_details(),
            _make_assignment(),
        )

    assert result.score == 7
    assert "Good explanation" in result.feedback
    assert len(result.rubric_breakdown) == 2
    mock_client.models.generate_content.assert_called_once()


async def test_grade_homework_with_pdf_attachment():
    fake_result = _fake_grading_result()
    mock_response = MagicMock()
    mock_response.parsed = fake_result

    pdf_bytes = b"%PDF-fake"
    submission = _make_submission(
        text="See attached",
        attachments=[{"s3_key": "submissions/1/abc/file.pdf", "mime": "application/pdf"}],
    )

    with patch("app.services.ai_grader.get_genai_client") as mock_client_fn, \
         patch("app.services.storage.download_object", new_callable=AsyncMock, return_value=pdf_bytes):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = await grade_homework(submission, _make_hw_details(), _make_assignment())

    assert result.score == 7
    # generate_content receives content with 2 parts: text + pdf
    call_args = mock_client.models.generate_content.call_args
    contents = call_args.kwargs["contents"]
    assert len(contents[0].parts) == 2


async def test_grade_homework_raises_on_none_parsed():
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = "invalid json"

    with patch("app.services.ai_grader.get_genai_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_fn.return_value = mock_client

        with pytest.raises(ValueError, match="unparseable"):
            await grade_homework(_make_submission(), _make_hw_details(), _make_assignment())


async def test_grade_homework_api_error_propagates():
    with patch("app.services.ai_grader.get_genai_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API unavailable")
        mock_client_fn.return_value = mock_client

        with pytest.raises(RuntimeError, match="API unavailable"):
            await grade_homework(_make_submission(), _make_hw_details(), _make_assignment())
