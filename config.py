import os
from dotenv import load_dotenv
import groq
import openai

load_dotenv()

TG_API_ID = int(os.environ["TG_API_ID"])
TG_API_HASH = os.environ["TG_API_HASH"]
TG_PHONE = os.environ["TG_PHONE"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]
MAX_CHATS = int(os.getenv("MAX_CHATS", "1000"))
KEYWORD_MIN_SCORE = int(os.getenv("KEYWORD_MIN_SCORE", "2"))

GROQ_MODEL = "llama-3.1-8b-instant"
NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

groq_client = groq.AsyncGroq(api_key=GROQ_API_KEY)
nvidia_client = openai.AsyncOpenAI(
    base_url=NVIDIA_BASE_URL,
    api_key=NVIDIA_API_KEY,
)
