import os
from typing import Dict

import requests

from .plugin import Plugin


class DeeplTranslatePlugin(Plugin):
    """
    A plugin to translate a given text from a language to another, using DeepL
    """

    def __init__(self):
            deepl_api_key = os.getenv('DEEPL_API_KEY')
            deepl_api_pro = os.getenv('DEEPL_API_PRO', 'false').lower() == 'true'
            if not deepl_api_key or not deepl_api_pro:
                raise ValueError('DEEPL_API_KEY and DEEPL_API_PLAN environment variable must be set to use DeepL Plugin')
            self.api_key = deepl_api_key
            self.api_pro = deepl_api_pro

    def get_source_name(self) -> str:
        return "DeepL Translate"

    def get_spec(self) -> [Dict]:
        return [{
            "name": "translate",
            "description": "Translate a given text from a language to another",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to translate"},
                    "to_language": {"type": "string", "description": "The language to translate to (e.g. 'it')"}
                },
                "required": ["text", "to_language"],
            },
        }]

    async def execute(self, function_name, **kwargs) -> Dict:
        if self.api_pro:
            url = "https://api.deepl.com/v2/translate"
        else:
            url = "https://api-free.deepl.com/v2/translate"
             
        headers = {
            "Authorization": f"DeepL-Auth-Key {self.api_key}",
            "User-Agent": "chatgpt-telegram-bot/0.2.7",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "text": kwargs['text'],
            "target_lang": kwargs['to_language']
        }

        return requests.post(url, headers=headers, data=data).json()["translations"][0]["text"]