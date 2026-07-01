from datetime import datetime
from app import db
from app.utils.llm_handler import summarize_text_with_llm


def process_feedback_with_llm(fb_item):
    """
    Runs a Feedback row through the LLM and persists the raw result onto its
    sentiment/summary/constructive_criticism columns, committing the change.

    On failure (LLM error, bad JSON, missing key), the columns are left as-is
    (None if never processed before) so the next read retries instead of
    permanently caching a failure.

    Returns the (sentiment, summary, constructive_criticism) tuple - raw values,
    with no display formatting (e.g. no sentiment emoji) applied.
    """
    feedback_input_dict = {
        'anon_identifier': fb_item.anon_identifier or 'Tidak disebutkan',
        'context_text': fb_item.context_text or 'Tidak disebutkan',
        'feedback_text': fb_item.feedback_text
    }

    try:
        llm_response_dict = summarize_text_with_llm(
            item_to_summarise=feedback_input_dict,
            model_provider="anthropic"
        )

        sentiment = llm_response_dict.get("sentiment", "")
        summary = llm_response_dict.get("summary", "")
        criticism = llm_response_dict.get("constructiveCriticism", "")

        if not sentiment or "error" in sentiment.lower() or "could not process" in summary.lower():
            # LLM indicated a failure - don't cache it, let the next read retry.
            return fb_item.sentiment, fb_item.summary, fb_item.constructive_criticism

        fb_item.sentiment = sentiment
        fb_item.summary = summary
        fb_item.constructive_criticism = criticism
        db.session.commit()

    except (ValueError, NotImplementedError) as e:
        print(f"LLM configuration error for feedback ID {fb_item.id}: {e}")
    except Exception as e:
        print(f"Error processing feedback ID {fb_item.id} with LLM: {e}")

    return fb_item.sentiment, fb_item.summary, fb_item.constructive_criticism


def format_sentiment_for_display(raw_sentiment):
    """Adds a UX emoji suffix to a raw sentiment string without mutating stored data."""
    if not raw_sentiment:
        return "Netral Aja 😐"
    lowered = raw_sentiment.lower()
    if "positif" in lowered:
        return f"{raw_sentiment} 👍"
    if "negatif" in lowered:
        return f"{raw_sentiment} 😟"
    return f"{raw_sentiment} 😐"
