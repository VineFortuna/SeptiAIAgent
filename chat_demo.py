from dotenv import load_dotenv
load_dotenv()

from bot import ClassAssistant

bot = ClassAssistant()
phone = input("Test phone number [+14165550100]: ").strip() or "+14165550100"

print("Type 'quit' to stop.\n")
while True:
    message = input("You: ").strip()
    if message.lower() == "quit":
        break
    print(f"Bot: {bot.reply(message, phone)}\n")
