"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def _format_listing(item: dict, session: dict) -> str:
    """Format a listing dict into a readable multi-line string for the UI panel."""
    lines = []
    lines.append(f"📦 {item.get('title', 'Unknown item')}")
    lines.append(f"💰 ${item.get('price', '?'):.2f}  |  🛍 {item.get('platform', '').capitalize()}")
    lines.append(f"📐 Size: {item.get('size', 'N/A')}  |  ✅ Condition: {item.get('condition', 'N/A').capitalize()}")
    colors = ", ".join(item.get("colors", []))
    if colors:
        lines.append(f"🎨 Colors: {colors}")
    tags = ", ".join(item.get("style_tags", []))
    if tags:
        lines.append(f"🏷  Tags: {tags}")
    if item.get("brand"):
        lines.append(f"👕 Brand: {item['brand']}")
    lines.append("")
    lines.append(item.get("description", ""))

    # Surface any search adaptations
    parsed = session.get("parsed", {})
    if parsed.get("size_relaxed"):
        lines.append("")
        lines.append(f"ℹ️  No results for size '{session['parsed'].get('size', '')}' — showing results for all sizes.")

    all_results = session.get("search_results", [])
    if len(all_results) > 1:
        lines.append("")
        lines.append(f"🔍 Found {len(all_results)} matches total. Showing the best fit.")

    return "\n".join(lines)


def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:      The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of three strings: (listing_text, outfit_suggestion, fit_card).
        Each string maps to one of the three output panels in the UI.
    """
    # Guard: empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query (e.g. 'vintage graphic tee under $30').", "", ""

    # Select wardrobe
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # Run the planning loop
    try:
        session = run_agent(user_query, wardrobe)
    except Exception as exc:
        return f"Something went wrong: {exc}\n\nPlease check your GROQ_API_KEY in .env.", "", ""

    # If the loop aborted early, surface the error in the first panel
    if session.get("error"):
        return session["error"], "", ""

    # Format outputs for the three panels
    listing_text = _format_listing(session["selected_item"], session)
    outfit_text = session.get("outfit_suggestion") or "No outfit suggestions generated."
    fit_card_text = session.get("fit_card") or "No fit card generated."

    return listing_text, outfit_text, fit_card_text


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
