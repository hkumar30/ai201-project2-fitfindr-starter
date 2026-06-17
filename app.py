"""
app.py

Gradio interface for FitFindr. Calls run_agent() and maps the session dict
to five output panels: listing, outfit, fit card, price assessment, and
trend report.

Run with:
    python app.py

Then open the URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(
    user_query: str,
    wardrobe_choice: str,
) -> tuple[str, str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:      The text the user typed into the search box.
        wardrobe_choice: "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of five strings mapped to the five output panels:
            (listing_text, outfit_suggestion, fit_card,
             price_assessment, trend_report)
    """
    # Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query to get started.", "", "", "", ""

    # Select wardrobe
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    # Run the agent
    session = run_agent(user_query.strip(), wardrobe)

    # Surface error if the agent stopped early
    if session["error"]:
        return session["error"], "", "", "", ""

    # Format the top listing
    item = session["selected_item"]
    brand_line = f"Brand: {item['brand']}\n" if item.get("brand") else ""
    retry_line = f"⚠️ {session['retry_info']}\n\n" if session.get("retry_info") else ""
    listing_text = (
        f"{retry_line}"
        f"{item['title']}\n"
        f"Price: ${item['price']:.2f}\n"
        f"Platform: {item['platform']}\n"
        f"Size: {item['size']}\n"
        f"Condition: {item['condition']}\n"
        f"{brand_line}"
        f"Style: {', '.join(item['style_tags'])}\n"
        f"Colors: {', '.join(item['colors'])}"
    )

    return (
        listing_text,
        session["outfit_suggestion"],
        session["fit_card"],
        session.get("price_assessment") or "",
        session.get("trend_report") or "",
    )


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
    "vintage graphic tee size XXXS under $20",  # triggers retry logic
]


def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas, price context, and trend analysis.
Describe what you're looking for — include size and price to filter results.
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

        # Row 1: core outputs
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

        # Row 2: stretch feature outputs
        with gr.Row():
            price_output = gr.Textbox(
                label="💰 Price assessment",
                lines=5,
                interactive=False,
            )
            trend_output = gr.Textbox(
                label="🔥 Trend report",
                lines=5,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        outputs = [
            listing_output, outfit_output, fitcard_output,
            price_output, trend_output,
        ]

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
