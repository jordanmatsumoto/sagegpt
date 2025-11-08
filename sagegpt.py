import json
from dotenv import load_dotenv
from openai import OpenAI
import gradio as gr
import base64
from io import BytesIO
from PIL import Image
from pydub import AudioSegment
from pydub.playback import play

# Load env and set constants
load_dotenv(override=True)
MODEL = "gpt-4o-mini"
openai = OpenAI()

# Define the system message for guiding behavior
system_message =  """You are SageGPT, a helpful technical tutor who answers 
questions about code, software engineering, data science, and LLMs. 
Provide clear, concise answers and include code examples when relevant.
If you don't know the answer, say so."""

# Dictionary of code snippets
code_snippets = {
    "python_list_comprehension": "squares = [x**2 for x in range(10)]",
    "pandas_groupby": "df.groupby('column').sum()",
    "llm_prompt_example": "prompt = 'Translate English to French'"
}

def get_code_snippet(topic):
    """Return a short code snippet for a given technical topic."""
    return code_snippets.get(topic.lower(), "No snippet available for this topic.")

# Define the metadata describing the get_code_snippet tool for the assistant
code_snippet_tool = {
    "name": "get_code_snippet",
    "description": "Return a short Python code snippet for a given technical topic.",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The technical topic for which to return a code snippet"
            }
        },
        "required": ["topic"],
        "additionalProperties": False
    }
}

# Include the tool in the assistant's available tools list
tools = [{"type": "function", "function": code_snippet_tool}]

def handle_tool_call(message):
    """Execute the code snippet tool requested by the model."""
    tool_call = message.tool_calls[0]
    arguments = json.loads(tool_call.function.arguments)
    topic = arguments.get("topic")
    snippet = get_code_snippet(topic)

    response = {
        "role": "tool",
        "content": json.dumps({"topic": topic, "snippet": snippet}),
        "tool_call_id": tool_call.id,
    }
    
    return response, topic

def artist(topic):
    """Generate a technical diagram or illustration for a given topic using DALL·E 3."""    
    image_response = openai.images.generate(
        model="dall-e-3",
        prompt=(
            f"A clear, illustrative diagram explaining the technical concept: {topic}, "
            f"in a clean and professional style"
        ),
        size="1024x1024",
        n=1,
        response_format="b64_json",
    )
    
    image_base64 = image_response.data[0].b64_json
    image_data = base64.b64decode(image_base64)
    return Image.open(BytesIO(image_data))

def talker(message, save_audio=False):
    """Convert text to speech and play it using the TTS model."""    
    response = openai.audio.speech.create(
        model="tts-1",
        voice="onyx",
        input=message
    )
    
    audio_stream = BytesIO(response.content)
    audio = AudioSegment.from_file(audio_stream, format="mp3")
    play(audio)

    # Optionally save the audio file.
    if save_audio:
        audio.export("sagegpt_response.mp3", format="mp3")

def chat_multimodal(history, voice_enabled, image_enabled):
    """
    Handle a conversation with the assistant, including text, tool calls,
    image generation, and optional speech output.
    """   
    messages = [{"role": "system", "content": system_message}] + history
    image = None
    last_user_message = history[-1]["content"].lower()

    # Direct image generation if user explicitly asks and toggle is on
    if image_enabled and any(word in last_user_message for word in ["image", "diagram", "illustration", "picture"]):
        image = artist(last_user_message)
        reply = "Here’s the image you requested!"
        history += [{"role": "assistant", "content": reply}]
        return history, image

    # Normal chat flow using model and tool calls
    response = openai.chat.completions.create(model=MODEL, messages=messages, tools=tools)

    if response.choices[0].finish_reason == "tool_calls":
        message = response.choices[0].message
        response, topic = handle_tool_call(message)
        messages.append(message)
        messages.append(response)
        # Only generate image if toggle is on
        if image_enabled:
            image = artist(topic)
        response = openai.chat.completions.create(model=MODEL, messages=messages)
    
    reply = response.choices[0].message.content
    history += [{"role": "assistant", "content": reply}]    

    # Only play audio if the toggle is enabled
    if voice_enabled:
        talker(reply, save_audio=True)
    
    return history, image

# Create Gradio UI
with open("assets/icons/sagegpt_icon.png", "rb") as f:
    icon_b64 = base64.b64encode(f.read()).decode()

theme = gr.themes.Soft(
    primary_hue="green",
).set(
    body_background_fill="#f8fafc",
    block_border_width="2px",
    block_shadow="0 2px 12px rgba(0,0,0,0.08)"
)

with gr.Blocks(theme=theme, title="SageGPT") as ui:

    with gr.Row():
        gr.Markdown(
            f"""
            <div style="
                display:flex;
                flex-direction:column;
                align-items:center;
                justify-content:center;
            ">
                <div style="
                    background:#f8fafc;
                    padding:0.5em;
                    border-radius:12px;
                    display:flex;
                    justify-content:center;
                    align-items:center;
                ">
                    <img src="data:image/png;base64,{icon_b64}" width="200" height="200" style="display:block;"/>
                </div>
                <p style="color:#2e7d32; font-size:1.1em; text-align:center; margin:0.5em 0 0 0;">
                    Your AI coding tutor — multimodal, smart, and elegant.
                </p>
            </div>
            """,
            elem_id="title"
        )

    # Chatbot display and image output
    with gr.Row(equal_height=True):
        chatbot = gr.Chatbot(height=550, type="messages", label="Chat")
        image_output = gr.Image(height=550, label="Generated Image", elem_classes="gr-box")
    
    # User input textbox
    with gr.Row():
        entry = gr.Textbox(
            label="Ask SageGPT a question:",
            placeholder="e.g. Explain transformers, or show a Pandas groupby example...",
            scale=9,
        )

        # Voice and image toggle boxes
        with gr.Column(scale=1):
            voice_toggle = gr.Checkbox(value=True, label="Enable voice replies")
            image_toggle = gr.Checkbox(value=True, label="Enable generated images")
    
    # Clear button
    with gr.Row():
        clear = gr.Button("Clear Conversation")

    chatbot.value = [
        {"role": "assistant", "content": "Hi, I'm SageGPT — your AI tutor! What would you like to learn today?"}
    ]

    def do_entry(message, history):
        """Append the user's message to the conversation history."""
        history += [{"role": "user", "content": message}]
        return "", history

    # Submit the user message and then handle chat response
    entry.submit(
        do_entry, inputs=[entry, chatbot], outputs=[entry, chatbot]
    ).then(
        chat_multimodal, inputs=[chatbot, voice_toggle, image_toggle], outputs=[chatbot, image_output]
    )

    # Clear conversation history
    clear.click(lambda: None, inputs=None, outputs=chatbot, queue=False)

    gr.Markdown(
        """
        <p style='text-align:center; font-size:0.85em; color:gray; margin-top:2em;'>
        © 2025 SageGPT — Built by Jordan Matsumoto with OpenAI & Gradio
        </p>
        """
    )

ui.launch(share=True, inbrowser=True)