# Telegram Cover Letter Bot

An intelligent Telegram bot that automatically generates personalized cover letters based on your CV and job descriptions. The bot uses OpenAI's GPT models to create professional, tailored cover letters in both Russian and English.

## Features

- 🤖 **AI-Powered**: Uses OpenAI GPT-4 models for intelligent cover letter generation
- 🌍 **Multilingual**: Supports both Russian and English languages
- 📝 **Personalized**: Creates tailored cover letters based on your CV and job requirements
- 💬 **Easy to Use**: Simple Telegram interface with intuitive commands
- 🔄 **Smart Language Detection**: Automatically detects and maintains language consistency
- 📱 **Telegram Integration**: Works seamlessly within Telegram messenger

## How It Works

1. **CV Storage**: Send your CV to the bot, and it will store it for future use
2. **Job Analysis**: Send any job posting, and the bot analyzes the requirements
3. **Cover Letter Generation**: The bot generates a personalized cover letter with:
   - Personalized greeting with your name and the position
   - "About Me" section based on your CV
   - "Why I'm a Good Fit" section matching job requirements to your experience
   - "Why I Want to Work Here" section based on company information
   - Contact information extracted from your CV

## Commands

- `/start` - Initialize the bot and get started
- `/reset` - Clear your saved CV and start over
- `/show_cv` - View your currently saved CV (first 500 characters)

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (get from [@BotFather](https://t.me/botfather))
- OpenAI API Key (get from [OpenAI Platform](https://platform.openai.com/))

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd telegram-cover-letter-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file in the project root:
   ```env
   BOT_TOKEN=your_telegram_bot_token_here
   OPENAI_API_KEY=your_openai_api_key_here
   ```

4. **Update the main.py file**
   
   Replace the placeholder tokens in `main.py` with your actual tokens:
   ```python
   BOT_TOKEN = "your_actual_bot_token"
   OPENAI_API_KEY = "your_actual_openai_api_key"
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

### Environment Variables (Recommended)

For better security, use environment variables instead of hardcoding tokens:

```python
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
```

If you choose this approach, add `python-dotenv==1.0.0` to your `requirements.txt`.

## Usage

1. **Start the bot**: Send `/start` to your bot
2. **Upload your CV**: Send your CV as a text message
3. **Send job postings**: Send any job description, and the bot will generate a personalized cover letter
4. **Manage your CV**: Use `/reset` to update your CV or `/show_cv` to view it

## Project Structure

```
telegram-cover-letter-bot/
├── main.py              # Main bot application
├── requirements.txt     # Python dependencies
├── README.md           # Project documentation
├── .env                # Environment variables (create this)
└── .gitignore          # Git ignore file
```

## Security Notes

⚠️ **Important**: Never commit your actual API keys to version control. Use environment variables or `.env` files that are excluded from Git.

## Dependencies

- `python-telegram-bot==20.7` - Telegram Bot API wrapper
- `openai==1.3.7` - OpenAI API client
- `nest-asyncio==1.5.8` - Asyncio support for Jupyter/IPython environments

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

If you encounter any issues or have questions, please open an issue on GitHub.

## Disclaimer

This bot is for educational and personal use. Always review generated cover letters before sending them to potential employers. The bot uses AI-generated content, which should be verified for accuracy and appropriateness. 